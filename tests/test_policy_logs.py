import unittest

from dah_flawless.environment.simulator import run_simulation


class PolicyLogTests(unittest.TestCase):
    def test_red_policy_state_has_weights_and_stats(self):
        logs, _ = run_simulation(seed=42, rounds=4)
        policy = logs[-1]["red_policy_state"]

        self.assertIn("attack_weights", policy)
        self.assertIn("attack_stats", policy)
        self.assertIn("telemetry_probe_delta", policy)
        self.assertGreaterEqual(policy["attack_stats"]["PRIORITY_POISONING"]["tries"], 1)

    def test_red_choice_log_has_candidate_scores_after_scripted_rounds(self):
        logs, _ = run_simulation(seed=42, rounds=4)
        red_choice = logs[-1]["decision_log"][0]

        self.assertEqual(red_choice["agent"], "RedAgent")
        self.assertIn("candidate_scores", red_choice["after"])
        self.assertIn(logs[-1]["attack"]["name"], red_choice["after"]["candidate_scores"])

    def test_blue_policy_state_records_confirmation_reason(self):
        logs, _ = run_simulation(seed=42, rounds=1, scenario="degraded_start")
        policy = logs[0]["blue_policy_state"]

        self.assertIn("threat_decisions", policy)
        self.assertEqual(policy["threat_decisions"][0]["reason"], "high_confidence")
        self.assertIn("availability_after_estimate", policy)

    def test_degraded_adaptive_produces_mixed_outcomes(self):
        logs, summary = run_simulation(seed=42, rounds=5, scenario="degraded_start", stealth_mode="adaptive")
        winners = {entry["score"]["winner"] for entry in logs}

        self.assertIn("RED_BREACH", winners)
        self.assertIn("RED_ATTRITION", winners)
        self.assertLess(summary["detection_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
