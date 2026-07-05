"""Blue feedback learner for observed-only defense policy updates."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.config import LOW_CONFIDENCE_THRESHOLD
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.schemas import DefenseAction, Score, Threat, decision

DOMAINS = ("telemetry", "mission", "command")
MIN_SENSITIVITY = 0.80
MAX_SENSITIVITY = 1.30
MIN_ESCALATION_THRESHOLD = 0.58
MAX_ESCALATION_THRESHOLD = 0.86


def default_blue_policy_state() -> dict:
    return {
        "domain_trust": {domain: 1.0 for domain in DOMAINS},
        "detection_sensitivity": {domain: 1.0 for domain in DOMAINS},
        "escalation_threshold": {domain: LOW_CONFIDENCE_THRESHOLD for domain in DOMAINS},
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
    }


def normalize_blue_policy_state(policy_state: dict | None) -> dict:
    normalized = default_blue_policy_state()
    if not policy_state:
        return normalized

    for key in ("domain_trust", "detection_sensitivity", "escalation_threshold"):
        for domain, value in policy_state.get(key, {}).items():
            if domain in normalized[key]:
                normalized[key][domain] = float(value)

    for domain, counts in policy_state.get("feedback_counts", {}).items():
        if domain not in normalized["feedback_counts"]:
            continue
        for name, value in counts.items():
            if name in normalized["feedback_counts"][domain]:
                normalized["feedback_counts"][domain][name] = int(value)

    _clamp_policy(normalized)
    return normalized


def apply_blue_policy_state(state: dict, policy_state: dict | None) -> None:
    policy = normalize_blue_policy_state(policy_state)
    runtime = state.setdefault("defense_runtime", {})
    runtime["domain_trust"] = deepcopy(policy["domain_trust"])
    runtime["detection_sensitivity"] = deepcopy(policy["detection_sensitivity"])
    runtime["escalation_threshold"] = deepcopy(policy["escalation_threshold"])
    runtime["feedback_counts"] = deepcopy(policy["feedback_counts"])


def export_blue_policy_state(state: dict) -> dict:
    runtime = state.get("defense_runtime", {})
    return normalize_blue_policy_state(
        {
            "domain_trust": runtime.get("domain_trust", {}),
            "detection_sensitivity": runtime.get("detection_sensitivity", {}),
            "escalation_threshold": runtime.get("escalation_threshold", {}),
            "feedback_counts": runtime.get("feedback_counts", {}),
        }
    )


def apply_detection_policy(threats: list[Threat], policy_state: dict | None) -> tuple[list[Threat], dict]:
    policy = normalize_blue_policy_state(policy_state)
    adjusted: list[Threat] = []
    before = [threat.to_dict() for threat in threats]

    for threat in threats:
        sensitivity = policy["detection_sensitivity"].get(threat.target, 1.0)
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
    reason = "stable_detection"

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

    if score.recovery_success:
        counts["recovered"] += 1

    if action_cost >= 0.10 or score.winner == "RED_ATTRITION":
        counts["over_defense"] += 1
        _adjust(policy, domain, trust_delta=0.02, sensitivity_delta=-0.03, threshold_delta=0.02)
        reason = f"{reason}_with_cost_control"

    _clamp_policy(policy)
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
            "over_defense": action_cost >= 0.10,
            "action_cost": action_cost,
        },
    )
    _apply_tunables(policy, reviewed_tunables)
    _clamp_policy(policy)
    return policy, decision(
        "BlueFeedbackLearner",
        "policy_updated",
        reason,
        before=before,
        after={
            "policy_state": deepcopy(policy),
            "action_cost": action_cost,
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


def _policy_tunables(policy: dict) -> dict:
    return {
        "domain_trust": deepcopy(policy["domain_trust"]),
        "detection_sensitivity": deepcopy(policy["detection_sensitivity"]),
        "escalation_threshold": deepcopy(policy["escalation_threshold"]),
    }


def _apply_tunables(policy: dict, tunables: dict) -> None:
    for key in ("domain_trust", "detection_sensitivity", "escalation_threshold"):
        for domain in DOMAINS:
            if domain in tunables.get(key, {}):
                policy[key][domain] = tunables[key][domain]


def _clamp_policy(policy: dict) -> None:
    for domain in DOMAINS:
        policy["domain_trust"][domain] = round(min(1.0, max(0.0, policy["domain_trust"][domain])), 4)
        policy["detection_sensitivity"][domain] = round(
            min(MAX_SENSITIVITY, max(MIN_SENSITIVITY, policy["detection_sensitivity"][domain])), 4
        )
        policy["escalation_threshold"][domain] = round(
            min(MAX_ESCALATION_THRESHOLD, max(MIN_ESCALATION_THRESHOLD, policy["escalation_threshold"][domain])), 4
        )
