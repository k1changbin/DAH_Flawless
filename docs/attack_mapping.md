# Attack Mapping to Schema and Tags

이 문서는 공격 3종을 `world`, `blue_observed`, situation tag, Blue 방어 결과에 연결한다. 보고서 4.2 공격 시나리오와 5.2 Detect/Contain/Recover 표의 근거로 사용한다.

용어 주의: 이 문서의 `world`는 코드 호환 키 `state["world"]`이며 의미상 `scorer_truth`다. 현실 원천 신호인 `raw_world`는 `docs/raw_world_schema.md`를 기준으로 한다.

## 1. 공통 전제

```text
Red는 scorer_truth(state["world"])를 보지 않는다.
Red는 Blue 관제 AI가 받는 blue_observed의 일부 필드에만 영향을 준다.
Blue는 scorer_truth(state["world"])를 보지 않고 blue_observed 내부의 불변식 위반만 본다.
Scorer만 scorer_truth와 blue_observed를 비교해 성공 여부를 판정한다.
```

Observe v0.2 기준에서는 `blue_observed` 안에서도 `external_observe`만 Red의 직접 mutation 대상이다. 기존 `blue_observed.telemetry`, `blue_observed.c2_message` 같은 경로는 현재 MVP 호환용 flat view이며, 정책상 `blue_observed.external_observe.*`의 alias로 본다. 허용 필드와 max delta는 [mutation_policy.md](mutation_policy.md)와 [../configs/mutation_policy.yaml](../configs/mutation_policy.yaml)을 따른다.

## 2. TELEMETRY_FDI

| 필드 | 내용 |
|---|---|
| 공격명 | `TELEMETRY_FDI` |
| 목적 | UAV의 실제 상태와 다른 텔레메트리를 Blue AI가 믿게 함 |
| 조작 대상 | `blue_observed.telemetry.battery_percent`, `blue_observed.telemetry.motor_status` |
| world 기준 | `world.uav.battery_percent`, `world.uav.motor_status` |
| 예시 | loud_demo 기준: 실제 배터리 20%, 모터 고장인데 observed는 배터리 82%, 모터 OK |
| 탐지 태그 | `TELEMETRY_CONFLICT`, `BATTERY_MOTOR_INCONSISTENT` |
| Blue 탐지 단서 | 배터리 보고값, drain rate, 모터 상태, 임무 지속 판단 간 물리 정합성 위반 |
| 방어 | 오염 필드 격리, 마지막 정상 상태 fallback, 복귀 판단 복원 |

보고서 문장:

```text
TELEMETRY_FDI는 scorer_truth 기준 UAV 상태를 바꾸지 않고, Blue 관제 AI가 수신하는 텔레메트리 값을 오염시킨다. Blue는 scorer_truth를 알지 못하지만, 배터리 보고값과 소모율, 모터 상태의 물리 정합성 위반을 통해 조작 가능성을 탐지한다.
```

## 3. PRIORITY_POISONING

| 필드 | 내용 |
|---|---|
| 공격명 | `PRIORITY_POISONING` |
| 목적 | 관제 AI가 잘못된 임무 구역을 우선하도록 유도 |
| 조작 대상 | `blue_observed.mission.area_priority` |
| world 기준 | `world.mission.area_priority` |
| 예시 | 실제 A구역 우선순위 0.9, C구역 0.2인데 observed는 A 0.2, C 0.95 |
| 탐지 태그 | `MISSION_PRIORITY_CHANGED` |
| Blue 탐지 단서 | 우선순위 급변, 근거 센서/임무 이벤트 부족, 이전 라운드와의 불연속 |
| 방어 | priority update 격리, 기존 임무 목표 유지, 재검증 요청 |

보고서 문장:

```text
PRIORITY_POISONING은 임무 우선순위 입력을 오염시켜 관제 AI가 잘못된 표적 구역을 선택하게 만드는 공격이다. Blue는 우선순위 값의 급격한 변화와 이를 뒷받침하는 관측 근거의 부재를 탐지 단서로 사용한다.
```

## 4. TIME_DESYNC_REPLAY

| 필드 | 내용 |
|---|---|
| 공격명 | `TIME_DESYNC_REPLAY` |
| 목적 | 과거 명령 또는 상태를 최신 정보처럼 처리하게 함 |
| 조작 대상 | `blue_observed.c2_message.sequence_number`, `blue_observed.time.received_timestamp`, `blue_observed.c2_message.command`, `blue_observed.comms.ack_delay_ms`, `blue_observed.comms.heartbeat_gap_ms` |
| world 기준 | `world.command.expected_sequence_number`, `world.time.true_timestamp`, `world.command.last_valid_command` |
| 예시 | 정상 sequence는 1021인데 observed message는 1008, command는 `CONTINUE_MISSION` |
| 탐지 태그 | `SEQUENCE_REGRESSION`, `TIMESTAMP_SKEW`, `REPLAY_SUSPECTED`, `ACK_TIMING_ANOMALY`, `HEARTBEAT_GAP`, `PACKET_INTERVAL_ANOMALY` |
| Blue 탐지 단서 | sequence 역행, timestamp skew, ACK 인과관계 불일치, heartbeat 공백, packet interval 이상 |
| 방어 | 명령 보류, 마지막 정상 명령 유지, 재검증 요청 |

보고서 문장:

```text
TIME_DESYNC_REPLAY는 C2 메시지의 sequence number와 timestamp를 교란하여 과거 명령이 최신 명령처럼 처리되도록 유도한다. Blue는 메시지 내용 전체를 복호화하지 못하더라도 sequence, timestamp, ACK, heartbeat, packet interval 같은 통신 외형 메타데이터의 이상을 통해 replay/delay/drop 가능성을 탐지한다.
```

## 5. 공격별 Detect / Contain / Recover

| 공격 | Detect | Contain | Recover |
|---|---|---|---|
| `TELEMETRY_FDI` | 텔레메트리 물리 정합성 위반 | 오염 telemetry 필드 격리 | 마지막 정상 상태 fallback, 복귀 판단 |
| `PRIORITY_POISONING` | 우선순위 급변 + 근거 부족 | priority update 격리 | 원 임무 목표 유지, 재검증 |
| `TIME_DESYNC_REPLAY` | sequence 역행 + timestamp skew | command hold | 마지막 정상 명령 유지 |

## 6. Scorer 판정 기준

```text
attack_success
= 공격이 노린 target domain에서 scorer_truth와 blue_observed가 불일치하고,
  그 값이 격리 전에 임무 판단에 반영된 경우

detection_success
= 탐지 윈도 내 Blue가 공격 대상 domain에 해당하는 threat를 발화하고,
  confidence가 임계값 이상인 경우
```

예시:

```text
TELEMETRY_FDI:
world.uav.battery_percent = 20
blue_observed.telemetry.battery_percent = 82  # loud_demo example
Blue가 TELEMETRY_CONFLICT를 탐지하지 못하고 CONTINUE_MISSION을 선택
=> RED_BREACH
```

