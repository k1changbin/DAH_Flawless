# Field Format Reference

이 문서는 runtime state의 `world`, `blue_observed`, `tag`, `score/log`에 들어가는 각 값의 형식, 단위, 범위, 예시를 정의한다. 구현할 때는 이 표를 기준으로 dataclass 또는 JSON schema를 만든다.

용어 주의:

```text
이 문서의 world.* 경로는 현재 코드 호환 키 state["world"]를 뜻한다.
의미상 이름은 scorer_truth.* 이며, raw_world 원천 신호 schema가 아니다.
raw_world 필드는 docs/raw_world_schema.md와 configs/raw_world_schema.yaml을 기준으로 한다.
```

## 1. 기본 타입 규칙

| 타입 | 형식 | 예시 |
|---|---|---|
| `int` | 정수 | `1021` |
| `float` | 실수 | `0.21`, `37.123` |
| `bool` | `true` 또는 `false` | `true` |
| `string` | 대문자 enum 또는 명령 문자열 | `"CLEAR"`, `"RETURN_TO_BASE"` |
| `timestamp` | Unix epoch seconds, `int` | `1710001200` |
| `ratio` | 0.0~1.0 실수 | `0.12` |
| `percent` | 0~100 숫자 | `82` |
| `lat/lon` | WGS84 decimal degrees | `37.123`, `127.456` |
| `tag` | 대문자 snake case 문자열 | `"GNSS_DEGRADED"` |

## 2. Scorer Truth Field Formats

### 2.1 Time

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.time.true_timestamp` | `timestamp` | Unix seconds | `1710001200` | scorer truth 기준 시간 |
| `world.time.round` | `int` | 0 이상 | `3` | 시뮬레이션 라운드 |

### 2.2 Environment

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.environment.weather` | enum string | `CLEAR`, `RAIN`, `FOG`, `WIND`, `STORM` | `"CLEAR"` | scorer truth 기상 |
| `world.environment.terrain` | enum string | `OPEN`, `URBAN`, `LOW_MOUNTAIN`, `COASTAL` | `"LOW_MOUNTAIN"` | scorer truth 지형 |
| `world.environment.rf_noise_level` | `ratio` | 0.0~1.0 | `0.21` | raw_world에서 해석된 전파 잡음 수준 |
| `world.environment.gnss_interference` | enum string | `NONE`, `JAMMING`, `SPOOFING`, `MULTIPATH`, `UNKNOWN` | `"NONE"` | raw_world에서 해석된 GNSS 간섭 상태 |

### 2.3 UAV

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.uav.position.lat` | `float` | -90~90 degrees | `37.123` | scorer truth 위도 |
| `world.uav.position.lon` | `float` | -180~180 degrees | `127.456` | scorer truth 경도 |
| `world.uav.position.altitude_m` | `float` | meters | `180` | scorer truth 고도 |
| `world.uav.speed_mps` | `float` | meters/second, 0 이상 | `42` | scorer truth 속도 |
| `world.uav.heading_deg` | `float` | 0~359.999 degrees | `91` | scorer truth 진행 방향 |
| `world.uav.battery_percent` | `percent` | 0~100 | `20` | scorer truth 배터리 잔량 |
| `world.uav.battery_drain_rate` | `float` | percent/round 또는 percent/min | `1.0` | scorer truth 배터리 소모율 |
| `world.uav.motor_status` | enum string | `OK`, `DEGRADED`, `FAULT`, `UNKNOWN` | `"FAULT"` | scorer truth 모터 상태 |
| `world.uav.imu_accel.x` | `float` | m/s^2 | `0.1` | 실제 x축 가속도 |
| `world.uav.imu_accel.y` | `float` | m/s^2 | `0.0` | 실제 y축 가속도 |
| `world.uav.imu_accel.z` | `float` | m/s^2 | `9.8` | 실제 z축 가속도 |

### 2.4 Mission

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.mission.current_area` | enum string | `A`, `B`, `C` | `"A"` | scorer truth 현재 임무 구역 |
| `world.mission.area_priority.A` | `ratio` | 0.0~1.0 | `0.9` | A구역 scorer truth 우선순위 |
| `world.mission.area_priority.B` | `ratio` | 0.0~1.0 | `0.4` | B구역 scorer truth 우선순위 |
| `world.mission.area_priority.C` | `ratio` | 0.0~1.0 | `0.2` | C구역 scorer truth 우선순위 |
| `world.mission.return_required` | `bool` | true/false | `true` | scorer truth 복귀 필요 여부 |

### 2.5 Command

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.command.expected_sequence_number` | `int` | 0 이상, 단조 증가 | `1021` | 정상적으로 기대되는 다음 명령 번호 |
| `world.command.last_valid_command` | enum string | `CONTINUE_MISSION`, `RETURN_TO_BASE`, `HOLD_POSITION`, `ENTER_SAFE_MODE` | `"RETURN_TO_BASE"` | 마지막 정상 명령 |

## 3. Blue Observed Field Formats

Observe v0.3 기준에서 `blue_observed`는 canonical하게 `internal_observe`와 `external_observe`로 나뉜다.

- `blue_observed.internal_observe.*`: 내부 센서/로컬 상태 관측. Red 직접 mutation 금지.
- `blue_observed.external_observe.*`: 외부 신호/통신/원격 관측. Red mutation 허용 표면.
- `blue_observed.telemetry_channels`: 송출/수신 telemetry projection. Red가 읽을 수는 있지만 직접 mutation하지 못하는 memory/intel 자원.
- `blue_observed.observe_access.red_visibility`: Red가 읽을 수 있는 telemetry channel path와 mutation 제외 path를 명시하는 visibility policy.
- `blue_observed.telemetry`, `blue_observed.navigation`, `blue_observed.mission`, `blue_observed.c2_message`, `blue_observed.comms`는 현재 MVP 코드 호환용 flat view이며 `external_observe`의 alias다.

### 3.1 Time

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.time.received_timestamp` | `timestamp` | Unix seconds | `1710000800` | Blue가 수신한 메시지 시간 |
| `blue_observed.time.local_clock_offset_ms` | `int` | milliseconds | `430` | 로컬 시계 오프셋 |

### 3.2 Telemetry

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.telemetry.battery_percent` | `percent` | 0~100 | `20` | Blue가 받은 배터리 값. `TELEMETRY_FDI` 실행 경로에서는 직접 변조하지 않음 |
| `blue_observed.telemetry.battery_drain_rate` | `float` | percent/round 또는 percent/min | `1.0` | Blue가 받은 배터리 소모율 |
| `blue_observed.telemetry.motor_status` | enum string | `OK`, `DEGRADED`, `FAULT`, `UNKNOWN` | `"FAULT"` | Blue가 받은 모터 상태. `TELEMETRY_FDI` 실행 경로에서는 직접 변조하지 않음 |
| `blue_observed.telemetry.altitude_m` | `float` | meters | `180` | Blue가 받은 고도 |
| `blue_observed.telemetry.speed_mps` | `float` | meters/second | `42` | Blue가 받은 속도 |
| `blue_observed.telemetry.heading_deg` | `float` | 0~359.999 degrees | `91` | Blue가 받은 진행 방향 |

### 3.2.1 Telemetry Channels

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.telemetry_channels.schema_id` | string | schema id | `"dah.telemetry_channels.v0_1"` | telemetry 송출/수신 projection schema |
| `blue_observed.telemetry_channels.asset_tx_mirror.battery_percent` | percent | 0~100 | `20` | asset이 송출한 telemetry projection. Red read-only |
| `blue_observed.telemetry_channels.asset_tx_mirror.motor_status` | enum string | `OK`, `DEGRADED`, `FAULT`, `UNKNOWN` | `"FAULT"` | asset 송출 모터 상태 projection. Red direct mutation 금지 |
| `blue_observed.telemetry_channels.ground_rx_view.battery_percent` | percent | 0~100 | `20` | Blue ground side가 수신한 telemetry view. Red direct mutation 금지 |
| `blue_observed.telemetry_channels.ground_rx_view.freshness_s` | float | seconds | `0.0` | 송출 timestamp 대비 수신 freshness |
| `blue_observed.telemetry_channels.ground_rx_view.confidence` | float | 0~1 | `0.921` | latency/loss/jitter 기반 수신 confidence |
| `blue_observed.telemetry_channels.link_summary.latency_ms` | int | milliseconds | `180` | telemetry 수신 채널 요약 latency |
| `blue_observed.observe_access.red_visibility.policy_id` | string | policy id | `"dah.red_visibility.v0_1"` | Red observe visibility policy |
| `blue_observed.observe_access.red_visibility.can_read.telemetry_channel_paths` | list[string] | path list | `["blue_observed.external_observe.telemetry_channels.asset_tx_mirror"]` | Red가 읽을 수 있는 송출/수신 telemetry 경로 |
| `blue_observed.observe_access.red_visibility.mutation_excluded.paths` | list[string] | path patterns | `["blue_observed.external_observe.telemetry_channels.*"]` | Red mutation path에서 제외되는 read-only telemetry 경로 |

### 3.2.2 Red Telemetry Memory

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `decision_log[].after.telemetry_memory.schema_id` | string | schema id | `"dah.red_telemetry_memory.v0_1"` | Red telemetry memory schema |
| `decision_log[].after.telemetry_memory.max_records` | int | 1 이상 | `12` | 유지하는 최근 telemetry memory record 수 |
| `decision_log[].after.telemetry_memory.records[].asset_tx_mirror` | object | read-only telemetry projection | `{...}` | Red가 읽은 asset 송출 telemetry projection snapshot |
| `decision_log[].after.telemetry_memory.records[].ground_rx_view` | object | read-only telemetry projection | `{...}` | Red가 읽은 Blue 수신 telemetry projection snapshot |
| `decision_log[].after.telemetry_memory.records[].derived.battery_delta_rx_minus_tx` | float/null | percent delta | `0.0` | 수신 배터리값 - 송출 배터리값 |
| `decision_log[].after.telemetry_memory.records[].derived.read_only_confirmed` | bool | true/false | `true` | memory source가 direct mutation 금지 projection인지 여부 |
| `decision_log[].after.telemetry_memory.features.pattern_hint` | enum string | memory hint | `"stable_tx_rx_alignment"` | Red 선택 로그에 남는 telemetry memory 요약 hint |

### 3.2.3 Blue Telemetry Channel Checks

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `decision_log[].after.telemetry_channel_checks.schema_id` | string | schema id | `"dah.blue_telemetry_channel_checks.v0_1"` | Blue telemetry 채널 검사 schema |
| `decision_log[].after.telemetry_channel_checks.checks.internal_vs_tx.status` | enum string | `PASS`, `WARN`, `FAIL` | `"PASS"` | internal telemetry와 asset tx mirror 일치 여부 |
| `decision_log[].after.telemetry_channel_checks.checks.tx_vs_rx.status` | enum string | `PASS`, `WARN`, `FAIL` | `"FAIL"` | asset tx mirror와 ground rx view 일치 여부 |
| `decision_log[].after.telemetry_channel_checks.checks.rx_vs_command.status` | enum string | `PASS`, `WARN`, `FAIL` | `"FAIL"` | 수신 telemetry 상태와 command/ACK 의미의 정합성 |
| `decision_log[].after.telemetry_channel_checks.checks.freshness.status` | enum string | `PASS`, `WARN`, `FAIL` | `"WARN"` | 수신 telemetry freshness/link quality 상태 |
| `decision_log[].after.telemetry_channel_checks.failed_checks` | array | check id list | `["tx_vs_rx"]` | 실패 또는 경고인 검사 축 |

### 3.2.4 Telemetry Learning Signal

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `score.evidence.goal_score.evidence.telemetry_command_confusion` | ratio | 0.0~1.0 | `0.62` | rx telemetry와 command/ACK 의미가 충돌해 Blue 명령 해석을 흔드는 정도 |
| `score.evidence.goal_score.evidence.stale_state_acceptance` | ratio | 0.0~1.0 | `0.50` | freshness, sequence, timestamp, link timing 때문에 오래된 상태를 받아들일 위험 |
| `score.evidence.goal_score.evidence.wrong_safety_decision` | ratio | 0.0~1.0 | `0.58` | telemetry/command 조합이 복귀/안전 판단을 틀리게 만들 위험 |
| `score.evidence.goal_score.evidence.tx_rx_consistency_pressure` | ratio | 0.0~1.0 | `0.22` | internal-vs-tx 또는 tx-vs-rx 불일치 압력 |
| `score.evidence.goal_score.evidence.legacy_sensor_delta` | ratio | 0.0~1.0 | `0.0` | 과거 직접 battery/motor delta 호환 축. 현재 TELEMETRY_FDI에서는 보조 evidence |
| `score.evidence.goal_score.evidence.telemetry_learning_signal.axis_weights` | object | ratio weights | `{...}` | TELEMETRY_FDI scorer 축별 가중치 |
| `score.evidence.goal_score.evidence.telemetry_learning_signal.dominant_axis` | enum string | axis id | `"telemetry_command_confusion"` | 해당 라운드에서 가장 큰 telemetry 학습 축 |
| `score.evidence.goal_score.evidence.telemetry_learning_signal.active_axes` | array | axis ids | `["telemetry_command_confusion", "stale_state_acceptance"]` | 0.20 이상으로 활성화된 telemetry 축 |
| `score.evidence.goal_score.evidence.telemetry_learning_signal.red_policy_diversity_bonus` | ratio | 0.0~0.12 | `0.07` | Red 상대 공격 가중치 업데이트에 주는 telemetry 다양화 보너스 |

### 3.3 Navigation / GNSS

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.navigation.gnss_position.lat` | `float` | -90~90 degrees | `37.128` | GNSS 계산 위도 |
| `blue_observed.navigation.gnss_position.lon` | `float` | -180~180 degrees | `127.460` | GNSS 계산 경도 |
| `blue_observed.navigation.gnss_position.altitude_m` | `float` | meters | `181` | GNSS 계산 고도 |
| `blue_observed.navigation.gnss_fix_quality` | enum string | `NO_FIX`, `DEGRADED`, `NORMAL`, `RTK_FIXED` | `"DEGRADED"` | GNSS fix 품질 |
| `blue_observed.navigation.satellite_count` | `int` | 0 이상 | `4` | 수신 위성 수 |
| `blue_observed.navigation.hdop` | `float` | 0 이상, 낮을수록 좋음 | `6.2` | 수평 위치 정밀도 저하 지표 |
| `blue_observed.navigation.cn0_avg` | `float` | dB-Hz | `22.5` | 평균 반송파 대 잡음밀도비 |
| `blue_observed.navigation.imu_position_estimate.lat` | `float` | -90~90 degrees | `37.123` | IMU 기반 추정 위도 |
| `blue_observed.navigation.imu_position_estimate.lon` | `float` | -180~180 degrees | `127.456` | IMU 기반 추정 경도 |

### 3.4 Mission

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.mission.area_priority.A` | `ratio` | 0.0~1.0 | `0.2` | Blue가 받은 A구역 우선순위 |
| `blue_observed.mission.area_priority.B` | `ratio` | 0.0~1.0 | `0.4` | Blue가 받은 B구역 우선순위 |
| `blue_observed.mission.area_priority.C` | `ratio` | 0.0~1.0 | `0.95` | Blue가 받은 C구역 우선순위 |
| `blue_observed.mission.recommended_area` | enum string | `A`, `B`, `C`, `NONE` | `"C"` | 관측값 기반 추천 구역 |

### 3.5 C2 Message

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.c2_message.sequence_number` | `int` | 0 이상, 정상 stream에서는 단조 증가 | `1008` | 수신 메시지 sequence |
| `blue_observed.c2_message.command` | enum string | `CONTINUE_MISSION`, `RETURN_TO_BASE`, `HOLD_POSITION`, `ENTER_SAFE_MODE` | `"CONTINUE_MISSION"` | 수신 명령 |
| `blue_observed.c2_message.sysid` | `int` | 0~255 | `1` | 송신 system id |
| `blue_observed.c2_message.compid` | `int` | 0~255 | `1` | 송신 component id |
| `blue_observed.c2_message.msgid` | `int` | 0 이상 | `76` | 메시지 타입 id |
| `blue_observed.c2_message.message_role` | enum string | `COMMAND`, `STATE_UPDATE`, `HEARTBEAT`, `ACK`, `UNKNOWN` | `"COMMAND"` | 메시지 역할 추정값 |
| `blue_observed.c2_message.sequence_visible` | `bool` | true/false | `true` | sequence 필드 관찰 가능 여부 |
| `blue_observed.c2_message.timestamp_visible` | `bool` | true/false | `true` | timestamp/수신시간 관찰 가능 여부 |
| `blue_observed.c2_message.metadata_plaintext` | `bool` | true/false | `true` | payload 밖 메타데이터 관찰 가능 여부 |
| `blue_observed.c2_message.checksum_valid` | `bool` | true/false | `true` | checksum 검증 결과 |
| `blue_observed.c2_message.signature_present` | `bool` | true/false | `true` | 메시지 서명 존재 여부 |
| `blue_observed.c2_message.auth_valid` | `bool` | true/false | `true` | 인증/서명 검증 결과 |
| `blue_observed.c2_message.ack.visible` | `bool` | true/false | `true` | ACK 흐름 관찰 가능 여부 |
| `blue_observed.c2_message.ack.sequence_number` | `int` | 0 이상 | `1021` | 확인 응답이 가리키는 sequence |
| `blue_observed.c2_message.ack.status` | enum string | `ACCEPTED`, `REJECTED`, `PENDING`, `UNKNOWN` | `"ACCEPTED"` | ACK 상태 |

### 3.6 Comms

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.comms.channel` | enum string | `SATCOM`, `LOS`, `MESH`, `UNKNOWN` | `"SATCOM"` | 통신 채널 |
| `blue_observed.comms.encrypted` | `bool` | true/false | `true` | 암호화 여부 |
| `blue_observed.comms.payload_visible` | `bool` | true/false | `false` | payload 내용을 볼 수 있는지 |
| `blue_observed.comms.latency_ms` | `int` | milliseconds, 0 이상 | `850` | 수신 지연 |
| `blue_observed.comms.packet_loss` | `ratio` | 0.0~1.0 | `0.12` | 패킷 손실률 |
| `blue_observed.comms.message_queue_depth` | `int` | 0 이상 | `12` | 처리 대기 메시지 수 |
| `blue_observed.comms.request_rate` | `float` | requests/second 또는 requests/round | `20` | 요청 빈도 |
| `blue_observed.comms.packet_interval_ms` | `int` | milliseconds, 0 이상 | `1000` | 관측된 평균 패킷 주기 |
| `blue_observed.comms.packet_interval_jitter_ms` | `int` | milliseconds, 0 이상 | `18` | 패킷 주기 흔들림 |
| `blue_observed.comms.packet_size_bytes` | `int` | bytes, 0 이상 | `96` | 관측 패킷 크기 |
| `blue_observed.comms.packet_size_variance` | `float` | bytes 기준 분산/변동량 | `6` | 패킷 크기 패턴 안정도 |
| `blue_observed.comms.ack_visible` | `bool` | true/false | `true` | ACK 채널 관찰 가능 여부 |
| `blue_observed.comms.ack_delay_ms` | `int` | milliseconds, 0 이상 | `210` | ACK 지연 |
| `blue_observed.comms.route_metadata_visible` | `bool` | true/false | `true` | routing/sender/channel 메타데이터 관찰 가능 여부 |
| `blue_observed.comms.state_update_dependency` | enum string | `LOW`, `MEDIUM`, `HIGH` | `"HIGH"` | 최신 상태 업데이트 의존도 |
| `blue_observed.comms.anti_replay_window_s` | `int` | seconds, 0 이상 | `180` | 허용되는 replay 방지 시간창 추정 |
| `blue_observed.comms.heartbeat_interval_ms` | `int` | milliseconds, 0 이상 | `1000` | 정상 heartbeat 주기 |
| `blue_observed.comms.heartbeat_gap_ms` | `int` | milliseconds, 0 이상 | `0` | 최근 heartbeat 공백 |
| `blue_observed.comms.crypto_profile.algorithm` | enum/string | 구현별 명칭 | `"AEAD_SIM"` | 암호 방식 추정/시뮬레이션 명칭 |
| `blue_observed.comms.crypto_profile.nonce_reuse_suspected` | `bool` | true/false | `false` | nonce 재사용 의심 단서 |
| `blue_observed.comms.crypto_profile.weak_cipher_hint` | `bool` | true/false | `false` | 약한 암호 설정 의심 단서 |

## 4. Mission Runtime / Defense Field Formats

Current availability budget rule: `availability_recovery` is kept as a backward-compatible
log field name, but the active algorithm is `round_episode_budget_reset_v1`.
`availability_recovery_applied` and `trust_recovery_applied` are `0.0`; the
round starts from `defense_runtime.episode_initial_budget` so availability
attrition is scoped to one round-level combat episode.

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `mission.availability` | `ratio` | 0.0~1.0 | `0.78` | 임무 가용성 |
| `mission.trust_budget` | `ratio` | 0.0~1.0 | `0.64` | 남은 신뢰/방어 예산 |
| `defense_runtime.active_defense_slots` | `int` | 0 이상 | `2` | 동시 방어 작업 슬롯 수 |
| `defense_runtime.active_defenses` | array | defense object list | `[]` | 실행 중 방어 작업 |
| `defense_runtime.pending_defenses` | array | defense object list | `[]` | 대기 중 방어 작업 |
| `defense_runtime.telemetry_axis_sensitivity.telemetry_command_confusion` | ratio | 0.80~1.30 | `1.05` | Blue가 telemetry command-confusion threat confidence에 곱하는 축별 민감도 |
| `defense_runtime.telemetry_axis_threshold.stale_state_acceptance` | ratio | 0.20~0.75 | `0.32` | Blue가 stale-state 축 feedback에서 사용하는 축별 임계값 |
| `defense_runtime.telemetry_axis_feedback_counts.*.missed_axis` | int | 0 이상 | `3` | scorer가 본 dominant telemetry 축을 Blue threat tags가 직접 짚지 못한 횟수 |
| `defense_runtime.availability_recovery.algorithm` | string | model id | `"blue_availability_recovery_v2"` | Blue recovery 계산 모델 |
| `defense_runtime.availability_recovery.maintenance_cycle` | `bool` | true/false | `true` | 정비/재검증 회복 주기 여부 |
| `defense_runtime.availability_recovery.previous_active_defense_cost` | `ratio` | 0.0~1.0 | `0.18` | 직전 active defense availability cost |
| `defense_runtime.availability_recovery.fatigue_penalty` | `ratio` | 0.0~1.0 | `0.036` | 직전 방어 비용으로 인해 줄어든 회복량 |
| `defense_runtime.availability_recovery.availability_recovery_applied` | `ratio` | 0.0~1.0 | `0.124` | 실제 적용된 availability 회복량 |
| `defense_runtime.availability_recovery.trust_recovery_applied` | `ratio` | 0.0~1.0 | `0.091` | 실제 적용된 trust_budget 회복량 |

Defense object 형식:

```json
{
  "action": "QUARANTINE_FIELD",
  "target": "blue_observed.telemetry.battery_percent",
  "priority": 2,
  "duration_ticks": 1,
  "availability_cost": 0.05,
  "status": "ACTIVE"
}
```

| 필드 | 타입 | 단위/범위 | 예시 |
|---|---|---|---|
| `action` | enum string | `QUARANTINE_FIELD`, `HOLD_COMMAND`, `FALLBACK_TO_TRUSTED_STATE`, `REQUEST_REVALIDATION`, `ENTER_SAFE_MODE`, `RESTORE_LAST_KNOWN_GOOD` | `"QUARANTINE_FIELD"` |
| `target` | string path | schema path | `"blue_observed.telemetry.battery_percent"` |
| `priority` | `int` | 높을수록 우선 | `2` |
| `duration_ticks` | `int` | round count | `1` |
| `availability_cost` | `ratio` | 0.0~1.0 | `0.05` |
| `status` | enum string | `PENDING`, `ACTIVE`, `DONE`, `FAILED` | `"ACTIVE"` |

## 5. Attack / Detection / Score Field Formats

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `attack.name` | enum string | attack catalog name | `"TELEMETRY_FDI"` | 공격명 |
| `attack.feasibility` | enum string | `real`, `abstracted`, `out_of_scope` | `"real"` | 현실성 분류 |
| `attack.weight` | `float` | 0 이상 | `5.0` | 선택 가중치 |
| `attack.preferred_tags` | array of tag | tag list | `["GNSS_PRIMARY"]` | 선호 상황 태그 |
| `attack.target_domain` | enum string | `telemetry`, `mission`, `command`, `comms`, `navigation` | `"telemetry"` | 공격 대상 영역 |
| `threat.target` | enum string | target domain | `"telemetry"` | 탐지 대상 영역 |
| `threat.confidence` | `ratio` | 0.0~1.0 | `0.82` | 탐지 신뢰도 |
| `attack_success` | `bool` | true/false | `true` | 공격 성공 여부 |
| `detection_success` | `bool` | true/false | `false` | 탐지 성공 여부 |
| `false_positive` | `bool` | true/false | `false` | 오탐 여부 |
| `recovery_success` | `bool` | true/false | `true` | 복구 성공 여부 |
| `containment_score` | `ratio` | 0.0~1.0 | `0.62` | Blue가 공격 effect를 완전 복구 전 단계에서 억제한 정도 |
| `winner` | enum string | `RED_BREACH`, `RED_ATTRITION`, `BLUE`, `BLUE_RECOVERY`, `DRAW` | `"RED_BREACH"` | 라운드 판정 |
| `winner_side` | enum string | `RED`, `BLUE`, `DRAW` | `"RED"` | frontend/report display용 승패 주체 |
| `winner_detail` | enum string | `BREACH`, `ATTRITION`, `PARTIAL_BREACH`, `DETECTION`, `CONTAINMENT`, `PARTIAL_CONTAINMENT`, `RECOVERY`, `NO_EFFECT`, `FALSE_POSITIVE` | `"BREACH"` | outcome 세부 결과 |
| `outcome_reason` | string | reason code | `"undetected_attack_achieved_selected_goal"` | 결과 라벨 부여 근거 |

Containment evidence extension:

| field | type | range | example | description |
|---|---|---|---|---|
| `evidence.containment.effect_id` | string | effect id | `EFFECT_COMMAND_STALE_ACCEPTANCE` | Blue가 억제하려 한 cyber-effect |
| `evidence.containment.pressure_before` | ratio | 0.0~1.0 | `0.72` | 방어 전 effect pressure |
| `evidence.containment.pressure_after` | ratio | 0.0~1.0 | `0.18` | 방어 후 effect pressure |
| `evidence.containment.effect_reduction_ratio` | ratio | 0.0~1.0 | `0.75` | effect pressure 감소율 |
| `evidence.containment.action_coverage` | ratio | 0.0~1.0 | `1.0` | contract에 맞는 action 적용 정도 |
| `evidence.containment.operational_safety` | ratio | 0.0~1.0 | `0.84` | availability/trust_budget 보존 정도 |
| `evidence.containment.containment_level` | enum string | level | `CONTAINED` | `RECOVERED`, `CONTAINED`, `PARTIAL_CONTAINMENT`, `UNCONTAINED` |

Attrition evidence extension:

| field | type | range | example | description |
|---|---|---|---|---|
| `evidence.attrition.red_round_attack_cost` | ratio | 0.0~1.0 | `0.18` | Red simulated cost accumulated in the combat round |
| `evidence.attrition.round_defense_cost` | ratio | 0.0~1.0 | `0.31` | Blue defense availability cost accumulated in the combat round |
| `evidence.attrition.cost_effective` | bool | true/false | `true` | Whether Blue defense cost meaningfully exceeds Red cost |

Summary telemetry diversity extension:

| field | type | range | example | description |
|---|---|---|---|---|
| `summary.avg_telemetry_learning_signal` | ratio | 0.0~1.0 | `0.28` | 평균 telemetry split-channel 학습 신호 |
| `summary.telemetry_learning_axis_entropy` | float | 0 이상 | `1.58` | active telemetry axis 분포 entropy |
| `summary.telemetry_dominant_axis_entropy` | float | 0 이상 | `0.0` | dominant telemetry axis만 본 분포 entropy |
| `summary.telemetry_policy_diversity_contribution.dominant_axis_counts` | object | counts | `{...}` | 어떤 telemetry 축이 Red/Blue 학습에 주로 기여했는지 |

Red tactic object 형식:

```json
{
  "strategy": "ack_confusion",
  "selector": "tag_scored_tactic_policy",
  "matched_tags": ["ACK_CHANNEL_VISIBLE", "ACK_TIMING_ANOMALY"],
  "score": 8.432,
  "score_breakdown": {
    "base_score": 1.7,
    "impact": 2.0,
    "tag_bonus": 5.782,
    "detectability_penalty": 0.65,
    "execution_cost": 0.4
  }
}
```

| 필드 | 타입 | 예시 | 의미 |
|---|---|---|---|
| `strategy` | enum string | `"replay"` | 선택된 세부 tactic |
| `selector` | string | `"tag_scored_tactic_policy"` | 선택 방식 |
| `matched_tags` | array of tag | `["SEQUENCE_VISIBLE"]` | tactic 선택 근거 태그 |
| `score` | `float` | `7.875` | tactic 최종 점수 |
| `score_breakdown` | object | `{}` | 점수 계산 근거 |
| `candidate_scores` | array | `[]` | 비교된 tactic 후보 점수표 |

## 6. Situation Tag Format

태그는 대문자 snake case 문자열 배열로 저장한다.

```json
{
  "situation_tags": [
    "GNSS_DEGRADED",
    "SEQUENCE_REGRESSION",
    "REPLAY_SUSPECTED"
  ]
}
```

| 태그 | 타입 | 예시 |
|---|---|---|
| `GNSS_DEGRADED` | string enum | `"GNSS_DEGRADED"` |
| `SEQUENCE_REGRESSION` | string enum | `"SEQUENCE_REGRESSION"` |
| `SEQUENCE_VISIBLE` | string enum | `"SEQUENCE_VISIBLE"` |
| `ACK_CHANNEL_VISIBLE` | string enum | `"ACK_CHANNEL_VISIBLE"` |
| `PACKET_INTERVAL_ANOMALY` | string enum | `"PACKET_INTERVAL_ANOMALY"` |
| `TELEMETRY_CONFLICT` | string enum | `"TELEMETRY_CONFLICT"` |
| `MISSION_PRIORITY_CHANGED` | string enum | `"MISSION_PRIORITY_CHANGED"` |

상세 태그는 Red AI의 Situation Tagger와 Decision Logger가 사용한다.

```json
{
  "tag": "SEQUENCE_VISIBLE",
  "confidence": 0.91,
  "evidence": ["c2_message.sequence_visible=True", "c2_message.sequence_number"],
  "meaning": "message order information can be observed"
}
```

| 필드 | 타입 | 예시 | 의미 |
|---|---|---|---|
| `tag` | string enum | `"SEQUENCE_VISIBLE"` | 상황 태그명 |
| `confidence` | `ratio` | `0.91` | 태그 판단 신뢰도 |
| `evidence` | array of string | `["comms.ack_visible=True"]` | 태그를 만든 observed 경로와 값 |
| `meaning` | string | `"message order information can be observed"` | 공격/방어 판단에서의 의미 |

## 7. Log Field Formats

각 라운드 로그는 JSONL 한 줄로 저장한다.

```json
{
  "round": 3,
  "seed": 42,
  "prev_hash": "a0b1...",
  "this_hash": "f9e8...",
  "situation_tags": ["ACK_TIMING_ANOMALY"],
  "attack": {"name": "TELEMETRY_FDI", "target_domain": "telemetry"},
  "threats": [{"target": "telemetry", "confidence": 0.82}],
  "score": {"winner": "BLUE", "attack_success": true, "detection_success": true}
}
```

| 경로 | 타입 | 형식 | 예시 | 의미 |
|---|---|---|---|---|
| `round` | `int` | 1 이상 | `3` | 라운드 번호 |
| `seed` | `int` | 0 이상 | `42` | 재현용 seed |
| `prev_hash` | string | hex digest | `"a0b1..."` | 이전 로그 해시 |
| `this_hash` | string | hex digest | `"f9e8..."` | 현재 로그 해시 |
| `decision_log` | array | decision object list | `[]` | 에이전트 판단/학습 기록 |

Decision log object 형식:

```json
{
  "agent": "RedAgent",
  "event": "weight_update",
  "reason": "attack_detected",
  "before": 5.0,
  "after": 4.0
}
```

| 필드 | 타입 | 예시 |
|---|---|---|
| `agent` | enum string | `"RedAgent"`, `"BlueAgent"` |
| `event` | enum string | `"weight_update"`, `"threshold_update"`, `"action_selected"` |
| `reason` | string | `"attack_detected"` |
| `before` | number/string/object | `5.0` |
| `after` | number/string/object | `4.0` |

Blue readiness gate fields:

| field | type | example | description |
|---|---|---|---|
| `update_mode.planned_red_update_enabled` | bool | `true` | Whether the schedule intended to update Red |
| `update_mode.red_update_enabled` | bool | `false` | Whether Red was actually updated after readiness gating |
| `update_mode.blue_readiness_gate.ready` | bool | `false` | Whether recent Blue defense score passed the gate |
| `update_mode.blue_readiness_gate.success_rate` | ratio | `0.42` | Rolling average of continuous Blue defense score |
| `update_mode.blue_readiness_gate.successes` | int | `8` | Number of samples whose defense score exceeded the threshold |
| `update_mode.blue_readiness_gate.threshold` | ratio | `0.40` | Minimum rolling defense score for opening Red updates |
| `update_mode.blue_readiness_gate.algorithm` | string | `"rolling_blue_containment_readiness_gate_v2"` | Readiness gate scoring model |
