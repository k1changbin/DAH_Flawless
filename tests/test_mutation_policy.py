import unittest
from pathlib import Path

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.attacks.mutation_policy import FIELD_POLICIES, FIELD_POLICY_BY_PATH, POLICY_SOURCE, MutationPolicyEnforcer
from dah_flawless.attacks.mutations import apply_attack
from dah_flawless.config import BASE_TIMESTAMP
from dah_flawless.environment.state_factory import create_baseline_state


ROOT = Path(__file__).resolve().parents[1]


class MutationPolicyTests(unittest.TestCase):
    def test_mutation_policy_config_defines_core_boundaries(self):
        policy = (ROOT / "configs" / "mutation_policy.yaml").read_text(encoding="utf-8")

        self.assertIn("schema_id: dah.mutation_policy.v0_1", policy)
        self.assertIn("internal_observe:", policy)
        self.assertIn("external_observe:", policy)
        self.assertIn("mutable_by_red: false", policy)
        self.assertIn("mutable_by_red: true", policy)
        self.assertIn("global_forbidden_mutations:", policy)
        self.assertIn("blue_observed.internal_observe.*", policy)
        self.assertIn("approval_llm_contract:", policy)
        self.assertIn('role: "reviewer_only"', policy)
        self.assertIn("allowed_actions:", policy)
        self.assertIn("forbidden_actions:", policy)
        self.assertIn("Mutation Engine applies the final approved simulated mutation", policy)
        self.assertIn("deterministic policy wins", policy)

    def test_mutation_policy_docs_exist(self):
        doc = (ROOT / "docs" / "mutation_policy.md").read_text(encoding="utf-8")

        self.assertIn("internal_observe", doc)
        self.assertIn("external_observe", doc)
        self.assertIn("loud_demo", doc)
        self.assertIn("Mutation Approval LLM", doc)
        self.assertIn("reviewer-only", doc)
        self.assertIn("approve", doc)
        self.assertIn("clamp", doc)
        self.assertIn("reject", doc)
        self.assertIn("explain", doc)
        self.assertIn("runtime enforcement", doc)

    def test_runtime_policy_loads_yaml_config_as_source(self):
        self.assertTrue(POLICY_SOURCE.endswith("configs\\mutation_policy.yaml") or POLICY_SOURCE.endswith("configs/mutation_policy.yaml"))
        self.assertGreaterEqual(len(FIELD_POLICIES), 19)
        self.assertEqual(FIELD_POLICY_BY_PATH["navigation.hdop"].policy_id, "gnss_hdop")
        self.assertEqual(FIELD_POLICY_BY_PATH["c2_message.command"].policy_id, "c2_command")

    def test_runtime_policy_rejects_internal_observe_mutation(self):
        observed = {"internal_observe": {"telemetry": {"battery_percent": 20}}}
        policy = MutationPolicyEnforcer("aggressive")

        applied = policy.set_absolute(
            observed,
            "internal_observe.telemetry.battery_percent",
            99,
            value_min=0,
            value_max=100,
        )

        self.assertEqual(applied, 20)
        self.assertEqual(observed["internal_observe"]["telemetry"]["battery_percent"], 20)
        self.assertFalse(policy.decision_dicts()[0]["approved"])

    def test_runtime_policy_clamps_stealth_telemetry_probe(self):
        state = create_baseline_state(seed=1)

        attacked, log = apply_attack(
            state,
            get_attack("TELEMETRY_FDI"),
            stealth=True,
            tactic={"mutation_profile": "loud_demo", "probe_delta": 999},
        )

        self.assertEqual(log["mutation_profile"], "stealth")
        self.assertEqual(attacked["blue_observed"]["telemetry"]["battery_percent"], 28)
        battery_decision = next(
            decision for decision in log["policy_decisions"] if decision["path"] == "telemetry.battery_percent"
        )
        self.assertEqual(battery_decision["action"], "clamped")
        self.assertEqual(battery_decision["applied_delta"], 8)

    def test_runtime_policy_clamps_time_desync_params(self):
        state = create_baseline_state(seed=1)

        attacked, log = apply_attack(
            state,
            get_attack("TIME_DESYNC_REPLAY"),
            tactic={
                "mutation_profile": "aggressive",
                "strategy": "replay",
                "params": {
                    "sequence_delta": -100,
                    "timestamp_delta_s": -999,
                    "latency_ms": 10000,
                    "packet_loss": 0.99,
                },
            },
        )

        self.assertEqual(attacked["blue_observed"]["c2_message"]["sequence_number"], 1009)
        self.assertEqual(attacked["blue_observed"]["time"]["received_timestamp"], BASE_TIMESTAMP - 60)
        self.assertEqual(attacked["blue_observed"]["comms"]["latency_ms"], 1380)
        self.assertEqual(attacked["blue_observed"]["comms"]["packet_loss"], 0.25)
        self.assertTrue(any(decision["action"] == "clamped" for decision in log["policy_decisions"]))


if __name__ == "__main__":
    unittest.main()
