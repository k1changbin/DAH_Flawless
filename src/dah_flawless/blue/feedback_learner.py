"""Blue feedback learner for observed-only defense policy updates."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.blue.goal_consistency import EFFECT_TAGS, effect_id_from_goal_id, effect_ids_from_tags
from dah_flawless.config import LOW_CONFIDENCE_THRESHOLD
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.schemas import DefenseAction, Score, Threat, decision

DOMAINS = ("telemetry", "mission", "command")
MIN_DOMAIN_TRUST = 0.12
MIN_SENSITIVITY = 0.80
MAX_SENSITIVITY = 1.30
MIN_ESCALATION_THRESHOLD = 0.58
MAX_ESCALATION_THRESHOLD = 0.86
MIN_EFFECT_THRESHOLD = 0.54
MAX_EFFECT_THRESHOLD = 0.86


def default_blue_policy_state() -> dict:
    return {
        "domain_trust": {domain: 1.0 for domain in DOMAINS},
        "detection_sensitivity": {domain: 1.0 for domain in DOMAINS},
        "escalation_threshold": {domain: LOW_CONFIDENCE_THRESHOLD for domain in DOMAINS},
        "effect_sensitivity": {effect: 1.0 for effect in EFFECT_TAGS},
        "effect_threshold": {effect: LOW_CONFIDENCE_THRESHOLD for effect in EFFECT_TAGS},
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
    runtime["feedback_counts"] = deepcopy(policy["feedback_counts"])
    runtime["effect_feedback_counts"] = deepcopy(policy["effect_feedback_counts"])


def export_blue_policy_state(state: dict) -> dict:
    runtime = state.get("defense_runtime", {})
    return normalize_blue_policy_state(
        {
            "domain_trust": runtime.get("domain_trust", {}),
            "detection_sensitivity": runtime.get("detection_sensitivity", {}),
            "escalation_threshold": runtime.get("escalation_threshold", {}),
            "effect_sensitivity": runtime.get("effect_sensitivity", {}),
            "effect_threshold": runtime.get("effect_threshold", {}),
            "feedback_counts": runtime.get("feedback_counts", {}),
            "effect_feedback_counts": runtime.get("effect_feedback_counts", {}),
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
        sensitivity = domain_sensitivity * effect_sensitivity
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
    threat_seen = any(threat.target == domain for threat in threats)
    goal_effect_id = _score_effect_id(score)
    seen_effect_ids = set(_threat_effect_ids(threats))
    effect_seen = goal_effect_id in seen_effect_ids if goal_effect_id else False
    reason = "stable_detection"
    effect_reason = None

    if score.attack_success and not score.detection_success:
        counts["missed_attack"] += 1
        _adjust(policy, domain, trust_delta=-0.08, sensitivity_delta=0.06, threshold_delta=-0.03)
        reason = "missed_attack_raise_sensitivity"
    elif score.false_positive:
        counts["false_positive"] += 1
        _adjust(policy, domain, trust_delta=0.04, sensitivity_delta=-0.05, threshold_delta=0.03)
        reason = "false_positive_reduce_sensitivity"
    elif score.detection_success:
        counts["detected"] += 1
        trust_delta = 0.02 if score.recovery_success else -0.02
        sensitivity_delta = 0.01 if threat_seen else 0.0
        _adjust(policy, domain, trust_delta=trust_delta, sensitivity_delta=sensitivity_delta, threshold_delta=0.0)
        reason = "detected_reinforce_domain"

    if goal_effect_id:
        effect_counts = policy["effect_feedback_counts"][goal_effect_id]
        if score.goal_success and not effect_seen:
            effect_counts["missed_effect"] += 1
            _adjust_effect(policy, goal_effect_id, sensitivity_delta=0.08, threshold_delta=-0.04)
            effect_reason = "missed_goal_effect_raise_sensitivity"
        elif score.goal_success and effect_seen:
            effect_counts["detected_effect"] += 1
            _adjust_effect(
                policy,
                goal_effect_id,
                sensitivity_delta=0.01 if score.recovery_success else 0.03,
                threshold_delta=0.0,
            )
            effect_reason = "detected_goal_effect_reinforce"
        elif (not score.goal_success) and effect_seen:
            effect_counts["false_positive_effect"] += 1
            _adjust_effect(policy, goal_effect_id, sensitivity_delta=-0.04, threshold_delta=0.03)
            effect_reason = "false_positive_goal_effect_reduce_sensitivity"

        if score.recovery_success and effect_seen:
            effect_counts["recovered_effect"] += 1

    if score.recovery_success:
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
            "goal_id": score.goal_id,
            "goal_success": score.goal_success,
            "goal_effect_id": goal_effect_id,
            "goal_effect_seen": effect_seen,
            "seen_effect_ids": sorted(seen_effect_ids),
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


def _policy_tunables(policy: dict) -> dict:
    return {
        "domain_trust": deepcopy(policy["domain_trust"]),
        "detection_sensitivity": deepcopy(policy["detection_sensitivity"]),
        "escalation_threshold": deepcopy(policy["escalation_threshold"]),
        "effect_sensitivity": deepcopy(policy["effect_sensitivity"]),
        "effect_threshold": deepcopy(policy["effect_threshold"]),
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


def _threat_effect_ids(threats: list[Threat]) -> list[str]:
    effect_ids: list[str] = []
    for threat in threats:
        effect_ids.extend(effect_ids_from_tags(threat.tags))
    return sorted(set(effect_ids))
