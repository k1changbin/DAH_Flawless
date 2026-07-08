"""Aggregate metrics for simulation summaries."""

from __future__ import annotations

from collections import Counter
from math import log2


def summarize_logs(logs: list[dict]) -> dict:
    winners = Counter(entry["score"]["winner"] for entry in logs)
    winner_sides = Counter(_winner_side(entry["score"]) for entry in logs)
    winner_details = Counter(_winner_detail(entry["score"]) for entry in logs)
    attacks = Counter(entry["attack"]["name"] for entry in logs)
    tactics = Counter((entry.get("red_tactic") or {}).get("strategy") or "UNKNOWN" for entry in logs)
    goals = Counter((entry.get("red_goal") or {}).get("goal_id") or entry["score"].get("goal_id") for entry in logs)
    detections = sum(1 for entry in logs if entry["score"]["detection_success"])
    attack_successes = sum(1 for entry in logs if entry["score"]["attack_success"])
    goal_successes = sum(1 for entry in logs if entry["score"].get("goal_success"))
    goal_rewards = [float(entry["score"].get("goal_reward", 0.0)) for entry in logs]
    mission_impacts = [
        float(entry["score"].get("evidence", {}).get("mission_impact", {}).get("mission_impact_score", 0.0))
        for entry in logs
    ]
    high_mission_impacts = sum(1 for impact in mission_impacts if impact >= 0.75)
    availability = [entry["score"]["availability"] for entry in logs]
    causal_scores = [
        float(entry.get("causal_consistency", {}).get("consistency_score", 0.0))
        for entry in logs
        if "causal_consistency" in entry
    ]
    causal_failures = sum(1 for entry in logs if entry.get("causal_consistency", {}).get("status") == "FAIL")
    causal_warnings = sum(1 for entry in logs if entry.get("causal_consistency", {}).get("status") == "WARN")
    attrition_records = [
        entry["score"].get("evidence", {}).get("attrition", {})
        for entry in logs
        if entry["score"].get("winner") == "RED_ATTRITION"
    ]
    attrition_net_costs = [float(item.get("net_defense_cost", 0.0)) for item in attrition_records]
    attrition_ratios = [float(item.get("defense_to_attack_cost_ratio", 0.0)) for item in attrition_records]
    zta_policies = [entry.get("zta_policy", {}) for entry in logs if entry.get("zta_policy")]
    zta_correctness = [
        float(policy.get("policy_decision_correctness", 0.0))
        for policy in zta_policies
        if policy.get("policy_decision_correctness") is not None
    ]
    zta_decision_counts = Counter()
    for policy in zta_policies:
        zta_decision_counts.update(policy.get("decision_counts", {}))

    return {
        "rounds": len(logs),
        "winners": dict(sorted(winners.items())),
        "winner_sides": dict(sorted(winner_sides.items())),
        "winner_details": dict(sorted(winner_details.items())),
        "attacks": dict(sorted(attacks.items())),
        "tactics": dict(sorted(tactics.items())),
        "attack_entropy": _entropy(attacks),
        "tactic_entropy": _entropy(tactics),
        "goals": dict(sorted((goal or "UNKNOWN", count) for goal, count in goals.items())),
        "detection_rate": round(detections / len(logs), 4) if logs else 0.0,
        "attack_success_rate": round(attack_successes / len(logs), 4) if logs else 0.0,
        "goal_success_rate": round(goal_successes / len(logs), 4) if logs else 0.0,
        "avg_goal_reward": round(sum(goal_rewards) / len(goal_rewards), 4) if goal_rewards else 0.0,
        "avg_mission_impact_score": round(sum(mission_impacts) / len(mission_impacts), 4) if mission_impacts else 0.0,
        "high_mission_impact_count": high_mission_impacts,
        "avg_causal_consistency": round(sum(causal_scores) / len(causal_scores), 4) if causal_scores else 0.0,
        "causal_warning_count": causal_warnings,
        "causal_failure_count": causal_failures,
        "final_availability": availability[-1] if availability else None,
        "min_availability": min(availability) if availability else None,
        "avg_attrition_net_defense_cost": round(sum(attrition_net_costs) / len(attrition_net_costs), 4)
        if attrition_net_costs
        else 0.0,
        "avg_attrition_defense_to_attack_ratio": round(sum(attrition_ratios) / len(attrition_ratios), 4)
        if attrition_ratios
        else 0.0,
        "avg_policy_decision_correctness": round(sum(zta_correctness) / len(zta_correctness), 4)
        if zta_correctness
        else 0.0,
        "zta_decision_counts": dict(sorted(zta_decision_counts.items())),
    }


def _entropy(counter: Counter) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return round(-sum((count / total) * log2(count / total) for count in counter.values()), 4)


def _winner_side(score: dict) -> str:
    side = score.get("winner_side")
    if side:
        return str(side)
    winner = score.get("winner", "")
    if winner.startswith("RED"):
        return "RED"
    if winner.startswith("BLUE"):
        return "BLUE"
    if winner == "DRAW":
        return "DRAW"
    return "UNKNOWN"


def _winner_detail(score: dict) -> str:
    detail = score.get("winner_detail")
    if detail:
        return str(detail)
    return {
        "RED_BREACH": "BREACH",
        "RED_ATTRITION": "ATTRITION",
        "BLUE_RECOVERY": "RECOVERY",
        "BLUE": "DETECTION",
        "DRAW": "NO_DECISION",
    }.get(score.get("winner"), "UNKNOWN")
