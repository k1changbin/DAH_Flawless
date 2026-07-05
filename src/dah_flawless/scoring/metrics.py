"""Aggregate metrics for simulation summaries."""

from __future__ import annotations

from collections import Counter
from math import log2


def summarize_logs(logs: list[dict]) -> dict:
    winners = Counter(entry["score"]["winner"] for entry in logs)
    attacks = Counter(entry["attack"]["name"] for entry in logs)
    tactics = Counter((entry.get("red_tactic") or {}).get("strategy") or "UNKNOWN" for entry in logs)
    goals = Counter((entry.get("red_goal") or {}).get("goal_id") or entry["score"].get("goal_id") for entry in logs)
    detections = sum(1 for entry in logs if entry["score"]["detection_success"])
    attack_successes = sum(1 for entry in logs if entry["score"]["attack_success"])
    goal_successes = sum(1 for entry in logs if entry["score"].get("goal_success"))
    goal_rewards = [float(entry["score"].get("goal_reward", 0.0)) for entry in logs]
    availability = [entry["score"]["availability"] for entry in logs]
    causal_scores = [
        float(entry.get("causal_consistency", {}).get("consistency_score", 0.0))
        for entry in logs
        if "causal_consistency" in entry
    ]
    causal_failures = sum(1 for entry in logs if entry.get("causal_consistency", {}).get("status") == "FAIL")
    causal_warnings = sum(1 for entry in logs if entry.get("causal_consistency", {}).get("status") == "WARN")

    return {
        "rounds": len(logs),
        "winners": dict(sorted(winners.items())),
        "attacks": dict(sorted(attacks.items())),
        "tactics": dict(sorted(tactics.items())),
        "attack_entropy": _entropy(attacks),
        "tactic_entropy": _entropy(tactics),
        "goals": dict(sorted((goal or "UNKNOWN", count) for goal, count in goals.items())),
        "detection_rate": round(detections / len(logs), 4) if logs else 0.0,
        "attack_success_rate": round(attack_successes / len(logs), 4) if logs else 0.0,
        "goal_success_rate": round(goal_successes / len(logs), 4) if logs else 0.0,
        "avg_goal_reward": round(sum(goal_rewards) / len(goal_rewards), 4) if goal_rewards else 0.0,
        "avg_causal_consistency": round(sum(causal_scores) / len(causal_scores), 4) if causal_scores else 0.0,
        "causal_warning_count": causal_warnings,
        "causal_failure_count": causal_failures,
        "final_availability": availability[-1] if availability else None,
        "min_availability": min(availability) if availability else None,
    }


def _entropy(counter: Counter) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return round(-sum((count / total) * log2(count / total) for count in counter.values()), 4)
