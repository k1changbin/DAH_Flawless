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
