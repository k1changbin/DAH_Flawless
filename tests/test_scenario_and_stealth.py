"""Tests for the ported strengths: degraded_start / capability paralysis and
the Stealth Controller (adaptive Red stealth)."""

import unittest

from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.blue.defense_planner import apply_defense_actions, plan_defense
from dah_flawless.blue.invariants import analyze_invariants
from dah_flawless.blue.tagger import derive_tags
from dah_flawless.config import SCENARIOS
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.scenarios import SCENARIO_PRESETS
from dah_flawless.environment.simulator import _advance_normal_state, run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.schemas import DefenseAction, Threat


class DegradedScenarioTests(unittest.TestCase):
    def test_config_scenarios_match_presets(self):
        self.assertEqual(SCENARIOS, tuple(SCENARIO_PRESETS))

    def test_low_battery_fault_uses_scenario_world(self):
        state = create_baseline_state(seed=1, scenario="low_battery_fault")

        self.assertEqual(state["world"]["uav"]["battery_percent"], 14)
        self.assertEqual(state["blue_observed"]["telemetry"]["battery_percent"], 14)
        self.assertEqual(state["world"]["uav"]["motor_status"], "FAULT")
        self.assertEqual(state["blue_observed"]["telemetry"]["motor_status"], "FAULT")

    def test_urban_rf_noise_keeps_world_alignment_after_advance(self):
        state = create_baseline_state(seed=1, scenario="urban_rf_noise")
        advanced = _advance_normal_state(state, round_number=1)

        self.assertEqual(advanced["world"]["mission"]["current_area"], "B")
        self.assertEqual(advanced["blue_observed"]["mission"]["recommended_area"], "B")
        self.assertEqual(advanced["blue_observed"]["telemetry"]["speed_mps"], 28)

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            create_baseline_state(seed=1, scenario="missing")

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

    def test_degraded_cross_check_emits_red_preference_tag(self):
        state = create_baseline_state(seed=1, scenario="degraded_start")
        tags = derive_tags(redact_state(state), make_history(state))

        self.assertIn("CROSS_CHECK_UNAVAILABLE", tags)

    def test_degraded_start_first_round_keeps_initial_availability(self):
        logs, _ = run_simulation(seed=42, rounds=1, scenario="degraded_start")
        defense_log = next(
            item for item in logs[0]["decision_log"] if item["agent"] == "DefensePlannerAgent"
        )

        self.assertEqual(defense_log["before"]["availability"], 0.55)

    def test_degraded_trusted_restore_raises_restore_cost(self):
        logs, _ = run_simulation(seed=42, rounds=1, scenario="degraded_start")
        restore_action = next(
            action for action in logs[0]["defense_actions"] if action["action"] == "QUARANTINE_FIELD"
        )

        self.assertEqual(restore_action["availability_cost"], 0.075)
        self.assertEqual(restore_action["status"], "DONE_RESTORE_DEGRADED")

    def test_unavailable_trusted_restore_does_not_recover_from_history(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        state["capabilities"]["trusted_restore"] = "UNAVAILABLE"
        state["blue_observed"]["mission"]["area_priority"] = {"A": 0.2, "B": 0.4, "C": 0.95}
        action = DefenseAction("QUARANTINE_FIELD", "blue_observed.mission.area_priority", 3, 1, 0.05)

        defended = apply_defense_actions(state, [action], history, capabilities=state["capabilities"])

        self.assertEqual(defended["blue_observed"]["mission"]["area_priority"], {"A": 0.2, "B": 0.4, "C": 0.95})
        self.assertEqual(
            defended["defense_runtime"]["active_defenses"][0]["status"],
            "FAILED_RESTORE_UNAVAILABLE",
        )

    def test_trusted_restore_uses_last_known_good_not_last_observed(self):
        state = create_baseline_state(seed=1)
        clean_priority = dict(state["last_known_good"]["mission"]["area_priority"])
        poisoned_priority = {"A": 0.2, "B": 0.4, "C": 0.95}
        state["blue_observed"]["mission"]["area_priority"] = poisoned_priority
        contaminated_history = make_history(state)
        action = DefenseAction("QUARANTINE_FIELD", "blue_observed.mission.area_priority", 3, 1, 0.05)

        defended = apply_defense_actions(
            state,
            [action],
            contaminated_history,
            threats=[Threat("mission", 0.9, ("MISSION_PRIORITY_CHANGED",), ("priority changed sharply",))],
            capabilities=state["capabilities"],
        )

        self.assertEqual(defended["blue_observed"]["mission"]["area_priority"], clean_priority)
        self.assertEqual(contaminated_history["last_area_priority"], poisoned_priority)


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
