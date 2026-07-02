import unittest

from dah_flawless.environment.simulator import run_simulation


class SeedReproducibilityTests(unittest.TestCase):
    def test_same_seed_produces_same_logs(self):
        logs_a, summary_a = run_simulation(seed=7, rounds=3)
        logs_b, summary_b = run_simulation(seed=7, rounds=3)

        self.assertEqual(logs_a, logs_b)
        self.assertEqual(summary_a, summary_b)


if __name__ == "__main__":
    unittest.main()
