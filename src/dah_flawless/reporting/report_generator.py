"""Training/Holdout report generation.

The report generator converts simulator summaries into a compact, report-ready
artifact. It does not re-score attacks and it does not inspect scorer truth; it
only summarizes metrics already emitted by the simulator/evaluators.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from dah_flawless.environment.hash_log import verify_hash_chain


def build_training_holdout_report(
    *,
    training_summary: dict,
    holdout_summary: dict | None = None,
    training_logs: list[dict] | None = None,
    holdout_logs: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a structured report from training and optional holdout outputs."""

    training = _run_section(training_summary, logs=training_logs, label="training")
    holdout = _run_section(holdout_summary, logs=holdout_logs, label="holdout") if holdout_summary else None
    report = {
        "report_type": "training_holdout_report",
        "generated_from": {
            "training_runner": training_summary.get("runner", "unknown"),
            "holdout_runner": (holdout_summary or {}).get("runner") if holdout_summary else None,
        },
        "training": training,
        "holdout": holdout,
        "comparison": _comparison(training, holdout),
        "takeaways": _takeaways(training, holdout),
    }
    return report


def write_training_holdout_report(
    *,
    training_summary: dict,
    holdout_summary: dict | None = None,
    training_logs: list[dict] | None = None,
    holdout_logs: list[dict] | None = None,
    markdown_path: Path,
    json_path: Path | None = None,
) -> dict[str, Any]:
    report = build_training_holdout_report(
        training_summary=training_summary,
        holdout_summary=holdout_summary,
        training_logs=training_logs,
        holdout_logs=holdout_logs,
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    training = report["training"]
    holdout = report.get("holdout")
    lines = [
        "# DAH Flawless Training/Holdout Report",
        "",
        "## Executive Summary",
        "",
    ]
    for item in report.get("takeaways", []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Training Overview",
            "",
            _metric_table(training["overview"]),
            "",
            "## Training Metrics",
            "",
            _metric_table(training["metrics"]),
            "",
            "## Training Blocks",
            "",
            _rows_table(
                training["block_rows"],
                (
                    "block",
                    "episodes",
                    "steps",
                    "winner_top",
                    "goal_success_rate",
                    "avg_mission_impact_score",
                    "avg_causal_consistency",
                ),
            ),
            "",
            "## Policy Delta",
            "",
            "### Red Attack Weights",
            "",
            _rows_table(training["policy_delta"]["red_attack_weights"], ("attack", "start", "end", "delta")),
            "",
            "### Blue Domain Policy",
            "",
            _rows_table(
                training["policy_delta"]["blue_domain_policy"],
                ("domain", "trust_start", "trust_end", "sensitivity_start", "sensitivity_end", "threshold_start", "threshold_end"),
            ),
        ]
    )

    if holdout:
        lines.extend(
            [
                "",
                "## Holdout Overview",
                "",
                _metric_table(holdout["overview"]),
                "",
                "## Holdout Metrics",
                "",
                _metric_table(holdout["metrics"]),
                "",
                "## Holdout Scenario Results",
                "",
                _rows_table(
                    holdout["scenario_rows"],
                    (
                        "scenario",
                        "seed",
                        "steps",
                        "winner_top",
                        "goal_success_rate",
                        "avg_mission_impact_score",
                        "avg_causal_consistency",
                        "min_availability",
                    ),
                ),
                "",
                "## Generalization Flags",
                "",
            ]
        )
        flags = holdout["quality_flags"] or ["none"]
        lines.extend(f"- {flag}" for flag in flags)

    lines.extend(
        [
            "",
            "## Comparison",
            "",
            _metric_table(report["comparison"]),
            "",
        ]
    )
    return "\n".join(lines)


def load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _run_section(summary: dict, *, logs: list[dict] | None, label: str) -> dict[str, Any]:
    return {
        "overview": _overview(summary, logs=logs, label=label),
        "metrics": _metrics(summary),
        "block_rows": _block_rows(summary),
        "scenario_rows": _scenario_rows(summary),
        "policy_delta": _policy_delta(summary),
        "quality_flags": _quality_flags(summary, logs=logs, label=label),
    }


def _overview(summary: dict, *, logs: list[dict] | None, label: str) -> dict[str, Any]:
    overview = {
        "label": label,
        "runner": summary.get("runner", "unknown"),
        "rounds": summary.get("rounds", 0),
        "episodes": summary.get("episodes"),
        "steps_per_episode": summary.get("steps_per_episode"),
        "total_steps": summary.get("total_steps", summary.get("rounds", 0)),
        "scenario": summary.get("scenario"),
        "cases": summary.get("cases"),
        "scenario_count": len(summary.get("scenarios", [])),
        "scripted_red_coverage": summary.get("scripted_red_coverage"),
    }
    if logs is not None:
        overview["log_entries"] = len(logs)
        overview["hash_chain_ok"] = verify_hash_chain(logs)
    return {key: value for key, value in overview.items() if value is not None}


def _metrics(summary: dict) -> dict[str, Any]:
    keys = (
        "detection_rate",
        "attack_success_rate",
        "goal_success_rate",
        "avg_goal_reward",
        "avg_mission_impact_score",
        "high_mission_impact_count",
        "attack_entropy",
        "tactic_entropy",
        "avg_causal_consistency",
        "causal_warning_count",
        "causal_failure_count",
        "final_availability",
        "min_availability",
    )
    metrics = {key: summary.get(key) for key in keys if key in summary}
    metrics["winner_top"] = _top_item(summary.get("winners", {}))
    metrics["attack_top"] = _top_item(summary.get("attacks", {}))
    metrics["goal_top"] = _top_item(summary.get("goals", {}))
    return metrics


def _block_rows(summary: dict) -> list[dict[str, Any]]:
    rows = []
    for block in summary.get("block_summaries", []):
        rows.append(
            {
                "block": block.get("block"),
                "episodes": block.get("episodes"),
                "steps": block.get("rounds"),
                "winner_top": _top_item(block.get("winners", {})),
                "goal_success_rate": block.get("goal_success_rate"),
                "avg_mission_impact_score": block.get("avg_mission_impact_score"),
                "avg_causal_consistency": block.get("avg_causal_consistency"),
                "attack_entropy": block.get("attack_entropy"),
                "tactic_entropy": block.get("tactic_entropy"),
            }
        )
    return rows


def _scenario_rows(summary: dict) -> list[dict[str, Any]]:
    rows = []
    for case in summary.get("case_summaries", []):
        rows.append(
            {
                "scenario": case.get("holdout_scenario") or case.get("scenario"),
                "seed": case.get("holdout_seed") or case.get("episode_seed"),
                "steps": case.get("rounds"),
                "winner_top": _top_item(case.get("winners", {})),
                "attack_top": _top_item(case.get("attacks", {})),
                "goal_top": _top_item(case.get("goals", {})),
                "goal_success_rate": case.get("goal_success_rate"),
                "avg_mission_impact_score": case.get("avg_mission_impact_score"),
                "avg_causal_consistency": case.get("avg_causal_consistency"),
                "min_availability": case.get("min_availability"),
                "scenario_emphasis": ",".join(case.get("scenario_profile", {}).get("emphasis", [])),
            }
        )
    return rows


def _policy_delta(summary: dict) -> dict[str, list[dict[str, Any]]]:
    start_red, start_blue = _initial_policy_states(summary)
    end_red = summary.get("final_red_policy_state") or summary.get("red_policy_state") or {}
    end_blue = summary.get("final_blue_policy_state") or summary.get("blue_policy_state") or {}
    return {
        "red_attack_weights": _red_weight_rows(start_red, end_red),
        "blue_domain_policy": _blue_domain_rows(start_blue, end_blue),
    }


def _initial_policy_states(summary: dict) -> tuple[dict, dict]:
    blocks = summary.get("block_summaries", [])
    if blocks:
        return (
            deepcopy(blocks[0].get("red_policy_start", {})),
            deepcopy(blocks[0].get("blue_policy_start", {})),
        )
    return (
        deepcopy(summary.get("red_policy_state", {})),
        deepcopy(summary.get("blue_policy_state", {})),
    )


def _red_weight_rows(start_red: dict, end_red: dict) -> list[dict[str, Any]]:
    start_weights = start_red.get("weights", {})
    end_weights = end_red.get("weights", {})
    attacks = sorted(set(start_weights).union(end_weights))
    return [
        {
            "attack": attack,
            "start": _round(start_weights.get(attack)),
            "end": _round(end_weights.get(attack)),
            "delta": _round(_delta(start_weights.get(attack), end_weights.get(attack))),
        }
        for attack in attacks
    ]


def _blue_domain_rows(start_blue: dict, end_blue: dict) -> list[dict[str, Any]]:
    domains = sorted(
        set(start_blue.get("domain_trust", {}))
        .union(end_blue.get("domain_trust", {}))
        .union(start_blue.get("detection_sensitivity", {}))
        .union(end_blue.get("detection_sensitivity", {}))
    )
    rows = []
    for domain in domains:
        rows.append(
            {
                "domain": domain,
                "trust_start": _round(start_blue.get("domain_trust", {}).get(domain)),
                "trust_end": _round(end_blue.get("domain_trust", {}).get(domain)),
                "sensitivity_start": _round(start_blue.get("detection_sensitivity", {}).get(domain)),
                "sensitivity_end": _round(end_blue.get("detection_sensitivity", {}).get(domain)),
                "threshold_start": _round(start_blue.get("escalation_threshold", {}).get(domain)),
                "threshold_end": _round(end_blue.get("escalation_threshold", {}).get(domain)),
            }
        )
    return rows


def _comparison(training: dict, holdout: dict | None) -> dict[str, Any]:
    if holdout is None:
        return {"holdout_present": False}
    training_metrics = training["metrics"]
    holdout_metrics = holdout["metrics"]
    return {
        "holdout_present": True,
        "goal_success_delta": _round(
            _delta(training_metrics.get("goal_success_rate"), holdout_metrics.get("goal_success_rate"))
        ),
        "detection_rate_delta": _round(
            _delta(training_metrics.get("detection_rate"), holdout_metrics.get("detection_rate"))
        ),
        "causal_consistency_delta": _round(
            _delta(training_metrics.get("avg_causal_consistency"), holdout_metrics.get("avg_causal_consistency"))
        ),
        "mission_impact_delta": _round(
            _delta(
                training_metrics.get("avg_mission_impact_score"),
                holdout_metrics.get("avg_mission_impact_score"),
            )
        ),
        "attack_entropy_delta": _round(
            _delta(training_metrics.get("attack_entropy"), holdout_metrics.get("attack_entropy"))
        ),
        "tactic_entropy_delta": _round(
            _delta(training_metrics.get("tactic_entropy"), holdout_metrics.get("tactic_entropy"))
        ),
    }


def _quality_flags(summary: dict, *, logs: list[dict] | None, label: str) -> list[str]:
    flags = list(summary.get("generalization_flags", []) or [])
    if summary.get("causal_failure_count", 0) > 0:
        flags.append(f"{label}_causal_failure")
    if summary.get("avg_causal_consistency", 1.0) < 0.85:
        flags.append(f"{label}_low_causal_consistency")
    if summary.get("attack_entropy", 0.0) < 0.75 and summary.get("rounds", 0) >= 4:
        flags.append(f"{label}_low_attack_diversity")
    if summary.get("tactic_entropy", 0.0) < 0.75 and summary.get("rounds", 0) >= 4:
        flags.append(f"{label}_low_tactic_diversity")
    min_availability = summary.get("min_availability")
    if min_availability is not None and min_availability < 0.50:
        flags.append(f"{label}_availability_floor_pressure")
    if logs is not None and not verify_hash_chain(logs):
        flags.append(f"{label}_hash_chain_invalid")
    return sorted(set(flags))


def _takeaways(training: dict, holdout: dict | None) -> list[str]:
    items = []
    training_metrics = training["metrics"]
    items.append(
        "Training reached "
        f"goal_success_rate={_fmt(training_metrics.get('goal_success_rate'))}, "
        f"avg_mission_impact={_fmt(training_metrics.get('avg_mission_impact_score'))}, "
        f"avg_causal_consistency={_fmt(training_metrics.get('avg_causal_consistency'))}."
    )
    items.append(
        "Training diversity: "
        f"attack_entropy={_fmt(training_metrics.get('attack_entropy'))}, "
        f"tactic_entropy={_fmt(training_metrics.get('tactic_entropy'))}."
    )
    if holdout:
        holdout_metrics = holdout["metrics"]
        items.append(
            "Holdout reached "
            f"goal_success_rate={_fmt(holdout_metrics.get('goal_success_rate'))}, "
            f"avg_mission_impact={_fmt(holdout_metrics.get('avg_mission_impact_score'))}, "
            f"avg_causal_consistency={_fmt(holdout_metrics.get('avg_causal_consistency'))} "
            f"across {holdout['overview'].get('scenario_count', 0)} scenario types."
        )
        if holdout["quality_flags"]:
            items.append(f"Holdout flags: {', '.join(holdout['quality_flags'])}.")
        else:
            items.append("Holdout produced no generalization flags.")
    if training["quality_flags"]:
        items.append(f"Training flags: {', '.join(training['quality_flags'])}.")
    return items


def _metric_table(data: dict[str, Any]) -> str:
    rows = ["| Metric | Value |", "|---|---|"]
    for key, value in data.items():
        rows.append(f"| `{key}` | {_fmt(value)} |")
    return "\n".join(rows)


def _rows_table(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _top_item(counter: dict[str, int] | None) -> str:
    if not counter:
        return "none"
    key, value = max(counter.items(), key=lambda item: (item[1], item[0]))
    return f"{key}:{value}"


def _delta(start: Any, end: Any) -> float | None:
    if start is None or end is None:
        return None
    return float(end) - float(start)


def _round(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        rounded = round(float(value), 4)
        return 0.0 if abs(rounded) < 0.00005 else rounded
    return value


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if abs(value) < 0.00005:
            value = 0.0
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
