import unittest
from copy import deepcopy

from dah_flawless.blue.zero_trust_gate import (
    GATED_DOMAINS,
    evaluate_zero_trust,
    summarize_zta,
    zta_action_candidates,
)
from dah_flawless.blue.defense_planner import plan_defense
from dah_flawless.environment.round_combat_runner import run_combat_rounds
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.observation import sync_external_observe_from_flat
from dah_flawless.schemas import Threat


def _clean_inputs(scenario: str = "clean_start"):
    state = create_baseline_state(42, scenario)
    history = make_history(state)
    return (
        state["blue_observed"],
        history,
        state["capabilities"],
        state["defense_runtime"]["domain_trust"],
        state["mission"],
    )


def _by_domain(decisions):
    return {item.domain: item for item in decisions}


class ZeroTrustGateTests(unittest.TestCase):
    def test_clean_state_allows_every_domain(self):
        blue_observed, history, capabilities, domain_trust, mission = _clean_inputs()
        decisions, log = evaluate_zero_trust(blue_observed, history, capabilities, domain_trust, mission, [])

        self.assertEqual({item.domain for item in decisions}, set(GATED_DOMAINS))
        for item in decisions:
            self.assertEqual(item.decision, "ALLOW")
            self.assertFalse(item.restrictive)
            self.assertEqual(item.allowed_use, "operational")
        self.assertEqual(log["agent"], "ZeroTrustObserveGate")

    def test_telemetry_fdi_gap_restricts_only_telemetry(self):
        blue_observed, history, capabilities, domain_trust, mission = _clean_inputs()
        spoofed = deepcopy(blue_observed)
        spoofed["telemetry"]["battery_percent"] = 88  # internal anchor stays at 20
        spoofed["telemetry"]["motor_status"] = "OK"
        sync_external_observe_from_flat(spoofed)
        threats = [Threat("telemetry", 0.85, ("EFFECT_TELEMETRY_TRUST_EROSION",), ("gap",))]

        decisions = _by_domain(
            evaluate_zero_trust(spoofed, history, capabilities, domain_trust, mission, threats)[0]
        )
        self.assertTrue(decisions["telemetry"].restrictive)
        self.assertIn("internal_external_telemetry_gap", decisions["telemetry"].reasons)
        self.assertEqual(decisions["command"].decision, "ALLOW")
        self.assertEqual(decisions["mission"].decision, "ALLOW")

    def test_command_replay_drives_command_restriction(self):
        blue_observed, history, capabilities, domain_trust, mission = _clean_inputs()
        spoofed = deepcopy(blue_observed)
        spoofed["c2_message"]["auth_valid"] = False
        spoofed["c2_message"]["checksum_valid"] = False
        spoofed["c2_message"]["sequence_number"] = history["last_sequence_number"] - 12
        spoofed["c2_message"]["ack"]["sequence_number"] = spoofed["c2_message"]["sequence_number"] - 4
        sync_external_observe_from_flat(spoofed)
        threats = [Threat("command", 0.8, ("EFFECT_COMMAND_STALE_ACCEPTANCE",), ("replay",))]

        decisions = _by_domain(
            evaluate_zero_trust(spoofed, history, capabilities, domain_trust, mission, threats)[0]
        )
        self.assertTrue(decisions["command"].restrictive)
        self.assertIn("sequence_regression", decisions["command"].reasons)
        self.assertIn("auth_invalid", decisions["command"].reasons)
        self.assertLess(decisions["command"].trust_score, 0.45)

    def test_lower_domain_trust_pushes_score_down(self):
        blue_observed, history, capabilities, _, mission = _clean_inputs()
        high = evaluate_zero_trust(blue_observed, history, capabilities, {"command": 1.0}, mission, [])[0]
        low = evaluate_zero_trust(blue_observed, history, capabilities, {"command": 0.0}, mission, [])[0]
        high_cmd = _by_domain(high)["command"].trust_score
        low_cmd = _by_domain(low)["command"].trust_score
        self.assertGreater(high_cmd, low_cmd)

    def test_action_candidates_only_for_restrictive_decisions(self):
        blue_observed, history, capabilities, domain_trust, mission = _clean_inputs()
        spoofed = deepcopy(blue_observed)
        spoofed["c2_message"]["auth_valid"] = False
        spoofed["c2_message"]["sequence_number"] = history["last_sequence_number"] - 30
        sync_external_observe_from_flat(spoofed)
        threats = [Threat("command", 0.9, ("EFFECT_COMMAND_STALE_ACCEPTANCE",), ("replay",))]

        decisions = evaluate_zero_trust(spoofed, history, capabilities, domain_trust, mission, threats)[0]
        candidates = zta_action_candidates(decisions)
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertEqual(candidate["domain"], "command")
            self.assertIn(candidate["action"], {"HOLD_COMMAND", "REQUEST_REVALIDATION"})

    def test_defense_planner_accepts_zta_policy_only_candidate(self):
        blue_observed, history, capabilities, domain_trust, mission = _clean_inputs()
        spoofed = deepcopy(blue_observed)
        spoofed["c2_message"]["auth_valid"] = False
        spoofed["c2_message"]["checksum_valid"] = False
        spoofed["c2_message"]["sequence_number"] = history["last_sequence_number"] - 20
        sync_external_observe_from_flat(spoofed)

        decisions = evaluate_zero_trust(spoofed, history, capabilities, domain_trust, mission, [])[0]
        actions, log = plan_defense([], [], mission, {"domain_trust": domain_trust}, decisions)

        self.assertTrue(actions)
        self.assertIn(actions[0].action, {"OBSERVE_DOMAIN", "HOLD_COMMAND", "REQUEST_REVALIDATION"})
        self.assertEqual(log["before"]["zta_policy_candidates"][0]["domain"], "command")
        self.assertEqual(log["after"]["zta_policy_actions"][0]["action"], actions[0].action)

    def test_summarize_rewards_restricting_attacked_domain(self):
        blue_observed, history, capabilities, domain_trust, mission = _clean_inputs()
        spoofed = deepcopy(blue_observed)
        spoofed["telemetry"]["battery_percent"] = 90
        sync_external_observe_from_flat(spoofed)
        threats = [Threat("telemetry", 0.85, ("EFFECT_TELEMETRY_TRUST_EROSION",), ("gap",))]
        decisions = evaluate_zero_trust(spoofed, history, capabilities, domain_trust, mission, threats)[0]

        summary = summarize_zta([decisions], "telemetry")
        self.assertEqual(summary["policy_decision_correctness"], 1.0)
        self.assertTrue(summary["per_domain"]["telemetry"]["restricted"])
        self.assertFalse(summary["per_domain"]["command"]["restricted"])

    def test_runner_emits_zta_policy_and_step_decisions(self):
        logs, summary = run_combat_rounds(seed=42, rounds=3, max_steps=16, min_steps=4)
        for entry in logs:
            policy = entry["zta_policy"]
            self.assertIn("policy_decision_correctness", policy)
            self.assertEqual(policy["attack_target_domain"], entry["attack"]["target_domain"])
            first_step = entry["combat_steps"][0]
            self.assertEqual(
                {item["domain"] for item in first_step["zta_decisions"]}, set(GATED_DOMAINS)
            )

    def test_run_simulation_emits_zta_policy_and_score_evidence(self):
        logs, summary = run_simulation(seed=42, rounds=1)
        entry = logs[0]

        self.assertIn("zta_policy", entry)
        self.assertIn("avg_policy_decision_correctness", summary)
        self.assertEqual({item["domain"] for item in entry["zta_decisions"]}, set(GATED_DOMAINS))
        self.assertEqual(
            {item["domain"] for item in entry["score"]["evidence"]["zta_policy_decisions"]},
            set(GATED_DOMAINS),
        )


if __name__ == "__main__":
    unittest.main()
