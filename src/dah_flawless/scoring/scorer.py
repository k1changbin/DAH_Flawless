"""Objective scorer for attack and defense outcomes.

``state["world"]`` is a compatibility key for scorer-only truth. It is not the
raw-world signal bundle produced by ``dah_flawless.world.generator``.
"""

from __future__ import annotations

from dah_flawless.config import (
    AVAIL_FLOOR,
    CONFIDENCE_THRESHOLD,
    DETECTION_WINDOW,
    RECOVERY_TARGET,
    RECOVERY_WINDOW,
)
from dah_flawless.scoring.goal_scorer import score_red_goal
from dah_flawless.schemas import Attack, DefenseAction, Score, Threat


def score_round(
    pre_defense_state: dict,
    post_defense_state: dict,
    attack: Attack,
    threats: list[Threat],
    actions: list[DefenseAction],
    threat_history: list[list[Threat]] | None = None,
    recovery_history: list[dict[str, bool]] | None = None,
    red_goal: dict | None = None,
) -> Score:
    evidence = _attack_evidence(pre_defense_state, attack)
    attack_success = bool(evidence["mismatch"])
    detection_success = _detected_in_window(attack, threats, threat_history)
    false_positive = (not attack_success) and bool(threats)
    current_recovery_success = _recovery_success(post_defense_state, attack)
    recovery_success = _recovered_in_window(attack, current_recovery_success, recovery_history)
    availability = post_defense_state["mission"]["availability"]
    goal_score = score_red_goal(
        pre_defense_state=pre_defense_state,
        post_defense_state=post_defense_state,
        attack=attack,
        red_goal=red_goal,
        threats=threats,
        actions=actions,
        attack_success=attack_success,
        detection_success=detection_success,
        recovery_success=recovery_success,
    )

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
    evidence["truth_model"] = "scorer_truth"
    evidence["truth_storage_key"] = 'state["world"]'
    evidence["detection_window"] = DETECTION_WINDOW
    evidence["recovery_window"] = RECOVERY_WINDOW
    evidence["current_recovery_success"] = current_recovery_success
    evidence["goal_score"] = goal_score
    return Score(
        winner=winner,
        attack_success=attack_success,
        detection_success=detection_success,
        false_positive=false_positive,
        recovery_success=recovery_success,
        availability=availability,
        target_domain=attack.target_domain,
        evidence=evidence,
        goal_id=goal_score["goal_id"],
        goal_success=goal_score["goal_success"],
        goal_reward=goal_score["goal_reward"],
    )


def _attack_evidence(state: dict, attack: Attack) -> dict:
    scorer_truth = state["world"]
    observed = state["blue_observed"]

    if attack.target_domain == "telemetry":
        trusted = {
            "battery_percent": scorer_truth["uav"]["battery_percent"],
            "motor_status": scorer_truth["uav"]["motor_status"],
        }
        received = {
            "battery_percent": observed["telemetry"]["battery_percent"],
            "motor_status": observed["telemetry"]["motor_status"],
        }
        mismatch = trusted != received
    elif attack.target_domain == "mission":
        trusted = scorer_truth["mission"]["area_priority"]
        received = observed["mission"]["area_priority"]
        mismatch = max(abs(trusted[area] - received[area]) for area in trusted) > 0.35
    elif attack.target_domain == "command":
        trusted = {
            "expected_sequence_number": scorer_truth["command"]["expected_sequence_number"],
            "true_timestamp": scorer_truth["time"]["true_timestamp"],
            "last_valid_command": scorer_truth["command"]["last_valid_command"],
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
    scorer_truth = state["world"]
    observed = state["blue_observed"]

    if attack.target_domain == "telemetry":
        return (
            observed["telemetry"]["battery_percent"] == scorer_truth["uav"]["battery_percent"]
            and observed["telemetry"]["motor_status"] == scorer_truth["uav"]["motor_status"]
        )
    if attack.target_domain == "mission":
        return observed["mission"]["area_priority"] == scorer_truth["mission"]["area_priority"]
    if attack.target_domain == "command":
        return (
            observed["c2_message"]["sequence_number"] == scorer_truth["command"]["expected_sequence_number"]
            and observed["c2_message"]["command"] == scorer_truth["command"]["last_valid_command"]
        )
    return False


def _detected_in_window(
    attack: Attack,
    threats: list[Threat],
    threat_history: list[list[Threat]] | None,
) -> bool:
    history_window = (threat_history or [])[-max(0, DETECTION_WINDOW - 1) :]
    for threat_batch in [*history_window, threats]:
        for threat in threat_batch:
            if threat.target == attack.target_domain and threat.confidence >= CONFIDENCE_THRESHOLD:
                return True
    return False


def _recovered_in_window(
    attack: Attack,
    current_recovery_success: bool,
    recovery_history: list[dict[str, bool]] | None,
) -> bool:
    if current_recovery_success:
        return True
    history_window = (recovery_history or [])[-max(0, RECOVERY_WINDOW - 1) :]
    return any(recovery.get(attack.target_domain, False) for recovery in history_window)
