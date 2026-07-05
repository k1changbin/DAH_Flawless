import unittest
from copy import deepcopy

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.attacks.mutations import apply_attack
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.state_factory import create_baseline_state


class ObserveModelTests(unittest.TestCase):
    def test_blue_observed_has_internal_and_external_views(self):
        state = create_baseline_state(seed=42)
        observed = state["blue_observed"]

        self.assertEqual(observed["observe_schema_version"], "dah.observe.v0_2")
        self.assertIn("internal_observe", observed)
        self.assertIn("external_observe", observed)
        self.assertIs(observed["telemetry"], observed["external_observe"]["telemetry"])
        self.assertIs(observed["c2_message"], observed["external_observe"]["c2_message"])
        self.assertFalse(observed["observe_access"]["red_direct_mutation"]["internal_observe"])
        self.assertTrue(observed["observe_access"]["red_direct_mutation"]["external_observe"])

    def test_red_mutation_preserves_internal_observe(self):
        state = create_baseline_state(seed=42)
        before_internal = deepcopy(state["blue_observed"]["internal_observe"])

        attacked_state, _ = apply_attack(state, get_attack("TELEMETRY_FDI"))

        self.assertEqual(before_internal, attacked_state["blue_observed"]["internal_observe"])
        self.assertNotEqual(
            state["blue_observed"]["external_observe"]["telemetry"],
            attacked_state["blue_observed"]["external_observe"]["telemetry"],
        )

    def test_redacted_state_keeps_observe_boundary_without_world(self):
        state = create_baseline_state(seed=42)
        redacted = redact_state(state)

        self.assertNotIn("world", redacted)
        self.assertIn("internal_observe", redacted["blue_observed"])
        self.assertIn("external_observe", redacted["blue_observed"])


if __name__ == "__main__":
    unittest.main()
