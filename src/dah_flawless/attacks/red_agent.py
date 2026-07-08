"""Policy-based Red Agent.

For the report MVP, the first three rounds use a fixed sequence so every core
attack has evidence. Later rounds use weighted tag matching.

The agent also runs a small Stealth Controller: in ``adaptive`` mode an attack
that gets detected is switched to a stealth variant on its next use, so the
detection feedback visibly changes Red's behaviour (co-evolution).
"""

from __future__ import annotations

import random

from dah_flawless.attacks.catalog import get_attack, realistic_attacks
from dah_flawless.attacks.goal_planner import (
    default_goal_stats,
    normalize_goal_stats,
    score_goal_candidates,
    select_goal_for_attack,
    update_goal_stats,
)
from dah_flawless.attacks.selector import build_tactic, score_attack_candidates
from dah_flawless.attacks.telemetry_memory import TelemetryMemory
from dah_flawless.config import (
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_STEALTH_MODE,
    DEFAULT_TACTIC_EXPLORATION_RATE,
    SCRIPTED_ATTACKS,
)
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.schemas import Attack, SituationTag, decision

RED_WEIGHT_RELATIVE_LEARNING_RATE = 0.08
RED_WEIGHT_MEAN_REVERSION_RATE = 0.04
RED_WEIGHT_RELATIVE_FLOOR = 0.55
RED_WEIGHT_RELATIVE_CEILING = 1.45


class RedAgent:
    def __init__(
        self,
        seed: int,
        scripted_attacks: tuple[str, ...] = SCRIPTED_ATTACKS,
        stealth_mode: str = DEFAULT_STEALTH_MODE,
        mutation_profile: str = DEFAULT_MUTATION_PROFILE,
        policy_state: dict | None = None,
        policy_update_reviewer: PolicyUpdateReviewer | None = None,
    ):
        self._rng = random.Random(seed)
        self._scripted_attacks = scripted_attacks
        self._stealth_mode = stealth_mode
        self._mutation_profile = mutation_profile
        self._base_weights = {attack.name: attack.weight for attack in realistic_attacks()}
        self._weights = dict(self._base_weights)
        self._goal_stats = default_goal_stats()
        self._stealth_for: set[str] = set()  # attacks switched to stealth (adaptive)
        self._telemetry_probe_delta = 24
        self._tactic_exploration_rate = DEFAULT_TACTIC_EXPLORATION_RATE
        self._telemetry_memory = TelemetryMemory()
        self._policy_update_reviewer = policy_update_reviewer or build_policy_update_reviewer()
        self.load_policy_state(policy_state)

    def choose_attack(
        self,
        round_number: int,
        observed_state: dict,
        tags: list[str],
        tag_details: list[SituationTag] | None = None,
        previous_logs: list[dict] | None = None,
    ) -> tuple[Attack, bool, dict, dict]:
        telemetry_memory = self._telemetry_memory.observe(observed_state, round_number=round_number)
        goal_candidates = score_goal_candidates(
            tag_details=tag_details,
            observed_state=observed_state,
            previous_logs=previous_logs or [],
            goal_stats=self._goal_stats,
            round_number=round_number,
        )
        if round_number <= len(self._scripted_attacks):
            attack = get_attack(self._scripted_attacks[round_number - 1])
            goal_plan = select_goal_for_attack(attack.name, goal_candidates)
            stealth = self._use_stealth(attack.name)
            tactic = self._build_tactic(
                attack.name,
                stealth,
                tag_details,
                goal_plan,
                exploration_rate=0.0,
                recent_tactics=[],
            )
            log = decision(
                "RedAgent",
                "attack_selected",
                "scripted_mvp_coverage",
                before=_tag_context(tags, tag_details),
                after={
                    "attack": attack.name,
                    "stealth": stealth,
                    "goal": goal_plan,
                    "tactic": tactic,
                    "telemetry_memory": telemetry_memory,
                    "goal_candidate_scores": goal_candidates,
                    "attack_candidate_scores": score_attack_candidates(
                        realistic_attacks(),
                        self._weights,
                        tag_details,
                        goal_plan=goal_plan,
                        previous_logs=previous_logs or [],
                    ),
                },
            )
            return attack, stealth, tactic, log

        goal_plan = goal_candidates[0]
        attack_candidates = score_attack_candidates(
            realistic_attacks(),
            self._weights,
            tag_details,
            goal_plan=goal_plan,
            previous_logs=previous_logs or [],
        )
        attacks_by_name = {attack.name: attack for attack in realistic_attacks()}
        weighted = [(attacks_by_name[candidate["attack"]], max(candidate["score"], 0.0)) for candidate in attack_candidates]

        total = sum(weight for _, weight in weighted)
        pick = self._rng.uniform(0.0, total)
        cursor = 0.0
        chosen = weighted[-1][0]
        reason = "fallback"
        for attack, weight in weighted:
            cursor += weight
            if pick <= cursor:
                chosen = attack
                reason = "weighted_tag_policy"
                break

        stealth = self._use_stealth(chosen.name)
        tactic = self._build_tactic(
            chosen.name,
            stealth,
            tag_details,
            goal_plan,
            exploration_rate=self._tactic_exploration_rate,
            recent_tactics=_recent_tactics(previous_logs or [], chosen.name),
        )
        log = decision(
            "RedAgent",
            "attack_selected",
            reason,
            before=_tag_context(tags, tag_details),
            after={
                "attack": chosen.name,
                "stealth": stealth,
                "goal": goal_plan,
                "tactic": tactic,
                "telemetry_memory": telemetry_memory,
                "goal_candidate_scores": goal_candidates,
                "attack_candidate_scores": attack_candidates,
            },
        )
        return chosen, stealth, tactic, log

    def _use_stealth(self, attack_name: str) -> bool:
        if self._stealth_mode == "on":
            return True
        if self._stealth_mode == "off":
            return False
        return attack_name in self._stealth_for  # adaptive

    def _build_tactic(
        self,
        attack_name: str,
        stealth: bool,
        tag_details: list[SituationTag] | None,
        goal_plan: dict | None = None,
        exploration_rate: float = 0.0,
        recent_tactics: list[str] | None = None,
    ) -> dict:
        return build_tactic(
            attack_name,
            stealth,
            tag_details,
            self._telemetry_probe_delta,
            mutation_profile=self._mutation_profile,
            goal_plan=goal_plan,
            rng=self._rng,
            exploration_rate=exploration_rate,
            recent_tactics=recent_tactics,
        )

    def update_weight(
        self,
        attack_name: str,
        detected: bool,
        goal_id: str | None = None,
        score=None,
        round_number: int = 0,
    ) -> dict:
        before = self._weights.get(attack_name, 0.0)
        before_weights = dict(self._weights)
        baseline = self._base_weights.get(attack_name, before or 1.0)
        before_probe_delta = self._telemetry_probe_delta
        goal_update = None
        feedback_signal = _attack_weight_feedback_signal(detected=detected, score=score)
        telemetry_learning_feedback = _telemetry_learning_feedback(score)
        proposed_weight_before_normalization = _proposed_attack_weight(
            before,
            detected=detected,
            score=score,
            baseline_weight=baseline,
        )
        proposed_weights = dict(self._weights)
        proposed_weights[attack_name] = proposed_weight_before_normalization
        proposed_weights, proposed_normalization = _normalize_relative_attack_weights(
            proposed_weights,
            self._base_weights,
        )
        proposed_weight = proposed_weights.get(attack_name, proposed_weight_before_normalization)
        proposed_probe_delta = before_probe_delta
        if attack_name == "TELEMETRY_FDI":
            if detected:
                proposed_probe_delta = max(2, before_probe_delta - 6)
            else:
                proposed_probe_delta = min(28, before_probe_delta + 2)

        reviewed, review_log = self._policy_update_reviewer.review_update(
            agent="RedAgent",
            update_name="attack_weight",
            before={
                "weight": before,
                "weights": before_weights,
                "telemetry_probe_delta": before_probe_delta,
            },
            proposed={
                "weight": proposed_weight,
                "weights": proposed_weights,
                "telemetry_probe_delta": proposed_probe_delta,
            },
            context={
                "attack_name": attack_name,
                "detected": detected,
                "goal_success": getattr(score, "goal_success", None) if score is not None else None,
                "goal_reward": getattr(score, "goal_reward", None) if score is not None else None,
                "winner_detail": getattr(score, "winner_detail", None) if score is not None else None,
                "agent_family": "red_probe",
                "stealth_mode": self._stealth_mode,
                "weight_update_policy": "relative_feedback_normalized_mean_v1",
                "baseline_weight": baseline,
                "feedback_signal": feedback_signal,
                "telemetry_learning_feedback": telemetry_learning_feedback,
                "proposed_weight_before_normalization": proposed_weight_before_normalization,
                "proposed_weight_normalization": proposed_normalization,
            },
        )

        reviewed_weights = reviewed.get("weights") if isinstance(reviewed.get("weights"), dict) else None
        if reviewed_weights:
            normalized_weights, applied_normalization = _normalize_relative_attack_weights(
                {name: float(value) for name, value in reviewed_weights.items()},
                self._base_weights,
            )
            self._weights = normalized_weights
        else:
            self._weights[attack_name] = float(reviewed["weight"])
            self._weights, applied_normalization = _normalize_relative_attack_weights(
                self._weights,
                self._base_weights,
            )
        after = float(self._weights.get(attack_name, reviewed["weight"]))
        self._telemetry_probe_delta = int(reviewed["telemetry_probe_delta"])
        # Adaptive stealth: once an attack is detected, retry it quietly.
        if self._stealth_mode == "adaptive" and detected:
            self._stealth_for.add(attack_name)
        if goal_id and score is not None:
            self._goal_stats, goal_update = update_goal_stats(self._goal_stats, goal_id, score, round_number=round_number)
        return decision(
            "RedAgent",
            "weight_update",
            "attack_detected" if detected else "attack_not_detected",
            before={
                "weight": before,
                "weights": before_weights,
                "telemetry_probe_delta": before_probe_delta,
            },
            after={
                "weight": after,
                "weights": dict(sorted(self._weights.items())),
                "telemetry_probe_delta": self._telemetry_probe_delta,
                "relative_weight_update": {
                    "algorithm": "relative_feedback_normalized_mean_v1",
                    "baseline_weight": round(float(baseline), 4),
                    "feedback_signal": feedback_signal,
                    "telemetry_learning_feedback": telemetry_learning_feedback,
                    "learning_rate": RED_WEIGHT_RELATIVE_LEARNING_RATE,
                    "mean_reversion_rate": RED_WEIGHT_MEAN_REVERSION_RATE,
                    "relative_floor": RED_WEIGHT_RELATIVE_FLOOR,
                    "relative_ceiling": RED_WEIGHT_RELATIVE_CEILING,
                    "proposed_weight_before_normalization": proposed_weight_before_normalization,
                    "proposed_weight_after_normalization": proposed_weight,
                    "applied_weight_normalization": applied_normalization,
                },
                "policy_update_review": review_log,
                "goal_feedback": goal_update,
            },
        )

    def load_policy_state(self, policy_state: dict | None) -> None:
        if not policy_state:
            return
        weights = policy_state.get("weights", {})
        for attack_name in self._weights:
            if attack_name in weights:
                self._weights[attack_name] = float(weights[attack_name])
        self._stealth_for = set(policy_state.get("stealth_for", []))
        if "telemetry_probe_delta" in policy_state:
            self._telemetry_probe_delta = int(policy_state["telemetry_probe_delta"])
        if "tactic_exploration_rate" in policy_state:
            self._tactic_exploration_rate = float(policy_state["tactic_exploration_rate"])
        if "goal_stats" in policy_state:
            self._goal_stats = normalize_goal_stats(policy_state["goal_stats"])
        if "telemetry_memory" in policy_state:
            self._telemetry_memory = TelemetryMemory.from_state(policy_state["telemetry_memory"])

    def export_policy_state(self) -> dict:
        return {
            "weights": dict(sorted(self._weights.items())),
            "goal_stats": deepcopy_sorted_goal_stats(self._goal_stats),
            "stealth_for": sorted(self._stealth_for),
            "telemetry_probe_delta": self._telemetry_probe_delta,
            "tactic_exploration_rate": self._tactic_exploration_rate,
            "stealth_mode": self._stealth_mode,
            "mutation_profile": self._mutation_profile,
        }

    def export_telemetry_memory_state(self) -> dict:
        return self._telemetry_memory.export_state()


def _tag_context(tags: list[str], tag_details: list[SituationTag] | None) -> dict:
    return {
        "tags": tags,
        "tag_details": [detail.to_dict() for detail in tag_details or []],
    }


def deepcopy_sorted_goal_stats(goal_stats: dict) -> dict:
    return {goal_id: dict(goal_stats[goal_id]) for goal_id in sorted(goal_stats)}


def _proposed_attack_weight(
    before: float,
    *,
    detected: bool,
    score,
    baseline_weight: float | None = None,
) -> float:
    baseline = float(baseline_weight if baseline_weight is not None else before or 1.0)
    signal = _attack_weight_feedback_signal(detected=detected, score=score)
    relative_delta = float(before) * RED_WEIGHT_RELATIVE_LEARNING_RATE * signal
    anchor_delta = (baseline - float(before)) * RED_WEIGHT_MEAN_REVERSION_RATE
    lower, upper = _relative_weight_bounds(baseline)
    return round(min(upper, max(lower, float(before) + relative_delta + anchor_delta)), 4)


def _attack_weight_feedback_signal(*, detected: bool, score) -> float:
    if score is None:
        return -0.50 if detected else 0.36

    goal_reward = float(getattr(score, "goal_reward", 0.0))
    goal_success = bool(getattr(score, "goal_success", False))
    winner_detail = getattr(score, "winner_detail", None)
    winner = getattr(score, "winner", None)
    attrition = getattr(score, "evidence", {}).get("attrition", {}) if score is not None else {}
    attrition_cost_effective = bool(attrition.get("cost_effective", True))

    signal = -0.20 if detected else 0.12
    signal += 0.55 * (goal_reward - 0.45)
    signal += 0.22 if goal_success else -0.22

    if winner == "RED_BREACH":
        signal += 0.18
    elif winner == "RED_ATTRITION":
        signal += 0.16 if attrition_cost_effective else -0.14
    elif winner == "BLUE_RECOVERY":
        signal -= 0.24
    elif winner == "BLUE":
        signal -= 0.12

    if winner_detail == "PARTIAL_BREACH":
        signal -= 0.18
    elif winner_detail in {"NO_EFFECT", "FALSE_POSITIVE"}:
        signal -= 0.12

    signal += _telemetry_learning_feedback(score).get("red_weight_bonus", 0.0)
    return round(min(1.0, max(-1.0, signal)), 4)


def _telemetry_learning_feedback(score) -> dict:
    if score is None or getattr(score, "target_domain", None) != "telemetry":
        return {"applied": False, "reason": "non_telemetry_or_no_score", "red_weight_bonus": 0.0}
    evidence = getattr(score, "evidence", {}) or {}
    goal_score = evidence.get("goal_score", {})
    goal_evidence = goal_score.get("evidence", {}) if isinstance(goal_score, dict) else {}
    signal = goal_evidence.get("telemetry_learning_signal")
    if not isinstance(signal, dict):
        return {"applied": False, "reason": "missing_telemetry_learning_signal", "red_weight_bonus": 0.0}

    active_axes = signal.get("active_axes", []) or []
    axis_entropy = float(signal.get("axis_entropy", 0.0) or 0.0)
    weighted_effect_score = float(signal.get("weighted_effect_score", 0.0) or 0.0)
    diversity_bonus = float(signal.get("red_policy_diversity_bonus", 0.0) or 0.0)
    red_weight_bonus = min(0.14, diversity_bonus + min(0.04, weighted_effect_score * 0.04))
    return {
        "applied": red_weight_bonus > 0.0,
        "dominant_axis": signal.get("dominant_axis"),
        "active_axes": list(active_axes),
        "axis_entropy": round(axis_entropy, 4),
        "weighted_effect_score": round(weighted_effect_score, 4),
        "red_weight_bonus": round(red_weight_bonus, 4),
    }


def _normalize_relative_attack_weights(
    weights: dict[str, float],
    base_weights: dict[str, float],
) -> tuple[dict[str, float], dict]:
    target_total = sum(float(value) for value in base_weights.values())
    normalized = {
        attack_name: _clamp_relative_weight(
            float(weights.get(attack_name, baseline)),
            float(baseline),
        )
        for attack_name, baseline in base_weights.items()
    }
    clipped_before_scaling = [
        attack_name
        for attack_name, baseline in base_weights.items()
        if round(float(weights.get(attack_name, baseline)), 4) != normalized[attack_name]
    ]

    for _ in range(8):
        current_total = sum(normalized.values())
        if current_total <= 0:
            break
        scale = target_total / current_total
        if abs(scale - 1.0) < 0.0001:
            break
        next_weights = {
            attack_name: _clamp_relative_weight(value * scale, float(base_weights[attack_name]))
            for attack_name, value in normalized.items()
        }
        if all(abs(next_weights[name] - normalized[name]) < 0.0001 for name in normalized):
            normalized = next_weights
            break
        normalized = next_weights

    normalized = {attack_name: round(value, 4) for attack_name, value in sorted(normalized.items())}
    return normalized, {
        "algorithm": "preserve_relative_attack_weight_mean_v1",
        "target_total": round(target_total, 4),
        "actual_total": round(sum(normalized.values()), 4),
        "relative_floor": RED_WEIGHT_RELATIVE_FLOOR,
        "relative_ceiling": RED_WEIGHT_RELATIVE_CEILING,
        "clipped_before_scaling": sorted(clipped_before_scaling),
    }


def _relative_weight_bounds(baseline_weight: float) -> tuple[float, float]:
    baseline = max(0.0001, float(baseline_weight))
    return baseline * RED_WEIGHT_RELATIVE_FLOOR, baseline * RED_WEIGHT_RELATIVE_CEILING


def _clamp_relative_weight(value: float, baseline_weight: float) -> float:
    lower, upper = _relative_weight_bounds(baseline_weight)
    return round(min(upper, max(lower, float(value))), 4)


def _recent_tactics(previous_logs: list[dict], attack_name: str, window: int = 5) -> list[str]:
    tactics: list[str] = []
    for entry in reversed(previous_logs):
        if entry.get("attack", {}).get("name") != attack_name:
            continue
        strategy = (entry.get("red_tactic") or {}).get("strategy")
        if strategy:
            tactics.append(strategy)
        if len(tactics) >= window:
            break
    return list(reversed(tactics))
