"""Threat Detection Agent."""

from __future__ import annotations

from dah_flawless.blue.goal_consistency import infer_goal_effect_threats, merge_goal_effect_threats
from dah_flawless.blue.invariants import analyze_invariants
from dah_flawless.blue.tagger import derive_tags
from dah_flawless.blue.telemetry_channel_checks import analyze_telemetry_channel_checks
from dah_flawless.schemas import Threat, decision


def detect_threats(
    redacted_state: dict, history: dict, capabilities: dict | None = None
) -> tuple[list[str], list[Threat], dict]:
    base_tags = derive_tags(redacted_state, history, capabilities)
    telemetry_channel_checks = analyze_telemetry_channel_checks(redacted_state)
    tags = list(dict.fromkeys([*base_tags, *telemetry_channel_checks["tags"]]))
    invariant_threats = analyze_invariants(redacted_state, history, tags, capabilities)
    effect_threats, effect_hypotheses = infer_goal_effect_threats(redacted_state, history, tags, capabilities)
    threats = merge_goal_effect_threats(invariant_threats, effect_threats)
    log = decision(
        "ThreatDetectionAgent",
        "invariants_checked",
        "observed_only_tags_and_goal_effect_consistency",
        before=tags,
        after={
            "threats": [threat.to_dict() for threat in threats],
            "effect_hypotheses": effect_hypotheses,
            "telemetry_channel_checks": telemetry_channel_checks,
        },
    )
    return tags, threats, log
