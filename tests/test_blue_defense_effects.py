import unittest

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.blue.defense_effects import assess_defense_containment
from dah_flawless.blue.defense_planner import apply_defense_actions
from dah_flawless.environment.readiness import blue_defense_score
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.scoring.scorer import score_round
from dah_flawless.schemas import DefenseAction, Threat


class BlueDefenseEffectContractTests(unittest.TestCase):
    def test_hold_command_contains_stale_command_effect(self):
        attack = get_attack("TIME_DESYNC_REPLAY")
        pre = create_baseline_state(seed=1)
        pre["blue_observed"]["c2_message"]["sequence_number"] -= 3
        pre["blue_observed"]["time"]["received_timestamp"] -= 90
        threats = [
            Threat(
                "command",
                0.91,
                ("EFFECT_COMMAND_STALE_ACCEPTANCE",),
                ("sequence lag",),
            )
        ]
        actions = [DefenseAction("HOLD_COMMAND", "blue_observed.c2_message.command", 3, 1, 0.05)]

        post = apply_defense_actions(pre, actions, make_history(pre), threats=threats, capabilities=pre["capabilities"])
        score = score_round(pre, post, attack, threats, actions)

        self.assertGreaterEqual(score.containment_score, 0.55)
        self.assertTrue(score.evidence["containment"]["contained"])
        self.assertEqual(score.evidence["containment"]["effect_id"], "EFFECT_COMMAND_STALE_ACCEPTANCE")

    def test_contract_scores_partial_containment_without_full_recovery(self):
        attack = get_attack("TELEMETRY_FDI")
        pre = create_baseline_state(seed=1)
        pre["blue_observed"]["telemetry"]["battery_percent"] = 82
        pre["blue_observed"]["telemetry"]["motor_status"] = "OK"
        post = create_baseline_state(seed=1)
        post["blue_observed"]["telemetry"]["battery_percent"] = 36
        post["blue_observed"]["telemetry"]["motor_status"] = "OK"
        threats = [
            Threat(
                "telemetry",
                0.90,
                ("EFFECT_TELEMETRY_TRUST_EROSION",),
                ("battery gap",),
            )
        ]
        actions = [DefenseAction("QUARANTINE_FIELD", "blue_observed.telemetry.battery_percent", 3, 1, 0.04)]

        containment = assess_defense_containment(
            pre_defense_state=pre,
            post_defense_state=post,
            attack=attack,
            threats=threats,
            actions=actions,
            goal_score={"goal_id": "TELEMETRY_TRUST_EROSION"},
            detection_success=True,
            recovery_success=False,
            attack_success=True,
        )

        self.assertGreater(containment["containment_score"], 0.35)
        self.assertEqual(containment["containment_level"], "PARTIAL_CONTAINMENT")

    def test_policy_gate_can_limit_use_without_counting_as_detection(self):
        attack = get_attack("TELEMETRY_FDI")
        pre = create_baseline_state(seed=1)
        pre["blue_observed"]["telemetry"]["battery_percent"] = 82
        pre["blue_observed"]["telemetry"]["motor_status"] = "OK"
        post = create_baseline_state(seed=1)
        post["blue_observed"]["telemetry"]["battery_percent"] = 82
        post["blue_observed"]["telemetry"]["motor_status"] = "OK"
        post["defense_runtime"]["observe_policy_gate"] = {
            "algorithm": "zta_inspired_abac_radac_external_observe_v1",
            "scope": "external_observe_only",
            "by_domain": {
                "telemetry": {
                    "domain": "telemetry",
                    "decision": "QUARANTINE",
                    "allowed_use": "detection_only",
                    "use_weight": 0.05,
                    "trust_score": 0.31,
                    "required_assurance": 0.69,
                }
            },
            "decisions": [],
        }

        containment = assess_defense_containment(
            pre_defense_state=pre,
            post_defense_state=post,
            attack=attack,
            threats=[],
            actions=[],
            goal_score={"goal_id": "TELEMETRY_TRUST_EROSION"},
            detection_success=False,
            recovery_success=False,
            attack_success=True,
        )

        self.assertEqual(containment["detection_component"], 0.0)
        self.assertGreaterEqual(containment["policy_containment_score"], 0.90)
        self.assertGreaterEqual(containment["containment_score"], 0.35)
        self.assertEqual(containment["containment_level"], "PARTIAL_CONTAINMENT")
        self.assertEqual(
            containment["recovery_interpretation"],
            "policy_limited_authoritative_use_without_full_restore",
        )

    def test_readiness_uses_containment_but_caps_red_attrition(self):
        contained_draw = {
            "score": {
                "winner": "DRAW",
                "winner_side": "DRAW",
                "attack_success": True,
                "detection_success": True,
                "recovery_success": False,
                "goal_success": True,
                "availability": 0.72,
                "containment_score": 0.70,
                "evidence": {"containment": {"containment_score": 0.70}},
            }
        }
        red_attrition = {
            "score": {
                "winner": "RED_ATTRITION",
                "winner_side": "RED",
                "attack_success": True,
                "detection_success": True,
                "recovery_success": True,
                "goal_success": True,
                "availability": 0.20,
                "containment_score": 0.90,
                "evidence": {"containment": {"containment_score": 0.90}},
            }
        }

        self.assertGreater(blue_defense_score(contained_draw), 0.50)
        self.assertLessEqual(blue_defense_score(red_attrition), 0.38)


if __name__ == "__main__":
    unittest.main()
