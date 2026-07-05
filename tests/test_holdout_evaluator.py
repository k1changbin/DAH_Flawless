import unittest

from dah_flawless.environment.hash_log import verify_hash_chain
from dah_flawless.environment.holdout_evaluator import run_holdout_evaluation
from dah_flawless.environment.training_scheduler import run_training_schedule


class HoldoutEvaluatorTests(unittest.TestCase):
    def test_holdout_runs_frozen_policy_across_seed_scenario_grid(self):
        _, training_summary = run_training_schedule(
            seed=42,
            blue_update_episodes=1,
            red_update_episodes=1,
            eval_episodes=0,
            steps_per_episode=3,
        )

        logs, summary = run_holdout_evaluation(
            red_policy_state=training_summary["final_red_policy_state"],
            blue_policy_state=training_summary["final_blue_policy_state"],
            seeds=(142, 143),
            scenarios=("clean_start", "degraded_start"),
            steps_per_case=2,
        )

        self.assertEqual(len(logs), 8)
        self.assertEqual(summary["runner"], "HoldoutEvaluator")
        self.assertEqual(summary["cases"], 4)
        self.assertEqual(summary["total_steps"], 8)
        self.assertFalse(summary["scripted_red_coverage"])
        self.assertEqual(
            summary["update_mode"],
            {"red_update_enabled": False, "blue_update_enabled": False},
        )
        self.assertTrue(verify_hash_chain(logs))
        self.assertEqual([entry["global_step"] for entry in logs], list(range(1, 9)))
        self.assertTrue(all(entry["runner"] == "HoldoutEvaluator" for entry in logs))
        self.assertTrue(all(not entry["update_mode"]["red_update_enabled"] for entry in logs))
        self.assertTrue(all(not entry["update_mode"]["blue_update_enabled"] for entry in logs))
        self.assertTrue(all(entry["decision_log"][0]["reason"] != "scripted_mvp_coverage" for entry in logs))
        self.assertIn("generalization_flags", summary)

    def test_holdout_rejects_unknown_scenario(self):
        with self.assertRaises(ValueError):
            run_holdout_evaluation(
                red_policy_state={},
                blue_policy_state={},
                seeds=(1,),
                scenarios=("unknown",),
                steps_per_case=1,
            )


if __name__ == "__main__":
    unittest.main()
