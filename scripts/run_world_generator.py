"""CLI for the rule-based DAH raw world generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dah_flawless.world.generator import RuleBasedWorldGenerator, ScenarioCondition  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate DAH raw world samples.")
    parser.add_argument("--seed", type=int, default=20260704)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--mission-phase", default="RECON_APPROACH")
    parser.add_argument("--terrain", default="MOUNTAIN")
    parser.add_argument("--weather", default="LOW_VISIBILITY")
    parser.add_argument("--enemy-presence", default="LIKELY", choices=["NONE", "POSSIBLE", "LIKELY", "CONFIRMED"])
    parser.add_argument("--link-context", default="BLOS", choices=["LOS", "BLOS", "SATCOM_ONLY", "MESH"])
    parser.add_argument("--area-id", default="AO-NORTH-RIDGE")
    parser.add_argument("--out", default="tmp/world/raw_world_samples.jsonl")
    parser.add_argument("--pretty", action="store_true", help="Print first sample as pretty JSON.")
    return parser.parse_args(argv)


def resolve_project_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    condition = ScenarioCondition(
        mission_phase=args.mission_phase,
        terrain=args.terrain,
        weather=args.weather,
        enemy_presence=args.enemy_presence,
        link_context=args.link_context,
        area_id=args.area_id,
    )
    generator = RuleBasedWorldGenerator(seed=args.seed)

    out_path = resolve_project_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    samples = [generator.generate(condition, sample_index=i) for i in range(args.count)]
    with out_path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"wrote {len(samples)} sample(s) to {out_path}")
    print(f"first_raw_world_hash={samples[0]['raw_world_hash']}")
    if args.pretty:
        print(json.dumps(samples[0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
