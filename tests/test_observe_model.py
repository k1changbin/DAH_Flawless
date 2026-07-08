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

        self.assertEqual(observed["observe_schema_version"], "dah.observe.v0_3")
        self.assertIn("internal_observe", observed)
        self.assertIn("external_observe", observed)
        self.assertIs(observed["telemetry"], observed["external_observe"]["telemetry"])
        self.assertIs(observed["c2_message"], observed["external_observe"]["c2_message"])
        self.assertIs(observed["telemetry_channels"], observed["external_observe"]["telemetry_channels"])
        self.assertFalse(observed["observe_access"]["red_direct_mutation"]["internal_observe"])
        self.assertTrue(observed["observe_access"]["red_direct_mutation"]["external_observe"])
        self.assertIn(
            "telemetry_channels",
            observed["observe_access"]["red_direct_mutation"]["read_only_external_domains"],
        )
        self.assertNotIn(
            "telemetry_channels",
            observed["observe_access"]["red_direct_mutation"]["allowed_external_domains"],
        )

    def test_red_visibility_policy_marks_telemetry_channels_read_only(self):
        state = create_baseline_state(seed=42)
        policy = state["blue_observed"]["observe_access"]["red_visibility"]

        self.assertEqual(policy["policy_id"], "dah.red_visibility.v0_1")
        self.assertIn(
            "blue_observed.external_observe.telemetry_channels.asset_tx_mirror",
            policy["can_read"]["telemetry_channel_paths"],
        )
        self.assertIn(
            "blue_observed.external_observe.telemetry_channels.ground_rx_view",
            policy["can_read"]["telemetry_channel_paths"],
        )
        self.assertIn(
            "blue_observed.external_observe.telemetry_channels.*",
            policy["mutation_excluded"]["paths"],
        )
        self.assertNotIn(
            "telemetry_channels",
            policy["direct_mutation_allowed"]["external_domains"],
        )

    def test_telemetry_channels_split_asset_tx_from_ground_rx(self):
        state = create_baseline_state(seed=42)
        channels = state["blue_observed"]["telemetry_channels"]

        self.assertEqual(channels["schema_id"], "dah.telemetry_channels.v0_1")
        self.assertEqual(
            channels["asset_tx_mirror"]["battery_percent"],
            state["blue_observed"]["internal_observe"]["telemetry"]["battery_percent"],
        )
        self.assertEqual(
            channels["ground_rx_view"]["battery_percent"],
            state["blue_observed"]["telemetry"]["battery_percent"],
        )
        self.assertFalse(channels["asset_tx_mirror"]["red_direct_mutation_allowed"])
        self.assertFalse(channels["ground_rx_view"]["red_direct_mutation_allowed"])
        self.assertEqual(channels["red_use_policy"]["allowed_use"], "intel_and_memory_only")

    def test_red_mutation_preserves_internal_observe(self):
        state = create_baseline_state(seed=42)
        before_internal = deepcopy(state["blue_observed"]["internal_observe"])
        before_asset_tx = deepcopy(state["blue_observed"]["telemetry_channels"]["asset_tx_mirror"])
        before_external_telemetry = deepcopy(state["blue_observed"]["external_observe"]["telemetry"])

        attacked_state, _ = apply_attack(state, get_attack("TELEMETRY_FDI"))

        self.assertEqual(before_internal, attacked_state["blue_observed"]["internal_observe"])
        self.assertEqual(before_asset_tx, attacked_state["blue_observed"]["telemetry_channels"]["asset_tx_mirror"])
        self.assertEqual(before_external_telemetry, attacked_state["blue_observed"]["external_observe"]["telemetry"])
        self.assertNotEqual(
            state["blue_observed"]["external_observe"]["c2_message"]["ack"]["sequence_number"],
            attacked_state["blue_observed"]["external_observe"]["c2_message"]["ack"]["sequence_number"],
        )
        self.assertEqual(
            attacked_state["blue_observed"]["telemetry_channels"]["ground_rx_view"]["battery_percent"],
            attacked_state["blue_observed"]["telemetry"]["battery_percent"],
        )

    def test_redacted_state_keeps_observe_boundary_without_world(self):
        state = create_baseline_state(seed=42)
        redacted = redact_state(state)

        self.assertNotIn("world", redacted)
        self.assertIn("internal_observe", redacted["blue_observed"])
        self.assertIn("external_observe", redacted["blue_observed"])
        self.assertEqual(
            redacted["blue_observed"]["observe_access"]["red_visibility"]["policy_id"],
            "dah.red_visibility.v0_1",
        )


if __name__ == "__main__":
    unittest.main()
