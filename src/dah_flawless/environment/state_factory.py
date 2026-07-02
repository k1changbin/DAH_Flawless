"""Initial scenario generation for the DAH Flawless MVP."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.config import BASE_TIMESTAMP


def create_baseline_state(seed: int) -> dict:
    """Create a single-UAV reconnaissance scenario.

    The world and observed values start aligned. Red mutations later change
    only blue_observed, while scorer keeps access to world.
    """

    world = {
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

    blue_observed = {
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
            "checksum_valid": True,
            "signature_present": True,
            "auth_valid": True,
        },
        "comms": {
            "channel": "SATCOM",
            "encrypted": True,
            "payload_visible": False,
            "latency_ms": 180,
            "packet_loss": 0.02,
            "message_queue_depth": 3,
            "request_rate": 4.0,
        },
    }

    return {
        "round": 0,
        "seed": seed,
        "world": world,
        "blue_observed": blue_observed,
        "mission": {"availability": 1.0, "trust_budget": 1.0},
        "capabilities": {"cross_check_telemetry": "OK"},
        "defense_runtime": {
            "active_defense_slots": 2,
            "active_defenses": [],
            "pending_defenses": [],
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
        "last_command": obs["c2_message"]["command"],
    }
