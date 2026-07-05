"""Observed-only Blue consistency checks for Red cyber-effect hypotheses.

Blue does not know Red's selected goal. These checks infer likely effects from
internal/external observe disagreement, history, and situation tags.
"""

from __future__ import annotations

from dah_flawless.config import CAPABILITY_FACTORS
from dah_flawless.schemas import Threat


EFFECT_TAGS = (
    "EFFECT_TELEMETRY_TRUST_EROSION",
    "EFFECT_WRONG_TARGET_SELECTION",
    "EFFECT_COMMAND_STALE_ACCEPTANCE",
    "EFFECT_ACK_CAUSAL_CONFUSION",
    "EFFECT_CHANNEL_STATE_SUPPRESSION",
    "EFFECT_DETECTION_BOUNDARY_PROBE",
)


def effect_ids_from_tags(tags: tuple[str, ...] | list[str]) -> list[str]:
    tag_set = set(tags)
    return sorted(tag for tag in EFFECT_TAGS if tag in tag_set)


def effect_id_from_goal_id(goal_id: str | None) -> str | None:
    if not goal_id:
        return None
    effect_id = f"EFFECT_{goal_id}"
    return effect_id if effect_id in EFFECT_TAGS else None


def infer_goal_effect_threats(
    redacted_state: dict,
    history: dict,
    tags: list[str],
    capabilities: dict | None = None,
) -> tuple[list[Threat], list[dict]]:
    obs = redacted_state["blue_observed"]
    tag_set = set(tags)
    capabilities = capabilities or {}
    hypotheses: list[dict] = []

    _maybe_add_telemetry_trust_erosion(hypotheses, obs, capabilities)
    _maybe_add_wrong_target_selection(hypotheses, obs, history)
    _maybe_add_command_stale_acceptance(hypotheses, obs, history, tag_set, capabilities)
    _maybe_add_ack_causal_confusion(hypotheses, obs, tag_set, capabilities)
    _maybe_add_channel_state_suppression(hypotheses, obs, tag_set, capabilities)
    _maybe_add_boundary_probe(hypotheses)

    threats = [_threat_from_hypothesis(hypothesis) for hypothesis in hypotheses if hypothesis["confidence"] >= 0.54]
    return threats, hypotheses


def merge_goal_effect_threats(base_threats: list[Threat], effect_threats: list[Threat]) -> list[Threat]:
    merged: dict[str, Threat] = {threat.target: threat for threat in base_threats}
    order = [threat.target for threat in base_threats]

    for threat in effect_threats:
        current = merged.get(threat.target)
        if current is None:
            merged[threat.target] = threat
            order.append(threat.target)
            continue

        merged[threat.target] = Threat(
            target=threat.target,
            confidence=round(max(current.confidence, threat.confidence), 3),
            tags=tuple(sorted(set(current.tags).union(threat.tags))),
            evidence=tuple(dict.fromkeys([*current.evidence, *threat.evidence])),
        )

    return [merged[target] for target in order]


def _maybe_add_telemetry_trust_erosion(hypotheses: list[dict], obs: dict, capabilities: dict) -> None:
    internal = obs.get("internal_observe", {}).get("telemetry", {})
    external = obs.get("telemetry", {})
    if not internal or not external:
        return

    battery_delta = abs(float(external.get("battery_percent", 0.0)) - float(internal.get("battery_percent", 0.0)))
    motor_mismatch = external.get("motor_status") != internal.get("motor_status")
    drain_mismatch = abs(
        float(external.get("battery_drain_rate", 0.0)) - float(internal.get("battery_drain_rate", 0.0))
    )
    effect_score = min(1.0, battery_delta / 35.0 + (0.25 if motor_mismatch else 0.0) + min(0.20, drain_mismatch / 5.0))
    if effect_score < 0.22:
        return

    confidence = (0.58 + effect_score * 0.36) * _capability_factor(capabilities, "cross_check_telemetry")
    _add_hypothesis(
        hypotheses,
        goal_id="TELEMETRY_TRUST_EROSION",
        target="telemetry",
        confidence=confidence,
        tags=("EFFECT_TELEMETRY_TRUST_EROSION", "INTERNAL_EXTERNAL_TELEMETRY_DISAGREE"),
        evidence=(
            f"external.telemetry.battery_percent={external.get('battery_percent')}",
            f"internal.telemetry.battery_percent={internal.get('battery_percent')}",
            f"battery_delta={round(battery_delta, 4)}",
            f"motor_mismatch={motor_mismatch}",
        ),
        effect_score=effect_score,
    )


def _maybe_add_wrong_target_selection(hypotheses: list[dict], obs: dict, history: dict) -> None:
    mission = obs.get("mission", {})
    current = mission.get("area_priority", {})
    previous = history.get("last_area_priority", {})
    if len(current) < 2 or len(previous) < 2:
        return

    top_current = _top_area(current)
    top_previous = _top_area(previous)
    recommended = mission.get("recommended_area")
    max_delta = max(abs(float(current.get(area, 0.0)) - float(previous.get(area, 0.0))) for area in previous)
    top_shift = top_current != top_previous
    recommendation_shift = recommended is not None and recommended != top_previous
    effect_score = min(1.0, max_delta + (0.25 if top_shift else 0.0) + (0.15 if recommendation_shift else 0.0))
    if effect_score < 0.22:
        return

    _add_hypothesis(
        hypotheses,
        goal_id="WRONG_TARGET_SELECTION",
        target="mission",
        confidence=0.56 + effect_score * 0.34,
        tags=("EFFECT_WRONG_TARGET_SELECTION", "MISSION_BELIEF_DRIFT"),
        evidence=(
            f"history.top_area={top_previous}",
            f"observed.top_area={top_current}",
            f"observed.recommended_area={recommended}",
            f"max_priority_delta={round(max_delta, 4)}",
        ),
        effect_score=effect_score,
    )


def _maybe_add_command_stale_acceptance(
    hypotheses: list[dict],
    obs: dict,
    history: dict,
    tag_set: set[str],
    capabilities: dict,
) -> None:
    c2 = obs.get("c2_message", {})
    time = obs.get("time", {})
    sequence_lag = max(0, int(history.get("last_sequence_number", 0)) - int(c2.get("sequence_number", 0)))
    timestamp_lag = max(0, int(history.get("last_received_timestamp", 0)) - int(time.get("received_timestamp", 0)))
    replay_tags = {"SEQUENCE_REGRESSION", "TIMESTAMP_SKEW", "REPLAY_SUSPECTED"}.intersection(tag_set)
    effect_score = min(1.0, sequence_lag / 4.0 + timestamp_lag / 120.0 + len(replay_tags) * 0.18)
    if effect_score < 0.20:
        return

    confidence = (0.58 + effect_score * 0.35) * _capability_factor(capabilities, "time_validation")
    _add_hypothesis(
        hypotheses,
        goal_id="COMMAND_STALE_ACCEPTANCE",
        target="command",
        confidence=confidence,
        tags=("EFFECT_COMMAND_STALE_ACCEPTANCE", "STALE_COMMAND_METADATA"),
        evidence=(
            f"sequence_lag_vs_history={sequence_lag}",
            f"timestamp_lag_vs_history_s={timestamp_lag}",
            f"replay_tags={sorted(replay_tags)}",
        ),
        effect_score=effect_score,
    )


def _maybe_add_ack_causal_confusion(
    hypotheses: list[dict],
    obs: dict,
    tag_set: set[str],
    capabilities: dict,
) -> None:
    c2 = obs.get("c2_message", {})
    comms = obs.get("comms", {})
    ack = c2.get("ack", {})
    ack_visible = bool(comms.get("ack_visible") or ack.get("visible"))
    if not ack_visible:
        return

    sequence_number = int(c2.get("sequence_number", 0))
    ack_sequence = int(ack.get("sequence_number", sequence_number))
    ack_gap = abs(sequence_number - ack_sequence)
    ack_delay = int(comms.get("ack_delay_ms", 0))
    accepted_with_gap = ack.get("status") == "ACCEPTED" and ack_gap > 0
    effect_score = min(
        1.0,
        ack_gap / 4.0
        + ack_delay / 1600.0
        + (0.18 if "ACK_TIMING_ANOMALY" in tag_set else 0.0)
        + (0.12 if accepted_with_gap else 0.0),
    )
    if effect_score < 0.24:
        return

    confidence = (0.55 + effect_score * 0.38) * _capability_factor(capabilities, "time_validation")
    _add_hypothesis(
        hypotheses,
        goal_id="ACK_CAUSAL_CONFUSION",
        target="command",
        confidence=confidence,
        tags=("EFFECT_ACK_CAUSAL_CONFUSION", "ACK_CAUSALITY_BREAK"),
        evidence=(
            f"c2_message.sequence_number={sequence_number}",
            f"c2_message.ack.sequence_number={ack_sequence}",
            f"ack_gap={ack_gap}",
            f"ack_delay_ms={ack_delay}",
            f"accepted_with_gap={accepted_with_gap}",
        ),
        effect_score=effect_score,
    )


def _maybe_add_channel_state_suppression(
    hypotheses: list[dict],
    obs: dict,
    tag_set: set[str],
    capabilities: dict,
) -> None:
    comms = obs.get("comms", {})
    packet_loss = float(comms.get("packet_loss", 0.0))
    latency_ms = int(comms.get("latency_ms", 0))
    heartbeat_gap_ms = int(comms.get("heartbeat_gap_ms", 0))
    jitter_ms = int(comms.get("packet_interval_jitter_ms", 0))
    queue_depth = int(comms.get("message_queue_depth", 0))
    effect_tags = {"PACKET_LOSS_HIGH", "HEARTBEAT_GAP", "PACKET_INTERVAL_ANOMALY", "HIGH_LATENCY"}.intersection(tag_set)
    effect_score = min(
        1.0,
        packet_loss * 2.0
        + latency_ms / 1300.0
        + heartbeat_gap_ms / 7000.0
        + jitter_ms / 1500.0
        + queue_depth / 50.0
        + len(effect_tags) * 0.06,
    )
    if effect_score < 0.28:
        return

    confidence = (0.52 + effect_score * 0.40) * _capability_factor(capabilities, "time_validation")
    _add_hypothesis(
        hypotheses,
        goal_id="CHANNEL_STATE_SUPPRESSION",
        target="command",
        confidence=confidence,
        tags=("EFFECT_CHANNEL_STATE_SUPPRESSION", "CHANNEL_FRESHNESS_LOSS"),
        evidence=(
            f"packet_loss={round(packet_loss, 4)}",
            f"latency_ms={latency_ms}",
            f"heartbeat_gap_ms={heartbeat_gap_ms}",
            f"packet_interval_jitter_ms={jitter_ms}",
            f"message_queue_depth={queue_depth}",
        ),
        effect_score=effect_score,
    )


def _maybe_add_boundary_probe(hypotheses: list[dict]) -> None:
    if len(hypotheses) != 1:
        return
    current = hypotheses[0]
    if not (0.20 <= current["effect_score"] <= 0.48 and current["confidence"] < 0.74):
        return

    _add_hypothesis(
        hypotheses,
        goal_id="DETECTION_BOUNDARY_PROBE",
        target=current["target"],
        confidence=max(0.54, current["confidence"] - 0.08),
        tags=("EFFECT_DETECTION_BOUNDARY_PROBE", "LOW_AMPLITUDE_EFFECT_PROBE"),
        evidence=(
            f"source_goal_id={current['goal_id']}",
            f"source_effect_score={current['effect_score']}",
            f"source_confidence={current['confidence']}",
        ),
        effect_score=current["effect_score"],
    )


def _add_hypothesis(
    hypotheses: list[dict],
    *,
    goal_id: str,
    target: str,
    confidence: float,
    tags: tuple[str, ...],
    evidence: tuple[str, ...],
    effect_score: float,
) -> None:
    hypotheses.append(
        {
            "goal_id": goal_id,
            "target": target,
            "confidence": round(min(0.99, max(0.01, confidence)), 3),
            "tags": list(tags),
            "evidence": list(evidence),
            "effect_score": round(min(1.0, max(0.0, effect_score)), 4),
            "source": "observed_only_goal_consistency",
        }
    )


def _threat_from_hypothesis(hypothesis: dict) -> Threat:
    return Threat(
        target=hypothesis["target"],
        confidence=hypothesis["confidence"],
        tags=tuple(hypothesis["tags"]),
        evidence=tuple([f"suspected_goal_id={hypothesis['goal_id']}", *hypothesis["evidence"]]),
    )


def _top_area(priorities: dict[str, float]) -> str:
    return max(priorities, key=lambda area: float(priorities[area]))


def _capability_factor(capabilities: dict, name: str) -> float:
    return CAPABILITY_FACTORS.get(capabilities.get(name, "OK"), 1.0)
