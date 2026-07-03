"""Observed-only Red mutations."""

from __future__ import annotations

from copy import deepcopy

from dah_flawless.schemas import Attack


def apply_attack(
    state: dict,
    attack: Attack,
    stealth: bool = False,
    tactic: dict | None = None,
) -> tuple[dict, dict]:
    """Apply an attack to blue_observed only.

    The function intentionally never reads state["world"]. This keeps Red's
    mutation model aligned with the world/observed split.

    When ``stealth`` is set, Red uses a smaller telemetry mutation that still
    leaves observed values mismatched from world. Cross-signal checks can still
    catch a static small jump; adaptive Red can pass ``tactic["probe_delta"]``
    to probe the boundary. PRIORITY_POISONING and TIME_DESYNC_REPLAY have no
    useful stealth margin, so stealth only changes their log metadata.
    """

    next_state = deepcopy(state)
    obs = next_state["blue_observed"]

    if attack.name == "TELEMETRY_FDI":
        before = {
            "battery_percent": obs["telemetry"]["battery_percent"],
            "motor_status": obs["telemetry"]["motor_status"],
        }
        if stealth:
            # Without a tactic this preserves the old static stealth value
            # (20 -> 44). Adaptive Red can pass a smaller probe_delta.
            probe_delta = int((tactic or {}).get("probe_delta", 24))
            obs["telemetry"]["battery_percent"] = min(100, obs["telemetry"]["battery_percent"] + probe_delta)
            obs["telemetry"]["motor_status"] = "FAULT"
        else:
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
        "stealth": stealth,
        "tactic": tactic or {"stealth": stealth},
        "before": before,
        "after": after,
    }
    return next_state, mutation_log
