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

    def test_goal_planner_penalizes_recent_goal_collapse(self):
        previous_logs = [
            {
                "round": round_number,
                "red_goal": {"goal_id": "COMMAND_STALE_ACCEPTANCE"},
                "score": {
                    "winner": "RED_BREACH",
                    "attack_success": True,
                    "detection_success": False,
                    "recovery_success": False,
                    "target_domain": "command",
                    "evidence": {"defense_actions": []},
                },
                "defense_actions": [],
            }
            for round_number in range(1, 7)
        ]
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        candidates = score_goal_candidates(
            tag_details=details,
            observed_state=redact_state(state),
            previous_logs=previous_logs,
            goal_stats=default_goal_stats(),
            round_number=7,
        )

        repeated = next(candidate for candidate in candidates if candidate["goal_id"] == "COMMAND_STALE_ACCEPTANCE")
        underused = next(candidate for candidate in candidates if candidate["goal_id"] == "TELEMETRY_TRUST_EROSION")
        self.assertEqual(repeated["score_breakdown"]["recent_goal_count"], 6)
        self.assertEqual(repeated["score_breakdown"]["consecutive_goal_count"], 6)
        self.assertGreater(repeated["score_breakdown"]["repeat_penalty"], 0.0)
        self.assertGreater(underused["score_breakdown"]["underused_bonus"], 0.0)

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

    def test_red_weight_can_increase_when_detected_attack_beats_baseline(self):
        agent = RedAgent(seed=1)
        before = agent.export_policy_state()["weights"]["TELEMETRY_FDI"]
        score = Score(
            winner="BLUE_RECOVERY",
            attack_success=True,
            detection_success=True,
            false_positive=False,
            recovery_success=True,
            availability=0.9,
            target_domain="telemetry",
            evidence={
                "mission_impact": {"mission_impact_score": 0.65},
                "attrition": {"cost_effective": False},
                "defense_actions": ["QUARANTINE_FIELD"],
            },
            goal_id="TELEMETRY_TRUST_EROSION",
            goal_success=True,
            goal_reward=0.9,
            winner_side="BLUE",
            winner_detail="RECOVERY",
            containment_score=0.75,
            attempted_effect_success=True,
            pre_defense_goal_success=True,
            post_defense_effective_breach=False,
            blue_recovered=True,
        )

        log = agent.update_weight(
            "TELEMETRY_FDI",
            detected=True,
            goal_id="TELEMETRY_TRUST_EROSION",
            score=score,
            round_number=10,
        )
        state = agent.export_policy_state()

        self.assertGreater(state["weights"]["TELEMETRY_FDI"], before)
        self.assertGreater(state["attack_reward_ema"]["TELEMETRY_FDI"], 0.45)
        self.assertGreater(log["after"]["red_learning_reward"]["relative_advantage"], 0)

    def test_red_floor_guard_restores_relative_preference(self):
        agent = RedAgent(seed=1)
        for attack_name in agent._weights:
            agent._weights[attack_name] = 1.0
        agent._attack_reward_ema.update(
            {
                "PRIORITY_POISONING": 0.35,
                "TELEMETRY_FDI": 0.62,
                "TIME_DESYNC_REPLAY": 0.42,
            }
        )

        agent._restore_relative_floor_if_saturated()
        state = agent.export_policy_state()

        self.assertGreater(state["weights"]["TELEMETRY_FDI"], state["weights"]["PRIORITY_POISONING"])
        self.assertGreater(state["weights"]["TELEMETRY_FDI"], 1.0)

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
