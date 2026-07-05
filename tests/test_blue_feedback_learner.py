import unittest

from dah_flawless.blue.feedback_learner import (
    apply_detection_policy,
    default_blue_policy_state,
    update_blue_policy,
)
from dah_flawless.schemas import DefenseAction, Score, Threat


class BlueFeedbackLearnerTests(unittest.TestCase):
    def test_missed_attack_increases_domain_sensitivity(self):
        policy = default_blue_policy_state()
        score = Score(
            winner="RED_BREACH",
            attack_success=True,
            detection_success=False,
            false_positive=False,
            recovery_success=False,
            availability=0.95,
            target_domain="command",
        )

        updated, log = update_blue_policy(policy, score, [], [])

        self.assertEqual(log["agent"], "BlueFeedbackLearner")
        self.assertGreater(updated["detection_sensitivity"]["command"], policy["detection_sensitivity"]["command"])
        self.assertLess(updated["escalation_threshold"]["command"], policy["escalation_threshold"]["command"])
        self.assertEqual(updated["feedback_counts"]["command"]["missed_attack"], 1)

    def test_false_positive_reduces_domain_sensitivity(self):
        policy = default_blue_policy_state()
        score = Score(
            winner="DRAW",
            attack_success=False,
            detection_success=False,
            false_positive=True,
            recovery_success=False,
            availability=0.99,
            target_domain="telemetry",
        )

        updated, _ = update_blue_policy(policy, score, [], [])

        self.assertLess(updated["detection_sensitivity"]["telemetry"], policy["detection_sensitivity"]["telemetry"])
        self.assertGreater(updated["escalation_threshold"]["telemetry"], policy["escalation_threshold"]["telemetry"])
        self.assertEqual(updated["feedback_counts"]["telemetry"]["false_positive"], 1)

    def test_detection_policy_adjusts_threat_confidence(self):
        policy = default_blue_policy_state()
        policy["detection_sensitivity"]["mission"] = 1.2
        threats = [Threat("mission", 0.70, ("MISSION_PRIORITY_CHANGED",), ("priority changed",))]

        adjusted, log = apply_detection_policy(threats, policy)

        self.assertEqual(adjusted[0].confidence, 0.84)
        self.assertEqual(log["event"], "threat_confidence_adjusted")

    def test_detection_policy_applies_effect_sensitivity(self):
        policy = default_blue_policy_state()
        policy["effect_sensitivity"]["EFFECT_ACK_CAUSAL_CONFUSION"] = 1.2
        threats = [
            Threat(
                "command",
                0.50,
                ("EFFECT_ACK_CAUSAL_CONFUSION", "ACK_CAUSALITY_BREAK"),
                ("ack gap",),
            )
        ]

        adjusted, log = apply_detection_policy(threats, policy)

        self.assertEqual(adjusted[0].confidence, 0.60)
        self.assertIn("effect_sensitivity", log["after"])

    def test_missed_goal_effect_raises_effect_sensitivity(self):
        policy = default_blue_policy_state()
        score = Score(
            winner="BLUE",
            attack_success=True,
            detection_success=True,
            false_positive=False,
            recovery_success=False,
            availability=0.90,
            target_domain="command",
            goal_id="ACK_CAUSAL_CONFUSION",
            goal_success=True,
            goal_reward=0.72,
            evidence={"goal_score": {"goal_id": "ACK_CAUSAL_CONFUSION"}},
        )
        threats = [Threat("command", 0.80, ("REPLAY_SUSPECTED",), ("generic command anomaly",))]

        updated, log = update_blue_policy(policy, score, threats, [])

        self.assertGreater(
            updated["effect_sensitivity"]["EFFECT_ACK_CAUSAL_CONFUSION"],
            policy["effect_sensitivity"]["EFFECT_ACK_CAUSAL_CONFUSION"],
        )
        self.assertLess(
            updated["effect_threshold"]["EFFECT_ACK_CAUSAL_CONFUSION"],
            policy["effect_threshold"]["EFFECT_ACK_CAUSAL_CONFUSION"],
        )
        self.assertEqual(
            updated["effect_feedback_counts"]["EFFECT_ACK_CAUSAL_CONFUSION"]["missed_effect"],
            1,
        )
        self.assertEqual(log["after"]["effect_update_reason"], "missed_goal_effect_raise_sensitivity")

    def test_false_positive_goal_effect_reduces_effect_sensitivity(self):
        policy = default_blue_policy_state()
        score = Score(
            winner="DRAW",
            attack_success=False,
            detection_success=False,
            false_positive=True,
            recovery_success=False,
            availability=0.99,
            target_domain="command",
            goal_id="CHANNEL_STATE_SUPPRESSION",
            goal_success=False,
            goal_reward=0.10,
            evidence={"goal_score": {"goal_id": "CHANNEL_STATE_SUPPRESSION"}},
        )
        threats = [
            Threat(
                "command",
                0.75,
                ("EFFECT_CHANNEL_STATE_SUPPRESSION", "CHANNEL_FRESHNESS_LOSS"),
                ("packet loss looked high",),
            )
        ]

        updated, _ = update_blue_policy(policy, score, threats, [])

        self.assertLess(
            updated["effect_sensitivity"]["EFFECT_CHANNEL_STATE_SUPPRESSION"],
            policy["effect_sensitivity"]["EFFECT_CHANNEL_STATE_SUPPRESSION"],
        )
        self.assertGreater(
            updated["effect_threshold"]["EFFECT_CHANNEL_STATE_SUPPRESSION"],
            policy["effect_threshold"]["EFFECT_CHANNEL_STATE_SUPPRESSION"],
        )
        self.assertEqual(
            updated["effect_feedback_counts"]["EFFECT_CHANNEL_STATE_SUPPRESSION"]["false_positive_effect"],
            1,
        )

    def test_costly_defense_adds_over_defense_count(self):
        policy = default_blue_policy_state()
        score = Score(
            winner="BLUE",
            attack_success=True,
            detection_success=True,
            false_positive=False,
            recovery_success=False,
            availability=0.70,
            target_domain="telemetry",
        )
        actions = [
            DefenseAction("QUARANTINE_FIELD", "blue_observed.telemetry.battery_percent", 3, 1, 0.06),
            DefenseAction("FALLBACK_TO_TRUSTED_STATE", "blue_observed.telemetry", 2, 1, 0.05),
        ]

        updated, _ = update_blue_policy(policy, score, [], actions)

        self.assertEqual(updated["feedback_counts"]["telemetry"]["over_defense"], 1)
        self.assertGreater(updated["escalation_threshold"]["telemetry"], policy["escalation_threshold"]["telemetry"])


if __name__ == "__main__":
    unittest.main()
