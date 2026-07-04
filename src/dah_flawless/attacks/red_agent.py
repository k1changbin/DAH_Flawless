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
        self._attack_stats = {
            attack.name: {"tries": 0, "detected": 0, "not_detected": 0}
            for attack in realistic_attacks()
        }
        self._stealth_for: set[str] = set()  # attacks switched to stealth (adaptive)
        self._telemetry_probe_delta = 24

    def choose_attack(
        self, round_number: int, observed_state: dict, tags: list[str]
    ) -> tuple[Attack, bool, dict, dict]:
        if round_number <= len(self._scripted_attacks):
            attack = get_attack(self._scripted_attacks[round_number - 1])
            stealth = self._use_stealth(attack.name)
            tactic = self._build_tactic(attack.name, stealth)
            self._record_try(attack.name)
            log = decision(
                "RedAgent",
                "attack_selected",
                "scripted_mvp_coverage",
                before=None,
                after={
                    "attack": attack.name,
                    "stealth": stealth,
                    "tactic": tactic,
                    "candidate_scores": {
                        attack.name: {
                            "base_weight": self._weights.get(attack.name, 0.0),
                            "tag_match_multiplier": 1,
                            "final_score": self._weights.get(attack.name, 0.0),
                        }
                    },
                },
            )
            return attack, stealth, tactic, log

        weighted = []
        candidate_scores = {}
        tag_set = set(tags)
        for attack in realistic_attacks():
            base_weight = self._weights[attack.name]
            tag_match = bool(tag_set.intersection(attack.preferred_tags))
            multiplier = 3 if tag_match else 1
            score = max(base_weight * multiplier, 0.0)
            candidate_scores[attack.name] = {
                "base_weight": round(base_weight, 4),
                "tag_match_multiplier": multiplier,
                "final_score": round(score, 4),
            }
            weighted.append((attack, score))

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
        self._record_try(chosen.name)
        log = decision(
            "RedAgent",
            "attack_selected",
            reason,
            before=tags,
            after={
                "attack": chosen.name,
                "stealth": stealth,
                "tactic": tactic,
                "candidate_scores": candidate_scores,
            },
        )
        return chosen, stealth, tactic, log

    def snapshot_policy(self) -> dict:
        return {
            "attack_weights": {name: round(weight, 4) for name, weight in sorted(self._weights.items())},
            "attack_stats": {
                name: dict(stats)
                for name, stats in sorted(self._attack_stats.items())
            },
            "stealth_mode": self._stealth_mode,
            "stealth_for": sorted(self._stealth_for),
            "telemetry_probe_delta": self._telemetry_probe_delta,
        }

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
        stats = self._attack_stats.setdefault(attack_name, {"tries": 0, "detected": 0, "not_detected": 0})
        if detected:
            stats["detected"] += 1
        else:
            stats["not_detected"] += 1
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
            after={
                "weight": after,
                "telemetry_probe_delta": self._telemetry_probe_delta,
                "policy_state": self.snapshot_policy(),
            },
        )

    def _record_try(self, attack_name: str) -> None:
        stats = self._attack_stats.setdefault(attack_name, {"tries": 0, "detected": 0, "not_detected": 0})
        stats["tries"] += 1
