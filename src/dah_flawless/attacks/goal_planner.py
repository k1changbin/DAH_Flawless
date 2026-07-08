"""Goal planner for simulated Red cyber effects.

The planner chooses *effects* such as stale-command acceptance or mission-belief
drift, not real-world attack procedures. It uses a small contextual UCB-style
score: current tags and observed state provide context, previous logs provide
reward history, and a confidence bonus keeps under-tried goals visible.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import log, sqrt
from typing import Any

from dah_flawless.scoring.telemetry_learning import telemetry_learning_signal
from dah_flawless.schemas import Score, SituationTag

GOAL_DIVERSITY_WINDOW = 6
GOAL_REPEAT_PENALTY_PER_USE = 0.10
GOAL_CONSECUTIVE_PENALTY_PER_USE = 0.12
GOAL_DOMAIN_REPEAT_PENALTY_PER_USE = 0.035
GOAL_UNDERUSED_BONUS_PER_COUNT = 0.04
MAX_GOAL_DIVERSITY_PENALTY = 0.45
MAX_GOAL_UNDERUSED_BONUS = 0.16


@dataclass(frozen=True)
class GoalSpec:
    goal_id: str
    target_domain: str
    intended_effect: str
    preferred_attacks: tuple[str, ...]
    preferred_tactics: tuple[str, ...]
    preferred_tags: tuple[str, ...]
    cyber_effects: tuple[str, ...]
    mission_impact: float
    detectability_risk: float
    policy_risk: float
    learning_value: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("preferred_attacks", "preferred_tactics", "preferred_tags", "cyber_effects"):
            data[key] = list(data[key])
        return data


GOAL_CATALOG: tuple[GoalSpec, ...] = (
    GoalSpec(
        goal_id="COMMAND_STALE_ACCEPTANCE",
        target_domain="command",
        intended_effect="make stale command or state metadata look operationally current",
        preferred_attacks=("TIME_DESYNC_REPLAY",),
        preferred_tactics=("replay", "metadata_poisoning"),
        preferred_tags=("SEQUENCE_VISIBLE", "TIMESTAMP_VISIBLE", "REPLAY_WINDOW_OPEN", "C2_ENCRYPTED", "PAYLOAD_HIDDEN"),
        cyber_effects=("encrypted_payload_opacity", "metadata_timing", "sequence_freshness"),
        mission_impact=0.88,
        detectability_risk=0.62,
        policy_risk=0.18,
        learning_value=0.62,
    ),
    GoalSpec(
        goal_id="ACK_CAUSAL_CONFUSION",
        target_domain="command",
        intended_effect="break command-to-ack causality inside observed metadata",
        preferred_attacks=("TIME_DESYNC_REPLAY",),
        preferred_tactics=("ack_confusion",),
        preferred_tags=("ACK_CHANNEL_VISIBLE", "ACK_TIMING_ANOMALY", "SEQUENCE_VISIBLE", "HIGH_LATENCY"),
        cyber_effects=("ack_semantics", "metadata_consistency", "command_acceptance_belief"),
        mission_impact=0.82,
        detectability_risk=0.58,
        policy_risk=0.16,
        learning_value=0.68,
    ),
    GoalSpec(
        goal_id="CHANNEL_STATE_SUPPRESSION",
        target_domain="command",
        intended_effect="make Blue reason over delayed, dropped, or stale state updates",
        preferred_attacks=("TIME_DESYNC_REPLAY",),
        preferred_tactics=("delay", "selective_drop"),
        preferred_tags=("PACKET_LOSS_HIGH", "HEARTBEAT_GAP", "PACKET_INTERVAL_ANOMALY", "STATE_UPDATE_DEPENDENT"),
        cyber_effects=("channel_delay", "drop_jitter_reorder", "state_update_starvation"),
        mission_impact=0.80,
        detectability_risk=0.70,
        policy_risk=0.22,
        learning_value=0.70,
    ),
    GoalSpec(
        goal_id="WRONG_TARGET_SELECTION",
        target_domain="mission",
        intended_effect="bias Blue toward the wrong mission area or target priority",
        preferred_attacks=("PRIORITY_POISONING",),
        preferred_tactics=("mission_priority_shift", "recommended_area_nudge", "mission_confidence_shaping"),
        preferred_tags=("MISSION_PRIORITY_CHANGED", "METADATA_PLAINTEXT", "PAYLOAD_HIDDEN", "C2_ENCRYPTED"),
        cyber_effects=("mission_belief_poisoning", "target_priority_drift", "decision_support_pollution"),
        mission_impact=0.92,
        detectability_risk=0.55,
        policy_risk=0.14,
        learning_value=0.58,
    ),
    GoalSpec(
        goal_id="TELEMETRY_TRUST_EROSION",
        target_domain="telemetry",
        intended_effect="use read-only telemetry tx/rx memory to confuse command, ack, freshness, or safety interpretation",
        preferred_attacks=("TELEMETRY_FDI",),
        preferred_tactics=("telemetry_false_data", "boundary_probe", "confidence_spoofing", "internal_external_gap_shaping"),
        preferred_tags=(
            "CROSS_CHECK_UNAVAILABLE",
            "GNSS_PRIMARY",
            "ACK_CHANNEL_VISIBLE",
            "ACK_TIMING_ANOMALY",
            "TELEMETRY_RX_COMMAND_INCONSISTENT",
            "TELEMETRY_FRESHNESS_RISK",
        ),
        cyber_effects=(
            "telemetry_command_confusion",
            "stale_state_acceptance",
            "wrong_safety_decision",
            "tx_rx_consistency_pressure",
        ),
        mission_impact=0.86,
        detectability_risk=0.66,
        policy_risk=0.15,
        learning_value=0.74,
    ),
    GoalSpec(
        goal_id="BLUE_OVERDEFENSE_ATTRITION",
        target_domain="multi_domain",
        intended_effect="induce costly Blue containment while staying inside simulated observe bounds",
        preferred_attacks=("TIME_DESYNC_REPLAY", "TELEMETRY_FDI", "PRIORITY_POISONING"),
        preferred_tactics=("selective_drop", "ack_confusion", "telemetry_false_data", "mission_priority_shift"),
        preferred_tags=("LOW_CONFIDENCE", "PACKET_LOSS_HIGH", "QUEUE_DEPTH_HIGH", "REQUEST_RATE_HIGH", "GNSS_DEGRADED"),
        cyber_effects=("defense_cost_pressure", "multi_domain_ambiguity", "availability_attrition"),
        mission_impact=0.78,
        detectability_risk=0.76,
        policy_risk=0.26,
        learning_value=0.80,
    ),
    GoalSpec(
        goal_id="DETECTION_BOUNDARY_PROBE",
        target_domain="multi_domain",
        intended_effect="learn Blue detection margins using low-amplitude simulated mutations",
        preferred_attacks=("TELEMETRY_FDI", "TIME_DESYNC_REPLAY", "PRIORITY_POISONING"),
        preferred_tactics=("boundary_probe", "metadata_poisoning", "mission_priority_shift"),
        preferred_tags=("CROSS_CHECK_UNAVAILABLE", "ACK_CHANNEL_VISIBLE", "METADATA_PLAINTEXT", "GNSS_PRIMARY"),
        cyber_effects=("detector_threshold_mapping", "stealth_margin_estimation", "safe_probe_feedback"),
        mission_impact=0.55,
        detectability_risk=0.34,
        policy_risk=0.08,
        learning_value=0.95,
    ),
)


def default_goal_stats() -> dict[str, dict[str, float | int]]:
    return {
        goal.goal_id: {
            "count": 0,
            "reward_sum": 0.0,
            "success_count": 0,
            "detected_count": 0,
            "last_round": 0,
        }
        for goal in GOAL_CATALOG
    }


def normalize_goal_stats(goal_stats: dict | None) -> dict[str, dict[str, float | int]]:
    normalized = default_goal_stats()
    for goal_id, stats in (goal_stats or {}).items():
        if goal_id not in normalized:
            continue
        for key in normalized[goal_id]:
            if key in stats:
                normalized[goal_id][key] = float(stats[key]) if key == "reward_sum" else int(stats[key])
    return normalized


def score_goal_candidates(
    *,
    tag_details: list[SituationTag] | None,
    observed_state: dict,
    previous_logs: list[dict] | None,
    goal_stats: dict | None,
    round_number: int,
) -> list[dict[str, Any]]:
    tag_confidence = {detail.tag: detail.confidence for detail in tag_details or []}
    stats = _merge_log_stats(normalize_goal_stats(goal_stats), previous_logs or [])
    total_count = max(1, sum(int(item["count"]) for item in stats.values()))
    recent_logs = previous_logs or []
    recent_counts = _recent_goal_counts(recent_logs, window=GOAL_DIVERSITY_WINDOW)
    recent_domain_counts = _recent_goal_domain_counts(recent_logs, window=GOAL_DIVERSITY_WINDOW)
    mean_count = total_count / max(1, len(GOAL_CATALOG))

    candidates = []
    for goal in GOAL_CATALOG:
        goal_stat = stats[goal.goal_id]
        count = int(goal_stat["count"])
        history_reward = _mean_reward(goal_stat)
        context_fit, matched_tags = _context_fit(goal, tag_confidence)
        world_fit = _world_fit(goal, observed_state, previous_logs or [])
        ucb_bonus = sqrt(2.0 * log(total_count + 1) / (count + 1))
        ucb_bonus = min(1.0, round(ucb_bonus, 4))
        recent_detection = _recent_detection_rate(recent_logs, goal.target_domain)
        repeat_penalty = _goal_diversity_penalty(goal, recent_logs, recent_counts, recent_domain_counts)
        underused_bonus = _goal_underused_bonus(count, mean_count)
        detection_risk = min(1.0, round(goal.detectability_risk * 0.7 + recent_detection * 0.3, 4))

        score = (
            0.24 * context_fit
            + 0.20 * world_fit
            + 0.18 * history_reward
            + 0.16 * goal.mission_impact
            + 0.14 * ucb_bonus
            + 0.08 * goal.learning_value
            + underused_bonus
            - 0.14 * detection_risk
            - 0.10 * goal.policy_risk
            - repeat_penalty
        )
        score = round(max(0.0, score), 4)
        candidates.append(
            {
                "goal_id": goal.goal_id,
                "target_domain": goal.target_domain,
                "intended_effect": goal.intended_effect,
                "preferred_attacks": list(goal.preferred_attacks),
                "preferred_tactics": list(goal.preferred_tactics),
                "cyber_effects": list(goal.cyber_effects),
                "score": score,
                "matched_tags": matched_tags,
                "score_breakdown": {
                    "context_fit": context_fit,
                    "world_fit": world_fit,
                    "history_reward": history_reward,
                    "ucb_exploration_bonus": ucb_bonus,
                    "mission_impact": goal.mission_impact,
                    "learning_value": goal.learning_value,
                    "detection_risk": detection_risk,
                    "policy_risk": goal.policy_risk,
                    "repeat_penalty": round(repeat_penalty, 4),
                    "underused_bonus": round(underused_bonus, 4),
                    "recent_goal_count": recent_counts.get(goal.goal_id, 0),
                    "recent_domain_count": recent_domain_counts.get(goal.target_domain, 0),
                    "consecutive_goal_count": _consecutive_goal_count(recent_logs, goal.goal_id),
                    "count": count,
                },
                "algorithm": "contextual_ucb_multi_criteria_goal_diversity_guard",
            }
        )

    return sorted(candidates, key=lambda item: (-item["score"], item["goal_id"]))


def select_goal_for_attack(attack_name: str, goal_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    compatible = [goal for goal in goal_candidates if attack_name in goal.get("preferred_attacks", [])]
    if compatible:
        selected = deepcopy(compatible[0])
        selected["selection_constraint"] = f"scripted_attack:{attack_name}"
        return selected
    selected = deepcopy(goal_candidates[0])
    selected["selection_constraint"] = "best_available"
    return selected


def update_goal_stats(goal_stats: dict | None, goal_id: str, score: Score, round_number: int) -> tuple[dict, dict]:
    stats = normalize_goal_stats(goal_stats)
    if goal_id not in stats:
        return stats, {"reason": "unknown_goal", "goal_id": goal_id}

    before = deepcopy(stats[goal_id])
    reward = reward_from_score(score)
    stats[goal_id]["count"] = int(stats[goal_id]["count"]) + 1
    stats[goal_id]["reward_sum"] = round(float(stats[goal_id]["reward_sum"]) + reward, 4)
    stats[goal_id]["success_count"] = int(stats[goal_id]["success_count"]) + int(bool(score.goal_success))
    stats[goal_id]["detected_count"] = int(stats[goal_id]["detected_count"]) + int(bool(score.detection_success))
    stats[goal_id]["last_round"] = round_number
    return stats, {
        "goal_id": goal_id,
        "reward": reward,
        "before": before,
        "after": deepcopy(stats[goal_id]),
    }


def reward_from_score(score: Score | dict) -> float:
    data = score.to_dict() if hasattr(score, "to_dict") else dict(score)
    explicit_goal_reward = data.get("goal_reward")
    if explicit_goal_reward is None:
        explicit_goal_reward = data.get("evidence", {}).get("goal_score", {}).get("goal_reward")
    goal_success = bool(data.get("goal_success", data.get("attack_success")))
    reward = 0.05
    if data.get("attack_success"):
        reward += 0.35
    if goal_success:
        reward += 0.20
    elif data.get("attack_success"):
        reward -= 0.18
    if not data.get("detection_success"):
        reward += 0.25
    else:
        reward -= 0.10
    if data.get("recovery_success"):
        reward -= 0.10

    winner = data.get("winner")
    winner_detail = data.get("winner_detail")
    evidence = data.get("evidence", {})
    attrition = evidence.get("attrition", {})
    attrition_cost_effective = bool(attrition.get("cost_effective", True))
    if winner == "RED_BREACH":
        reward += 0.30
    elif winner == "RED_ATTRITION":
        reward += 0.24 if attrition_cost_effective else -0.10
    elif winner == "BLUE_RECOVERY":
        reward -= 0.12
    elif winner == "BLUE":
        reward -= 0.06
    if winner_detail == "PARTIAL_BREACH":
        reward -= 0.14
    elif winner_detail in {"FALSE_POSITIVE", "NO_EFFECT"}:
        reward -= 0.08

    defense_count = len(evidence.get("defense_actions", []) or [])
    reward += min(0.16, defense_count * 0.04)
    if explicit_goal_reward is not None:
        reward = 0.65 * float(explicit_goal_reward) + 0.35 * reward
    return round(min(1.0, max(0.0, reward)), 4)


def goal_catalog_as_dicts() -> list[dict[str, Any]]:
    return [goal.to_dict() for goal in GOAL_CATALOG]


def _merge_log_stats(goal_stats: dict[str, dict[str, float | int]], previous_logs: list[dict]) -> dict:
    merged = deepcopy(goal_stats)
    for entry in previous_logs:
        goal_id = _goal_id_from_log(entry)
        if goal_id not in merged:
            continue
        score = entry.get("score")
        if not score:
            continue
        reward = reward_from_score(score)
        merged[goal_id]["count"] = int(merged[goal_id]["count"]) + 1
        merged[goal_id]["reward_sum"] = round(float(merged[goal_id]["reward_sum"]) + reward, 4)
        merged[goal_id]["success_count"] = int(merged[goal_id]["success_count"]) + int(
            bool(score.get("goal_success", score.get("attack_success")))
        )
        merged[goal_id]["detected_count"] = int(merged[goal_id]["detected_count"]) + int(bool(score.get("detection_success")))
        merged[goal_id]["last_round"] = int(entry.get("round", merged[goal_id]["last_round"]))
    return merged


def _goal_id_from_log(entry: dict) -> str | None:
    red_goal = entry.get("red_goal") or {}
    if red_goal.get("goal_id"):
        return red_goal["goal_id"]

    for item in entry.get("decision_log", []):
        goal = item.get("after", {}).get("goal") or item.get("after", {}).get("goal_plan") or {}
        if goal.get("goal_id"):
            return goal["goal_id"]

    attack_name = entry.get("attack", {}).get("name")
    if attack_name == "PRIORITY_POISONING":
        return "WRONG_TARGET_SELECTION"
    if attack_name == "TELEMETRY_FDI":
        return "TELEMETRY_TRUST_EROSION"
    if attack_name == "TIME_DESYNC_REPLAY":
        return "COMMAND_STALE_ACCEPTANCE"
    return None


def _mean_reward(goal_stat: dict[str, float | int]) -> float:
    count = int(goal_stat["count"])
    if count <= 0:
        return 0.5
    return round(float(goal_stat["reward_sum"]) / count, 4)


def _context_fit(goal: GoalSpec, tag_confidence: dict[str, float]) -> tuple[float, list[str]]:
    matched = sorted(set(goal.preferred_tags).intersection(tag_confidence))
    if not goal.preferred_tags:
        return 0.0, matched
    score = sum(tag_confidence[tag] for tag in matched) / max(1, len(goal.preferred_tags))
    return round(min(1.0, score * 1.65), 4), matched


def _world_fit(goal: GoalSpec, observed_state: dict, previous_logs: list[dict]) -> float:
    obs = observed_state.get("blue_observed", {})
    mission = observed_state.get("mission", {})
    capabilities = observed_state.get("capabilities", {})
    comms = obs.get("comms", {})
    c2 = obs.get("c2_message", {})
    telemetry = obs.get("telemetry", {})
    navigation = obs.get("navigation", {})

    if goal.goal_id == "COMMAND_STALE_ACCEPTANCE":
        score = 0.25
        score += 0.2 if c2.get("sequence_visible", True) else 0.0
        score += 0.2 if c2.get("timestamp_visible", True) else 0.0
        score += 0.18 if comms.get("encrypted") and not comms.get("payload_visible") else 0.0
        score += 0.12 if comms.get("anti_replay_window_s", 0) >= 60 else 0.0
        return round(min(1.0, score), 4)
    if goal.goal_id == "ACK_CAUSAL_CONFUSION":
        ack = c2.get("ack", {})
        score = 0.2
        score += 0.35 if comms.get("ack_visible") or ack.get("visible") else 0.0
        score += 0.2 if comms.get("ack_delay_ms", 0) >= 250 else 0.0
        score += 0.1 if comms.get("latency_ms", 0) >= 180 else 0.0
        return round(min(1.0, score), 4)
    if goal.goal_id == "CHANNEL_STATE_SUPPRESSION":
        score = 0.22
        score += min(0.25, comms.get("packet_loss", 0.0) * 2.0)
        score += 0.2 if comms.get("state_update_dependency") == "HIGH" else 0.0
        score += 0.18 if comms.get("packet_interval_jitter_ms", 0) > 150 else 0.0
        score += 0.14 if comms.get("heartbeat_gap_ms", 0) > 0 else 0.0
        return round(min(1.0, score), 4)
    if goal.goal_id == "WRONG_TARGET_SELECTION":
        priorities = obs.get("mission", {}).get("area_priority", {})
        margin = _priority_margin(priorities)
        ambiguity = 1.0 - min(1.0, margin / 0.6)
        score = 0.26 + 0.36 * ambiguity
        score += 0.12 if comms.get("route_metadata_visible") or c2.get("metadata_plaintext") else 0.0
        score += 0.1 if mission.get("trust_budget", 1.0) < 0.9 else 0.0
        return round(min(1.0, score), 4)
    if goal.goal_id == "TELEMETRY_TRUST_EROSION":
        learning_signal = telemetry_learning_signal(obs, include_world_truth=False)
        axes = learning_signal["axis_scores"]
        indirect_score = float(learning_signal["indirect_evidence"].get("indirect_effect_score", 0.0))
        active_axis_bonus = min(0.08, 0.03 * len(learning_signal.get("active_axes", [])))
        score = 0.20
        score += axes["telemetry_command_confusion"] * 0.18
        score += axes["stale_state_acceptance"] * 0.16
        score += axes["wrong_safety_decision"] * 0.16
        score += axes["tx_rx_consistency_pressure"] * 0.12
        score += indirect_score * 0.14
        score += active_axis_bonus
        score += 0.10 if capabilities.get("cross_check_telemetry") in {"DEGRADED", "UNAVAILABLE"} else 0.0
        score += 0.06 if navigation.get("gnss_fix_quality") == "NORMAL" else 0.0
        score += 0.04 if telemetry.get("battery_drain_rate", 0.0) >= 0.8 else 0.0
        return round(min(1.0, score), 4)
    if goal.goal_id == "BLUE_OVERDEFENSE_ATTRITION":
        recent_cost = _recent_defense_cost(previous_logs)
        availability_pressure = 1.0 - float(mission.get("availability", 1.0))
        score = 0.18 + min(0.34, recent_cost * 1.7) + min(0.28, availability_pressure * 1.4)
        score += 0.12 if mission.get("trust_budget", 1.0) < 0.9 else 0.0
        return round(min(1.0, score), 4)
    if goal.goal_id == "DETECTION_BOUNDARY_PROBE":
        recent_detection = _recent_detection_rate(previous_logs, "multi_domain")
        score = 0.38 + 0.32 * recent_detection
        score += 0.14 if capabilities.get("cross_check_telemetry") in {"DEGRADED", "UNAVAILABLE"} else 0.0
        return round(min(1.0, score), 4)
    return 0.5


def _priority_margin(priorities: dict[str, float]) -> float:
    if len(priorities) < 2:
        return 1.0
    values = sorted((float(value) for value in priorities.values()), reverse=True)
    return round(values[0] - values[1], 4)


def _recent_goal_counts(previous_logs: list[dict], window: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in previous_logs[-window:]:
        goal_id = _goal_id_from_log(entry)
        if goal_id:
            counts[goal_id] = counts.get(goal_id, 0) + 1
    return counts


def _recent_goal_domain_counts(previous_logs: list[dict], window: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    goal_by_id = {goal.goal_id: goal for goal in GOAL_CATALOG}
    for entry in previous_logs[-window:]:
        goal_id = _goal_id_from_log(entry)
        if not goal_id or goal_id not in goal_by_id:
            continue
        domain = goal_by_id[goal_id].target_domain
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def _consecutive_goal_count(previous_logs: list[dict], goal_id: str) -> int:
    count = 0
    for entry in reversed(previous_logs):
        if _goal_id_from_log(entry) != goal_id:
            break
        count += 1
    return count


def _goal_diversity_penalty(
    goal: GoalSpec,
    previous_logs: list[dict],
    recent_counts: dict[str, int],
    recent_domain_counts: dict[str, int],
) -> float:
    recent_goal_count = recent_counts.get(goal.goal_id, 0)
    recent_domain_count = recent_domain_counts.get(goal.target_domain, 0)
    consecutive_count = _consecutive_goal_count(previous_logs, goal.goal_id)
    penalty = (
        GOAL_REPEAT_PENALTY_PER_USE * recent_goal_count
        + GOAL_CONSECUTIVE_PENALTY_PER_USE * consecutive_count
        + GOAL_DOMAIN_REPEAT_PENALTY_PER_USE * recent_domain_count
    )
    return round(min(MAX_GOAL_DIVERSITY_PENALTY, penalty), 4)


def _goal_underused_bonus(count: int, mean_count: float) -> float:
    if count >= mean_count:
        return 0.0
    return round(min(MAX_GOAL_UNDERUSED_BONUS, (mean_count - count) * GOAL_UNDERUSED_BONUS_PER_COUNT), 4)


def _recent_detection_rate(previous_logs: list[dict], target_domain: str) -> float:
    relevant = []
    for entry in previous_logs[-5:]:
        score = entry.get("score", {})
        if target_domain != "multi_domain" and score.get("target_domain") != target_domain:
            continue
        relevant.append(bool(score.get("detection_success")))
    if not relevant:
        return 0.0
    return round(sum(relevant) / len(relevant), 4)


def _recent_defense_cost(previous_logs: list[dict]) -> float:
    costs = []
    for entry in previous_logs[-5:]:
        cost = sum(float(action.get("availability_cost", 0.0)) for action in entry.get("defense_actions", []))
        costs.append(cost)
    if not costs:
        return 0.0
    return round(sum(costs) / len(costs), 4)
