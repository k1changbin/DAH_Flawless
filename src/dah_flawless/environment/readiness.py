"""Blue readiness gate for staged Red/Blue co-training."""

from __future__ import annotations

from dah_flawless.config import (
    DEFAULT_BLUE_READINESS_MIN_SAMPLES,
    DEFAULT_BLUE_READINESS_THRESHOLD,
    DEFAULT_BLUE_READINESS_WINDOW,
)


def assess_blue_readiness(
    logs: list[dict],
    *,
    threshold: float = DEFAULT_BLUE_READINESS_THRESHOLD,
    min_samples: int = DEFAULT_BLUE_READINESS_MIN_SAMPLES,
    window: int = DEFAULT_BLUE_READINESS_WINDOW,
) -> dict:
    """Return whether Blue is ready for Red policy updates.

    Readiness is intentionally based on recent defense outcomes rather than raw
    Red/Blue win balance. Blue is considered successful when it detects or
    recovers a round without allowing a decisive Red result.
    """

    recent = list(logs[-max(1, window) :])
    readiness_scores = [blue_defense_score(entry) for entry in recent]
    successes = sum(1 for score in readiness_scores if score >= threshold)
    samples = len(recent)
    rate = round(sum(readiness_scores) / samples, 4) if samples else 0.0
    ready = samples >= min_samples and rate >= threshold
    if samples < min_samples:
        reason = "insufficient_blue_training_samples"
    elif rate < threshold:
        reason = "blue_defense_success_below_threshold"
    else:
        reason = "blue_ready_for_red_updates"
    return {
        "ready": ready,
        "reason": reason,
        "success_rate": rate,
        "successes": successes,
        "samples": samples,
        "threshold": threshold,
        "min_samples": min_samples,
        "window": window,
        "algorithm": "rolling_blue_containment_readiness_gate_v2",
    }


def blue_defense_success(entry: dict) -> bool:
    return blue_defense_score(entry) >= DEFAULT_BLUE_READINESS_THRESHOLD


def blue_defense_score(entry: dict) -> float:
    """Return a continuous Blue readiness score in the 0..1 range."""

    score = entry.get("score", {})
    winner = score.get("winner")
    winner_side = score.get("winner_side")
    if winner_side == "BLUE" or winner in {"BLUE", "BLUE_RECOVERY"}:
        return 1.0
    containment_score = _containment_score(score)
    if winner_side == "RED" or str(winner or "").startswith("RED"):
        if winner == "RED_ATTRITION":
            return round(min(0.38, containment_score), 4)
        return round(min(0.16, containment_score), 4)
    detection_success = bool(score.get("detection_success", False))
    recovery_success = bool(score.get("recovery_success", False))
    goal_success = bool(score.get("goal_success", score.get("attack_success", False)))
    attack_success = bool(score.get("attack_success", False))
    false_positive = bool(score.get("false_positive", False))
    availability = float(score.get("availability", 0.0) or 0.0)
    availability_component = min(1.0, availability / 0.50)

    if recovery_success:
        return round(max(0.65, containment_score), 4)
    if detection_success:
        base = 0.24 + 0.46 * containment_score + 0.20 * availability_component
        if goal_success:
            base -= 0.12
        return round(min(0.82, max(0.0, base)), 4)
    if false_positive:
        return 0.18
    if not attack_success:
        return round(0.45 + 0.15 * availability_component, 4)
    return round(min(0.25, containment_score), 4)


def _containment_score(score: dict) -> float:
    containment = score.get("evidence", {}).get("containment", {})
    return float(score.get("containment_score", containment.get("containment_score", 0.0)) or 0.0)
