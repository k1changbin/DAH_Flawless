"""Observed-only Red mutations."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.schemas import Attack


def apply_attack(state: dict, attack: Attack) -> tuple[dict, dict]:
    """Apply an attack to blue_observed only.

    The function intentionally never reads state["world"]. This keeps Red's
    mutation model aligned with the world/observed split.
    """

    next_state = deepcopy(state)
    obs = next_state["blue_observed"]

    if attack.name == "TELEMETRY_FDI":
        before = {
            "battery_percent": obs["telemetry"]["battery_percent"],
            "motor_status": obs["telemetry"]["motor_status"],
        }
        obs["telemetry"]["battery_percent"] = 82
        obs["telemetry"]["motor_status"] = "OK"
        after = {
            "battery_percent": obs["telemetry"]["battery_percent"],
            "motor_status": obs["telemetry"]["motor_status"],
        }
    elif attack.name == "PRIORITY_POISONING":
        before = deepcopy(obs["mission"]["area_priority"])
        obs["mission"]["area_priority"] = {"A": 0.20, "B": 0.40, "C": 0.95}
        obs["mission"]["recommended_area"] = "C"
        after = deepcopy(obs["mission"]["area_priority"])
    elif attack.name == "TIME_DESYNC_REPLAY":
        before = {
            "sequence_number": obs["c2_message"]["sequence_number"],
            "received_timestamp": obs["time"]["received_timestamp"],
            "command": obs["c2_message"]["command"],
        }
        obs["c2_message"]["sequence_number"] = 1008
        obs["time"]["received_timestamp"] = obs["time"]["received_timestamp"] - 400
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        obs["comms"]["latency_ms"] = 850
        obs["comms"]["packet_loss"] = 0.12
        after = {
            "sequence_number": obs["c2_message"]["sequence_number"],
            "received_timestamp": obs["time"]["received_timestamp"],
            "command": obs["c2_message"]["command"],
        }
    else:
        raise ValueError(f"mutation not implemented for {attack.name}")

    mutation_log = {
        "agent": "RedAgent",
        "event": "mutation_applied",
        "reason": attack.name,
        "before": before,
        "after": after,
    }
    return next_state, mutation_log
