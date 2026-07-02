"""Minimal defense planner and action application."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from dah_flawless.schemas import DefenseAction, MissionRisk, Threat, decision


def plan_defense(threats: list[Threat], risks: list[MissionRisk], mission_state: dict) -> tuple[list[DefenseAction], dict]:
    actions: list[DefenseAction] = []

    for threat in threats:
        if threat.target == "telemetry":
            actions.extend(
                [
                    DefenseAction("QUARANTINE_FIELD", "blue_observed.telemetry.battery_percent", 3, 1, 0.04),
                    DefenseAction("QUARANTINE_FIELD", "blue_observed.telemetry.motor_status", 3, 1, 0.04),
                    DefenseAction("FALLBACK_TO_TRUSTED_STATE", "blue_observed.telemetry", 2, 1, 0.03),
                ]
            )
        elif threat.target == "mission":
            actions.extend(
                [
                    DefenseAction("QUARANTINE_FIELD", "blue_observed.mission.area_priority", 3, 1, 0.05),
                    DefenseAction("REQUEST_REVALIDATION", "blue_observed.mission", 1, 1, 0.02),
                ]
            )
        elif threat.target == "command":
            actions.extend(
                [
                    DefenseAction("HOLD_COMMAND", "blue_observed.c2_message.command", 3, 1, 0.06),
                    DefenseAction("REQUEST_REVALIDATION", "blue_observed.c2_message", 2, 1, 0.03),
                ]
            )

    cost = round(sum(action.availability_cost for action in actions), 4)
    log = decision(
        "DefensePlannerAgent",
        "action_selected",
        "minimal_defense_by_target",
        before={"threats": [threat.to_dict() for threat in threats], "availability": mission_state["availability"]},
        after={"actions": [action.to_dict() for action in actions], "availability_cost": cost},
    )
    return actions, log


def apply_defense_actions(state: dict, actions: list[DefenseAction], history: dict) -> dict:
    next_state = deepcopy(state)
    active_actions = []
    for action in actions:
        active = DefenseAction(
            action=action.action,
            target=action.target,
            priority=action.priority,
            duration_ticks=0,
            availability_cost=action.availability_cost,
            status="DONE",
        )
        active_actions.append(active.to_dict())
        _apply_single_action(next_state, active, history)

    total_cost = sum(action.availability_cost for action in actions)
    next_state["mission"]["availability"] = max(0.0, round(next_state["mission"]["availability"] - total_cost, 4))
    next_state["mission"]["trust_budget"] = max(0.0, round(next_state["mission"]["trust_budget"] - total_cost * 0.8, 4))
    next_state["defense_runtime"]["active_defenses"] = active_actions
    next_state["defense_runtime"]["pending_defenses"] = []
    return next_state


def _apply_single_action(state: dict, action: DefenseAction, history: dict) -> None:
    if action.action in {"QUARANTINE_FIELD", "FALLBACK_TO_TRUSTED_STATE"}:
        target = action.target.removeprefix("blue_observed.")
        fallback = _get_path(history["last_observed"], target)
        _set_path(state["blue_observed"], target, deepcopy(fallback))
    elif action.action == "HOLD_COMMAND":
        state["blue_observed"]["c2_message"]["command"] = history["last_command"]
        state["blue_observed"]["c2_message"]["sequence_number"] = history["last_sequence_number"]
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
