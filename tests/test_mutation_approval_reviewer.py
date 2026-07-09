import unittest
from copy import deepcopy

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.attacks.mutations import apply_attack
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state
from dah_flawless.llm import LLMAdapterConfig, LLMJsonAdapter
from dah_flawless.mutation_review import (
    ExternalLLMMutationApprovalReviewer,
    HeuristicMutationApprovalReviewer,
    build_mutation_approval_reviewer,
)


class FakeOutcome:
    def __init__(self, policy_decisions=None):
        self.policy_decisions = policy_decisions or []
        self.requested_delta = {}
        self.applied_delta = {}


class FailingMutationLLMAdapter(LLMJsonAdapter):
    def _call_openai_compatible(self, **kwargs):
        raise ConnectionError("offline")


class ClampMutationLLMAdapter(LLMJsonAdapter):
    def _call_openai_compatible(self, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"action": "clamp", "selected_scale": 0.5, "score": 0.86, '
                            '"reason": "half-scale is enough for the simulated test", '
                            '"allowed_fields": ["c2_message.ack.sequence_number", "comms.ack_delay_ms"], '
                            '"safety_boundary": "simulated observe mutation only"}'
                        )
                    }
                }
            ]
        }


class MutationApprovalReviewerTests(unittest.TestCase):
    def test_default_builder_returns_offline_reviewer(self):
        reviewer = build_mutation_approval_reviewer()

        self.assertIsInstance(reviewer, HeuristicMutationApprovalReviewer)

    def test_heuristic_reviewer_rejects_internal_observe_change(self):
        reviewer = HeuristicMutationApprovalReviewer()
        before = {"internal_observe": {"telemetry": {"battery_percent": 20}}, "telemetry": {"battery_percent": 20}}
        proposed = deepcopy(before)
        proposed["internal_observe"]["telemetry"]["battery_percent"] = 99

        selected, log = reviewer.review_mutation(
            attack_name="TELEMETRY_FDI",
            profile="aggressive",
            tactic={"mutation_profile": "aggressive"},
            before_observe=before,
            proposed_observe=proposed,
            outcome=FakeOutcome(),
        )

        self.assertEqual(selected, before)
        self.assertEqual(log["after"]["action"], "reject")
        self.assertIn("forbidden_observe_scope", log["after"]["reason"])

    def test_heuristic_reviewer_rejects_telemetry_channel_projection_change(self):
        reviewer = HeuristicMutationApprovalReviewer()
        before = {
            "telemetry_channels": {
                "asset_tx_mirror": {"battery_percent": 20},
                "ground_rx_view": {"battery_percent": 20},
            }
        }
        proposed = deepcopy(before)
        proposed["telemetry_channels"]["asset_tx_mirror"]["battery_percent"] = 99

        selected, log = reviewer.review_mutation(
            attack_name="TELEMETRY_FDI",
            profile="aggressive",
            tactic={"mutation_profile": "aggressive"},
            before_observe=before,
            proposed_observe=proposed,
            outcome=FakeOutcome(),
        )

        self.assertEqual(selected, before)
        self.assertEqual(log["after"]["action"], "reject")
        self.assertIn("forbidden_observe_scope", log["after"]["reason"])

    def test_external_reviewer_can_clamp_bounded_mutation(self):
        state = create_baseline_state(seed=1)
        reviewer = ExternalLLMMutationApprovalReviewer(
            fallback=HeuristicMutationApprovalReviewer(),
            llm_adapter=ClampMutationLLMAdapter(_enabled_config(), role_name="mutation_approval_reviewer"),
        )

        attacked, log = apply_attack(
            state,
            get_attack("TELEMETRY_FDI"),
            tactic={"mutation_profile": "aggressive"},
            mutation_approval_reviewer=reviewer,
        )

        self.assertEqual(attacked["blue_observed"]["telemetry"]["battery_percent"], 20)
        self.assertEqual(attacked["blue_observed"]["c2_message"]["ack"]["sequence_number"], 1020)
        self.assertEqual(attacked["blue_observed"]["comms"]["ack_delay_ms"], 580)
        self.assertEqual(attacked["blue_observed"]["comms"]["latency_ms"], 360)
        review = log["mutation_approval_review"]["after"]
        self.assertEqual(review["action"], "clamp")
        self.assertEqual(review["selected_scale"], 0.5)
        self.assertTrue(review["external_llm_used"])

    def test_external_reviewer_falls_back_when_unavailable(self):
        state = create_baseline_state(seed=1)
        reviewer = ExternalLLMMutationApprovalReviewer(
            fallback=HeuristicMutationApprovalReviewer(),
            llm_adapter=FailingMutationLLMAdapter(_enabled_config(), role_name="mutation_approval_reviewer"),
        )

        attacked, log = apply_attack(
            state,
            get_attack("TELEMETRY_FDI"),
            tactic={"mutation_profile": "aggressive"},
            mutation_approval_reviewer=reviewer,
        )

        self.assertEqual(attacked["blue_observed"]["telemetry"]["battery_percent"], 20)
        self.assertEqual(attacked["blue_observed"]["c2_message"]["ack"]["sequence_number"], 1019)
        self.assertEqual(attacked["blue_observed"]["comms"]["ack_delay_ms"], 950)
        review = log["mutation_approval_review"]["after"]
        self.assertFalse(review["external_llm_used"])
        self.assertEqual(review["fallback_error"], "offline")

    def test_simulation_logs_mutation_approval_review(self):
        logs, _ = run_simulation(seed=42, rounds=1)
        mutation_log = next(item for item in logs[0]["decision_log"] if item["event"] == "mutation_applied")

        self.assertIn("mutation_approval_review", mutation_log)
        self.assertEqual(mutation_log["mutation_approval_review"]["event"], "mutation_approval_reviewed")


def _enabled_config() -> LLMAdapterConfig:
    return LLMAdapterConfig(enabled=True, provider="openai_compatible", fallback_on_error=True)


if __name__ == "__main__":
    unittest.main()
