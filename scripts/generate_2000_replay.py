from __future__ import annotations

import argparse
import json
from pathlib import Path

from dah_flawless.environment.round_combat_runner import run_combat_rounds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a local 2000-round combat replay for the frontend."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", default="clean_start")
    parser.add_argument("--rounds", type=int, default=2000)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--min-steps", type=int, default=4)
    parser.add_argument("--logs", type=Path, default=Path("data/logs/round_2000_logs.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("data/logs/round_2000_summary.json"))
    parser.add_argument(
        "--frontend",
        type=Path,
        default=Path("data/frontend/runs/seed42_clean_start_2000.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs, summary = run_combat_rounds(
        seed=args.seed,
        rounds=args.rounds,
        max_steps=args.max_steps,
        min_steps=args.min_steps,
        scenario=args.scenario,
        log_path=args.logs,
        summary_path=args.summary,
        frontend_log_path=args.frontend,
    )
    result = {
        "rounds": len(logs),
        "seed": args.seed,
        "scenario": args.scenario,
        "logs": str(args.logs),
        "summary": str(args.summary),
        "frontend": str(args.frontend),
        "winner_counts": summary.get("winner_counts") or summary.get("winners"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
