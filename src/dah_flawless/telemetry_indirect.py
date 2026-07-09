"""Observed-only telemetry-memory evidence for indirect trust erosion."""

from __future__ import annotations

from typing import Any


def telemetry_memory_confusion_evidence(observed: dict[str, Any]) -> dict[str, Any]:
    """Score command/ACK ambiguity that is anchored in read-only telemetry memory."""

    channels = observed.get("telemetry_channels") or observed.get("external_observe", {}).get("telemetry_channels", {})
    asset_tx = channels.get("asset_tx_mirror", {})
    ground_rx = channels.get("ground_rx_view", {})
    c2_message = observed.get("c2_message", {})
    comms = observed.get("comms", {})
    ack = c2_message.get("ack", {})

    sequence_number = _as_int(c2_message.get("sequence_number"), 0)
    ack_sequence = _as_int(ack.get("sequence_number"), sequence_number)
    ack_gap = abs(sequence_number - ack_sequence)
    ack_delay_ms = _as_int(comms.get("ack_delay_ms"), 0)
    latency_ms = _as_int(comms.get("latency_ms"), 0)
    jitter_ms = _as_int(comms.get("packet_interval_jitter_ms"), 0)
    freshness_s = _as_float(ground_rx.get("freshness_s"))
    rx_confidence = _as_float(ground_rx.get("confidence"))
    battery_delta = _numeric_delta(ground_rx.get("battery_percent"), asset_tx.get("battery_percent"))
    motor_mismatch = (
        ground_rx.get("motor_status") is not None
        and asset_tx.get("motor_status") is not None
        and ground_rx.get("motor_status") != asset_tx.get("motor_status")
    )
    memory_anchor_present = bool(asset_tx or ground_rx)
    read_only_confirmed = memory_anchor_present and not bool(
        asset_tx.get("red_direct_mutation_allowed", False)
    ) and not bool(ground_rx.get("red_direct_mutation_allowed", False))
    low_confidence_rx = rx_confidence is not None and rx_confidence < 0.75
    stale_rx = freshness_s is not None and freshness_s > 2.0
    command_decoy = _is_command_decoy(c2_message.get("command"), asset_tx)

    effect_score = min(
        1.0,
        ack_gap / 4.0
        + max(0, ack_delay_ms - 250) / 1400.0
        + max(0, latency_ms - 250) / 1200.0
        + max(0, jitter_ms - 100) / 1200.0
        + (0.12 if command_decoy else 0.0)
        + (0.08 if stale_rx else 0.0)
        + (0.06 if low_confidence_rx else 0.0),
    )
    if not memory_anchor_present:
        effect_score = min(effect_score, 0.20)

    return {
        "telemetry_memory_anchor_present": memory_anchor_present,
        "telemetry_memory_read_only_confirmed": read_only_confirmed,
        "asset_tx_battery_percent": asset_tx.get("battery_percent"),
        "ground_rx_battery_percent": ground_rx.get("battery_percent"),
        "battery_delta_rx_minus_tx": battery_delta,
        "motor_mismatch_rx_tx": motor_mismatch,
        "rx_confidence": rx_confidence,
        "freshness_s": freshness_s,
        "command_decoy": command_decoy,
        "ack_visible": bool(comms.get("ack_visible") or ack.get("visible")),
        "sequence_number": sequence_number,
        "ack_sequence_number": ack_sequence,
        "ack_gap": ack_gap,
        "ack_delay_ms": ack_delay_ms,
        "latency_ms": latency_ms,
        "packet_interval_jitter_ms": jitter_ms,
        "indirect_effect_score": round(effect_score, 4),
    }


def _is_command_decoy(command: Any, asset_tx: dict[str, Any]) -> bool:
    battery = asset_tx.get("battery_percent")
    motor = asset_tx.get("motor_status")
    safety_critical = (isinstance(battery, (int, float)) and float(battery) <= 25.0) or motor not in {None, "OK"}
    return bool(safety_critical and command in {"CONTINUE_MISSION", "HOLD_POSITION"})


def _numeric_delta(after: Any, before: Any) -> float | None:
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return None
    return round(float(after) - float(before), 4)


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 4)
