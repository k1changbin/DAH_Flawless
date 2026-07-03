"""Tag-scored Attack Selector and tactic selector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dah_flawless.schemas import Attack, SituationTag


@dataclass(frozen=True)
class TacticSpec:
    attack_name: str
    strategy: str
    goal: str
    preferred_tags: tuple[str, ...]
    base_score: float
    impact: float
    detectability: float
    cost: float
    params: dict[str, Any] = field(default_factory=dict)


TACTIC_CATALOG: tuple[TacticSpec, ...] = (
    TacticSpec(
        attack_name="PRIORITY_POISONING",
        strategy="mission_priority_shift",
        goal="bias target-area selection through observed mission priority fields",
        preferred_tags=("PAYLOAD_HIDDEN", "C2_ENCRYPTED", "METADATA_PLAINTEXT"),
        base_score=1.6,
        impact=1.8,
        detectability=0.8,
        cost=0.3,
    ),
    TacticSpec(
        attack_name="TELEMETRY_FDI",
        strategy="telemetry_false_data",
        goal="make observed telemetry disagree with physical mission constraints",
        preferred_tags=("GNSS_PRIMARY", "C2_ENCRYPTED", "CROSS_CHECK_UNAVAILABLE"),
        base_score=1.5,
        impact=2.0,
        detectability=0.9,
        cost=0.4,
    ),
    TacticSpec(
        attack_name="TIME_DESYNC_REPLAY",
        strategy="replay",
        goal="reuse stale command metadata as if it were current",
        preferred_tags=(
            "SEQUENCE_VISIBLE",
            "TIMESTAMP_VISIBLE",
            "REPLAY_WINDOW_OPEN",
            "C2_ENCRYPTED",
            "PAYLOAD_HIDDEN",
        ),
        base_score=1.9,
        impact=2.1,
        detectability=0.9,
        cost=0.4,
        params={"sequence_delta": -13, "timestamp_delta_s": -400},
    ),
    TacticSpec(
        attack_name="TIME_DESYNC_REPLAY",
        strategy="delay",
        goal="delay state or command delivery until Blue reasons over stale state",
        preferred_tags=(
            "TIMESTAMP_VISIBLE",
            "REGULAR_PACKET_INTERVAL",
            "STATE_UPDATE_DEPENDENT",
            "HIGH_LATENCY",
            "PACKET_INTERVAL_ANOMALY",
        ),
        base_score=1.5,
        impact=1.9,
        detectability=0.7,
        cost=0.5,
        params={"timestamp_delta_s": -180, "latency_ms": 900},
    ),
    TacticSpec(
        attack_name="TIME_DESYNC_REPLAY",
        strategy="selective_drop",
        goal="create a heartbeat or state-update gap without inspecting encrypted payload",
        preferred_tags=(
            "PACKET_SIZE_PATTERN",
            "STATE_UPDATE_DEPENDENT",
            "PACKET_LOSS_HIGH",
            "HEARTBEAT_GAP",
        ),
        base_score=1.3,
        impact=1.8,
        detectability=0.8,
        cost=0.7,
        params={"packet_loss": 0.16, "heartbeat_gap_ms": 3600},
    ),
    TacticSpec(
        attack_name="TIME_DESYNC_REPLAY",
        strategy="ack_confusion",
        goal="break command-to-ack causality so Blue misreads command acceptance",
        preferred_tags=("ACK_CHANNEL_VISIBLE", "ACK_TIMING_ANOMALY", "SEQUENCE_VISIBLE"),
        base_score=1.7,
        impact=2.0,
        detectability=0.65,
        cost=0.4,
        params={"ack_delay_ms": 950, "ack_sequence_delta": -2},
    ),
    TacticSpec(
        attack_name="TIME_DESYNC_REPLAY",
        strategy="metadata_poisoning",
        goal="alter visible metadata while encrypted payload remains opaque",
        preferred_tags=(
            "METADATA_PLAINTEXT",
            "SEQUENCE_VISIBLE",
            "TIMESTAMP_VISIBLE",
            "STATE_UPDATE_DEPENDENT",
        ),
        base_score=1.6,
        impact=1.9,
        detectability=0.85,
        cost=0.4,
        params={"sequence_delta": -2, "timestamp_delta_s": -90},
    ),
)

TACTIC_TAG_MULTIPLIERS: dict[tuple[str, str], float] = {
    ("ack_confusion", "ACK_TIMING_ANOMALY"): 3.5,
    ("ack_confusion", "ACK_CHANNEL_VISIBLE"): 1.3,
    ("selective_drop", "HEARTBEAT_GAP"): 3.2,
    ("selective_drop", "PACKET_LOSS_HIGH"): 1.7,
    ("delay", "PACKET_INTERVAL_ANOMALY"): 2.4,
    ("delay", "HIGH_LATENCY"): 1.6,
    ("metadata_poisoning", "METADATA_PLAINTEXT"): 1.7,
    ("replay", "REPLAY_WINDOW_OPEN"): 1.4,
}


def score_attack_candidates(
    attacks: list[Attack],
    learned_weights: dict[str, float],
    tag_details: list[SituationTag] | None,
) -> list[dict[str, Any]]:
    tag_confidence = _tag_confidence(tag_details)
    candidates = []

    for attack in attacks:
        matched_tags = sorted(set(attack.preferred_tags).intersection(tag_confidence))
        matched_strength = round(sum(tag_confidence[tag] for tag in matched_tags), 3)
        score = round(learned_weights.get(attack.name, attack.weight) * (1.0 + min(2.5, 0.7 * matched_strength)), 3)
        candidates.append(
            {
                "attack": attack.name,
                "score": score,
                "base_weight": learned_weights.get(attack.name, attack.weight),
                "matched_tags": matched_tags,
                "matched_strength": matched_strength,
            }
        )

    return sorted(candidates, key=lambda item: (-item["score"], item["attack"]))


def build_tactic(
    attack_name: str,
    stealth: bool,
    tag_details: list[SituationTag] | None,
    telemetry_probe_delta: int,
) -> dict[str, Any]:
    if stealth and attack_name == "TELEMETRY_FDI":
        return {
            "stealth": True,
            "strategy": "boundary_probe",
            "probe_delta": telemetry_probe_delta,
            "selector": "stealth_controller",
        }

    tactic_scores = score_tactic_candidates(attack_name, tag_details)
    if not tactic_scores:
        return {
            "stealth": stealth,
            "strategy": "no_boundary_margin" if stealth else "loud",
            "selector": "fallback",
        }

    chosen = tactic_scores[0]
    return {
        "stealth": stealth,
        "strategy": chosen["strategy"],
        "goal": chosen["goal"],
        "selector": "tag_scored_tactic_policy",
        "score": chosen["score"],
        "score_breakdown": chosen["score_breakdown"],
        "matched_tags": chosen["matched_tags"],
        "params": chosen["params"],
        "candidate_scores": tactic_scores,
    }


def score_tactic_candidates(attack_name: str, tag_details: list[SituationTag] | None) -> list[dict[str, Any]]:
    tag_confidence = _tag_confidence(tag_details)
    candidates = []

    for tactic in TACTIC_CATALOG:
        if tactic.attack_name != attack_name:
            continue
        matched_tags = sorted(set(tactic.preferred_tags).intersection(tag_confidence))
        matched_strength = round(
            sum(
                tag_confidence[tag] * TACTIC_TAG_MULTIPLIERS.get((tactic.strategy, tag), 1.0)
                for tag in matched_tags
            ),
            3,
        )
        tag_bonus = round(matched_strength * 1.15, 3)
        score = round(tactic.base_score + tactic.impact + tag_bonus - tactic.detectability - tactic.cost, 3)
        candidates.append(
            {
                "attack": tactic.attack_name,
                "strategy": tactic.strategy,
                "goal": tactic.goal,
                "score": score,
                "matched_tags": matched_tags,
                "params": dict(tactic.params),
                "score_breakdown": {
                    "base_score": tactic.base_score,
                    "impact": tactic.impact,
                    "matched_strength": matched_strength,
                    "tag_bonus": tag_bonus,
                    "detectability_penalty": tactic.detectability,
                    "execution_cost": tactic.cost,
                },
            }
        )

    return sorted(candidates, key=lambda item: (-item["score"], item["strategy"]))


def _tag_confidence(tag_details: list[SituationTag] | None) -> dict[str, float]:
    return {detail.tag: detail.confidence for detail in tag_details or []}
