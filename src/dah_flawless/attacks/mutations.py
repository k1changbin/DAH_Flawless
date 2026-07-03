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
    mutation model aligned with the scorer_truth/observed split.

    When ``stealth`` is set, Red uses a smaller telemetry mutation that still
    leaves observed values mismatched from scorer truth. Cross-signal checks can still
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
            "ack_sequence_number": obs["c2_message"].get("ack", {}).get("sequence_number"),
            "latency_ms": obs["comms"].get("latency_ms"),
            "packet_loss": obs["comms"].get("packet_loss"),
            "ack_delay_ms": obs["comms"].get("ack_delay_ms"),
            "heartbeat_gap_ms": obs["comms"].get("heartbeat_gap_ms"),
        }
        _apply_time_desync_tactic(obs, tactic or {})
        after = {
            "sequence_number": obs["c2_message"]["sequence_number"],
            "received_timestamp": obs["time"]["received_timestamp"],
            "command": obs["c2_message"]["command"],
            "ack_sequence_number": obs["c2_message"].get("ack", {}).get("sequence_number"),
            "latency_ms": obs["comms"].get("latency_ms"),
            "packet_loss": obs["comms"].get("packet_loss"),
            "ack_delay_ms": obs["comms"].get("ack_delay_ms"),
            "heartbeat_gap_ms": obs["comms"].get("heartbeat_gap_ms"),
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


def _apply_time_desync_tactic(obs: dict, tactic: dict) -> None:
    strategy = tactic.get("strategy", "replay")
    params = tactic.get("params", {})

    if strategy == "delay":
        obs["time"]["received_timestamp"] += int(params.get("timestamp_delta_s", -180))
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        obs["comms"]["latency_ms"] = int(params.get("latency_ms", 900))
        obs["comms"]["packet_interval_jitter_ms"] = 460
        obs["comms"]["packet_loss"] = max(obs["comms"].get("packet_loss", 0.0), 0.08)
    elif strategy == "selective_drop":
        obs["c2_message"]["sequence_number"] += 3
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        obs["comms"]["packet_loss"] = float(params.get("packet_loss", 0.16))
        obs["comms"]["heartbeat_gap_ms"] = int(params.get("heartbeat_gap_ms", 3600))
        obs["comms"]["packet_interval_jitter_ms"] = 460
    elif strategy == "ack_confusion":
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        ack = obs["c2_message"].setdefault("ack", {})
        ack["visible"] = True
        ack["sequence_number"] = obs["c2_message"]["sequence_number"] + int(params.get("ack_sequence_delta", -2))
        ack["status"] = "ACCEPTED"
        obs["comms"]["ack_visible"] = True
        obs["comms"]["ack_delay_ms"] = int(params.get("ack_delay_ms", 950))
        obs["comms"]["latency_ms"] = max(obs["comms"].get("latency_ms", 0), 540)
    elif strategy == "metadata_poisoning":
        obs["c2_message"]["sequence_number"] += int(params.get("sequence_delta", -2))
        obs["time"]["received_timestamp"] += int(params.get("timestamp_delta_s", -90))
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        obs["c2_message"]["sysid"] = 99
        obs["c2_message"]["compid"] = 42
        obs["comms"]["latency_ms"] = max(obs["comms"].get("latency_ms", 0), 620)
    else:
        sequence_delta = int(params.get("sequence_delta", -13))
        obs["c2_message"]["sequence_number"] = max(0, obs["c2_message"]["sequence_number"] + sequence_delta)
        obs["time"]["received_timestamp"] += int(params.get("timestamp_delta_s", -400))
        obs["c2_message"]["command"] = "CONTINUE_MISSION"
        obs["comms"]["latency_ms"] = 850
        obs["comms"]["packet_loss"] = 0.12
        obs["comms"]["packet_interval_jitter_ms"] = 460
        obs["comms"]["ack_delay_ms"] = 950
        obs["comms"]["heartbeat_gap_ms"] = 3200
