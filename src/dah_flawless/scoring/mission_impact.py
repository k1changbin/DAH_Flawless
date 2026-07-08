"""Mission-impact scoring for simulated Red effects.

This module keeps a separate score for operational impact. The existing
``attack_success`` flag still says whether observed values diverged from
scorer truth; mission impact asks whether that divergence could plausibly alter
mission decisions, safety posture, or availability inside the simulator.
"""

from __future__ import annotations

from typing import Any

from dah_flawless.blue.observe_policy_gate import (
    compact_policy_gate,
    domain_policy_decision,
    domain_use_weight,
)
from dah_flawless.config import AVAIL_FLOOR
from dah_flawless.scoring.telemetry_learning import telemetry_learning_signal
from dah_flawless.schemas import Attack, DefenseAction


def assess_mission_impact(
    *,
    pre_defense_state: dict,
    post_defense_state: dict,
    attack: Attack,
    red_goal: dict | None,
    actions: list[DefenseAction],
) -> dict[str, Any]:
    """Return a bounded mission-impact score and component evidence."""

    components = {
        "mission_belief": _mission_belief_impact(pre_defense_state),
        "telemetry_safety": _telemetry_safety_impact(pre_defense_state),
        "command_freshness": _command_freshness_impact(pre_defense_state),
        "availability_pressure": _availability_pressure_impact(pre_defense_state, post_defense_state, actions),
    }
    policy_gate = _observe_policy_gate(post_defense_state) or _observe_policy_gate(pre_defense_state)
    components = _apply_policy_gate_to_components(components, policy_gate)
    primary_component = max(components, key=lambda name: components[name]["score"])
    target_component = _target_component(attack.target_domain, (red_goal or {}).get("goal_id"))
    target_score = components.get(target_component, components[primary_component])["score"]
    primary_score = components[primary_component]["score"]
    score = round(max(target_score, primary_score * 0.85), 4)
    return {
        "mission_impact_score": score,
        "level": _impact_level(score),
        "primary_component": primary_component,
        "target_component": target_component,
        "components": components,
        "observe_policy_gate": compact_policy_gate(policy_gate),
        "algorithm": "mission_impact_rule_score_v2_policy_gated",
    }


def blend_goal_reward_with_mission_impact(goal_score: dict[str, Any], mission_impact: dict[str, Any]) -> dict[str, Any]:
    """Blend goal reward with mission impact for contract-supported goals only."""

    updated = dict(goal_score)
    impact_score = float(mission_impact.get("mission_impact_score", 0.0))
    supported = updated.get("contract_alignment", {}).get("supported_goal", True)
    updated["mission_impact_score"] = round(impact_score, 4)
    if not supported:
        updated["mission_impact_reward_adjustment"] = 0.0
        updated["reward_algorithm"] = "contract_violation_reward_clamp"
        return updated

    before = float(updated.get("goal_reward", 0.0))
    after = round(min(1.0, max(0.0, 0.65 * before + 0.35 * impact_score)), 4)
    updated["goal_reward_before_mission_impact"] = round(before, 4)
    updated["goal_reward"] = after
    updated["mission_impact_reward_adjustment"] = round(after - before, 4)
    updated["reward_algorithm"] = "goal_reward_blended_with_mission_impact_v1"
    return updated


def _mission_belief_impact(state: dict) -> dict[str, Any]:
    truth = state["world"]["mission"]["area_priority"]
    observed_mission = state["blue_observed"]["mission"]
    observed = observed_mission["area_priority"]
    truth_top = _top_area(truth)
    observed_top = _top_area(observed)
    recommended = observed_mission.get("recommended_area")
    max_delta = max(abs(float(truth[area]) - float(observed.get(area, 0.0))) for area in truth)
    top_mismatch = observed_top != truth_top
    recommendation_mismatch = recommended is not None and recommended != truth_top
    score = min(1.0, max_delta * 0.65 + (0.25 if top_mismatch else 0.0) + (0.20 if recommendation_mismatch else 0.0))
    return {
        "score": round(score, 4),
        "truth_top_area": truth_top,
        "observed_top_area": observed_top,
        "recommended_area": recommended,
        "max_priority_delta": round(max_delta, 4),
        "top_mismatch": top_mismatch,
        "recommendation_mismatch": recommendation_mismatch,
    }


def _telemetry_safety_impact(state: dict) -> dict[str, Any]:
    truth = state["world"]
    observed = state["blue_observed"]["telemetry"]
    learning_signal = telemetry_learning_signal(state, include_world_truth=True)
    axes = learning_signal["axis_scores"]
    true_battery = float(truth["uav"]["battery_percent"])
    observed_battery = float(observed["battery_percent"])
    battery_delta = abs(observed_battery - true_battery)
    motor_mismatch = observed["motor_status"] != truth["uav"]["motor_status"]
    return_required = bool(truth["mission"].get("return_required"))
    false_continue_margin = return_required and true_battery <= 25 and observed_battery >= 45
    hidden_fault = truth["uav"]["motor_status"] != "OK" and observed["motor_status"] == "OK"
    impossible_energy = observed_battery > true_battery and float(observed.get("battery_drain_rate", 0.0)) > 0
    direct_score = min(
        1.0,
        battery_delta / 60.0
        + (0.30 if false_continue_margin else 0.0)
        + (0.22 if motor_mismatch else 0.0)
        + (0.18 if hidden_fault else 0.0)
        + (0.10 if impossible_energy else 0.0),
    )
    split_channel_score = min(
        1.0,
        axes["telemetry_command_confusion"] * 0.30
        + axes["stale_state_acceptance"] * 0.18
        + axes["wrong_safety_decision"] * 0.42
        + axes["tx_rx_consistency_pressure"] * 0.07
        + axes["legacy_sensor_delta"] * 0.03,
    )
    score = max(direct_score, split_channel_score)
    return {
        "score": round(score, 4),
        "direct_safety_score": round(direct_score, 4),
        "split_channel_safety_score": round(split_channel_score, 4),
        "telemetry_command_confusion": axes["telemetry_command_confusion"],
        "stale_state_acceptance": axes["stale_state_acceptance"],
        "wrong_safety_decision": axes["wrong_safety_decision"],
        "tx_rx_consistency_pressure": axes["tx_rx_consistency_pressure"],
        "legacy_sensor_delta": axes["legacy_sensor_delta"],
        "true_battery_percent": true_battery,
        "observed_battery_percent": observed_battery,
        "battery_delta": round(battery_delta, 4),
        "motor_mismatch": motor_mismatch,
        "false_continue_margin": false_continue_margin,
        "hidden_fault": hidden_fault,
        "impossible_energy": impossible_energy,
        "telemetry_learning_signal": learning_signal,
    }


def _command_freshness_impact(state: dict) -> dict[str, Any]:
    truth = state["world"]
    observed = state["blue_observed"]
    expected_sequence = int(truth["command"]["expected_sequence_number"])
    received_sequence = int(observed["c2_message"]["sequence_number"])
    true_timestamp = int(truth["time"]["true_timestamp"])
    received_timestamp = int(observed["time"]["received_timestamp"])
    sequence_lag = max(0, expected_sequence - received_sequence)
    timestamp_lag = max(0, true_timestamp - received_timestamp)
    command_mismatch = observed["c2_message"]["command"] != truth["command"]["last_valid_command"]
    unsafe_continue = bool(truth["mission"].get("return_required")) and observed["c2_message"]["command"] != "RETURN_TO_BASE"
    score = min(
        1.0,
        sequence_lag / 10.0
        + timestamp_lag / 240.0
        + (0.25 if command_mismatch else 0.0)
        + (0.25 if unsafe_continue else 0.0),
    )
    return {
        "score": round(score, 4),
        "sequence_lag": sequence_lag,
        "timestamp_lag_s": timestamp_lag,
        "command_mismatch": command_mismatch,
        "unsafe_continue": unsafe_continue,
    }


def _availability_pressure_impact(
    pre_defense_state: dict,
    post_defense_state: dict,
    actions: list[DefenseAction],
) -> dict[str, Any]:
    pre_mission = pre_defense_state["mission"]
    post_mission = post_defense_state["mission"]
    availability_drop = max(0.0, float(pre_mission["availability"]) - float(post_mission["availability"]))
    trust_budget_drop = max(0.0, float(pre_mission["trust_budget"]) - float(post_mission["trust_budget"]))
    action_cost = sum(float(action.availability_cost) for action in actions)
    floor_pressure = max(0.0, AVAIL_FLOOR - float(post_mission["availability"]))
    score = min(1.0, availability_drop * 3.0 + trust_budget_drop * 1.5 + action_cost * 1.5 + floor_pressure * 2.0)
    return {
        "score": round(score, 4),
        "availability_before": round(float(pre_mission["availability"]), 4),
        "availability_after": round(float(post_mission["availability"]), 4),
        "availability_drop": round(availability_drop, 4),
        "trust_budget_drop": round(trust_budget_drop, 4),
        "action_cost": round(action_cost, 4),
        "floor_pressure": round(floor_pressure, 4),
    }


def _target_component(target_domain: str, goal_id: str | None) -> str:
    if goal_id == "BLUE_OVERDEFENSE_ATTRITION":
        return "availability_pressure"
    if target_domain == "mission":
        return "mission_belief"
    if target_domain == "telemetry":
        return "telemetry_safety"
    if target_domain == "command":
        return "command_freshness"
    return "availability_pressure"


def _observe_policy_gate(state: dict) -> dict | None:
    return state.get("defense_runtime", {}).get("observe_policy_gate")


def _apply_policy_gate_to_components(
    components: dict[str, dict[str, Any]],
    policy_gate: dict | None,
) -> dict[str, dict[str, Any]]:
    if not policy_gate:
        return components

    component_domains = {
        "mission_belief": "mission",
        "telemetry_safety": "telemetry",
        "command_freshness": "command",
    }
    updated = {name: dict(value) for name, value in components.items()}
    for component, domain in component_domains.items():
        if component not in updated:
            continue
        use_weight = domain_use_weight(policy_gate, domain)
        mitigation_factor = round(0.20 + 0.80 * use_weight, 4)
        raw_score = float(updated[component].get("score", 0.0))
        adjusted_score = round(raw_score * mitigation_factor, 4)
        domain_decision = domain_policy_decision(policy_gate, domain) or {}
        updated[component]["raw_score_before_policy"] = round(raw_score, 4)
        updated[component]["score"] = adjusted_score
        updated[component]["observe_policy_gate"] = {
            "domain": domain,
            "decision": domain_decision.get("decision", "ALLOW"),
            "allowed_use": domain_decision.get("allowed_use", "authoritative"),
            "trust_score": domain_decision.get("trust_score"),
            "required_assurance": domain_decision.get("required_assurance"),
            "use_weight": round(use_weight, 4),
            "mitigation_factor": mitigation_factor,
            "interpretation": "external observe impact scaled by usage authority",
        }
    return updated


def _impact_level(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    if score >= 0.20:
        return "LOW"
    return "MINIMAL"


def _top_area(priorities: dict[str, float]) -> str:
    return max(priorities, key=lambda area: float(priorities[area]))
