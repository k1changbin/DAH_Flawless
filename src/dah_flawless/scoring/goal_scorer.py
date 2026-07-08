"""Goal-aware scoring for simulated Red cyber effects.

This module scores whether Red achieved its selected *effect* in the simulator.
It does not model or reward real exploit execution. The scorer only compares
scorer-truth state, Blue's observed state, Blue threats, and defense cost.
"""

from __future__ import annotations

from typing import Any

from dah_flawless.attacks.effect_contracts import score_contract_alignment
from dah_flawless.schemas import Attack, DefenseAction, Threat
from dah_flawless.scoring.telemetry_learning import (
    telemetry_goal_effect_score,
    telemetry_goal_success,
    telemetry_learning_signal,
)


def score_red_goal(
    *,
    pre_defense_state: dict,
    post_defense_state: dict,
    attack: Attack,
    red_goal: dict | None,
    threats: list[Threat],
    actions: list[DefenseAction],
    attack_success: bool,
    detection_success: bool,
    recovery_success: bool,
) -> dict[str, Any]:
    goal_id = (red_goal or {}).get("goal_id") or _default_goal_for_attack(attack.name)
    scorer = GOAL_SCORERS.get(goal_id, _score_domain_mismatch_goal)
    goal_score = scorer(
        pre_defense_state=pre_defense_state,
        post_defense_state=post_defense_state,
        attack=attack,
        red_goal=red_goal or {},
        threats=threats,
        actions=actions,
        attack_success=attack_success,
        detection_success=detection_success,
        recovery_success=recovery_success,
    )
    goal_score.setdefault("goal_id", goal_id)
    goal_score.setdefault("target_domain", attack.target_domain)
    goal_score.setdefault("goal_success", bool(goal_score.get("effect_score", 0.0) >= 0.55))
    goal_score.setdefault("goal_reward", _reward_from_effect(goal_score["effect_score"], detection_success, recovery_success))
    contract_alignment = score_contract_alignment(attack.name, red_goal or {"goal_id": goal_id})
    goal_score["contract_alignment"] = contract_alignment
    if not contract_alignment["supported_goal"]:
        goal_score["goal_success"] = False
        goal_score["effect_score"] = round(min(0.10, float(goal_score.get("effect_score", 0.0))), 4)
        goal_score["goal_reward"] = round(min(0.06, float(goal_score.get("goal_reward", 0.0))), 4)
        evidence = dict(goal_score.get("evidence", {}))
        evidence["contract_violation"] = contract_alignment["reason"]
        evidence["expected_mutation_paths"] = contract_alignment["expected_mutation_paths"]
        goal_score["evidence"] = evidence
    goal_score["goal_reward"] = round(min(1.0, max(0.0, float(goal_score["goal_reward"]))), 4)
    goal_score["goal_success"] = bool(goal_score["goal_success"])
    goal_score["algorithm"] = (
        "goal_effect_contract_rule_score_v2_telemetry_axes"
        if goal_id == "TELEMETRY_TRUST_EROSION"
        else "goal_effect_contract_rule_score_v1"
    )
    return goal_score


def _score_wrong_target_selection(**ctx: Any) -> dict[str, Any]:
    truth = ctx["pre_defense_state"]["world"]["mission"]["area_priority"]
    observed_mission = ctx["pre_defense_state"]["blue_observed"]["mission"]
    observed = observed_mission["area_priority"]
    truth_top = _top_area(truth)
    observed_top = _top_area(observed)
    recommended = observed_mission.get("recommended_area")
    max_delta = max(abs(float(truth[area]) - float(observed.get(area, 0.0))) for area in truth)
    top_mismatch = observed_top != truth_top
    recommendation_mismatch = recommended is not None and recommended != truth_top
    effect_score = min(1.0, 0.25 + max_delta + (0.25 if top_mismatch else 0.0) + (0.15 if recommendation_mismatch else 0.0))

    return _goal_result(
        ctx,
        effect_score=effect_score,
        goal_success=max_delta > 0.35 or top_mismatch or recommendation_mismatch,
        evidence={
            "truth_top_area": truth_top,
            "observed_top_area": observed_top,
            "recommended_area": recommended,
            "max_priority_delta": round(max_delta, 4),
        },
    )


def _score_telemetry_trust_erosion(**ctx: Any) -> dict[str, Any]:
    signal = telemetry_learning_signal(ctx["pre_defense_state"], include_world_truth=True)
    axis_scores = signal["axis_scores"]
    legacy = signal["legacy_direct_evidence"]
    indirect = signal["indirect_evidence"]
    effect_score = telemetry_goal_effect_score(signal)

    return _goal_result(
        ctx,
        effect_score=effect_score,
        goal_success=telemetry_goal_success(signal),
        evidence={
            "telemetry_command_confusion": axis_scores["telemetry_command_confusion"],
            "stale_state_acceptance": axis_scores["stale_state_acceptance"],
            "wrong_safety_decision": axis_scores["wrong_safety_decision"],
            "tx_rx_consistency_pressure": axis_scores["tx_rx_consistency_pressure"],
            "legacy_sensor_delta": axis_scores["legacy_sensor_delta"],
            "battery_delta": legacy["battery_delta"],
            "motor_mismatch": legacy["motor_mismatch"],
            "impossible_drain_hint": legacy["impossible_drain_hint"],
            **indirect,
            "telemetry_learning_signal": signal,
        },
    )


def _score_command_stale_acceptance(**ctx: Any) -> dict[str, Any]:
    truth = ctx["pre_defense_state"]["world"]
    observed = ctx["pre_defense_state"]["blue_observed"]
    expected_sequence = int(truth["command"]["expected_sequence_number"])
    received_sequence = int(observed["c2_message"]["sequence_number"])
    true_timestamp = int(truth["time"]["true_timestamp"])
    received_timestamp = int(observed["time"]["received_timestamp"])
    sequence_lag = max(0, expected_sequence - received_sequence)
    timestamp_lag = max(0, true_timestamp - received_timestamp)
    command_mismatch = observed["c2_message"]["command"] != truth["command"]["last_valid_command"]
    effect_score = min(1.0, sequence_lag / 8.0 + timestamp_lag / 180.0 + (0.15 if command_mismatch else 0.0))

    return _goal_result(
        ctx,
        effect_score=effect_score,
        goal_success=sequence_lag >= 1 or timestamp_lag >= 5 or command_mismatch,
        evidence={
            "sequence_lag": sequence_lag,
            "timestamp_lag_s": timestamp_lag,
            "command_mismatch": command_mismatch,
        },
    )


def _score_ack_causal_confusion(**ctx: Any) -> dict[str, Any]:
    observed = ctx["pre_defense_state"]["blue_observed"]
    c2 = observed["c2_message"]
    ack = c2.get("ack", {})
    ack_visible = bool(observed["comms"].get("ack_visible") or ack.get("visible"))
    sequence_number = int(c2["sequence_number"])
    ack_sequence = int(ack.get("sequence_number", sequence_number))
    ack_gap = abs(sequence_number - ack_sequence)
    ack_delay = int(observed["comms"].get("ack_delay_ms", 0))
    accepted_with_gap = ack.get("status") == "ACCEPTED" and ack_gap > 0
    effect_score = min(1.0, (0.25 if ack_visible else 0.0) + ack_gap / 4.0 + ack_delay / 1400.0)

    return _goal_result(
        ctx,
        effect_score=effect_score,
        goal_success=ack_visible and (ack_gap >= 1 or ack_delay >= 300 or accepted_with_gap),
        evidence={
            "ack_visible": ack_visible,
            "sequence_number": sequence_number,
            "ack_sequence_number": ack_sequence,
            "ack_gap": ack_gap,
            "ack_delay_ms": ack_delay,
            "accepted_with_gap": accepted_with_gap,
        },
    )


def _score_channel_state_suppression(**ctx: Any) -> dict[str, Any]:
    observed = ctx["pre_defense_state"]["blue_observed"]
    comms = observed["comms"]
    packet_loss = float(comms.get("packet_loss", 0.0))
    latency_ms = int(comms.get("latency_ms", 0))
    heartbeat_gap_ms = int(comms.get("heartbeat_gap_ms", 0))
    jitter_ms = int(comms.get("packet_interval_jitter_ms", 0))
    queue_depth = int(comms.get("message_queue_depth", 0))
    effect_score = min(
        1.0,
        packet_loss * 2.2 + latency_ms / 1200.0 + heartbeat_gap_ms / 6000.0 + jitter_ms / 1200.0 + queue_depth / 40.0,
    )

    return _goal_result(
        ctx,
        effect_score=effect_score,
        goal_success=packet_loss >= 0.05 or heartbeat_gap_ms >= 1500 or latency_ms >= 300 or jitter_ms >= 150,
        evidence={
            "packet_loss": round(packet_loss, 4),
            "latency_ms": latency_ms,
            "heartbeat_gap_ms": heartbeat_gap_ms,
            "packet_interval_jitter_ms": jitter_ms,
            "message_queue_depth": queue_depth,
        },
    )


def _score_blue_overdefense_attrition(**ctx: Any) -> dict[str, Any]:
    action_cost = _action_cost(ctx["actions"])
    pre_availability = float(ctx["pre_defense_state"]["mission"]["availability"])
    post_availability = float(ctx["post_defense_state"]["mission"]["availability"])
    availability_drop = max(0.0, pre_availability - post_availability)
    combat_attrition = ctx["post_defense_state"].get("defense_runtime", {}).get("combat_attrition", {})
    round_defense_cost = float(combat_attrition.get("round_defense_cost", action_cost))
    red_round_attack_cost = float(combat_attrition.get("red_round_attack_cost", 0.0))
    net_defense_cost = max(0.0, round_defense_cost - red_round_attack_cost)
    defense_to_attack_cost_ratio = round_defense_cost / max(red_round_attack_cost, 0.01)
    cost_effective = net_defense_cost >= 0.06 and defense_to_attack_cost_ratio >= 1.20
    action_count = len(ctx["actions"])
    high_cost_actions = [action.action for action in ctx["actions"] if action.availability_cost >= 0.05]
    effect_score = min(
        1.0,
        action_cost * 2.0
        + round_defense_cost * 1.2
        + availability_drop * 2.4
        + net_defense_cost * 1.4
        + action_count / 14.0,
    )
    pressure_success = action_cost >= 0.10 or availability_drop >= 0.08 or len(high_cost_actions) >= 2

    return _goal_result(
        ctx,
        effect_score=effect_score,
        goal_success=pressure_success and cost_effective,
        evidence={
            "action_cost": action_cost,
            "availability_drop": round(availability_drop, 4),
            "round_defense_cost": round(round_defense_cost, 4),
            "red_round_attack_cost": round(red_round_attack_cost, 4),
            "net_defense_cost": round(net_defense_cost, 4),
            "defense_to_attack_cost_ratio": round(defense_to_attack_cost_ratio, 4),
            "cost_effective": cost_effective,
            "defense_action_count": action_count,
            "high_cost_actions": high_cost_actions,
        },
        availability_pressure_bonus=0.15,
    )


def _score_detection_boundary_probe(**ctx: Any) -> dict[str, Any]:
    attack_evidence = _score_domain_mismatch_goal(**ctx)
    effect_score = float(attack_evidence["effect_score"])
    action_cost = _action_cost(ctx["actions"])
    detector_feedback = bool(ctx["threats"]) or ctx["detection_success"]
    low_cost_probe = action_cost < 0.10
    reward = 0.25 + 0.35 * effect_score + (0.20 if detector_feedback else 0.0) + (0.15 if low_cost_probe else 0.0)
    if ctx["recovery_success"]:
        reward -= 0.05

    attack_evidence.update(
        {
            "goal_success": bool(effect_score >= 0.20 and detector_feedback),
            "goal_reward": round(min(1.0, max(0.0, reward)), 4),
            "evidence": {
                **attack_evidence["evidence"],
                "detector_feedback_available": detector_feedback,
                "low_cost_probe": low_cost_probe,
                "action_cost": action_cost,
            },
        }
    )
    return attack_evidence


def _score_domain_mismatch_goal(**ctx: Any) -> dict[str, Any]:
    attack = ctx["attack"]
    state = ctx["pre_defense_state"]
    if attack.target_domain == "mission":
        return _score_wrong_target_selection(**ctx)
    if attack.target_domain == "telemetry":
        return _score_telemetry_trust_erosion(**ctx)
    if attack.target_domain == "command":
        return _score_command_stale_acceptance(**ctx)
    return _goal_result(
        ctx,
        effect_score=1.0 if ctx["attack_success"] else 0.0,
        goal_success=ctx["attack_success"],
        evidence={
            "unsupported_domain": attack.target_domain,
            "available_state_keys": sorted(state.keys()),
        },
    )


def _goal_result(
    ctx: dict[str, Any],
    *,
    effect_score: float,
    goal_success: bool,
    evidence: dict[str, Any],
    availability_pressure_bonus: float = 0.0,
) -> dict[str, Any]:
    effect_score = round(min(1.0, max(0.0, float(effect_score))), 4)
    reward = _reward_from_effect(effect_score, ctx["detection_success"], ctx["recovery_success"])
    reward += availability_pressure_bonus if goal_success else 0.0
    return {
        "goal_id": (ctx["red_goal"] or {}).get("goal_id"),
        "target_domain": ctx["attack"].target_domain,
        "intended_effect": (ctx["red_goal"] or {}).get("intended_effect"),
        "goal_success": bool(goal_success),
        "effect_score": effect_score,
        "goal_reward": round(min(1.0, max(0.0, reward)), 4),
        "evidence": evidence,
    }


def _reward_from_effect(effect_score: float, detection_success: bool, recovery_success: bool) -> float:
    reward = 0.10 + 0.55 * effect_score
    reward += 0.18 if not detection_success else -0.08
    reward += -0.08 if recovery_success else 0.08
    return round(min(1.0, max(0.0, reward)), 4)


def _top_area(priorities: dict[str, float]) -> str:
    return max(priorities, key=lambda area: float(priorities[area]))


def _action_cost(actions: list[DefenseAction]) -> float:
    return round(sum(float(action.availability_cost) for action in actions), 4)


def _default_goal_for_attack(attack_name: str) -> str:
    if attack_name == "PRIORITY_POISONING":
        return "WRONG_TARGET_SELECTION"
    if attack_name == "TELEMETRY_FDI":
        return "TELEMETRY_TRUST_EROSION"
    if attack_name == "TIME_DESYNC_REPLAY":
        return "COMMAND_STALE_ACCEPTANCE"
    return "DOMAIN_MISMATCH"


GOAL_SCORERS = {
    "WRONG_TARGET_SELECTION": _score_wrong_target_selection,
    "TELEMETRY_TRUST_EROSION": _score_telemetry_trust_erosion,
    "COMMAND_STALE_ACCEPTANCE": _score_command_stale_acceptance,
    "ACK_CAUSAL_CONFUSION": _score_ack_causal_confusion,
    "CHANNEL_STATE_SUPPRESSION": _score_channel_state_suppression,
    "BLUE_OVERDEFENSE_ATTRITION": _score_blue_overdefense_attrition,
    "DETECTION_BOUNDARY_PROBE": _score_detection_boundary_probe,
}
