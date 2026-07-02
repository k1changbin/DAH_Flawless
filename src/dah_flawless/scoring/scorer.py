"""Objective scorer for attack and defense outcomes."""

from __future__ import annotations

from dah_flawless.config import AVAIL_FLOOR, CONFIDENCE_THRESHOLD, RECOVERY_TARGET
from dah_flawless.schemas import Attack, DefenseAction, Score, Threat


def score_round(
    pre_defense_state: dict,
    post_defense_state: dict,
    attack: Attack,
    threats: list[Threat],
    actions: list[DefenseAction],
) -> Score:
    evidence = _attack_evidence(pre_defense_state, attack)
    attack_success = bool(evidence["mismatch"])
    detection_success = any(
        threat.target == attack.target_domain and threat.confidence >= CONFIDENCE_THRESHOLD for threat in threats
    )
    false_positive = (not attack_success) and bool(threats)
    recovery_success = _recovery_success(post_defense_state, attack)
    availability = post_defense_state["mission"]["availability"]

    if attack_success and not detection_success:
        winner = "RED_BREACH"
    elif availability < AVAIL_FLOOR:
        winner = "RED_ATTRITION"
    elif recovery_success and availability >= RECOVERY_TARGET:
        winner = "BLUE_RECOVERY"
    elif detection_success and availability >= AVAIL_FLOOR:
        winner = "BLUE"
    else:
        winner = "DRAW"

    evidence["defense_actions"] = [action.action for action in actions]
    return Score(
        winner=winner,
        attack_success=attack_success,
        detection_success=detection_success,
        false_positive=false_positive,
        recovery_success=recovery_success,
        availability=availability,
        target_domain=attack.target_domain,
        evidence=evidence,
    )


def _attack_evidence(state: dict, attack: Attack) -> dict:
    world = state["world"]
    observed = state["blue_observed"]

    if attack.target_domain == "telemetry":
        trusted = {
            "battery_percent": world["uav"]["battery_percent"],
            "motor_status": world["uav"]["motor_status"],
        }
        received = {
            "battery_percent": observed["telemetry"]["battery_percent"],
            "motor_status": observed["telemetry"]["motor_status"],
        }
        mismatch = trusted != received
    elif attack.target_domain == "mission":
        trusted = world["mission"]["area_priority"]
        received = observed["mission"]["area_priority"]
        mismatch = max(abs(trusted[area] - received[area]) for area in trusted) > 0.35
    elif attack.target_domain == "command":
        trusted = {
            "expected_sequence_number": world["command"]["expected_sequence_number"],
            "true_timestamp": world["time"]["true_timestamp"],
            "last_valid_command": world["command"]["last_valid_command"],
        }
        received = {
            "sequence_number": observed["c2_message"]["sequence_number"],
            "received_timestamp": observed["time"]["received_timestamp"],
            "command": observed["c2_message"]["command"],
        }
        mismatch = (
            received["sequence_number"] < trusted["expected_sequence_number"]
            or received["received_timestamp"] < trusted["true_timestamp"] - 120
            or received["command"] != trusted["last_valid_command"]
        )
    else:
        trusted = None
        received = None
        mismatch = False

    return {"trusted_value": trusted, "observed_value": received, "mismatch": mismatch}


def _recovery_success(state: dict, attack: Attack) -> bool:
    world = state["world"]
    observed = state["blue_observed"]

    if attack.target_domain == "telemetry":
        return (
            observed["telemetry"]["battery_percent"] == world["uav"]["battery_percent"]
            and observed["telemetry"]["motor_status"] == world["uav"]["motor_status"]
        )
    if attack.target_domain == "mission":
        return observed["mission"]["area_priority"] == world["mission"]["area_priority"]
    if attack.target_domain == "command":
        return (
            observed["c2_message"]["sequence_number"] == world["command"]["expected_sequence_number"]
            and observed["c2_message"]["command"] == world["command"]["last_valid_command"]
        )
    return False
