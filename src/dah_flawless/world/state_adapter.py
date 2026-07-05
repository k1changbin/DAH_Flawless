"""Adapt generated raw-world samples into the MVP simulation state."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from dah_flawless.environment.state_factory import create_baseline_state
from dah_flawless.observation import refresh_internal_observe_from_truth, sync_external_observe_from_flat
from dah_flawless.world.feature_extractor import RawWorldFeatureExtractor


def build_state_from_raw_world(
    sample: dict[str, Any],
    seed: int,
    scenario: str = "raw_world_start",
) -> dict:
    """Create a simulation initial state from a generated raw-world sample.

    The raw-world sample is converted into scorer truth plus observed values.
    For MVP compatibility, scorer truth is stored under ``state["world"]``.
    Blue and Red receive only the observed projection through redaction.
    """

    state = create_baseline_state(seed=seed)
    raw_world = sample.get("raw_world", sample)
    feature_row = RawWorldFeatureExtractor().extract(sample)
    features = feature_row["features"]

    state["scenario"] = scenario
    state["world"]["raw_world_hash"] = sample.get("raw_world_hash", sample.get("world_hash"))
    state["world"]["raw_world_schema_id"] = sample.get("schema_id")
    state["world"]["raw_world_condition"] = deepcopy(sample.get("condition", {}))
    state["world"]["raw_world_feature_scores"] = deepcopy(feature_row["candidate_scores"])
    state["world"]["raw_world_feature_evidence"] = deepcopy(feature_row["evidence"])

    _apply_time(state, raw_world)
    _apply_environment(state, raw_world, features)
    _apply_mission(state, raw_world)
    _apply_uav_scene(state, raw_world)
    _apply_navigation_observation(state, features)
    _apply_c2_observation(state, raw_world, features)
    sync_external_observe_from_flat(state["blue_observed"])
    refresh_internal_observe_from_truth(state)
    _refresh_last_known_good(state)
    return state


def _apply_time(state: dict, raw_world: dict[str, Any]) -> None:
    time_reference = raw_world.get("time_reference", {})
    utc_ms = time_reference.get("utc_time_unix_ms")
    if utc_ms is not None:
        timestamp = int(utc_ms // 1000)
        state["world"]["time"]["true_timestamp"] = timestamp
        state["blue_observed"]["time"]["received_timestamp"] = timestamp
    clock_quality = float(time_reference.get("clock_reference_quality", 0.85))
    state["blue_observed"]["time"]["local_clock_offset_ms"] = int(round((1.0 - clock_quality) * 1000))


def _apply_environment(state: dict, raw_world: dict[str, Any], features: dict[str, Any]) -> None:
    condition = state["world"].get("raw_world_condition", {})
    weather = raw_world.get("weather_field", {})
    terrain = raw_world.get("terrain_field", {})
    gnss = features["gnss"]
    rf = raw_world.get("rf_spectrum", {})

    state["world"]["environment"] = {
        "weather": _weather_label(weather, condition.get("weather")),
        "terrain": condition.get("terrain", "UNKNOWN"),
        "rf_noise_level": _noise_level(rf.get("noise_floor_dbm", -96.0)),
        "gnss_interference": _gnss_interference_label(gnss),
        "terrain_occlusion_score": features["environment"]["terrain_occlusion_score"],
        "terrain_multipath_score": features["environment"]["terrain_multipath_score"],
        "visibility_m": weather.get("visibility_m"),
        "terrain_refs": {
            "dem_ref": terrain.get("dem_ref"),
            "landcover_ref": terrain.get("landcover_ref"),
        },
    }


def _apply_mission(state: dict, raw_world: dict[str, Any]) -> None:
    mission_space = raw_world.get("mission_space", {})
    targets = mission_space.get("targets", [])
    priorities = {}
    for idx, area in enumerate(("A", "B", "C")):
        if idx < len(targets):
            priorities[area] = float(targets[idx].get("priority_ground_truth", 0.2))
        else:
            priorities[area] = 0.2

    current_area = max(priorities, key=priorities.get)
    state["world"]["mission"]["current_area"] = current_area
    state["world"]["mission"]["area_priority"] = priorities
    state["blue_observed"]["mission"]["area_priority"] = deepcopy(priorities)
    state["blue_observed"]["mission"]["recommended_area"] = current_area


def _apply_uav_scene(state: dict, raw_world: dict[str, Any]) -> None:
    friendly_uav = _find_object(raw_world, "FRIENDLY_UAV")
    if not friendly_uav:
        return

    position = friendly_uav.get("position_truth") or []
    velocity = friendly_uav.get("velocity_truth_mps") or []
    if len(position) >= 3:
        state["world"]["uav"]["position"] = {
            "lat": position[0],
            "lon": position[1],
            "altitude_m": position[2],
        }
        state["blue_observed"]["telemetry"]["altitude_m"] = position[2]
        state["blue_observed"]["navigation"]["imu_position_estimate"] = {
            "lat": position[0],
            "lon": position[1],
        }
    if velocity:
        speed_mps = round(math.sqrt(sum(float(v) ** 2 for v in velocity)), 3)
        state["world"]["uav"]["speed_mps"] = speed_mps
        state["blue_observed"]["telemetry"]["speed_mps"] = speed_mps


def _apply_navigation_observation(state: dict, features: dict[str, Any]) -> None:
    gnss = features["gnss"]
    degradation = float(gnss["gnss_degradation_score"])
    satellite_count = int(gnss["satellite_count"])
    state["blue_observed"]["navigation"]["satellite_count"] = satellite_count
    state["blue_observed"]["navigation"]["cn0_avg"] = float(gnss["avg_cn0_dbhz"])
    state["blue_observed"]["navigation"]["hdop"] = round(1.0 + degradation * 7.0, 2)
    state["blue_observed"]["navigation"]["gnss_fix_quality"] = (
        "DEGRADED" if degradation > 0.55 or satellite_count < 5 else "NORMAL"
    )


def _apply_c2_observation(state: dict, raw_world: dict[str, Any], features: dict[str, Any]) -> None:
    frames = raw_world.get("uav_c2_emissions", {}).get("frames", [])
    command_frame = _latest_command_frame(frames)
    latest_frame = max(frames, key=lambda frame: frame.get("sequence_number", -1), default={})
    sequence_number = int(latest_frame.get("sequence_number", state["world"]["command"]["expected_sequence_number"]))
    command = _command_from_frame(command_frame)

    state["world"]["command"]["expected_sequence_number"] = sequence_number
    state["world"]["command"]["last_valid_command"] = command
    state["blue_observed"]["c2_message"]["sequence_number"] = sequence_number
    state["blue_observed"]["c2_message"]["command"] = command
    state["blue_observed"]["c2_message"]["sysid"] = int(command_frame.get("source_system_id", 255) if command_frame else 255)
    state["blue_observed"]["c2_message"]["compid"] = int(command_frame.get("source_component_id", 1) if command_frame else 1)
    state["blue_observed"]["c2_message"]["msgid"] = int(command_frame.get("message_id", 76) if command_frame else 76)
    state["blue_observed"]["c2_message"]["signature_present"] = bool(latest_frame.get("signature_present", True))
    state["blue_observed"]["c2_message"]["auth_valid"] = bool(latest_frame.get("signed", True))
    state["blue_observed"]["c2_message"]["ack"]["sequence_number"] = sequence_number

    link_profile = _link_profile_from_features(raw_world, features)
    state["world"]["link_profile"] = link_profile
    state["blue_observed"]["comms"].update(link_profile)


def _link_profile_from_features(raw_world: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    satcom = features["satcom"]
    mavlink = features["mavlink_c2"]
    channel = _channel_label(mavlink.get("channels", []))
    latency_ms = int(max(80, round(float(satcom.get("max_propagation_delay_ms") or 180))))
    availability = float(satcom.get("avg_availability_score") or 0.95)
    rain_fade = float(satcom.get("max_rain_fade_score") or 0.0)
    packet_loss = round(min(0.25, max(0.01, (1.0 - availability) * 0.35 + rain_fade * 0.12)), 3)
    interval_ms = _packet_interval_ms(raw_world)
    jitter_ms = int(max(18, round(latency_ms * 0.12 + packet_loss * 250)))
    return {
        "channel": channel,
        "encrypted": True,
        "payload_visible": False,
        "latency_ms": latency_ms,
        "packet_loss": packet_loss,
        "message_queue_depth": 3,
        "request_rate": round(max(2.0, float(mavlink.get("frame_count", 3)) * 1.4), 2),
        "packet_interval_ms": interval_ms,
        "packet_interval_jitter_ms": jitter_ms,
        "packet_size_bytes": 96,
        "packet_size_variance": 6,
        "ack_visible": True,
        "ack_delay_ms": int(latency_ms + 30),
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
    }


def _refresh_last_known_good(state: dict) -> None:
    state["last_known_good"] = deepcopy(state["blue_observed"])


def _find_object(raw_world: dict[str, Any], object_type: str) -> dict[str, Any] | None:
    for obj in raw_world.get("physical_scene", {}).get("objects", []):
        if obj.get("object_type") == object_type:
            return obj
    return None


def _latest_command_frame(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    commands = [frame for frame in frames if str(frame.get("message_name", "")).startswith("COMMAND")]
    return max(commands, key=lambda frame: frame.get("sequence_number", -1), default=None)


def _command_from_frame(frame: dict[str, Any] | None) -> str:
    if not frame:
        return "RETURN_TO_BASE"
    mav_command = str(frame.get("decoded_payload", {}).get("command", ""))
    if "RETURN" in mav_command:
        return "RETURN_TO_BASE"
    if "LOITER" in mav_command or "HOLD" in mav_command:
        return "HOLD_POSITION"
    return "CONTINUE_MISSION"


def _weather_label(weather: dict[str, Any], fallback: str | None) -> str:
    if fallback:
        return fallback
    if float(weather.get("precipitation_level", 0.0)) > 0.65:
        return "STORM"
    if int(weather.get("visibility_m", 10_000)) < 3500 or float(weather.get("fog_level", 0.0)) > 0.35:
        return "LOW_VISIBILITY"
    return "CLEAR"


def _gnss_interference_label(gnss_features: dict[str, Any]) -> str:
    if int(gnss_features.get("interference_source_count", 0)) <= 0:
        return "NONE"
    if float(gnss_features.get("interference_score", 0.0)) > 0.6:
        return "SPOOFING_OR_JAMMING"
    return "UNKNOWN"


def _noise_level(noise_floor_dbm: float) -> float:
    return round(max(0.0, min(1.0, (float(noise_floor_dbm) + 110.0) / 45.0)), 3)


def _channel_label(channels: list[str]) -> str:
    values = set(channels)
    if "BLOS_SATCOM" in values:
        return "SATCOM"
    if "MESH_RELAY" in values or "MESH" in values:
        return "MESH"
    if "LOS_RF" in values:
        return "LOS"
    return "UNKNOWN"


def _packet_interval_ms(raw_world: dict[str, Any]) -> int:
    frames = raw_world.get("uav_c2_emissions", {}).get("frames", [])
    times = sorted(int(frame.get("tx_time_ms", 0)) for frame in frames if frame.get("tx_time_ms") is not None)
    if len(times) < 2:
        return 1000
    gaps = [curr - prev for prev, curr in zip(times, times[1:]) if curr > prev]
    if not gaps:
        return 1000
    return int(max(80, round(sum(gaps) / len(gaps))))
