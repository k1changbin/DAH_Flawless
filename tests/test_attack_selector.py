import unittest

from dah_flawless.attacks.catalog import realistic_attacks
from dah_flawless.attacks.selector import build_tactic, score_attack_candidates, score_tactic_candidates
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.situation_tagger import derive_tag_details


class AttackSelectorTests(unittest.TestCase):
    def test_attack_selector_scores_candidates_from_tag_confidence(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))
        weights = {attack.name: attack.weight for attack in realistic_attacks()}

        candidates = score_attack_candidates(realistic_attacks(), weights, details)

        self.assertEqual(candidates[0]["attack"], "TIME_DESYNC_REPLAY")
        self.assertIn("SEQUENCE_VISIBLE", candidates[0]["matched_tags"])
        self.assertGreater(candidates[0]["score"], 0)

    def test_baseline_time_desync_prefers_replay_tactic(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        tactic = build_tactic("TIME_DESYNC_REPLAY", False, details, telemetry_probe_delta=24)

        self.assertEqual(tactic["strategy"], "replay")
        self.assertIn("REPLAY_WINDOW_OPEN", tactic["matched_tags"])
        self.assertTrue(tactic["candidate_scores"])

    def test_ack_anomaly_prefers_ack_confusion_tactic(self):
        state = create_baseline_state(seed=1)
        obs = state["blue_observed"]
        obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"] - 2
        obs["comms"]["ack_delay_ms"] = 950
        details = derive_tag_details(redact_state(state), make_history(state))

        tactic = build_tactic("TIME_DESYNC_REPLAY", False, details, telemetry_probe_delta=24)

        self.assertEqual(tactic["strategy"], "ack_confusion")
        self.assertIn("ACK_TIMING_ANOMALY", tactic["matched_tags"])

    def test_tactic_score_table_keeps_all_time_desync_options_visible(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        scores = score_tactic_candidates("TIME_DESYNC_REPLAY", details)
        strategies = {candidate["strategy"] for candidate in scores}

        self.assertGreaterEqual(len(scores), 5)
        self.assertEqual(
            strategies,
            {"replay", "delay", "selective_drop", "ack_confusion", "metadata_poisoning"},
        )

    def test_simulation_logs_attack_selector_score_tables(self):
        logs, _ = run_simulation(seed=42, rounds=3)
        red_choice = logs[2]["decision_log"][0]

        self.assertIn("attack_candidate_scores", red_choice["after"])
        self.assertIn("candidate_scores", red_choice["after"]["tactic"])
        self.assertEqual(red_choice["after"]["tactic"]["selector"], "tag_scored_tactic_policy")


if __name__ == "__main__":
    unittest.main()
