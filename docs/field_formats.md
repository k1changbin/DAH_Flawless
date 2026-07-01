# Field Format Reference

이 문서는 `world`, `blue_observed`, `tag`, `score/log`에 들어가는 각 값의 형식, 단위, 범위, 예시를 정의한다. 구현할 때는 이 표를 기준으로 dataclass 또는 JSON schema를 만든다.

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

## 2. World Field Formats

### 2.1 Time

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.time.true_timestamp` | `timestamp` | Unix seconds | `1710001200` | 실제 기준 시간 |
| `world.time.round` | `int` | 0 이상 | `3` | 시뮬레이션 라운드 |

### 2.2 Environment

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.environment.weather` | enum string | `CLEAR`, `RAIN`, `FOG`, `WIND`, `STORM` | `"CLEAR"` | 실제 기상 |
| `world.environment.terrain` | enum string | `OPEN`, `URBAN`, `LOW_MOUNTAIN`, `COASTAL` | `"LOW_MOUNTAIN"` | 실제 지형 |
| `world.environment.rf_noise_level` | `ratio` | 0.0~1.0 | `0.21` | 실제 전파 잡음 수준 |
| `world.environment.gnss_interference` | enum string | `NONE`, `JAMMING`, `SPOOFING`, `MULTIPATH`, `UNKNOWN` | `"NONE"` | 실제 GNSS 간섭 상태 |

### 2.3 UAV

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.uav.position.lat` | `float` | -90~90 degrees | `37.123` | 실제 위도 |
| `world.uav.position.lon` | `float` | -180~180 degrees | `127.456` | 실제 경도 |
| `world.uav.position.altitude_m` | `float` | meters | `180` | 실제 고도 |
| `world.uav.speed_mps` | `float` | meters/second, 0 이상 | `42` | 실제 속도 |
| `world.uav.heading_deg` | `float` | 0~359.999 degrees | `91` | 실제 진행 방향 |
| `world.uav.battery_percent` | `percent` | 0~100 | `20` | 실제 배터리 잔량 |
| `world.uav.battery_drain_rate` | `float` | percent/round 또는 percent/min | `1.0` | 실제 배터리 소모율 |
| `world.uav.motor_status` | enum string | `OK`, `DEGRADED`, `FAULT`, `UNKNOWN` | `"FAULT"` | 실제 모터 상태 |
| `world.uav.imu_accel.x` | `float` | m/s^2 | `0.1` | 실제 x축 가속도 |
| `world.uav.imu_accel.y` | `float` | m/s^2 | `0.0` | 실제 y축 가속도 |
| `world.uav.imu_accel.z` | `float` | m/s^2 | `9.8` | 실제 z축 가속도 |

### 2.4 Mission

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.mission.current_area` | enum string | `A`, `B`, `C` | `"A"` | 실제 현재 임무 구역 |
| `world.mission.area_priority.A` | `ratio` | 0.0~1.0 | `0.9` | A구역 실제 우선순위 |
| `world.mission.area_priority.B` | `ratio` | 0.0~1.0 | `0.4` | B구역 실제 우선순위 |
| `world.mission.area_priority.C` | `ratio` | 0.0~1.0 | `0.2` | C구역 실제 우선순위 |
| `world.mission.return_required` | `bool` | true/false | `true` | 실제 복귀 필요 여부 |

### 2.5 Command

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `world.command.expected_sequence_number` | `int` | 0 이상, 단조 증가 | `1021` | 정상적으로 기대되는 다음 명령 번호 |
| `world.command.last_valid_command` | enum string | `CONTINUE_MISSION`, `RETURN_TO_BASE`, `HOLD_POSITION`, `ENTER_SAFE_MODE` | `"RETURN_TO_BASE"` | 마지막 정상 명령 |

## 3. Blue Observed Field Formats

### 3.1 Time

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.time.received_timestamp` | `timestamp` | Unix seconds | `1710000800` | Blue가 수신한 메시지 시간 |
| `blue_observed.time.local_clock_offset_ms` | `int` | milliseconds | `430` | 로컬 시계 오프셋 |

### 3.2 Telemetry

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `blue_observed.telemetry.battery_percent` | `percent` | 0~100 | `82` | Blue가 받은 배터리 값 |
| `blue_observed.telemetry.battery_drain_rate` | `float` | percent/round 또는 percent/min | `1.0` | Blue가 받은 배터리 소모율 |
| `blue_observed.telemetry.motor_status` | enum string | `OK`, `DEGRADED`, `FAULT`, `UNKNOWN` | `"OK"` | Blue가 받은 모터 상태 |
| `blue_observed.telemetry.altitude_m` | `float` | meters | `180` | Blue가 받은 고도 |
| `blue_observed.telemetry.speed_mps` | `float` | meters/second | `42` | Blue가 받은 속도 |
| `blue_observed.telemetry.heading_deg` | `float` | 0~359.999 degrees | `91` | Blue가 받은 진행 방향 |

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
| `blue_observed.c2_message.checksum_valid` | `bool` | true/false | `true` | checksum 검증 결과 |
| `blue_observed.c2_message.signature_present` | `bool` | true/false | `true` | 메시지 서명 존재 여부 |
| `blue_observed.c2_message.auth_valid` | `bool` | true/false | `true` | 인증/서명 검증 결과 |

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

## 4. Mission Runtime / Defense Field Formats

| 경로 | 타입 | 단위/범위 | 예시 | 의미 |
|---|---|---|---|---|
| `mission.availability` | `ratio` | 0.0~1.0 | `0.78` | 임무 가용성 |
| `mission.trust_budget` | `ratio` | 0.0~1.0 | `0.64` | 남은 신뢰/방어 예산 |
| `defense_runtime.active_defense_slots` | `int` | 0 이상 | `2` | 동시 방어 작업 슬롯 수 |
| `defense_runtime.active_defenses` | array | defense object list | `[]` | 실행 중 방어 작업 |
| `defense_runtime.pending_defenses` | array | defense object list | `[]` | 대기 중 방어 작업 |

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
| `winner` | enum string | `RED_BREACH`, `RED_ATTRITION`, `BLUE`, `BLUE_RECOVERY`, `DRAW` | `"RED_BREACH"` | 라운드 판정 |

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
| `TELEMETRY_CONFLICT` | string enum | `"TELEMETRY_CONFLICT"` |
| `MISSION_PRIORITY_CHANGED` | string enum | `"MISSION_PRIORITY_CHANGED"` |

## 7. Log Field Formats

각 라운드 로그는 JSONL 한 줄로 저장한다.

```json
{
  "round": 3,
  "seed": 42,
  "prev_hash": "a0b1...",
  "this_hash": "f9e8...",
  "situation_tags": ["TELEMETRY_CONFLICT"],
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

