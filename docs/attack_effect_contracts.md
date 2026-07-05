# Attack-Effect Contracts

이 문서는 Red 공격 후보와 기대되는 시뮬레이션 효과를 묶는 계약서다.
목적은 실제 침투 절차를 설명하는 것이 아니라, `이 공격을 골랐으면 어떤 observe 효과를 기대해야 하는가`를 명확히 하는 것이다.

## Why This Exists

이전 구조에서는 Goal Planner가 목표를 고르고 Attack Selector가 공격을 고를 때, 둘 사이의 연결이 느슨했다.
그래서 `PRIORITY_POISONING`이 `COMMAND_STALE_ACCEPTANCE` 같은 command-domain 목표와 결합될 수 있었다.
이 경우 scorer가 대체로 실패로 처리하긴 했지만, 왜 실패인지 설명하는 명시적 계약이 없었다.

Attack-Effect Contract는 다음을 고정한다.

```text
attack_name
-> supported_goal_ids
-> supported_tactics
-> mutation_paths
-> expected_tags
-> expected_effect_tags
-> success_evidence_keys
-> failure_modes
```

## Safety Boundary

이 계약은 실제 RF, API, exploit, payload, key, replay 절차를 만들지 않는다.
코드에 반영되는 것은 오직 안전한 시뮬레이터 내부의 `blue_observed` 필드, 상황 태그, scorer evidence뿐이다.

## Source Basis

| Source | Used For |
|---|---|
| MAVLink Message Signing docs, https://mavlink.io/en/guide/message_signing.html | signed packet timestamp monotonicity, replay rejection, signing/unsigned boundary |
| MAVLink Command Protocol docs, https://mavlink.io/en/services/command.html | command-to-ACK causal relation and retry/timeout assumptions |
| MAVLink Heartbeat Protocol docs, https://mavlink.io/en/services/heartbeat.html | heartbeat gaps and disconnected-state reasoning |
| Allouch et al., MAVSec, https://arxiv.org/abs/1905.00265 | MAVLink confidentiality, integrity, replay, deletion, modification, DoS threat families |
| Sathaye et al., SemperFi, https://arxiv.org/abs/2105.01860 | UAV GNSS spoofing resilience and inertial consistency as a defensive anchor |
| Pekaric et al., UAV sensor spoofing simulation, https://arxiv.org/abs/2309.09648 | representing GPS/LiDAR spoofing as simulator-level security tests |
| Ying et al., SODA ADS-B spoofing detector, https://arxiv.org/abs/1904.09969 | unauthenticated broadcast metadata can create false situational beliefs |

## Contracts

### PRIORITY_POISONING

Purpose: mission-belief pollution.

Supported goals:

- `WRONG_TARGET_SELECTION`
- `DETECTION_BOUNDARY_PROBE`
- `BLUE_OVERDEFENSE_ATTRITION`

Mutation paths:

- `mission.area_priority`
- `mission.recommended_area`

Expected tags:

- `MISSION_PRIORITY_CHANGED`
- `METADATA_PLAINTEXT`
- `PAYLOAD_HIDDEN`
- `C2_ENCRYPTED`

Success evidence:

- `max_priority_delta`
- `observed_top_area`
- `recommended_area`

This contract is coherent when Red tries to bias Blue's target or area selection.
It is not coherent evidence for stale command acceptance, ACK confusion, or telemetry trust erosion.

### TELEMETRY_FDI

Purpose: external telemetry trust erosion.

Supported goals:

- `TELEMETRY_TRUST_EROSION`
- `DETECTION_BOUNDARY_PROBE`
- `BLUE_OVERDEFENSE_ATTRITION`

Mutation paths:

- `telemetry.battery_percent`
- `telemetry.motor_status`

Expected tags:

- `TELEMETRY_CONFLICT`
- `BATTERY_MOTOR_INCONSISTENT`
- `BATTERY_ENERGY_IMPOSSIBLE`
- `IMU_TELEMETRY_DIVERGENCE`
- `CROSS_CHECK_UNAVAILABLE`
- `GNSS_PRIMARY`

Success evidence:

- `battery_delta`
- `motor_mismatch`
- `impossible_drain_hint`

This contract models false-data effects against external telemetry belief.
The defensive anchor is cross-checking against internal observe and physical consistency.

### TIME_DESYNC_REPLAY

Purpose: encrypted-channel metadata and freshness confusion.

Supported goals:

- `COMMAND_STALE_ACCEPTANCE`
- `ACK_CAUSAL_CONFUSION`
- `CHANNEL_STATE_SUPPRESSION`
- `DETECTION_BOUNDARY_PROBE`
- `BLUE_OVERDEFENSE_ATTRITION`

Mutation paths:

- `c2_message.sequence_number`
- `time.received_timestamp`
- `c2_message.command`
- `c2_message.ack.sequence_number`
- `c2_message.ack.status`
- `comms.latency_ms`
- `comms.packet_loss`
- `comms.packet_interval_jitter_ms`
- `comms.ack_delay_ms`
- `comms.heartbeat_gap_ms`

Expected tags:

- `SEQUENCE_VISIBLE`
- `TIMESTAMP_VISIBLE`
- `REPLAY_WINDOW_OPEN`
- `SEQUENCE_REGRESSION`
- `TIMESTAMP_SKEW`
- `COMMAND_TIMING_INCONSISTENT`
- `ACK_CHANNEL_VISIBLE`
- `ACK_TIMING_ANOMALY`
- `PACKET_INTERVAL_ANOMALY`
- `HEARTBEAT_GAP`
- `PACKET_LOSS_HIGH`
- `STATE_UPDATE_DEPENDENT`

Success evidence:

- `sequence_lag`
- `timestamp_lag_s`
- `ack_gap`
- `ack_delay_ms`
- `heartbeat_gap_ms`
- `packet_loss`
- `latency_ms`

This contract is coherent when payload remains opaque but sequence, timing, ACK, or channel-shape metadata makes Blue reason over stale or missing state.

## Critical Assessment

What improved:

- Attack selection now has contract alignment. Tag fit alone is no longer enough, and unsupported goals are hard-gated out of attack selection.
- Goal scoring now records `contract_alignment`.
- Unsupported attack-goal pairs are clamped to failed/low-reward outcomes.
- Logs can now explain whether a result came from mission, telemetry, or command effect evidence.

Observed 10-round comparison with seed 42:

| Metric | Before contract | After contract |
|---|---:|---:|
| unsupported attack-goal pairs | 2 | 0 |
| goal_success_rate | 0.8 | 1.0 |
| avg_goal_reward | 0.659 | 0.729 |
| detection_rate | 1.0 | 1.0 |
| final_availability | 0.93 | 0.94 |
| attack entropy | 1.361 | 1.1568 |

Guarded follow-up after adding Causal Consistency Monitor, repeat guard, entropy metrics, and policy saturation guard:

| Metric | Contract only | Contract + guards |
|---|---:|---:|
| unsupported attack-goal pairs | 0 | 0 |
| goal_success_rate | 1.0 | 1.0 |
| avg_causal_consistency | not measured | 0.99 |
| causal failure count | not measured | 0 |
| attack entropy | 1.1568 | 1.371 |
| tactic entropy | not measured | 1.9219 |
| min command domain_trust | 0.0 | 0.12 |

What did not improve enough:

- Contracts are still human-authored. They are clearer, but not learned causal proof.
- Evidence thresholds are still rule-based. A learned causal model could later estimate these from generated episodes.
- The current simulator has only three implemented attack families, so contracts are precise but narrow.
- `DETECTION_BOUNDARY_PROBE` remains broad by design, which is useful for learning but can hide weaker semantic alignment.
- Hard-gating improves semantic correctness but reduces exploration. The repeat guard partially recovers tactic diversity, but deeper goal diversity still depends on richer world scenarios and more contract-compatible attack families.

Bottom line: this is a real improvement for explainability and reward hygiene. It is not a pure quality win: it makes the simulator more honest but also more rigid, so the next improvement should add controlled exploration among contract-compatible tactics rather than relaxing the contract itself.
