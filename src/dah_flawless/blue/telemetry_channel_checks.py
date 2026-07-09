"""Blue-side telemetry channel consistency checks."""

from __future__ import annotations

from typing import Any


TELEMETRY_CHANNEL_CHECK_SCHEMA_ID = "dah.blue_telemetry_channel_checks.v0_1"


def analyze_telemetry_channel_checks(observed_state: dict[str, Any]) -> dict[str, Any]:
    """Split telemetry detection into internal/tx, tx/rx, rx/command, freshness checks."""

    obs = observed_state.get("blue_observed", observed_state)
    channels = obs.get("telemetry_channels") or obs.get("external_observe", {}).get("telemetry_channels", {})
    internal = obs.get("internal_observe", {}).get("telemetry", {})
    asset_tx = channels.get("asset_tx_mirror") or internal
    ground_rx = channels.get("ground_rx_view") or obs.get("telemetry", {})
    link_summary = channels.get("link_summary", {})
    comms = obs.get("comms", {})
    c2_message = obs.get("c2_message", {})

    checks = {
        "internal_vs_tx": _internal_vs_tx_check(internal, asset_tx),
        "tx_vs_rx": _tx_vs_rx_check(asset_tx, ground_rx),
        "rx_vs_command": _rx_vs_command_check(ground_rx, c2_message, comms),
        "freshness": _freshness_check(ground_rx, link_summary, comms),
    }
    tags: list[str] = []
    evidence: list[str] = []
    for check_id, check in checks.items():
        if check["status"] != "PASS":
            tags.extend(check["tags"])
            evidence.extend(f"{check_id}:{item}" for item in check["evidence"])

    return {
        "schema_id": TELEMETRY_CHANNEL_CHECK_SCHEMA_ID,
        "checks": checks,
        "failed_checks": [check_id for check_id, check in checks.items() if check["status"] != "PASS"],
        "tags": tuple(dict.fromkeys(tags)),
        "evidence": tuple(evidence),
        "max_score": round(max((float(check["score"]) for check in checks.values()), default=0.0), 4),
    }


def _internal_vs_tx_check(internal: dict[str, Any], asset_tx: dict[str, Any]) -> dict[str, Any]:
    battery_gap = abs(_as_float(asset_tx.get("battery_percent")) - _as_float(internal.get("battery_percent")))
    drain_gap = abs(_as_float(asset_tx.get("battery_drain_rate")) - _as_float(internal.get("battery_drain_rate")))
    motor_mismatch = _mismatch(asset_tx.get("motor_status"), internal.get("motor_status"))
    score = min(1.0, battery_gap / 8.0 + drain_gap / 1.5 + (0.50 if motor_mismatch else 0.0))
    return _check(
        "internal_vs_tx",
        score,
        ("TELEMETRY_INTERNAL_TX_DISAGREE",),
        (
            f"internal.battery_percent={internal.get('battery_percent')}",
            f"asset_tx.battery_percent={asset_tx.get('battery_percent')}",
            f"battery_gap={round(battery_gap, 4)}",
            f"motor_mismatch={motor_mismatch}",
        ),
    )


def _tx_vs_rx_check(asset_tx: dict[str, Any], ground_rx: dict[str, Any]) -> dict[str, Any]:
    battery_gap = abs(_as_float(ground_rx.get("battery_percent")) - _as_float(asset_tx.get("battery_percent")))
    drain_gap = abs(_as_float(ground_rx.get("battery_drain_rate")) - _as_float(asset_tx.get("battery_drain_rate")))
    motor_mismatch = _mismatch(ground_rx.get("motor_status"), asset_tx.get("motor_status"))
    score = min(1.0, battery_gap / 8.0 + drain_gap / 1.5 + (0.50 if motor_mismatch else 0.0))
    return _check(
        "tx_vs_rx",
        score,
        ("TELEMETRY_TX_RX_DISAGREE",),
        (
            f"asset_tx.battery_percent={asset_tx.get('battery_percent')}",
            f"ground_rx.battery_percent={ground_rx.get('battery_percent')}",
            f"battery_gap={round(battery_gap, 4)}",
            f"motor_mismatch={motor_mismatch}",
        ),
    )


def _rx_vs_command_check(ground_rx: dict[str, Any], c2_message: dict[str, Any], comms: dict[str, Any]) -> dict[str, Any]:
    ack = c2_message.get("ack", {})
    sequence_number = _as_int(c2_message.get("sequence_number"), 0)
    ack_sequence = _as_int(ack.get("sequence_number"), sequence_number)
    ack_gap = abs(sequence_number - ack_sequence)
    ack_delay_ms = _as_int(comms.get("ack_delay_ms"), 0)
    latency_ms = _as_int(comms.get("latency_ms"), 0)
    jitter_ms = _as_int(comms.get("packet_interval_jitter_ms"), 0)
    safety_critical_rx = _as_float(ground_rx.get("battery_percent"), 100.0) <= 25.0 or ground_rx.get("motor_status") != "OK"
    command = c2_message.get("command")
    unsafe_command = command in {"CONTINUE_MISSION", "HOLD_POSITION"}
    accepted_with_gap = ack.get("status") == "ACCEPTED" and ack_gap > 0
    score = min(
        1.0,
        (0.48 if safety_critical_rx and unsafe_command else 0.0)
        + (0.20 if accepted_with_gap else 0.0)
        + min(0.20, max(0, ack_delay_ms - 250) / 1200.0)
        + min(0.12, max(0, latency_ms - 250) / 1200.0)
        + min(0.10, max(0, jitter_ms - 100) / 1000.0),
    )
    return _check(
        "rx_vs_command",
        score,
        ("TELEMETRY_RX_COMMAND_INCONSISTENT",),
        (
            f"ground_rx.battery_percent={ground_rx.get('battery_percent')}",
            f"ground_rx.motor_status={ground_rx.get('motor_status')}",
            f"c2_message.command={command}",
            f"ack_gap={ack_gap}",
            f"ack_delay_ms={ack_delay_ms}",
            f"safety_critical_rx={safety_critical_rx}",
            f"unsafe_command={unsafe_command}",
        ),
    )


def _freshness_check(ground_rx: dict[str, Any], link_summary: dict[str, Any], comms: dict[str, Any]) -> dict[str, Any]:
    freshness_s = _as_float(ground_rx.get("freshness_s"))
    latency_ms = _as_int(link_summary.get("latency_ms", comms.get("latency_ms")), 0)
    jitter_ms = _as_int(link_summary.get("packet_interval_jitter_ms", comms.get("packet_interval_jitter_ms")), 0)
    heartbeat_gap_ms = _as_int(link_summary.get("heartbeat_gap_ms", comms.get("heartbeat_gap_ms")), 0)
    packet_loss = _as_float(link_summary.get("packet_loss", comms.get("packet_loss")), 0.0)
    rx_confidence = _as_float(ground_rx.get("confidence"), 1.0)
    score = min(
        1.0,
        max(0.0, freshness_s - 2.0) / 8.0
        + max(0, latency_ms - 350) / 1400.0
        + max(0, jitter_ms - 120) / 1200.0
        + heartbeat_gap_ms / 7000.0
        + packet_loss * 1.2
        + (0.12 if rx_confidence < 0.55 else 0.0),
    )
    return _check(
        "freshness",
        score,
        ("TELEMETRY_FRESHNESS_RISK",),
        (
            f"ground_rx.freshness_s={ground_rx.get('freshness_s')}",
            f"ground_rx.confidence={ground_rx.get('confidence')}",
            f"latency_ms={latency_ms}",
            f"packet_interval_jitter_ms={jitter_ms}",
            f"heartbeat_gap_ms={heartbeat_gap_ms}",
            f"packet_loss={round(packet_loss, 4)}",
        ),
    )


def _check(check_id: str, score: float, tags: tuple[str, ...], evidence: tuple[str, ...]) -> dict[str, Any]:
    score = round(min(1.0, max(0.0, float(score))), 4)
    status = "FAIL" if score >= 0.45 else "WARN" if score >= 0.20 else "PASS"
    return {
        "check_id": check_id,
        "status": status,
        "score": score,
        "tags": tags if status != "PASS" else (),
        "evidence": evidence,
    }


def _mismatch(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    return left != right


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)
