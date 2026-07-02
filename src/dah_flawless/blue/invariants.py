"""Attack-name-independent invariant checks."""

from __future__ import annotations

from dah_flawless.schemas import Threat


def analyze_invariants(redacted_state: dict, history: dict, tags: list[str]) -> list[Threat]:
    threats: list[Threat] = []
    tag_set = set(tags)

    if {"TELEMETRY_CONFLICT", "BATTERY_MOTOR_INCONSISTENT"}.intersection(tag_set):
        threats.append(
            Threat(
                target="telemetry",
                confidence=0.84,
                tags=tuple(sorted(tag_set.intersection({"TELEMETRY_CONFLICT", "BATTERY_MOTOR_INCONSISTENT"}))),
                evidence=(
                    "battery_percent changed sharply while drain_rate remained positive",
                    "motor_status and battery trend imply inconsistent flight condition",
                ),
            )
        )

    if "MISSION_PRIORITY_CHANGED" in tag_set:
        threats.append(
            Threat(
                target="mission",
                confidence=0.78,
                tags=("MISSION_PRIORITY_CHANGED",),
                evidence=(
                    "area priority changed beyond allowed delta",
                    "no supporting mission event exists in observed state",
                ),
            )
        )

    if {"SEQUENCE_REGRESSION", "TIMESTAMP_SKEW", "REPLAY_SUSPECTED"}.intersection(tag_set):
        threats.append(
            Threat(
                target="command",
                confidence=0.88,
                tags=tuple(sorted(tag_set.intersection({"SEQUENCE_REGRESSION", "TIMESTAMP_SKEW", "REPLAY_SUSPECTED"}))),
                evidence=(
                    "message sequence moved backward",
                    "received timestamp moved backward or exceeded skew bound",
                ),
            )
        )

    return threats
