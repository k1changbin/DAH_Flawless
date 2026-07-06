"""Rolling log-memory compression for long simulation runs.

The simulator keeps full output logs for auditability. This module only
compresses the *planning context* passed back to Red, so long runs can preserve
trend information without feeding every previous round back into selection.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from dah_flawless.attacks.goal_planner import GOAL_CATALOG
from dah_flawless.scoring.metrics import summarize_logs

DEFAULT_MEMORY_PROXY_SIZE = 12
COUNTERFACTUAL_VARIATION_RATE = 0.12
REWARD_JITTER = 0.06
IMPACT_JITTER = 0.08

_DOMAIN_BY_GOAL = {goal.goal_id: goal.target_domain for goal in GOAL_CATALOG}


def compress_log_memory(
    logs: list[dict],
    *,
    seed: int,
    compacted_at_step: int,
    proxy_size: int = DEFAULT_MEMORY_PROXY_SIZE,
) -> dict[str, Any]:
    """Compress logs into a saved memory snapshot and small proxy context."""

    if proxy_size < 1:
        raise ValueError("proxy_size must be >= 1")
    records = []
    for entry in logs:
        record = _record_from_log(entry)
        if record is not None:
            records.append(record)
    summary = summarize_logs(logs)
    rng = random.Random(seed + compacted_at_step * 7919 + len(records))
    proxy_logs = _build_proxy_logs(records, rng=rng, proxy_size=proxy_size, compacted_at_step=compacted_at_step)
    return {
        "memory_type": "rolling_log_memory",
        "version": 1,
        "compacted_at_step": compacted_at_step,
        "source_log_count": len(logs),
        "source_record_count": len(records),
        "proxy_log_count": len(proxy_logs),
        "summary": summary,
        "distributions": _distributions(records),
        "trend": _trend(records),
        "variation": {
            "counterfactual_rate": COUNTERFACTUAL_VARIATION_RATE,
            "reward_jitter": REWARD_JITTER,
            "impact_jitter": IMPACT_JITTER,
            "seed": seed,
        },
        "proxy_logs": proxy_logs,
    }


def write_memory_snapshot(path: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Append one memory snapshot to a compact JSON store."""

    path.parent.mkdir(parents=True, exist_ok=True)
    store = _load_memory_store(path)
    saved_snapshot = deepcopy(snapshot)
    saved_snapshot["proxy_logs"] = [
        _compact_proxy_for_store(proxy_log)
        for proxy_log in saved_snapshot.get("proxy_logs", [])
    ]
    store["snapshots"].append(saved_snapshot)
    store["latest"] = saved_snapshot
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return store


def memory_event_from_snapshot(snapshot: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    event = {
        "memory_type": snapshot["memory_type"],
        "version": snapshot["version"],
        "compacted_at_step": snapshot["compacted_at_step"],
        "source_log_count": snapshot["source_log_count"],
        "proxy_log_count": snapshot["proxy_log_count"],
        "summary": {
            "rounds": snapshot["summary"].get("rounds"),
            "attack_entropy": snapshot["summary"].get("attack_entropy"),
            "tactic_entropy": snapshot["summary"].get("tactic_entropy"),
            "goal_success_rate": snapshot["summary"].get("goal_success_rate"),
            "avg_goal_reward": snapshot["summary"].get("avg_goal_reward"),
            "avg_mission_impact_score": snapshot["summary"].get("avg_mission_impact_score"),
        },
        "trend": snapshot["trend"],
    }
    if path is not None:
        event["memory_path"] = str(path)
    return event


def _load_memory_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"memory_store_type": "rolling_log_memory_store", "snapshots": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("memory_store_type") != "rolling_log_memory_store":
        return {"memory_store_type": "rolling_log_memory_store", "snapshots": []}
    data.setdefault("snapshots", [])
    return data


def _record_from_log(entry: dict) -> dict[str, Any] | None:
    attack_name = (entry.get("attack") or {}).get("name")
    score = entry.get("score") or {}
    goal_id = ((entry.get("red_goal") or {}).get("goal_id") or score.get("goal_id"))
    if not attack_name or not goal_id:
        return None
    tactic = (entry.get("red_tactic") or {}).get("strategy") or "UNKNOWN"
    mission_impact = (score.get("evidence") or {}).get("mission_impact", {})
    goal_score = (score.get("evidence") or {}).get("goal_score", {})
    actions = entry.get("defense_actions") or []
    return {
        "attack": attack_name,
        "goal_id": goal_id,
        "target_domain": score.get("target_domain") or _DOMAIN_BY_GOAL.get(goal_id, "multi_domain"),
        "tactic": tactic,
        "winner": score.get("winner", "DRAW"),
        "attack_success": bool(score.get("attack_success", False)),
        "detection_success": bool(score.get("detection_success", False)),
        "recovery_success": bool(score.get("recovery_success", False)),
        "goal_success": bool(score.get("goal_success", False)),
        "goal_reward": float(score.get("goal_reward", goal_score.get("goal_reward", 0.0))),
        "mission_impact_score": float(mission_impact.get("mission_impact_score", 0.0)),
        "mission_impact_level": mission_impact.get("level", "MINIMAL"),
        "mission_impact_component": mission_impact.get("primary_component"),
        "defense_action_count": len(actions),
        "defense_action_cost": round(sum(float(action.get("availability_cost", 0.0)) for action in actions), 4),
    }


def _build_proxy_logs(
    records: list[dict[str, Any]],
    *,
    rng: random.Random,
    proxy_size: int,
    compacted_at_step: int,
) -> list[dict[str, Any]]:
    if not records:
        return []
    grouped = _group_records(records)
    proxy_logs = []
    for index in range(1, proxy_size + 1):
        record = deepcopy(_weighted_choice(grouped, rng))
        _apply_bounded_variation(record, rng)
        proxy_logs.append(_proxy_log_from_record(record, compacted_at_step=compacted_at_step, index=index))
    return proxy_logs


def _group_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["attack"], record["goal_id"], record["tactic"])
        if key not in grouped:
            grouped[key] = deepcopy(record)
            grouped[key]["count"] = 0
            grouped[key]["reward_sum"] = 0.0
            grouped[key]["impact_sum"] = 0.0
        item = grouped[key]
        item["count"] += 1
        item["reward_sum"] += record["goal_reward"]
        item["impact_sum"] += record["mission_impact_score"]
        for name in ("attack_success", "detection_success", "recovery_success", "goal_success"):
            item[name] = bool(item[name] or record[name])
    for item in grouped.values():
        item["goal_reward"] = round(item["reward_sum"] / item["count"], 4)
        item["mission_impact_score"] = round(item["impact_sum"] / item["count"], 4)
    return list(grouped.values())


def _weighted_choice(records: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    weights = [
        max(0.05, float(record["count"]) * (0.65 + 0.25 * record["goal_reward"] + 0.10 * record["mission_impact_score"]))
        for record in records
    ]
    total = sum(weights)
    pick = rng.uniform(0.0, total)
    cursor = 0.0
    for record, weight in zip(records, weights):
        cursor += weight
        if pick <= cursor:
            return record
    return records[-1]


def _apply_bounded_variation(record: dict[str, Any], rng: random.Random) -> None:
    record["goal_reward"] = _clamp01(record["goal_reward"] + rng.uniform(-REWARD_JITTER, REWARD_JITTER))
    record["mission_impact_score"] = _clamp01(
        record["mission_impact_score"] + rng.uniform(-IMPACT_JITTER, IMPACT_JITTER)
    )
    record["mission_impact_level"] = _impact_level(record["mission_impact_score"])
    if rng.random() < COUNTERFACTUAL_VARIATION_RATE:
        record["detection_success"] = not bool(record["detection_success"])
        if record["attack_success"] and not record["detection_success"]:
            record["winner"] = "RED_BREACH"
            record["recovery_success"] = False
        elif record["detection_success"]:
            record["winner"] = "BLUE_RECOVERY" if record["recovery_success"] else "BLUE"
    if rng.random() < COUNTERFACTUAL_VARIATION_RATE * 0.5:
        record["recovery_success"] = not bool(record["recovery_success"])
        if record["detection_success"]:
            record["winner"] = "BLUE_RECOVERY" if record["recovery_success"] else "BLUE"


def _proxy_log_from_record(record: dict[str, Any], *, compacted_at_step: int, index: int) -> dict[str, Any]:
    return {
        "round": compacted_at_step + index,
        "memory_proxy": True,
        "memory_source_step": compacted_at_step,
        "attack": {"name": record["attack"]},
        "red_goal": {"goal_id": record["goal_id"], "target_domain": record["target_domain"]},
        "red_tactic": {"strategy": record["tactic"]},
        "score": {
            "winner": record["winner"],
            "attack_success": record["attack_success"],
            "detection_success": record["detection_success"],
            "recovery_success": record["recovery_success"],
            "false_positive": False,
            "availability": 1.0,
            "target_domain": record["target_domain"],
            "goal_id": record["goal_id"],
            "goal_success": record["goal_success"],
            "goal_reward": round(record["goal_reward"], 4),
            "evidence": {
                "goal_score": {
                    "goal_id": record["goal_id"],
                    "goal_reward": round(record["goal_reward"], 4),
                    "memory_proxy": True,
                },
                "mission_impact": {
                    "mission_impact_score": round(record["mission_impact_score"], 4),
                    "level": record["mission_impact_level"],
                    "primary_component": record["mission_impact_component"],
                    "memory_proxy": True,
                },
                "defense_actions": ["MEMORY_PROXY_ACTION"] * int(record["defense_action_count"]),
            },
        },
        "defense_actions": [
            {"action": "MEMORY_PROXY_ACTION", "availability_cost": round(record["defense_action_cost"], 4)}
        ],
    }


def _distributions(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "attacks": dict(sorted(Counter(record["attack"] for record in records).items())),
        "goals": dict(sorted(Counter(record["goal_id"] for record in records).items())),
        "tactics": dict(sorted(Counter(record["tactic"] for record in records).items())),
        "winners": dict(sorted(Counter(record["winner"] for record in records).items())),
        "mission_impact_levels": dict(sorted(Counter(record["mission_impact_level"] for record in records).items())),
        "mission_impact_components": dict(
            sorted(Counter(record["mission_impact_component"] or "UNKNOWN" for record in records).items())
        ),
    }


def _trend(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    return {
        "avg_goal_reward": round(sum(record["goal_reward"] for record in records) / len(records), 4),
        "avg_mission_impact_score": round(
            sum(record["mission_impact_score"] for record in records) / len(records), 4
        ),
        "detection_rate": round(sum(1 for record in records if record["detection_success"]) / len(records), 4),
        "recovery_rate": round(sum(1 for record in records if record["recovery_success"]) / len(records), 4),
    }


def _compact_proxy_for_store(proxy_log: dict[str, Any]) -> dict[str, Any]:
    return {
        "attack": proxy_log["attack"],
        "red_goal": proxy_log["red_goal"],
        "red_tactic": proxy_log["red_tactic"],
        "score": proxy_log["score"],
        "memory_proxy": True,
    }


def _impact_level(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    if score >= 0.20:
        return "LOW"
    return "MINIMAL"


def _clamp01(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 4)
