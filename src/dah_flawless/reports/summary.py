"""Helpers for loading simulation outputs."""

from __future__ import annotations

from pathlib import Path

from dah_flawless.environment.hash_log import read_jsonl
from dah_flawless.scoring.metrics import summarize_logs


def summarize_jsonl(path: Path) -> dict:
    return summarize_logs(read_jsonl(path))
