"""Minimal defense planner and action application."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from dah_flawless.config import (
    LOW_CONFIDENCE_THRESHOLD,
    TRUST_ESCALATION_THRESHOLD,
    TRUST_PENALTY_FACTOR,
    TRUST_RECOVERY_PER_ROUND,
    TRUST_RESTORE_BONUS,
    TRUSTED_RESTORE_DEGRADED_COST_MULTIPLIER,
)
from dah_flawless.schemas import DefenseAction, MissionRisk, Threat, decision


def plan_defense(
    threats: list[Threat],
    risks: list[MissionRisk],
    mission_state: dict,
    defense_runtime: dict | None = None,
) -> tuple[list[DefenseAction], dict]:
    actions: list[DefenseAction] = []
    domain_trust = (defense_runtime or {}).get("domain_trust", {})

    for threat in threats:
        trust = domain_trust.get(threat.target, 1.0)
        confirmed = threat.confidence >= LOW_CONFIDENCE_THRESHOLD or trust < TRUST_ESCALATION_THRESHOLD
        actions.extend(_actions_for_threat(threat, confirmed))

    cost = round(sum(action.availability_cost for action in actions), 4)
    log = decision(
        "DefensePlannerAgent",
        "action_selected",
        "staged_defense_by_confidence_and_trust",
        before={
            "threats": [threat.to_dict() for threat in threats],
            "availability": mission_state["availability"],
            "domain_trust": domain_trust,
        },
        after={"actions": [action.to_dict() for action in actions], "availability_cost": cost},
    )
    return actions, log


def apply_defense_actions(
    state: dict,
    actions: list[DefenseAction],
    history: dict,
    threats: list[Threat] | None = None,
    capabilities: dict | None = None,
) -> dict:
    next_state = deepcopy(state)
    capabilities = capabilities if capabilities is not None else next_state.get("capabilities", {})
    active_actions = []
    effective_actions: list[DefenseAction] = []
    for action in actions:
        active = _effective_action_for_capability(action, capabilities)
        effective_actions.append(active)
        active_actions.append(active.to_dict())
        if not active.status.startswith("FAILED"):
            _apply_single_action(next_state, active, history)

    total_cost = sum(action.availability_cost for action in effective_actions)
    next_state["mission"]["availability"] = max(0.0, round(next_state["mission"]["availability"] - total_cost, 4))
    next_state["mission"]["trust_budget"] = max(0.0, round(next_state["mission"]["trust_budget"] - total_cost * 0.8, 4))
    next_state["defense_runtime"]["active_defenses"] = active_actions
    next_state["defense_runtime"]["pending_defenses"] = []
    _update_domain_trust(next_state, effective_actions, threats or [])
    return next_state


def _effective_action_for_capability(action: DefenseAction, capabilities: dict) -> DefenseAction:
    availability_cost = action.availability_cost
    status = "DONE"

    if _is_trusted_restore_action(action):
        restore_capability = capabilities.get("trusted_restore", "OK")
        if restore_capability == "DEGRADED":
            availability_cost = round(availability_cost * TRUSTED_RESTORE_DEGRADED_COST_MULTIPLIER, 4)
            status = "DONE_RESTORE_DEGRADED"
        elif restore_capability == "UNAVAILABLE":
            status = "FAILED_RESTORE_UNAVAILABLE"

    return DefenseAction(
        action=action.action,
        target=action.target,
        priority=action.priority,
        duration_ticks=0,
        availability_cost=availability_cost,
        status=status,
    )


def _actions_for_threat(threat: Threat, confirmed: bool) -> list[DefenseAction]:
    if not confirmed:
        return [
            DefenseAction("OBSERVE_DOMAIN", threat.target, 1, 1, 0.005),
            DefenseAction("REQUEST_REVALIDATION", f"blue_observed.{threat.target}", 1, 1, 0.01),
        ]

    if threat.target == "telemetry":
        return [
            DefenseAction("QUARANTINE_FIELD", "blue_observed.telemetry.battery_percent", 3, 1, 0.04),
            DefenseAction("QUARANTINE_FIELD", "blue_observed.telemetry.motor_status", 3, 1, 0.04),
            DefenseAction("FALLBACK_TO_TRUSTED_STATE", "blue_observed.telemetry", 2, 1, 0.03),
        ]
    if threat.target == "mission":
        return [
            DefenseAction("QUARANTINE_FIELD", "blue_observed.mission.area_priority", 3, 1, 0.05),
            DefenseAction("REQUEST_REVALIDATION", "blue_observed.mission", 1, 1, 0.02),
        ]
    if threat.target == "command":
        return [
            DefenseAction("HOLD_COMMAND", "blue_observed.c2_message.command", 3, 1, 0.06),
            DefenseAction("REQUEST_REVALIDATION", "blue_observed.c2_message", 2, 1, 0.03),
        ]
    return [DefenseAction("OBSERVE_DOMAIN", threat.target, 1, 1, 0.005)]


def _update_domain_trust(state: dict, actions: list[DefenseAction], threats: list[Threat]) -> None:
    trust_scores = state["defense_runtime"].setdefault(
        "domain_trust", {"telemetry": 1.0, "mission": 1.0, "command": 1.0}
    )
    threat_by_domain = {threat.target: threat for threat in threats}

    for domain in ("telemetry", "mission", "command"):
        before = trust_scores.get(domain, 1.0)
        if domain in threat_by_domain:
            after = before - threat_by_domain[domain].confidence * TRUST_PENALTY_FACTOR
        else:
            after = before + TRUST_RECOVERY_PER_ROUND
        if any(_action_domain(action) == domain and _restores_trusted_state(action) for action in actions):
            after += TRUST_RESTORE_BONUS
        trust_scores[domain] = min(1.0, max(0.0, round(after, 4)))


def _action_domain(action: DefenseAction) -> str:
    if action.target.startswith("blue_observed."):
        return action.target.split(".")[1]
    return action.target


def _restores_trusted_state(action: DefenseAction) -> bool:
    return _is_trusted_restore_action(action) and not action.status.startswith("FAILED")


def _is_trusted_restore_action(action: DefenseAction) -> bool:
    return action.action in {"FALLBACK_TO_TRUSTED_STATE", "HOLD_COMMAND", "QUARANTINE_FIELD"}


def _apply_single_action(state: dict, action: DefenseAction, history: dict) -> None:
    if action.action in {"QUARANTINE_FIELD", "FALLBACK_TO_TRUSTED_STATE"}:
        target = action.target.removeprefix("blue_observed.")
        fallback = _get_path(history["last_observed"], target)
        _set_path(state["blue_observed"], target, deepcopy(fallback))
    elif action.action == "HOLD_COMMAND":
        state["blue_observed"]["c2_message"]["command"] = history["last_command"]
        state["blue_observed"]["c2_message"]["sequence_number"] = history["last_sequence_number"]
        state["blue_observed"]["time"]["received_timestamp"] = history["last_received_timestamp"]
    elif action.action == "REQUEST_REVALIDATION":
        state["blue_observed"]["comms"]["message_queue_depth"] += 1


def _get_path(data: dict, path: str) -> Any:
    cursor: Any = data
    for part in path.split("."):
        cursor = cursor[part]
    return cursor


def _set_path(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cursor: Any = data
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value
