"""Helpers for the Blue observe model.

The canonical model separates Blue input into internal and external observe
surfaces. Existing MVP code still reads the flat ``blue_observed`` keys, so this
module keeps compatibility aliases while making the trust boundary explicit.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


OBSERVE_SCHEMA_VERSION = "dah.observe.v0_3"
TELEMETRY_CHANNEL_SCHEMA_VERSION = "dah.telemetry_channels.v0_1"
RED_VISIBILITY_POLICY_ID = "dah.red_visibility.v0_1"

LEGACY_EXTERNAL_OBSERVE_KEYS = (
    "time",
    "telemetry",
    "navigation",
    "mission",
    "c2_message",
    "comms",
)
EXTERNAL_OBSERVE_KEYS = (*LEGACY_EXTERNAL_OBSERVE_KEYS, "telemetry_channels")

RED_MUTABLE_EXTERNAL_KEYS = (
    "time",
    "telemetry",
    "navigation",
    "mission",
    "c2_message",
    "comms",
)
RED_TELEMETRY_CHANNEL_READ_PATHS = (
    "blue_observed.external_observe.telemetry_channels.asset_tx_mirror",
    "blue_observed.external_observe.telemetry_channels.ground_rx_view",
    "blue_observed.external_observe.telemetry_channels.link_summary",
    "blue_observed.telemetry_channels.asset_tx_mirror",
    "blue_observed.telemetry_channels.ground_rx_view",
    "blue_observed.telemetry_channels.link_summary",
)
RED_TELEMETRY_CHANNEL_MUTATION_EXCLUDED_PATHS = (
    "blue_observed.external_observe.telemetry_channels.*",
    "blue_observed.telemetry_channels.*",
)


def build_blue_observed(
    *,
    internal_observe: dict[str, Any],
    external_observe: dict[str, Any],
) -> dict[str, Any]:
    """Build a Blue observe object with canonical and compatibility views."""

    observed = {
        "observe_schema_version": OBSERVE_SCHEMA_VERSION,
        "internal_observe": deepcopy(internal_observe),
        "external_observe": deepcopy(external_observe),
        "observe_access": {
            "red_direct_mutation": {
                "internal_observe": False,
                "external_observe": True,
                "allowed_external_domains": list(RED_MUTABLE_EXTERNAL_KEYS),
                "read_only_external_domains": ["telemetry_channels"],
            },
            "red_can_read": {
                "external_observe": True,
                "telemetry_channels": True,
                "telemetry_channels_intended_use": "pattern_memory_and_situation_awareness_only",
            },
            "blue_can_read": {
                "internal_observe": True,
                "external_observe": True,
            },
        },
    }
    attach_red_visibility_policy(observed)
    attach_flat_observe_aliases(observed)
    return observed


def build_red_visibility_policy() -> dict[str, Any]:
    """Return Red read/mutation boundaries for observe data."""

    return {
        "policy_id": RED_VISIBILITY_POLICY_ID,
        "scope": "red_observe_visibility",
        "can_read": {
            "telemetry_channel_paths": list(RED_TELEMETRY_CHANNEL_READ_PATHS),
            "intended_use": [
                "telemetry_pattern_memory",
                "situation_awareness",
                "indirect_command_or_timing_action_selection",
            ],
        },
        "mutation_excluded": {
            "paths": list(RED_TELEMETRY_CHANNEL_MUTATION_EXCLUDED_PATHS),
            "reason": "telemetry tx/rx records are read-only intel; Red may use them for memory, not direct field mutation",
        },
        "direct_mutation_allowed": {
            "external_domains": list(RED_MUTABLE_EXTERNAL_KEYS),
            "note": "telemetry_channels is intentionally excluded",
        },
    }


def attach_red_visibility_policy(blue_observed: dict[str, Any]) -> dict[str, Any]:
    """Attach the Red observe visibility policy without changing observe values."""

    access = blue_observed.setdefault("observe_access", {})
    access["red_visibility"] = build_red_visibility_policy()
    return blue_observed


def attach_flat_observe_aliases(blue_observed: dict[str, Any]) -> dict[str, Any]:
    """Expose legacy flat keys as aliases of ``external_observe`` domains."""

    refresh_telemetry_channels(blue_observed)
    attach_red_visibility_policy(blue_observed)
    external = blue_observed.setdefault("external_observe", {})
    for key in EXTERNAL_OBSERVE_KEYS:
        if key in external:
            blue_observed[key] = external[key]
    return blue_observed


def sync_external_observe_from_flat(blue_observed: dict[str, Any]) -> dict[str, Any]:
    """Persist legacy flat-domain updates back into ``external_observe``."""

    external = blue_observed.setdefault("external_observe", {})
    for key in LEGACY_EXTERNAL_OBSERVE_KEYS:
        if key in blue_observed:
            external[key] = blue_observed[key]
    refresh_telemetry_channels(blue_observed)
    attach_red_visibility_policy(blue_observed)
    attach_flat_observe_aliases(blue_observed)
    return blue_observed


def refresh_telemetry_channels(blue_observed: dict[str, Any]) -> dict[str, Any]:
    """Refresh read-only telemetry tx/rx projections from current observe data."""

    external = blue_observed.setdefault("external_observe", {})
    internal = blue_observed.setdefault("internal_observe", {})
    internal_telemetry = internal.get("telemetry", {})
    external_telemetry = external.get("telemetry", blue_observed.get("telemetry", {}))
    comms = external.get("comms", blue_observed.get("comms", {}))
    external_time = external.get("time", blue_observed.get("time", {}))
    internal_time = internal.get("time", {})
    c2_message = external.get("c2_message", blue_observed.get("c2_message", {}))
    internal_c2 = internal.get("c2_message", {})
    inertial = internal.get("inertial_navigation", {})

    tx_timestamp = internal_time.get("true_timestamp", external_time.get("received_timestamp"))
    rx_timestamp = external_time.get("received_timestamp", tx_timestamp)
    tx_sequence = internal_c2.get("sequence_number", c2_message.get("sequence_number"))
    rx_sequence = c2_message.get("sequence_number", tx_sequence)

    asset_tx = {
        "battery_percent": internal_telemetry.get("battery_percent"),
        "battery_drain_rate": internal_telemetry.get("battery_drain_rate"),
        "motor_status": internal_telemetry.get("motor_status"),
        "altitude_m": inertial.get("altitude_m", external_telemetry.get("altitude_m")),
        "speed_mps": inertial.get("speed_mps", external_telemetry.get("speed_mps")),
        "heading_deg": inertial.get("heading_deg", external_telemetry.get("heading_deg")),
        "timestamp": tx_timestamp,
        "frame_seq": tx_sequence,
        "source": "asset_tx_projection",
        "red_visible": True,
        "red_direct_mutation_allowed": False,
        "mutation_policy": "read_only_intel",
    }
    ground_rx = {
        "battery_percent": external_telemetry.get("battery_percent"),
        "battery_drain_rate": external_telemetry.get("battery_drain_rate"),
        "motor_status": external_telemetry.get("motor_status"),
        "altitude_m": external_telemetry.get("altitude_m"),
        "speed_mps": external_telemetry.get("speed_mps"),
        "heading_deg": external_telemetry.get("heading_deg"),
        "received_timestamp": rx_timestamp,
        "frame_seq": rx_sequence,
        "freshness_s": _freshness_seconds(tx_timestamp, rx_timestamp),
        "confidence": _telemetry_rx_confidence(comms),
        "source": "ground_rx_projection",
        "red_visible": True,
        "red_direct_mutation_allowed": False,
        "mutation_policy": "read_only_memory_resource",
        "intended_red_use": "remember_patterns_then_choose_indirect_command_or_timing_actions",
    }
    external["telemetry_channels"] = {
        "schema_id": TELEMETRY_CHANNEL_SCHEMA_VERSION,
        "asset_tx_mirror": asset_tx,
        "ground_rx_view": ground_rx,
        "link_summary": {
            "channel": comms.get("channel"),
            "latency_ms": comms.get("latency_ms"),
            "packet_loss": comms.get("packet_loss"),
            "packet_interval_jitter_ms": comms.get("packet_interval_jitter_ms"),
            "ack_delay_ms": comms.get("ack_delay_ms"),
            "heartbeat_gap_ms": comms.get("heartbeat_gap_ms"),
        },
        "red_use_policy": {
            "can_read": True,
            "can_directly_mutate_asset_tx": False,
            "can_directly_mutate_ground_rx": False,
            "allowed_use": "intel_and_memory_only",
        },
    }
    blue_observed["telemetry_channels"] = external["telemetry_channels"]
    return blue_observed


def refresh_internal_observe_from_truth(state: dict[str, Any]) -> None:
    """Refresh internal observe anchors from scorer truth in simulator code only."""

    observed = state["blue_observed"]
    internal = observed.setdefault("internal_observe", {})
    truth = state["world"]
    external = observed.get("external_observe", observed)

    internal["time"] = {
        "true_timestamp": truth["time"]["true_timestamp"],
        "round": truth["time"].get("round", state.get("round", 0)),
        "local_clock_offset_ms": external.get("time", {}).get("local_clock_offset_ms", 0),
    }
    internal["telemetry"] = {
        "battery_percent": truth["uav"]["battery_percent"],
        "battery_drain_rate": truth["uav"]["battery_drain_rate"],
        "motor_status": truth["uav"]["motor_status"],
    }
    internal["inertial_navigation"] = {
        "position_estimate": deepcopy(truth["uav"].get("position", {})),
        "speed_mps": truth["uav"].get("speed_mps"),
        "heading_deg": truth["uav"].get("heading_deg"),
        "altitude_m": truth["uav"].get("position", {}).get("altitude_m"),
    }
    internal["c2_message"] = {
        "sequence_number": truth["command"]["expected_sequence_number"],
        "command": truth["command"]["last_valid_command"],
        "received_timestamp": truth["time"]["true_timestamp"],
        "source": "internal_observe",
        "red_direct_mutation_allowed": False,
    }
    internal["health"] = {
        "source": "internal_observe",
        "red_direct_mutation_allowed": False,
    }
    refresh_telemetry_channels(observed)


def _freshness_seconds(tx_timestamp: Any, rx_timestamp: Any) -> float | None:
    if not isinstance(tx_timestamp, (int, float)) or not isinstance(rx_timestamp, (int, float)):
        return None
    return round(max(0.0, float(tx_timestamp) - float(rx_timestamp)), 4)


def _telemetry_rx_confidence(comms: dict[str, Any]) -> float:
    latency_penalty = min(0.35, float(comms.get("latency_ms", 0) or 0) / 4000.0)
    loss_penalty = min(0.45, float(comms.get("packet_loss", 0.0) or 0.0) * 1.4)
    jitter_penalty = min(0.20, float(comms.get("packet_interval_jitter_ms", 0) or 0) / 3000.0)
    return round(max(0.0, min(1.0, 1.0 - latency_penalty - loss_penalty - jitter_penalty)), 4)
