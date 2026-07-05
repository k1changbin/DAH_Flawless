import unittest

from dah_flawless.environment.episode_runner import EpisodeRunner, run_episodes
from dah_flawless.environment.hash_log import verify_hash_chain


class EpisodeRunnerTests(unittest.TestCase):
    def test_episode_runner_groups_steps_and_preserves_hash_chain(self):
        logs, summary = run_episodes(seed=7, episodes=2, steps_per_episode=3)

        self.assertEqual(len(logs), 6)
        self.assertEqual(summary["runner"], "EpisodeRunner")
        self.assertEqual(summary["episodes"], 2)
        self.assertEqual(summary["steps_per_episode"], 3)
        self.assertEqual(summary["total_steps"], 6)
        self.assertEqual(len(summary["episode_summaries"]), 2)
        self.assertTrue(verify_hash_chain(logs))

        first_episode = logs[:3]
        second_episode = logs[3:]
        self.assertEqual([entry["episode"] for entry in first_episode], [1, 1, 1])
        self.assertEqual([entry["episode_step"] for entry in first_episode], [1, 2, 3])
        self.assertEqual([entry["global_step"] for entry in first_episode], [1, 2, 3])
        self.assertEqual([entry["episode"] for entry in second_episode], [2, 2, 2])
        self.assertEqual([entry["episode_seed"] for entry in second_episode], [8, 8, 8])
        self.assertEqual([entry["episode_step"] for entry in second_episode], [1, 2, 3])
        self.assertEqual([entry["global_step"] for entry in second_episode], [4, 5, 6])

    def test_episode_runner_rejects_non_positive_sizes(self):
        with self.assertRaises(ValueError):
            EpisodeRunner(episodes=0)
        with self.assertRaises(ValueError):
            EpisodeRunner(steps_per_episode=0)


if __name__ == "__main__":
    unittest.main()
