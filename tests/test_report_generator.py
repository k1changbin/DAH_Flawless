import json
import tempfile
import unittest
from pathlib import Path

from dah_flawless.environment.holdout_evaluator import run_holdout_evaluation
from dah_flawless.environment.training_scheduler import run_training_schedule
from dah_flawless.reporting.report_generator import (
    build_training_holdout_report,
    render_markdown_report,
    write_training_holdout_report,
)


class ReportGeneratorTests(unittest.TestCase):
    def test_report_summarizes_training_and_holdout(self):
        training_logs, training_summary = run_training_schedule(
            seed=42,
            blue_update_episodes=1,
            red_update_episodes=1,
            eval_episodes=0,
            steps_per_episode=2,
        )
        holdout_logs, holdout_summary = run_holdout_evaluation(
            red_policy_state=training_summary["final_red_policy_state"],
            blue_policy_state=training_summary["final_blue_policy_state"],
            seeds=(142,),
            scenarios=("clean_start", "satcom_delay"),
            steps_per_case=1,
        )

        report = build_training_holdout_report(
            training_summary=training_summary,
            holdout_summary=holdout_summary,
            training_logs=training_logs,
            holdout_logs=holdout_logs,
        )
        markdown = render_markdown_report(report)

        self.assertEqual(report["report_type"], "training_holdout_report")
        self.assertTrue(report["training"]["overview"]["hash_chain_ok"])
        self.assertTrue(report["holdout"]["overview"]["hash_chain_ok"])
        self.assertEqual(len(report["holdout"]["scenario_rows"]), 2)
        self.assertIn("Training Overview", markdown)
        self.assertIn("Holdout Scenario Results", markdown)
        self.assertIn("satcom_delay", markdown)

    def test_report_writer_outputs_markdown_and_json(self):
        training_logs, training_summary = run_training_schedule(
            seed=7,
            blue_update_episodes=1,
            red_update_episodes=0,
            eval_episodes=0,
            steps_per_episode=2,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            markdown_path = Path(tmpdir) / "report.md"
            json_path = Path(tmpdir) / "report.json"
            report = write_training_holdout_report(
                training_summary=training_summary,
                training_logs=training_logs,
                markdown_path=markdown_path,
                json_path=json_path,
            )

            self.assertTrue(markdown_path.exists())
            self.assertTrue(json_path.exists())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["report_type"], report["report_type"])
            self.assertIn("Policy Delta", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
