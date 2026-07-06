import unittest

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.attacks.goal_planner import reward_from_score
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state
from dah_flawless.scoring.scorer import score_round


class GoalAwareScorerTests(unittest.TestCase):
    def test_score_round_emits_goal_score_fields(self):
        logs, summary = run_simulation(seed=42, rounds=3)

        for entry in logs:
            score = entry["score"]
            self.assertTrue(score["goal_id"])
            self.assertIn("goal_success", score)
            self.assertIn("goal_reward", score)
            self.assertIn("goal_score", score["evidence"])
            self.assertEqual(score["goal_id"], entry["red_goal"]["goal_id"])

        self.assertIn("goal_success_rate", summary)
        self.assertIn("avg_goal_reward", summary)
        self.assertIn("avg_mission_impact_score", summary)
        self.assertIn("high_mission_impact_count", summary)
        self.assertIn("goals", summary)

    def test_wrong_target_goal_scores_priority_drift(self):
        state = create_baseline_state(seed=1)
        attacked = create_baseline_state(seed=1)
        attacked["blue_observed"]["mission"]["area_priority"] = {"A": 0.20, "B": 0.40, "C": 0.95}
        attacked["blue_observed"]["mission"]["recommended_area"] = "C"
        attack = get_attack("PRIORITY_POISONING")
        score = score_round(
            attacked,
            attacked,
            attack,
            threats=[],
            actions=[],
            red_goal={"goal_id": "WRONG_TARGET_SELECTION", "intended_effect": "bias target selection"},
        )

        goal_score = score.evidence["goal_score"]
        self.assertTrue(score.goal_success)
        self.assertGreater(goal_score["evidence"]["max_priority_delta"], 0.35)
        self.assertEqual(goal_score["evidence"]["observed_top_area"], "C")

    def test_ack_goal_scores_causal_gap(self):
        state = create_baseline_state(seed=1)
        obs = state["blue_observed"]
        obs["c2_message"]["ack"]["visible"] = True
        obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"] - 2
        obs["comms"]["ack_visible"] = True
        obs["comms"]["ack_delay_ms"] = 950
        attack = get_attack("TIME_DESYNC_REPLAY")
        score = score_round(
            state,
            state,
            attack,
            threats=[],
            actions=[],
            red_goal={"goal_id": "ACK_CAUSAL_CONFUSION", "intended_effect": "break ack causality"},
        )

        self.assertTrue(score.goal_success)
        self.assertEqual(score.evidence["goal_score"]["evidence"]["ack_gap"], 2)

    def test_mission_impact_scores_high_for_hidden_safety_fault(self):
        state = create_baseline_state(seed=1)
        # Baseline truth is battery=20, motor=FAULT, return_required=True.
        state["blue_observed"]["telemetry"]["battery_percent"] = 82
        state["blue_observed"]["telemetry"]["motor_status"] = "OK"
        attack = get_attack("TELEMETRY_FDI")
        score = score_round(
            state,
            state,
            attack,
            threats=[],
            actions=[],
            red_goal={"goal_id": "TELEMETRY_TRUST_EROSION", "intended_effect": "hide safety fault"},
        )

        impact = score.evidence["mission_impact"]
        goal_score = score.evidence["goal_score"]
        self.assertGreaterEqual(impact["mission_impact_score"], 0.75)
        self.assertEqual(impact["primary_component"], "telemetry_safety")
        self.assertEqual(goal_score["mission_impact_score"], impact["mission_impact_score"])
        self.assertEqual(goal_score["reward_algorithm"], "goal_reward_blended_with_mission_impact_v1")
        self.assertEqual(score.goal_reward, goal_score["goal_reward"])

    def test_goal_reward_is_used_by_feedback_reward(self):
        high_goal = {
            "winner": "BLUE",
            "attack_success": True,
            "detection_success": True,
            "recovery_success": False,
            "evidence": {"goal_score": {"goal_reward": 0.95}, "defense_actions": []},
        }
        low_goal = {
            "winner": "BLUE",
            "attack_success": True,
            "detection_success": True,
            "recovery_success": False,
            "evidence": {"goal_score": {"goal_reward": 0.10}, "defense_actions": []},
        }

        self.assertGreater(reward_from_score(high_goal), reward_from_score(low_goal))


if __name__ == "__main__":
    unittest.main()
