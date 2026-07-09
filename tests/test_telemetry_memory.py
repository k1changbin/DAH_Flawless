import unittest
from copy import deepcopy

from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.attacks.telemetry_memory import TelemetryMemory
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.state_factory import create_baseline_state


class TelemetryMemoryTests(unittest.TestCase):
    def test_memory_records_red_visible_telemetry_channels_without_world(self):
        state = create_baseline_state(seed=42)
        redacted = redact_state(state)
        memory = TelemetryMemory()

        snapshot = memory.observe(redacted, round_number=1)

        self.assertEqual(snapshot["schema_id"], "dah.red_telemetry_memory.v0_1")
        self.assertEqual(snapshot["record_count"], 1)
        self.assertEqual(snapshot["latest"]["asset_tx_mirror"]["battery_percent"], 20)
        self.assertEqual(snapshot["latest"]["ground_rx_view"]["battery_percent"], 20)
        self.assertEqual(snapshot["features"]["pattern_hint"], "stable_tx_rx_alignment")
        self.assertFalse(snapshot["policy"]["red_direct_mutation_allowed"])
        self.assert_no_world(snapshot)

    def test_memory_window_is_bounded_and_summarizes_rx_delta(self):
        state = create_baseline_state(seed=42)
        redacted = redact_state(state)
        memory = TelemetryMemory(max_records=3)

        for round_number in range(1, 6):
            observed = deepcopy(redacted)
            channels = observed["blue_observed"]["telemetry_channels"]
            channels["ground_rx_view"]["battery_percent"] = 20 + round_number
            memory.observe(observed, round_number=round_number)

        snapshot = memory.snapshot()

        self.assertEqual(snapshot["record_count"], 3)
        self.assertEqual(snapshot["features"]["round_span"], [3, 5])
        self.assertEqual(snapshot["features"]["max_abs_battery_delta"], 5.0)
        self.assertEqual(snapshot["features"]["pattern_hint"], "battery_delta_memory")

    def test_red_agent_logs_and_exports_telemetry_memory(self):
        state = create_baseline_state(seed=42)
        redacted = redact_state(state)
        agent = RedAgent(seed=1)

        _, _, _, log = agent.choose_attack(1, redacted, [], [])
        exported = agent.export_telemetry_memory_state()
        loaded = RedAgent(seed=2, policy_state={"telemetry_memory": exported})

        self.assertEqual(log["after"]["telemetry_memory"]["record_count"], 1)
        self.assertEqual(exported["schema_id"], "dah.red_telemetry_memory.v0_1")
        self.assertEqual(exported["records"][0]["round"], 1)
        self.assertNotIn("telemetry_memory", agent.export_policy_state())
        self.assertEqual(loaded.export_telemetry_memory_state()["records"][0]["round"], 1)

    def assert_no_world(self, value):
        if isinstance(value, dict):
            self.assertNotIn("world", value)
            for nested in value.values():
                self.assert_no_world(nested)
        elif isinstance(value, list):
            for nested in value:
                self.assert_no_world(nested)


if __name__ == "__main__":
    unittest.main()
