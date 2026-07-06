import unittest

from dah_flawless.environment.hash_log import verify_hash_chain
from dah_flawless.environment.round_combat_runner import RoundCombatRunner, run_combat_rounds


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


if __name__ == "__main__":
    unittest.main()
