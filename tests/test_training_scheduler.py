import unittest

from dah_flawless.environment.hash_log import verify_hash_chain
from dah_flawless.environment.training_scheduler import TrainingScheduler, run_training_schedule


class TrainingSchedulerTests(unittest.TestCase):
    def test_training_scheduler_runs_alternating_blocks(self):
        logs, summary = run_training_schedule(
            seed=11,
            blue_update_episodes=1,
            red_update_episodes=1,
            eval_episodes=1,
            steps_per_episode=3,
        )

        self.assertEqual(len(logs), 9)
        self.assertEqual(summary["runner"], "TrainingScheduler")
        self.assertEqual(summary["episodes"], 3)
        self.assertEqual(summary["steps_per_episode"], 3)
        self.assertEqual(summary["total_steps"], 9)
        self.assertEqual(
            [block["block"] for block in summary["block_summaries"]],
            ["BLUE_UPDATE", "RED_UPDATE", "FIXED_EVAL"],
        )
        self.assertTrue(verify_hash_chain(logs))

        self.assertEqual([entry["episode"] for entry in logs[:3]], [1, 1, 1])
        self.assertEqual([entry["block"] for entry in logs[:3]], ["BLUE_UPDATE"] * 3)
        self.assertEqual([entry["global_step"] for entry in logs], list(range(1, 10)))

    def test_scheduler_freezes_inactive_policy_side(self):
        _, summary = run_training_schedule(
            seed=5,
            blue_update_episodes=1,
            red_update_episodes=1,
            eval_episodes=1,
            steps_per_episode=3,
            blue_readiness_gate_enabled=False,
        )
        blue_block, red_block, eval_block = summary["block_summaries"]

        self.assertEqual(blue_block["red_policy_start"], blue_block["red_policy_end"])
        self.assertNotEqual(blue_block["blue_policy_start"], blue_block["blue_policy_end"])
        self.assertNotEqual(red_block["red_policy_start"], red_block["red_policy_end"])
        self.assertEqual(red_block["blue_policy_start"], red_block["blue_policy_end"])
        self.assertEqual(eval_block["red_policy_start"], eval_block["red_policy_end"])
        self.assertEqual(eval_block["blue_policy_start"], eval_block["blue_policy_end"])

    def test_readiness_gate_blocks_red_updates_until_blue_is_ready(self):
        logs, summary = run_training_schedule(
            seed=5,
            blue_update_episodes=1,
            red_update_episodes=1,
            eval_episodes=0,
            steps_per_episode=3,
        )
        red_block = summary["block_summaries"][1]

        self.assertGreater(red_block["effective_update_counts"]["red_updates_blocked_by_readiness"], 0)
        self.assertEqual(red_block["red_policy_start"], red_block["red_policy_end"])
        self.assertTrue(all(not entry["update_mode"]["red_update_enabled"] for entry in logs[3:]))
        self.assertTrue(all(entry["update_mode"]["blue_update_enabled"] for entry in logs[3:]))
        self.assertEqual(
            logs[3]["update_mode"]["blue_readiness_gate"]["reason"],
            "insufficient_blue_training_samples",
        )

    def test_scheduler_rejects_empty_schedule(self):
        with self.assertRaises(ValueError):
            TrainingScheduler(blue_update_episodes=0, red_update_episodes=0, eval_episodes=0)


if __name__ == "__main__":
    unittest.main()
