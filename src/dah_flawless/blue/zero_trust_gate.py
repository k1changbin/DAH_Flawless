"""Zero Trust Observe/Command Policy Gate (NIST SP 800-207 inspired).

This module adds an explicit policy-judgment layer to Blue. It does *not*
redesign the whole system as a ZTA. Instead it treats each external observe
domain as an untrusted resource and, per combat step, decides how far Blue may
trust that resource for mission judgement: ``ALLOW``, ``ALLOW_WITH_LOW_CONFIDENCE``,
``DOWNGRADE``, ``REVALIDATE``, ``QUARANTINE`` or ``DENY``.

Mapping to NIST SP 800-207 logical components:

* Policy Enforcement Point (PEP): ``evaluate_zero_trust`` - the gate itself.
* Policy Engine (PE): the per-domain ``_score_*`` trust functions.
* Policy Administrator (PA): ``zta_action_candidates`` - turns decisions into
  defense action candidates (HOLD_COMMAND / QUARANTINE_FIELD / REQUEST_REVALIDATION).
* Policy Information Point (PIP): ``internal_observe`` vs ``external_observe``,
  history, capabilities, ``defense_runtime.domain_trust``, threat evidence.

The gate reads Blue-visible inputs only (never scorer truth) and is
side-effect free; the runner records its decisions for audit and replay.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from dah_flawless.schemas import Threat, decision

# Resource domains the gate governs. These match the three operational attack
# surfaces in the simulation (command / telemetry / mission priority). ACK and
# channel timing feed the command decision as evidence rather than as a
# separate gated resource.
GATED_DOMAINS = ("command", "telemetry", "mission")

# Feature weights from the ZTA design section 11. They sum to 1.0; the threat
# confidence penalty is subtracted afterwards and the result is clamped to [0, 1].
FEATURE_WEIGHTS = {
    "identity_auth": 0.30,
    "freshness": 0.20,
    "internal_consistency": 0.20,
    "domain_trust": 0.15,
    "channel_health": 0.10,
    "capability": 0.05,
}

# Decision bands from the ZTA design section 11, highest threshold first.
DECISION_BANDS = (
    (0.80, "ALLOW"),
    (0.65, "ALLOW_WITH_LOW_CONFIDENCE"),
    (0.45, "DOWNGRADE"),
    (0.25, "REVALIDATE"),
    (0.10, "QUARANTINE"),
    (0.0, "DENY"),
)

# How far the resource may be used, and the (informational) availability cost of
# taking each decision. The cost models "continuous verification is not free"
# (ZTA design section 10) but is recorded for reporting only; it does not mutate the
# scorer's availability so the existing attrition balance stays intact.
ALLOWED_USE = {
    "ALLOW": "operational",
    "ALLOW_WITH_LOW_CONFIDENCE": "operational_low_confidence",
    "DOWNGRADE": "partial_non_authoritative",
    "REVALIDATE": "hold_pending_revalidation",
    "QUARANTINE": "detection_only",
    "DENY": "blocked",
}
DECISION_COST = {
    "ALLOW": 0.0,
    "ALLOW_WITH_LOW_CONFIDENCE": 0.005,
    "DOWNGRADE": 0.01,
    "REVALIDATE": 0.015,
    "QUARANTINE": 0.02,
    "DENY": 0.02,
}
RESTRICTIVE_DECISIONS = frozenset({"DOWNGRADE", "REVALIDATE", "QUARANTINE", "DENY"})

_DOMAIN_META = {
    "command": ("blue_observed.c2_message.command", "external_c2_source"),
    "telemetry": ("blue_observed.telemetry", "external_telemetry_source"),
    "mission": ("blue_observed.mission.recommended_area", "external_mission_report_source"),
}
_DOMAIN_CAPABILITY = {
    "command": "time_validation",
    "telemetry": "cross_check_telemetry",
    "mission": "trusted_restore",
}


@dataclass(frozen=True)
class ZtaDecision:
    """One policy decision for one external observe resource in one step."""

    domain: str
    resource: str
    subject: str
    decision: str
    trust_score: float
    reasons: tuple[str, ...]
    allowed_use: str
    availability_cost: float
    feature_scores: dict[str, float] = field(default_factory=dict)

    @property
    def restrictive(self) -> bool:
        return self.decision in RESTRICTIVE_DECISIONS

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def evaluate_zero_trust(
    blue_observed: dict,
    history: dict,
    capabilities: dict | None,
    domain_trust: dict | None,
    mission_state: dict | None,
    threats: list[Threat],
    *,
    domains: tuple[str, ...] = GATED_DOMAINS,
) -> tuple[list[ZtaDecision], dict]:
    """Return one policy decision per gated domain plus an audit log.

    Blue-visible inputs only. ``blue_observed`` is expected to carry both the
    flat external aliases and ``internal_observe`` (see ``observation.py``).
    """

    capabilities = capabilities or {}
    domain_trust = domain_trust or {}
    mission_state = mission_state or {}
    threat_conf_by_domain = _threat_confidence_by_domain(threats)

    decisions = [
        _decide_domain(
            domain=domain,
            blue_observed=blue_observed,
            history=history,
            capabilities=capabilities,
            domain_trust=domain_trust,
            threat_confidence=threat_conf_by_domain.get(domain, 0.0),
        )
        for domain in domains
    ]

    log = decision(
        "ZeroTrustObserveGate",
        "observe_use_policy_decided",
        "per_resource_dynamic_trust_scoring",
        before={
            "domain_trust": {d: round(float(domain_trust.get(d, 1.0)), 4) for d in domains},
            "threat_confidence": {d: round(threat_conf_by_domain.get(d, 0.0), 4) for d in domains},
            "availability": mission_state.get("availability"),
            "trust_budget": mission_state.get("trust_budget"),
        },
        after={"decisions": [d.to_dict() for d in decisions]},
    )
    return decisions, log


def _decide_domain(
    *,
    domain: str,
    blue_observed: dict,
    history: dict,
    capabilities: dict,
    domain_trust: dict,
    threat_confidence: float,
) -> ZtaDecision:
    external = blue_observed
    internal = blue_observed.get("internal_observe", {})

    if domain == "command":
        features, reasons = _score_command(external, internal, history)
    elif domain == "telemetry":
        features, reasons = _score_telemetry(external, internal)
    else:
        features, reasons = _score_mission(external, history)

    features["domain_trust"] = _clamp(float(domain_trust.get(domain, 1.0)))
    features["channel_health"], channel_reasons = _channel_health(external.get("comms", {}))
    features["capability"], capability_reason = _capability_score(domain, capabilities)
    reasons.extend(channel_reasons)
    reasons.extend(capability_reason)

    weighted = sum(FEATURE_WEIGHTS[name] * features[name] for name in FEATURE_WEIGHTS)
    penalty = round(0.6 * _clamp(threat_confidence), 4)
    if penalty > 0:
        reasons.append("threat_confidence_penalty")
    trust_score = round(_clamp(weighted - penalty), 4)

    verdict = _band(trust_score)
    resource, subject = _DOMAIN_META[domain]
    if not reasons:
        reasons.append("nominal")
    return ZtaDecision(
        domain=domain,
        resource=resource,
        subject=subject,
        decision=verdict,
        trust_score=trust_score,
        reasons=tuple(dict.fromkeys(reasons)),  # dedupe, keep order
        allowed_use=ALLOWED_USE[verdict],
        availability_cost=DECISION_COST[verdict],
        feature_scores={name: round(float(value), 4) for name, value in features.items()},
    )


def _score_command(external: dict, internal: dict, history: dict) -> tuple[dict[str, float], list[str]]:
    reasons: list[str] = []
    c2 = external.get("c2_message", {})
    internal_c2 = internal.get("c2_message", {})

    # Identity / authentication: signed, checksummed, authenticated command.
    identity = 0.5 * _flag(c2.get("auth_valid")) + 0.3 * _flag(c2.get("signature_present")) + 0.2 * _flag(
        c2.get("checksum_valid")
    )
    if not c2.get("auth_valid", True):
        reasons.append("auth_invalid")
    if not c2.get("checksum_valid", True):
        reasons.append("checksum_invalid")

    # Freshness: sequence monotonicity, timestamp forward progress, ACK causality.
    freshness = 1.0
    seq = _as_int(c2.get("sequence_number"))
    last_seq = _as_int(history.get("last_sequence_number"))
    if seq is not None and last_seq is not None and seq < last_seq:
        freshness -= 0.45
        reasons.append("sequence_regression")
    ts = _as_int(external.get("time", {}).get("received_timestamp"))
    last_ts = _as_int(history.get("last_received_timestamp"))
    if ts is not None and last_ts is not None and ts < last_ts:
        freshness -= 0.25
        reasons.append("timestamp_regression")
    ack = c2.get("ack", {})
    ack_seq = _as_int(ack.get("sequence_number"))
    if ack.get("visible") and seq is not None and ack_seq is not None and abs(seq - ack_seq) >= 2:
        freshness -= 0.25
        reasons.append("ack_causality_gap")

    # Internal consistency: external command vs trusted internal anchor.
    consistency = 1.0
    if internal_c2:
        if internal_c2.get("command") is not None and c2.get("command") != internal_c2.get("command"):
            consistency -= 0.5
            reasons.append("command_internal_mismatch")
        internal_seq = _as_int(internal_c2.get("sequence_number"))
        if seq is not None and internal_seq is not None and seq < internal_seq:
            consistency -= 0.3
            reasons.append("sequence_behind_internal_anchor")
    return {"identity_auth": _clamp(identity), "freshness": _clamp(freshness), "internal_consistency": _clamp(consistency)}, reasons


def _score_telemetry(external: dict, internal: dict) -> tuple[dict[str, float], list[str]]:
    reasons: list[str] = []
    ext_tel = external.get("telemetry", {})
    int_tel = internal.get("telemetry", {})

    # Telemetry is not individually signed; identity is a weak channel-integrity
    # proxy (encrypted link, no crypto anomalies).
    comms = external.get("comms", {})
    crypto = comms.get("crypto_profile", {})
    identity = (
        0.5 * _flag(comms.get("encrypted", True))
        + 0.25 * _flag(not crypto.get("nonce_reuse_suspected", False))
        + 0.25 * _flag(not crypto.get("weak_cipher_hint", False))
    )

    # Freshness: implausible drain rate hints at injected telemetry.
    freshness = 1.0
    drain = _as_float(ext_tel.get("battery_drain_rate"))
    if drain is not None and (drain <= 0.0 or drain > 6.0):
        freshness -= 0.3
        reasons.append("implausible_drain_rate")

    # Internal consistency: the core FDI signal - external vs internal telemetry.
    consistency = 1.0
    ext_batt = _as_float(ext_tel.get("battery_percent"))
    int_batt = _as_float(int_tel.get("battery_percent"))
    if ext_batt is not None and int_batt is not None:
        gap = abs(ext_batt - int_batt)
        if gap > 0:
            consistency -= min(0.6, gap / 40.0)
            reasons.append("internal_external_telemetry_gap")
    if int_tel.get("motor_status") is not None and ext_tel.get("motor_status") != int_tel.get("motor_status"):
        consistency -= 0.3
        reasons.append("motor_status_mismatch")
    return {"identity_auth": _clamp(identity), "freshness": _clamp(freshness), "internal_consistency": _clamp(consistency)}, reasons


def _score_mission(external: dict, history: dict) -> tuple[dict[str, float], list[str]]:
    reasons: list[str] = []
    mission = external.get("mission", {})
    priorities = mission.get("area_priority", {})

    comms = external.get("comms", {})
    crypto = comms.get("crypto_profile", {})
    identity = (
        0.5 * _flag(comms.get("encrypted", True))
        + 0.25 * _flag(comms.get("route_metadata_visible", True))
        + 0.25 * _flag(not crypto.get("weak_cipher_hint", False))
    )

    # Freshness: priority drift away from the last accepted priority vector.
    freshness = 1.0
    last_priorities = history.get("last_area_priority", {})
    drift = _priority_drift(last_priorities, priorities)
    if drift > 0.0:
        freshness -= min(0.6, drift * 4.0)
        reasons.append("area_priority_drift")

    # Internal consistency: recommended_area must match the top priority area.
    consistency = 1.0
    recommended = mission.get("recommended_area")
    if priorities and recommended not in (None, "NONE"):
        top_area = max(priorities, key=lambda area: _as_float(priorities.get(area)) or 0.0)
        if recommended != top_area:
            consistency -= 0.5
            reasons.append("recommended_area_mismatch")
    return {"identity_auth": _clamp(identity), "freshness": _clamp(freshness), "internal_consistency": _clamp(consistency)}, reasons


def _channel_health(comms: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    health = 1.0
    latency = _as_float(comms.get("latency_ms"))
    if latency is not None and latency > 500:
        health -= min(0.4, (latency - 500) / 2000.0)
        reasons.append("high_channel_latency")
    loss = _as_float(comms.get("packet_loss"))
    if loss is not None and loss > 0.08:
        health -= min(0.3, (loss - 0.08) * 2.0)
        reasons.append("high_packet_loss")
    gap = _as_float(comms.get("heartbeat_gap_ms"))
    if gap is not None and gap > 1500:
        health -= min(0.3, (gap - 1500) / 6000.0)
        reasons.append("heartbeat_gap")
    return _clamp(health), reasons


def _capability_score(domain: str, capabilities: dict) -> tuple[float, list[str]]:
    capability = _DOMAIN_CAPABILITY[domain]
    state = capabilities.get(capability, "OK")
    score = {"OK": 1.0, "DEGRADED": 0.5}.get(state, 0.0)
    reasons = [] if score >= 1.0 else [f"{capability}_{str(state).lower()}"]
    return score, reasons


def zta_action_candidates(decisions: list[ZtaDecision]) -> list[dict[str, Any]]:
    """Policy Administrator role: map restrictive decisions to defense action
    candidates the Defense Planner already understands. Advisory only."""

    action_by_domain = {
        "command": "HOLD_COMMAND",
        "telemetry": "QUARANTINE_FIELD",
        "mission": "QUARANTINE_FIELD",
    }
    candidates: list[dict[str, Any]] = []
    for item in decisions:
        if not item.restrictive:
            continue
        if item.decision == "DOWNGRADE":
            action = "OBSERVE_DOMAIN"
        elif item.decision == "REVALIDATE":
            action = "REQUEST_REVALIDATION"
        else:
            action = action_by_domain[item.domain]
        candidates.append(
            {
                "action": action,
                "target": item.domain if action == "OBSERVE_DOMAIN" else item.resource,
                "domain": item.domain,
                "decision": item.decision,
                "trust_score": item.trust_score,
                "allowed_use": item.allowed_use,
                "availability_cost": item.availability_cost,
                "reasons": list(item.reasons),
            }
        )
    return candidates


def summarize_zta(step_decisions: list[list[ZtaDecision]], attack_target_domain: str | None) -> dict[str, Any]:
    """Round-level policy summary + a scorer-style ``policy_decision_correctness``.

    Correctness rewards restricting the domain that was actually attacked and
    leaving clean domains operational. It uses the strongest decision seen for
    each domain across the round (did Blue ever restrict it?).
    """

    strongest: dict[str, ZtaDecision] = {}
    decision_counts: dict[str, int] = {}
    for step in step_decisions:
        for item in step:
            decision_counts[item.decision] = decision_counts.get(item.decision, 0) + 1
            current = strongest.get(item.domain)
            if current is None or _restriction_rank(item.decision) > _restriction_rank(current.decision):
                strongest[item.domain] = item

    per_domain: dict[str, Any] = {}
    correct = 0
    for domain, item in strongest.items():
        should_restrict = domain == attack_target_domain
        restricted = item.restrictive
        is_correct = restricted == should_restrict
        correct += int(is_correct)
        per_domain[domain] = {
            "decision": item.decision,
            "trust_score": item.trust_score,
            "restricted": restricted,
            "expected_restricted": should_restrict,
            "correct": is_correct,
        }

    correctness = round(correct / len(strongest), 4) if strongest else 0.0
    return {
        "attack_target_domain": attack_target_domain,
        "policy_decision_correctness": correctness,
        "decision_counts": dict(sorted(decision_counts.items())),
        "per_domain": per_domain,
        "informational_availability_cost": round(
            sum(item.availability_cost for item in strongest.values()), 4
        ),
    }


def _threat_confidence_by_domain(threats: list[Threat]) -> dict[str, float]:
    by_domain: dict[str, float] = {}
    for threat in threats:
        by_domain[threat.target] = max(by_domain.get(threat.target, 0.0), float(threat.confidence))
    return by_domain


def _band(trust_score: float) -> str:
    for threshold, verdict in DECISION_BANDS:
        if trust_score >= threshold:
            return verdict
    return "DENY"


def _restriction_rank(verdict: str) -> int:
    order = ["ALLOW", "ALLOW_WITH_LOW_CONFIDENCE", "DOWNGRADE", "REVALIDATE", "QUARANTINE", "DENY"]
    return order.index(verdict) if verdict in order else 0


def _priority_drift(before: dict, after: dict) -> float:
    if not before or not after:
        return 0.0
    keys = set(before) | set(after)
    return round(sum(abs((_as_float(after.get(k)) or 0.0) - (_as_float(before.get(k)) or 0.0)) for k in keys), 4)


def _flag(value: Any) -> float:
    return 1.0 if value else 0.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None
