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
from dah_flawless.config import (
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_STEALTH_MODE,
    DEFAULT_TACTIC_EXPLORATION_RATE,
    SCRIPTED_ATTACKS,
)
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.schemas import Attack, SituationTag, decision


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
        self._weights = {attack.name: attack.weight for attack in realistic_attacks()}
        self._goal_stats = default_goal_stats()
        self._attack_reward_ema = {attack.name: 0.45 for attack in realistic_attacks()}
        self._global_reward_ema = 0.45
        self._stealth_for: set[str] = set()  # attacks switched to stealth (adaptive)
        self._telemetry_probe_delta = 24
        self._tactic_exploration_rate = DEFAULT_TACTIC_EXPLORATION_RATE
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
        before_probe_delta = self._telemetry_probe_delta
        before_attack_reward_ema = self._attack_reward_ema.get(attack_name, self._global_reward_ema)
        before_global_reward_ema = self._global_reward_ema
        goal_update = None
        reward_context = _red_reward_context(
            score,
            detected=detected,
            baseline_reward=before_global_reward_ema,
        )
        proposed_weight = _proposed_attack_weight(
            before,
            detected=detected,
            score=score,
            baseline_reward=before_global_reward_ema,
            reward_context=reward_context,
        )
        proposed_attack_reward_ema = _ema(before_attack_reward_ema, reward_context["red_learning_reward"], alpha=0.22)
        proposed_global_reward_ema = _ema(
            before_global_reward_ema,
            reward_context["red_learning_reward"],
            alpha=0.08,
        )
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
                "telemetry_probe_delta": before_probe_delta,
                "attack_reward_ema": before_attack_reward_ema,
                "global_reward_ema": before_global_reward_ema,
            },
            proposed={
                "weight": proposed_weight,
                "telemetry_probe_delta": proposed_probe_delta,
                "attack_reward_ema": proposed_attack_reward_ema,
                "global_reward_ema": proposed_global_reward_ema,
            },
            context={
                "attack_name": attack_name,
                "detected": detected,
                "goal_success": getattr(score, "goal_success", None) if score is not None else None,
                "goal_reward": getattr(score, "goal_reward", None) if score is not None else None,
                "winner_detail": getattr(score, "winner_detail", None) if score is not None else None,
                "winner_side": getattr(score, "winner_side", None) if score is not None else None,
                "containment_score": getattr(score, "containment_score", None) if score is not None else None,
                "attempted_effect_success": getattr(score, "attempted_effect_success", None)
                if score is not None
                else None,
                "pre_defense_goal_success": getattr(score, "pre_defense_goal_success", None)
                if score is not None
                else None,
                "post_defense_effective_breach": getattr(score, "post_defense_effective_breach", None)
                if score is not None
                else None,
                "blue_recovered": getattr(score, "blue_recovered", None) if score is not None else None,
                "red_learning_reward": reward_context["red_learning_reward"],
                "baseline_reward": reward_context["baseline_reward"],
                "relative_advantage": reward_context["relative_advantage"],
                "agent_family": "red_probe",
                "stealth_mode": self._stealth_mode,
            },
        )

        after = float(reviewed["weight"])
        self._weights[attack_name] = after
        self._telemetry_probe_delta = int(reviewed["telemetry_probe_delta"])
        self._attack_reward_ema[attack_name] = float(reviewed.get("attack_reward_ema", proposed_attack_reward_ema))
        self._global_reward_ema = float(reviewed.get("global_reward_ema", proposed_global_reward_ema))
        self._restore_relative_floor_if_saturated()
        # Adaptive stealth: once an attack is detected, retry it quietly.
        if self._stealth_mode == "adaptive" and detected:
            self._stealth_for.add(attack_name)
        if goal_id and score is not None:
            self._goal_stats, goal_update = update_goal_stats(self._goal_stats, goal_id, score, round_number=round_number)
        return decision(
            "RedAgent",
            "weight_update",
            "attack_detected" if detected else "attack_not_detected",
            before={"weight": before, "telemetry_probe_delta": before_probe_delta},
            after={
                "weight": self._weights[attack_name],
                "telemetry_probe_delta": self._telemetry_probe_delta,
                "red_learning_reward": reward_context,
                "attack_reward_ema": self._attack_reward_ema[attack_name],
                "global_reward_ema": self._global_reward_ema,
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
        reward_ema = policy_state.get("attack_reward_ema") or policy_state.get("reward_ema") or {}
        for attack_name in self._attack_reward_ema:
            if attack_name in reward_ema:
                self._attack_reward_ema[attack_name] = float(reward_ema[attack_name])
        if "global_reward_ema" in policy_state:
            self._global_reward_ema = float(policy_state["global_reward_ema"])

    def export_policy_state(self) -> dict:
        return {
            "weights": dict(sorted(self._weights.items())),
            "attack_reward_ema": dict(sorted(self._attack_reward_ema.items())),
            "global_reward_ema": round(self._global_reward_ema, 4),
            "goal_stats": deepcopy_sorted_goal_stats(self._goal_stats),
            "stealth_for": sorted(self._stealth_for),
            "telemetry_probe_delta": self._telemetry_probe_delta,
            "tactic_exploration_rate": self._tactic_exploration_rate,
            "stealth_mode": self._stealth_mode,
            "mutation_profile": self._mutation_profile,
        }

    def _restore_relative_floor_if_saturated(self) -> None:
        if not self._weights or any(weight > 1.0001 for weight in self._weights.values()):
            return
        min_reward = min(self._attack_reward_ema.values())
        max_reward = max(self._attack_reward_ema.values())
        if max_reward - min_reward < 0.02:
            return
        for attack_name, reward in self._attack_reward_ema.items():
            self._weights[attack_name] = round(1.0 + max(0.0, reward - min_reward) * 2.0, 4)


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
    baseline_reward: float = 0.45,
    reward_context: dict | None = None,
) -> float:
    if score is None:
        return max(1.0, before - 0.5) if detected else before + 0.5

    reward_context = reward_context or _red_reward_context(score, detected=detected, baseline_reward=baseline_reward)
    relative_advantage = float(reward_context["relative_advantage"])
    attempted_effect = bool(getattr(score, "attempted_effect_success", getattr(score, "attack_success", False)))
    pre_defense_goal_success = bool(
        getattr(score, "pre_defense_goal_success", getattr(score, "goal_success", False))
    )
    post_defense_effective_breach = bool(getattr(score, "post_defense_effective_breach", False))
    winner_detail = getattr(score, "winner_detail", None)
    winner = getattr(score, "winner", None)
    attrition = getattr(score, "evidence", {}).get("attrition", {}) if score is not None else {}
    attrition_cost_effective = bool(attrition.get("cost_effective", True))

    delta = 0.70 * relative_advantage
    if attempted_effect:
        delta += 0.04
    else:
        delta -= 0.08
    if pre_defense_goal_success:
        delta += 0.05
    if post_defense_effective_breach:
        delta += 0.08

    if winner == "RED_BREACH":
        delta += 0.12
    elif winner == "RED_ATTRITION":
        delta += 0.10 if attrition_cost_effective else -0.10
    elif winner == "BLUE_RECOVERY":
        delta -= 0.08
    elif winner == "BLUE":
        delta -= 0.04

    if winner_detail == "PARTIAL_BREACH":
        delta -= 0.06
    elif winner_detail in {"NO_EFFECT", "FALSE_POSITIVE"}:
        delta -= 0.10

    delta = max(-0.35, min(0.35, delta))
    return max(1.0, round(before + delta, 4))


def _red_reward_context(score, *, detected: bool, baseline_reward: float) -> dict:
    if score is None:
        reward = 0.28 if detected else 0.56
        return {
            "red_learning_reward": reward,
            "baseline_reward": round(float(baseline_reward), 4),
            "relative_advantage": round(reward - float(baseline_reward), 4),
            "algorithm": "relative_red_reward_v2_no_score",
        }

    goal_reward = float(getattr(score, "goal_reward", 0.0))
    mission_impact = float(getattr(score, "evidence", {}).get("mission_impact", {}).get("mission_impact_score", 0.0))
    containment_score = float(getattr(score, "containment_score", 0.0))
    attempted_effect = bool(getattr(score, "attempted_effect_success", getattr(score, "attack_success", False)))
    pre_defense_goal_success = bool(
        getattr(score, "pre_defense_goal_success", getattr(score, "goal_success", False))
    )
    post_defense_effective_breach = bool(getattr(score, "post_defense_effective_breach", False))
    blue_recovered = bool(getattr(score, "blue_recovered", getattr(score, "recovery_success", False)))
    winner_side = getattr(score, "winner_side", None)
    winner = getattr(score, "winner", None)
    winner_detail = getattr(score, "winner_detail", None)
    attrition = getattr(score, "evidence", {}).get("attrition", {})
    attrition_cost_effective = bool(attrition.get("cost_effective", False))

    reward = 0.05 + 0.45 * goal_reward + 0.15 * mission_impact
    if attempted_effect:
        reward += 0.07
    if pre_defense_goal_success:
        reward += 0.10
    if post_defense_effective_breach:
        reward += 0.14
    if winner_side == "RED":
        reward += 0.10
    if winner == "RED_ATTRITION" and attrition_cost_effective:
        reward += 0.08

    if detected and containment_score >= 0.80:
        reward -= 0.12
    elif detected and containment_score >= 0.55:
        reward -= 0.07
    elif detected:
        reward -= 0.03
    if blue_recovered and not post_defense_effective_breach:
        reward -= 0.04
    if winner_detail == "RECOVERY":
        reward -= 0.04
    elif winner_detail in {"NO_EFFECT", "FALSE_POSITIVE"}:
        reward -= 0.08

    reward = round(min(1.0, max(0.0, reward)), 4)
    baseline = round(float(baseline_reward), 4)
    return {
        "red_learning_reward": reward,
        "baseline_reward": baseline,
        "relative_advantage": round(reward - baseline, 4),
        "goal_reward": round(goal_reward, 4),
        "mission_impact_score": round(mission_impact, 4),
        "containment_score": round(containment_score, 4),
        "attempted_effect_success": attempted_effect,
        "pre_defense_goal_success": pre_defense_goal_success,
        "post_defense_effective_breach": post_defense_effective_breach,
        "blue_recovered": blue_recovered,
        "algorithm": "relative_red_reward_v2",
    }


def _ema(before: float, value: float, *, alpha: float) -> float:
    return round((1.0 - alpha) * float(before) + alpha * float(value), 4)


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
