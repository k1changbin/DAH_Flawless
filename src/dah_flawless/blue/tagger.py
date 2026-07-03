"""Observed-only situation tag derivation."""

from __future__ import annotations

from math import cos, radians, sqrt

from dah_flawless.config import (
    GNSS_IMU_DRIFT_TOLERANCE_M,
    ROUND_SECONDS,
    TELEMETRY_BATTERY_TOLERANCE,
)


def derive_tags(redacted_state: dict, history: dict) -> list[str]:
    obs = redacted_state["blue_observed"]
    tags: list[str] = []

    if obs["navigation"]["gnss_fix_quality"] == "NORMAL":
        tags.append("GNSS_PRIMARY")
    if obs["navigation"]["satellite_count"] < 5 or obs["navigation"]["hdop"] > 5.0:
        tags.append("GNSS_DEGRADED")
    if _gnss_internal_conflict(obs["navigation"]):
        tags.append("GNSS_INTERNAL_CONFLICT")
    if obs["comms"]["encrypted"]:
        tags.append("C2_ENCRYPTED")
    if not obs["comms"]["payload_visible"]:
        tags.append("PAYLOAD_HIDDEN")
    if obs["c2_message"]["signature_present"]:
        tags.append("SIGNATURE_PRESENT")
    if obs["c2_message"]["auth_valid"]:
        tags.append("AUTH_VALID")
    else:
        tags.append("AUTH_INVALID")
    if not obs["c2_message"]["checksum_valid"]:
        tags.append("CHECKSUM_INVALID")
    if obs["comms"]["latency_ms"] > 500:
        tags.append("HIGH_LATENCY")
    if obs["comms"]["packet_loss"] > 0.10:
        tags.append("PACKET_LOSS_HIGH")
    if obs["comms"]["message_queue_depth"] > 10:
        tags.append("QUEUE_DEPTH_HIGH")
    if obs["comms"]["request_rate"] > 10:
        tags.append("REQUEST_RATE_HIGH")

    if obs["c2_message"]["sequence_number"] < history["last_sequence_number"]:
        tags.append("SEQUENCE_REGRESSION")
        tags.append("REPLAY_SUSPECTED")
    if obs["time"]["received_timestamp"] < history["last_received_timestamp"]:
        tags.append("TIMESTAMP_SKEW")
        if "REPLAY_SUSPECTED" not in tags:
            tags.append("REPLAY_SUSPECTED")
    if _command_time_inconsistent(obs, history):
        tags.append("COMMAND_TIMING_INCONSISTENT")

    telemetry = obs["telemetry"]
    last_telemetry = history["last_telemetry"]
    if telemetry["battery_percent"] - last_telemetry["battery_percent"] > 25 and telemetry["battery_drain_rate"] > 0:
        tags.append("TELEMETRY_CONFLICT")
    if telemetry["battery_percent"] > 70 and telemetry["motor_status"] == "OK" and telemetry["battery_drain_rate"] >= 0.8:
        tags.append("BATTERY_MOTOR_INCONSISTENT")
    if _battery_energy_impossible(obs, history):
        tags.append("BATTERY_ENERGY_IMPOSSIBLE")
    if _imu_telemetry_divergence(obs, history):
        tags.append("IMU_TELEMETRY_DIVERGENCE")

    priority_delta = max(
        abs(obs["mission"]["area_priority"][area] - history["last_area_priority"][area])
        for area in obs["mission"]["area_priority"]
    )
    if priority_delta > 0.35:
        tags.append("MISSION_PRIORITY_CHANGED")

    return sorted(set(tags))


def _battery_energy_impossible(obs: dict, history: dict) -> bool:
    telemetry = obs["telemetry"]
    last_telemetry = history["last_telemetry"]
    elapsed_seconds = max(0, obs["time"]["received_timestamp"] - history["last_received_timestamp"])
    elapsed_minutes = elapsed_seconds / 60
    expected_max = (
        last_telemetry["battery_percent"]
        - last_telemetry.get("battery_drain_rate", telemetry["battery_drain_rate"]) * elapsed_minutes
        + TELEMETRY_BATTERY_TOLERANCE
    )
    return telemetry["battery_drain_rate"] > 0 and telemetry["battery_percent"] > expected_max


def _gnss_internal_conflict(navigation: dict) -> bool:
    if navigation["gnss_fix_quality"] != "NORMAL":
        return False
    weak_signal = navigation.get("cn0_avg", 99.0) < 25.0
    poor_geometry = navigation["satellite_count"] < 5 or navigation["hdop"] > 5.0
    return weak_signal or poor_geometry


def _imu_telemetry_divergence(obs: dict, history: dict) -> bool:
    last_navigation = history.get("last_navigation")
    if not last_navigation:
        return False

    current = obs["navigation"].get("imu_position_estimate")
    previous = last_navigation.get("imu_position_estimate")
    if not current or not previous:
        return False

    elapsed_seconds = max(0, obs["time"]["received_timestamp"] - history["last_received_timestamp"])
    distance_m = _distance_m(previous, current)
    max_distance_m = obs["telemetry"]["speed_mps"] * elapsed_seconds + GNSS_IMU_DRIFT_TOLERANCE_M
    return distance_m > max_distance_m


def _command_time_inconsistent(obs: dict, history: dict) -> bool:
    sequence_delta = obs["c2_message"]["sequence_number"] - history["last_sequence_number"]
    time_delta = obs["time"]["received_timestamp"] - history["last_received_timestamp"]
    if sequence_delta <= 0:
        return False
    expected_time_delta = sequence_delta * ROUND_SECONDS
    return abs(time_delta - expected_time_delta) > ROUND_SECONDS


def _distance_m(previous: dict, current: dict) -> float:
    lat_scale = 111_320
    lon_scale = lat_scale * cos(radians((previous["lat"] + current["lat"]) / 2))
    d_lat = (current["lat"] - previous["lat"]) * lat_scale
    d_lon = (current["lon"] - previous["lon"]) * lon_scale
    return sqrt(d_lat * d_lat + d_lon * d_lon)
