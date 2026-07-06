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
from dah_flawless.scoring.mission_impact import assess_mission_impact, blend_goal_reward_with_mission_impact
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
    mission_impact = assess_mission_impact(
        pre_defense_state=pre_defense_state,
        post_defense_state=post_defense_state,
        attack=attack,
        red_goal=red_goal,
        actions=actions,
    )
    goal_score = blend_goal_reward_with_mission_impact(goal_score, mission_impact)
    attrition = _attrition_evidence(pre_defense_state, post_defense_state, actions, goal_score)

    if attack_success and not detection_success:
        winner = "RED_BREACH"
    elif attrition["triggered"]:
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
    evidence["mission_impact"] = mission_impact
    evidence["goal_score"] = goal_score
    evidence["attrition"] = attrition
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


def _attrition_evidence(
    pre_defense_state: dict,
    post_defense_state: dict,
    actions: list[DefenseAction],
    goal_score: dict,
) -> dict:
    pre_availability = float(pre_defense_state["mission"]["availability"])
    post_availability = float(post_defense_state["mission"]["availability"])
    availability_drop = max(0.0, pre_availability - post_availability)
    action_cost = round(sum(float(action.availability_cost) for action in actions), 4)
    high_cost_action_count = sum(1 for action in actions if float(action.availability_cost) >= 0.05)
    combat_attrition = post_defense_state.get("defense_runtime", {}).get("combat_attrition", {})
    round_defense_cost = float(combat_attrition.get("round_defense_cost", action_cost))
    round_defense_steps = int(combat_attrition.get("defense_steps", 1 if actions else 0))
    consecutive_defense_steps = int(combat_attrition.get("consecutive_defense_steps", 1 if actions else 0))

    floor_breach = post_availability < AVAIL_FLOOR
    already_below_floor = pre_availability < AVAIL_FLOOR
    current_pressure = action_cost >= 0.10 or availability_drop >= 0.08 or high_cost_action_count >= 2
    sustained_pressure = round_defense_steps >= 2 and round_defense_cost >= 0.16
    consecutive_pressure = consecutive_defense_steps >= 2 and round_defense_cost >= 0.12
    goal_pressure = (
        goal_score.get("goal_id") == "BLUE_OVERDEFENSE_ATTRITION"
        and bool(goal_score.get("goal_success"))
        and (action_cost >= 0.07 or availability_drop >= 0.04 or sustained_pressure)
    )
    stale_floor_pressure = already_below_floor and availability_drop < 0.03 and action_cost < 0.07
    triggered = floor_breach and not stale_floor_pressure and (
        current_pressure or sustained_pressure or consecutive_pressure or goal_pressure
    )

    return {
        "triggered": bool(triggered),
        "floor_breach": floor_breach,
        "already_below_floor": already_below_floor,
        "availability_before": round(pre_availability, 4),
        "availability_after": round(post_availability, 4),
        "availability_drop": round(availability_drop, 4),
        "action_cost": action_cost,
        "defense_action_count": len(actions),
        "high_cost_action_count": high_cost_action_count,
        "round_defense_cost": round(round_defense_cost, 4),
        "round_defense_steps": round_defense_steps,
        "consecutive_defense_steps": consecutive_defense_steps,
        "current_pressure": current_pressure,
        "sustained_pressure": sustained_pressure,
        "goal_pressure": goal_pressure,
        "stale_floor_pressure": stale_floor_pressure,
    }
