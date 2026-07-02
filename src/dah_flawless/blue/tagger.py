"""Observed-only situation tag derivation."""

from __future__ import annotations


def derive_tags(redacted_state: dict, history: dict) -> list[str]:
    obs = redacted_state["blue_observed"]
    tags: list[str] = []

    if obs["navigation"]["gnss_fix_quality"] == "NORMAL":
        tags.append("GNSS_PRIMARY")
    if obs["navigation"]["satellite_count"] < 5 or obs["navigation"]["hdop"] > 5.0:
        tags.append("GNSS_DEGRADED")
    if obs["comms"]["encrypted"]:
        tags.append("C2_ENCRYPTED")
    if not obs["comms"]["payload_visible"]:
        tags.append("PAYLOAD_HIDDEN")
    if obs["c2_message"]["signature_present"]:
        tags.append("SIGNATURE_PRESENT")
    if obs["c2_message"]["auth_valid"]:
        tags.append("AUTH_VALID")
    else:
        tags.append("AUTH_INVALID")
    if not obs["c2_message"]["checksum_valid"]:
        tags.append("CHECKSUM_INVALID")
    if obs["comms"]["latency_ms"] > 500:
        tags.append("HIGH_LATENCY")
    if obs["comms"]["packet_loss"] > 0.10:
        tags.append("PACKET_LOSS_HIGH")
    if obs["comms"]["message_queue_depth"] > 10:
        tags.append("QUEUE_DEPTH_HIGH")
    if obs["comms"]["request_rate"] > 10:
        tags.append("REQUEST_RATE_HIGH")

    if obs["c2_message"]["sequence_number"] < history["last_sequence_number"]:
        tags.append("SEQUENCE_REGRESSION")
        tags.append("REPLAY_SUSPECTED")
    if obs["time"]["received_timestamp"] < history["last_received_timestamp"]:
        tags.append("TIMESTAMP_SKEW")
        if "REPLAY_SUSPECTED" not in tags:
            tags.append("REPLAY_SUSPECTED")

    telemetry = obs["telemetry"]
    last_telemetry = history["last_telemetry"]
    if telemetry["battery_percent"] - last_telemetry["battery_percent"] > 25 and telemetry["battery_drain_rate"] > 0:
        tags.append("TELEMETRY_CONFLICT")
    if telemetry["battery_percent"] > 70 and telemetry["motor_status"] == "OK" and telemetry["battery_drain_rate"] >= 0.8:
        tags.append("BATTERY_MOTOR_INCONSISTENT")

    priority_delta = max(
        abs(obs["mission"]["area_priority"][area] - history["last_area_priority"][area])
        for area in obs["mission"]["area_priority"]
    )
    if priority_delta > 0.35:
        tags.append("MISSION_PRIORITY_CHANGED")

    return sorted(set(tags))
