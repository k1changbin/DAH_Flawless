"""Initial scenario generation for the DAH Flawless MVP."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.config import BASE_TIMESTAMP, DEFAULT_SCENARIO
from dah_flawless.environment.scenarios import get_scenario_preset


def create_baseline_state(seed: int, scenario: str = DEFAULT_SCENARIO) -> dict:
    """Create a single-UAV reconnaissance scenario.

    The world and observed values start aligned. Red mutations later change
    only blue_observed, while scorer keeps access to world.

    Scenario presets live in ``environment.scenarios``. The selected preset
    defines the initial world value, mission state, Blue capabilities, and any
    Blue-observed overrides.
    """

    preset = get_scenario_preset(scenario, BASE_TIMESTAMP)
    world = preset["world"]
    blue_observed = _create_blue_observed(world)
    _deep_update(blue_observed, preset["blue_observed"])

    return {
        "round": 0,
        "seed": seed,
        "scenario": scenario,
        "world": world,
        "blue_observed": blue_observed,
        "mission": preset["mission"],
        "capabilities": preset["capabilities"],
        "defense_runtime": {
            "active_defense_slots": 2,
            "active_defenses": [],
            "pending_defenses": [],
            "domain_trust": {"telemetry": 1.0, "mission": 1.0, "command": 1.0},
        },
        "last_known_good": deepcopy(blue_observed),
    }


def _create_blue_observed(world: dict) -> dict:
    position = world["uav"]["position"]
    return {
        "time": {
            "received_timestamp": world["time"]["true_timestamp"],
            "local_clock_offset_ms": 430,
        },
        "telemetry": {
            "battery_percent": world["uav"]["battery_percent"],
            "battery_drain_rate": world["uav"]["battery_drain_rate"],
            "motor_status": world["uav"]["motor_status"],
            "altitude_m": position["altitude_m"],
            "speed_mps": world["uav"]["speed_mps"],
            "heading_deg": world["uav"]["heading_deg"],
        },
        "navigation": {
            "gnss_fix_quality": "NORMAL",
            "satellite_count": 7,
            "hdop": 1.4,
            "cn0_avg": 35.0,
            "imu_position_estimate": {"lat": position["lat"], "lon": position["lon"]},
        },
        "mission": {
            "area_priority": deepcopy(world["mission"]["area_priority"]),
            "recommended_area": world["mission"]["current_area"],
        },
        "c2_message": {
            "sequence_number": world["command"]["expected_sequence_number"],
            "command": world["command"]["last_valid_command"],
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


def _deep_update(target: dict, overrides: dict) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = deepcopy(value)


def make_history(state: dict) -> dict:
    obs = state["blue_observed"]
    return {
        "last_observed": deepcopy(obs),
        "last_sequence_number": obs["c2_message"]["sequence_number"],
        "last_received_timestamp": obs["time"]["received_timestamp"],
        "last_area_priority": deepcopy(obs["mission"]["area_priority"]),
        "last_telemetry": deepcopy(obs["telemetry"]),
        "last_navigation": deepcopy(obs["navigation"]),
        "last_command": obs["c2_message"]["command"],
    }
