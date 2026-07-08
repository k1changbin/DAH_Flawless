"""Blue per-episode availability budget tests."""

import unittest

from dah_flawless.environment.simulator import _advance_normal_state, run_simulation
from dah_flawless.environment.state_factory import create_baseline_state


class BlueAvailabilityRecoveryTests(unittest.TestCase):
    def test_round_start_resets_budget_to_episode_initial_baseline(self):
        base_state = create_baseline_state(seed=1, scenario="low_trust_start")
        base_state["mission"]["availability"] = 0.12
        base_state["mission"]["trust_budget"] = 0.18
        base_state["defense_runtime"]["active_defenses"] = [
            {"action": "HOLD_COMMAND", "availability_cost": 0.20, "status": "DONE"}
        ]
        base_state["defense_runtime"]["pending_defenses"] = [
            {"action": "REQUEST_REVALIDATION", "availability_cost": 0.04, "status": "PENDING"}
        ]

        next_round = _advance_normal_state(base_state, round_number=2)
        reset = next_round["defense_runtime"]["availability_recovery"]

        self.assertEqual(reset["algorithm"], "round_episode_budget_reset_v1")
        self.assertEqual(next_round["mission"]["availability"], 0.70)
        self.assertEqual(next_round["mission"]["trust_budget"], 0.58)
        self.assertEqual(next_round["defense_runtime"]["active_defenses"], [])
        self.assertEqual(next_round["defense_runtime"]["pending_defenses"], [])
        self.assertEqual(reset["cleared_active_defense_count"], 1)
        self.assertEqual(reset["cleared_pending_defense_count"], 1)
        self.assertEqual(reset["availability_recovery_applied"], 0.0)
        self.assertEqual(reset["trust_recovery_applied"], 0.0)
        self.assertGreater(reset["availability_reset_delta"], 0.0)

    def test_budget_resets_are_summarized_without_cross_round_recovery(self):
        logs, summary = run_simulation(seed=42, rounds=6, scenario="degraded_start")

        reset_logs = [entry["availability_recovery"] for entry in logs if entry.get("availability_recovery")]
        self.assertEqual(len(reset_logs), 6)
        self.assertTrue(all(entry["algorithm"] == "round_episode_budget_reset_v1" for entry in reset_logs))
        self.assertTrue(all(entry["availability_after"] == 0.55 for entry in reset_logs))
        self.assertEqual(summary["episode_budget_reset_count"], 6)
        self.assertEqual(summary["total_availability_recovery"], 0.0)
        self.assertEqual(summary["maintenance_recovery_count"], 0)


if __name__ == "__main__":
    unittest.main()
