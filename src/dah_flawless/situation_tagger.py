"""Shared observed-only Situation Tagger for Red and Blue agents."""

from __future__ import annotations

from math import cos, radians, sqrt

from dah_flawless.config import (
    GNSS_IMU_DRIFT_TOLERANCE_M,
    ROUND_SECONDS,
    TELEMETRY_BATTERY_TOLERANCE,
)
from dah_flawless.schemas import SituationTag


TAG_MEANINGS: dict[str, str] = {
    "CROSS_CHECK_UNAVAILABLE": "telemetry cross-check capability is degraded or unavailable",
    "GNSS_PRIMARY": "GNSS appears usable as a primary navigation reference",
    "GNSS_DEGRADED": "GNSS quality is weak enough to lower navigation trust",
    "GNSS_INTERNAL_CONFLICT": "GNSS fix status conflicts with signal quality or geometry",
    "C2_ENCRYPTED": "C2 payload cannot be directly inspected",
    "PAYLOAD_HIDDEN": "payload content is hidden, so metadata and timing become more important",
    "SEQUENCE_VISIBLE": "message order information can be observed",
    "TIMESTAMP_VISIBLE": "message time information can be observed",
    "REGULAR_PACKET_INTERVAL": "packet timing is regular enough that delay or drop can stand out",
    "ACK_CHANNEL_VISIBLE": "command acknowledgement flow can be observed",
    "PACKET_SIZE_PATTERN": "packet size is stable enough to infer message role patterns",
    "METADATA_PLAINTEXT": "metadata outside the encrypted payload is observable",
    "STATE_UPDATE_DEPENDENT": "agent judgement depends heavily on fresh state updates",
    "REPLAY_WINDOW_OPEN": "anti-replay timing window leaves room for stale-message attempts",
    "CRYPTO_WEAKNESS_HINT": "observed crypto metadata hints at weak configuration",
    "PACKET_INTERVAL_ANOMALY": "packet timing deviates from the normal interval",
    "HEARTBEAT_GAP": "heartbeat gap is longer than the expected channel rhythm",
    "ACK_TIMING_ANOMALY": "acknowledgement timing or sequence does not match the command flow",
    "SEQUENCE_GAP": "message sequence advanced with a suspicious gap",
    "SIGNATURE_PRESENT": "message signature metadata is present",
    "AUTH_VALID": "message authentication is currently valid",
    "AUTH_INVALID": "message authentication failed",
    "CHECKSUM_INVALID": "message checksum failed",
    "HIGH_LATENCY": "channel latency is high",
    "PACKET_LOSS_HIGH": "packet loss is high",
    "QUEUE_DEPTH_HIGH": "message queue is congested",
    "REQUEST_RATE_HIGH": "request rate is unusually high",
    "SEQUENCE_REGRESSION": "message sequence moved backward",
    "REPLAY_SUSPECTED": "sequence or timestamp pattern is consistent with stale-message reuse",
    "TIMESTAMP_SKEW": "received timestamp moved backward",
    "COMMAND_TIMING_INCONSISTENT": "message sequence and timestamp progression disagree",
    "TELEMETRY_CONFLICT": "telemetry fields changed in a physically inconsistent way",
    "TELEMETRY_ANCHOR_RESIDUAL": "external telemetry has a residual gap against internal trusted telemetry",
    "TELEMETRY_SAFETY_ANCHOR_RESIDUAL": "external telemetry makes a low-battery or fault state look safer than the internal anchor",
    "TELEMETRY_SERIAL_DRIFT": "telemetry residual is drifting in the same direction over consecutive observations",
    "BATTERY_MOTOR_INCONSISTENT": "battery, drain rate, and motor state do not agree",
    "BATTERY_ENERGY_IMPOSSIBLE": "battery value exceeds the physically plausible energy envelope",
    "IMU_TELEMETRY_DIVERGENCE": "IMU position motion exceeds speed and time constraints",
    "MISSION_PRIORITY_CHANGED": "mission priority changed sharply without supporting context",
}


def derive_tags(redacted_state: dict, history: dict, capabilities: dict | None = None) -> list[str]:
    return [detail.tag for detail in derive_tag_details(redacted_state, history, capabilities)]


def derive_tag_details(
    redacted_state: dict,
    history: dict,
    capabilities: dict | None = None,
) -> list[SituationTag]:
    obs = redacted_state["blue_observed"]
    capabilities = capabilities if capabilities is not None else redacted_state.get("capabilities", {})
    details: list[SituationTag] = []

    if capabilities.get("cross_check_telemetry") in {"DEGRADED", "UNAVAILABLE"}:
        details.append(
            _tag(
                "CROSS_CHECK_UNAVAILABLE",
                0.86,
                (f"capabilities.cross_check_telemetry={capabilities.get('cross_check_telemetry')}",),
            )
        )
    if obs["navigation"]["gnss_fix_quality"] == "NORMAL":
        details.append(_tag("GNSS_PRIMARY", 0.78, ("navigation.gnss_fix_quality=NORMAL",)))
    if obs["navigation"]["satellite_count"] < 5 or obs["navigation"]["hdop"] > 5.0:
        details.append(
            _tag(
                "GNSS_DEGRADED",
                0.88,
                (
                    f"navigation.satellite_count={obs['navigation']['satellite_count']}",
                    f"navigation.hdop={obs['navigation']['hdop']}",
                ),
            )
        )
    if _gnss_internal_conflict(obs["navigation"]):
        details.append(
            _tag(
                "GNSS_INTERNAL_CONFLICT",
                0.91,
                (
                    f"navigation.gnss_fix_quality={obs['navigation']['gnss_fix_quality']}",
                    f"navigation.cn0_avg={obs['navigation'].get('cn0_avg')}",
                    f"navigation.satellite_count={obs['navigation']['satellite_count']}",
                    f"navigation.hdop={obs['navigation']['hdop']}",
                ),
            )
        )
    if obs["comms"]["encrypted"]:
        details.append(_tag("C2_ENCRYPTED", 0.98, ("comms.encrypted=True",)))
    if not obs["comms"]["payload_visible"]:
        details.append(_tag("PAYLOAD_HIDDEN", 0.96, ("comms.payload_visible=False",)))

    details.extend(_derive_channel_shape_details(obs, history))

    if obs["c2_message"]["signature_present"]:
        details.append(_tag("SIGNATURE_PRESENT", 0.90, ("c2_message.signature_present=True",)))
    if obs["c2_message"]["auth_valid"]:
        details.append(_tag("AUTH_VALID", 0.92, ("c2_message.auth_valid=True",)))
    else:
        details.append(_tag("AUTH_INVALID", 0.96, ("c2_message.auth_valid=False",)))
    if not obs["c2_message"]["checksum_valid"]:
        details.append(_tag("CHECKSUM_INVALID", 0.95, ("c2_message.checksum_valid=False",)))
    if obs["comms"]["latency_ms"] > 500:
        details.append(_tag("HIGH_LATENCY", 0.90, (f"comms.latency_ms={obs['comms']['latency_ms']}",)))
    if obs["comms"]["packet_loss"] > 0.10:
        details.append(_tag("PACKET_LOSS_HIGH", 0.90, (f"comms.packet_loss={obs['comms']['packet_loss']}",)))
    if obs["comms"]["message_queue_depth"] > 10:
        details.append(
            _tag("QUEUE_DEPTH_HIGH", 0.85, (f"comms.message_queue_depth={obs['comms']['message_queue_depth']}",))
        )
    if obs["comms"]["request_rate"] > 10:
        details.append(_tag("REQUEST_RATE_HIGH", 0.84, (f"comms.request_rate={obs['comms']['request_rate']}",)))

    if obs["c2_message"]["sequence_number"] < history["last_sequence_number"]:
        evidence = (
            f"c2_message.sequence_number={obs['c2_message']['sequence_number']}",
            f"history.last_sequence_number={history['last_sequence_number']}",
        )
        details.append(_tag("SEQUENCE_REGRESSION", 0.96, evidence))
        details.append(_tag("REPLAY_SUSPECTED", 0.91, evidence))
    if obs["time"]["received_timestamp"] < history["last_received_timestamp"]:
        evidence = (
            f"time.received_timestamp={obs['time']['received_timestamp']}",
            f"history.last_received_timestamp={history['last_received_timestamp']}",
        )
        details.append(_tag("TIMESTAMP_SKEW", 0.96, evidence))
        details.append(_tag("REPLAY_SUSPECTED", 0.89, evidence))
    if _command_time_inconsistent(obs, history):
        details.append(
            _tag(
                "COMMAND_TIMING_INCONSISTENT",
                0.87,
                (
                    f"c2_message.sequence_number={obs['c2_message']['sequence_number']}",
                    f"history.last_sequence_number={history['last_sequence_number']}",
                    f"time.received_timestamp={obs['time']['received_timestamp']}",
                    f"history.last_received_timestamp={history['last_received_timestamp']}",
                ),
            )
        )

    telemetry = obs["telemetry"]
    last_telemetry = history["last_telemetry"]
    internal_telemetry = obs.get("internal_observe", {}).get("telemetry", {})
    if internal_telemetry:
        details.extend(_derive_telemetry_anchor_details(telemetry, internal_telemetry, last_telemetry))
    if telemetry["battery_percent"] - last_telemetry["battery_percent"] > 25 and telemetry["battery_drain_rate"] > 0:
        details.append(
            _tag(
                "TELEMETRY_CONFLICT",
                0.88,
                (
                    f"telemetry.battery_percent={telemetry['battery_percent']}",
                    f"history.last_telemetry.battery_percent={last_telemetry['battery_percent']}",
                    f"telemetry.battery_drain_rate={telemetry['battery_drain_rate']}",
                ),
            )
        )
    if telemetry["battery_percent"] > 70 and telemetry["motor_status"] == "OK" and telemetry["battery_drain_rate"] >= 0.8:
        details.append(
            _tag(
                "BATTERY_MOTOR_INCONSISTENT",
                0.90,
                (
                    f"telemetry.battery_percent={telemetry['battery_percent']}",
                    f"telemetry.motor_status={telemetry['motor_status']}",
                    f"telemetry.battery_drain_rate={telemetry['battery_drain_rate']}",
                ),
            )
        )
    if _battery_energy_impossible(obs, history):
        details.append(
            _tag(
                "BATTERY_ENERGY_IMPOSSIBLE",
                0.92,
                (
                    f"telemetry.battery_percent={telemetry['battery_percent']}",
                    f"history.last_telemetry.battery_percent={last_telemetry['battery_percent']}",
                    f"telemetry.battery_drain_rate={telemetry['battery_drain_rate']}",
                ),
            )
        )
    if _imu_telemetry_divergence(obs, history):
        details.append(
            _tag(
                "IMU_TELEMETRY_DIVERGENCE",
                0.88,
                (
                    "navigation.imu_position_estimate",
                    "history.last_navigation.imu_position_estimate",
                    f"telemetry.speed_mps={telemetry['speed_mps']}",
                ),
            )
        )

    priority_delta = max(
        abs(obs["mission"]["area_priority"][area] - history["last_area_priority"][area])
        for area in obs["mission"]["area_priority"]
    )
    if priority_delta > 0.35:
        details.append(
            _tag(
                "MISSION_PRIORITY_CHANGED",
                0.89,
                (
                    f"mission.area_priority={obs['mission']['area_priority']}",
                    f"history.last_area_priority={history['last_area_priority']}",
                    f"priority_delta={round(priority_delta, 3)}",
                ),
            )
        )

    return _dedupe_details(details)


def _derive_channel_shape_details(obs: dict, history: dict) -> list[SituationTag]:
    details: list[SituationTag] = []
    comms = obs.get("comms", {})
    c2_message = obs.get("c2_message", {})
    time = obs.get("time", {})

    sequence_visible = c2_message.get("sequence_visible", "sequence_number" in c2_message)
    timestamp_visible = c2_message.get("timestamp_visible", "received_timestamp" in time)
    ack = c2_message.get("ack", {})

    if sequence_visible and "sequence_number" in c2_message:
        details.append(_tag("SEQUENCE_VISIBLE", 0.91, ("c2_message.sequence_visible=True", "c2_message.sequence_number")))
    if timestamp_visible and "received_timestamp" in time:
        details.append(_tag("TIMESTAMP_VISIBLE", 0.91, ("c2_message.timestamp_visible=True", "time.received_timestamp")))
    if _has_regular_packet_interval(comms):
        details.append(
            _tag(
                "REGULAR_PACKET_INTERVAL",
                0.82,
                (
                    f"comms.packet_interval_ms={comms.get('packet_interval_ms')}",
                    f"comms.packet_interval_jitter_ms={comms.get('packet_interval_jitter_ms')}",
                ),
            )
        )
    if comms.get("ack_visible") or ack.get("visible"):
        details.append(
            _tag(
                "ACK_CHANNEL_VISIBLE",
                0.90,
                (f"comms.ack_visible={comms.get('ack_visible')}", f"c2_message.ack.visible={ack.get('visible')}"),
            )
        )
    if _has_packet_size_pattern(comms):
        details.append(
            _tag(
                "PACKET_SIZE_PATTERN",
                0.76,
                (
                    f"comms.packet_size_bytes={comms.get('packet_size_bytes')}",
                    f"comms.packet_size_variance={comms.get('packet_size_variance')}",
                ),
            )
        )
    if c2_message.get("metadata_plaintext") or comms.get("route_metadata_visible"):
        details.append(
            _tag(
                "METADATA_PLAINTEXT",
                0.86,
                (
                    f"c2_message.metadata_plaintext={c2_message.get('metadata_plaintext')}",
                    f"comms.route_metadata_visible={comms.get('route_metadata_visible')}",
                ),
            )
        )
    if comms.get("state_update_dependency") == "HIGH" or c2_message.get("message_role") in {
        "COMMAND",
        "STATE_UPDATE",
    }:
        details.append(
            _tag(
                "STATE_UPDATE_DEPENDENT",
                0.84,
                (
                    f"comms.state_update_dependency={comms.get('state_update_dependency')}",
                    f"c2_message.message_role={c2_message.get('message_role')}",
                ),
            )
        )
    if comms.get("anti_replay_window_s", 0) > 60 and sequence_visible and timestamp_visible:
        details.append(
            _tag(
                "REPLAY_WINDOW_OPEN",
                0.74,
                (
                    f"comms.anti_replay_window_s={comms.get('anti_replay_window_s')}",
                    f"c2_message.sequence_visible={sequence_visible}",
                    f"c2_message.timestamp_visible={timestamp_visible}",
                ),
            )
        )

    crypto_profile = comms.get("crypto_profile", {})
    if crypto_profile.get("weak_cipher_hint") or crypto_profile.get("nonce_reuse_suspected"):
        details.append(
            _tag(
                "CRYPTO_WEAKNESS_HINT",
                0.71,
                (
                    f"comms.crypto_profile.weak_cipher_hint={crypto_profile.get('weak_cipher_hint')}",
                    f"comms.crypto_profile.nonce_reuse_suspected={crypto_profile.get('nonce_reuse_suspected')}",
                ),
            )
        )

    if _has_packet_interval_anomaly(comms):
        details.append(
            _tag(
                "PACKET_INTERVAL_ANOMALY",
                0.90,
                (
                    f"comms.packet_interval_ms={comms.get('packet_interval_ms')}",
                    f"comms.packet_interval_jitter_ms={comms.get('packet_interval_jitter_ms')}",
                ),
            )
        )
    if _has_heartbeat_gap(comms):
        details.append(
            _tag(
                "HEARTBEAT_GAP",
                0.91,
                (
                    f"comms.heartbeat_interval_ms={comms.get('heartbeat_interval_ms')}",
                    f"comms.heartbeat_gap_ms={comms.get('heartbeat_gap_ms')}",
                ),
            )
        )
    if _has_ack_timing_anomaly(c2_message, comms):
        details.append(
            _tag(
                "ACK_TIMING_ANOMALY",
                0.92,
                (
                    f"c2_message.ack.sequence_number={ack.get('sequence_number')}",
                    f"c2_message.sequence_number={c2_message.get('sequence_number')}",
                    f"comms.ack_delay_ms={comms.get('ack_delay_ms')}",
                    f"comms.latency_ms={comms.get('latency_ms')}",
                ),
            )
        )
    if _has_sequence_gap(c2_message, history, comms):
        details.append(
            _tag(
                "SEQUENCE_GAP",
                0.86,
                (
                    f"c2_message.sequence_number={c2_message.get('sequence_number')}",
                    f"history.last_sequence_number={history.get('last_sequence_number')}",
                    f"comms.packet_loss={comms.get('packet_loss')}",
                ),
            )
        )

    return details


def _derive_telemetry_anchor_details(
    telemetry: dict,
    internal_telemetry: dict,
    last_telemetry: dict,
) -> list[SituationTag]:
    details: list[SituationTag] = []
    external_battery = float(telemetry.get("battery_percent", 0.0))
    internal_battery = float(internal_telemetry.get("battery_percent", external_battery))
    battery_gap = external_battery - internal_battery
    abs_gap = abs(battery_gap)
    motor_mismatch = telemetry.get("motor_status") != internal_telemetry.get("motor_status")
    internal_safety_critical = internal_battery <= 25.0 or internal_telemetry.get("motor_status") != "OK"
    external_looks_safer = (
        battery_gap >= 1.0
        or (telemetry.get("motor_status") == "OK" and internal_telemetry.get("motor_status") != "OK")
    )

    if abs_gap >= 6.0 or motor_mismatch:
        details.append(
            _tag(
                "TELEMETRY_ANCHOR_RESIDUAL",
                0.86,
                (
                    f"external.telemetry.battery_percent={telemetry.get('battery_percent')}",
                    f"internal.telemetry.battery_percent={internal_telemetry.get('battery_percent')}",
                    f"battery_anchor_gap={round(battery_gap, 4)}",
                    f"motor_mismatch={motor_mismatch}",
                ),
            )
        )

    if internal_safety_critical and external_looks_safer:
        details.append(
            _tag(
                "TELEMETRY_SAFETY_ANCHOR_RESIDUAL",
                0.93,
                (
                    f"external.telemetry.battery_percent={telemetry.get('battery_percent')}",
                    f"internal.telemetry.battery_percent={internal_telemetry.get('battery_percent')}",
                    f"external.telemetry.motor_status={telemetry.get('motor_status')}",
                    f"internal.telemetry.motor_status={internal_telemetry.get('motor_status')}",
                    "safety_context=low_battery_or_fault_anchor",
                ),
            )
        )

    previous_battery = float(last_telemetry.get("battery_percent", external_battery))
    step_delta = external_battery - previous_battery
    drain_rate = float(telemetry.get("battery_drain_rate", 0.0))
    if internal_safety_critical and battery_gap >= 1.0 and step_delta > 0.35 and drain_rate > 0:
        details.append(
            _tag(
                "TELEMETRY_SERIAL_DRIFT",
                0.87,
                (
                    f"telemetry.battery_step_delta={round(step_delta, 4)}",
                    f"battery_anchor_gap={round(battery_gap, 4)}",
                    f"telemetry.battery_drain_rate={drain_rate}",
                    "monitor=windowed_residual_drift",
                ),
            )
        )

    return details


def _tag(tag: str, confidence: float, evidence: tuple[str, ...]) -> SituationTag:
    return SituationTag(
        tag=tag,
        confidence=round(confidence, 3),
        evidence=evidence,
        meaning=TAG_MEANINGS.get(tag, "observed situation tag"),
    )


def _dedupe_details(details: list[SituationTag]) -> list[SituationTag]:
    by_tag: dict[str, SituationTag] = {}
    for detail in details:
        current = by_tag.get(detail.tag)
        if current is None:
            by_tag[detail.tag] = detail
            continue
        evidence = tuple(dict.fromkeys([*current.evidence, *detail.evidence]))
        confidence = max(current.confidence, detail.confidence)
        by_tag[detail.tag] = SituationTag(detail.tag, confidence, evidence, detail.meaning)
    return [by_tag[tag] for tag in sorted(by_tag)]


def _battery_energy_impossible(obs: dict, history: dict) -> bool:
    telemetry = obs["telemetry"]
    last_telemetry = history["last_telemetry"]
    elapsed_seconds = max(0, obs["time"]["received_timestamp"] - history["last_received_timestamp"])
    elapsed_minutes = elapsed_seconds / 60
    expected_max = (
        last_telemetry["battery_percent"]
        - last_telemetry.get("battery_drain_rate", telemetry["battery_drain_rate"]) * elapsed_minutes
        + TELEMETRY_BATTERY_TOLERANCE
    )
    return telemetry["battery_drain_rate"] > 0 and telemetry["battery_percent"] > expected_max


def _has_regular_packet_interval(comms: dict) -> bool:
    interval_ms = comms.get("packet_interval_ms")
    if interval_ms is None:
        return False
    jitter_ms = comms.get("packet_interval_jitter_ms")
    if jitter_ms is None:
        return False
    return jitter_ms <= max(50, interval_ms * 0.08)


def _has_packet_interval_anomaly(comms: dict) -> bool:
    interval_ms = comms.get("packet_interval_ms")
    jitter_ms = comms.get("packet_interval_jitter_ms")
    if interval_ms is None or jitter_ms is None:
        return False
    return jitter_ms > max(250, interval_ms * 0.40)


def _has_packet_size_pattern(comms: dict) -> bool:
    packet_size = comms.get("packet_size_bytes")
    variance = comms.get("packet_size_variance")
    if packet_size is None or variance is None:
        return False
    return variance <= max(16, packet_size * 0.15)


def _has_heartbeat_gap(comms: dict) -> bool:
    interval_ms = comms.get("heartbeat_interval_ms")
    gap_ms = comms.get("heartbeat_gap_ms")
    if interval_ms is None or gap_ms is None:
        return False
    return gap_ms > interval_ms * 2.5


def _has_ack_timing_anomaly(c2_message: dict, comms: dict) -> bool:
    ack = c2_message.get("ack", {})
    if not (comms.get("ack_visible") or ack.get("visible")):
        return False
    ack_sequence = ack.get("sequence_number")
    message_sequence = c2_message.get("sequence_number")
    if ack_sequence is not None and message_sequence is not None and ack_sequence != message_sequence:
        return True
    ack_delay_ms = comms.get("ack_delay_ms")
    latency_ms = comms.get("latency_ms", 0)
    return ack_delay_ms is not None and ack_delay_ms > max(800, latency_ms * 2)


def _has_sequence_gap(c2_message: dict, history: dict, comms: dict) -> bool:
    sequence_number = c2_message.get("sequence_number")
    last_sequence_number = history.get("last_sequence_number")
    if sequence_number is None or last_sequence_number is None:
        return False
    if sequence_number - last_sequence_number <= 1:
        return False
    return (
        comms.get("packet_loss", 0.0) > 0.05
        or _has_heartbeat_gap(comms)
        or _has_packet_interval_anomaly(comms)
    )


def _gnss_internal_conflict(navigation: dict) -> bool:
    if navigation["gnss_fix_quality"] != "NORMAL":
        return False
    weak_signal = navigation.get("cn0_avg", 99.0) < 25.0
    poor_geometry = navigation["satellite_count"] < 5 or navigation["hdop"] > 5.0
    return weak_signal or poor_geometry


def _imu_telemetry_divergence(obs: dict, history: dict) -> bool:
    last_navigation = history.get("last_navigation")
    if not last_navigation:
        return False

    current = obs["navigation"].get("imu_position_estimate")
    previous = last_navigation.get("imu_position_estimate")
    if not current or not previous:
        return False

    elapsed_seconds = max(0, obs["time"]["received_timestamp"] - history["last_received_timestamp"])
    distance_m = _distance_m(previous, current)
    max_distance_m = obs["telemetry"]["speed_mps"] * elapsed_seconds + GNSS_IMU_DRIFT_TOLERANCE_M
    return distance_m > max_distance_m


def _command_time_inconsistent(obs: dict, history: dict) -> bool:
    sequence_delta = obs["c2_message"]["sequence_number"] - history["last_sequence_number"]
    time_delta = obs["time"]["received_timestamp"] - history["last_received_timestamp"]
    if sequence_delta <= 0:
        return False
    expected_time_delta = sequence_delta * ROUND_SECONDS
    return abs(time_delta - expected_time_delta) > ROUND_SECONDS


def _distance_m(previous: dict, current: dict) -> float:
    lat_scale = 111_320
    lon_scale = lat_scale * cos(radians((previous["lat"] + current["lat"]) / 2))
    d_lat = (current["lat"] - previous["lat"]) * lat_scale
    d_lon = (current["lon"] - previous["lon"]) * lon_scale
    return sqrt(d_lat * d_lat + d_lon * d_lon)
