"""Aggregate metrics for simulation summaries."""

from __future__ import annotations

from collections import Counter


def summarize_logs(logs: list[dict]) -> dict:
    winners = Counter(entry["score"]["winner"] for entry in logs)
    attacks = Counter(entry["attack"]["name"] for entry in logs)
    detections = sum(1 for entry in logs if entry["score"]["detection_success"])
    attack_successes = sum(1 for entry in logs if entry["score"]["attack_success"])
    availability = [entry["score"]["availability"] for entry in logs]

    return {
        "rounds": len(logs),
        "winners": dict(sorted(winners.items())),
        "attacks": dict(sorted(attacks.items())),
        "detection_rate": round(detections / len(logs), 4) if logs else 0.0,
        "attack_success_rate": round(attack_successes / len(logs), 4) if logs else 0.0,
        "final_availability": availability[-1] if availability else None,
        "min_availability": min(availability) if availability else None,
    }
