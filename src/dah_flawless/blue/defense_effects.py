"""Blue defense-effect contracts and containment scoring.

The contract layer scores whether Blue contained a simulated Red effect before
full recovery. This is intentionally narrower than "Blue wins": containment can
be partial and still useful training signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dah_flawless.blue.goal_consistency import effect_id_from_goal_id, effect_ids_from_tags
from dah_flawless.blue.observe_policy_gate import policy_containment_score
from dah_flawless.config import AVAIL_FLOOR, RECOVERY_TARGET
from dah_flawless.schemas import Attack, DefenseAction, Threat


@dataclass(frozen=True)
class DefenseEffectContract:
    effect_id: str
    target_domain: str
    actions: tuple[str, ...]
    target_hints: tuple[str, ...]
    minimum_containment_score: float = 0.55


CONTRACTS: dict[str, DefenseEffectContract] = {
    "EFFECT_TELEMETRY_TRUST_EROSION": DefenseEffectContract(
        effect_id="EFFECT_TELEMETRY_TRUST_EROSION",
        target_domain="telemetry",
        actions=("QUARANTINE_FIELD", "FALLBACK_TO_TRUSTED_STATE", "REQUEST_REVALIDATION"),
        target_hints=("telemetry", "battery_percent", "motor_status"),
    ),
    "EFFECT_WRONG_TARGET_SELECTION": DefenseEffectContract(
        effect_id="EFFECT_WRONG_TARGET_SELECTION",
        target_domain="mission",
        actions=("QUARANTINE_FIELD", "REQUEST_REVALIDATION"),
        target_hints=("mission", "area_priority", "recommended_area"),
    ),
    "EFFECT_COMMAND_STALE_ACCEPTANCE": DefenseEffectContract(
        effect_id="EFFECT_COMMAND_STALE_ACCEPTANCE",
        target_domain="command",
        actions=("HOLD_COMMAND", "REQUEST_REVALIDATION", "QUARANTINE_FIELD"),
        target_hints=("c2_message", "command", "sequence_number"),
    ),
    "EFFECT_ACK_CAUSAL_CONFUSION": DefenseEffectContract(
        effect_id="EFFECT_ACK_CAUSAL_CONFUSION",
        target_domain="command",
        actions=("HOLD_COMMAND", "QUARANTINE_FIELD", "REQUEST_REVALIDATION"),
        target_hints=("ack", "c2_message", "comms"),
    ),
    "EFFECT_CHANNEL_STATE_SUPPRESSION": DefenseEffectContract(
        effect_id="EFFECT_CHANNEL_STATE_SUPPRESSION",
        target_domain="command",
        actions=("RESET_CHANNEL_TIMING", "REQUEST_REVALIDATION", "OBSERVE_DOMAIN"),
        target_hints=("comms", "command"),
    ),
}

DEFAULT_CONTRACT = DefenseEffectContract(
    effect_id="EFFECT_GENERIC_OBSERVE_CORRUPTION",
    target_domain="generic",
    actions=("OBSERVE_DOMAIN", "REQUEST_REVALIDATION", "QUARANTINE_FIELD"),
    target_hints=(),
    minimum_containment_score=0.50,
)


def assess_defense_containment(
    *,
    pre_defense_state: dict,
    post_defense_state: dict,
    attack: Attack,
    threats: list[Threat],
    actions: list[DefenseAction],
    goal_score: dict,
    detection_success: bool,
    recovery_success: bool,
    attack_success: bool,
) -> dict[str, Any]:
    """Score partial containment between detection and full recovery."""

    effect_id = _select_effect_id(attack, threats, goal_score)
    contract = CONTRACTS.get(effect_id, DEFAULT_CONTRACT)
    pressure_before = _effect_pressure(effect_id, pre_defense_state, attack)
    pressure_after = _effect_pressure(effect_id, post_defense_state, attack)
    effect_reduction = max(0.0, pressure_before - pressure_after)
    reduction_ratio = effect_reduction / max(pressure_before, 0.01)
    action_coverage = _action_coverage(contract, actions)
    operational_safety = _operational_safety(post_defense_state)
    detection_component = 1.0 if detection_success else 0.0
    recovery_component = 1.0 if recovery_success else 0.0
    low_cost_bonus = _low_cost_bonus(actions)
    policy_containment = policy_containment_score(
        post_defense_state.get("defense_runtime", {}).get("observe_policy_gate"),
        contract.target_domain,
    )
    policy_component = float(policy_containment["score"])
    raw_score = (
        0.22 * detection_component
        + 0.30 * reduction_ratio
        + 0.20 * action_coverage
        + 0.18 * operational_safety
        + 0.08 * recovery_component
        + 0.02 * low_cost_bonus
        + 0.38 * policy_component
    )
    if attack_success and not detection_success:
        no_detection_cap = 0.48 if policy_component >= 0.70 else 0.24
        raw_score = min(raw_score, no_detection_cap)
    containment_score = round(min(1.0, max(0.0, raw_score)), 4)
    contained = containment_score >= contract.minimum_containment_score

    return {
        "algorithm": "blue_defense_effect_contract_v2_policy_gate",
        "effect_id": effect_id,
        "target_domain": contract.target_domain,
        "contract": {
            "actions": list(contract.actions),
            "target_hints": list(contract.target_hints),
            "minimum_containment_score": contract.minimum_containment_score,
        },
        "pressure_before": round(pressure_before, 4),
        "pressure_after": round(pressure_after, 4),
        "effect_reduction": round(effect_reduction, 4),
        "effect_reduction_ratio": round(min(1.0, max(0.0, reduction_ratio)), 4),
        "action_coverage": round(action_coverage, 4),
        "operational_safety": round(operational_safety, 4),
        "policy_containment": policy_containment,
        "policy_containment_score": round(policy_component, 4),
        "detection_component": detection_component,
        "recovery_component": recovery_component,
        "low_cost_bonus": low_cost_bonus,
        "containment_score": containment_score,
        "contained": contained,
        "containment_level": _containment_level(containment_score, contained, recovery_success),
        "action_matches": _action_matches(contract, actions),
        "recovery_interpretation": _recovery_interpretation(recovery_success, policy_component),
    }


def _select_effect_id(attack: Attack, threats: list[Threat], goal_score: dict) -> str:
    goal_effect_id = effect_id_from_goal_id(goal_score.get("goal_id"))
    if goal_effect_id and goal_effect_id != "EFFECT_DETECTION_BOUNDARY_PROBE":
        return goal_effect_id

    for threat in threats:
        effect_ids = [effect for effect in effect_ids_from_tags(getattr(threat, "tags", ())) if effect in CONTRACTS]
        if effect_ids:
            return effect_ids[0]

    return {
        "TELEMETRY_FDI": "EFFECT_TELEMETRY_TRUST_EROSION",
        "PRIORITY_POISONING": "EFFECT_WRONG_TARGET_SELECTION",
        "TIME_DESYNC_REPLAY": "EFFECT_COMMAND_STALE_ACCEPTANCE",
    }.get(attack.name, "EFFECT_GENERIC_OBSERVE_CORRUPTION")


def _action_coverage(contract: DefenseEffectContract, actions: list[DefenseAction]) -> float:
    if not actions:
        return 0.0
    matches = _action_matches(contract, actions)
    return min(1.0, len(matches) / max(1, min(2, len(contract.actions))))


def _action_matches(contract: DefenseEffectContract, actions: list[DefenseAction]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    hints = tuple(hint.lower() for hint in contract.target_hints)
    for action in actions:
        target = action.target.lower()
        action_match = action.action in contract.actions
        target_match = not hints or any(hint in target for hint in hints)
        if action_match and target_match and not action.status.startswith("FAILED"):
            matches.append(action.to_dict())
    return matches


def _operational_safety(state: dict) -> float:
    availability = float(state["mission"].get("availability", 1.0))
    trust_budget = float(state["mission"].get("trust_budget", 1.0))
    availability_score = min(1.0, max(0.0, availability / max(AVAIL_FLOOR, 0.01)))
    trust_score = min(1.0, max(0.0, trust_budget / max(RECOVERY_TARGET, 0.01)))
    return round(0.70 * availability_score + 0.30 * trust_score, 4)


def _low_cost_bonus(actions: list[DefenseAction]) -> float:
    cost = sum(float(action.availability_cost) for action in actions)
    if cost <= 0:
        return 0.0
    if cost <= 0.03:
        return 1.0
    if cost <= 0.08:
        return 0.6
    if cost <= 0.12:
        return 0.3
    return 0.0


def _effect_pressure(effect_id: str, state: dict, attack: Attack) -> float:
    if effect_id == "EFFECT_TELEMETRY_TRUST_EROSION":
        truth = state["world"]["uav"]
        observed = state["blue_observed"]["telemetry"]
        battery_delta = abs(float(observed["battery_percent"]) - float(truth["battery_percent"]))
        motor_mismatch = 1.0 if observed["motor_status"] != truth["motor_status"] else 0.0
        drain_hint = (
            1.0
            if float(observed.get("battery_drain_rate", 0.0)) >= 0.8
            and observed["battery_percent"] > truth["battery_percent"]
            else 0.0
        )
        return min(1.0, battery_delta / 35.0 + 0.25 * motor_mismatch + 0.20 * drain_hint)

    if effect_id == "EFFECT_WRONG_TARGET_SELECTION":
        truth = state["world"]["mission"]["area_priority"]
        observed_mission = state["blue_observed"]["mission"]
        observed = observed_mission["area_priority"]
        truth_top = _top_area(truth)
        observed_top = _top_area(observed)
        recommended = observed_mission.get("recommended_area")
        max_delta = max(abs(float(truth[area]) - float(observed.get(area, 0.0))) for area in truth)
        return min(
            1.0,
            0.25
            + max_delta
            + (0.25 if observed_top != truth_top else 0.0)
            + (0.15 if recommended is not None and recommended != truth_top else 0.0),
        )

    if effect_id == "EFFECT_ACK_CAUSAL_CONFUSION":
        observed = state["blue_observed"]
        c2 = observed["c2_message"]
        ack = c2.get("ack", {})
        ack_visible = bool(observed["comms"].get("ack_visible") or ack.get("visible"))
        sequence_number = int(c2["sequence_number"])
        ack_sequence = int(ack.get("sequence_number", sequence_number))
        ack_gap = abs(sequence_number - ack_sequence)
        ack_delay = int(observed["comms"].get("ack_delay_ms", 0))
        return min(1.0, (0.25 if ack_visible else 0.0) + ack_gap / 4.0 + ack_delay / 1400.0)

    if effect_id == "EFFECT_CHANNEL_STATE_SUPPRESSION":
        comms = state["blue_observed"]["comms"]
        packet_loss = float(comms.get("packet_loss", 0.0))
        latency_ms = int(comms.get("latency_ms", 0))
        heartbeat_gap_ms = int(comms.get("heartbeat_gap_ms", 0))
        jitter_ms = int(comms.get("packet_interval_jitter_ms", 0))
        queue_depth = int(comms.get("message_queue_depth", 0))
        return min(
            1.0,
            packet_loss * 2.2
            + latency_ms / 1200.0
            + heartbeat_gap_ms / 6000.0
            + jitter_ms / 1200.0
            + queue_depth / 40.0,
        )

    if effect_id == "EFFECT_COMMAND_STALE_ACCEPTANCE":
        truth = state["world"]
        observed = state["blue_observed"]
        expected_sequence = int(truth["command"]["expected_sequence_number"])
        received_sequence = int(observed["c2_message"]["sequence_number"])
        true_timestamp = int(truth["time"]["true_timestamp"])
        received_timestamp = int(observed["time"]["received_timestamp"])
        sequence_lag = max(0, expected_sequence - received_sequence)
        timestamp_lag = max(0, true_timestamp - received_timestamp)
        command_mismatch = observed["c2_message"]["command"] != truth["command"]["last_valid_command"]
        return min(1.0, sequence_lag / 8.0 + timestamp_lag / 180.0 + (0.15 if command_mismatch else 0.0))

    if attack.target_domain:
        return 1.0 if _domain_mismatch(state, attack.target_domain) else 0.0
    return 0.0


def _domain_mismatch(state: dict, domain: str) -> bool:
    if domain == "telemetry":
        truth = state["world"]["uav"]
        observed = state["blue_observed"]["telemetry"]
        return (
            observed["battery_percent"] != truth["battery_percent"]
            or observed["motor_status"] != truth["motor_status"]
        )
    if domain == "mission":
        truth = state["world"]["mission"]["area_priority"]
        observed = state["blue_observed"]["mission"]["area_priority"]
        truth_top = _top_area(truth)
        return observed != truth or state["blue_observed"]["mission"].get("recommended_area") != truth_top
    if domain == "command":
        truth = state["world"]
        observed = state["blue_observed"]
        return (
            observed["c2_message"]["sequence_number"] < truth["command"]["expected_sequence_number"]
            or observed["c2_message"]["command"] != truth["command"]["last_valid_command"]
        )
    return False


def _top_area(priorities: dict[str, float]) -> str:
    return max(priorities, key=lambda area: float(priorities[area]))


def _containment_level(score: float, contained: bool, recovery_success: bool) -> str:
    if recovery_success and score >= 0.70:
        return "RECOVERED"
    if contained:
        return "CONTAINED"
    if score >= 0.35:
        return "PARTIAL_CONTAINMENT"
    return "UNCONTAINED"


def _recovery_interpretation(recovery_success: bool, policy_component: float) -> str:
    if recovery_success:
        return "strict_full_restore"
    if policy_component >= 0.70:
        return "policy_limited_authoritative_use_without_full_restore"
    return "partial_or_no_restore"
