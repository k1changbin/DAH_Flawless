"""Frontend-friendly combat log projection.

The simulator training log intentionally keeps full scorer, policy, and causal
evidence. This module builds a smaller UI contract from that log without
changing the training record.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

FRONTEND_LOG_SCHEMA = "dah_frontend_combat_log_v1"


def build_frontend_combat_log(logs: list[dict], summary: dict | None = None) -> dict[str, Any]:
    """Return a compact replay log for dashboard/frontend use."""

    summary = summary or {}
    frontend_rounds = [_round_view(entry) for entry in logs]
    return {
        "schema": FRONTEND_LOG_SCHEMA,
        "log_type": "round_combat_frontend_replay",
        "source": {
            "runner": summary.get("runner") or _first_value(logs, "runner"),
            "rounds": len(logs),
            "training_log_preserved": True,
            "note": "Derived projection. Use the JSONL training log for learning, audit, and hash-chain checks.",
        },
        "summary": _summary_view(frontend_rounds, summary),
        "filters": _filters(frontend_rounds),
        "policy_snapshot": _policy_snapshot(summary),
        "rounds": frontend_rounds,
    }


def write_frontend_combat_log(path: Path, logs: list[dict], summary: dict | None = None) -> dict[str, Any]:
    frontend_log = build_frontend_combat_log(logs, summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(frontend_log, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return frontend_log


def _summary_view(rounds: list[dict], summary: dict) -> dict[str, Any]:
    winner_sides = Counter(item["outcome"]["winner_side"] for item in rounds)
    winner_details = Counter(item["outcome"]["winner_detail"] for item in rounds)
    return {
        "rounds": len(rounds),
        "winner_sides": dict(sorted(winner_sides.items())),
        "winner_details": dict(sorted(winner_details.items())),
        "winners_raw": summary.get("winners", _count_outcomes(rounds, "winner")),
        "attacks": summary.get("attacks", _count_round_field(rounds, "attack", "name")),
        "goals": summary.get("goals", _count_round_field(rounds, "goal", "id")),
        "terminations": summary.get("terminations", _count_outcomes(rounds, "termination_reason")),
        "detection_rate": summary.get("detection_rate"),
        "attack_success_rate": summary.get("attack_success_rate"),
        "goal_success_rate": summary.get("goal_success_rate"),
        "avg_goal_reward": summary.get("avg_goal_reward"),
        "avg_mission_impact_score": summary.get("avg_mission_impact_score"),
        "avg_step_count": summary.get("avg_step_count") or _avg([item["step_count"] for item in rounds]),
        "final_availability": summary.get("final_availability"),
        "min_availability": summary.get("min_availability"),
    }


def _round_view(entry: dict) -> dict[str, Any]:
    attack = entry.get("attack", {})
    goal = entry.get("red_goal") or {}
    score = entry.get("score", {})
    outcome = _outcome_view(score, entry.get("termination_reason"))
    timeline = [_step_view(step) for step in entry.get("combat_steps", [])]
    return {
        "round": entry.get("round"),
        "title": _round_title(entry, outcome),
        "step_count": entry.get("step_count", len(timeline)),
        "attack": {
            "name": attack.get("name"),
            "target_domain": attack.get("target_domain"),
            "tactic": (entry.get("red_tactic") or {}).get("strategy"),
        },
        "goal": {
            "id": goal.get("goal_id") or score.get("goal_id"),
            "name": goal.get("goal_id") or score.get("goal_id"),
            "target_domain": goal.get("target_domain"),
            "intended_effect": goal.get("intended_effect"),
        },
        "outcome": outcome,
        "action_runs": _action_runs(timeline),
        "highlights": _highlights(timeline, outcome),
        "timeline": timeline,
    }


def _step_view(step: dict) -> dict[str, Any]:
    score = step.get("step_score", {})
    goal_score = score.get("evidence", {}).get("goal_score", {})
    mission_impact = score.get("evidence", {}).get("mission_impact", {})
    red_step = step.get("red_step", {})
    return {
        "step": step.get("step"),
        "red_action": step.get("red_action"),
        "blue_action": step.get("blue_action"),
        "phase": _phase(step),
        "suspicion": _round_float(step.get("blue_suspicion")),
        "detected": bool(step.get("detected_this_step", False)),
        "changed_paths": list(red_step.get("changed_paths", [])),
        "changed_path_count": len(red_step.get("changed_paths", [])),
        "delta": {
            "requested": red_step.get("requested_delta"),
            "applied": red_step.get("applied_delta"),
        },
        "defense_actions": [
            {
                "action": action.get("action"),
                "target": action.get("target"),
                "cost": action.get("availability_cost"),
                "status": action.get("status"),
            }
            for action in step.get("defense_actions", [])
        ],
        "score": {
            "winner": score.get("winner"),
            "winner_side": _winner_side(score),
            "winner_detail": _winner_detail(score),
            "attack_success": bool(score.get("attack_success", False)),
            "goal_success": bool(score.get("goal_success", False)),
            "detection_success": bool(score.get("detection_success", False)),
            "recovery_success": bool(score.get("recovery_success", False)),
            "goal_reward": _round_float(score.get("goal_reward")),
            "effect_score": _round_float(goal_score.get("effect_score")),
            "mission_impact_score": _round_float(mission_impact.get("mission_impact_score")),
            "availability": _round_float(score.get("availability")),
        },
        "budgets": _budget_view(step.get("budgets", {})),
    }


def _outcome_view(score: dict, termination_reason: str | None) -> dict[str, Any]:
    winner = score.get("winner")
    mission_impact = score.get("evidence", {}).get("mission_impact", {})
    return {
        "winner": winner,
        "winner_side": _winner_side(score),
        "winner_detail": _winner_detail(score),
        "termination_reason": termination_reason,
        "attack_success": bool(score.get("attack_success", False)),
        "goal_success": bool(score.get("goal_success", False)),
        "detection_success": bool(score.get("detection_success", False)),
        "recovery_success": bool(score.get("recovery_success", False)),
        "goal_id": score.get("goal_id"),
        "goal_reward": _round_float(score.get("goal_reward")),
        "mission_impact_score": _round_float(mission_impact.get("mission_impact_score")),
        "availability": _round_float(score.get("availability")),
        "reason": score.get("outcome_reason") or _outcome_reason(score, termination_reason),
    }


def _action_runs(timeline: list[dict]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for item in timeline:
        key = (item["red_action"], item["blue_action"])
        if current is None or current["red_action"] != key[0] or current["blue_action"] != key[1]:
            current = {
                "from_step": item["step"],
                "to_step": item["step"],
                "red_action": key[0],
                "blue_action": key[1],
                "count": 1,
            }
            runs.append(current)
        else:
            current["to_step"] = item["step"]
            current["count"] += 1
    return runs


def _highlights(timeline: list[dict], outcome: dict) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    _add_first(highlights, timeline, "first_detection", lambda step: step["detected"])
    _add_first(highlights, timeline, "first_defense", lambda step: bool(step["defense_actions"]))
    _add_first(highlights, timeline, "first_tactic_switch", lambda step: step["red_action"] == "SWITCH_TACTIC")
    _add_first(highlights, timeline, "finalize", lambda step: step["red_action"] == "FINALIZE_ATTACK")
    if outcome["winner_detail"] == "ATTRITION":
        highlights.append(
            {
                "type": "attrition_success",
                "step": timeline[-1]["step"] if timeline else None,
                "message": "Blue defense pressure crossed the attrition threshold.",
            }
        )
    return highlights


def _add_first(highlights: list[dict], timeline: list[dict], label: str, predicate: Any) -> None:
    for step in timeline:
        if predicate(step):
            highlights.append({"type": label, "step": step["step"], "message": _highlight_message(label, step)})
            return


def _highlight_message(label: str, step: dict) -> str:
    return {
        "first_detection": "Blue first detected this attack family.",
        "first_defense": "Blue first spent an active defense action.",
        "first_tactic_switch": "Red switched tactic after feedback.",
        "finalize": "Red declared the final attack state.",
    }.get(label, label)


def _phase(step: dict) -> str:
    red_action = step.get("red_action")
    blue_action = step.get("blue_action")
    if red_action == "PROBE_BOUNDARY":
        return "probe"
    if red_action in {"SLOW_DRIFT", "ESCALATE_MUTATION"}:
        return "mutation"
    if red_action == "SWITCH_TACTIC":
        return "adapt"
    if red_action == "FINALIZE_ATTACK":
        return "finalize"
    if blue_action == "DEFEND":
        return "defense"
    if red_action == "WAIT" and blue_action == "WAIT":
        return "idle"
    return "monitor"


def _budget_view(budgets: dict) -> dict[str, Any]:
    keys = (
        "red_budget",
        "blue_compute_budget",
        "blue_power_budget",
        "blue_round_defense_cost",
        "blue_defense_steps",
        "red_retry_attempts",
        "red_finalize_attempts",
        "red_round_attack_cost",
        "red_last_action_cost",
        "red_mutation_steps",
    )
    return {key: _round_float(budgets.get(key)) for key in keys if key in budgets}


def _policy_snapshot(summary: dict) -> dict[str, Any]:
    red = summary.get("red_policy_state", {})
    blue = summary.get("blue_policy_state", {})
    return {
        "red_weights": red.get("weights", {}),
        "red_goal_stats": red.get("goal_stats", {}),
        "blue_detection_sensitivity": blue.get("detection_sensitivity", {}),
        "blue_domain_trust": blue.get("domain_trust", {}),
    }


def _filters(rounds: list[dict]) -> dict[str, list[str]]:
    return {
        "attacks": _sorted_unique(item["attack"].get("name") for item in rounds),
        "goals": _sorted_unique(item["goal"].get("id") for item in rounds),
        "winner_sides": _sorted_unique(item["outcome"].get("winner_side") for item in rounds),
        "winner_details": _sorted_unique(item["outcome"].get("winner_detail") for item in rounds),
        "terminations": _sorted_unique(item["outcome"].get("termination_reason") for item in rounds),
    }


def _round_title(entry: dict, outcome: dict) -> str:
    attack = entry.get("attack", {}).get("name", "UNKNOWN")
    goal = (entry.get("red_goal") or {}).get("goal_id") or entry.get("score", {}).get("goal_id", "UNKNOWN")
    return f"R{entry.get('round', '?')} {attack} / {goal} -> {outcome['winner_side']}:{outcome['winner_detail']}"


def _winner_side(score: dict | str | None) -> str:
    if isinstance(score, dict):
        if score.get("winner_side"):
            return str(score["winner_side"])
        winner = score.get("winner")
    else:
        winner = score
    if not winner:
        return "UNKNOWN"
    if winner.startswith("RED"):
        return "RED"
    if winner.startswith("BLUE"):
        return "BLUE"
    if winner == "DRAW":
        return "DRAW"
    return "UNKNOWN"


def _winner_detail(score: dict | str | None) -> str:
    if isinstance(score, dict):
        if score.get("winner_detail"):
            return str(score["winner_detail"])
        winner = score.get("winner")
    else:
        winner = score
    if winner == "RED_BREACH":
        return "BREACH"
    if winner == "RED_ATTRITION":
        return "ATTRITION"
    if winner == "BLUE_RECOVERY":
        return "RECOVERY"
    if winner == "BLUE":
        return "DETECTION"
    if winner == "DRAW":
        return "NO_DECISION"
    return "UNKNOWN"


def _outcome_reason(score: dict, termination_reason: str | None) -> str:
    if score.get("winner") == "RED_BREACH" and not score.get("goal_success"):
        return "observe_corruption_without_detection_but_selected_goal_not_confirmed"
    if score.get("winner") == "RED_ATTRITION":
        return "blue_defense_pressure_reduced_mission_availability"
    if score.get("winner") == "BLUE_RECOVERY":
        return "blue_detected_and_restored_trusted_observe"
    if score.get("winner") == "BLUE":
        return "blue_detected_or_contained_final_attack"
    if termination_reason == "red_finalized_no_effect":
        return "red_finalized_without_confirmed_effect"
    return termination_reason or "not_available"


def _count_outcomes(rounds: list[dict], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item["outcome"].get(key, "UNKNOWN")) for item in rounds).items()))


def _count_round_field(rounds: list[dict], group: str, key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item[group].get(key, "UNKNOWN")) for item in rounds).items()))


def _sorted_unique(values: Any) -> list[str]:
    return sorted(str(value) for value in values if value is not None)


def _avg(values: list[Any]) -> float:
    cleaned = [float(value) for value in values if value is not None]
    return round(mean(cleaned), 4) if cleaned else 0.0


def _round_float(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    return value


def _first_value(logs: list[dict], key: str) -> Any:
    for entry in logs:
        if key in entry:
            return entry[key]
    return None
