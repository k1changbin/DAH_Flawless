from __future__ import annotations

import argparse
import json
from pathlib import Path

from dah_flawless.environment.hash_log import read_jsonl
from dah_flawless.reporting.frontend_log import write_frontend_combat_log
from dah_flawless.reporting.report_generator import load_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a frontend-friendly DAH combat replay log")
    parser.add_argument("--logs", type=Path, required=True, help="Training JSONL log produced by RoundCombatRunner")
    parser.add_argument("--summary", type=Path, help="Optional summary JSON for aggregate metrics and policy snapshot")
    parser.add_argument("--out", type=Path, default=Path("data/frontend/combat_replay.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = load_summary(args.summary) if args.summary else None
    frontend_log = write_frontend_combat_log(args.out, read_jsonl(args.logs), summary)
    print(f"wrote frontend combat log to {args.out}")
    print(json.dumps(frontend_log["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
