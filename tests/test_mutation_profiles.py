import unittest

from dah_flawless.attacks.catalog import get_attack
from dah_flawless.attacks.mutations import apply_attack, resolve_mutation_profile
from dah_flawless.attacks.selector import build_tactic
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.environment.redaction import redact_state
from dah_flawless.situation_tagger import derive_tag_details


class MutationProfileTests(unittest.TestCase):
    def test_profile_resolver_defaults_invalid_profile_to_aggressive(self):
        self.assertEqual(resolve_mutation_profile(False, {"mutation_profile": "oversized"}), "aggressive")

    def test_profile_resolver_stealth_overrides_invalid_profile(self):
        self.assertEqual(resolve_mutation_profile(True, {"mutation_profile": "oversized"}), "stealth")

    def test_time_desync_big_values_are_loud_demo_params(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        tactic = build_tactic("TIME_DESYNC_REPLAY", False, details, telemetry_probe_delta=24)

        self.assertEqual(tactic["mutation_profile"], "aggressive")
        self.assertNotEqual(tactic["params"].get("timestamp_delta_s"), -400)
        self.assertEqual(tactic["params_by_profile"]["loud_demo"]["timestamp_delta_s"], -400)

    def test_explicit_loud_demo_selects_big_time_desync_params(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        tactic = build_tactic(
            "TIME_DESYNC_REPLAY",
            False,
            details,
            telemetry_probe_delta=24,
            mutation_profile="loud_demo",
        )

        self.assertEqual(tactic["mutation_profile"], "loud_demo")
        self.assertEqual(tactic["params"]["timestamp_delta_s"], -400)

    def test_stealth_overrides_requested_loud_demo_profile(self):
        state = create_baseline_state(seed=1)
        details = derive_tag_details(redact_state(state), make_history(state))

        tactic = build_tactic(
            "TIME_DESYNC_REPLAY",
            True,
            details,
            telemetry_probe_delta=24,
            mutation_profile="loud_demo",
        )

        self.assertEqual(tactic["mutation_profile"], "stealth")
        self.assertNotEqual(tactic["params"]["timestamp_delta_s"], -400)

    def test_telemetry_aggressive_is_not_old_loud_value(self):
        state = create_baseline_state(seed=1)

        attacked, log = apply_attack(
            state,
            get_attack("TELEMETRY_FDI"),
            tactic={"mutation_profile": "aggressive"},
        )

        self.assertEqual(log["mutation_profile"], "aggressive")
        self.assertEqual(attacked["blue_observed"]["telemetry"]["battery_percent"], 45)
        self.assertNotEqual(attacked["blue_observed"]["telemetry"]["battery_percent"], 82)

    def test_telemetry_loud_demo_keeps_old_demo_value(self):
        state = create_baseline_state(seed=1)

        attacked, log = apply_attack(
            state,
            get_attack("TELEMETRY_FDI"),
            tactic={"mutation_profile": "loud_demo"},
        )

        self.assertEqual(log["mutation_profile"], "loud_demo")
        self.assertEqual(log["policy_id"], "dah.mutation_policy.v0_1.profile.loud_demo")
        self.assertEqual(attacked["blue_observed"]["telemetry"]["battery_percent"], 82)

    def test_out_of_scope_attack_has_no_mutation_handler(self):
        state = create_baseline_state(seed=1)

        with self.assertRaisesRegex(ValueError, "mutation not implemented"):
            apply_attack(state, get_attack("DIRECT_DECRYPTION"))

    def test_simulation_records_mutation_profile(self):
        logs, summary = run_simulation(seed=42, rounds=3, mutation_profile="loud_demo")

        self.assertEqual(summary["mutation_profile"], "loud_demo")
        for entry in logs:
            mutation_log = next(item for item in entry["decision_log"] if item["event"] == "mutation_applied")
            self.assertEqual(mutation_log["mutation_profile"], "loud_demo")


if __name__ == "__main__":
    unittest.main()
