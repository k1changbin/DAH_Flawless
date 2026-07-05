"""Runtime Mutation Policy enforcement for simulated observe mutations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dah_flawless.config import DEFAULT_MUTATION_PROFILE


RUNTIME_POLICY_ID = "dah.mutation_policy.v0_1.runtime"
DEFAULT_POLICY_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "mutation_policy.yaml"


@dataclass(frozen=True)
class RuntimeFieldPolicy:
    policy_id: str
    paths: tuple[str, ...]
    mutation_kind: str
    profiles: dict[str, dict[str, Any]]
    allowed_values: tuple[Any, ...] = ()


@dataclass(frozen=True)
class MutationPolicyDecision:
    policy_id: str
    path: str
    approved: bool
    action: str
    reason: str
    requested_value: Any
    applied_value: Any
    requested_delta: Any = None
    applied_delta: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MutationPolicyEnforcer:
    """Clamp or reject field mutations before the Mutation Engine writes them."""

    def __init__(self, profile: str = DEFAULT_MUTATION_PROFILE):
        self.profile = profile
        self._decisions: list[MutationPolicyDecision] = []

    @property
    def decisions(self) -> list[MutationPolicyDecision]:
        return list(self._decisions)

    def decision_dicts(self) -> list[dict[str, Any]]:
        return [decision.to_dict() for decision in self._decisions]

    def add_value(
        self,
        root: dict[str, Any],
        path: str,
        requested_delta: int | float,
        *,
        value_min: int | float | None = None,
        value_max: int | float | None = None,
    ) -> int | float:
        policy = self._policy_for(path)
        before = _get_path(root, path)
        if policy is None:
            self._reject(path, before, before, "no runtime field policy")
            return 0

        applied_delta = self._cap_delta(requested_delta, policy)
        after = before + applied_delta
        after = _cap_value(after, value_min=value_min, value_max=value_max)
        applied_delta = after - before
        _set_path(root, path, after)
        self._record(policy, path, before + requested_delta, after, requested_delta, applied_delta)
        return applied_delta

    def set_with_delta_limit(
        self,
        root: dict[str, Any],
        path: str,
        requested_value: int | float,
        *,
        value_min: int | float | None = None,
        value_max: int | float | None = None,
    ) -> int | float:
        before = _get_path(root, path)
        requested_delta = requested_value - before
        applied_delta = self.add_value(
            root,
            path,
            requested_delta,
            value_min=value_min,
            value_max=value_max,
        )
        return before + applied_delta

    def set_absolute(
        self,
        root: dict[str, Any],
        path: str,
        requested_value: int | float,
        *,
        value_min: int | float | None = None,
        value_max: int | float | None = None,
    ) -> int | float:
        policy = self._policy_for(path)
        before = _get_path(root, path)
        if policy is None:
            self._reject(path, requested_value, before, "no runtime field policy")
            return before

        applied_value = self._cap_absolute(requested_value, policy)
        applied_value = _cap_value(applied_value, value_min=value_min, value_max=value_max)
        _set_path(root, path, applied_value)
        self._record(
            policy,
            path,
            requested_value,
            applied_value,
            requested_value - before if _is_number(before) and _is_number(requested_value) else None,
            applied_value - before if _is_number(before) and _is_number(applied_value) else None,
        )
        return applied_value

    def set_enum(self, root: dict[str, Any], path: str, requested_value: Any) -> Any:
        policy = self._policy_for(path)
        before = _get_path(root, path)
        if policy is None:
            self._reject(path, requested_value, before, "no runtime field policy")
            return before

        allowed = self._allowed_values(policy)
        if requested_value not in allowed:
            self._reject(path, requested_value, before, f"value not allowed by {policy.policy_id}")
            return before

        _set_path(root, path, requested_value)
        self._record(policy, path, requested_value, requested_value, None, None)
        return requested_value

    def set_priority_vector(self, root: dict[str, Any], path: str, requested_value: dict[str, float]) -> dict[str, float]:
        policy = self._policy_for(path)
        before = deepcopy(_get_path(root, path))
        if policy is None:
            self._reject(path, requested_value, before, "no runtime field policy")
            return before

        max_delta = float(self._profile_spec(policy).get("per_area_delta_max", 0.0))
        applied: dict[str, float] = {}
        requested_delta: dict[str, float] = {}
        applied_delta: dict[str, float] = {}
        for area, before_value in before.items():
            target = float(requested_value.get(area, before_value))
            delta = target - float(before_value)
            capped_delta = max(-max_delta, min(max_delta, delta))
            applied_value = round(_cap_value(float(before_value) + capped_delta, value_min=0.0, value_max=1.0), 3)
            applied[area] = applied_value
            requested_delta[area] = round(delta, 3)
            applied_delta[area] = round(applied_value - float(before_value), 3)

        _set_path(root, path, applied)
        self._record(policy, path, requested_value, applied, requested_delta, applied_delta)
        return applied

    def set_heartbeat_gap(self, root: dict[str, Any], path: str, requested_value: int) -> int:
        policy = self._policy_for(path)
        before = _get_path(root, path)
        if policy is None:
            self._reject(path, requested_value, before, "no runtime field policy")
            return before

        interval = int(root.get("comms", {}).get("heartbeat_interval_ms") or root.get("comms", {}).get("packet_interval_ms") or 1000)
        max_beats = int(self._profile_spec(policy).get("missed_beats_max", 0))
        max_value = max_beats * interval if max_beats else requested_value
        applied_value = min(int(requested_value), max_value)
        _set_path(root, path, applied_value)
        self._record(policy, path, requested_value, applied_value, requested_value - before, applied_value - before)
        return applied_value

    def _policy_for(self, path: str) -> RuntimeFieldPolicy | None:
        normalized = _normalize_path(path)
        if normalized.startswith("internal_observe.") or normalized.startswith("state.world.") or normalized.startswith("raw_world."):
            return None
        return FIELD_POLICY_BY_PATH.get(normalized)

    def _profile_spec(self, policy: RuntimeFieldPolicy) -> dict[str, Any]:
        return policy.profiles.get(self.profile) or policy.profiles.get(DEFAULT_MUTATION_PROFILE, {})

    def _cap_delta(self, requested_delta: int | float, policy: RuntimeFieldPolicy) -> int | float:
        spec = self._profile_spec(policy)
        lower = _first_matching_number(spec, ("delta_min",))
        upper = _first_matching_number(spec, ("delta_max",))
        if lower is None and upper is None:
            return requested_delta
        if lower is not None and upper is not None and lower < 0 < upper:
            return max(lower, min(upper, requested_delta))
        if upper is not None and upper > 0:
            if requested_delta < 0:
                return 0
            return min(upper, requested_delta)
        if lower is not None and lower < 0:
            if requested_delta > 0:
                return 0
            return max(lower, requested_delta)
        return requested_delta

    def _cap_absolute(self, requested_value: int | float, policy: RuntimeFieldPolicy) -> int | float:
        spec = self._profile_spec(policy)
        absolute_max = _first_matching_number(spec, ("absolute_max",))
        if absolute_max is not None and requested_value > absolute_max:
            return absolute_max
        absolute_min = _first_matching_number(spec, ("absolute_min",))
        if absolute_min is not None and requested_value < 0:
            return absolute_min
        return requested_value

    def _allowed_values(self, policy: RuntimeFieldPolicy) -> tuple[Any, ...]:
        spec = self._profile_spec(policy)
        if "allowed_values" in spec:
            return tuple(spec["allowed_values"])
        return policy.allowed_values

    def _record(
        self,
        policy: RuntimeFieldPolicy,
        path: str,
        requested_value: Any,
        applied_value: Any,
        requested_delta: Any,
        applied_delta: Any,
    ) -> None:
        action = "approved" if requested_value == applied_value and requested_delta == applied_delta else "clamped"
        self._decisions.append(
            MutationPolicyDecision(
                policy_id=policy.policy_id,
                path=_normalize_path(path),
                approved=True,
                action=action,
                reason=f"{policy.policy_id} allowed under {self.profile} profile",
                requested_value=deepcopy(requested_value),
                applied_value=deepcopy(applied_value),
                requested_delta=deepcopy(requested_delta),
                applied_delta=deepcopy(applied_delta),
            )
        )

    def _reject(self, path: str, requested_value: Any, applied_value: Any, reason: str) -> None:
        self._decisions.append(
            MutationPolicyDecision(
                policy_id=RUNTIME_POLICY_ID,
                path=_normalize_path(path),
                approved=False,
                action="rejected",
                reason=reason,
                requested_value=deepcopy(requested_value),
                applied_value=deepcopy(applied_value),
            )
        )


FALLBACK_FIELD_POLICIES: tuple[RuntimeFieldPolicy, ...] = (
    RuntimeFieldPolicy(
        "c2_latency_ms",
        ("comms.latency_ms",),
        "add_clamped",
        {
            "stealth": {"delta_min_ms": 50, "delta_max_ms": 250},
            "aggressive": {"delta_min_ms": 300, "delta_max_ms": 1200},
            "loud_demo": {"delta_min_ms": 1200, "delta_max_ms": 1800},
        },
    ),
    RuntimeFieldPolicy(
        "c2_packet_interval_jitter_ms",
        ("comms.packet_interval_jitter_ms",),
        "add_clamped",
        {
            "stealth": {"delta_min_ms": 50, "delta_max_ms": 150},
            "aggressive": {"delta_min_ms": 300, "delta_max_ms": 700},
            "loud_demo": {"delta_min_ms": 700, "delta_max_ms": 1000},
        },
    ),
    RuntimeFieldPolicy(
        "c2_packet_loss",
        ("comms.packet_loss",),
        "set_or_add_clamped",
        {
            "stealth": {"delta_min_ratio": 0.02, "delta_max_ratio": 0.05, "absolute_max": 0.08},
            "aggressive": {"absolute_min": 0.10, "absolute_max": 0.25},
            "loud_demo": {"absolute_min": 0.25, "absolute_max": 0.40},
        },
    ),
    RuntimeFieldPolicy(
        "c2_heartbeat_gap_ms",
        ("comms.heartbeat_gap_ms",),
        "set_clamped",
        {
            "stealth": {"missed_beats_min": 1, "missed_beats_max": 2},
            "aggressive": {"missed_beats_min": 3, "missed_beats_max": 5},
            "loud_demo": {"missed_beats_min": 5, "missed_beats_max": 8},
        },
    ),
    RuntimeFieldPolicy(
        "c2_sequence_number",
        ("c2_message.sequence_number",),
        "add_clamped",
        {
            "stealth": {"delta_min": -3, "delta_max": 3},
            "aggressive": {"delta_min": -12, "delta_max": 12},
            "loud_demo": {"delta_min": -24, "delta_max": 24},
        },
    ),
    RuntimeFieldPolicy(
        "c2_received_timestamp",
        ("time.received_timestamp",),
        "add_clamped_seconds",
        {
            "stealth": {"delta_min_s": -5, "delta_max_s": 5},
            "aggressive": {"delta_min_s": -60, "delta_max_s": 60},
            "loud_demo": {"delta_min_s": -400, "delta_max_s": 400},
        },
    ),
    RuntimeFieldPolicy(
        "c2_command",
        ("c2_message.command",),
        "set_enum",
        {
            "stealth": {"allowed_values": ["CONTINUE_MISSION", "RETURN_TO_BASE", "HOLD_POSITION"]},
            "aggressive": {"allowed_values": ["CONTINUE_MISSION", "RETURN_TO_BASE", "HOLD_POSITION", "ENTER_SAFE_MODE"]},
            "loud_demo": {"allowed_values": ["CONTINUE_MISSION", "RETURN_TO_BASE", "HOLD_POSITION", "ENTER_SAFE_MODE"]},
        },
        allowed_values=("CONTINUE_MISSION", "RETURN_TO_BASE", "HOLD_POSITION", "ENTER_SAFE_MODE"),
    ),
    RuntimeFieldPolicy(
        "c2_ack_sequence_number",
        ("c2_message.ack.sequence_number",),
        "add_clamped",
        {
            "stealth": {"delta_min": -1, "delta_max": 1},
            "aggressive": {"delta_min": -5, "delta_max": 5},
            "loud_demo": {"delta_min": -10, "delta_max": 10},
        },
    ),
    RuntimeFieldPolicy(
        "c2_ack_delay_ms",
        ("comms.ack_delay_ms",),
        "add_clamped",
        {
            "stealth": {"delta_min_ms": 100, "delta_max_ms": 300},
            "aggressive": {"delta_min_ms": 500, "delta_max_ms": 1200},
            "loud_demo": {"delta_min_ms": 1200, "delta_max_ms": 1800},
        },
    ),
    RuntimeFieldPolicy(
        "c2_auth_valid",
        ("c2_message.auth_valid",),
        "degrade_only",
        {
            "stealth": {"allowed": False},
            "aggressive": {"allowed": False},
            "loud_demo": {"allowed": False},
        },
        allowed_values=(False,),
    ),
    RuntimeFieldPolicy(
        "external_telemetry_battery_percent",
        ("telemetry.battery_percent",),
        "add_clamped",
        {
            "stealth": {"delta_min_percent": -8, "delta_max_percent": 8},
            "aggressive": {"delta_min_percent": -25, "delta_max_percent": 25},
            "loud_demo": {"absolute_min_percent": 0, "absolute_max_percent": 100},
        },
    ),
    RuntimeFieldPolicy(
        "external_telemetry_battery_drain_rate",
        ("telemetry.battery_drain_rate",),
        "add_clamped",
        {
            "stealth": {"delta_min": -0.3, "delta_max": 0.3},
            "aggressive": {"delta_min": -1.0, "delta_max": 1.0},
            "loud_demo": {"delta_min": -2.0, "delta_max": 2.0},
        },
    ),
    RuntimeFieldPolicy(
        "external_telemetry_motor_status",
        ("telemetry.motor_status",),
        "set_enum",
        {
            "stealth": {"allowed_values": ["DEGRADED", "UNKNOWN", "FAULT"]},
            "aggressive": {"allowed_values": ["OK", "DEGRADED", "FAULT", "UNKNOWN"]},
            "loud_demo": {"allowed_values": ["OK", "DEGRADED", "FAULT", "UNKNOWN"]},
        },
        allowed_values=("OK", "DEGRADED", "FAULT", "UNKNOWN"),
    ),
    RuntimeFieldPolicy(
        "mission_area_priority",
        ("mission.area_priority",),
        "vector_shift_normalized",
        {
            "stealth": {"per_area_delta_max": 0.15},
            "aggressive": {"per_area_delta_max": 0.45},
            "loud_demo": {"per_area_delta_max": 0.80},
        },
    ),
    RuntimeFieldPolicy(
        "mission_recommended_area",
        ("mission.recommended_area",),
        "set_enum",
        {
            "stealth": {"allowed_values": ["A", "B", "C", "NONE"]},
            "aggressive": {"allowed_values": ["A", "B", "C", "NONE"]},
            "loud_demo": {"allowed_values": ["A", "B", "C", "NONE"]},
        },
        allowed_values=("A", "B", "C", "NONE"),
    ),
)

def _normalize_path(path: str) -> str:
    normalized = path
    for prefix in ("blue_observed.", "external_observe."):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    if normalized.startswith("blue_observed.external_observe."):
        normalized = normalized[len("blue_observed.external_observe.") :]
    return normalized


def _split_path(path: str) -> list[str]:
    return _normalize_path(path).split(".")


def _get_path(root: dict[str, Any], path: str) -> Any:
    node: Any = root
    for part in _split_path(path):
        node = node[part]
    return node


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    node: Any = root
    parts = _split_path(path)
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _cap_value(
    value: int | float,
    *,
    value_min: int | float | None = None,
    value_max: int | float | None = None,
) -> int | float:
    if value_min is not None:
        value = max(value_min, value)
    if value_max is not None:
        value = min(value_max, value)
    return value


def _first_matching_number(spec: dict[str, Any], prefixes: tuple[str, ...]) -> int | float | None:
    for key, value in spec.items():
        if any(key.startswith(prefix) for prefix in prefixes) and _is_number(value):
            return value
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_runtime_field_policies(config_path: Path | None = None) -> tuple[tuple[RuntimeFieldPolicy, ...], str]:
    """Load field policies from the YAML config without adding a YAML dependency.

    The project keeps `configs/mutation_policy.yaml` as the source of truth.
    This parser intentionally supports only the subset used by that file:
    field policy entries, scalar values, inline lists, inline maps, and simple
    list blocks for `fields` / `legacy_aliases`.
    """

    path = config_path or DEFAULT_POLICY_CONFIG
    try:
        text = path.read_text(encoding="utf-8")
        policies = tuple(_parse_field_policies(text))
    except OSError:
        return FALLBACK_FIELD_POLICIES, "fallback:missing_config"
    except ValueError:
        return FALLBACK_FIELD_POLICIES, "fallback:parse_error"

    if not policies:
        return FALLBACK_FIELD_POLICIES, "fallback:no_field_policies"
    return policies, str(path)


def _parse_field_policies(text: str) -> list[RuntimeFieldPolicy]:
    entries: list[list[str]] = []
    current: list[str] = []
    in_section = False

    for raw_line in text.splitlines():
        if raw_line.startswith("field_policies:"):
            in_section = True
            continue
        if not in_section:
            continue
        if raw_line and not raw_line.startswith(" "):
            break
        if raw_line.startswith("  - id:"):
            if current:
                entries.append(current)
            current = [raw_line]
        elif current:
            current.append(raw_line)

    if current:
        entries.append(current)

    policies: list[RuntimeFieldPolicy] = []
    for entry in entries:
        policy = _parse_field_policy_entry(entry)
        if policy is not None:
            policies.append(policy)
    return policies


def _parse_field_policy_entry(lines: list[str]) -> RuntimeFieldPolicy | None:
    data: dict[str, Any] = {}
    list_key: str | None = None
    in_profiles = False

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if stripped.startswith("- id:"):
            data["id"] = _parse_yaml_value(stripped.split(":", 1)[1].strip())
            list_key = None
            in_profiles = False
            continue

        if indent == 4 and stripped in {"fields:", "legacy_aliases:"}:
            list_key = stripped[:-1]
            data.setdefault(list_key, [])
            in_profiles = False
            continue

        if indent == 4 and stripped == "profiles:":
            list_key = None
            in_profiles = True
            data.setdefault("profiles", {})
            continue

        if list_key and indent >= 6 and stripped.startswith("- "):
            data[list_key].append(_parse_yaml_value(stripped[2:].strip()))
            continue

        if in_profiles and indent >= 6 and ":" in stripped:
            key, value = stripped.split(":", 1)
            data.setdefault("profiles", {})[key.strip()] = _parse_yaml_value(value.strip())
            continue

        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            data[key.strip()] = _parse_yaml_value(value.strip())
            list_key = None
            in_profiles = False

    policy_id = data.get("id")
    if not policy_id:
        return None

    paths: list[str] = []
    for key in ("field", "legacy_alias"):
        if key in data:
            paths.append(str(data[key]))
    for key in ("fields", "legacy_aliases"):
        paths.extend(str(path) for path in data.get(key, []))

    if not paths:
        return None

    allowed_values = tuple(data.get("allowed_values", ()))
    return RuntimeFieldPolicy(
        policy_id=str(policy_id),
        paths=tuple(paths),
        mutation_kind=str(data.get("mutation_kind", "")),
        profiles=data.get("profiles", {}),
        allowed_values=allowed_values,
    )


def _parse_yaml_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if value == "":
        return {}
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_value(part.strip()) for part in _split_top_level(inner)]
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        result: dict[str, Any] = {}
        if not inner:
            return result
        for item in _split_top_level(inner):
            key, item_value = item.split(":", 1)
            result[key.strip().strip('"').strip("'")] = _parse_yaml_value(item_value.strip())
        return result
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None

    for index, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char in "[{":
            depth += 1
            continue
        if char in "]}":
            depth -= 1
            continue
        if char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


FIELD_POLICIES, POLICY_SOURCE = load_runtime_field_policies()
FIELD_POLICY_BY_PATH: dict[str, RuntimeFieldPolicy] = {}
for _policy in FIELD_POLICIES:
    for _path in _policy.paths:
        FIELD_POLICY_BY_PATH[_normalize_path(_path)] = _policy
