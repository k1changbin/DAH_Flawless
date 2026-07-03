"""Command line entrypoint for the MVP simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

from dah_flawless.config import (
    DEFAULT_ROUNDS,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_STEALTH_MODE,
    SCENARIOS,
    STEALTH_MODES,
)
from dah_flawless.environment.simulator import run_simulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DAH Flawless MVP simulation")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--scenario", choices=SCENARIOS, default=DEFAULT_SCENARIO)
    parser.add_argument(
        "--red-stealth",
        dest="red_stealth",
        choices=STEALTH_MODES,
        default=DEFAULT_STEALTH_MODE,
        help="off=always loud, on=always stealth, adaptive=switch to stealth after detection",
    )
    parser.add_argument("--out", type=Path, default=Path("data/logs/round_logs.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("data/logs/summary.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs, summary = run_simulation(
        seed=args.seed,
        rounds=args.rounds,
        log_path=args.out,
        summary_path=args.summary,
        scenario=args.scenario,
        stealth_mode=args.red_stealth,
    )
    print(f"wrote {len(logs)} rounds to {args.out}")
    print(f"wrote summary to {args.summary}")
    print(summary)


if __name__ == "__main__":
    main()
