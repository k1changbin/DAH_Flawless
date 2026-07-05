# Mutation Policy

이 문서는 Red AI가 시뮬레이션 안에서 Blue의 observe를 어디까지 변조할 수 있는지 정의한다. 기준 설정 파일은 [configs/mutation_policy.yaml](../configs/mutation_policy.yaml)이다.

## 1. 목적

Mutation Policy는 Red AI를 "아무 값이나 바꾸는 모델"이 아니라, 허용된 observe 표면과 허용된 변조 폭 안에서만 움직이는 모델로 제한한다.

```text
Red request
-> Mutation Policy permission check
-> max delta clamp
-> Mutation Engine applies safe simulated mutation
-> Blue detects/contains/recovers
-> Scorer judges effect and cost
```

이 정책은 실제 RF 송신, 실제 API 공격, credential 탈취, malware, exploit payload를 다루지 않는다. 여기서 말하는 mutation은 Blue가 받는 관측값을 시뮬레이션 안에서 오염시키는 안전한 값 변형이다.

## 2. Observe 경계

Blue observe는 두 종류다.

| observe | 의미 | Red 직접 변조 |
|---|---|---|
| `internal_observe` | 내부 센서, 로컬 상태, 내부 health, inertial estimate | 금지 |
| `external_observe` | 외부 C2, GNSS, SATCOM/RF, 원격 telemetry, mission/target report | 허용 |

현재 MVP 코드는 호환성을 위해 `blue_observed.telemetry`, `blue_observed.c2_message` 같은 flat key를 유지한다. 이 flat key는 `blue_observed.external_observe.*`의 alias로 본다.

## 3. Profile

| profile | 용도 | 기본 학습 사용 |
|---|---|---|
| `stealth` | 탐지 경계 근처의 작은 변조 | 사용 |
| `aggressive` | 공격 효과를 키우는 중간/큰 변조 | 사용 |
| `loud_demo` | 보고서/시연/Blue hard-case 테스트용 명확한 변조 | 기본 학습 금지 |

`loud_demo`는 현재 코드의 `battery_percent = 82`, `timestamp_delta_s = -400` 같은 큰 변조를 설명하기 위한 profile이다. 현재 MVP 기본값은 `aggressive`이며, `stealth`는 낮은 폭의 경계 탐색이나 adaptive retry에 사용한다.

## 4. 금지 규칙

아래는 항상 금지한다.

- `blue_observed.internal_observe.*` 직접 변조
- `state["world"]` 또는 `scorer_truth` 변조
- `raw_world` 변조
- 실제 RF/API 공격 절차 생성
- exploit payload, malware, credential 탈취 방식 생성
- `auth_valid=false`를 `true`로 위조
- `signature_present=false`를 `true`로 위조
- 암호화 payload를 복호화한 것처럼 `payload_visible=false`를 `true`로 변경

인증/서명 관련 값은 실패하거나 누락되는 방향으로만 모델링한다. 성공적인 위조는 이 대회 시뮬레이션 범위 밖이다.

## 5. 허용 필드 요약

| domain | 대표 필드 | stealth | aggressive | loud_demo |
|---|---|---:|---:|---:|
| C2 latency | `external_observe.comms.latency_ms` | +50~250ms | +300~1200ms | +1200~1800ms |
| C2 jitter | `external_observe.comms.packet_interval_jitter_ms` | +50~150ms | +300~700ms | +700~1000ms |
| C2 loss | `external_observe.comms.packet_loss` | +0.02~0.05, max 0.08 | 0.10~0.25 | 0.25~0.40 |
| heartbeat gap | `external_observe.comms.heartbeat_gap_ms` | 1~2 beat | 3~5 beat | 5~8 beat |
| sequence | `external_observe.c2_message.sequence_number` | -3~+3 | -12~+12 | -24~+24 |
| timestamp | `external_observe.time.received_timestamp` | -5~+5s | -60~+60s | -400~+400s |
| ACK sequence | `external_observe.c2_message.ack.sequence_number` | -1~+1 | -5~+5 | -10~+10 |
| ACK delay | `external_observe.comms.ack_delay_ms` | +100~300ms | +500~1200ms | +1200~1800ms |
| GNSS satellite | `external_observe.navigation.satellite_count` | -1~-2 | -3~-6 | -6~-8 |
| GNSS C/N0 | `external_observe.navigation.cn0_avg` | -2~-5 dBHz | -6~-12 dBHz | -12~-20 dBHz |
| GNSS HDOP | `external_observe.navigation.hdop` | +0.3~1.5 | +2~6 | +6~10 |
| battery | `external_observe.telemetry.battery_percent` | +/-8% | +/-25% | 0~100% hard case |
| battery rate | `external_observe.telemetry.battery_drain_rate` | +/-0.3 | +/-1.0 | +/-2.0 |
| motor status | `external_observe.telemetry.motor_status` | DEGRADED/UNKNOWN | any enum | any enum |
| motion telemetry | speed/heading/altitude | 10%, 5deg, 8m | 30%, 20deg, 30m | 50%, 45deg, 80m |
| mission priority | `external_observe.mission.area_priority` | per-area 0.15 | per-area 0.45 | per-area 0.80 |
| recommended area | `external_observe.mission.recommended_area` | low-margin only | medium-margin | any |

## 6. Blue 탐지와 연결

Mutation Policy는 Blue가 어떤 단서를 볼 수 있는지도 함께 설명한다.

| mutation group | Blue detection hints |
|---|---|
| latency/jitter/loss | `HIGH_LATENCY`, `PACKET_INTERVAL_ANOMALY`, `PACKET_LOSS_HIGH` |
| sequence/timestamp/replay | `SEQUENCE_REGRESSION`, `SEQUENCE_GAP`, `TIMESTAMP_SKEW`, `REPLAY_SUSPECTED` |
| ACK confusion | `ACK_TIMING_ANOMALY`, `SEQUENCE_GAP` |
| GNSS quality | `GNSS_DEGRADED`, `GNSS_INTERNAL_CONFLICT` |
| external telemetry | `TELEMETRY_CONFLICT`, `BATTERY_ENERGY_IMPOSSIBLE`, `IMU_TELEMETRY_DIVERGENCE` |
| mission belief | `MISSION_PRIORITY_CHANGED`, `MISSION_EVIDENCE_MISSING` |

Blue는 attack name을 맞히는 것이 아니라, internal observe와 external observe 사이의 정합성, history, 통신 metadata, mission context로 threat를 만든다.

## 7. Mutation Approval LLM

필요하면 Red 내부에 `Mutation Approval LLM`을 둔다. 단, 이 LLM은 **reviewer-only**다. 공격을 선택하거나, 변조값을 새로 만들거나, `blue_observed`를 직접 수정하거나, payload를 만드는 모델이 아니다. Attack Selector와 deterministic Mutation Policy가 만든 후보 mutation을 보고 `approve`, `clamp`, `reject`, `explain`만 수행한다.

권한 경계:

| 항목 | 허용 여부 |
|---|---|
| 후보 mutation 정책 검토 | 허용 |
| 허용 폭 초과 시 더 작은 값으로 clamp 권고 | 허용 |
| 금지 필드/금지 방향/안전 경계 위반 reject | 허용 |
| reject/approve 이유 설명 | 허용 |
| 공격 목표나 tactic 직접 선택 | 금지 |
| 새 target field 발명 또는 변조폭 증가 | 금지 |
| `blue_observed`, `internal_observe`, `state["world"]`, `raw_world` 직접 수정 | 금지 |
| 실제 RF/API 절차, exploit payload, malware, credential guidance 생성 | 금지 |

LLM 출력과 deterministic policy가 충돌하면 deterministic policy가 항상 이긴다. 최종 state 변경은 `Mutation Engine`만 수행한다.

입력 예:

```json
{
  "requested_mutation": "increase C2 ACK delay",
  "target_field": "blue_observed.external_observe.comms.ack_delay_ms",
  "profile": "stealth",
  "requested_delta_ms": 700,
  "reason": "probe ACK timing detector"
}
```

출력 예:

```json
{
  "approved": true,
  "clamped_delta": 300,
  "allowed_fields": ["blue_observed.external_observe.comms.ack_delay_ms"],
  "reason": "stealth profile allows only +100~300ms for ACK delay",
  "safety_boundary": "simulated external observe metadata only; no real RF/API instruction"
}
```

reject 예:

```json
{
  "approved": false,
  "reason": "request touches internal_observe directly",
  "allowed_fields": [],
  "safety_boundary": "internal observe is a Blue trust anchor"
}
```

## 8. 다음 구현 단계

현재 `Mutation Engine`은 값을 직접 쓰기 전에 `src/dah_flawless/attacks/mutation_policy.py`의 runtime policy를 거친다. 즉 핵심 공격 필드에 대한 Mutation Policy runtime enforcement가 시작됐다. profile별 max delta clamp, 금지 scope reject, enum allow-list 검사가 구현되어 있다. runtime policy는 `configs/mutation_policy.yaml`의 `field_policies`를 시작 시점에 읽어 적용한다. `aggressive`가 기본 profile이고, 기존 큰 시연값은 `loud_demo`에 격리되어 `--mutation-profile loud_demo`로만 명시적으로 사용한다.

현재 loader는 외부 PyYAML 의존성 없이 이 설정 파일에서 사용하는 YAML subset을 읽는다. 남은 확장 단계는 YAML parser 의존성을 도입하거나 schema validation을 추가해 설정 오류 메시지를 더 엄격하게 만드는 것이다.

```text
Attack Selector
-> proposed mutation intent
-> MutationPolicy lookup
-> optional Mutation Approval LLM reviewer
-> clamp/reject
-> Mutation Engine apply
-> mutation_log records profile, requested delta, clamped delta, policy id
```

필수 테스트:

- Red가 `internal_observe`를 직접 변조하려 하면 reject
- 허용 필드라도 profile max delta를 넘으면 clamp
- `loud_demo`는 기본 training mode에서 사용 금지
- `auth_valid`와 `signature_present`는 성공 위조 방향으로 변경 금지
- mutation log에 `policy_id`, `profile`, `requested_delta`, `applied_delta` 기록
