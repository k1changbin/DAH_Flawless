import unittest

from dah_flawless.environment.simulator import run_simulation
from dah_flawless.llm import LLMAdapterConfig, LLMJsonAdapter
from dah_flawless.policy_review import ExternalLLMPolicyUpdateReviewer, HeuristicPolicyUpdateReviewer


class FailingLLMAdapter(LLMJsonAdapter):
    def _call_openai_compatible(self, **kwargs):
        raise ConnectionError("offline")


class SelectingLLMAdapter(LLMJsonAdapter):
    def _call_openai_compatible(self, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"decision": "accept", "selected_scale": 0.5, '
                            '"score": 0.91, "reason": "half-scale update is most plausible"}'
                        )
                    }
                }
            ]
        }


class PolicyUpdateReviewerTests(unittest.TestCase):
    def test_heuristic_reviewer_selects_bounded_candidate(self):
        reviewer = HeuristicPolicyUpdateReviewer()

        selected, log = reviewer.review_update(
            agent="RedAgent",
            update_name="attack_weight",
            before={"weight": 5.0, "telemetry_probe_delta": 24},
            proposed={"weight": 4.5, "telemetry_probe_delta": 18},
            context={"detected": True, "agent_family": "red_probe"},
        )

        self.assertEqual(selected["weight"], 4.5)
        self.assertEqual(selected["telemetry_probe_delta"], 18)
        self.assertEqual(log["agent"], "HeuristicPolicyUpdateReviewer")
        self.assertFalse(log["after"]["external_llm_used"])

    def test_external_reviewer_falls_back_when_unavailable(self):
        reviewer = ExternalLLMPolicyUpdateReviewer(
            fallback=HeuristicPolicyUpdateReviewer(),
            llm_adapter=FailingLLMAdapter(_enabled_config(), role_name="policy_update_reviewer"),
        )

        selected, log = reviewer.review_update(
            agent="BlueFeedbackLearner",
            update_name="domain_policy",
            before={
                "domain_trust": {"command": 1.0},
                "detection_sensitivity": {"command": 1.0},
                "escalation_threshold": {"command": 0.72},
            },
            proposed={
                "domain_trust": {"command": 0.92},
                "detection_sensitivity": {"command": 1.06},
                "escalation_threshold": {"command": 0.69},
            },
            context={"target_domain": "command", "attack_success": True, "detection_success": False},
        )

        self.assertEqual(selected["detection_sensitivity"]["command"], 1.06)
        self.assertEqual(log["reason"], "external_llm_unavailable_or_invalid_fallback")
        self.assertEqual(log["after"]["fallback_error"], "offline")

    def test_external_reviewer_can_select_bounded_scale(self):
        reviewer = ExternalLLMPolicyUpdateReviewer(
            fallback=HeuristicPolicyUpdateReviewer(),
            llm_adapter=SelectingLLMAdapter(_enabled_config(), role_name="policy_update_reviewer"),
        )

        selected, log = reviewer.review_update(
            agent="RedAgent",
            update_name="attack_weight",
            before={"weight": 5.0, "telemetry_probe_delta": 24},
            proposed={"weight": 4.0, "telemetry_probe_delta": 12},
            context={"detected": True, "agent_family": "red_probe"},
        )

        self.assertEqual(selected["weight"], 4.5)
        self.assertEqual(selected["telemetry_probe_delta"], 18)
        self.assertTrue(log["after"]["external_llm_used"])

    def test_simulation_logs_policy_update_review(self):
        logs, _ = run_simulation(seed=42, rounds=1)
        red_update = next(
            item for item in logs[0]["decision_log"] if item["agent"] == "RedAgent" and item["event"] == "weight_update"
        )
        blue_update = next(item for item in logs[0]["decision_log"] if item["agent"] == "BlueFeedbackLearner" and item["event"] == "policy_updated")

        self.assertIn("policy_update_review", red_update["after"])
        self.assertIn("policy_update_review", blue_update["after"])


def _enabled_config() -> LLMAdapterConfig:
    return LLMAdapterConfig(enabled=True, provider="openai_compatible", fallback_on_error=True)


if __name__ == "__main__":
    unittest.main()
