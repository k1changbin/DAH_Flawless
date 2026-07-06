import json
import tempfile
import unittest
from pathlib import Path

from dah_flawless.environment.hash_log import verify_hash_chain
from dah_flawless.environment.log_memory import compress_log_memory
from dah_flawless.environment.simulator import run_simulation


class LogMemoryTests(unittest.TestCase):
    def test_run_simulation_compacts_planning_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = Path(tmpdir) / "memory.json"
            logs, summary = run_simulation(
                seed=42,
                rounds=7,
                memory_compaction_interval=3,
                memory_proxy_size=4,
                memory_path=memory_path,
            )

            self.assertEqual(len(logs), 7)
            self.assertTrue(verify_hash_chain(logs))
            self.assertEqual(summary["log_memory"]["compaction_count"], 2)
            self.assertEqual(summary["log_memory"]["proxy_context_log_count"], 4)
            self.assertEqual(summary["log_memory"]["active_context_log_count"], 1)
            self.assertEqual([entry["round"] for entry in logs if "log_memory_event" in entry], [3, 6])

            store = json.loads(memory_path.read_text(encoding="utf-8"))
            self.assertEqual(store["memory_store_type"], "rolling_log_memory_store")
            self.assertEqual(len(store["snapshots"]), 2)
            self.assertEqual(store["latest"]["proxy_log_count"], 4)

    def test_compressed_memory_proxy_logs_keep_trends_with_variation(self):
        logs, _ = run_simulation(seed=7, rounds=5)

        memory = compress_log_memory(logs, seed=7, compacted_at_step=5, proxy_size=6)

        self.assertEqual(memory["memory_type"], "rolling_log_memory")
        self.assertEqual(memory["source_log_count"], 5)
        self.assertEqual(len(memory["proxy_logs"]), 6)
        self.assertIn("avg_goal_reward", memory["trend"])
        self.assertTrue(all(proxy["memory_proxy"] for proxy in memory["proxy_logs"]))
        self.assertTrue(all(proxy["score"]["evidence"]["goal_score"]["memory_proxy"] for proxy in memory["proxy_logs"]))

    def test_run_simulation_rejects_invalid_memory_sizes(self):
        with self.assertRaises(ValueError):
            run_simulation(memory_compaction_interval=-1)
        with self.assertRaises(ValueError):
            run_simulation(memory_compaction_interval=3, memory_proxy_size=0)


if __name__ == "__main__":
    unittest.main()
