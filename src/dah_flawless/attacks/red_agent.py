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
from dah_flawless.attacks.selector import build_tactic, score_attack_candidates
from dah_flawless.config import DEFAULT_MUTATION_PROFILE, DEFAULT_STEALTH_MODE, SCRIPTED_ATTACKS
from dah_flawless.schemas import Attack, SituationTag, decision


class RedAgent:
    def __init__(
        self,
        seed: int,
        scripted_attacks: tuple[str, ...] = SCRIPTED_ATTACKS,
        stealth_mode: str = DEFAULT_STEALTH_MODE,
        mutation_profile: str = DEFAULT_MUTATION_PROFILE,
        policy_state: dict | None = None,
    ):
        self._rng = random.Random(seed)
        self._scripted_attacks = scripted_attacks
        self._stealth_mode = stealth_mode
        self._mutation_profile = mutation_profile
        self._weights = {attack.name: attack.weight for attack in realistic_attacks()}
        self._stealth_for: set[str] = set()  # attacks switched to stealth (adaptive)
        self._telemetry_probe_delta = 24
        self.load_policy_state(policy_state)

    def choose_attack(
        self,
        round_number: int,
        observed_state: dict,
        tags: list[str],
        tag_details: list[SituationTag] | None = None,
    ) -> tuple[Attack, bool, dict, dict]:
        if round_number <= len(self._scripted_attacks):
            attack = get_attack(self._scripted_attacks[round_number - 1])
            stealth = self._use_stealth(attack.name)
            tactic = self._build_tactic(attack.name, stealth, tag_details)
            log = decision(
                "RedAgent",
                "attack_selected",
                "scripted_mvp_coverage",
                before=_tag_context(tags, tag_details),
                after={
                    "attack": attack.name,
                    "stealth": stealth,
                    "tactic": tactic,
                    "attack_candidate_scores": score_attack_candidates(
                        realistic_attacks(), self._weights, tag_details
                    ),
                },
            )
            return attack, stealth, tactic, log

        attack_candidates = score_attack_candidates(realistic_attacks(), self._weights, tag_details)
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
        tactic = self._build_tactic(chosen.name, stealth, tag_details)
        log = decision(
            "RedAgent",
            "attack_selected",
            reason,
            before=_tag_context(tags, tag_details),
            after={
                "attack": chosen.name,
                "stealth": stealth,
                "tactic": tactic,
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
    ) -> dict:
        return build_tactic(
            attack_name,
            stealth,
            tag_details,
            self._telemetry_probe_delta,
            mutation_profile=self._mutation_profile,
        )

    def update_weight(self, attack_name: str, detected: bool) -> dict:
        before = self._weights.get(attack_name, 0.0)
        after = max(1.0, before - 0.5) if detected else before + 0.5
        self._weights[attack_name] = after
        # Adaptive stealth: once an attack is detected, retry it quietly.
        if self._stealth_mode == "adaptive" and detected:
            self._stealth_for.add(attack_name)
        if attack_name == "TELEMETRY_FDI":
            if detected:
                self._telemetry_probe_delta = max(2, self._telemetry_probe_delta - 6)
            else:
                self._telemetry_probe_delta = min(28, self._telemetry_probe_delta + 2)
        return decision(
            "RedAgent",
            "weight_update",
            "attack_detected" if detected else "attack_not_detected",
            before=before,
            after={"weight": after, "telemetry_probe_delta": self._telemetry_probe_delta},
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

    def export_policy_state(self) -> dict:
        return {
            "weights": dict(sorted(self._weights.items())),
            "stealth_for": sorted(self._stealth_for),
            "telemetry_probe_delta": self._telemetry_probe_delta,
            "stealth_mode": self._stealth_mode,
            "mutation_profile": self._mutation_profile,
        }


def _tag_context(tags: list[str], tag_details: list[SituationTag] | None) -> dict:
    return {
        "tags": tags,
        "tag_details": [detail.to_dict() for detail in tag_details or []],
    }
