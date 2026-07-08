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
from dah_flawless.blue.defense_effects import assess_defense_containment
from dah_flawless.scoring.goal_scorer import score_red_goal
from dah_flawless.scoring.mission_impact import assess_mission_impact, blend_goal_reward_with_mission_impact
from dah_flawless.scoring.telemetry_learning import telemetry_goal_success, telemetry_learning_signal
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
    containment = assess_defense_containment(
        pre_defense_state=pre_defense_state,
        post_defense_state=post_defense_state,
        attack=attack,
        threats=threats,
        actions=actions,
        goal_score=goal_score,
        detection_success=detection_success,
        recovery_success=recovery_success,
        attack_success=attack_success,
    )
    attrition = _attrition_evidence(pre_defense_state, post_defense_state, actions, goal_score, mission_impact)
    goal_score = _shape_goal_reward(
        goal_score,
        attack_success=attack_success,
        detection_success=detection_success,
        recovery_success=recovery_success,
        attrition_triggered=bool(attrition["triggered"]),
    )

    outcome = _classify_outcome(
        attack_success=attack_success,
        detection_success=detection_success,
        false_positive=false_positive,
        recovery_success=recovery_success,
        availability=availability,
        attrition=attrition,
        goal_score=goal_score,
        containment=containment,
    )

    evidence["defense_actions"] = [action.action for action in actions]
    evidence["truth_model"] = "scorer_truth"
    evidence["truth_storage_key"] = 'state["world"]'
    evidence["detection_window"] = DETECTION_WINDOW
    evidence["recovery_window"] = RECOVERY_WINDOW
    evidence["current_recovery_success"] = current_recovery_success
    evidence["mission_impact"] = mission_impact
    evidence["goal_score"] = goal_score
    evidence["containment"] = containment
    evidence["attrition"] = attrition
    evidence["outcome"] = outcome
    return Score(
        winner=outcome["winner"],
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
        winner_side=outcome["winner_side"],
        winner_detail=outcome["winner_detail"],
        outcome_reason=outcome["reason"],
        containment_score=containment["containment_score"],
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
        learning_signal = telemetry_learning_signal(state, include_world_truth=True)
        indirect = learning_signal["indirect_evidence"]
        direct_mismatch = trusted != received
        mismatch = direct_mismatch or telemetry_goal_success(learning_signal)
        trusted["telemetry_memory_policy"] = "read_only_intel"
        received["indirect_confusion"] = indirect
        received["telemetry_learning_signal"] = learning_signal
    elif attack.target_domain == "mission":
        trusted = scorer_truth["mission"]["area_priority"]
        received = observed["mission"]["area_priority"]
        truth_top_area = max(trusted, key=lambda area: float(trusted[area]))
        recommended_area = observed["mission"].get("recommended_area")
        max_delta = max(abs(trusted[area] - received[area]) for area in trusted)
        mismatch = max_delta > 0.35 or recommended_area not in {None, truth_top_area}
        trusted = {"area_priority": trusted, "recommended_area": truth_top_area}
        received = {"area_priority": received, "recommended_area": recommended_area}
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
        direct_recovered = (
            observed["telemetry"]["battery_percent"] == scorer_truth["uav"]["battery_percent"]
            and observed["telemetry"]["motor_status"] == scorer_truth["uav"]["motor_status"]
        )
        learning_signal = telemetry_learning_signal(state, include_world_truth=True)
        return direct_recovered and not telemetry_goal_success(learning_signal)
    if attack.target_domain == "mission":
        truth_priority = scorer_truth["mission"]["area_priority"]
        truth_top_area = max(truth_priority, key=lambda area: float(truth_priority[area]))
        return (
            observed["mission"]["area_priority"] == truth_priority
            and observed["mission"].get("recommended_area") == truth_top_area
        )
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
    mission_impact: dict,
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
    red_round_attack_cost = float(combat_attrition.get("red_round_attack_cost", 0.0))
    red_mutation_steps = int(combat_attrition.get("red_mutation_steps", 0))
    cost_ratio = round_defense_cost / max(red_round_attack_cost, 0.01)
    net_defense_cost = max(0.0, round_defense_cost - red_round_attack_cost)
    mission_impact_score = float(mission_impact.get("mission_impact_score", goal_score.get("mission_impact_score", 0.0)))

    floor_breach = post_availability < AVAIL_FLOOR
    already_below_floor = pre_availability < AVAIL_FLOOR
    current_pressure = action_cost >= 0.10 or availability_drop >= 0.08 or high_cost_action_count >= 2
    sustained_pressure = round_defense_steps >= 2 and round_defense_cost >= 0.16
    consecutive_pressure = consecutive_defense_steps >= 2 and round_defense_cost >= 0.12
    cost_effective = net_defense_cost >= 0.06 and cost_ratio >= 1.20
    mission_meaningful = (
        mission_impact_score >= 0.35
        or availability_drop >= 0.08
        or post_availability <= AVAIL_FLOOR - 0.04
    )
    goal_pressure = (
        goal_score.get("goal_id") == "BLUE_OVERDEFENSE_ATTRITION"
        and bool(goal_score.get("goal_success"))
        and cost_effective
        and (action_cost >= 0.07 or availability_drop >= 0.04 or sustained_pressure)
    )
    stale_floor_pressure = already_below_floor and availability_drop < 0.03 and action_cost < 0.07
    triggered = floor_breach and not stale_floor_pressure and (
        current_pressure or sustained_pressure or consecutive_pressure or goal_pressure
    ) and cost_effective and mission_meaningful

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
        "red_round_attack_cost": round(red_round_attack_cost, 4),
        "red_mutation_steps": red_mutation_steps,
        "defense_to_attack_cost_ratio": round(cost_ratio, 4),
        "net_defense_cost": round(net_defense_cost, 4),
        "mission_impact_score": round(mission_impact_score, 4),
        "cost_effective": cost_effective,
        "mission_meaningful": mission_meaningful,
        "current_pressure": current_pressure,
        "sustained_pressure": sustained_pressure,
        "goal_pressure": goal_pressure,
        "stale_floor_pressure": stale_floor_pressure,
    }


def _classify_outcome(
    *,
    attack_success: bool,
    detection_success: bool,
    false_positive: bool,
    recovery_success: bool,
    availability: float,
    attrition: dict,
    goal_score: dict,
    containment: dict,
) -> dict:
    goal_success = bool(goal_score.get("goal_success", False))
    containment_score = float(containment.get("containment_score", 0.0))
    contained = bool(containment.get("contained", False))
    if attrition["triggered"]:
        return _outcome("RED_ATTRITION", "RED", "ATTRITION", "blue_defense_pressure_reduced_mission_availability")
    if attack_success and goal_success and not detection_success and containment_score >= 0.45:
        return _outcome(
            "DRAW",
            "DRAW",
            "POLICY_CONTAINMENT",
            "policy_gate_limited_authoritative_use_without_attack_detection",
        )
    if attack_success and goal_success and not detection_success:
        return _outcome("RED_BREACH", "RED", "BREACH", "undetected_attack_achieved_selected_goal")
    if attack_success and not detection_success:
        return _outcome("DRAW", "DRAW", "PARTIAL_BREACH", "observe_corrupted_but_selected_goal_failed")
    if false_positive:
        return _outcome("DRAW", "DRAW", "FALSE_POSITIVE", "blue_flagged_threat_without_scorer_attack_effect")
    if recovery_success and availability >= RECOVERY_TARGET:
        return _outcome("BLUE_RECOVERY", "BLUE", "RECOVERY", "blue_detected_and_restored_trusted_observe")
    if detection_success and contained and availability >= AVAIL_FLOOR:
        return _outcome("BLUE", "BLUE", "CONTAINMENT", "blue_detected_and_contained_attack_effect")
    if detection_success and containment_score >= 0.45 and availability >= AVAIL_FLOOR:
        return _outcome("BLUE", "BLUE", "PARTIAL_CONTAINMENT", "blue_limited_attack_effect_without_full_recovery")
    if detection_success and availability >= AVAIL_FLOOR:
        return _outcome("BLUE", "BLUE", "DETECTION", "blue_detected_or_contained_attack_effect")
    if attack_success:
        return _outcome("DRAW", "DRAW", "PARTIAL_EFFECT", "attack_effect_present_without_decisive_outcome")
    return _outcome("DRAW", "DRAW", "NO_EFFECT", "selected_attack_did_not_create_decisive_effect")


def _outcome(winner: str, side: str, detail: str, reason: str) -> dict:
    return {
        "winner": winner,
        "winner_side": side,
        "winner_detail": detail,
        "reason": reason,
    }


def _shape_goal_reward(
    goal_score: dict,
    *,
    attack_success: bool,
    detection_success: bool,
    recovery_success: bool,
    attrition_triggered: bool,
) -> dict:
    updated = dict(goal_score)
    before = float(updated.get("goal_reward", 0.0))
    goal_success = bool(updated.get("goal_success", False))
    caps: list[tuple[str, float]] = []

    if not goal_success:
        if attack_success and not detection_success:
            caps.append(("partial_breach_goal_failed", 0.30))
        elif attack_success:
            caps.append(("partial_effect_goal_failed", 0.24))
        else:
            caps.append(("no_goal_effect", 0.18))
    if recovery_success and not attrition_triggered:
        caps.append(("blue_recovered_effect", 0.38))

    after = before
    if caps:
        after = min(after, min(cap for _, cap in caps))
    if goal_success and not detection_success:
        after = min(1.0, after + 0.06)
    if attrition_triggered and goal_success and updated.get("goal_id") == "BLUE_OVERDEFENSE_ATTRITION":
        after = min(1.0, after + 0.08)

    updated["goal_reward_before_outcome_shaping"] = round(before, 4)
    updated["goal_reward"] = round(min(1.0, max(0.0, after)), 4)
    updated["outcome_reward_adjustment"] = round(updated["goal_reward"] - before, 4)
    updated["outcome_reward_caps"] = [{"reason": reason, "cap": cap} for reason, cap in caps]
    updated["outcome_reward_algorithm"] = "outcome_reward_shaping_v1"
    return updated
