"""Initial scenario generation for the DAH Flawless MVP."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.blue.feedback_learner import default_blue_policy_state
from dah_flawless.config import BASE_TIMESTAMP, DEFAULT_SCENARIO, SCENARIOS
from dah_flawless.observation import build_blue_observed, refresh_telemetry_channels


def create_baseline_state(seed: int, scenario: str = DEFAULT_SCENARIO) -> dict:
    """Create a single-UAV reconnaissance scenario.

    The scorer truth and observed values start aligned. Red mutations later
    change only blue_observed, while scorer keeps access to the compatibility
    key ``state["world"]``.

    scenario:
      clean_start         - full capabilities, availability 1.0 (default).
      degraded_start      - weakened recovery footing and GNSS.
      satcom_delay        - persistent high-latency / jittery SATCOM profile.
      gnss_degraded       - poor satellite geometry and weak GNSS signal.
      c2_metadata_noisy   - noisy but visible C2 metadata/auth/checksum state.
      telemetry_conflict  - physically suspicious telemetry operating point.
      low_trust_start     - reduced mission budget and lower Blue trust state.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")

    scorer_truth = {
        "time": {"true_timestamp": BASE_TIMESTAMP, "round": 0},
        "environment": {
            "weather": "CLEAR",
            "terrain": "LOW_MOUNTAIN",
            "rf_noise_level": 0.21,
            "gnss_interference": "NONE",
        },
        "uav": {
            "position": {"lat": 37.123, "lon": 127.456, "altitude_m": 180},
            "speed_mps": 42,
            "heading_deg": 91,
            "battery_percent": 20,
            "battery_drain_rate": 1.0,
            "motor_status": "FAULT",
        },
        "mission": {
            "current_area": "A",
            "area_priority": {"A": 0.90, "B": 0.40, "C": 0.20},
            "return_required": True,
        },
        "command": {
            "expected_sequence_number": 1021,
            "last_valid_command": "RETURN_TO_BASE",
        },
    }

    internal_observe = {
        "time": {
            "true_timestamp": BASE_TIMESTAMP,
            "round": 0,
            "local_clock_offset_ms": 430,
        },
        "telemetry": {
            "battery_percent": 20,
            "battery_drain_rate": 1.0,
            "motor_status": "FAULT",
        },
        "inertial_navigation": {
            "position_estimate": {"lat": 37.123, "lon": 127.456, "altitude_m": 180},
            "speed_mps": 42,
            "heading_deg": 91,
            "altitude_m": 180,
        },
        "c2_message": {
            "sequence_number": 1021,
            "command": "RETURN_TO_BASE",
            "received_timestamp": BASE_TIMESTAMP,
            "source": "internal_observe",
            "red_direct_mutation_allowed": False,
        },
        "health": {
            "source": "internal_observe",
            "red_direct_mutation_allowed": False,
        },
    }

    external_observe = {
        "time": {"received_timestamp": BASE_TIMESTAMP, "local_clock_offset_ms": 430},
        "telemetry": {
            "battery_percent": 20,
            "battery_drain_rate": 1.0,
            "motor_status": "FAULT",
            "altitude_m": 180,
            "speed_mps": 42,
            "heading_deg": 91,
        },
        "navigation": {
            "gnss_fix_quality": "NORMAL",
            "satellite_count": 7,
            "hdop": 1.4,
            "cn0_avg": 35.0,
            "imu_position_estimate": {"lat": 37.123, "lon": 127.456},
        },
        "mission": {
            "area_priority": {"A": 0.90, "B": 0.40, "C": 0.20},
            "recommended_area": "A",
        },
        "c2_message": {
            "sequence_number": 1021,
            "command": "RETURN_TO_BASE",
            "sysid": 1,
            "compid": 1,
            "msgid": 76,
            "message_role": "COMMAND",
            "sequence_visible": True,
            "timestamp_visible": True,
            "metadata_plaintext": True,
            "checksum_valid": True,
            "signature_present": True,
            "auth_valid": True,
            "ack": {
                "visible": True,
                "sequence_number": 1021,
                "status": "ACCEPTED",
            },
        },
        "comms": {
            "channel": "SATCOM",
            "encrypted": True,
            "payload_visible": False,
            "latency_ms": 180,
            "packet_loss": 0.02,
            "message_queue_depth": 3,
            "request_rate": 4.0,
            "packet_interval_ms": 1000,
            "packet_interval_jitter_ms": 18,
            "packet_size_bytes": 96,
            "packet_size_variance": 6,
            "ack_visible": True,
            "ack_delay_ms": 210,
            "route_metadata_visible": True,
            "state_update_dependency": "HIGH",
            "anti_replay_window_s": 180,
            "heartbeat_interval_ms": 1000,
            "heartbeat_gap_ms": 0,
            "crypto_profile": {
                "algorithm": "AEAD_SIM",
                "nonce_reuse_suspected": False,
                "weak_cipher_hint": False,
            },
        },
    }
    blue_observed = build_blue_observed(
        internal_observe=internal_observe,
        external_observe=external_observe,
    )

    mission = {"availability": 1.0, "trust_budget": 1.0}
    capabilities = {
        "cross_check_telemetry": "OK",
        "trusted_restore": "OK",
        "time_validation": "OK",
    }

    blue_policy = default_blue_policy_state()
    scenario_profile = _apply_scenario_profile(
        scenario=scenario,
        scorer_truth=scorer_truth,
        blue_observed=blue_observed,
        mission=mission,
        capabilities=capabilities,
        blue_policy=blue_policy,
    )
    refresh_telemetry_channels(blue_observed)

    return {
        "round": 0,
        "seed": seed,
        "scenario": scenario,
        "scenario_profile": scenario_profile,
        "world": scorer_truth,
        "blue_observed": blue_observed,
        "mission": mission,
        "capabilities": capabilities,
        "defense_runtime": {
            "active_defense_slots": 2,
            "active_defenses": [],
            "pending_defenses": [],
            "episode_initial_budget": {
                "availability": mission["availability"],
                "trust_budget": mission["trust_budget"],
            },
            "domain_trust": deepcopy(blue_policy["domain_trust"]),
            "detection_sensitivity": deepcopy(blue_policy["detection_sensitivity"]),
            "escalation_threshold": deepcopy(blue_policy["escalation_threshold"]),
            "effect_sensitivity": deepcopy(blue_policy["effect_sensitivity"]),
            "effect_threshold": deepcopy(blue_policy["effect_threshold"]),
            "effect_mission_impact_ema": deepcopy(blue_policy["effect_mission_impact_ema"]),
            "effect_mission_impact_counts": deepcopy(blue_policy["effect_mission_impact_counts"]),
            "telemetry_axis_sensitivity": deepcopy(blue_policy["telemetry_axis_sensitivity"]),
            "telemetry_axis_threshold": deepcopy(blue_policy["telemetry_axis_threshold"]),
            "feedback_counts": deepcopy(blue_policy["feedback_counts"]),
            "effect_feedback_counts": deepcopy(blue_policy["effect_feedback_counts"]),
            "telemetry_axis_feedback_counts": deepcopy(blue_policy["telemetry_axis_feedback_counts"]),
        },
        "last_known_good": deepcopy(blue_observed),
    }


def make_history(state: dict) -> dict:
    obs = state["blue_observed"]
    return {
        "last_observed": deepcopy(obs),
        "last_sequence_number": obs["c2_message"]["sequence_number"],
        "last_received_timestamp": obs["time"]["received_timestamp"],
        "last_area_priority": deepcopy(obs["mission"]["area_priority"]),
        "last_telemetry": deepcopy(obs["telemetry"]),
        "last_telemetry_channels": deepcopy(obs.get("telemetry_channels", {})),
        "last_navigation": deepcopy(obs["navigation"]),
        "last_command": obs["c2_message"]["command"],
    }


def _apply_scenario_profile(
    *,
    scenario: str,
    scorer_truth: dict,
    blue_observed: dict,
    mission: dict,
    capabilities: dict,
    blue_policy: dict,
) -> dict:
    if scenario == "clean_start":
        return {
            "name": scenario,
            "emphasis": ("baseline",),
            "description": "Nominal starting point with healthy Blue capabilities.",
        }

    if scenario == "degraded_start":
        mission["availability"] = 0.55
        mission["trust_budget"] = 0.72
        capabilities["cross_check_telemetry"] = "DEGRADED"
        capabilities["trusted_restore"] = "DEGRADED"
        blue_observed["navigation"]["gnss_fix_quality"] = "DEGRADED"
        blue_observed["navigation"]["satellite_count"] = 4
        blue_observed["navigation"]["hdop"] = 6.2
        blue_observed["navigation"]["cn0_avg"] = 27.0
        scorer_truth["environment"]["gnss_interference"] = "PARTIAL"
        return {
            "name": scenario,
            "emphasis": ("recovery_footing", "gnss_degraded", "capability_paralysis"),
            "description": "Partially paralyzed start with degraded cross-check and trusted restore.",
        }

    if scenario == "satcom_delay":
        link_profile = {
            "latency_ms": 760,
            "packet_loss": 0.14,
            "message_queue_depth": 14,
            "packet_interval_jitter_ms": 480,
            "packet_size_variance": 11,
            "ack_delay_ms": 1720,
            "heartbeat_gap_ms": 3300,
        }
        scorer_truth["link_profile"] = link_profile
        scorer_truth["environment"]["weather"] = "RAIN_FADE"
        blue_observed["comms"].update(link_profile)
        blue_observed["comms"]["channel"] = "SATCOM"
        mission["availability"] = 0.84
        mission["trust_budget"] = 0.86
        capabilities["time_validation"] = "DEGRADED"
        return {
            "name": scenario,
            "emphasis": ("satcom_delay", "channel_state_suppression", "ack_timing"),
            "description": "Persistent delayed and lossy SATCOM channel with visible timing metadata.",
        }

    if scenario == "gnss_degraded":
        scorer_truth["environment"]["gnss_interference"] = "SUSPECTED"
        blue_observed["navigation"]["gnss_fix_quality"] = "DEGRADED"
        blue_observed["navigation"]["satellite_count"] = 3
        blue_observed["navigation"]["hdop"] = 8.3
        blue_observed["navigation"]["cn0_avg"] = 21.5
        capabilities["cross_check_telemetry"] = "DEGRADED"
        mission["trust_budget"] = 0.88
        return {
            "name": scenario,
            "emphasis": ("gnss_degraded", "navigation_trust", "telemetry_cross_check"),
            "description": "Weak GNSS geometry and degraded telemetry cross-checks.",
        }

    if scenario == "c2_metadata_noisy":
        blue_observed["c2_message"]["checksum_valid"] = False
        blue_observed["c2_message"]["auth_valid"] = False
        blue_observed["c2_message"]["signature_present"] = True
        blue_observed["c2_message"]["metadata_plaintext"] = True
        blue_observed["comms"]["request_rate"] = 12.5
        blue_observed["comms"]["packet_size_variance"] = 4
        blue_observed["comms"]["crypto_profile"]["nonce_reuse_suspected"] = True
        blue_observed["comms"]["crypto_profile"]["weak_cipher_hint"] = True
        capabilities["time_validation"] = "DEGRADED"
        mission["trust_budget"] = 0.90
        return {
            "name": scenario,
            "emphasis": ("c2_metadata", "auth_noise", "crypto_metadata"),
            "description": "Noisy C2 metadata surface with visible auth/checksum irregularities.",
        }

    if scenario == "telemetry_conflict":
        scorer_truth["uav"]["battery_percent"] = 76
        scorer_truth["uav"]["battery_drain_rate"] = 1.1
        scorer_truth["uav"]["motor_status"] = "OK"
        blue_observed["telemetry"]["battery_percent"] = 76
        blue_observed["telemetry"]["battery_drain_rate"] = 1.1
        blue_observed["telemetry"]["motor_status"] = "OK"
        internal = blue_observed["internal_observe"]["telemetry"]
        internal["battery_percent"] = 76
        internal["battery_drain_rate"] = 1.1
        internal["motor_status"] = "OK"
        capabilities["cross_check_telemetry"] = "OK"
        mission["trust_budget"] = 0.92
        return {
            "name": scenario,
            "emphasis": ("telemetry_consistency", "battery_motor_anomaly", "blue_overdefense_risk"),
            "description": "A physically suspicious telemetry operating point without scorer-truth leakage.",
        }

    if scenario == "low_trust_start":
        mission["availability"] = 0.70
        mission["trust_budget"] = 0.58
        capabilities["trusted_restore"] = "DEGRADED"
        blue_policy["domain_trust"]["telemetry"] = 0.62
        blue_policy["domain_trust"]["mission"] = 0.60
        blue_policy["domain_trust"]["command"] = 0.58
        blue_policy["detection_sensitivity"]["command"] = 1.05
        blue_policy["detection_sensitivity"]["mission"] = 1.04
        blue_policy["escalation_threshold"]["command"] = 0.68
        blue_policy["escalation_threshold"]["mission"] = 0.68
        return {
            "name": scenario,
            "emphasis": ("low_trust", "overdefense_pressure", "degraded_restore"),
            "description": "Blue starts with lower mission budget and lower domain trust.",
        }

    raise ValueError(f"unknown scenario: {scenario}")
