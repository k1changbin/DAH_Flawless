"""Policy-based Red Agent.

For the report MVP, the first three rounds use a fixed sequence so every core
attack has evidence. Later rounds can use weighted tag matching.
"""

from __future__ import annotations

import random

from dah_flawless.attacks.catalog import get_attack, realistic_attacks
from dah_flawless.config import SCRIPTED_ATTACKS
from dah_flawless.schemas import Attack, decision


class RedAgent:
    def __init__(self, seed: int, scripted_attacks: tuple[str, ...] = SCRIPTED_ATTACKS):
        self._rng = random.Random(seed)
        self._scripted_attacks = scripted_attacks
        self._weights = {attack.name: attack.weight for attack in realistic_attacks()}

    def choose_attack(self, round_number: int, observed_state: dict, tags: list[str]) -> tuple[Attack, dict]:
        if round_number <= len(self._scripted_attacks):
            attack = get_attack(self._scripted_attacks[round_number - 1])
            log = decision(
                "RedAgent",
                "attack_selected",
                "scripted_mvp_coverage",
                before=None,
                after=attack.name,
            )
            return attack, log

        weighted = []
        tag_set = set(tags)
        for attack in realistic_attacks():
            weight = self._weights[attack.name]
            if tag_set.intersection(attack.preferred_tags):
                weight *= 3
            weighted.append((attack, max(weight, 0.0)))

        total = sum(weight for _, weight in weighted)
        pick = self._rng.uniform(0.0, total)
        cursor = 0.0
        for attack, weight in weighted:
            cursor += weight
            if pick <= cursor:
                return attack, decision(
                    "RedAgent",
                    "attack_selected",
                    "weighted_tag_policy",
                    before=tags,
                    after=attack.name,
                )

        attack = weighted[-1][0]
        return attack, decision("RedAgent", "attack_selected", "fallback", before=tags, after=attack.name)

    def update_weight(self, attack_name: str, detected: bool) -> dict:
        before = self._weights.get(attack_name, 0.0)
        after = max(1.0, before - 0.5) if detected else before + 0.5
        self._weights[attack_name] = after
        return decision(
            "RedAgent",
            "weight_update",
            "attack_detected" if detected else "attack_not_detected",
            before=before,
            after=after,
        )
