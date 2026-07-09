"""Tag-scored Attack Selector and tactic selector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dah_flawless.config import DEFAULT_MUTATION_PROFILE, MUTATION_PROFILES
from dah_flawless.attacks.effect_contracts import contract_supports_tactic, score_contract_alignment
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
    params_by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)


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
        attack_name="PRIORITY_POISONING",
        strategy="recommended_area_nudge",
        goal="bias the recommendation field before the full priority vector flips",
        preferred_tags=("METADATA_PLAINTEXT", "PAYLOAD_HIDDEN", "MISSION_PRIORITY_CHANGED"),
        base_score=1.5,
        impact=1.9,
        detectability=0.7,
        cost=0.25,
    ),
    TacticSpec(
        attack_name="PRIORITY_POISONING",
        strategy="mission_confidence_shaping",
        goal="make the wrong area appear consistently better across adjacent priority fields",
        preferred_tags=("MISSION_PRIORITY_CHANGED", "C2_ENCRYPTED", "PAYLOAD_HIDDEN"),
        base_score=1.45,
        impact=1.8,
        detectability=0.75,
        cost=0.32,
    ),
    TacticSpec(
        attack_name="TELEMETRY_FDI",
        strategy="telemetry_false_data",
        goal="use read-only telemetry memory to send a plausible command/ack decoy",
        preferred_tags=("GNSS_PRIMARY", "C2_ENCRYPTED", "CROSS_CHECK_UNAVAILABLE"),
        base_score=1.5,
        impact=2.0,
        detectability=0.9,
        cost=0.4,
        params_by_profile={
            "stealth": {
                "ack_sequence_delta": -1,
                "ack_delay_ms": 360,
                "latency_ms": 300,
                "packet_interval_jitter_ms": 150,
            },
            "aggressive": {
                "ack_sequence_delta": -2,
                "ack_delay_ms": 950,
                "latency_ms": 540,
                "packet_interval_jitter_ms": 460,
            },
            "loud_demo": {
                "ack_sequence_delta": -5,
                "ack_delay_ms": 1500,
                "latency_ms": 1200,
                "packet_interval_jitter_ms": 900,
            },
        },
    ),
    TacticSpec(
        attack_name="TELEMETRY_FDI",
        strategy="confidence_spoofing",
        goal="blend the decoy with link timing so telemetry-derived uncertainty looks operationally plausible",
        preferred_tags=("CROSS_CHECK_UNAVAILABLE", "GNSS_PRIMARY", "C2_ENCRYPTED"),
        base_score=1.35,
        impact=1.7,
        detectability=0.65,
        cost=0.35,
        params_by_profile={
            "stealth": {
                "ack_sequence_delta": -1,
                "ack_delay_ms": 330,
                "latency_ms": 280,
                "packet_interval_jitter_ms": 140,
            },
            "aggressive": {
                "ack_sequence_delta": -1,
                "ack_delay_ms": 760,
                "latency_ms": 640,
                "packet_interval_jitter_ms": 520,
            },
            "loud_demo": {
                "ack_sequence_delta": -3,
                "ack_delay_ms": 1320,
                "latency_ms": 1300,
                "packet_interval_jitter_ms": 920,
            },
        },
    ),
    TacticSpec(
        attack_name="TELEMETRY_FDI",
        strategy="internal_external_gap_shaping",
        goal="reuse remembered tx/rx telemetry context to widen command interpretation ambiguity",
        preferred_tags=("TELEMETRY_CONFLICT", "CROSS_CHECK_UNAVAILABLE", "GNSS_DEGRADED"),
        base_score=1.45,
        impact=1.9,
        detectability=0.8,
        cost=0.42,
        params_by_profile={
            "stealth": {
                "ack_sequence_delta": -1,
                "ack_delay_ms": 360,
                "latency_ms": 300,
                "packet_interval_jitter_ms": 150,
            },
            "aggressive": {
                "ack_sequence_delta": -2,
                "ack_delay_ms": 980,
                "latency_ms": 580,
                "packet_interval_jitter_ms": 480,
            },
            "loud_demo": {
                "ack_sequence_delta": -5,
                "ack_delay_ms": 1500,
                "latency_ms": 1200,
                "packet_interval_jitter_ms": 900,
            },
        },
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
        params_by_profile={
            "stealth": {"sequence_delta": -2, "timestamp_delta_s": -5},
            "aggressive": {"sequence_delta": -8, "timestamp_delta_s": -45},
            "loud_demo": {"sequence_delta": -13, "timestamp_delta_s": -400},
        },
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
        params_by_profile={
            "stealth": {"timestamp_delta_s": -5, "latency_ms": 300, "packet_interval_jitter_ms": 150},
            "aggressive": {"timestamp_delta_s": -45, "latency_ms": 720, "packet_interval_jitter_ms": 460},
            "loud_demo": {"timestamp_delta_s": -180, "latency_ms": 900, "packet_interval_jitter_ms": 700},
        },
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
        params_by_profile={
            "stealth": {"packet_loss": 0.05, "heartbeat_gap_ms": 2000, "packet_interval_jitter_ms": 150},
            "aggressive": {"packet_loss": 0.16, "heartbeat_gap_ms": 3600, "packet_interval_jitter_ms": 460},
            "loud_demo": {"packet_loss": 0.30, "heartbeat_gap_ms": 6000, "packet_interval_jitter_ms": 800},
        },
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
        params_by_profile={
            "stealth": {"ack_delay_ms": 300, "ack_sequence_delta": -1, "latency_ms": 300},
            "aggressive": {"ack_delay_ms": 950, "ack_sequence_delta": -2, "latency_ms": 540},
            "loud_demo": {"ack_delay_ms": 1500, "ack_sequence_delta": -5, "latency_ms": 1200},
        },
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
        params_by_profile={
            "stealth": {"sequence_delta": -1, "timestamp_delta_s": -5, "latency_ms": 250},
            "aggressive": {"sequence_delta": -2, "timestamp_delta_s": -45, "latency_ms": 620},
            "loud_demo": {"sequence_delta": -8, "timestamp_delta_s": -90, "latency_ms": 1000},
        },
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
    ("recommended_area_nudge", "METADATA_PLAINTEXT"): 1.5,
    ("mission_confidence_shaping", "MISSION_PRIORITY_CHANGED"): 1.4,
    ("confidence_spoofing", "CROSS_CHECK_UNAVAILABLE"): 1.5,
    ("internal_external_gap_shaping", "TELEMETRY_CONFLICT"): 1.5,
}

ATTACK_DIVERSITY_WINDOW = 8
ATTACK_REPEAT_PENALTY_PER_USE = 0.12
ATTACK_CONSECUTIVE_PENALTY_PER_USE = 0.16
ATTACK_UNDERUSED_BONUS_PER_COUNT = 0.10
MAX_ATTACK_DIVERSITY_PENALTY = 0.78
MAX_ATTACK_UNDERUSED_BONUS = 0.35


def score_attack_candidates(
    attacks: list[Attack],
    learned_weights: dict[str, float],
    tag_details: list[SituationTag] | None,
    goal_plan: dict[str, Any] | None = None,
    previous_logs: list[dict] | None = None,
) -> list[dict[str, Any]]:
    tag_confidence = _tag_confidence(tag_details)
    candidates = []
    preferred_attacks = set((goal_plan or {}).get("preferred_attacks", []))
    goal_target_domain = (goal_plan or {}).get("target_domain")
    recent_counts = _recent_attack_counts(previous_logs or [], window=ATTACK_DIVERSITY_WINDOW)
    total_counts = _total_attack_counts(previous_logs or [])
    mean_count = sum(total_counts.values()) / max(1, len(attacks))

    for attack in attacks:
        matched_tags = sorted(set(attack.preferred_tags).intersection(tag_confidence))
        matched_strength = round(sum(tag_confidence[tag] for tag in matched_tags), 3)
        goal_bonus = 0.0
        if attack.name in preferred_attacks:
            goal_bonus += 0.35
        if goal_target_domain in {attack.target_domain, "multi_domain"}:
            goal_bonus += 0.12
        contract_alignment = score_contract_alignment(attack.name, goal_plan, tag_details)
        contract_multiplier = round(0.20 + 0.80 * float(contract_alignment["score"]), 4)
        if (goal_plan or {}).get("goal_id") and not contract_alignment["supported_goal"]:
            score = 0.0
        else:
            base_score = (
                learned_weights.get(attack.name, attack.weight)
                * (1.0 + min(2.5, 0.7 * matched_strength) + goal_bonus)
                * contract_multiplier
            )
            repeat_penalty = _attack_diversity_penalty(attack.name, previous_logs or [], recent_counts)
            underused_bonus = _attack_underused_bonus(total_counts.get(attack.name, 0), mean_count)
            score = round(
                max(0.0, base_score * max(0.0, 1.0 - repeat_penalty) + underused_bonus),
                3,
            )
        repeat_penalty = _attack_diversity_penalty(attack.name, previous_logs or [], recent_counts)
        underused_bonus = _attack_underused_bonus(total_counts.get(attack.name, 0), mean_count)
        candidates.append(
            {
                "attack": attack.name,
                "score": score,
                "base_weight": learned_weights.get(attack.name, attack.weight),
                "matched_tags": matched_tags,
                "matched_strength": matched_strength,
                "goal_bonus": round(goal_bonus, 3),
                "contract_multiplier": contract_multiplier,
                "contract_alignment": contract_alignment,
                "goal_id": (goal_plan or {}).get("goal_id"),
                "attack_repeat_penalty": round(repeat_penalty, 4),
                "attack_underused_bonus": round(underused_bonus, 4),
                "recent_attack_count": recent_counts.get(attack.name, 0),
                "consecutive_attack_count": _consecutive_attack_count(previous_logs or [], attack.name),
            }
        )

    return sorted(candidates, key=lambda item: (-item["score"], item["attack"]))


def build_tactic(
    attack_name: str,
    stealth: bool,
    tag_details: list[SituationTag] | None,
    telemetry_probe_delta: int,
    mutation_profile: str = DEFAULT_MUTATION_PROFILE,
    goal_plan: dict[str, Any] | None = None,
    rng: Any | None = None,
    exploration_rate: float = 0.0,
    recent_tactics: list[str] | None = None,
) -> dict[str, Any]:
    profile = _profile_for_tactic(stealth, mutation_profile)
    if stealth and attack_name == "TELEMETRY_FDI":
        return {
            "stealth": True,
            "mutation_profile": profile,
            "strategy": "boundary_probe",
            "probe_delta": telemetry_probe_delta,
            "selector": "stealth_controller",
            "goal_plan": goal_plan,
        }

    tactic_scores = score_tactic_candidates(
        attack_name,
        tag_details,
        goal_plan=goal_plan,
        recent_tactics=recent_tactics,
    )
    if not tactic_scores:
        return {
            "stealth": stealth,
            "mutation_profile": profile,
            "strategy": "no_boundary_margin" if stealth else "profile_direct_mutation",
            "selector": "fallback",
            "goal_plan": goal_plan,
        }

    chosen, selector_reason = _select_tactic_candidate(tactic_scores, rng=rng, exploration_rate=exploration_rate)
    return {
        "stealth": stealth,
        "mutation_profile": profile,
        "strategy": chosen["strategy"],
        "goal": chosen["goal"],
        "goal_plan": goal_plan,
        "selector": selector_reason,
        "exploration_rate": round(exploration_rate, 4),
        "score": chosen["score"],
        "score_breakdown": chosen["score_breakdown"],
        "matched_tags": chosen["matched_tags"],
        "params": _params_for_profile(chosen, profile),
        "params_by_profile": chosen["params_by_profile"],
        "candidate_scores": tactic_scores,
    }


def score_tactic_candidates(
    attack_name: str,
    tag_details: list[SituationTag] | None,
    goal_plan: dict[str, Any] | None = None,
    recent_tactics: list[str] | None = None,
) -> list[dict[str, Any]]:
    tag_confidence = _tag_confidence(tag_details)
    preferred_tactics = set((goal_plan or {}).get("preferred_tactics", []))
    preferred_goal_tags = set((goal_plan or {}).get("matched_tags", []))
    recent_counts = {strategy: (recent_tactics or []).count(strategy) for strategy in set(recent_tactics or [])}
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
        goal_bonus = 0.0
        if tactic.strategy in preferred_tactics:
            goal_bonus += 0.8
        if preferred_goal_tags.intersection(matched_tags):
            goal_bonus += 0.25
        contract_tactic_bonus = 0.20 if contract_supports_tactic(attack_name, tactic.strategy) else -0.60
        repeat_penalty = min(1.20, 0.45 * recent_counts.get(tactic.strategy, 0))
        score = round(
            tactic.base_score
            + tactic.impact
            + tag_bonus
            + goal_bonus
            + contract_tactic_bonus
            - repeat_penalty
            - tactic.detectability
            - tactic.cost,
            3,
        )
        candidates.append(
            {
                "attack": tactic.attack_name,
                "strategy": tactic.strategy,
                "goal": tactic.goal,
                "score": score,
                "matched_tags": matched_tags,
                "goal_bonus": round(goal_bonus, 3),
                "contract_tactic_bonus": contract_tactic_bonus,
                "repeat_penalty": repeat_penalty,
                "goal_id": (goal_plan or {}).get("goal_id"),
                "params": dict(tactic.params),
                "params_by_profile": {profile: dict(params) for profile, params in tactic.params_by_profile.items()},
                "score_breakdown": {
                    "base_score": tactic.base_score,
                    "impact": tactic.impact,
                    "matched_strength": matched_strength,
                    "tag_bonus": tag_bonus,
                    "goal_bonus": round(goal_bonus, 3),
                    "contract_tactic_bonus": contract_tactic_bonus,
                    "repeat_penalty": repeat_penalty,
                    "detectability_penalty": tactic.detectability,
                    "execution_cost": tactic.cost,
                },
            }
        )

    return sorted(candidates, key=lambda item: (-item["score"], item["strategy"]))


def _tag_confidence(tag_details: list[SituationTag] | None) -> dict[str, float]:
    return {detail.tag: detail.confidence for detail in tag_details or []}


def _recent_attack_counts(previous_logs: list[dict], window: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in previous_logs[-window:]:
        attack_name = _attack_name_from_log(entry)
        if attack_name:
            counts[attack_name] = counts.get(attack_name, 0) + 1
    return counts


def _total_attack_counts(previous_logs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in previous_logs:
        attack_name = _attack_name_from_log(entry)
        if attack_name:
            counts[attack_name] = counts.get(attack_name, 0) + 1
    return counts


def _attack_diversity_penalty(
    attack_name: str,
    previous_logs: list[dict],
    recent_counts: dict[str, int],
) -> float:
    recent_count = recent_counts.get(attack_name, 0)
    consecutive_count = _consecutive_attack_count(previous_logs, attack_name)
    penalty = (
        ATTACK_REPEAT_PENALTY_PER_USE * recent_count
        + ATTACK_CONSECUTIVE_PENALTY_PER_USE * consecutive_count
    )
    return round(min(MAX_ATTACK_DIVERSITY_PENALTY, penalty), 4)


def _attack_underused_bonus(count: int, mean_count: float) -> float:
    if count >= mean_count:
        return 0.0
    return round(min(MAX_ATTACK_UNDERUSED_BONUS, (mean_count - count) * ATTACK_UNDERUSED_BONUS_PER_COUNT), 4)


def _consecutive_attack_count(previous_logs: list[dict], attack_name: str) -> int:
    count = 0
    for entry in reversed(previous_logs):
        if _attack_name_from_log(entry) != attack_name:
            break
        count += 1
    return count


def _attack_name_from_log(entry: dict) -> str | None:
    attack = entry.get("attack") or {}
    return attack.get("name")


def _profile_for_tactic(stealth: bool, mutation_profile: str) -> str:
    if stealth:
        return "stealth"
    if mutation_profile not in MUTATION_PROFILES:
        return DEFAULT_MUTATION_PROFILE
    return mutation_profile


def _params_for_profile(candidate: dict[str, Any], profile: str) -> dict[str, Any]:
    params_by_profile = candidate.get("params_by_profile") or {}
    if profile in params_by_profile:
        return dict(params_by_profile[profile])
    return dict(candidate.get("params", {}))


def _select_tactic_candidate(
    tactic_scores: list[dict[str, Any]],
    *,
    rng: Any | None,
    exploration_rate: float,
) -> tuple[dict[str, Any], str]:
    if not tactic_scores:
        raise ValueError("tactic_scores must not be empty")
    if len(tactic_scores) > 1:
        top = tactic_scores[0]
        runner_up = tactic_scores[1]
        if top.get("repeat_penalty", 0.0) >= 0.90 and runner_up["score"] >= top["score"] - 0.40:
            return runner_up, "contract_compatible_repeat_guard"
    if rng is None or exploration_rate <= 0.0 or len(tactic_scores) == 1:
        return tactic_scores[0], "tag_scored_tactic_policy"
    if rng.random() >= min(1.0, max(0.0, exploration_rate)):
        return tactic_scores[0], "tag_scored_tactic_policy"

    positive = [candidate for candidate in tactic_scores if candidate["score"] > 0]
    if not positive:
        return tactic_scores[0], "tag_scored_tactic_policy"
    total = sum(candidate["score"] for candidate in positive)
    pick = rng.uniform(0.0, total)
    cursor = 0.0
    for candidate in positive:
        cursor += candidate["score"]
        if pick <= cursor:
            return candidate, "contract_compatible_tactic_exploration"
    return positive[-1], "contract_compatible_tactic_exploration"
