import unittest

from dah_flawless.world.feature_extractor import RawWorldFeatureExtractor, summarize_features
from dah_flawless.world.generator import RuleBasedWorldGenerator, ScenarioCondition, generate_world
from dah_flawless.world.state_adapter import build_state_from_raw_world
from dah_flawless.environment.simulator import run_simulation


class WorldPipelineTests(unittest.TestCase):
    def test_world_generator_produces_shared_raw_world_domains(self):
        sample = generate_world(seed=123, sample_index=0)
        raw_world = sample["raw_world"]

        self.assertEqual(sample["schema_id"], "dah.raw_world.sample.v0_1")
        self.assertIn("raw_world_hash", sample)
        self.assertIn("world_hash", sample)
        for domain in {
            "time_reference",
            "mission_space",
            "rf_spectrum",
            "gnss_field",
            "uav_c2_emissions",
            "satcom_emissions",
            "cyber_message_surface",
        }:
            self.assertIn(domain, raw_world)

    def test_world_generator_is_seed_reproducible(self):
        condition = ScenarioCondition(enemy_presence="LIKELY", link_context="BLOS")
        first = RuleBasedWorldGenerator(seed=77).generate(condition, sample_index=2)
        second = RuleBasedWorldGenerator(seed=77).generate(condition, sample_index=2)

        self.assertEqual(first["raw_world_hash"], second["raw_world_hash"])

    def test_feature_extractor_scores_generated_world(self):
        sample = generate_world(seed=123, sample_index=0)
        row = RawWorldFeatureExtractor().extract(sample)

        self.assertEqual(row["schema_id"], "dah.raw_world.features.v0_1")
        self.assertEqual(row["source_raw_world_hash"], sample["raw_world_hash"])
        self.assertIn("C2_PATTERN_EXPLOIT", row["candidate_scores"])
        self.assertIn("rf", row["features"])
        self.assertIn("mavlink_c2", row["features"])
        self.assertIn("best=", summarize_features(row))

    def test_raw_world_adapter_builds_simulation_state(self):
        sample = generate_world(seed=123, sample_index=0)
        state = build_state_from_raw_world(sample, seed=123)

        self.assertEqual(state["scenario"], "raw_world_start")
        self.assertEqual(state["world"]["raw_world_hash"], sample["raw_world_hash"])
        self.assertIn("C2_PATTERN_EXPLOIT", state["world"]["raw_world_feature_scores"])
        self.assertIn("link_profile", state["world"])
        self.assertEqual(state["blue_observed"]["comms"]["latency_ms"], state["world"]["link_profile"]["latency_ms"])

    def test_simulation_can_start_from_raw_world_state(self):
        sample = generate_world(seed=123, sample_index=0)
        state = build_state_from_raw_world(sample, seed=123)

        logs, summary = run_simulation(seed=123, rounds=1, initial_state=state)

        self.assertEqual(summary["scenario"], "raw_world_start")
        self.assertEqual(summary["raw_world_source_hash"], sample["raw_world_hash"])
        self.assertEqual(logs[0]["raw_world_source_hash"], sample["raw_world_hash"])
        self.assertEqual(logs[0]["truth_model"], "scorer_truth")
        self.assertIn("C2_PATTERN_EXPLOIT", logs[0]["raw_world_feature_scores"])


if __name__ == "__main__":
    unittest.main()
