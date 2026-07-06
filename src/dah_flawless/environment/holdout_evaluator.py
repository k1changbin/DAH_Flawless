"""Holdout evaluation for frozen Red/Blue policy states."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Optional

from dah_flawless.attacks.selector import ATTACK_DIVERSITY_WINDOW
from dah_flawless.config import DEFAULT_SCENARIO, DEFAULT_SEED, DEFAULT_STEPS_PER_EPISODE, SCENARIOS
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.scoring.metrics import summarize_logs


DEFAULT_HOLDOUT_SEEDS = (DEFAULT_SEED + 100, DEFAULT_SEED + 200)
DEFAULT_HOLDOUT_SCENARIOS = tuple(SCENARIOS)
DEFAULT_HOLDOUT_STEPS = min(10, DEFAULT_STEPS_PER_EPISODE)


def run_holdout_evaluation(
    *,
    red_policy_state: dict | None,
    blue_policy_state: dict | None,
    seeds: tuple[int, ...] | list[int] = DEFAULT_HOLDOUT_SEEDS,
    scenarios: tuple[str, ...] | list[str] = DEFAULT_HOLDOUT_SCENARIOS,
    steps_per_case: int = DEFAULT_HOLDOUT_STEPS,
    log_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
    stealth_mode: str | None = None,
    mutation_profile: str | None = None,
) -> tuple[list[dict], dict]:
    if not seeds:
        raise ValueError("holdout seeds must not be empty")
    if not scenarios:
        raise ValueError("holdout scenarios must not be empty")
    if steps_per_case < 1:
        raise ValueError("steps_per_case must be >= 1")
    invalid_scenarios = sorted(set(scenarios).difference(SCENARIOS))
    if invalid_scenarios:
        raise ValueError(f"unknown holdout scenario(s): {', '.join(invalid_scenarios)}")

    all_logs: list[dict] = []
    case_summaries: list[dict] = []
    prev_hash = GENESIS_HASH
    global_step = 0
    case_index = 0

    for scenario in scenarios:
        for seed in seeds:
            case_index += 1
            step_logs, step_summary = run_simulation(
                seed=seed,
                rounds=steps_per_case,
                scenario=scenario,
                stealth_mode=stealth_mode or (red_policy_state or {}).get("stealth_mode", "off"),
                mutation_profile=mutation_profile or (red_policy_state or {}).get("mutation_profile", "aggressive"),
                red_update_enabled=False,
                blue_update_enabled=False,
                red_policy_state=deepcopy(red_policy_state),
                blue_policy_state=deepcopy(blue_policy_state),
                previous_logs=deepcopy(all_logs),
                scripted_attacks=(),
            )
            for step_log in step_logs:
                global_step += 1
                body = deepcopy(step_log)
                body.pop("prev_hash", None)
                body.pop("this_hash", None)
                body["runner"] = "HoldoutEvaluator"
                body["holdout_case"] = case_index
                body["holdout_seed"] = seed
                body["holdout_scenario"] = scenario
                body["holdout_step"] = body["round"]
                body["global_step"] = global_step
                body["update_mode"] = {
                    "red_update_enabled": False,
                    "blue_update_enabled": False,
                }
                entry = attach_hash(prev_hash, body)
                prev_hash = entry["this_hash"]
                all_logs.append(entry)

            case_summary = dict(step_summary)
            case_summary.update(
                {
                    "runner": "HoldoutEvaluator",
                    "holdout_case": case_index,
                    "holdout_seed": seed,
                    "holdout_scenario": scenario,
                    "steps_per_case": steps_per_case,
                    "global_step_start": global_step - len(step_logs) + 1,
                    "global_step_end": global_step,
                }
            )
            case_summaries.append(case_summary)

    summary = summarize_logs(all_logs)
    summary.update(
        {
            "runner": "HoldoutEvaluator",
            "cases": case_index,
            "seeds": list(seeds),
            "scenarios": list(scenarios),
            "steps_per_case": steps_per_case,
            "total_steps": len(all_logs),
            "update_mode": {
                "red_update_enabled": False,
                "blue_update_enabled": False,
            },
            "case_summaries": case_summaries,
            "generalization_flags": _generalization_flags(summary=summary),
            "scripted_red_coverage": False,
            "holdout_diversity_penalty": {
                "enabled": True,
                "scope": "cross_case_previous_logs",
                "attack_window": ATTACK_DIVERSITY_WINDOW,
                "policy_updates_remain_frozen": True,
            },
        }
    )
    if log_path is not None:
        write_jsonl(log_path, all_logs)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return all_logs, summary


def _generalization_flags(summary: dict) -> list[str]:
    flags = []
    if summary.get("causal_failure_count", 0) > 0:
        flags.append("causal_failure_on_holdout")
    if summary.get("avg_causal_consistency", 1.0) < 0.72:
        flags.append("low_causal_consistency_on_holdout")
    if summary.get("attack_entropy", 0.0) < 0.75 and summary.get("rounds", 0) >= 4:
        flags.append("low_attack_diversity_on_holdout")
    if summary.get("goal_success_rate", 0.0) < 0.40:
        flags.append("low_goal_success_on_holdout")
    return flags
