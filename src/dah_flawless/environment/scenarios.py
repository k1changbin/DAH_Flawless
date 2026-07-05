"""Scenario presets for initial world state and Blue starting conditions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_BASE_WORLD = {
    "time": {"true_timestamp": 0, "round": 0},
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

_DEFAULT_MISSION = {"availability": 1.0, "trust_budget": 1.0}
_DEFAULT_CAPABILITIES = {
    "cross_check_telemetry": "OK",
    "trusted_restore": "OK",
    "time_validation": "OK",
}

SCENARIO_PRESETS: dict[str, dict[str, Any]] = {
    "clean_start": {
        "description": "Full Blue capabilities and aligned world/observed state.",
    },
    "degraded_start": {
        "description": "Starts partially paralyzed with degraded cross-check and restore paths.",
        "mission": {"availability": 0.55},
        "capabilities": {
            "cross_check_telemetry": "DEGRADED",
            "trusted_restore": "DEGRADED",
        },
        "blue_observed": {
            "navigation": {
                "gnss_fix_quality": "DEGRADED",
                "satellite_count": 4,
                "hdop": 6.2,
            },
        },
    },
    "low_battery_fault": {
        "description": "UAV is already near forced return with a confirmed motor fault.",
        "world": {
            "environment": {"weather": "WIND", "rf_noise_level": 0.34},
            "uav": {
                "battery_percent": 14,
                "battery_drain_rate": 1.4,
                "motor_status": "FAULT",
            },
            "mission": {"return_required": True},
            "command": {"last_valid_command": "RETURN_TO_BASE"},
        },
    },
    "urban_rf_noise": {
        "description": "Urban terrain with elevated RF noise and a still-operational UAV.",
        "world": {
            "environment": {
                "weather": "FOG",
                "terrain": "URBAN",
                "rf_noise_level": 0.68,
                "gnss_interference": "MULTIPATH",
            },
            "uav": {
                "position": {"lat": 37.5665, "lon": 126.9780, "altitude_m": 120},
                "speed_mps": 28,
                "heading_deg": 35,
                "battery_percent": 64,
                "battery_drain_rate": 0.9,
                "motor_status": "OK",
            },
            "mission": {
                "current_area": "B",
                "area_priority": {"A": 0.45, "B": 0.88, "C": 0.35},
                "return_required": False,
            },
            "command": {
                "expected_sequence_number": 2040,
                "last_valid_command": "CONTINUE_MISSION",
            },
        },
        "blue_observed": {
            "navigation": {
                "satellite_count": 5,
                "hdop": 4.8,
                "cn0_avg": 26.0,
            },
            "comms": {
                "latency_ms": 260,
                "packet_loss": 0.06,
                "message_queue_depth": 5,
            },
        },
    },
}

SCENARIO_NAMES = tuple(SCENARIO_PRESETS)


def get_scenario_preset(name: str, base_timestamp: int) -> dict[str, Any]:
    """Return a fully merged scenario preset.

    The returned value is detached from module-level presets, so callers can
    mutate simulation state without contaminating future runs.
    """

    try:
        raw = SCENARIO_PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {name}") from exc

    world = _deep_merge(_BASE_WORLD, raw.get("world", {}))
    world["time"]["true_timestamp"] = base_timestamp
    world["time"]["round"] = 0

    return {
        "description": raw["description"],
        "world": world,
        "mission": _deep_merge(_DEFAULT_MISSION, raw.get("mission", {})),
        "capabilities": _deep_merge(_DEFAULT_CAPABILITIES, raw.get("capabilities", {})),
        "blue_observed": deepcopy(raw.get("blue_observed", {})),
    }


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged
