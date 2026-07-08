"""Blue feedback learner for observed-only defense policy updates."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.blue.goal_consistency import EFFECT_TAGS, effect_id_from_goal_id, effect_ids_from_tags
from dah_flawless.config import LOW_CONFIDENCE_THRESHOLD
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.scoring.telemetry_learning import (
    TELEMETRY_AXIS_DEFAULT_THRESHOLDS,
    TELEMETRY_LEARNING_AXIS_WEIGHTS,
)
from dah_flawless.schemas import DefenseAction, Score, Threat, decision

DOMAINS = ("telemetry", "mission", "command")
TELEMETRY_POLICY_AXES = tuple(TELEMETRY_LEARNING_AXIS_WEIGHTS)
MIN_DOMAIN_TRUST = 0.12
MIN_SENSITIVITY = 0.80
MAX_SENSITIVITY = 1.30
MIN_ESCALATION_THRESHOLD = 0.58
MAX_ESCALATION_THRESHOLD = 0.86
MIN_EFFECT_THRESHOLD = 0.54
MAX_EFFECT_THRESHOLD = 0.86
MIN_TELEMETRY_AXIS_THRESHOLD = 0.20
MAX_TELEMETRY_AXIS_THRESHOLD = 0.75
MEDIUM_MISSION_IMPACT_THRESHOLD = 0.45
HIGH_MISSION_IMPACT_THRESHOLD = 0.75
MISSION_IMPACT_EMA_ALPHA = 0.35
MAX_IMPACT_SENSITIVITY_BONUS = 0.04
MAX_IMPACT_THRESHOLD_BONUS = 0.02
META_GOAL_EFFECTS = {"EFFECT_DETECTION_BOUNDARY_PROBE"}
TELEMETRY_TAG_AXIS_MAP = {
    "TELEMETRY_MEMORY_COMMAND_CONFUSION": ("telemetry_command_confusion",),
    "TELEMETRY_RX_COMMAND_INCONSISTENT": ("telemetry_command_confusion",),
    "ACK_TIMING_ANOMALY": ("telemetry_command_confusion", "stale_state_acceptance"),
    "TELEMETRY_FRESHNESS_RISK": ("stale_state_acceptance",),
    "PACKET_INTERVAL_ANOMALY": ("stale_state_acceptance",),
    "HIGH_LATENCY": ("stale_state_acceptance",),
    "TELEMETRY_SAFETY_ANCHOR_RESIDUAL": ("wrong_safety_decision",),
    "BATTERY_MOTOR_INCONSISTENT": ("wrong_safety_decision", "legacy_sensor_delta"),
    "BATTERY_ENERGY_IMPOSSIBLE": ("wrong_safety_decision", "legacy_sensor_delta"),
    "TELEMETRY_INTERNAL_TX_DISAGREE": ("tx_rx_consistency_pressure",),
    "TELEMETRY_TX_RX_DISAGREE": ("tx_rx_consistency_pressure",),
    "INTERNAL_EXTERNAL_TELEMETRY_DISAGREE": ("tx_rx_consistency_pressure", "legacy_sensor_delta"),
    "TELEMETRY_CONFLICT": ("tx_rx_consistency_pressure", "legacy_sensor_delta"),
}


def default_blue_policy_state() -> dict:
    return {
        "domain_trust": {domain: 1.0 for domain in DOMAINS},
        "detection_sensitivity": {domain: 1.0 for domain in DOMAINS},
        "escalation_threshold": {domain: LOW_CONFIDENCE_THRESHOLD for domain in DOMAINS},
        "effect_sensitivity": {effect: 1.0 for effect in EFFECT_TAGS},
        "effect_threshold": {effect: LOW_CONFIDENCE_THRESHOLD for effect in EFFECT_TAGS},
        "effect_mission_impact_ema": {effect: 0.0 for effect in EFFECT_TAGS},
        "effect_mission_impact_counts": {effect: 0 for effect in EFFECT_TAGS},
        "telemetry_axis_sensitivity": {axis: 1.0 for axis in TELEMETRY_POLICY_AXES},
        "telemetry_axis_threshold": {
            axis: TELEMETRY_AXIS_DEFAULT_THRESHOLDS[axis] for axis in TELEMETRY_POLICY_AXES
        },
        "feedback_counts": {
            domain: {
                "missed_attack": 0,
                "detected": 0,
                "recovered": 0,
                "false_positive": 0,
                "over_defense": 0,
            }
            for domain in DOMAINS
        },
        "effect_feedback_counts": {
            effect: {
                "missed_effect": 0,
                "detected_effect": 0,
                "recovered_effect": 0,
                "false_positive_effect": 0,
                "over_defense_effect": 0,
            }
            for effect in EFFECT_TAGS
        },
        "telemetry_axis_feedback_counts": {
            axis: {
                "missed_axis": 0,
                "detected_axis": 0,
                "recovered_axis": 0,
                "false_positive_axis": 0,
            }
            for axis in TELEMETRY_POLICY_AXES
        },
    }


def normalize_blue_policy_state(policy_state: dict | None) -> dict:
    normalized = default_blue_policy_state()
    if not policy_state:
        return normalized

    for key in ("domain_trust", "detection_sensitivity", "escalation_threshold"):
        for domain, value in policy_state.get(key, {}).items():
            if domain in normalized[key]:
                normalized[key][domain] = float(value)

    for key in ("effect_sensitivity", "effect_threshold"):
        for effect, value in policy_state.get(key, {}).items():
            if effect in normalized[key]:
                normalized[key][effect] = float(value)

    for key in ("telemetry_axis_sensitivity", "telemetry_axis_threshold"):
        for axis, value in policy_state.get(key, {}).items():
            if axis in normalized[key]:
                normalized[key][axis] = float(value)

    for effect, value in policy_state.get("effect_mission_impact_ema", {}).items():
        if effect in normalized["effect_mission_impact_ema"]:
            normalized["effect_mission_impact_ema"][effect] = float(value)

    for effect, value in policy_state.get("effect_mission_impact_counts", {}).items():
        if effect in normalized["effect_mission_impact_counts"]:
            normalized["effect_mission_impact_counts"][effect] = int(value)

    for domain, counts in policy_state.get("feedback_counts", {}).items():
        if domain not in normalized["feedback_counts"]:
            continue
        for name, value in counts.items():
            if name in normalized["feedback_counts"][domain]:
                normalized["feedback_counts"][domain][name] = int(value)

    for effect, counts in policy_state.get("effect_feedback_counts", {}).items():
        if effect not in normalized["effect_feedback_counts"]:
            continue
        for name, value in counts.items():
            if name in normalized["effect_feedback_counts"][effect]:
                normalized["effect_feedback_counts"][effect][name] = int(value)

    for axis, counts in policy_state.get("telemetry_axis_feedback_counts", {}).items():
        if axis not in normalized["telemetry_axis_feedback_counts"]:
            continue
        for name, value in counts.items():
            if name in normalized["telemetry_axis_feedback_counts"][axis]:
                normalized["telemetry_axis_feedback_counts"][axis][name] = int(value)

    _clamp_policy(normalized)
    return normalized


def apply_blue_policy_state(state: dict, policy_state: dict | None) -> None:
    policy = normalize_blue_policy_state(policy_state)
    runtime = state.setdefault("defense_runtime", {})
    runtime["domain_trust"] = deepcopy(policy["domain_trust"])
    runtime["detection_sensitivity"] = deepcopy(policy["detection_sensitivity"])
    runtime["escalation_threshold"] = deepcopy(policy["escalation_threshold"])
    runtime["effect_sensitivity"] = deepcopy(policy["effect_sensitivity"])
    runtime["effect_threshold"] = deepcopy(policy["effect_threshold"])
    runtime["effect_mission_impact_ema"] = deepcopy(policy["effect_mission_impact_ema"])
    runtime["effect_mission_impact_counts"] = deepcopy(policy["effect_mission_impact_counts"])
    runtime["telemetry_axis_sensitivity"] = deepcopy(policy["telemetry_axis_sensitivity"])
    runtime["telemetry_axis_threshold"] = deepcopy(policy["telemetry_axis_threshold"])
    runtime["feedback_counts"] = deepcopy(policy["feedback_counts"])
    runtime["effect_feedback_counts"] = deepcopy(policy["effect_feedback_counts"])
    runtime["telemetry_axis_feedback_counts"] = deepcopy(policy["telemetry_axis_feedback_counts"])


def export_blue_policy_state(state: dict) -> dict:
    runtime = state.get("defense_runtime", {})
    return normalize_blue_policy_state(
        {
            "domain_trust": runtime.get("domain_trust", {}),
            "detection_sensitivity": runtime.get("detection_sensitivity", {}),
            "escalation_threshold": runtime.get("escalation_threshold", {}),
            "effect_sensitivity": runtime.get("effect_sensitivity", {}),
            "effect_threshold": runtime.get("effect_threshold", {}),
            "effect_mission_impact_ema": runtime.get("effect_mission_impact_ema", {}),
            "effect_mission_impact_counts": runtime.get("effect_mission_impact_counts", {}),
            "telemetry_axis_sensitivity": runtime.get("telemetry_axis_sensitivity", {}),
            "telemetry_axis_threshold": runtime.get("telemetry_axis_threshold", {}),
            "feedback_counts": runtime.get("feedback_counts", {}),
            "effect_feedback_counts": runtime.get("effect_feedback_counts", {}),
            "telemetry_axis_feedback_counts": runtime.get("telemetry_axis_feedback_counts", {}),
        }
    )


def apply_detection_policy(threats: list[Threat], policy_state: dict | None) -> tuple[list[Threat], dict]:
    policy = normalize_blue_policy_state(policy_state)
    adjusted: list[Threat] = []
    before = [threat.to_dict() for threat in threats]

    for threat in threats:
        domain_sensitivity = policy["detection_sensitivity"].get(threat.target, 1.0)
        effect_ids = effect_ids_from_tags(threat.tags)
        effect_sensitivity = max(
            [policy["effect_sensitivity"].get(effect_id, 1.0) for effect_id in effect_ids],
            default=1.0,
        )
        telemetry_axes = _telemetry_axes_from_tags(threat.tags) if threat.target == "telemetry" else []
        axis_sensitivity = max(
            [policy["telemetry_axis_sensitivity"].get(axis, 1.0) for axis in telemetry_axes],
            default=1.0,
        )
        sensitivity = domain_sensitivity * effect_sensitivity * axis_sensitivity
        confidence = round(min(0.99, max(0.01, threat.confidence * sensitivity)), 3)
        adjusted.append(
            Threat(
                target=threat.target,
                confidence=confidence,
                tags=threat.tags,
                evidence=threat.evidence,
            )
        )

    return adjusted, decision(
        "BlueFeedbackLearner",
        "threat_confidence_adjusted",
        "domain_detection_sensitivity",
        before=before,
        after={
            "threats": [threat.to_dict() for threat in adjusted],
            "detection_sensitivity": deepcopy(policy["detection_sensitivity"]),
            "escalation_threshold": deepcopy(policy["escalation_threshold"]),
            "effect_sensitivity": deepcopy(policy["effect_sensitivity"]),
            "effect_threshold": deepcopy(policy["effect_threshold"]),
            "effect_mission_impact_ema": deepcopy(policy["effect_mission_impact_ema"]),
            "telemetry_axis_sensitivity": deepcopy(policy["telemetry_axis_sensitivity"]),
            "telemetry_axis_threshold": deepcopy(policy["telemetry_axis_threshold"]),
        },
    )


def update_blue_policy(
    policy_state: dict | None,
    score: Score,
    threats: list[Threat],
    actions: list[DefenseAction],
    reviewer: PolicyUpdateReviewer | None = None,
) -> tuple[dict, dict]:
    policy = normalize_blue_policy_state(policy_state)
    before = deepcopy(policy)
    domain = score.target_domain

    if domain not in DOMAINS:
        return policy, decision(
            "BlueFeedbackLearner",
            "policy_update_skipped",
            "unsupported_target_domain",
            before=before,
            after=policy,
        )

    counts = policy["feedback_counts"][domain]
    action_cost = round(sum(action.availability_cost for action in actions), 4)
    containment_score = _containment_score(score)
    threat_seen = any(threat.target == domain for threat in threats)
    scorer_goal_effect_id = _score_effect_id(score)
    seen_effect_ids = set(_threat_effect_ids(threats))
    mission_impact_feedback = _mission_impact_feedback(score, scorer_goal_effect_id)
    telemetry_axis_feedback = _telemetry_axis_feedback(score, threats)
    goal_effect_id, training_effect_reason = _training_effect_id_for_feedback(
        scorer_goal_effect_id,
        mission_impact_feedback,
        seen_effect_ids,
    )
    effect_seen = goal_effect_id in seen_effect_ids if goal_effect_id else False
    mission_impact_feedback["training_effect_id"] = goal_effect_id
    mission_impact_feedback["training_effect_reason"] = training_effect_reason
    impact_score = mission_impact_feedback["mission_impact_score"]
    impact_sensitivity_bonus = _impact_scaled_bonus(impact_score, MAX_IMPACT_SENSITIVITY_BONUS)
    impact_threshold_bonus = _impact_scaled_bonus(impact_score, MAX_IMPACT_THRESHOLD_BONUS)
    reason = "stable_detection"
    effect_reason = None
    telemetry_axis_reason = None

    if score.attack_success and not score.detection_success:
        counts["missed_attack"] += 1
        _adjust(
            policy,
            domain,
            trust_delta=-0.08,
            sensitivity_delta=0.06 + impact_sensitivity_bonus * 0.5,
            threshold_delta=-0.03 - impact_threshold_bonus * 0.5,
        )
        reason = "missed_attack_raise_sensitivity"
    elif score.false_positive:
        counts["false_positive"] += 1
        _adjust(policy, domain, trust_delta=0.04, sensitivity_delta=-0.05, threshold_delta=0.03)
        reason = "false_positive_reduce_sensitivity"
    elif score.detection_success:
        counts["detected"] += 1
        trust_delta = 0.02 if score.recovery_success or containment_score >= 0.55 else -0.02
        sensitivity_delta = 0.01 if threat_seen else 0.0
        threshold_delta = 0.01 if containment_score >= 0.65 and not score.goal_success else 0.0
        _adjust(
            policy,
            domain,
            trust_delta=trust_delta,
            sensitivity_delta=sensitivity_delta,
            threshold_delta=threshold_delta,
        )
        reason = "detected_reinforce_domain"

    if goal_effect_id:
        _record_effect_mission_impact(policy, goal_effect_id, impact_score)
        mission_impact_feedback["effect_mission_impact_ema_after"] = policy["effect_mission_impact_ema"][
            goal_effect_id
        ]
        mission_impact_feedback["effect_mission_impact_count_after"] = policy["effect_mission_impact_counts"][
            goal_effect_id
        ]
        effect_counts = policy["effect_feedback_counts"][goal_effect_id]
        if score.goal_success and not effect_seen:
            effect_counts["missed_effect"] += 1
            _adjust_effect(
                policy,
                goal_effect_id,
                sensitivity_delta=0.08 + impact_sensitivity_bonus,
                threshold_delta=-0.04 - impact_threshold_bonus,
            )
            effect_reason = _impact_reason("missed_goal_effect_raise_sensitivity", impact_score)
        elif score.goal_success and effect_seen:
            effect_counts["detected_effect"] += 1
            effect_contained = containment_score >= 0.55
            reinforce_sensitivity = 0.01 if score.recovery_success or effect_contained else 0.03
            reinforce_threshold = 0.0 if score.recovery_success or effect_contained else -impact_threshold_bonus * 0.5
            _adjust_effect(
                policy,
                goal_effect_id,
                sensitivity_delta=reinforce_sensitivity + impact_sensitivity_bonus * 0.35,
                threshold_delta=reinforce_threshold,
            )
            effect_reason = _impact_reason("detected_goal_effect_reinforce", impact_score)
        elif (not score.goal_success) and effect_seen:
            effect_counts["false_positive_effect"] += 1
            _adjust_effect(policy, goal_effect_id, sensitivity_delta=-0.04, threshold_delta=0.03)
            effect_reason = "false_positive_goal_effect_reduce_sensitivity"

        if (score.recovery_success or containment_score >= 0.65) and effect_seen:
            effect_counts["recovered_effect"] += 1

    telemetry_axis_reason = _update_telemetry_axis_policy(
        policy=policy,
        feedback=telemetry_axis_feedback,
        score=score,
        containment_score=containment_score,
        impact_sensitivity_bonus=impact_sensitivity_bonus,
        impact_threshold_bonus=impact_threshold_bonus,
    )

    if score.recovery_success or containment_score >= 0.65:
        counts["recovered"] += 1

    if action_cost >= 0.10 or score.winner == "RED_ATTRITION":
        counts["over_defense"] += 1
        _adjust(policy, domain, trust_delta=0.02, sensitivity_delta=-0.03, threshold_delta=0.02)
        reason = f"{reason}_with_cost_control"
        for effect_id in seen_effect_ids:
            policy["effect_feedback_counts"][effect_id]["over_defense_effect"] += 1
            _adjust_effect(policy, effect_id, sensitivity_delta=-0.03, threshold_delta=0.02)
        if seen_effect_ids:
            effect_reason = f"{effect_reason or 'effect_detected'}_with_cost_control"
        for axis in _telemetry_axes_from_threats(threats):
            _adjust_telemetry_axis(policy, axis, sensitivity_delta=-0.02, threshold_delta=0.015)
            telemetry_axis_reason = f"{telemetry_axis_reason or 'axis_detected'}_with_cost_control"

    pre_review_clamp = deepcopy(policy)
    _clamp_policy(policy)
    saturation_guard = _saturation_guard_report(pre_review_clamp, policy)
    policy_update_reviewer = reviewer or build_policy_update_reviewer()
    reviewed_tunables, review_log = policy_update_reviewer.review_update(
        agent="BlueFeedbackLearner",
        update_name="domain_policy",
        before=_policy_tunables(before),
        proposed=_policy_tunables(policy),
        context={
            "target_domain": domain,
            "winner": score.winner,
            "attack_success": score.attack_success,
            "detection_success": score.detection_success,
            "false_positive": score.false_positive,
            "recovery_success": score.recovery_success,
            "containment_score": containment_score,
            "goal_id": score.goal_id,
            "goal_success": score.goal_success,
            "scorer_goal_effect_id": scorer_goal_effect_id,
            "goal_effect_id": goal_effect_id,
            "goal_effect_seen": effect_seen,
            "seen_effect_ids": sorted(seen_effect_ids),
            "mission_impact_feedback": mission_impact_feedback,
            "telemetry_axis_feedback": telemetry_axis_feedback,
            "mission_impact_score": impact_score,
            "over_defense": action_cost >= 0.10,
            "action_cost": action_cost,
        },
    )
    _apply_tunables(policy, reviewed_tunables)
    pre_final_clamp = deepcopy(policy)
    _clamp_policy(policy)
    saturation_guard["events"].extend(_saturation_guard_report(pre_final_clamp, policy)["events"])
    return policy, decision(
        "BlueFeedbackLearner",
        "policy_updated",
        reason,
        before=before,
        after={
            "policy_state": deepcopy(policy),
            "action_cost": action_cost,
            "effect_update_reason": effect_reason,
            "telemetry_axis_update_reason": telemetry_axis_reason,
            "telemetry_axis_feedback": telemetry_axis_feedback,
            "mission_impact_feedback": mission_impact_feedback,
            "saturation_guard": saturation_guard,
            "score": score.to_dict(),
            "policy_update_review": review_log,
        },
    )


def freeze_blue_policy(policy_state: dict | None) -> tuple[dict, dict]:
    policy = normalize_blue_policy_state(policy_state)
    return policy, decision(
        "BlueFeedbackLearner",
        "policy_update_skipped",
        "blue_policy_frozen",
        before=deepcopy(policy),
        after=deepcopy(policy),
    )


def _containment_score(score: Score) -> float:
    containment = (score.evidence or {}).get("containment", {})
    return float(getattr(score, "containment_score", containment.get("containment_score", 0.0)) or 0.0)


def _adjust(
    policy: dict,
    domain: str,
    *,
    trust_delta: float,
    sensitivity_delta: float,
    threshold_delta: float,
) -> None:
    policy["domain_trust"][domain] += trust_delta
    policy["detection_sensitivity"][domain] += sensitivity_delta
    policy["escalation_threshold"][domain] += threshold_delta


def _adjust_effect(
    policy: dict,
    effect_id: str,
    *,
    sensitivity_delta: float,
    threshold_delta: float,
) -> None:
    policy["effect_sensitivity"][effect_id] += sensitivity_delta
    policy["effect_threshold"][effect_id] += threshold_delta


def _adjust_telemetry_axis(
    policy: dict,
    axis: str,
    *,
    sensitivity_delta: float,
    threshold_delta: float,
) -> None:
    if axis not in policy["telemetry_axis_sensitivity"]:
        return
    policy["telemetry_axis_sensitivity"][axis] += sensitivity_delta
    policy["telemetry_axis_threshold"][axis] += threshold_delta


def _telemetry_axis_feedback(score: Score, threats: list[Threat]) -> dict:
    if score.target_domain != "telemetry":
        return {"skipped": True, "reason": "non_telemetry_domain"}

    signal = _telemetry_learning_signal_from_score(score)
    axis_scores = signal.get("axis_scores", {}) if signal else {}
    dominant_axis = signal.get("dominant_axis") if signal else None
    if dominant_axis not in TELEMETRY_POLICY_AXES:
        return {"skipped": True, "reason": "no_telemetry_learning_signal"}

    axes_seen = _telemetry_axes_from_threats(threats)
    axis_score = round(float(axis_scores.get(dominant_axis, 0.0)), 4)
    return {
        "skipped": False,
        "dominant_axis": dominant_axis,
        "dominant_axis_score": axis_score,
        "axis_scores": {axis: round(float(axis_scores.get(axis, 0.0)), 4) for axis in TELEMETRY_POLICY_AXES},
        "active_axes": list(signal.get("active_axes", [])),
        "axis_entropy": signal.get("axis_entropy", 0.0),
        "blue_policy_learning_value": signal.get("blue_policy_learning_value", 0.0),
        "axes_seen_in_threats": axes_seen,
        "dominant_axis_seen": dominant_axis in axes_seen,
    }


def _update_telemetry_axis_policy(
    *,
    policy: dict,
    feedback: dict,
    score: Score,
    containment_score: float,
    impact_sensitivity_bonus: float,
    impact_threshold_bonus: float,
) -> str | None:
    if feedback.get("skipped"):
        return None

    axis = feedback["dominant_axis"]
    axis_seen = bool(feedback["dominant_axis_seen"])
    counts = policy["telemetry_axis_feedback_counts"][axis]

    if score.goal_success and not axis_seen:
        counts["missed_axis"] += 1
        _adjust_telemetry_axis(
            policy,
            axis,
            sensitivity_delta=0.05 + impact_sensitivity_bonus * 0.50,
            threshold_delta=-0.03 - impact_threshold_bonus * 0.50,
        )
        return "missed_telemetry_axis_raise_sensitivity"

    if score.goal_success and axis_seen:
        counts["detected_axis"] += 1
        _adjust_telemetry_axis(
            policy,
            axis,
            sensitivity_delta=0.015 + impact_sensitivity_bonus * 0.25,
            threshold_delta=-impact_threshold_bonus * 0.25,
        )
        if score.recovery_success or containment_score >= 0.65:
            counts["recovered_axis"] += 1
        return "detected_telemetry_axis_reinforce"

    if score.false_positive and axis_seen:
        counts["false_positive_axis"] += 1
        _adjust_telemetry_axis(policy, axis, sensitivity_delta=-0.04, threshold_delta=0.025)
        return "false_positive_telemetry_axis_reduce_sensitivity"

    return None


def _record_effect_mission_impact(policy: dict, effect_id: str, impact_score: float) -> None:
    if effect_id not in policy["effect_mission_impact_ema"]:
        return
    current_count = int(policy["effect_mission_impact_counts"].get(effect_id, 0))
    current_ema = float(policy["effect_mission_impact_ema"].get(effect_id, 0.0))
    if current_count <= 0:
        next_ema = impact_score
    else:
        next_ema = current_ema * (1.0 - MISSION_IMPACT_EMA_ALPHA) + impact_score * MISSION_IMPACT_EMA_ALPHA
    policy["effect_mission_impact_counts"][effect_id] = current_count + 1
    policy["effect_mission_impact_ema"][effect_id] = round(min(1.0, max(0.0, next_ema)), 4)


def _mission_impact_feedback(score: Score, goal_effect_id: str | None) -> dict:
    mission_impact = (score.evidence or {}).get("mission_impact", {})
    impact_score = round(min(1.0, max(0.0, float(mission_impact.get("mission_impact_score", 0.0)))), 4)
    primary_component = mission_impact.get("primary_component")
    target_component = mission_impact.get("target_component")
    component_effect_id = _effect_id_from_mission_component(target_component) or _effect_id_from_mission_component(
        primary_component
    )
    return {
        "mission_impact_score": impact_score,
        "mission_impact_level": mission_impact.get("level") or _impact_level(impact_score),
        "primary_component": primary_component,
        "target_component": target_component,
        "goal_effect_id": goal_effect_id,
        "component_effect_id": component_effect_id,
        "training_effect_id": goal_effect_id or component_effect_id,
        "impact_sensitive_update": impact_score >= MEDIUM_MISSION_IMPACT_THRESHOLD,
    }


def _training_effect_id_for_feedback(
    goal_effect_id: str | None,
    mission_impact_feedback: dict,
    seen_effect_ids: set[str],
) -> tuple[str | None, str]:
    if goal_effect_id not in META_GOAL_EFFECTS:
        return goal_effect_id, "direct_goal_effect"

    component_effect_id = mission_impact_feedback.get("component_effect_id")
    if component_effect_id in EFFECT_TAGS:
        return component_effect_id, "meta_goal_remapped_to_mission_component"

    non_meta_seen = sorted(effect_id for effect_id in seen_effect_ids if effect_id not in META_GOAL_EFFECTS)
    if non_meta_seen:
        return non_meta_seen[0], "meta_goal_remapped_to_seen_effect"

    return None, "meta_goal_effect_feedback_skipped"


def _effect_id_from_mission_component(component: str | None) -> str | None:
    if component == "telemetry_safety":
        return "EFFECT_TELEMETRY_TRUST_EROSION"
    if component == "mission_belief":
        return "EFFECT_WRONG_TARGET_SELECTION"
    if component == "command_freshness":
        return "EFFECT_COMMAND_STALE_ACCEPTANCE"
    return None


def _impact_scaled_bonus(impact_score: float, max_bonus: float) -> float:
    if impact_score < MEDIUM_MISSION_IMPACT_THRESHOLD:
        return 0.0
    scale = (impact_score - MEDIUM_MISSION_IMPACT_THRESHOLD) / (1.0 - MEDIUM_MISSION_IMPACT_THRESHOLD)
    return round(max_bonus * min(1.0, max(0.0, scale)), 4)


def _impact_reason(base_reason: str, impact_score: float) -> str:
    if impact_score >= HIGH_MISSION_IMPACT_THRESHOLD:
        return f"{base_reason}_high_mission_impact"
    if impact_score >= MEDIUM_MISSION_IMPACT_THRESHOLD:
        return f"{base_reason}_medium_mission_impact"
    return base_reason


def _impact_level(impact_score: float) -> str:
    if impact_score >= HIGH_MISSION_IMPACT_THRESHOLD:
        return "HIGH"
    if impact_score >= MEDIUM_MISSION_IMPACT_THRESHOLD:
        return "MEDIUM"
    if impact_score > 0.0:
        return "LOW"
    return "MINIMAL"


def _policy_tunables(policy: dict) -> dict:
    return {
        "domain_trust": deepcopy(policy["domain_trust"]),
        "detection_sensitivity": deepcopy(policy["detection_sensitivity"]),
        "escalation_threshold": deepcopy(policy["escalation_threshold"]),
        "effect_sensitivity": deepcopy(policy["effect_sensitivity"]),
        "effect_threshold": deepcopy(policy["effect_threshold"]),
        "telemetry_axis_sensitivity": deepcopy(policy["telemetry_axis_sensitivity"]),
        "telemetry_axis_threshold": deepcopy(policy["telemetry_axis_threshold"]),
    }


def _apply_tunables(policy: dict, tunables: dict) -> None:
    for key in ("domain_trust", "detection_sensitivity", "escalation_threshold"):
        for domain in DOMAINS:
            if domain in tunables.get(key, {}):
                policy[key][domain] = tunables[key][domain]
    for key in ("effect_sensitivity", "effect_threshold"):
        for effect_id in EFFECT_TAGS:
            if effect_id in tunables.get(key, {}):
                policy[key][effect_id] = tunables[key][effect_id]
    for key in ("telemetry_axis_sensitivity", "telemetry_axis_threshold"):
        for axis in TELEMETRY_POLICY_AXES:
            if axis in tunables.get(key, {}):
                policy[key][axis] = tunables[key][axis]


def _clamp_policy(policy: dict) -> None:
    for domain in DOMAINS:
        policy["domain_trust"][domain] = round(min(1.0, max(MIN_DOMAIN_TRUST, policy["domain_trust"][domain])), 4)
        policy["detection_sensitivity"][domain] = round(
            min(MAX_SENSITIVITY, max(MIN_SENSITIVITY, policy["detection_sensitivity"][domain])), 4
        )
        policy["escalation_threshold"][domain] = round(
            min(MAX_ESCALATION_THRESHOLD, max(MIN_ESCALATION_THRESHOLD, policy["escalation_threshold"][domain])), 4
        )
    for effect_id in EFFECT_TAGS:
        policy["effect_sensitivity"][effect_id] = round(
            min(MAX_SENSITIVITY, max(MIN_SENSITIVITY, policy["effect_sensitivity"][effect_id])), 4
        )
        policy["effect_threshold"][effect_id] = round(
            min(MAX_EFFECT_THRESHOLD, max(MIN_EFFECT_THRESHOLD, policy["effect_threshold"][effect_id])), 4
        )
        policy["effect_mission_impact_ema"][effect_id] = round(
            min(1.0, max(0.0, policy["effect_mission_impact_ema"][effect_id])), 4
        )
        policy["effect_mission_impact_counts"][effect_id] = max(
            0,
            int(policy["effect_mission_impact_counts"][effect_id]),
        )
    for axis in TELEMETRY_POLICY_AXES:
        policy["telemetry_axis_sensitivity"][axis] = round(
            min(MAX_SENSITIVITY, max(MIN_SENSITIVITY, policy["telemetry_axis_sensitivity"][axis])), 4
        )
        policy["telemetry_axis_threshold"][axis] = round(
            min(
                MAX_TELEMETRY_AXIS_THRESHOLD,
                max(MIN_TELEMETRY_AXIS_THRESHOLD, policy["telemetry_axis_threshold"][axis]),
            ),
            4,
        )
        for count_name in policy["telemetry_axis_feedback_counts"][axis]:
            policy["telemetry_axis_feedback_counts"][axis][count_name] = max(
                0,
                int(policy["telemetry_axis_feedback_counts"][axis][count_name]),
            )


def _saturation_guard_report(before: dict, after: dict) -> dict:
    events = []
    for domain in DOMAINS:
        before_value = float(before["domain_trust"][domain])
        after_value = float(after["domain_trust"][domain])
        if before_value < MIN_DOMAIN_TRUST and after_value == MIN_DOMAIN_TRUST:
            events.append(
                {
                    "field": f"domain_trust.{domain}",
                    "before": round(before_value, 4),
                    "after": after_value,
                    "reason": "domain_trust_floor",
                }
            )
    return {
        "min_domain_trust": MIN_DOMAIN_TRUST,
        "events": events,
    }


def _score_effect_id(score: Score) -> str | None:
    effect_id = effect_id_from_goal_id(score.goal_id)
    if effect_id:
        return effect_id
    goal_score = score.evidence.get("goal_score", {}) if score.evidence else {}
    return effect_id_from_goal_id(goal_score.get("goal_id"))


def _telemetry_learning_signal_from_score(score: Score) -> dict:
    evidence = score.evidence or {}
    goal_score = evidence.get("goal_score", {})
    goal_evidence = goal_score.get("evidence", {}) if isinstance(goal_score, dict) else {}
    signal = goal_evidence.get("telemetry_learning_signal")
    if isinstance(signal, dict):
        return signal

    mission_impact = evidence.get("mission_impact", {})
    telemetry_component = (mission_impact.get("components") or {}).get("telemetry_safety", {})
    signal = telemetry_component.get("telemetry_learning_signal")
    return signal if isinstance(signal, dict) else {}


def _threat_effect_ids(threats: list[Threat]) -> list[str]:
    effect_ids: list[str] = []
    for threat in threats:
        effect_ids.extend(effect_ids_from_tags(threat.tags))
    return sorted(set(effect_ids))


def _telemetry_axes_from_threats(threats: list[Threat]) -> list[str]:
    axes: set[str] = set()
    for threat in threats:
        if threat.target != "telemetry":
            continue
        axes.update(_telemetry_axes_from_tags(threat.tags))
    return sorted(axes)


def _telemetry_axes_from_tags(tags: tuple[str, ...] | list[str]) -> list[str]:
    axes: set[str] = set()
    for tag in tags:
        axes.update(TELEMETRY_TAG_AXIS_MAP.get(tag, ()))
    return sorted(axis for axis in axes if axis in TELEMETRY_POLICY_AXES)
