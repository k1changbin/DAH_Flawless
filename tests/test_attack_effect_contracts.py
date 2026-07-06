import unittest

from dah_flawless.attacks.catalog import get_attack, realistic_attacks
from dah_flawless.attacks.effect_contracts import contract_supports_goal, score_contract_alignment
from dah_flawless.attacks.selector import score_attack_candidates
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.scoring.scorer import score_round
from dah_flawless.situation_tagger import derive_tag_details


class AttackEffectContractTests(unittest.TestCase):
    def test_contract_supports_only_coherent_goal_families(self):
        self.assertTrue(contract_supports_goal("TIME_DESYNC_REPLAY", "COMMAND_STALE_ACCEPTANCE"))
        self.assertTrue(contract_supports_goal("PRIORITY_POISONING", "WRONG_TARGET_SELECTION"))
        self.assertFalse(contract_supports_goal("PRIORITY_POISONING", "COMMAND_STALE_ACCEPTANCE"))
        self.assertFalse(contract_supports_goal("TELEMETRY_FDI", "WRONG_TARGET_SELECTION"))

    def test_attack_selector_penalizes_contract_mismatch(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))
        weights = {attack.name: attack.weight for attack in realistic_attacks()}
        goal_plan = {
            "goal_id": "COMMAND_STALE_ACCEPTANCE",
            "target_domain": "command",
            "preferred_attacks": ["TIME_DESYNC_REPLAY"],
            "preferred_tactics": ["replay"],
        }

        candidates = score_attack_candidates(realistic_attacks(), weights, details, goal_plan=goal_plan)
        by_attack = {candidate["attack"]: candidate for candidate in candidates}

        self.assertEqual(candidates[0]["attack"], "TIME_DESYNC_REPLAY")
        self.assertLess(
            by_attack["PRIORITY_POISONING"]["contract_multiplier"],
            by_attack["TIME_DESYNC_REPLAY"]["contract_multiplier"],
        )
        self.assertFalse(by_attack["PRIORITY_POISONING"]["contract_alignment"]["supported_goal"])

    def test_goal_scorer_clamps_contract_mismatch_reward(self):
        state = create_baseline_state(seed=1)
        attack = get_attack("PRIORITY_POISONING")
        score = score_round(
            state,
            state,
            attack,
            threats=[],
            actions=[],
            red_goal={"goal_id": "COMMAND_STALE_ACCEPTANCE", "target_domain": "command"},
        )

        goal_score = score.evidence["goal_score"]
        self.assertFalse(score.goal_success)
        self.assertFalse(goal_score["contract_alignment"]["supported_goal"])
        self.assertEqual(goal_score["reward_algorithm"], "contract_violation_reward_clamp")
        self.assertEqual(goal_score["mission_impact_reward_adjustment"], 0.0)
        self.assertLessEqual(score.goal_reward, 0.06)

    def test_simulation_logs_contract_alignment_for_goal_scores(self):
        logs, _ = run_simulation(seed=42, rounds=10)

        mismatches = []
        for entry in logs:
            goal_score = entry["score"]["evidence"]["goal_score"]
            self.assertIn("contract_alignment", goal_score)
            alignment = goal_score["contract_alignment"]
            if not alignment["supported_goal"]:
                mismatches.append((entry["round"], entry["attack"]["name"], entry["red_goal"]["goal_id"]))

        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
