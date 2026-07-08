import unittest

from dah_flawless.environment.hash_log import verify_hash_chain
from dah_flawless.environment.round_combat_runner import (
    CombatStepMemory,
    RoundCombatRunner,
    _plan_blue_step,
    run_combat_rounds,
)
from dah_flawless.schemas import Threat


class RoundCombatRunnerTests(unittest.TestCase):
    def test_dynamic_combat_round_emits_step_logs_and_hash_chain(self):
        logs, summary = run_combat_rounds(seed=7, rounds=2, max_steps=12, min_steps=4)

        self.assertEqual(len(logs), 2)
        self.assertEqual(summary["runner"], "RoundCombatRunner")
        self.assertEqual(summary["rounds"], 2)
        self.assertLessEqual(summary["avg_step_count"], 12)
        self.assertTrue(verify_hash_chain(logs))

        first = logs[0]
        self.assertEqual(first["runner"], "RoundCombatRunner")
        self.assertGreaterEqual(first["step_count"], 1)
        self.assertLessEqual(first["step_count"], 12)
        self.assertEqual(len(first["combat_steps"]), first["step_count"])
        self.assertIn(first["termination_reason"], summary["terminations"])
        self.assertIn("score", first)
        self.assertIn("red_step_action_counts", first)
        self.assertIn("blue_step_action_counts", first)
        self.assertIn("combat_mutation_log", first)
        self.assertIn("observe_policy_gate", first)
        self.assertIn("observe_policy_gate", first["combat_steps"][0])
        self.assertEqual(first["observe_policy_gate"]["scope"], "external_observe_only")
        self.assertTrue(first["combat_mutation_log"]["changed_paths"])
        self.assertNotIn("no_contract_mutation_path_changed", first["causal_consistency"]["violations"])
        self.assertEqual(summary["causal_failure_count"], 0)

        red_actions = {step["red_action"] for entry in logs for step in entry["combat_steps"]}
        blue_actions = {step["blue_action"] for entry in logs for step in entry["combat_steps"]}
        self.assertIn("PROBE_BOUNDARY", red_actions)
        self.assertTrue(blue_actions.intersection({"WAIT", "PASSIVE_MONITOR", "INSPECT_INTERNAL"}))

    def test_combat_runner_rejects_invalid_sizes(self):
        with self.assertRaises(ValueError):
            RoundCombatRunner(rounds=0)
        with self.assertRaises(ValueError):
            RoundCombatRunner(max_steps=0)
        with self.assertRaises(ValueError):
            RoundCombatRunner(max_steps=3, min_steps=4)

    def test_combat_runner_resets_availability_per_round_episode(self):
        logs, summary = run_combat_rounds(
            seed=7,
            rounds=3,
            max_steps=10,
            min_steps=4,
            scenario="low_trust_start",
        )

        resets = [entry["availability_recovery"] for entry in logs]
        self.assertEqual(summary["episode_budget_reset_count"], 3)
        self.assertTrue(all(reset["algorithm"] == "round_episode_budget_reset_v1" for reset in resets))
        self.assertTrue(all(reset["availability_after"] == 0.70 for reset in resets))
        self.assertTrue(all(reset["trust_after"] == 0.58 for reset in resets))
        self.assertEqual(summary["total_availability_recovery"], 0.0)

    def test_blue_step_planner_preserves_low_availability(self):
        threat = Threat("command", 0.86, ("ACK_TIMING_ANOMALY",), ("ack delay",))
        memory = CombatStepMemory(blue_defense_cost_total=0.24)

        action = _plan_blue_step(
            step_number=5,
            suspicion=0.86,
            candidate_threats=[threat],
            memory=memory,
            availability=0.16,
            trust_budget=0.40,
        )

        self.assertEqual(action, "INSPECT_INTERNAL")

    def test_blue_step_planner_allows_critical_defense_even_when_low(self):
        threat = Threat("command", 0.98, ("ACK_TIMING_ANOMALY",), ("ack delay",))
        memory = CombatStepMemory(blue_defense_cost_total=0.24)

        action = _plan_blue_step(
            step_number=5,
            suspicion=0.98,
            candidate_threats=[threat],
            memory=memory,
            availability=0.16,
            trust_budget=0.40,
        )

        self.assertEqual(action, "DEFEND")


if __name__ == "__main__":
    unittest.main()
