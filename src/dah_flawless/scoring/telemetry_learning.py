"""Telemetry split-channel evidence used by scoring and policy learning."""

from __future__ import annotations

from math import log2
from typing import Any

from dah_flawless.blue.telemetry_channel_checks import analyze_telemetry_channel_checks
from dah_flawless.telemetry_indirect import telemetry_memory_confusion_evidence


TELEMETRY_LEARNING_SCHEMA_ID = "dah.telemetry_learning_signal.v0_1"
TELEMETRY_LEARNING_AXIS_WEIGHTS = {
    "telemetry_command_confusion": 0.34,
    "stale_state_acceptance": 0.24,
    "wrong_safety_decision": 0.27,
    "tx_rx_consistency_pressure": 0.10,
    "legacy_sensor_delta": 0.05,
}
TELEMETRY_AXIS_DEFAULT_THRESHOLDS = {
    "telemetry_command_confusion": 0.30,
    "stale_state_acceptance": 0.35,
    "wrong_safety_decision": 0.35,
    "tx_rx_consistency_pressure": 0.45,
    "legacy_sensor_delta": 0.65,
}

UNSAFE_CONTINUE_COMMANDS = {"CONTINUE_MISSION", "HOLD_POSITION"}


def telemetry_learning_signal(state: dict[str, Any], *, include_world_truth: bool = True) -> dict[str, Any]:
    """Return weighted evidence axes for telemetry trust erosion.

    ``include_world_truth=False`` keeps the result usable by Red planning code:
    it only reads the observe surface and read-only telemetry channel records.
    """

    observed = state.get("blue_observed", state)
    world = state.get("world", {}) if include_world_truth else {}
    channel_checks = analyze_telemetry_channel_checks(observed)
    indirect = telemetry_memory_confusion_evidence(observed)
    check_scores = {
        check_id: float(check.get("score", 0.0)) for check_id, check in channel_checks.get("checks", {}).items()
    }
    legacy = _legacy_sensor_delta(observed, world)
    command = _command_confusion_score(check_scores, indirect)
    stale = _stale_state_score(observed, world, check_scores, indirect)
    safety = _wrong_safety_decision_score(observed, world, check_scores, indirect)
    tx_rx = max(check_scores.get("internal_vs_tx", 0.0), check_scores.get("tx_vs_rx", 0.0))
    axis_scores = {
        "telemetry_command_confusion": round(command, 4),
        "stale_state_acceptance": round(stale, 4),
        "wrong_safety_decision": round(safety, 4),
        "tx_rx_consistency_pressure": round(tx_rx, 4),
        "legacy_sensor_delta": round(float(legacy["score"]), 4),
    }
    weighted_score = round(
        sum(axis_scores[axis] * weight for axis, weight in TELEMETRY_LEARNING_AXIS_WEIGHTS.items()),
        4,
    )
    dominant_axis = max(axis_scores, key=lambda axis: axis_scores[axis])
    active_axes = [axis for axis, score in axis_scores.items() if score >= 0.20]
    axis_entropy = _axis_entropy(axis_scores)
    red_diversity_bonus = min(
        0.12,
        0.04 * max(0, len(active_axes) - 1) + 0.04 * _normalized_entropy(axis_entropy) + 0.04 * weighted_score,
    )

    return {
        "schema_id": TELEMETRY_LEARNING_SCHEMA_ID,
        "axis_weights": dict(TELEMETRY_LEARNING_AXIS_WEIGHTS),
        "axis_thresholds": dict(TELEMETRY_AXIS_DEFAULT_THRESHOLDS),
        "axis_scores": axis_scores,
        "weighted_effect_score": weighted_score,
        "dominant_axis": dominant_axis,
        "dominant_axis_score": axis_scores[dominant_axis],
        "active_axes": active_axes,
        "axis_entropy": round(axis_entropy, 4),
        "blue_policy_learning_value": round(min(1.0, weighted_score + 0.06 * len(active_axes)), 4),
        "red_policy_diversity_bonus": round(red_diversity_bonus, 4),
        "channel_check_scores": {name: round(value, 4) for name, value in check_scores.items()},
        "channel_check_status": {
            name: check.get("status") for name, check in channel_checks.get("checks", {}).items()
        },
        "telemetry_channel_checks": channel_checks,
        "indirect_evidence": indirect,
        "legacy_direct_evidence": legacy,
    }


def telemetry_goal_effect_score(signal: dict[str, Any]) -> float:
    axis_scores = signal.get("axis_scores", {})
    max_axis_score = max((float(value) for value in axis_scores.values()), default=0.0)
    active_axis_count = len(signal.get("active_axes", []) or [])
    weighted_score = float(signal.get("weighted_effect_score", 0.0))
    return round(min(1.0, max(weighted_score, max_axis_score * 0.88 + min(0.12, active_axis_count * 0.03))), 4)


def telemetry_goal_success(signal: dict[str, Any]) -> bool:
    axis_scores = signal.get("axis_scores", {})
    thresholds = signal.get("axis_thresholds", TELEMETRY_AXIS_DEFAULT_THRESHOLDS)
    legacy = signal.get("legacy_direct_evidence", {})
    if (
        float(legacy.get("battery_delta", 0.0)) >= 8.0
        or bool(legacy.get("motor_mismatch"))
        or bool(legacy.get("impossible_drain_hint"))
    ):
        return True
    if float(signal.get("weighted_effect_score", 0.0)) >= 0.42:
        return True
    return any(float(axis_scores.get(axis, 0.0)) >= float(thresholds.get(axis, 1.0)) for axis in axis_scores)


def _command_confusion_score(check_scores: dict[str, float], indirect: dict[str, Any]) -> float:
    ack_gap = int(indirect.get("ack_gap", 0) or 0)
    command_decoy = bool(indirect.get("command_decoy"))
    indirect_score = float(indirect.get("indirect_effect_score", 0.0))
    indirect_command = min(
        1.0,
        indirect_score * 0.72
        + (0.12 if command_decoy else 0.0)
        + min(0.14, ack_gap / 10.0),
    )
    return min(1.0, max(check_scores.get("rx_vs_command", 0.0), indirect_command))


def _stale_state_score(
    observed: dict[str, Any],
    world: dict[str, Any],
    check_scores: dict[str, float],
    indirect: dict[str, Any],
) -> float:
    c2 = observed.get("c2_message", {})
    observed_time = observed.get("time", {})
    sequence_lag = 0
    timestamp_lag = 0
    if world:
        sequence_lag = max(
            0,
            _as_int(world.get("command", {}).get("expected_sequence_number"), 0)
            - _as_int(c2.get("sequence_number"), 0),
        )
        timestamp_lag = max(
            0,
            _as_int(world.get("time", {}).get("true_timestamp"), 0)
            - _as_int(observed_time.get("received_timestamp"), 0),
        )
    ack_delay_ms = _as_int(indirect.get("ack_delay_ms"), 0)
    latency_ms = _as_int(indirect.get("latency_ms"), 0)
    jitter_ms = _as_int(indirect.get("packet_interval_jitter_ms"), 0)
    stale_from_command = min(1.0, sequence_lag / 8.0 + timestamp_lag / 180.0)
    stale_from_timing = min(
        1.0,
        max(0, ack_delay_ms - 250) / 1800.0
        + max(0, latency_ms - 350) / 1600.0
        + max(0, jitter_ms - 120) / 1500.0,
    )
    return min(1.0, max(check_scores.get("freshness", 0.0), stale_from_command, stale_from_timing))


def _wrong_safety_decision_score(
    observed: dict[str, Any],
    world: dict[str, Any],
    check_scores: dict[str, float],
    indirect: dict[str, Any],
) -> float:
    telemetry = observed.get("telemetry", {})
    channels = observed.get("telemetry_channels") or observed.get("external_observe", {}).get("telemetry_channels", {})
    asset_tx = channels.get("asset_tx_mirror", {})
    ground_rx = channels.get("ground_rx_view", {})
    truth_uav = world.get("uav", {}) or asset_tx
    truth_mission = world.get("mission", {})
    command = observed.get("c2_message", {}).get("command")

    truth_battery = _as_float(truth_uav.get("battery_percent"))
    observed_battery = _as_float(telemetry.get("battery_percent"))
    rx_battery = _as_float(ground_rx.get("battery_percent"))
    truth_motor = truth_uav.get("motor_status")
    observed_motor = telemetry.get("motor_status")
    rx_motor = ground_rx.get("motor_status")
    return_required = bool(truth_mission.get("return_required"))
    safety_critical = return_required or truth_battery <= 25.0 or truth_motor not in {None, "OK"}
    observed_looks_safe = observed_battery >= 45.0 or observed_motor == "OK"
    rx_looks_safe = rx_battery >= 45.0 or rx_motor == "OK"
    unsafe_command = command in UNSAFE_CONTINUE_COMMANDS or (return_required and command != "RETURN_TO_BASE")
    battery_false_safe = truth_battery <= 25.0 and max(observed_battery, rx_battery) >= 45.0
    hidden_fault = truth_motor not in {None, "OK"} and (observed_motor == "OK" or rx_motor == "OK")
    command_decoy = bool(indirect.get("command_decoy"))

    score = 0.0
    score += 0.35 if battery_false_safe else 0.0
    score += 0.25 if hidden_fault else 0.0
    score += 0.25 if safety_critical and unsafe_command else 0.0
    score += 0.15 if command_decoy else 0.0
    score += 0.12 if safety_critical and (observed_looks_safe or rx_looks_safe) else 0.0
    score += min(0.16, check_scores.get("rx_vs_command", 0.0) * 0.34)
    return min(1.0, score)


def _legacy_sensor_delta(observed: dict[str, Any], world: dict[str, Any]) -> dict[str, Any]:
    telemetry = observed.get("telemetry", {})
    truth_uav = world.get("uav", {})
    if not truth_uav:
        channels = observed.get("telemetry_channels") or observed.get("external_observe", {}).get("telemetry_channels", {})
        truth_uav = channels.get("asset_tx_mirror", {})
    true_battery = _as_float(truth_uav.get("battery_percent"))
    observed_battery = _as_float(telemetry.get("battery_percent"))
    battery_delta = abs(observed_battery - true_battery)
    motor_mismatch = telemetry.get("motor_status") != truth_uav.get("motor_status")
    impossible_drain = _as_float(telemetry.get("battery_drain_rate")) >= 0.8 and observed_battery > true_battery
    score = min(1.0, battery_delta / 35.0 + (0.25 if motor_mismatch else 0.0) + (0.20 if impossible_drain else 0.0))
    return {
        "battery_delta": round(battery_delta, 4),
        "motor_mismatch": bool(motor_mismatch),
        "impossible_drain_hint": bool(impossible_drain),
        "score": round(score, 4),
    }


def _axis_entropy(axis_scores: dict[str, float]) -> float:
    values = [max(0.0, float(value)) for value in axis_scores.values()]
    total = sum(values)
    if total <= 0:
        return 0.0
    return -sum((value / total) * log2(value / total) for value in values if value > 0)


def _normalized_entropy(axis_entropy: float) -> float:
    axis_count = max(1, len(TELEMETRY_LEARNING_AXIS_WEIGHTS))
    return min(1.0, max(0.0, axis_entropy / log2(axis_count)))


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)
