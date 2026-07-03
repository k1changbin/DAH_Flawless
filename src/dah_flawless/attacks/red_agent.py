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
from dah_flawless.config import DEFAULT_STEALTH_MODE, SCRIPTED_ATTACKS
from dah_flawless.schemas import Attack, decision


class RedAgent:
    def __init__(
        self,
        seed: int,
        scripted_attacks: tuple[str, ...] = SCRIPTED_ATTACKS,
        stealth_mode: str = DEFAULT_STEALTH_MODE,
    ):
        self._rng = random.Random(seed)
        self._scripted_attacks = scripted_attacks
        self._stealth_mode = stealth_mode
        self._weights = {attack.name: attack.weight for attack in realistic_attacks()}
        self._stealth_for: set[str] = set()  # attacks switched to stealth (adaptive)
        self._telemetry_probe_delta = 24

    def choose_attack(
        self, round_number: int, observed_state: dict, tags: list[str]
    ) -> tuple[Attack, bool, dict, dict]:
        if round_number <= len(self._scripted_attacks):
            attack = get_attack(self._scripted_attacks[round_number - 1])
            stealth = self._use_stealth(attack.name)
            tactic = self._build_tactic(attack.name, stealth)
            log = decision(
                "RedAgent",
                "attack_selected",
                "scripted_mvp_coverage",
                before=None,
                after={"attack": attack.name, "stealth": stealth, "tactic": tactic},
            )
            return attack, stealth, tactic, log

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
        chosen = weighted[-1][0]
        reason = "fallback"
        for attack, weight in weighted:
            cursor += weight
            if pick <= cursor:
                chosen = attack
                reason = "weighted_tag_policy"
                break

        stealth = self._use_stealth(chosen.name)
        tactic = self._build_tactic(chosen.name, stealth)
        log = decision(
            "RedAgent",
            "attack_selected",
            reason,
            before=tags,
            after={"attack": chosen.name, "stealth": stealth, "tactic": tactic},
        )
        return chosen, stealth, tactic, log

    def _use_stealth(self, attack_name: str) -> bool:
        if self._stealth_mode == "on":
            return True
        if self._stealth_mode == "off":
            return False
        return attack_name in self._stealth_for  # adaptive

    def _build_tactic(self, attack_name: str, stealth: bool) -> dict:
        if not stealth:
            return {"stealth": False, "strategy": "loud"}
        if attack_name == "TELEMETRY_FDI":
            return {
                "stealth": True,
                "strategy": "boundary_probe",
                "probe_delta": self._telemetry_probe_delta,
            }
        return {"stealth": True, "strategy": "no_boundary_margin"}

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
