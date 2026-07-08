"""Attack-name-independent invariant checks.

Blue never sees ``world``; it fires threats from contradictions inside
``blue_observed``. Degraded capabilities (paralysis model) lower the
confidence of the affected check, so the same violation becomes harder to
confirm - this is what makes ``degraded_start`` a real recovery challenge.
"""

from __future__ import annotations

from dah_flawless.config import CAPABILITY_FACTORS
from dah_flawless.schemas import Threat


def _capability_factor(capabilities: dict, name: str) -> float:
    return CAPABILITY_FACTORS.get(capabilities.get(name, "OK"), 1.0)


def analyze_invariants(
    redacted_state: dict,
    history: dict,
    tags: list[str],
    capabilities: dict | None = None,
) -> list[Threat]:
    capabilities = capabilities or {}
    threats: list[Threat] = []
    tag_set = set(tags)

    telemetry_tags = {
        "TELEMETRY_CONFLICT",
        "TELEMETRY_ANCHOR_RESIDUAL",
        "TELEMETRY_SAFETY_ANCHOR_RESIDUAL",
        "TELEMETRY_SERIAL_DRIFT",
        "BATTERY_MOTOR_INCONSISTENT",
        "BATTERY_ENERGY_IMPOSSIBLE",
        "GNSS_INTERNAL_CONFLICT",
        "IMU_TELEMETRY_DIVERGENCE",
    }.intersection(tag_set)
    if telemetry_tags:
        base_confidence = 0.78 if "TELEMETRY_SAFETY_ANCHOR_RESIDUAL" in telemetry_tags else 0.70
        confidence = _confidence(base_confidence, telemetry_tags, capabilities, "cross_check_telemetry")
        threats.append(
            Threat(
                target="telemetry",
                confidence=confidence,
                tags=tuple(sorted(telemetry_tags)),
                evidence=(
                    "battery, drain rate, motor state, GNSS, and IMU signals are not mutually consistent",
                    "observed-only cross-checks indicate telemetry manipulation or sensor paralysis",
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

    command_tags = {
        "SEQUENCE_REGRESSION",
        "SEQUENCE_GAP",
        "TIMESTAMP_SKEW",
        "REPLAY_SUSPECTED",
        "COMMAND_TIMING_INCONSISTENT",
        "PACKET_INTERVAL_ANOMALY",
        "HEARTBEAT_GAP",
        "ACK_TIMING_ANOMALY",
    }.intersection(tag_set)
    if command_tags:
        confidence = _confidence(0.78, command_tags, capabilities, "time_validation")
        threats.append(
            Threat(
                target="command",
                confidence=confidence,
                tags=tuple(sorted(command_tags)),
                evidence=(
                    "message sequence, timestamp, heartbeat, and ack timing are not mutually consistent",
                    "observed channel shape is consistent with replay, delay, drop, or desynchronization",
                ),
            )
        )

    return threats


def _confidence(base: float, evidence_tags: set[str], capabilities: dict, capability_name: str) -> float:
    evidence_bonus = min(0.16, 0.04 * (len(evidence_tags) - 1))
    return round((base + evidence_bonus) * _capability_factor(capabilities, capability_name), 3)
