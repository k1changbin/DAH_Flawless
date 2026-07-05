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
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.environment.training_scheduler import run_training_schedule
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
    parser.add_argument(
        "--raw-world-sample",
        type=Path,
        help="Optional raw-world JSON or JSONL sample used to initialize the simulation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initial_state = None
    if args.raw_world_sample:
        sample = _read_raw_world_sample(args.raw_world_sample)
        initial_state = build_state_from_raw_world(sample, seed=args.seed)
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
        )
        print(f"wrote {len(logs)} rounds to {args.out}")
    print(f"wrote summary to {args.summary}")
    print(summary)


def _read_raw_world_sample(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"empty raw-world sample file: {path}")
    first_line = next(line for line in text.splitlines() if line.strip())
    return json.loads(first_line)


if __name__ == "__main__":
    main()
