"""Attack-to-effect contracts for safe simulator scoring.

The contracts do not describe real attack procedures. They define which
simulated observe fields, situation tags, and cyber-effect goals are coherent
for each Red attack family.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dah_flawless.schemas import SituationTag


@dataclass(frozen=True)
class AttackEffectContract:
    attack_name: str
    target_domain: str
    supported_goal_ids: tuple[str, ...]
    supported_tactics: tuple[str, ...]
    mutation_paths: tuple[str, ...]
    expected_tags: tuple[str, ...]
    expected_effect_tags: tuple[str, ...]
    success_evidence_keys: tuple[str, ...]
    failure_modes: tuple[str, ...]
    source_refs: tuple[str, ...]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, tuple):
                data[key] = list(value)
        return data


GOAL_EFFECT_TAG: dict[str, str] = {
    "TELEMETRY_TRUST_EROSION": "EFFECT_TELEMETRY_TRUST_EROSION",
    "WRONG_TARGET_SELECTION": "EFFECT_WRONG_TARGET_SELECTION",
    "COMMAND_STALE_ACCEPTANCE": "EFFECT_COMMAND_STALE_ACCEPTANCE",
    "ACK_CAUSAL_CONFUSION": "EFFECT_ACK_CAUSAL_CONFUSION",
    "CHANNEL_STATE_SUPPRESSION": "EFFECT_CHANNEL_STATE_SUPPRESSION",
    "DETECTION_BOUNDARY_PROBE": "EFFECT_DETECTION_BOUNDARY_PROBE",
}


CONTRACTS: dict[str, AttackEffectContract] = {
    "PRIORITY_POISONING": AttackEffectContract(
        attack_name="PRIORITY_POISONING",
        target_domain="mission",
        supported_goal_ids=(
            "WRONG_TARGET_SELECTION",
            "DETECTION_BOUNDARY_PROBE",
            "BLUE_OVERDEFENSE_ATTRITION",
        ),
        supported_tactics=("mission_priority_shift", "recommended_area_nudge", "mission_confidence_shaping"),
        mutation_paths=("mission.area_priority", "mission.recommended_area"),
        expected_tags=(
            "MISSION_PRIORITY_CHANGED",
            "METADATA_PLAINTEXT",
            "PAYLOAD_HIDDEN",
            "C2_ENCRYPTED",
        ),
        expected_effect_tags=(
            "EFFECT_WRONG_TARGET_SELECTION",
            "EFFECT_DETECTION_BOUNDARY_PROBE",
        ),
        success_evidence_keys=(
            "max_priority_delta",
            "observed_top_area",
            "recommended_area",
            "action_cost",
            "availability_drop",
            "defense_action_count",
        ),
        failure_modes=(
            "priority drift does not change top or recommended mission area",
            "Blue restores mission state from last-known-good data",
            "selected goal is not mission-belief or boundary-probe related",
        ),
        source_refs=(
            "MAVSec 2019: MAVLink confidentiality/integrity gaps and spoofing/modification risks",
            "ADS-B SODA 2019: unauthenticated surveillance messages can create false traffic beliefs",
            "MAVLink command/mission docs: command and positional semantics rely on message interpretation",
        ),
        rationale=(
            "This contract models decision-support pollution: visible mission priority metadata "
            "drifts away from scorer-truth priorities, causing wrong target selection or detector "
            "boundary feedback. It is not coherent evidence for stale C2 command acceptance."
        ),
    ),
    "TELEMETRY_FDI": AttackEffectContract(
        attack_name="TELEMETRY_FDI",
        target_domain="telemetry",
        supported_goal_ids=(
            "TELEMETRY_TRUST_EROSION",
            "DETECTION_BOUNDARY_PROBE",
            "BLUE_OVERDEFENSE_ATTRITION",
        ),
        supported_tactics=(
            "telemetry_false_data",
            "boundary_probe",
            "confidence_spoofing",
            "internal_external_gap_shaping",
        ),
        mutation_paths=("telemetry.battery_percent", "telemetry.motor_status"),
        expected_tags=(
            "TELEMETRY_CONFLICT",
            "BATTERY_MOTOR_INCONSISTENT",
            "BATTERY_ENERGY_IMPOSSIBLE",
            "IMU_TELEMETRY_DIVERGENCE",
            "CROSS_CHECK_UNAVAILABLE",
            "GNSS_PRIMARY",
        ),
        expected_effect_tags=(
            "EFFECT_TELEMETRY_TRUST_EROSION",
            "EFFECT_DETECTION_BOUNDARY_PROBE",
        ),
        success_evidence_keys=(
            "battery_delta",
            "motor_mismatch",
            "impossible_drain_hint",
            "action_cost",
            "availability_drop",
            "defense_action_count",
        ),
        failure_modes=(
            "external telemetry remains physically plausible",
            "internal observe and cross-check capability dominate Blue trust",
            "selected goal requires command freshness or mission-priority effects",
        ),
        source_refs=(
            "SemperFi 2021: UAV GPS spoofing resilience relies on inertial consistency checks",
            "Sensor spoofing simulation 2023: UAV GPS/LiDAR spoofing can be represented in simulation",
            "MAVSec 2019: unsecured telemetry links lack integrity protection in common MAVLink setups",
        ),
        rationale=(
            "This contract models false-data injection against external telemetry belief. The expected "
            "effect is trust erosion through physical inconsistency, not command replay or target-priority drift."
        ),
    ),
    "TIME_DESYNC_REPLAY": AttackEffectContract(
        attack_name="TIME_DESYNC_REPLAY",
        target_domain="command",
        supported_goal_ids=(
            "COMMAND_STALE_ACCEPTANCE",
            "ACK_CAUSAL_CONFUSION",
            "CHANNEL_STATE_SUPPRESSION",
            "DETECTION_BOUNDARY_PROBE",
            "BLUE_OVERDEFENSE_ATTRITION",
        ),
        supported_tactics=("replay", "delay", "selective_drop", "ack_confusion", "metadata_poisoning"),
        mutation_paths=(
            "c2_message.sequence_number",
            "time.received_timestamp",
            "c2_message.command",
            "c2_message.ack.sequence_number",
            "c2_message.ack.status",
            "comms.latency_ms",
            "comms.packet_loss",
            "comms.packet_interval_jitter_ms",
            "comms.ack_delay_ms",
            "comms.heartbeat_gap_ms",
        ),
        expected_tags=(
            "SEQUENCE_VISIBLE",
            "TIMESTAMP_VISIBLE",
            "REPLAY_WINDOW_OPEN",
            "SEQUENCE_REGRESSION",
            "TIMESTAMP_SKEW",
            "COMMAND_TIMING_INCONSISTENT",
            "ACK_CHANNEL_VISIBLE",
            "ACK_TIMING_ANOMALY",
            "PACKET_INTERVAL_ANOMALY",
            "HEARTBEAT_GAP",
            "PACKET_LOSS_HIGH",
            "STATE_UPDATE_DEPENDENT",
        ),
        expected_effect_tags=(
            "EFFECT_COMMAND_STALE_ACCEPTANCE",
            "EFFECT_ACK_CAUSAL_CONFUSION",
            "EFFECT_CHANNEL_STATE_SUPPRESSION",
            "EFFECT_DETECTION_BOUNDARY_PROBE",
        ),
        success_evidence_keys=(
            "sequence_lag",
            "timestamp_lag_s",
            "ack_gap",
            "ack_delay_ms",
            "heartbeat_gap_ms",
            "packet_loss",
            "latency_ms",
            "action_cost",
            "availability_drop",
            "defense_action_count",
        ),
        failure_modes=(
            "monotonic sequence/timestamp checks reject stale metadata",
            "ACK causality remains aligned with the current command",
            "heartbeat and state updates stay within normal timing envelopes",
            "selected goal requires mission-priority or telemetry-trust effects",
        ),
        source_refs=(
            "MAVLink signing docs: signed packet timestamps must monotonically increase and stale signed packets are rejected",
            "MAVLink command protocol docs: commands expect matching COMMAND_ACK and retry on missing ACK",
            "MAVLink heartbeat docs: missing heartbeats imply connection timeout on many RF telemetry links",
            "MAVSec 2019: replay, message deletion, modification, and DoS are MAVLink security threats",
        ),
        rationale=(
            "This contract models encrypted-channel metadata attacks: payload remains opaque, but visible "
            "sequence, timing, ACK, and channel-shape fields can make Blue reason over stale or missing state."
        ),
    ),
}


def get_attack_effect_contract(attack_name: str) -> AttackEffectContract:
    try:
        return CONTRACTS[attack_name]
    except KeyError as exc:
        raise ValueError(f"unknown attack-effect contract: {attack_name}") from exc


def contract_supports_goal(attack_name: str, goal_id: str | None) -> bool:
    if not goal_id:
        return True
    contract = CONTRACTS.get(attack_name)
    return bool(contract and goal_id in contract.supported_goal_ids)


def contract_supports_tactic(attack_name: str, strategy: str | None) -> bool:
    if not strategy:
        return True
    contract = CONTRACTS.get(attack_name)
    return bool(contract and strategy in contract.supported_tactics)


def score_contract_alignment(
    attack_name: str,
    goal_plan: dict[str, Any] | None,
    tag_details: list[SituationTag] | None = None,
) -> dict[str, Any]:
    contract = CONTRACTS.get(attack_name)
    if contract is None:
        return {
            "score": 0.0,
            "supported_goal": False,
            "matched_contract_tags": [],
            "expected_mutation_paths": [],
            "reason": "missing_contract",
        }

    goal_id = (goal_plan or {}).get("goal_id")
    supported_goal = contract_supports_goal(attack_name, goal_id)
    tag_confidence = _tag_confidence(tag_details)
    matched_tags = sorted(set(contract.expected_tags).intersection(tag_confidence))
    matched_strength = min(1.0, sum(tag_confidence[tag] for tag in matched_tags) / 3.0)

    target_domain = (goal_plan or {}).get("target_domain")
    target_match = target_domain in {None, contract.target_domain, "multi_domain"}
    preferred_tactics = set((goal_plan or {}).get("preferred_tactics", []))
    tactic_match = bool(preferred_tactics.intersection(contract.supported_tactics)) if preferred_tactics else True

    score = 0.10
    if supported_goal:
        score += 0.48
    if target_match:
        score += 0.16
    if tactic_match:
        score += 0.12
    score += 0.14 * matched_strength
    score = round(min(1.0, max(0.0, score)), 4)

    if not supported_goal:
        reason = "goal_not_supported_by_attack_effect_contract"
    elif not target_match:
        reason = "goal_target_domain_mismatch"
    elif not tactic_match:
        reason = "goal_tactic_mismatch"
    else:
        reason = "contract_aligned"

    return {
        "score": score,
        "supported_goal": supported_goal,
        "target_domain_match": target_match,
        "tactic_match": tactic_match,
        "matched_contract_tags": matched_tags,
        "expected_effect_tags": list(contract.expected_effect_tags),
        "expected_mutation_paths": list(contract.mutation_paths),
        "success_evidence_keys": list(contract.success_evidence_keys),
        "failure_modes": list(contract.failure_modes),
        "reason": reason,
    }


def contract_summary_for_attack(attack_name: str) -> dict[str, Any]:
    return get_attack_effect_contract(attack_name).to_dict()


def _tag_confidence(tag_details: list[SituationTag] | None) -> dict[str, float]:
    return {detail.tag: detail.confidence for detail in tag_details or []}
