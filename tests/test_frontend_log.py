import json
import tempfile
import unittest
from pathlib import Path

from dah_flawless.environment.hash_log import read_jsonl
from dah_flawless.environment.round_combat_runner import run_combat_rounds
from dah_flawless.reporting.frontend_log import FRONTEND_LOG_SCHEMA, build_frontend_combat_log


class FrontendLogTests(unittest.TestCase):
    def test_frontend_log_is_compact_projection_of_training_log(self):
        logs, summary = run_combat_rounds(seed=7, rounds=2, max_steps=12, min_steps=4)

        frontend = build_frontend_combat_log(logs, summary)

        self.assertEqual(frontend["schema"], FRONTEND_LOG_SCHEMA)
        self.assertEqual(frontend["log_type"], "round_combat_frontend_replay")
        self.assertEqual(frontend["source"]["training_log_preserved"], True)
        self.assertEqual(len(frontend["rounds"]), len(logs))

        training_first = logs[0]
        ui_first = frontend["rounds"][0]
        self.assertIn("combat_steps", training_first)
        self.assertNotIn("combat_steps", ui_first)
        self.assertNotIn("decision_log", ui_first)
        self.assertEqual(len(ui_first["timeline"]), training_first["step_count"])
        self.assertIn("winner_side", ui_first["outcome"])
        self.assertIn("winner_detail", ui_first["outcome"])
        self.assertTrue(ui_first["action_runs"])
        self.assertIn("filters", frontend)
        self.assertIn("zero_trust", frontend)
        self.assertIn("avg_policy_decision_correctness", frontend["summary"])
        self.assertIn("zta_decisions", frontend["filters"])
        self.assertIn("zta_policy", ui_first)
        self.assertTrue(ui_first["timeline"][0]["zta"])

    def test_round_combat_runner_can_write_frontend_log_separately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            training_log_path = root / "round_logs.jsonl"
            frontend_log_path = root / "frontend_replay.json"

            run_combat_rounds(
                seed=7,
                rounds=2,
                max_steps=12,
                min_steps=4,
                log_path=training_log_path,
                frontend_log_path=frontend_log_path,
            )

            training_logs = read_jsonl(training_log_path)
            frontend = json.loads(frontend_log_path.read_text(encoding="utf-8"))
            self.assertIn("combat_steps", training_logs[0])
            self.assertEqual(frontend["schema"], FRONTEND_LOG_SCHEMA)
            self.assertEqual(frontend["rounds"][0]["step_count"], training_logs[0]["step_count"])


if __name__ == "__main__":
    unittest.main()
