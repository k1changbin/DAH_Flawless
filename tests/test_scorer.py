import unittest

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.environment.state_factory import create_baseline_state
from dah_flawless.scoring.scorer import score_round
from dah_flawless.schemas import DefenseAction


class ScorerTests(unittest.TestCase):
    def test_red_breach_when_attack_success_without_detection(self):
        attack = get_attack("TELEMETRY_FDI")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        # Direct loud_demo hard case for scorer behavior, not the default mutation profile.
        pre["blue_observed"]["telemetry"]["battery_percent"] = 82
        pre["blue_observed"]["telemetry"]["motor_status"] = "OK"

        score = score_round(pre, post, attack, threats=[], actions=[])

        self.assertTrue(score.attack_success)
        self.assertFalse(score.detection_success)
        self.assertEqual(score.winner, "RED_BREACH")
        self.assertEqual(score.winner_side, "RED")
        self.assertEqual(score.winner_detail, "BREACH")

    def test_partial_breach_when_attack_effect_does_not_reach_goal(self):
        attack = get_attack("TELEMETRY_FDI")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        pre["blue_observed"]["telemetry"]["battery_percent"] = pre["world"]["uav"]["battery_percent"] + 2
        pre["blue_observed"]["telemetry"]["motor_status"] = pre["world"]["uav"]["motor_status"]
        pre["blue_observed"]["telemetry"]["battery_drain_rate"] = 0.0

        score = score_round(pre, post, attack, threats=[], actions=[])

        self.assertTrue(score.attack_success)
        self.assertFalse(score.goal_success)
        self.assertEqual(score.winner, "DRAW")
        self.assertEqual(score.winner_side, "DRAW")
        self.assertEqual(score.winner_detail, "PARTIAL_BREACH")
        self.assertLessEqual(score.goal_reward, 0.30)

    def test_policy_quarantine_prevents_small_telemetry_drift_breach(self):
        attack = get_attack("TELEMETRY_FDI")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        pre["blue_observed"]["telemetry"]["battery_percent"] = 21.4
        post["blue_observed"]["telemetry"]["battery_percent"] = 21.4
        post["defense_runtime"]["observe_policy_gate"] = {
            "algorithm": "zta_inspired_abac_radac_external_observe_v1",
            "scope": "external_observe_only",
            "by_domain": {
                "telemetry": {
                    "domain": "telemetry",
                    "decision": "QUARANTINE",
                    "allowed_use": "detection_only",
                    "use_weight": 0.05,
                    "trust_score": 0.45,
                    "required_assurance": 0.75,
                }
            },
            "decisions": [],
        }

        score = score_round(pre, post, attack, threats=[], actions=[])

        self.assertTrue(score.attack_success)
        self.assertTrue(score.goal_success)
        self.assertFalse(score.detection_success)
        self.assertEqual(score.winner, "DRAW")
        self.assertEqual(score.winner_detail, "POLICY_CONTAINMENT")
        self.assertGreaterEqual(score.containment_score, 0.45)

    def test_mission_recommended_area_counts_as_attack_effect(self):
        attack = get_attack("PRIORITY_POISONING")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        pre["blue_observed"]["mission"]["recommended_area"] = "C"

        score = score_round(pre, post, attack, threats=[], actions=[])

        self.assertTrue(score.attack_success)
        self.assertTrue(score.goal_success)
        self.assertEqual(score.winner, "RED_BREACH")

    def test_attrition_requires_fresh_defense_pressure(self):
        attack = get_attack("PRIORITY_POISONING")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        # Direct loud_demo hard case for scorer behavior, not the default mutation profile.
        pre["blue_observed"]["mission"]["area_priority"] = {"A": 0.2, "B": 0.4, "C": 0.95}
        post["mission"]["availability"] = 0.4

        class FakeThreat:
            target = "mission"
            confidence = 0.9

        actions = [
            DefenseAction("QUARANTINE_FIELD", "blue_observed.mission.area_priority", 3, 1, 0.05),
            DefenseAction("REQUEST_REVALIDATION", "blue_observed.mission", 1, 1, 0.05),
        ]
        score = score_round(pre, post, attack, threats=[FakeThreat()], actions=actions)

        self.assertEqual(score.winner, "RED_ATTRITION")
        self.assertEqual(score.winner_side, "RED")
        self.assertEqual(score.winner_detail, "ATTRITION")
        self.assertTrue(score.evidence["attrition"]["triggered"])

    def test_attrition_requires_defense_cost_to_exceed_red_cost(self):
        attack = get_attack("PRIORITY_POISONING")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        pre["blue_observed"]["mission"]["area_priority"] = {"A": 0.2, "B": 0.4, "C": 0.95}
        post["mission"]["availability"] = 0.4
        post["defense_runtime"]["combat_attrition"] = {
            "round_defense_cost": 0.10,
            "red_round_attack_cost": 0.18,
            "defense_steps": 2,
            "consecutive_defense_steps": 2,
        }

        class FakeThreat:
            target = "mission"
            confidence = 0.9

        actions = [
            DefenseAction("QUARANTINE_FIELD", "blue_observed.mission.area_priority", 3, 1, 0.05),
            DefenseAction("REQUEST_REVALIDATION", "blue_observed.mission", 1, 1, 0.05),
        ]
        score = score_round(pre, post, attack, threats=[FakeThreat()], actions=actions)

        self.assertNotEqual(score.winner, "RED_ATTRITION")
        self.assertFalse(score.evidence["attrition"]["triggered"])
        self.assertFalse(score.evidence["attrition"]["cost_effective"])

    def test_low_availability_without_new_pressure_does_not_force_attrition(self):
        attack = get_attack("PRIORITY_POISONING")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        pre["blue_observed"]["mission"]["area_priority"] = {"A": 0.2, "B": 0.4, "C": 0.95}
        pre["mission"]["availability"] = 0.42
        post["mission"]["availability"] = 0.41

        class FakeThreat:
            target = "mission"
            confidence = 0.9

        score = score_round(pre, post, attack, threats=[FakeThreat()], actions=[])

        self.assertEqual(score.winner, "DRAW")
        self.assertFalse(score.evidence["attrition"]["triggered"])
        self.assertTrue(score.evidence["attrition"]["stale_floor_pressure"])

    def test_detection_window_uses_recent_threat_history(self):
        attack = get_attack("TELEMETRY_FDI")
        pre = create_baseline_state(seed=1)
        post = create_baseline_state(seed=1)
        # Direct loud_demo hard case for scorer behavior, not the default mutation profile.
        pre["blue_observed"]["telemetry"]["battery_percent"] = 82
        pre["blue_observed"]["telemetry"]["motor_status"] = "OK"

        class FakeThreat:
            target = "telemetry"
            confidence = 0.9

        score = score_round(pre, post, attack, threats=[], actions=[], threat_history=[[FakeThreat()]])

        self.assertTrue(score.detection_success)
        self.assertEqual(score.evidence["detection_window"], 2)


if __name__ == "__main__":
    unittest.main()
