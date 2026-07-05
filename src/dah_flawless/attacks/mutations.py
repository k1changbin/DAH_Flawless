"""Observed-only Red mutations with amplitude profiles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Callable

from dah_flawless.attacks.mutation_policy import MutationPolicyEnforcer
from dah_flawless.config import DEFAULT_MUTATION_PROFILE, MUTATION_PROFILES
from dah_flawless.mutation_review import MutationApprovalReviewer, build_mutation_approval_reviewer
from dah_flawless.observation import sync_external_observe_from_flat
from dah_flawless.schemas import Attack


@dataclass(frozen=True)
class MutationOutcome:
    before: Any
    after: Any
    requested_delta: Any
    applied_delta: Any
    policy_decisions: list[dict[str, Any]]


MutationHandler = Callable[[dict, dict, str], MutationOutcome]


PROFILE_POLICY_ID = {
    "stealth": "dah.mutation_policy.v0_1.profile.stealth",
    "aggressive": "dah.mutation_policy.v0_1.profile.aggressive",
    "loud_demo": "dah.mutation_policy.v0_1.profile.loud_demo",
}

TELEMETRY_PROFILE = {
    "stealth": {"max_probe_delta": 8, "motor_status": "FAULT"},
    "aggressive": {"battery_delta": 25, "motor_status": "OK"},
    "loud_demo": {"battery_absolute": 82, "motor_status": "OK"},
}

MISSION_PRIORITY_PROFILE = {
    "stealth": {"area_priority": {"A": 0.78, "B": 0.40, "C": 0.35}, "recommended_area": "A"},
    "aggressive": {"area_priority": {"A": 0.45, "B": 0.40, "C": 0.65}, "recommended_area": "C"},
    "loud_demo": {"area_priority": {"A": 0.20, "B": 0.40, "C": 0.95}, "recommended_area": "C"},
}

TIME_DESYNC_FALLBACK_PROFILE = {
    "stealth": {
        "sequence_delta": -2,
        "timestamp_delta_s": -5,
        "latency_ms": 300,
        "packet_loss": 0.05,
        "packet_interval_jitter_ms": 150,
        "ack_delay_ms": 300,
        "heartbeat_gap_ms": 2000,
    },
    "aggressive": {
        "sequence_delta": -8,
        "timestamp_delta_s": -45,
        "latency_ms": 720,
        "packet_loss": 0.12,
        "packet_interval_jitter_ms": 460,
        "ack_delay_ms": 950,
        "heartbeat_gap_ms": 3200,
    },
    "loud_demo": {
        "sequence_delta": -13,
        "timestamp_delta_s": -400,
        "latency_ms": 850,
        "packet_loss": 0.12,
        "packet_interval_jitter_ms": 460,
        "ack_delay_ms": 950,
        "heartbeat_gap_ms": 3200,
    },
}


def apply_attack(
    state: dict,
    attack: Attack,
    stealth: bool = False,
    tactic: dict | None = None,
    mutation_approval_reviewer: MutationApprovalReviewer | None = None,
) -> tuple[dict, dict]:
    """Apply an attack to blue_observed only.

    The function intentionally never reads state["world"]. This keeps Red's
    mutation model aligned with the scorer_truth/observed split.

    ``tactic["mutation_profile"]`` separates normal training values from old
    large demonstration values. The current profiles are:

    - stealth: low-amplitude boundary probe.
    - aggressive: default report/training profile.
    - loud_demo: legacy large values for clear demos and hard cases.
    """

    next_state = deepcopy(state)
    obs = next_state["blue_observed"]
    before_observe = deepcopy(obs)
    profile = resolve_mutation_profile(stealth, tactic)
    tactic_payload = tactic or {}
    handler = MUTATION_HANDLERS.get(attack.name)
    if handler is None:
        raise ValueError(f"mutation not implemented for {attack.name}")

    outcome = handler(obs, tactic_payload, profile)
    reviewer = mutation_approval_reviewer or build_mutation_approval_reviewer()
    reviewed_observe, approval_log = reviewer.review_mutation(
        attack_name=attack.name,
        profile=profile,
        tactic=tactic_payload,
        before_observe=before_observe,
        proposed_observe=obs,
        outcome=outcome,
    )
    next_state["blue_observed"] = reviewed_observe
    obs = next_state["blue_observed"]
    sync_external_observe_from_flat(obs)
    reviewed_outcome = _reviewed_outcome(attack.name, outcome, obs)
    return next_state, _mutation_log(attack.name, stealth, profile, tactic_payload, reviewed_outcome, approval_log)


def _mutation_log(
    attack_name: str,
    stealth: bool,
    profile: str,
    tactic: dict,
    outcome: MutationOutcome,
    approval_log: dict,
) -> dict:
    return {
        "agent": "RedAgent",
        "event": "mutation_applied",
        "reason": attack_name,
        "stealth": stealth,
        "mutation_profile": profile,
        "policy_id": PROFILE_POLICY_ID[profile],
        "tactic": tactic or {"stealth": stealth},
        "requested_delta": outcome.requested_delta,
        "applied_delta": outcome.applied_delta,
        "policy_decisions": outcome.policy_decisions,
        "mutation_approval_review": approval_log,
        "before": outcome.before,
        "after": outcome.after,
    }


def _mutate_telemetry(obs: dict, tactic: dict, profile: str) -> MutationOutcome:
    policy = MutationPolicyEnforcer(profile)
    before = {
        "battery_percent": obs["telemetry"]["battery_percent"],
        "motor_status": obs["telemetry"]["motor_status"],
    }
    profile_spec = TELEMETRY_PROFILE[profile]

    if profile == "stealth":
        requested_delta = int(tactic.get("probe_delta", profile_spec["max_probe_delta"]))
        applied_delta = policy.add_value(
            obs,
            "telemetry.battery_percent",
            requested_delta,
            value_min=0,
            value_max=100,
        )
    elif "battery_absolute" in profile_spec:
        requested_delta = profile_spec["battery_absolute"] - obs["telemetry"]["battery_percent"]
        before_battery = obs["telemetry"]["battery_percent"]
        applied_value = policy.set_absolute(
            obs,
            "telemetry.battery_percent",
            profile_spec["battery_absolute"],
            value_min=0,
            value_max=100,
        )
        applied_delta = applied_value - before_battery
    else:
        requested_delta = profile_spec["battery_delta"]
        applied_delta = policy.add_value(
            obs,
            "telemetry.battery_percent",
            requested_delta,
            value_min=0,
            value_max=100,
        )

    policy.set_enum(obs, "telemetry.motor_status", profile_spec["motor_status"])
    after = {
        "battery_percent": obs["telemetry"]["battery_percent"],
        "motor_status": obs["telemetry"]["motor_status"],
    }
    return MutationOutcome(before, after, requested_delta, applied_delta, policy.decision_dicts())


def _mutate_priority(obs: dict, _tactic: dict, profile: str) -> MutationOutcome:
    policy = MutationPolicyEnforcer(profile)
    before = deepcopy(obs["mission"]["area_priority"])
    profile_spec = MISSION_PRIORITY_PROFILE[profile]
    requested_delta = _priority_delta(before, profile_spec["area_priority"])
    policy.set_priority_vector(obs, "mission.area_priority", profile_spec["area_priority"])
    policy.set_enum(obs, "mission.recommended_area", profile_spec["recommended_area"])
    after = deepcopy(obs["mission"]["area_priority"])
    return MutationOutcome(before, after, requested_delta, _priority_delta(before, after), policy.decision_dicts())


def _mutate_time_desync(obs: dict, tactic: dict, profile: str) -> MutationOutcome:
    policy = MutationPolicyEnforcer(profile)
    before = _time_desync_snapshot(obs)
    requested_delta = deepcopy(tactic.get("params", {}))
    applied_delta = _apply_time_desync_strategy(obs, tactic, profile, policy)
    after = _time_desync_snapshot(obs)
    return MutationOutcome(before, after, requested_delta, applied_delta, policy.decision_dicts())


def _time_desync_snapshot(obs: dict) -> dict:
    return {
        "sequence_number": obs["c2_message"]["sequence_number"],
        "received_timestamp": obs["time"]["received_timestamp"],
        "command": obs["c2_message"]["command"],
        "ack_sequence_number": obs["c2_message"].get("ack", {}).get("sequence_number"),
        "latency_ms": obs["comms"].get("latency_ms"),
        "packet_loss": obs["comms"].get("packet_loss"),
        "ack_delay_ms": obs["comms"].get("ack_delay_ms"),
        "heartbeat_gap_ms": obs["comms"].get("heartbeat_gap_ms"),
    }


def _reviewed_outcome(attack_name: str, outcome: MutationOutcome, obs: dict) -> MutationOutcome:
    after = _snapshot_for_attack(attack_name, obs)
    applied_delta = _delta_for_attack(attack_name, outcome.before, after)
    return replace(outcome, after=after, applied_delta=applied_delta)


def _snapshot_for_attack(attack_name: str, obs: dict) -> Any:
    if attack_name == "TELEMETRY_FDI":
        return {
            "battery_percent": obs["telemetry"]["battery_percent"],
            "motor_status": obs["telemetry"]["motor_status"],
        }
    if attack_name == "PRIORITY_POISONING":
        return deepcopy(obs["mission"]["area_priority"])
    if attack_name == "TIME_DESYNC_REPLAY":
        return _time_desync_snapshot(obs)
    return None


def _delta_for_attack(attack_name: str, before: Any, after: Any) -> Any:
    if attack_name == "PRIORITY_POISONING":
        return _priority_delta(before, after)
    if attack_name == "TELEMETRY_FDI":
        return after["battery_percent"] - before["battery_percent"]
    if attack_name == "TIME_DESYNC_REPLAY":
        return _generic_delta(before, after)
    return None


def _generic_delta(before: Any, after: Any) -> Any:
    if isinstance(before, dict) and isinstance(after, dict):
        delta: dict[str, Any] = {}
        for key in sorted(set(before).union(after)):
            if key not in before:
                delta[key] = after[key]
            elif key not in after:
                delta[key] = None
            else:
                value = _generic_delta(before[key], after[key])
                if value is not None:
                    delta[key] = value
        return delta
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and not isinstance(before, bool):
        value = after - before
        if isinstance(before, int) and isinstance(after, int):
            return value
        return round(value, 4)
    if before != after:
        return after
    return None


def _apply_time_desync_strategy(
    obs: dict,
    tactic: dict,
    profile: str,
    policy: MutationPolicyEnforcer,
) -> dict:
    strategy = tactic.get("strategy", "replay")
    params = {**TIME_DESYNC_FALLBACK_PROFILE[profile], **tactic.get("params", {})}
    applied: dict[str, Any] = {}

    if strategy == "delay":
        applied["timestamp_delta_s"] = policy.add_value(
            obs,
            "time.received_timestamp",
            int(params.get("timestamp_delta_s", -180)),
        )
        applied["command"] = policy.set_enum(obs, "c2_message.command", "CONTINUE_MISSION")
        applied["latency_ms"] = policy.set_with_delta_limit(obs, "comms.latency_ms", int(params.get("latency_ms", 900)))
        applied["packet_interval_jitter_ms"] = policy.set_with_delta_limit(
            obs,
            "comms.packet_interval_jitter_ms",
            int(params.get("packet_interval_jitter_ms", 460)),
        )
        applied["packet_loss"] = policy.set_absolute(
            obs,
            "comms.packet_loss",
            max(obs["comms"].get("packet_loss", 0.0), float(params.get("packet_loss", 0.08))),
            value_min=0.0,
            value_max=1.0,
        )
    elif strategy == "selective_drop":
        applied["sequence_delta"] = policy.add_value(obs, "c2_message.sequence_number", 3, value_min=0)
        applied["command"] = policy.set_enum(obs, "c2_message.command", "CONTINUE_MISSION")
        applied["packet_loss"] = policy.set_absolute(
            obs,
            "comms.packet_loss",
            float(params.get("packet_loss", 0.16)),
            value_min=0.0,
            value_max=1.0,
        )
        applied["heartbeat_gap_ms"] = policy.set_heartbeat_gap(
            obs,
            "comms.heartbeat_gap_ms",
            int(params.get("heartbeat_gap_ms", 3600)),
        )
        applied["packet_interval_jitter_ms"] = policy.set_with_delta_limit(
            obs,
            "comms.packet_interval_jitter_ms",
            int(params.get("packet_interval_jitter_ms", 460)),
        )
    elif strategy == "ack_confusion":
        applied["command"] = policy.set_enum(obs, "c2_message.command", "CONTINUE_MISSION")
        ack = obs["c2_message"].setdefault("ack", {})
        ack["visible"] = True
        applied["ack_sequence_number"] = policy.set_with_delta_limit(
            obs,
            "c2_message.ack.sequence_number",
            obs["c2_message"]["sequence_number"] + int(params.get("ack_sequence_delta", -2)),
            value_min=0,
        )
        ack["status"] = "ACCEPTED"
        obs["comms"]["ack_visible"] = True
        applied["ack_delay_ms"] = policy.set_with_delta_limit(
            obs,
            "comms.ack_delay_ms",
            int(params.get("ack_delay_ms", 950)),
        )
        applied["latency_ms"] = policy.set_with_delta_limit(
            obs,
            "comms.latency_ms",
            max(obs["comms"].get("latency_ms", 0), int(params.get("latency_ms", 540))),
        )
    elif strategy == "metadata_poisoning":
        applied["sequence_delta"] = policy.add_value(
            obs,
            "c2_message.sequence_number",
            int(params.get("sequence_delta", -2)),
            value_min=0,
        )
        applied["timestamp_delta_s"] = policy.add_value(
            obs,
            "time.received_timestamp",
            int(params.get("timestamp_delta_s", -90)),
        )
        applied["command"] = policy.set_enum(obs, "c2_message.command", "CONTINUE_MISSION")
        applied["sysid"] = policy.set_absolute(obs, "c2_message.sysid", 99, value_min=0)
        applied["compid"] = policy.set_absolute(obs, "c2_message.compid", 42, value_min=0)
        applied["latency_ms"] = policy.set_with_delta_limit(
            obs,
            "comms.latency_ms",
            max(obs["comms"].get("latency_ms", 0), int(params.get("latency_ms", 620))),
        )
    else:
        applied["sequence_delta"] = policy.add_value(
            obs,
            "c2_message.sequence_number",
            int(params.get("sequence_delta", -13)),
            value_min=0,
        )
        applied["timestamp_delta_s"] = policy.add_value(
            obs,
            "time.received_timestamp",
            int(params.get("timestamp_delta_s", -400)),
        )
        applied["command"] = policy.set_enum(obs, "c2_message.command", "CONTINUE_MISSION")
        applied["latency_ms"] = policy.set_with_delta_limit(obs, "comms.latency_ms", int(params.get("latency_ms", 850)))
        applied["packet_loss"] = policy.set_absolute(
            obs,
            "comms.packet_loss",
            float(params.get("packet_loss", 0.12)),
            value_min=0.0,
            value_max=1.0,
        )
        applied["packet_interval_jitter_ms"] = policy.set_with_delta_limit(
            obs,
            "comms.packet_interval_jitter_ms",
            int(params.get("packet_interval_jitter_ms", 460)),
        )
        applied["ack_delay_ms"] = policy.set_with_delta_limit(obs, "comms.ack_delay_ms", int(params.get("ack_delay_ms", 950)))
        applied["heartbeat_gap_ms"] = policy.set_heartbeat_gap(
            obs,
            "comms.heartbeat_gap_ms",
            int(params.get("heartbeat_gap_ms", 3200)),
        )
    return applied


def resolve_mutation_profile(stealth: bool, tactic: dict | None) -> str:
    if stealth:
        return "stealth"
    profile = (tactic or {}).get("mutation_profile", DEFAULT_MUTATION_PROFILE)
    if profile not in MUTATION_PROFILES:
        return DEFAULT_MUTATION_PROFILE
    return profile


def _priority_delta(before: dict, after: dict) -> dict:
    return {area: round(after.get(area, 0.0) - value, 3) for area, value in before.items()}


MUTATION_HANDLERS: dict[str, MutationHandler] = {
    "TELEMETRY_FDI": _mutate_telemetry,
    "PRIORITY_POISONING": _mutate_priority,
    "TIME_DESYNC_REPLAY": _mutate_time_desync,
}
