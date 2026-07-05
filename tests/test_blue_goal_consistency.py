import unittest

from dah_flawless.blue.defense_planner import apply_defense_actions, plan_defense
from dah_flawless.blue.feedback_learner import default_blue_policy_state
from dah_flawless.blue.threat_detection import detect_threats
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.schemas import Threat


class BlueGoalConsistencyTests(unittest.TestCase):
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
