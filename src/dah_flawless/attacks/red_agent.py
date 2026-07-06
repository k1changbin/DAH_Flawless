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
        goal_update = None
        proposed_weight = max(1.0, before - 0.5) if detected else before + 0.5
        proposed_probe_delta = before_probe_delta
        if attack_name == "TELEMETRY_FDI":
            if detected:
                proposed_probe_delta = max(2, before_probe_delta - 6)
            else:
                proposed_probe_delta = min(28, before_probe_delta + 2)

        reviewed, review_log = self._policy_update_reviewer.review_update(
            agent="RedAgent",
            update_name="attack_weight",
            before={"weight": before, "telemetry_probe_delta": before_probe_delta},
            proposed={"weight": proposed_weight, "telemetry_probe_delta": proposed_probe_delta},
            context={
                "attack_name": attack_name,
                "detected": detected,
                "agent_family": "red_probe",
                "stealth_mode": self._stealth_mode,
            },
        )

        after = float(reviewed["weight"])
        self._weights[attack_name] = after
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
            before={"weight": before, "telemetry_probe_delta": before_probe_delta},
            after={
                "weight": after,
                "telemetry_probe_delta": self._telemetry_probe_delta,
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


def _tag_context(tags: list[str], tag_details: list[SituationTag] | None) -> dict:
    return {
        "tags": tags,
        "tag_details": [detail.to_dict() for detail in tag_details or []],
    }


def deepcopy_sorted_goal_stats(goal_stats: dict) -> dict:
    return {goal_id: dict(goal_stats[goal_id]) for goal_id in sorted(goal_stats)}


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
