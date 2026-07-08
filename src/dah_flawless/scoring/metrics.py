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
    containment_scores = [
        float(
            entry["score"].get(
                "containment_score",
                entry["score"].get("evidence", {}).get("containment", {}).get("containment_score", 0.0),
            )
        )
        for entry in logs
    ]
    contained_rounds = sum(
        1 for entry in logs if entry["score"].get("evidence", {}).get("containment", {}).get("contained")
    )
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
    recovery_records = [entry.get("availability_recovery", {}) for entry in logs if entry.get("availability_recovery")]
    episode_budget_resets = [
        item for item in recovery_records if item.get("algorithm") == "round_episode_budget_reset_v1"
    ]
    availability_recoveries = [
        float(item.get("availability_recovery_applied", 0.0)) for item in recovery_records
    ]
    trust_recoveries = [float(item.get("trust_recovery_applied", 0.0)) for item in recovery_records]
    policy_gates = [entry.get("observe_policy_gate", {}) for entry in logs if entry.get("observe_policy_gate")]
    policy_min_trust = [float(gate.get("min_trust_score", 1.0)) for gate in policy_gates]
    policy_restricted_rounds = sum(1 for gate in policy_gates if gate.get("restricted_domains"))
    policy_domain_decisions = Counter(
        f"{domain}:{decision.get('decision')}"
        for gate in policy_gates
        for domain, decision in (gate.get("by_domain") or {}).items()
    )
    telemetry_learning_signals = [_telemetry_learning_signal(entry) for entry in logs]
    telemetry_learning_signals = [signal for signal in telemetry_learning_signals if signal]
    telemetry_dominant_axes = Counter(
        signal.get("dominant_axis", "UNKNOWN") for signal in telemetry_learning_signals
    )
    telemetry_active_axes = Counter(
        axis for signal in telemetry_learning_signals for axis in signal.get("active_axes", [])
    )
    telemetry_weighted_scores = [
        float(signal.get("weighted_effect_score", 0.0)) for signal in telemetry_learning_signals
    ]
    telemetry_axis_scores = _average_telemetry_axis_scores(telemetry_learning_signals)
    telemetry_dominant_axis_entropy = _entropy(telemetry_dominant_axes)
    telemetry_active_axis_entropy = _entropy(telemetry_active_axes)

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
        "avg_containment_score": round(sum(containment_scores) / len(containment_scores), 4)
        if containment_scores
        else 0.0,
        "contained_round_count": contained_rounds,
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
        "avg_availability_recovery": round(sum(availability_recoveries) / len(availability_recoveries), 4)
        if availability_recoveries
        else 0.0,
        "total_availability_recovery": round(sum(availability_recoveries), 4),
        "episode_budget_reset_count": len(episode_budget_resets),
        "avg_trust_recovery": round(sum(trust_recoveries) / len(trust_recoveries), 4) if trust_recoveries else 0.0,
        "maintenance_recovery_count": sum(1 for item in recovery_records if item.get("maintenance_cycle")),
        "avg_observe_policy_min_trust": round(sum(policy_min_trust) / len(policy_min_trust), 4)
        if policy_min_trust
        else None,
        "observe_policy_restricted_round_count": policy_restricted_rounds,
        "observe_policy_domain_decisions": dict(sorted(policy_domain_decisions.items())),
        "avg_telemetry_learning_signal": round(sum(telemetry_weighted_scores) / len(telemetry_weighted_scores), 4)
        if telemetry_weighted_scores
        else 0.0,
        "telemetry_learning_axis_entropy": telemetry_active_axis_entropy,
        "telemetry_dominant_axis_entropy": telemetry_dominant_axis_entropy,
        "telemetry_policy_diversity_contribution": {
            "telemetry_round_count": len(telemetry_learning_signals),
            "dominant_axis_counts": dict(sorted(telemetry_dominant_axes.items())),
            "active_axis_counts": dict(sorted(telemetry_active_axes.items())),
            "avg_axis_scores": telemetry_axis_scores,
            "axis_entropy": telemetry_active_axis_entropy,
            "dominant_axis_entropy": telemetry_dominant_axis_entropy,
            "active_axis_entropy": telemetry_active_axis_entropy,
            "attack_entropy": _entropy(attacks),
            "tactic_entropy": _entropy(tactics),
            "interpretation": "higher axis entropy means telemetry tx/rx/internal/command/freshness changes trained more varied Red and Blue policy responses",
        },
    }


def _entropy(counter: Counter) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    entropy = round(-sum((count / total) * log2(count / total) for count in counter.values()), 4)
    return 0.0 if abs(entropy) < 0.0001 else entropy


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


def _telemetry_learning_signal(entry: dict) -> dict:
    score = entry.get("score", {})
    goal_score = score.get("evidence", {}).get("goal_score", {})
    goal_evidence = goal_score.get("evidence", {}) if isinstance(goal_score, dict) else {}
    signal = goal_evidence.get("telemetry_learning_signal")
    return signal if isinstance(signal, dict) else {}


def _average_telemetry_axis_scores(signals: list[dict]) -> dict:
    if not signals:
        return {}
    axes = sorted({axis for signal in signals for axis in signal.get("axis_scores", {})})
    return {
        axis: round(
            sum(float(signal.get("axis_scores", {}).get(axis, 0.0)) for signal in signals) / len(signals),
            4,
        )
        for axis in axes
    }
