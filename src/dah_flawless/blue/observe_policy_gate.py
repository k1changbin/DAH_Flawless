"""ZTA-inspired usage policy gate for external observe values.

This module is deliberately not a threat detector. It decides how much
authority Blue may give to each external observe domain. Internal observe is
used only as a local trust anchor for cross-checking where it exists.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from dah_flawless.schemas import decision

DECISION_USE_WEIGHT = {
    "ALLOW": 1.0,
    "ALLOW_WITH_MONITOR": 0.8,
    "DOWNGRADE": 0.45,
    "REVALIDATE": 0.25,
    "QUARANTINE": 0.05,
    "DENY": 0.0,
}

ALLOWED_USE = {
    "ALLOW": "authoritative",
    "ALLOW_WITH_MONITOR": "authoritative_with_monitor",
    "DOWNGRADE": "advisory_only",
    "REVALIDATE": "hold_for_revalidation",
    "QUARANTINE": "detection_only",
    "DENY": "blocked",
}

POLICY_DOMAINS = ("telemetry", "mission", "command")

_ATTRIBUTE_WEIGHTS = {
    "telemetry": {
        "provenance": 0.12,
        "integrity_auth": 0.10,
        "freshness": 0.14,
        "anchor_agreement": 0.40,
        "history_consistency": 0.12,
        "capability": 0.12,
    },
    "mission": {
        "provenance": 0.18,
        "integrity_auth": 0.12,
        "freshness": 0.12,
        "anchor_agreement": 0.10,
        "history_consistency": 0.38,
        "capability": 0.10,
    },
    "command": {
        "provenance": 0.12,
        "integrity_auth": 0.25,
        "freshness": 0.24,
        "anchor_agreement": 0.20,
        "history_consistency": 0.10,
        "capability": 0.09,
    },
}


def evaluate_observe_policy(
    redacted_state: dict,
    history: dict | None = None,
    capabilities: dict | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate external observe authority without reading scorer truth."""

    observed = redacted_state.get("blue_observed", {})
    external = observed.get("external_observe", observed)
    internal = observed.get("internal_observe", {})
    capabilities = capabilities or redacted_state.get("capabilities", {})
    history = history or {}

    decisions = [
        _domain_decision("telemetry", redacted_state, external, internal, history, capabilities),
        _domain_decision("mission", redacted_state, external, internal, history, capabilities),
        _domain_decision("command", redacted_state, external, internal, history, capabilities),
    ]
    by_domain = {item["domain"]: item for item in decisions}
    min_trust = min((item["trust_score"] for item in decisions), default=1.0)
    restrictive = [item for item in decisions if item["decision"] not in {"ALLOW", "ALLOW_WITH_MONITOR"}]
    policy = {
        "algorithm": "zta_inspired_abac_radac_external_observe_v1",
        "scope": "external_observe_only",
        "internal_observe_role": "trust_anchor",
        "decision_semantics": "usage_authority_not_attack_detection",
        "decisions": decisions,
        "by_domain": by_domain,
        "min_trust_score": round(min_trust, 4),
        "restrictive_decision_count": len(restrictive),
        "restricted_domains": [item["domain"] for item in restrictive],
    }
    log = decision(
        "ObservePolicyGate",
        "usage_policy_evaluated",
        "zta_inspired_abac_radac_external_observe",
        before={
            "scope": policy["scope"],
            "internal_observe_role": policy["internal_observe_role"],
            "available_domains": sorted(key for key in external if key in {"telemetry", "mission", "c2_message", "comms"}),
        },
        after={
            "algorithm": policy["algorithm"],
            "min_trust_score": policy["min_trust_score"],
            "restricted_domains": policy["restricted_domains"],
            "domain_decisions": {
                item["domain"]: {
                    "decision": item["decision"],
                    "trust_score": item["trust_score"],
                    "required_assurance": item["required_assurance"],
                    "use_weight": item["use_weight"],
                }
                for item in decisions
            },
        },
    )
    return policy, log


def domain_use_weight(policy_gate: dict | None, domain: str, default: float = 1.0) -> float:
    item = domain_policy_decision(policy_gate, domain)
    if not item:
        return default
    return _clamp01(float(item.get("use_weight", default)))


def domain_policy_label(policy_gate: dict | None, domain: str, default: str = "ALLOW") -> str:
    item = domain_policy_decision(policy_gate, domain)
    if not item:
        return default
    return str(item.get("decision", default))


def domain_policy_decision(policy_gate: dict | None, domain: str) -> dict[str, Any] | None:
    if not policy_gate:
        return None
    by_domain = policy_gate.get("by_domain") or {}
    if domain in by_domain:
        return by_domain[domain]
    for item in policy_gate.get("decisions", []):
        if item.get("domain") == domain:
            return item
    return None


def policy_containment_score(policy_gate: dict | None, domain: str) -> dict[str, Any]:
    item = domain_policy_decision(policy_gate, domain)
    if not item:
        return {
            "score": 0.0,
            "domain": domain,
            "decision": "NOT_EVALUATED",
            "use_weight": 1.0,
            "reason": "observe_policy_gate_absent",
        }
    use_weight = domain_use_weight(policy_gate, domain)
    score = 0.0 if item.get("decision") in {"ALLOW", "ALLOW_WITH_MONITOR"} else 1.0 - use_weight
    return {
        "score": round(_clamp01(score), 4),
        "domain": domain,
        "decision": item.get("decision"),
        "use_weight": round(use_weight, 4),
        "trust_score": item.get("trust_score"),
        "required_assurance": item.get("required_assurance"),
        "allowed_use": item.get("allowed_use"),
    }


def compact_policy_gate(policy_gate: dict | None) -> dict[str, Any]:
    if not policy_gate:
        return {
            "algorithm": "not_evaluated",
            "scope": "external_observe_only",
            "domain_decisions": {},
        }
    return {
        "algorithm": policy_gate.get("algorithm"),
        "scope": policy_gate.get("scope"),
        "internal_observe_role": policy_gate.get("internal_observe_role"),
        "decision_semantics": policy_gate.get("decision_semantics"),
        "min_trust_score": policy_gate.get("min_trust_score"),
        "restricted_domains": list(policy_gate.get("restricted_domains", [])),
        "domain_decisions": {
            item.get("domain"): {
                "decision": item.get("decision"),
                "trust_score": item.get("trust_score"),
                "required_assurance": item.get("required_assurance"),
                "use_weight": item.get("use_weight"),
                "allowed_use": item.get("allowed_use"),
            }
            for item in policy_gate.get("decisions", [])
        },
    }


def _domain_decision(
    domain: str,
    state: dict,
    external: dict,
    internal: dict,
    history: dict,
    capabilities: dict,
) -> dict[str, Any]:
    if domain == "telemetry":
        attributes, reasons = _telemetry_attributes(external, internal, history, capabilities)
        resource = "blue_observed.external_observe.telemetry"
        requested_action = "use_as_authoritative"
    elif domain == "mission":
        attributes, reasons = _mission_attributes(external, history, capabilities)
        resource = "blue_observed.external_observe.mission"
        requested_action = "use_as_authoritative"
    elif domain == "command":
        attributes, reasons = _command_attributes(external, internal, history, capabilities)
        resource = "blue_observed.external_observe.c2_message"
        c2 = external.get("c2_message", {})
        requested_action = "execute_command" if c2.get("message_role") == "COMMAND" else "use_as_authoritative"
    else:
        attributes, reasons = {}, []
        resource = f"blue_observed.external_observe.{domain}"
        requested_action = "use_as_authoritative"

    weights = _ATTRIBUTE_WEIGHTS.get(domain, _ATTRIBUTE_WEIGHTS["mission"])
    trust_score = _weighted_score(attributes, weights)
    required = _required_assurance(domain, requested_action, state, external, internal, attributes)
    label = _decision_from_margin(domain, requested_action, trust_score, required)
    if domain == "telemetry" and "telemetry_safety_anchor_residual" in reasons:
        if label in {"ALLOW", "ALLOW_WITH_MONITOR", "DOWNGRADE", "REVALIDATE"}:
            label = "QUARANTINE"
    if domain == "mission" and {
        "mission_priority_step_residual",
        "mission_recommendation_history_shift",
        "mission_top_area_history_flip",
    }.intersection(reasons):
        if label in {"ALLOW", "ALLOW_WITH_MONITOR"}:
            label = "DOWNGRADE"
        if "mission_top_area_history_flip" in reasons and label == "DOWNGRADE":
            label = "REVALIDATE"
    if (
        domain == "command"
        and requested_action == "execute_command"
        and label == "DOWNGRADE"
        and {"command_auth_invalid", "command_checksum_invalid"}.intersection(reasons)
    ):
        label = "REVALIDATE"
    return {
        "domain": domain,
        "resource": resource,
        "requested_action": requested_action,
        "decision": label,
        "allowed_use": ALLOWED_USE[label],
        "use_weight": DECISION_USE_WEIGHT[label],
        "trust_score": round(trust_score, 4),
        "required_assurance": round(required, 4),
        "margin": round(trust_score - required, 4),
        "attributes": {key: round(_clamp01(value), 4) for key, value in attributes.items()},
        "attribute_weights": deepcopy(weights),
        "reasons": tuple(reasons),
        "scope": "external_observe",
    }


def _telemetry_attributes(
    external: dict,
    internal: dict,
    history: dict,
    capabilities: dict,
) -> tuple[dict[str, float], list[str]]:
    telemetry = external.get("telemetry", {})
    internal_telemetry = internal.get("telemetry", {})
    reasons: list[str] = []

    provenance = 0.70 if telemetry else 0.30
    integrity_auth = 0.68
    freshness = _timestamp_freshness(external, internal, reasons)
    anchor = _telemetry_anchor_agreement(telemetry, internal_telemetry, reasons)
    history_score = _telemetry_history_consistency(telemetry, history.get("last_telemetry", {}), reasons)
    capability = _capability_score(capabilities.get("cross_check_telemetry", "OK"))

    return (
        {
            "provenance": provenance,
            "integrity_auth": integrity_auth,
            "freshness": freshness,
            "anchor_agreement": anchor,
            "history_consistency": history_score,
            "capability": capability,
        },
        reasons,
    )


def _mission_attributes(
    external: dict,
    history: dict,
    capabilities: dict,
) -> tuple[dict[str, float], list[str]]:
    mission = external.get("mission", {})
    priorities = mission.get("area_priority", {})
    reasons: list[str] = []

    provenance = 0.66 if priorities else 0.30
    integrity_auth = 0.64
    freshness = _link_freshness(external, reasons)
    anchor = _mission_self_consistency(mission, reasons)
    history_score = _mission_history_consistency(mission, history.get("last_area_priority", {}), reasons)
    runtime_trust = _capability_score(capabilities.get("trusted_restore", "OK"))

    return (
        {
            "provenance": provenance,
            "integrity_auth": integrity_auth,
            "freshness": freshness,
            "anchor_agreement": anchor,
            "history_consistency": history_score,
            "capability": runtime_trust,
        },
        reasons,
    )


def _command_attributes(
    external: dict,
    internal: dict,
    history: dict,
    capabilities: dict,
) -> tuple[dict[str, float], list[str]]:
    c2 = external.get("c2_message", {})
    comms = external.get("comms", {})
    internal_c2 = internal.get("c2_message", {})
    reasons: list[str] = []

    provenance = 0.78 if c2.get("sysid") is not None and c2.get("compid") is not None else 0.55
    integrity_auth = _command_integrity(c2, comms, reasons)
    freshness = _command_freshness(external, internal_c2, reasons)
    anchor = _command_anchor_agreement(c2, external, internal_c2, reasons)
    history_score = _command_history_consistency(c2, external, history, reasons)
    capability = _capability_score(capabilities.get("time_validation", "OK"))

    return (
        {
            "provenance": provenance,
            "integrity_auth": integrity_auth,
            "freshness": freshness,
            "anchor_agreement": anchor,
            "history_consistency": history_score,
            "capability": capability,
        },
        reasons,
    )


def _required_assurance(
    domain: str,
    requested_action: str,
    state: dict,
    external: dict,
    internal: dict,
    attributes: dict[str, float],
) -> float:
    base = {"telemetry": 0.62, "mission": 0.64, "command": 0.72}.get(domain, 0.62)
    if requested_action == "execute_command":
        base += 0.08

    if domain == "telemetry":
        telemetry = internal.get("telemetry", {})
        if float(telemetry.get("battery_percent", 100.0)) <= 25.0 or telemetry.get("motor_status") != "OK":
            base += 0.07
        if attributes.get("anchor_agreement", 1.0) < 0.72:
            base += 0.06
    if domain == "command":
        if external.get("c2_message", {}).get("command") == "RETURN_TO_BASE":
            base += 0.04
    if domain == "mission":
        if attributes.get("history_consistency", 1.0) < 0.75:
            base += 0.04

    availability = float(state.get("mission", {}).get("availability", 1.0))
    if availability < 0.35:
        base -= 0.03
    trust_budget = float(state.get("mission", {}).get("trust_budget", 1.0))
    if trust_budget < 0.50:
        base += 0.03
    return _clamp(base, 0.45, 0.92)


def _decision_from_margin(domain: str, requested_action: str, trust_score: float, required: float) -> str:
    margin = trust_score - required
    if margin >= 0.15:
        return "ALLOW"
    if margin >= 0.04:
        return "ALLOW_WITH_MONITOR"
    if margin >= -0.10:
        return "DOWNGRADE"
    if margin >= -0.25:
        return "REVALIDATE"
    if margin >= -0.55:
        return "QUARANTINE"
    if domain == "command" and requested_action == "execute_command":
        return "DENY"
    return "QUARANTINE"


def _telemetry_anchor_agreement(telemetry: dict, internal_telemetry: dict, reasons: list[str]) -> float:
    if not telemetry or not internal_telemetry:
        reasons.append("telemetry_internal_anchor_missing")
        return 0.45
    external_battery = float(telemetry.get("battery_percent", 0.0))
    internal_battery = float(internal_telemetry.get("battery_percent", external_battery))
    battery_gap = abs(external_battery - internal_battery)
    signed_battery_gap = external_battery - internal_battery
    drain_gap = abs(float(telemetry.get("battery_drain_rate", 0.0)) - float(internal_telemetry.get("battery_drain_rate", 0.0)))
    motor_mismatch = telemetry.get("motor_status") != internal_telemetry.get("motor_status")
    safety_critical_anchor = internal_battery <= 25.0 or internal_telemetry.get("motor_status") != "OK"
    external_looks_safer = (
        signed_battery_gap >= 1.0
        or (telemetry.get("motor_status") == "OK" and internal_telemetry.get("motor_status") != "OK")
    )
    if battery_gap >= 8.0:
        reasons.append("telemetry_battery_internal_gap")
    if motor_mismatch:
        reasons.append("telemetry_motor_internal_mismatch")
    if safety_critical_anchor and external_looks_safer:
        reasons.append("telemetry_safety_anchor_residual")
    penalty = battery_gap / 50.0 + drain_gap / 6.0 + (0.35 if motor_mismatch else 0.0)
    if safety_critical_anchor and external_looks_safer:
        penalty += 0.42 + min(0.22, max(0.0, signed_battery_gap) / 18.0)
    return _clamp01(1.0 - penalty)


def _telemetry_history_consistency(telemetry: dict, previous: dict, reasons: list[str]) -> float:
    if not telemetry or not previous:
        return 0.74
    battery_delta = abs(float(telemetry.get("battery_percent", 0.0)) - float(previous.get("battery_percent", 0.0)))
    drain_delta = abs(float(telemetry.get("battery_drain_rate", 0.0)) - float(previous.get("battery_drain_rate", 0.0)))
    motor_flip = telemetry.get("motor_status") != previous.get("motor_status")
    if battery_delta >= 10.0:
        reasons.append("telemetry_history_jump")
    if motor_flip:
        reasons.append("telemetry_motor_history_flip")
    penalty = battery_delta / 45.0 + drain_delta / 5.0 + (0.25 if motor_flip else 0.0)
    return _clamp01(1.0 - penalty)


def _mission_self_consistency(mission: dict, reasons: list[str]) -> float:
    priorities = mission.get("area_priority", {})
    if not priorities:
        reasons.append("mission_priority_missing")
        return 0.40
    top_area = max(priorities, key=lambda area: float(priorities[area]))
    recommended = mission.get("recommended_area")
    values = [float(value) for value in priorities.values()]
    out_of_range = any(value < 0.0 or value > 1.0 for value in values)
    score = 0.82
    if recommended not in {None, top_area}:
        reasons.append("mission_recommendation_priority_mismatch")
        score -= 0.22
    if out_of_range:
        reasons.append("mission_priority_out_of_range")
        score -= 0.35
    return _clamp01(score)


def _mission_history_consistency(mission: dict, previous: dict, reasons: list[str]) -> float:
    priorities = mission.get("area_priority", {})
    if not priorities or not previous:
        return 0.74
    max_delta = max(abs(float(priorities.get(area, 0.0)) - float(previous.get(area, 0.0))) for area in set(priorities) | set(previous))
    top_now = max(priorities, key=lambda area: float(priorities[area]))
    top_before = max(previous, key=lambda area: float(previous[area]))
    recommended = mission.get("recommended_area")
    recommendation_shift = recommended is not None and recommended != top_before
    if max_delta >= 0.03:
        reasons.append("mission_priority_step_residual")
    if max_delta >= 0.16:
        reasons.append("mission_priority_history_drift")
    if top_now != top_before:
        reasons.append("mission_top_area_history_flip")
    if recommendation_shift:
        reasons.append("mission_recommendation_history_shift")
    penalty = (
        max_delta * 2.20
        + (0.24 if top_now != top_before else 0.0)
        + (0.18 if recommendation_shift else 0.0)
        + (0.12 if max_delta >= 0.03 else 0.0)
    )
    return _clamp01(1.0 - penalty)


def _command_integrity(c2: dict, comms: dict, reasons: list[str]) -> float:
    checksum = bool(c2.get("checksum_valid", True))
    signature = bool(c2.get("signature_present", False))
    auth = bool(c2.get("auth_valid", True))
    encrypted = bool(comms.get("encrypted", False))
    crypto = comms.get("crypto_profile", {})
    nonce_reuse = bool(crypto.get("nonce_reuse_suspected", False))
    weak_cipher = bool(crypto.get("weak_cipher_hint", False))

    score = 0.20
    score += 0.24 if checksum else 0.0
    score += 0.22 if signature else 0.0
    score += 0.26 if auth else 0.0
    score += 0.08 if encrypted else 0.0
    if not checksum:
        reasons.append("command_checksum_invalid")
    if not auth:
        reasons.append("command_auth_invalid")
    if not signature:
        reasons.append("command_signature_absent")
    if nonce_reuse:
        reasons.append("command_crypto_nonce_reuse_hint")
        score -= 0.15
    if weak_cipher:
        reasons.append("command_crypto_weak_cipher_hint")
        score -= 0.12
    return _clamp01(score)


def _command_freshness(external: dict, internal_c2: dict, reasons: list[str]) -> float:
    c2 = external.get("c2_message", {})
    comms = external.get("comms", {})
    time = external.get("time", {})
    expected_sequence = int(internal_c2.get("sequence_number", c2.get("sequence_number", 0)))
    received_sequence = int(c2.get("sequence_number", expected_sequence))
    internal_ts = int(internal_c2.get("received_timestamp", time.get("received_timestamp", 0)))
    received_ts = int(time.get("received_timestamp", internal_ts))
    ack = c2.get("ack", {})
    ack_sequence = int(ack.get("sequence_number", received_sequence))

    sequence_lag = max(0, expected_sequence - received_sequence)
    timestamp_lag = max(0, internal_ts - received_ts)
    ack_gap = abs(received_sequence - ack_sequence)
    ack_delay = int(comms.get("ack_delay_ms", 0))
    latency_ms = int(comms.get("latency_ms", 0))
    packet_loss = float(comms.get("packet_loss", 0.0))
    heartbeat_gap = int(comms.get("heartbeat_gap_ms", 0))
    if sequence_lag >= 2:
        reasons.append("command_sequence_lag")
    if timestamp_lag >= 45:
        reasons.append("command_timestamp_lag")
    if ack_gap >= 2:
        reasons.append("command_ack_sequence_gap")
    if heartbeat_gap >= 2000:
        reasons.append("command_heartbeat_gap")

    penalty = (
        sequence_lag / 6.0 * 0.35
        + timestamp_lag / 180.0 * 0.30
        + ack_gap / 4.0 * 0.15
        + ack_delay / 2400.0 * 0.08
        + latency_ms / 1800.0 * 0.06
        + packet_loss * 0.30
        + heartbeat_gap / 6000.0 * 0.08
    )
    return _clamp01(1.0 - penalty)


def _command_anchor_agreement(c2: dict, external: dict, internal_c2: dict, reasons: list[str]) -> float:
    if not internal_c2:
        reasons.append("command_internal_anchor_missing")
        return 0.50
    expected_sequence = int(internal_c2.get("sequence_number", c2.get("sequence_number", 0)))
    received_sequence = int(c2.get("sequence_number", expected_sequence))
    internal_ts = int(internal_c2.get("received_timestamp", external.get("time", {}).get("received_timestamp", 0)))
    received_ts = int(external.get("time", {}).get("received_timestamp", internal_ts))
    command_match = c2.get("command") == internal_c2.get("command")
    sequence_lag = max(0, expected_sequence - received_sequence)
    timestamp_lag = max(0, internal_ts - received_ts)
    if not command_match:
        reasons.append("command_internal_anchor_mismatch")
    penalty = sequence_lag / 8.0 + timestamp_lag / 240.0 + (0.30 if not command_match else 0.0)
    return _clamp01(1.0 - penalty)


def _command_history_consistency(c2: dict, external: dict, history: dict, reasons: list[str]) -> float:
    last_sequence = history.get("last_sequence_number")
    last_ts = history.get("last_received_timestamp")
    if last_sequence is None or last_ts is None:
        return 0.76
    current_sequence = int(c2.get("sequence_number", last_sequence))
    current_ts = int(external.get("time", {}).get("received_timestamp", last_ts))
    sequence_regression = max(0, int(last_sequence) - current_sequence)
    timestamp_regression = max(0, int(last_ts) - current_ts)
    if sequence_regression > 0:
        reasons.append("command_sequence_history_regression")
    if timestamp_regression > 0:
        reasons.append("command_timestamp_history_regression")
    penalty = sequence_regression / 4.0 + timestamp_regression / 180.0
    return _clamp01(1.0 - penalty)


def _timestamp_freshness(external: dict, internal: dict, reasons: list[str]) -> float:
    time = external.get("time", {})
    internal_time = internal.get("time", {})
    if "received_timestamp" not in time or "true_timestamp" not in internal_time:
        return _link_freshness(external, reasons)
    lag = max(0, int(internal_time["true_timestamp"]) - int(time["received_timestamp"]))
    if lag >= 45:
        reasons.append("observe_timestamp_lag")
    timestamp_score = _clamp01(1.0 - lag / 240.0)
    return min(timestamp_score, _link_freshness(external, reasons))


def _link_freshness(external: dict, reasons: list[str]) -> float:
    comms = external.get("comms", {})
    latency = int(comms.get("latency_ms", 0))
    packet_loss = float(comms.get("packet_loss", 0.0))
    jitter = int(comms.get("packet_interval_jitter_ms", 0))
    heartbeat_gap = int(comms.get("heartbeat_gap_ms", 0))
    if latency >= 900:
        reasons.append("link_high_latency")
    if packet_loss >= 0.20:
        reasons.append("link_high_packet_loss")
    if heartbeat_gap >= 2500:
        reasons.append("link_heartbeat_gap")
    penalty = latency / 2400.0 + packet_loss * 0.55 + jitter / 2500.0 + heartbeat_gap / 8000.0
    return _clamp01(1.0 - penalty)


def _weighted_score(attributes: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.values()) or 1.0
    return _clamp01(sum(_clamp01(attributes.get(name, 0.0)) * weight for name, weight in weights.items()) / total_weight)


def _capability_score(value: Any) -> float:
    return {
        "OK": 1.0,
        "DEGRADED": 0.62,
        "UNAVAILABLE": 0.35,
    }.get(str(value), 0.70)


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, float(value)))
