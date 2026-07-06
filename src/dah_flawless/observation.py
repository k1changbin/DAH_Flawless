"""Helpers for the Blue observe model.

The canonical model separates Blue input into internal and external observe
surfaces. Existing MVP code still reads the flat ``blue_observed`` keys, so this
module keeps compatibility aliases while making the trust boundary explicit.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


OBSERVE_SCHEMA_VERSION = "dah.observe.v0_2"

EXTERNAL_OBSERVE_KEYS = (
    "time",
    "telemetry",
    "navigation",
    "mission",
    "c2_message",
    "comms",
)

RED_MUTABLE_EXTERNAL_KEYS = (
    "time",
    "telemetry",
    "navigation",
    "mission",
    "c2_message",
    "comms",
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
            },
            "blue_can_read": {
                "internal_observe": True,
                "external_observe": True,
            },
        },
    }
    attach_flat_observe_aliases(observed)
    return observed


def attach_flat_observe_aliases(blue_observed: dict[str, Any]) -> dict[str, Any]:
    """Expose legacy flat keys as aliases of ``external_observe`` domains."""

    external = blue_observed.setdefault("external_observe", {})
    for key in EXTERNAL_OBSERVE_KEYS:
        if key in external:
            blue_observed[key] = external[key]
    return blue_observed


def sync_external_observe_from_flat(blue_observed: dict[str, Any]) -> dict[str, Any]:
    """Persist legacy flat-domain updates back into ``external_observe``."""

    external = blue_observed.setdefault("external_observe", {})
    for key in EXTERNAL_OBSERVE_KEYS:
        if key in blue_observed:
            external[key] = blue_observed[key]
    attach_flat_observe_aliases(blue_observed)
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
