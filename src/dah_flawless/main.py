"""Command line entrypoint for the MVP simulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dah_flawless.config import (
    DEFAULT_BLUE_UPDATE_EPISODES,
    DEFAULT_EVAL_EPISODES,
    DEFAULT_RED_UPDATE_EPISODES,
    DEFAULT_ROUNDS,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_STEALTH_MODE,
    DEFAULT_STEPS_PER_EPISODE,
    MUTATION_PROFILES,
    SCENARIOS,
    STEALTH_MODES,
)
from dah_flawless.environment.episode_runner import run_episodes
from dah_flawless.environment.hash_log import reset_log_outputs
from dah_flawless.environment.holdout_evaluator import (
    DEFAULT_HOLDOUT_SCENARIOS,
    DEFAULT_HOLDOUT_SEEDS,
    DEFAULT_HOLDOUT_STEPS,
    run_holdout_evaluation,
)
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.training_scheduler import run_training_schedule
from dah_flawless.reporting.report_generator import write_training_holdout_report
from dah_flawless.world.state_adapter import build_state_from_raw_world


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DAH Flawless MVP simulation")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument(
        "--training-schedule",
        action="store_true",
        help="Run alternating Blue-update, Red-update, and fixed-eval episode blocks.",
    )
    parser.add_argument("--blue-update-episodes", type=int, default=DEFAULT_BLUE_UPDATE_EPISODES)
    parser.add_argument("--red-update-episodes", type=int, default=DEFAULT_RED_UPDATE_EPISODES)
    parser.add_argument("--eval-episodes", type=int, default=DEFAULT_EVAL_EPISODES)
    parser.add_argument(
        "--episodes",
        type=int,
        help=f"Run episode mode with this many independent episodes. Default step count is {DEFAULT_STEPS_PER_EPISODE}.",
    )
    parser.add_argument("--steps-per-episode", type=int, default=DEFAULT_STEPS_PER_EPISODE)
    parser.add_argument(
        "--holdout-eval",
        action="store_true",
        help="After the main run, evaluate frozen final Red/Blue policies on separate seed/scenario cases.",
    )
    parser.add_argument(
        "--holdout-seeds",
        default=",".join(str(seed) for seed in DEFAULT_HOLDOUT_SEEDS),
        help="Comma-separated seeds for frozen-policy holdout evaluation.",
    )
    parser.add_argument(
        "--holdout-scenarios",
        default=",".join(DEFAULT_HOLDOUT_SCENARIOS),
        help="Comma-separated scenarios for frozen-policy holdout evaluation.",
    )
    parser.add_argument("--holdout-steps", type=int, default=DEFAULT_HOLDOUT_STEPS)
    parser.add_argument("--scenario", choices=SCENARIOS, default=DEFAULT_SCENARIO)
    parser.add_argument(
        "--red-stealth",
        dest="red_stealth",
        choices=STEALTH_MODES,
        default=DEFAULT_STEALTH_MODE,
        help="off=use mutation profile, on=always stealth, adaptive=switch to stealth after detection",
    )
    parser.add_argument(
        "--mutation-profile",
        choices=MUTATION_PROFILES,
        default=DEFAULT_MUTATION_PROFILE,
        help="Mutation amplitude profile for non-stealth Red actions.",
    )
    parser.add_argument("--out", type=Path, default=Path("data/logs/round_logs.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("data/logs/summary.json"))
    parser.add_argument("--holdout-out", type=Path, default=Path("data/logs/holdout_logs.jsonl"))
    parser.add_argument("--holdout-summary", type=Path, default=Path("data/logs/holdout_summary.json"))
    parser.add_argument(
        "--report-out",
        type=Path,
        help="Optional markdown report path generated from the main run and optional holdout run.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional structured JSON companion for --report-out.",
    )
    parser.add_argument(
        "--reset-logs",
        action="store_true",
        help="Delete the selected --out and --summary files before running.",
    )
    parser.add_argument(
        "--memory-compaction-interval",
        type=int,
        default=0,
        help="Compress Red planning context every N rounds. 0 disables rolling log memory.",
    )
    parser.add_argument(
        "--memory-proxy-size",
        type=int,
        default=12,
        help="Number of synthetic proxy logs retained after each memory compaction.",
    )
    parser.add_argument(
        "--memory-out",
        type=Path,
        help="Optional JSON file that stores rolling compressed memory snapshots.",
    )
    parser.add_argument(
        "--raw-world-sample",
        type=Path,
        help="Optional raw-world JSON or JSONL sample used to initialize the simulation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.memory_compaction_interval and (args.training_schedule or args.episodes is not None):
        raise ValueError("rolling log memory is currently supported for round mode; use --rounds without episode mode")
    if args.reset_logs:
        reset_targets = [args.out, args.summary]
        if args.holdout_eval:
            reset_targets.extend([args.holdout_out, args.holdout_summary])
        if args.report_out:
            reset_targets.append(args.report_out)
        if args.report_json:
            reset_targets.append(args.report_json)
        if args.memory_out:
            reset_targets.append(args.memory_out)
        removed = reset_log_outputs(reset_targets)
        removed_text = ", ".join(str(path) for path in removed) if removed else "none"
        print(f"reset log outputs: {removed_text}")

    initial_state = None
    if args.raw_world_sample:
        sample = _read_raw_world_sample(args.raw_world_sample)
        initial_state = build_state_from_raw_world(sample, seed=args.seed)
    holdout_logs = None
    holdout_summary = None
    if args.training_schedule:
        logs, summary = run_training_schedule(
            seed=args.seed,
            blue_update_episodes=args.blue_update_episodes,
            red_update_episodes=args.red_update_episodes,
            eval_episodes=args.eval_episodes,
            steps_per_episode=args.steps_per_episode,
            log_path=args.out,
            summary_path=args.summary,
            scenario=args.scenario,
            stealth_mode=args.red_stealth,
            mutation_profile=args.mutation_profile,
            initial_state=initial_state,
        )
        print(f"wrote training schedule with {summary['episodes']} episodes / {len(logs)} steps to {args.out}")
    elif args.episodes is not None:
        logs, summary = run_episodes(
            seed=args.seed,
            episodes=args.episodes,
            steps_per_episode=args.steps_per_episode,
            log_path=args.out,
            summary_path=args.summary,
            scenario=args.scenario,
            stealth_mode=args.red_stealth,
            mutation_profile=args.mutation_profile,
            initial_state=initial_state,
        )
        print(f"wrote {summary['episodes']} episodes / {len(logs)} steps to {args.out}")
    else:
        logs, summary = run_simulation(
            seed=args.seed,
            rounds=args.rounds,
            log_path=args.out,
            summary_path=args.summary,
            scenario=args.scenario,
            stealth_mode=args.red_stealth,
            mutation_profile=args.mutation_profile,
            initial_state=initial_state,
            memory_compaction_interval=args.memory_compaction_interval,
            memory_proxy_size=args.memory_proxy_size,
            memory_path=args.memory_out,
        )
        print(f"wrote {len(logs)} rounds to {args.out}")
    if args.holdout_eval:
        holdout_seeds = _parse_int_list(args.holdout_seeds, name="--holdout-seeds")
        holdout_scenarios = _parse_str_list(args.holdout_scenarios, name="--holdout-scenarios")
        holdout_logs, holdout_summary = run_holdout_evaluation(
            red_policy_state=summary.get("final_red_policy_state") or summary.get("red_policy_state"),
            blue_policy_state=summary.get("final_blue_policy_state") or summary.get("blue_policy_state"),
            seeds=holdout_seeds,
            scenarios=holdout_scenarios,
            steps_per_case=args.holdout_steps,
            log_path=args.holdout_out,
            summary_path=args.holdout_summary,
            stealth_mode=args.red_stealth,
            mutation_profile=args.mutation_profile,
        )
        print(
            "wrote frozen-policy holdout with "
            f"{holdout_summary['cases']} cases / {len(holdout_logs)} steps to {args.holdout_out}"
        )
        print(f"wrote holdout summary to {args.holdout_summary}")
        print(holdout_summary)
    if args.report_out:
        report = write_training_holdout_report(
            training_summary=summary,
            holdout_summary=holdout_summary,
            training_logs=logs,
            holdout_logs=holdout_logs,
            markdown_path=args.report_out,
            json_path=args.report_json,
        )
        print(f"wrote report to {args.report_out}")
        if args.report_json:
            print(f"wrote report json to {args.report_json}")
        print(report["comparison"])
    print(f"wrote summary to {args.summary}")
    print(summary)


def _parse_int_list(text: str, *, name: str) -> list[int]:
    values = [item.strip() for item in text.split(",") if item.strip()]
    if not values:
        raise ValueError(f"{name} must contain at least one integer")
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise ValueError(f"{name} must be a comma-separated integer list") from exc


def _parse_str_list(text: str, *, name: str) -> list[str]:
    values = [item.strip() for item in text.split(",") if item.strip()]
    if not values:
        raise ValueError(f"{name} must contain at least one value")
    unknown = sorted(set(values).difference(SCENARIOS))
    if unknown:
        raise ValueError(f"{name} contains unknown scenario(s): {', '.join(unknown)}")
    return values


def _read_raw_world_sample(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"empty raw-world sample file: {path}")
    first_line = next(line for line in text.splitlines() if line.strip())
    return json.loads(first_line)


if __name__ == "__main__":
    main()
