import unittest

from dah_flawless.attacks.goal_planner import (
    default_goal_stats,
    score_goal_candidates,
    select_goal_for_attack,
    update_goal_stats,
)
from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.environment.training_scheduler import run_training_schedule
from dah_flawless.schemas import Score
from dah_flawless.situation_tagger import derive_tag_details


class GoalPlannerTests(unittest.TestCase):
    def test_goal_planner_scores_current_cyber_context(self):
        state = create_baseline_state(seed=1)
        obs = state["blue_observed"]
        obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"] - 2
        obs["comms"]["ack_delay_ms"] = 950
        details = derive_tag_details(redact_state(state), make_history(state))

        candidates = score_goal_candidates(
            tag_details=details,
            observed_state=redact_state(state),
            previous_logs=[],
            goal_stats=default_goal_stats(),
            round_number=1,
        )

        self.assertIn(candidates[0]["goal_id"], {"ACK_CAUSAL_CONFUSION", "COMMAND_STALE_ACCEPTANCE"})
        self.assertTrue(candidates[0]["cyber_effects"])
        self.assertIn("contextual_ucb", candidates[0]["algorithm"])

    def test_goal_planner_uses_previous_log_rewards(self):
        previous_logs = [
            {
                "round": 1,
                "red_goal": {"goal_id": "WRONG_TARGET_SELECTION"},
                "score": {
                    "winner": "RED_BREACH",
                    "attack_success": True,
                    "detection_success": False,
                    "recovery_success": False,
                    "target_domain": "mission",
                    "evidence": {"defense_actions": []},
                },
                "defense_actions": [],
            }
            for _ in range(3)
        ]
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        candidates = score_goal_candidates(
            tag_details=details,
            observed_state=redact_state(state),
            previous_logs=previous_logs,
            goal_stats=default_goal_stats(),
            round_number=4,
        )

        wrong_target = next(candidate for candidate in candidates if candidate["goal_id"] == "WRONG_TARGET_SELECTION")
        self.assertGreaterEqual(wrong_target["score_breakdown"]["history_reward"], 0.8)

    def test_select_goal_for_scripted_attack_keeps_attack_compatible(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))
        candidates = score_goal_candidates(
            tag_details=details,
            observed_state=redact_state(state),
            previous_logs=[],
            goal_stats=default_goal_stats(),
            round_number=1,
        )

        selected = select_goal_for_attack("PRIORITY_POISONING", candidates)

        self.assertIn("PRIORITY_POISONING", selected["preferred_attacks"])

    def test_red_agent_exports_goal_feedback_stats(self):
        agent = RedAgent(seed=1)
        score = Score(
            winner="RED_BREACH",
            attack_success=True,
            detection_success=False,
            false_positive=False,
            recovery_success=False,
            availability=0.8,
            target_domain="mission",
            evidence={"defense_actions": []},
        )

        log = agent.update_weight(
            "PRIORITY_POISONING",
            detected=False,
            goal_id="WRONG_TARGET_SELECTION",
            score=score,
            round_number=2,
        )
        state = agent.export_policy_state()

        self.assertEqual(state["goal_stats"]["WRONG_TARGET_SELECTION"]["count"], 1)
        self.assertEqual(log["after"]["goal_feedback"]["goal_id"], "WRONG_TARGET_SELECTION")

    def test_simulation_logs_goal_plan_and_candidates(self):
        logs, summary = run_simulation(seed=42, rounds=4)

        self.assertIn("red_goal", logs[0])
        self.assertIn("goal_candidate_scores", logs[0]["decision_log"][0]["after"])
        self.assertIn("goal_stats", summary["red_policy_state"])
        self.assertTrue(logs[3]["red_goal"]["goal_id"])

    def test_scheduler_passes_previous_episode_logs_to_goal_planner(self):
        logs, _ = run_training_schedule(
            seed=42,
            blue_update_episodes=1,
            red_update_episodes=1,
            eval_episodes=0,
            steps_per_episode=3,
        )

        first_second_episode = logs[3]
        candidates = first_second_episode["decision_log"][0]["after"]["goal_candidate_scores"]
        self.assertGreater(max(candidate["score_breakdown"]["count"] for candidate in candidates), 0)


if __name__ == "__main__":
    unittest.main()
