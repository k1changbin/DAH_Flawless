"""Tests for the ported strengths: degraded_start / capability paralysis and
the Stealth Controller (adaptive Red stealth)."""

import unittest

from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.blue.defense_planner import plan_defense
from dah_flawless.blue.invariants import analyze_invariants
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state
from dah_flawless.schemas import Threat


class DegradedScenarioTests(unittest.TestCase):
    def test_degraded_start_lowers_availability_and_capabilities(self):
        state = create_baseline_state(seed=1, scenario="degraded_start")
        self.assertEqual(state["scenario"], "degraded_start")
        self.assertLess(state["mission"]["availability"], 1.0)
        self.assertEqual(state["capabilities"]["cross_check_telemetry"], "DEGRADED")
        self.assertEqual(state["blue_observed"]["navigation"]["gnss_fix_quality"], "DEGRADED")

    def test_clean_start_keeps_full_capabilities(self):
        state = create_baseline_state(seed=1)
        self.assertEqual(state["mission"]["availability"], 1.0)
        self.assertTrue(all(v == "OK" for v in state["capabilities"].values()))

    def test_degraded_capability_lowers_detection_confidence(self):
        tags = ["TELEMETRY_CONFLICT", "BATTERY_MOTOR_INCONSISTENT"]
        ok = analyze_invariants({}, {}, tags, {"cross_check_telemetry": "OK"})
        degraded = analyze_invariants({}, {}, tags, {"cross_check_telemetry": "DEGRADED"})
        self.assertGreater(ok[0].confidence, degraded[0].confidence)


class StealthControllerTests(unittest.TestCase):
    def test_static_stealth_telemetry_is_caught_by_cross_checks(self):
        logs, _ = run_simulation(seed=42, rounds=3, stealth_mode="on")
        telemetry = next(entry for entry in logs if entry["attack"]["name"] == "TELEMETRY_FDI")
        self.assertTrue(telemetry["stealth"])
        self.assertTrue(telemetry["score"]["attack_success"])
        self.assertTrue(telemetry["score"]["detection_success"])
        self.assertIn("BATTERY_ENERGY_IMPOSSIBLE", telemetry["situation_tags"])

    def test_loud_telemetry_is_detected(self):
        logs, _ = run_simulation(seed=42, rounds=3, stealth_mode="off")
        telemetry = next(entry for entry in logs if entry["attack"]["name"] == "TELEMETRY_FDI")
        self.assertFalse(telemetry["stealth"])
        self.assertTrue(telemetry["score"]["detection_success"])

    def test_adaptive_switches_to_stealth_after_detection(self):
        agent = RedAgent(seed=1, stealth_mode="adaptive")
        self.assertFalse(agent._use_stealth("TELEMETRY_FDI"))
        agent.update_weight("TELEMETRY_FDI", detected=True)
        self.assertTrue(agent._use_stealth("TELEMETRY_FDI"))

    def test_adaptive_red_reduces_telemetry_probe_after_detection(self):
        agent = RedAgent(seed=1, stealth_mode="adaptive")
        for _ in range(4):
            agent.update_weight("TELEMETRY_FDI", detected=True)
        _, stealth, tactic, _ = agent.choose_attack(2, {}, [])

        self.assertTrue(stealth)
        self.assertEqual(tactic["strategy"], "boundary_probe")
        self.assertLessEqual(tactic["probe_delta"], 2)


class RecoveryAndStagedDefenseTests(unittest.TestCase):
    def test_availability_recovers_in_long_clean_run(self):
        logs, summary = run_simulation(seed=42, rounds=30)

        self.assertGreater(summary["final_availability"], 0.5)
        self.assertGreater(min(entry["score"]["availability"] for entry in logs), 0.45)
        self.assertLess(summary["winners"].get("RED_ATTRITION", 0), 5)

    def test_weak_telemetry_threat_uses_low_cost_observation(self):
        threat = Threat(
            target="telemetry",
            confidence=0.70,
            tags=("BATTERY_ENERGY_IMPOSSIBLE",),
            evidence=("battery and drain rate disagree",),
        )
        actions, _ = plan_defense(
            [threat],
            [],
            {"availability": 1.0},
            {"domain_trust": {"telemetry": 1.0, "mission": 1.0, "command": 1.0}},
        )

        self.assertEqual([action.action for action in actions], ["OBSERVE_DOMAIN", "REQUEST_REVALIDATION"])
        self.assertLess(sum(action.availability_cost for action in actions), 0.02)

    def test_repeated_telemetry_suspicion_escalates_defense(self):
        threat = Threat(
            target="telemetry",
            confidence=0.70,
            tags=("BATTERY_ENERGY_IMPOSSIBLE",),
            evidence=("battery and drain rate disagree",),
        )
        actions, _ = plan_defense(
            [threat],
            [],
            {"availability": 1.0},
            {"domain_trust": {"telemetry": 0.60, "mission": 1.0, "command": 1.0}},
        )

        self.assertIn("QUARANTINE_FIELD", [action.action for action in actions])


if __name__ == "__main__":
    unittest.main()
