import unittest

from dah_flawless.environment.simulator import run_simulation


class CausalConsistencyTests(unittest.TestCase):
    def test_simulation_logs_causal_consistency(self):
        logs, summary = run_simulation(seed=42, rounds=3)

        self.assertIn("avg_causal_consistency", summary)
        self.assertEqual(summary["causal_failure_count"], 0)
        for entry in logs:
            report = entry["causal_consistency"]
            self.assertIn(report["status"], {"PASS", "WARN"})
            self.assertTrue(report["contract_supported"])
            self.assertTrue(report["matched_mutation_paths"])
            self.assertIn("CausalConsistencyMonitor", [item["agent"] for item in entry["decision_log"]])


if __name__ == "__main__":
    unittest.main()
