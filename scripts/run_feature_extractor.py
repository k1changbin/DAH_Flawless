"""CLI for extracting DAH Situation Tagger features from raw world JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dah_flawless.world.feature_extractor import RawWorldFeatureExtractor, summarize_features  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract DAH raw-world features.")
    parser.add_argument("--in", dest="input_path", default="tmp/world/raw_world_samples.jsonl")
    parser.add_argument("--out", dest="output_path", default="tmp/world/world_features.jsonl")
    parser.add_argument("--summary", action="store_true", help="Print one-line feature summaries.")
    parser.add_argument("--pretty-first", action="store_true", help="Print first feature row as pretty JSON.")
    return parser.parse_args(argv)


def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    input_path = resolve_project_path(args.input_path)
    output_path = resolve_project_path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    extractor = RawWorldFeatureExtractor()
    rows = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            sample = json.loads(line)
            rows.append(extractor.extract(sample))

    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"read {len(rows)} raw world sample(s) from {input_path}")
    print(f"wrote {len(rows)} feature row(s) to {output_path}")
    if args.summary:
        for row in rows:
            print(summarize_features(row))
    if args.pretty_first and rows:
        print(json.dumps(rows[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
