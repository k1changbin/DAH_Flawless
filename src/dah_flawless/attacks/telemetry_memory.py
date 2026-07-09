"""Red-side read-only memory for telemetry tx/rx channel observations."""

from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any


TELEMETRY_MEMORY_SCHEMA_VERSION = "dah.red_telemetry_memory.v0_1"
DEFAULT_TELEMETRY_MEMORY_WINDOW = 12
LOW_CONFIDENCE_THRESHOLD = 0.75
STALE_FRESHNESS_THRESHOLD_S = 2.0


class TelemetryMemory:
    """Bounded Red memory of telemetry channel projections.

    This is intentionally read-only. It records telemetry tx/rx projections that
    are already visible in Red's redacted observe view, and it exposes compact
    features for future indirect command/timing tactics.
    """

    def __init__(self, records: list[dict] | None = None, *, max_records: int = DEFAULT_TELEMETRY_MEMORY_WINDOW):
        if max_records < 1:
            raise ValueError("max_records must be >= 1")
        self.max_records = max_records
        self._records = list(records or [])[-self.max_records :]

    def observe(self, observed_state: dict[str, Any], *, round_number: int) -> dict[str, Any]:
        record = build_telemetry_memory_record(observed_state, round_number=round_number)
        if record is not None:
            self._records.append(record)
            self._records = self._records[-self.max_records :]
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_id": TELEMETRY_MEMORY_SCHEMA_VERSION,
            "memory_type": "red_read_only_telemetry_channel_memory",
            "max_records": self.max_records,
            "record_count": len(self._records),
            "records": deepcopy(self._records),
            "latest": deepcopy(self._records[-1]) if self._records else None,
            "features": _memory_features(self._records),
            "policy": {
                "source": "blue_observed.telemetry_channels",
                "red_can_read": True,
                "red_direct_mutation_allowed": False,
                "allowed_use": "memory_features_for_future_indirect_actions",
            },
        }

    def export_state(self) -> dict[str, Any]:
        return {
            "schema_id": TELEMETRY_MEMORY_SCHEMA_VERSION,
            "max_records": self.max_records,
            "records": deepcopy(self._records),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any] | None) -> "TelemetryMemory":
        if not state:
            return cls()
        return cls(
            records=deepcopy(state.get("records", [])),
            max_records=int(state.get("max_records", DEFAULT_TELEMETRY_MEMORY_WINDOW)),
        )


def build_telemetry_memory_record(observed_state: dict[str, Any], *, round_number: int) -> dict[str, Any] | None:
    channels = _telemetry_channels(observed_state)
    if not channels:
        return None
    asset_tx = deepcopy(channels.get("asset_tx_mirror", {}))
    ground_rx = deepcopy(channels.get("ground_rx_view", {}))
    link_summary = deepcopy(channels.get("link_summary", {}))
    if not asset_tx and not ground_rx:
        return None

    battery_delta = _numeric_delta(ground_rx.get("battery_percent"), asset_tx.get("battery_percent"))
    motor_mismatch = _motor_mismatch(ground_rx.get("motor_status"), asset_tx.get("motor_status"))
    return {
        "round": round_number,
        "schema_id": "dah.red_telemetry_memory_record.v0_1",
        "source_schema_id": channels.get("schema_id"),
        "asset_tx_mirror": _compact_telemetry_endpoint(asset_tx),
        "ground_rx_view": _compact_telemetry_endpoint(ground_rx),
        "link_summary": {
            "channel": link_summary.get("channel"),
            "latency_ms": link_summary.get("latency_ms"),
            "packet_loss": link_summary.get("packet_loss"),
            "packet_interval_jitter_ms": link_summary.get("packet_interval_jitter_ms"),
            "ack_delay_ms": link_summary.get("ack_delay_ms"),
            "heartbeat_gap_ms": link_summary.get("heartbeat_gap_ms"),
        },
        "derived": {
            "battery_delta_rx_minus_tx": battery_delta,
            "abs_battery_delta": abs(battery_delta) if battery_delta is not None else None,
            "motor_mismatch": motor_mismatch,
            "rx_confidence": _as_float_or_none(ground_rx.get("confidence")),
            "freshness_s": _as_float_or_none(ground_rx.get("freshness_s")),
            "read_only_confirmed": not bool(asset_tx.get("red_direct_mutation_allowed", False))
            and not bool(ground_rx.get("red_direct_mutation_allowed", False)),
        },
        "intended_red_use": "remember_patterns_then_choose_indirect_command_or_timing_actions",
    }


def _telemetry_channels(observed_state: dict[str, Any]) -> dict[str, Any]:
    blue_observed = observed_state.get("blue_observed", observed_state)
    channels = blue_observed.get("telemetry_channels")
    if channels:
        return channels
    return blue_observed.get("external_observe", {}).get("telemetry_channels", {})


def _compact_telemetry_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(endpoint.get(key))
        for key in (
            "battery_percent",
            "battery_drain_rate",
            "motor_status",
            "altitude_m",
            "speed_mps",
            "heading_deg",
            "timestamp",
            "received_timestamp",
            "frame_seq",
            "confidence",
            "freshness_s",
            "source",
            "red_visible",
            "red_direct_mutation_allowed",
            "mutation_policy",
        )
        if key in endpoint
    }


def _memory_features(records: list[dict]) -> dict[str, Any]:
    if not records:
        return {
            "record_count": 0,
            "pattern_hint": "no_telemetry_memory",
            "avg_abs_battery_delta": 0.0,
            "max_abs_battery_delta": 0.0,
            "motor_mismatch_count": 0,
            "low_confidence_count": 0,
            "stale_rx_count": 0,
        }
    deltas = [
        float(record["derived"]["abs_battery_delta"])
        for record in records
        if record.get("derived", {}).get("abs_battery_delta") is not None
    ]
    confidences = [
        float(record["derived"]["rx_confidence"])
        for record in records
        if record.get("derived", {}).get("rx_confidence") is not None
    ]
    stale_count = sum(
        1
        for record in records
        if (record.get("derived", {}).get("freshness_s") is not None)
        and float(record["derived"]["freshness_s"]) > STALE_FRESHNESS_THRESHOLD_S
    )
    mismatch_count = sum(1 for record in records if record.get("derived", {}).get("motor_mismatch"))
    low_confidence_count = sum(1 for value in confidences if value < LOW_CONFIDENCE_THRESHOLD)
    latest = records[-1]
    return {
        "record_count": len(records),
        "round_span": [records[0].get("round"), latest.get("round")],
        "avg_abs_battery_delta": round(mean(deltas), 4) if deltas else 0.0,
        "max_abs_battery_delta": round(max(deltas), 4) if deltas else 0.0,
        "motor_mismatch_count": mismatch_count,
        "low_confidence_count": low_confidence_count,
        "stale_rx_count": stale_count,
        "latest_rx_confidence": confidences[-1] if confidences else None,
        "latest_asset_tx_battery": latest.get("asset_tx_mirror", {}).get("battery_percent"),
        "latest_ground_rx_battery": latest.get("ground_rx_view", {}).get("battery_percent"),
        "pattern_hint": _pattern_hint(deltas, mismatch_count, low_confidence_count, stale_count),
    }


def _pattern_hint(
    abs_battery_deltas: list[float],
    motor_mismatch_count: int,
    low_confidence_count: int,
    stale_rx_count: int,
) -> str:
    if stale_rx_count:
        return "stale_rx_memory"
    if low_confidence_count:
        return "low_confidence_rx_memory"
    if motor_mismatch_count:
        return "motor_mismatch_memory"
    if abs_battery_deltas and max(abs_battery_deltas) >= 3.0:
        return "battery_delta_memory"
    return "stable_tx_rx_alignment"


def _numeric_delta(after: Any, before: Any) -> float | None:
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return None
    return round(float(after) - float(before), 4)


def _motor_mismatch(rx_status: Any, tx_status: Any) -> bool:
    if rx_status is None or tx_status is None:
        return False
    return rx_status != tx_status


def _as_float_or_none(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 4)
