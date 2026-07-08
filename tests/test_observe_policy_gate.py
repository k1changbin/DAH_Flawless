import unittest

from dah_flawless.blue.observe_policy_gate import evaluate_observe_policy
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.state_factory import create_baseline_state, make_history


class ObservePolicyGateTests(unittest.TestCase):
    def test_baseline_external_observe_remains_authoritative(self):
        state = create_baseline_state(seed=1)
        policy, log = evaluate_observe_policy(redact_state(state), make_history(state), state["capabilities"])

        self.assertEqual(policy["scope"], "external_observe_only")
        self.assertEqual(policy["internal_observe_role"], "trust_anchor")
        self.assertEqual(log["agent"], "ObservePolicyGate")
        self.assertIn(policy["by_domain"]["telemetry"]["decision"], {"ALLOW", "ALLOW_WITH_MONITOR"})
        self.assertGreaterEqual(policy["by_domain"]["telemetry"]["use_weight"], 0.8)

    def test_telemetry_internal_anchor_gap_downgrades_external_use(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["blue_observed"]["telemetry"]["battery_percent"] = 82
        state["blue_observed"]["telemetry"]["motor_status"] = "OK"

        policy, _ = evaluate_observe_policy(redact_state(state), history, state["capabilities"])
        telemetry = policy["by_domain"]["telemetry"]

        self.assertIn(telemetry["decision"], {"DOWNGRADE", "REVALIDATE", "QUARANTINE"})
        self.assertLess(telemetry["use_weight"], 0.8)
        self.assertIn("telemetry_battery_internal_gap", telemetry["reasons"])

    def test_safety_critical_small_telemetry_drift_is_quarantined(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        # Baseline internal anchor is battery=20 and motor=FAULT. A small
        # external upward drift can still make a return-required state look
        # safer than it is, so the gate must restrict authoritative use.
        state["blue_observed"]["telemetry"]["battery_percent"] = 21.4

        policy, _ = evaluate_observe_policy(redact_state(state), history, state["capabilities"])
        telemetry = policy["by_domain"]["telemetry"]

        self.assertEqual(telemetry["decision"], "QUARANTINE")
        self.assertEqual(telemetry["allowed_use"], "detection_only")
        self.assertIn("telemetry_safety_anchor_residual", telemetry["reasons"])

    def test_noisy_command_metadata_revalidates_or_quarantines_command_use(self):
        state = create_baseline_state(seed=1, scenario="c2_metadata_noisy")
        policy, _ = evaluate_observe_policy(redact_state(state), make_history(state), state["capabilities"])
        command = policy["by_domain"]["command"]

        self.assertIn(command["decision"], {"REVALIDATE", "QUARANTINE", "DENY"})
        self.assertLess(command["use_weight"], 0.8)
        self.assertIn("command_auth_invalid", command["reasons"])

    def test_mission_priority_drift_downgrades_authoritative_use(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["blue_observed"]["mission"]["area_priority"]["A"] = 0.84
        state["blue_observed"]["mission"]["area_priority"]["C"] = 0.28
        state["blue_observed"]["mission"]["recommended_area"] = "C"

        policy, _ = evaluate_observe_policy(redact_state(state), history, state["capabilities"])
        mission = policy["by_domain"]["mission"]

        self.assertIn(mission["decision"], {"DOWNGRADE", "REVALIDATE"})
        self.assertLess(mission["use_weight"], 0.8)
        self.assertIn("mission_priority_step_residual", mission["reasons"])
        self.assertIn("mission_recommendation_history_shift", mission["reasons"])


if __name__ == "__main__":
    unittest.main()
