import unittest

from dah_flawless.blue.defense_planner import apply_defense_actions, plan_defense
from dah_flawless.blue.feedback_learner import default_blue_policy_state
from dah_flawless.blue.threat_detection import detect_threats
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.observation import refresh_internal_observe_from_truth, refresh_telemetry_channels
from dah_flawless.schemas import DefenseAction, Threat


class BlueGoalConsistencyTests(unittest.TestCase):
    def test_baseline_telemetry_channel_checks_pass(self):
        state = create_baseline_state(seed=1)

        tags, threats, log = detect_threats(redact_state(state), make_history(state), state["capabilities"])
        checks = log["after"]["telemetry_channel_checks"]

        self.assertEqual(checks["failed_checks"], [])
        self.assertNotIn("TELEMETRY_INTERNAL_TX_DISAGREE", tags)
        self.assertNotIn("TELEMETRY_TX_RX_DISAGREE", tags)
        self.assertFalse(any(threat.target == "telemetry" for threat in threats))

    def test_ack_causal_confusion_becomes_goal_effect_threat(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        obs = state["blue_observed"]
        obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"] - 2
        obs["c2_message"]["ack"]["visible"] = True
        obs["comms"]["ack_visible"] = True
        obs["comms"]["ack_delay_ms"] = 950

        _, threats, log = detect_threats(redact_state(state), history, state["capabilities"])
        command_threat = next(threat for threat in threats if threat.target == "command")
        actions, _ = plan_defense(threats, [], state["mission"], state["defense_runtime"])

        self.assertIn("EFFECT_ACK_CAUSAL_CONFUSION", command_threat.tags)
        self.assertTrue(log["after"]["effect_hypotheses"])
        self.assertIn("HOLD_COMMAND", [action.action for action in actions])
        self.assertIn("blue_observed.c2_message.ack", [action.target for action in actions])

    def test_internal_external_telemetry_disagreement_is_detected(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        obs = state["blue_observed"]
        obs["telemetry"]["battery_percent"] = 45
        obs["telemetry"]["motor_status"] = "OK"

        _, threats, _ = detect_threats(redact_state(state), history, state["capabilities"])
        telemetry_threat = next(threat for threat in threats if threat.target == "telemetry")

        self.assertIn("EFFECT_TELEMETRY_TRUST_EROSION", telemetry_threat.tags)
        self.assertIn("INTERNAL_EXTERNAL_TELEMETRY_DISAGREE", telemetry_threat.tags)

    def test_telemetry_channel_checks_split_tx_rx_command_and_freshness(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        obs = state["blue_observed"]
        obs["telemetry"]["battery_percent"] = 45
        obs["telemetry"]["motor_status"] = "OK"
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"] - 2
        obs["comms"]["ack_delay_ms"] = 950
        obs["comms"]["latency_ms"] = 540
        obs["comms"]["packet_interval_jitter_ms"] = 460
        refresh_telemetry_channels(obs)

        tags, threats, log = detect_threats(redact_state(state), history, state["capabilities"])
        checks = log["after"]["telemetry_channel_checks"]["checks"]
        telemetry_threat = next(threat for threat in threats if threat.target == "telemetry")

        self.assertEqual(checks["internal_vs_tx"]["status"], "PASS")
        self.assertEqual(checks["tx_vs_rx"]["status"], "FAIL")
        self.assertEqual(checks["rx_vs_command"]["status"], "FAIL")
        self.assertIn(checks["freshness"]["status"], {"WARN", "FAIL"})
        self.assertIn("TELEMETRY_TX_RX_DISAGREE", tags)
        self.assertIn("TELEMETRY_RX_COMMAND_INCONSISTENT", tags)
        self.assertIn("TELEMETRY_FRESHNESS_RISK", tags)
        self.assertIn("TELEMETRY_TX_RX_DISAGREE", telemetry_threat.tags)
        self.assertIn("TELEMETRY_RX_COMMAND_INCONSISTENT", telemetry_threat.tags)

    def test_internal_vs_tx_projection_disagreement_is_separate_check(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["blue_observed"]["telemetry_channels"]["asset_tx_mirror"]["battery_percent"] = 35

        tags, threats, log = detect_threats(redact_state(state), history, state["capabilities"])
        checks = log["after"]["telemetry_channel_checks"]["checks"]
        telemetry_threat = next(threat for threat in threats if threat.target == "telemetry")

        self.assertEqual(checks["internal_vs_tx"]["status"], "FAIL")
        self.assertEqual(checks["tx_vs_rx"]["status"], "FAIL")
        self.assertIn("TELEMETRY_INTERNAL_TX_DISAGREE", tags)
        self.assertIn("TELEMETRY_INTERNAL_TX_DISAGREE", telemetry_threat.tags)

    def test_safety_critical_telemetry_residual_becomes_threat(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["blue_observed"]["telemetry"]["battery_percent"] = 21.4

        tags, threats, _ = detect_threats(redact_state(state), history, state["capabilities"])
        telemetry_threat = next(threat for threat in threats if threat.target == "telemetry")

        self.assertIn("TELEMETRY_SAFETY_ANCHOR_RESIDUAL", tags)
        self.assertIn("EFFECT_TELEMETRY_TRUST_EROSION", telemetry_threat.tags)
        self.assertIn("TELEMETRY_SAFETY_ANCHOR_RESIDUAL", telemetry_threat.tags)
        self.assertGreaterEqual(telemetry_threat.confidence, 0.72)

    def test_channel_suppression_selects_channel_timing_reset(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        obs = state["blue_observed"]
        obs["comms"]["packet_loss"] = 0.16
        obs["comms"]["latency_ms"] = 720
        obs["comms"]["packet_interval_jitter_ms"] = 460
        obs["comms"]["heartbeat_gap_ms"] = 3200

        _, threats, _ = detect_threats(redact_state(state), history, state["capabilities"])
        actions, _ = plan_defense(threats, [], state["mission"], state["defense_runtime"])
        defended = apply_defense_actions(state, actions, history, threats, state["capabilities"])

        self.assertIn("RESET_CHANNEL_TIMING", [action.action for action in actions])
        self.assertEqual(defended["blue_observed"]["comms"]["heartbeat_gap_ms"], 0)
        self.assertEqual(defended["blue_observed"]["comms"]["packet_interval_jitter_ms"], 18)

    def test_recommended_area_conflict_becomes_wrong_target_effect(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["blue_observed"]["mission"]["recommended_area"] = "C"

        _, threats, log = detect_threats(redact_state(state), history, state["capabilities"])
        mission_threat = next(threat for threat in threats if threat.target == "mission")

        self.assertIn("EFFECT_WRONG_TARGET_SELECTION", mission_threat.tags)
        hypothesis = next(
            item
            for item in log["after"]["effect_hypotheses"]
            if item["goal_id"] == "WRONG_TARGET_SELECTION"
        )
        self.assertIn("recommended_conflicts_with_observed_top=True", hypothesis["evidence"])

    def test_hold_command_restores_current_internal_c2_anchor(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["world"]["command"]["expected_sequence_number"] += 1
        state["world"]["time"]["true_timestamp"] += 30
        refresh_internal_observe_from_truth(state)
        state["blue_observed"]["c2_message"]["sequence_number"] -= 5
        state["blue_observed"]["c2_message"]["command"] = "CONTINUE_MISSION"
        state["blue_observed"]["time"]["received_timestamp"] -= 120
        actions = [
            DefenseAction("HOLD_COMMAND", "blue_observed.c2_message.command", 3, 1, 0.04),
        ]

        defended = apply_defense_actions(state, actions, history, [], state["capabilities"])

        self.assertEqual(
            defended["blue_observed"]["c2_message"]["sequence_number"],
            state["world"]["command"]["expected_sequence_number"],
        )
        self.assertEqual(
            defended["blue_observed"]["c2_message"]["command"],
            state["world"]["command"]["last_valid_command"],
        )
        self.assertEqual(
            defended["blue_observed"]["time"]["received_timestamp"],
            state["world"]["time"]["true_timestamp"],
        )

    def test_effect_threshold_can_confirm_specific_defense(self):
        state = create_baseline_state(seed=1)
        policy = default_blue_policy_state()
        policy["effect_threshold"]["EFFECT_ACK_CAUSAL_CONFUSION"] = 0.60
        state["defense_runtime"].update(policy)
        threats = [
            Threat(
                "command",
                0.65,
                ("EFFECT_ACK_CAUSAL_CONFUSION", "ACK_CAUSALITY_BREAK"),
                ("ack gap",),
            )
        ]

        actions, _ = plan_defense(threats, [], state["mission"], state["defense_runtime"])

        self.assertIn("HOLD_COMMAND", [action.action for action in actions])
        self.assertIn("blue_observed.c2_message.ack", [action.target for action in actions])

    def test_simulation_logs_goal_effect_hypotheses(self):
        logs, _ = run_simulation(seed=42, rounds=1)
        threat_log = next(item for item in logs[0]["decision_log"] if item["agent"] == "ThreatDetectionAgent")

        self.assertIn("effect_hypotheses", threat_log["after"])
        self.assertTrue(threat_log["after"]["effect_hypotheses"])


if __name__ == "__main__":
    unittest.main()
