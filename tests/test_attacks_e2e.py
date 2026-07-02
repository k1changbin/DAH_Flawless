import unittest

from dah_flawless.environment.simulator import run_simulation


class AttackE2ETests(unittest.TestCase):
    def test_three_core_attacks_have_detection_and_score_evidence(self):
        logs, summary = run_simulation(seed=42, rounds=3)

        self.assertEqual(
            [entry["attack"]["name"] for entry in logs],
            ["PRIORITY_POISONING", "TELEMETRY_FDI", "TIME_DESYNC_REPLAY"],
        )
        self.assertEqual(summary["rounds"], 3)
        for entry in logs:
            self.assertTrue(entry["blue_input_redacted"])
            self.assertTrue(entry["score"]["attack_success"], entry)
            self.assertTrue(entry["score"]["detection_success"], entry)
            self.assertIn(entry["score"]["winner"], {"BLUE", "BLUE_RECOVERY"})


if __name__ == "__main__":
    unittest.main()
