"""Canonical JSONL logging with a hash chain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

GENESIS_HASH = "0" * 64


def canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_entry(prev_hash: str, entry_without_hash: dict) -> str:
    payload = f"{prev_hash}|{canonical_json(entry_without_hash)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def attach_hash(prev_hash: str, entry: dict) -> dict:
    body = dict(entry)
    body["prev_hash"] = prev_hash
    body["this_hash"] = hash_entry(prev_hash, body)
    return body


def write_jsonl(path: Path, entries: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def reset_log_outputs(paths: Iterable[Path]) -> list[Path]:
    """Delete selected log output files before a run.

    This intentionally handles only explicit file paths. It never removes a
    directory tree, so a reset cannot wipe unrelated local artifacts.
    """

    removed: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        normalized = path.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        if not path.exists():
            continue
        if path.is_dir():
            raise IsADirectoryError(f"log reset target is a directory: {path}")
        path.unlink()
        removed.append(path)
    return removed


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def verify_hash_chain(entries: list[dict]) -> bool:
    prev_hash = GENESIS_HASH
    for entry in entries:
        observed_hash = entry.get("this_hash")
        if entry.get("prev_hash") != prev_hash:
            return False
        body = dict(entry)
        body.pop("this_hash", None)
        if hash_entry(prev_hash, body) != observed_hash:
            return False
        prev_hash = observed_hash
    return True
