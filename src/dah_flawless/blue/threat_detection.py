"""Threat Detection Agent."""

from __future__ import annotations

from dah_flawless.blue.invariants import analyze_invariants
from dah_flawless.blue.tagger import derive_tags
from dah_flawless.schemas import Threat, decision


def detect_threats(
    redacted_state: dict, history: dict, capabilities: dict | None = None
) -> tuple[list[str], list[Threat], dict]:
    tags = derive_tags(redacted_state, history, capabilities)
    threats = analyze_invariants(redacted_state, history, tags, capabilities)
    log = decision(
        "ThreatDetectionAgent",
        "invariants_checked",
        "observed_only_tags",
        before=tags,
        after=[threat.to_dict() for threat in threats],
    )
    return tags, threats, log
