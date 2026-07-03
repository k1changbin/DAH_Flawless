import unittest

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.blue.invariants import analyze_invariants
from dah_flawless.blue.tagger import derive_tags
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.situation_tagger import derive_tag_details


class EncryptedChannelTagTests(unittest.TestCase):
    def test_baseline_exposes_encrypted_channel_attack_surface_tags(self):
        state = create_baseline_state(seed=1)
        tags = set(derive_tags(redact_state(state), make_history(state)))

        for expected in {
            "SEQUENCE_VISIBLE",
            "TIMESTAMP_VISIBLE",
            "REGULAR_PACKET_INTERVAL",
            "ACK_CHANNEL_VISIBLE",
            "PACKET_SIZE_PATTERN",
            "METADATA_PLAINTEXT",
            "STATE_UPDATE_DEPENDENT",
            "REPLAY_WINDOW_OPEN",
        }:
            self.assertIn(expected, tags)

        self.assertNotIn("CRYPTO_WEAKNESS_HINT", tags)
        self.assertNotIn("HEARTBEAT_GAP", tags)

    def test_red_situation_tagger_returns_explainable_tag_details(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))
        by_tag = {detail.tag: detail for detail in details}

        ack = by_tag["ACK_CHANNEL_VISIBLE"]
        self.assertGreaterEqual(ack.confidence, 0.80)
        self.assertTrue(ack.evidence)
        self.assertIn("ack", ack.meaning.lower())

        hidden = by_tag["PAYLOAD_HIDDEN"]
        self.assertIn("comms.payload_visible=False", hidden.evidence)

    def test_channel_shape_anomalies_become_command_threat_evidence(self):
        state = create_baseline_state(seed=1)
        history = make_history(state)
        obs = state["blue_observed"]
        obs["c2_message"]["sequence_number"] += 3
        obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"] - 2
        obs["comms"]["packet_interval_jitter_ms"] = 460
        obs["comms"]["ack_delay_ms"] = 950
        obs["comms"]["heartbeat_gap_ms"] = 3200

        redacted = redact_state(state)
        tags = derive_tags(redacted, history)
        threats = analyze_invariants(redacted, history, tags, state["capabilities"])

        self.assertIn("SEQUENCE_GAP", tags)
        self.assertIn("PACKET_INTERVAL_ANOMALY", tags)
        self.assertIn("ACK_TIMING_ANOMALY", tags)
        self.assertIn("HEARTBEAT_GAP", tags)
        self.assertTrue(any(threat.target == "command" for threat in threats))

    def test_crypto_weakness_hint_requires_explicit_crypto_signal(self):
        state = create_baseline_state(seed=1)
        state["blue_observed"]["comms"]["crypto_profile"]["nonce_reuse_suspected"] = True

        tags = derive_tags(redact_state(state), make_history(state))

        self.assertIn("CRYPTO_WEAKNESS_HINT", tags)

    def test_simulation_logs_red_situation_tag_details(self):
        logs, _ = run_simulation(seed=42, rounds=1)
        first = logs[0]

        self.assertIn("red_situation_tags", first)
        self.assertIn("red_situation_tag_details", first)
        self.assertIn("SEQUENCE_VISIBLE", first["red_situation_tags"])
        self.assertTrue(all("confidence" in detail for detail in first["red_situation_tag_details"]))
        self.assertTrue(all("evidence" in detail for detail in first["red_situation_tag_details"]))

    def test_time_desync_replay_prefers_communication_shape_tags(self):
        attack = get_attack("TIME_DESYNC_REPLAY")

        for expected in {
            "SEQUENCE_VISIBLE",
            "TIMESTAMP_VISIBLE",
            "ACK_CHANNEL_VISIBLE",
            "METADATA_PLAINTEXT",
            "STATE_UPDATE_DEPENDENT",
            "REPLAY_WINDOW_OPEN",
            "PACKET_INTERVAL_ANOMALY",
            "HEARTBEAT_GAP",
            "ACK_TIMING_ANOMALY",
        }:
            self.assertIn(expected, attack.preferred_tags)


if __name__ == "__main__":
    unittest.main()
