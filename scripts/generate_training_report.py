from __future__ import annotations

import argparse
from pathlib import Path

from dah_flawless.environment.hash_log import read_jsonl
from dah_flawless.reporting.report_generator import load_summary, write_training_holdout_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a DAH training/holdout markdown report")
    parser.add_argument("--training-summary", type=Path, required=True)
    parser.add_argument("--holdout-summary", type=Path)
    parser.add_argument("--training-logs", type=Path)
    parser.add_argument("--holdout-logs", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/reports/training_holdout_report.md"))
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = write_training_holdout_report(
        training_summary=load_summary(args.training_summary),
        holdout_summary=load_summary(args.holdout_summary) if args.holdout_summary else None,
        training_logs=read_jsonl(args.training_logs) if args.training_logs else None,
        holdout_logs=read_jsonl(args.holdout_logs) if args.holdout_logs else None,
        markdown_path=args.out,
        json_path=args.json_out,
    )
    print(f"wrote report to {args.out}")
    if args.json_out:
        print(f"wrote report json to {args.json_out}")
    print(report["comparison"])


if __name__ == "__main__":
    main()
