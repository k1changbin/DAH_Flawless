# Stepwise Attack Scenarios

이 문서는 최근 `tmp/telemetry_mission_gate1000` 1000라운드 실행 결과를 기준으로, 현재 Red/Blue 공방에서 자주 선택되는 공격 시나리오를 step 단위로 설명한다.

주의: 아래 내용은 실제 침투 절차가 아니라 DAH_Flawless 시뮬레이터 안에서 `external_observe`를 제한적으로 변조하고 Blue가 이를 탐지/격리/복구하는 흐름이다.

## 1. 선택 빈도 요약

### 공격군 빈도

| 공격군 | 선택 횟수 | 의미 |
|---|---:|---|
| `TIME_DESYNC_REPLAY` | 477 | sequence, timestamp, ACK, latency, packet timing 같은 암호화 외부 metadata를 흔드는 공격군 |
| `TELEMETRY_FDI` | 298 | battery, motor status 등 외부 telemetry를 조금씩 오염시키는 false data injection 공격군 |
| `PRIORITY_POISONING` | 225 | mission priority, recommended area 등 임무 판단값을 오염시키는 공격군 |

### 목표 빈도

| 목표 | 선택 횟수 | 의미 |
|---|---:|---|
| `DETECTION_BOUNDARY_PROBE` | 251 | Blue 탐지 경계와 policy gate 반응을 확인하는 탐색 목표 |
| `COMMAND_STALE_ACCEPTANCE` | 145 | 오래된 command나 stale state를 Blue가 받아들이게 유도 |
| `WRONG_TARGET_SELECTION` | 144 | 잘못된 target/area가 더 중요해 보이도록 유도 |
| `ACK_CAUSAL_CONFUSION` | 143 | command와 ACK의 인과 관계를 흐리게 만듦 |
| `TELEMETRY_TRUST_EROSION` | 142 | telemetry 신뢰도를 깎거나 잘못된 안전 판단을 유도 |
| `CHANNEL_STATE_SUPPRESSION` | 141 | 채널 상태 이상을 숨기거나 늦게 보이게 만듦 |
| `BLUE_OVERDEFENSE_ATTRITION` | 34 | Blue가 과도한 방어 비용을 쓰도록 압박 |

### 전술 빈도

| 전술 | 선택 횟수 | 주로 연결되는 공격군 |
|---|---:|---|
| `replay` | 294 | `TIME_DESYNC_REPLAY` |
| `telemetry_false_data` | 183 | `TELEMETRY_FDI` |
| `metadata_poisoning` | 145 | `TIME_DESYNC_REPLAY` |
| `mission_priority_shift` | 119 | `PRIORITY_POISONING` |
| `confidence_spoofing` | 105 | `TELEMETRY_FDI` |
| `recommended_area_nudge` | 70 | `PRIORITY_POISONING` |
| `mission_confidence_shaping` | 36 | `PRIORITY_POISONING` |
| `ack_confusion` | 17 | `TIME_DESYNC_REPLAY` |

## 2. 시나리오 A: Replay 기반 stale command 유도

대표 라운드: 661
공격군: `TIME_DESYNC_REPLAY`
목표: `COMMAND_STALE_ACCEPTANCE`
전술: `replay`
결과: `BLUE / CONTAINMENT`
종료 이유: `red_abort`

### 의도

Red는 암호화 payload를 직접 보거나 바꾸는 대신, 외부에서 보이는 sequence, timestamp, ACK sequence, latency, ACK delay를 흔든다. 목표는 Blue가 오래된 command 상태를 최신 상태처럼 받아들이게 만드는 것이다.

### Step 흐름

| Step | Red 행동 | Blue 행동 | 진행 해석 |
|---:|---|---|---|
| 1 | `PROBE_BOUNDARY` | `INSPECT_INTERNAL` | Red가 sequence/timestamp/ACK/latency를 작게 건드린다. Blue는 내부 기준점과 비교하지만 아직 결정적 방어 action은 안 쓴다. |
| 2 | `ESCALATE_MUTATION` | `DEFEND` | Red가 ACK delay와 sequence lag를 크게 만든다. Blue는 `HOLD_COMMAND`, `QUARANTINE_FIELD`, `REQUEST_REVALIDATION`으로 command 사용을 멈추고 재검증한다. |
| 3 | `WAIT` | `INSPECT_INTERNAL` | Red는 잠깐 기다리며 Blue 반응을 본다. Blue는 내부 observe와 외부 command metadata의 일관성을 다시 확인한다. |
| 4-6 | `ESCALATE_MUTATION` 반복 | `DEFEND` 반복 | Red는 같은 방향으로 replay 압력을 유지한다. Blue는 계속 command hold, quarantine, revalidation을 수행한다. |
| 7-9 | `SWITCH_TACTIC` | `DEFEND` 또는 `INSPECT_INTERNAL` | Red는 delta를 바꿔 탐지 경계를 다시 탐색한다. Blue는 command domain 중심으로 containment를 유지한다. |
| 10 | `WAIT` | `INSPECT_INTERNAL` | Blue는 방어 action 없이도 command timing 이상을 탐지한다. |
| 11-13 | `ESCALATE_MUTATION`, `SLOW_DRIFT` | `DEFEND` | Red가 다시 강하게 밀어붙이지만 Blue의 command policy gate가 `command` domain을 제한하고 방어 action이 유지된다. |
| 14 | `ABORT` | `PASSIVE_MONITOR` | Red가 더 진행해도 효과가 낮다고 보고 중단한다. Blue는 containment 상태를 유지한다. |

### 관찰점

- 이 패턴은 현재 가장 자주 등장하는 조합이다.
- Blue는 `HOLD_COMMAND`를 통해 stale command가 임무 판단에 반영되는 것을 막는다.
- Red가 성공하려면 단순히 sequence를 늦추는 것만으로는 부족하고, Blue의 내부 command anchor와 history consistency까지 동시에 흔들어야 한다.

## 3. 시나리오 B: Metadata poisoning 기반 channel suppression

대표 라운드: 20
공격군: `TIME_DESYNC_REPLAY`
목표: `CHANNEL_STATE_SUPPRESSION`
전술: `metadata_poisoning`
결과: `BLUE / PARTIAL_CONTAINMENT`
종료 이유: `blue_recovered_final_attack`

### 의도

Red는 payload 내용이 암호화되어 있다고 가정하고, link metadata만 사용한다. latency, ACK delay, packet timing, heartbeat gap 주변 값을 흔들어 실제 채널 이상을 정상적인 지연처럼 보이게 만들려 한다.

### Step 흐름

| Step | Red 행동 | Blue 행동 | 진행 해석 |
|---:|---|---|---|
| 1 | `PROBE_BOUNDARY` | `INSPECT_INTERNAL` | 작은 ACK delay와 latency 변화로 Blue의 민감도를 확인한다. |
| 2 | `ESCALATE_MUTATION` | `DEFEND` | Blue가 timing 이상을 command/channel 위협으로 판단하고 `HOLD_COMMAND`, `QUARANTINE_FIELD`, `REQUEST_REVALIDATION`을 적용한다. |
| 3 | `WAIT` | `INSPECT_INTERNAL` | Red는 방어 후 잔여 효과를 본다. Blue는 내부 상태와 외부 metadata 차이를 재확인한다. |
| 4-5 | `ESCALATE_MUTATION`, `WAIT` | `DEFEND`, `INSPECT_INTERNAL` | Red는 다시 지연을 키우고, Blue는 반복적으로 검토한다. |
| 6-8 | `SWITCH_TACTIC` 반복 | `DEFEND` 반복 | Red는 ACK sequence와 latency delta 조합을 바꾸며 Blue 방어 비용을 유발한다. |
| 9-10 | `SLOW_DRIFT` | `DEFEND` | 큰 폭이 아니라 서서히 흔드는 방향으로 전환한다. Blue는 계속 방어하지만 완전 복구보다는 partial containment에 머문다. |
| 11 | `FINALIZE_ATTACK` | `PASSIVE_MONITOR` | 최종적으로 Blue가 부분 격리와 제한 사용으로 피해를 줄인다. |

### 관찰점

- 이 공격은 "안 보이는 payload" 대신 "보이는 metadata"를 이용하는 구조라 우리 설계 방향과 잘 맞는다.
- 다만 Blue가 command freshness, ACK causal check, policy gate를 같이 쓰면 breach보다는 partial containment로 끝나는 경우가 많다.

## 4. 시나리오 C: Telemetry false data로 배터리 신뢰도 오염

대표 라운드: 378
공격군: `TELEMETRY_FDI`
목표: `TELEMETRY_TRUST_EROSION`
전술: `telemetry_false_data`
결과: `BLUE / CONTAINMENT`
종료 이유: `red_finalized_detected`

### 의도

Red는 `telemetry.battery_percent`를 조금씩 바꿔 Blue가 실제보다 안전하다고 믿게 만들거나, 반대로 telemetry 자체를 못 믿게 만들려 한다.

### Step 흐름

| Step | Red 행동 | Blue 행동 | 진행 해석 |
|---:|---|---|---|
| 1 | `PROBE_BOUNDARY` | `WAIT` | Red가 battery 값을 작게 건드린다. Blue는 아직 움직이지 않는다. 이 순간 step score상으로는 breach 가능성이 잠깐 생긴다. |
| 2-4 | `SLOW_DRIFT`, `SWITCH_TACTIC` | `INSPECT_INTERNAL` | Blue가 내부 배터리/모터/드레인율 anchor와 외부 telemetry를 비교하기 시작한다. |
| 5-9 | `ESCALATE_MUTATION` 반복 | `INSPECT_INTERNAL` 반복 | Red가 delta를 키우지만, Blue는 telemetry domain 위협을 계속 감지한다. policy gate는 `telemetry`를 제한한다. |
| 10-12 | `ESCALATE_MUTATION`, `SLOW_DRIFT` | `DEFEND` | Blue가 `OBSERVE_DOMAIN`, `REQUEST_REVALIDATION`으로 telemetry를 재검증한다. |
| 13 | `SLOW_DRIFT` | `DEFEND` | Blue가 `QUARANTINE_FIELD`, `FALLBACK_TO_TRUSTED_STATE`를 적용해 외부 telemetry 대신 내부 기준점으로 fallback한다. |
| 14 | `SWITCH_TACTIC` | `PASSIVE_MONITOR` | Red가 tactic을 바꾸지만 Blue는 이미 복구/containment 상태다. |
| 15-16 | `SLOW_DRIFT`, `FINALIZE_ATTACK` | `INSPECT_INTERNAL` | Blue가 최종 공격을 탐지한 상태로 끝난다. |

### 관찰점

- `TELEMETRY_FDI`는 공격 성공률 자체는 높아 보일 수 있지만, Blue가 내부 observe를 trust anchor로 쓰면 최종 breach는 어렵다.
- 현재 Blue는 battery/motor/drain-rate 정합성 검사에 강하다.
- Red 입장에서는 단일 battery 값만 바꾸기보다 motor status, energy drain, mission urgency를 더 정교하게 묶어야 실제 임무 영향이 커진다.

## 5. 시나리오 D: Mission priority poisoning으로 wrong target 유도

대표 라운드: 345
공격군: `PRIORITY_POISONING`
목표: `WRONG_TARGET_SELECTION`
전술: `recommended_area_nudge`
결과: `RED_ATTRITION / ATTRITION`
종료 이유: `red_attrition_success`

### 의도

Red는 mission priority에서 A의 점수를 낮추고 C의 점수를 올리거나, `recommended_area`를 조금씩 흔들어 Blue가 잘못된 area를 더 중요하다고 판단하게 만들려 한다.

### Step 흐름

| Step | Red 행동 | Blue 행동 | 진행 해석 |
|---:|---|---|---|
| 1 | `PROBE_BOUNDARY` | `RAISE_SUSPICION` | Blue가 초반부터 mission domain 이상을 의심한다. policy gate가 `mission` 사용권한을 낮춘다. |
| 2 | `SWITCH_TACTIC` | `RAISE_SUSPICION` | Red는 priority drift 모양을 바꾸지만 Blue 의심은 유지된다. |
| 3-4 | `SWITCH_TACTIC`, `SLOW_DRIFT` | `DEFEND` | Blue가 `OBSERVE_DOMAIN`, `REQUEST_REVALIDATION`으로 mission observe를 재확인한다. |
| 5 | `SLOW_DRIFT` | `INSPECT_INTERNAL` | Blue는 내부/외부 mission 판단 차이를 검사한다. |
| 6 | `ESCALATE_MUTATION` | `DEFEND` | Red가 priority shift를 키운다. Blue는 mission 방어와 channel timing 방어를 함께 수행해 비용이 커진다. |
| 7 | `SLOW_DRIFT` | `DEFEND` | Blue가 `QUARANTINE_FIELD`, `REQUEST_REVALIDATION`으로 mission field를 격리한다. |
| 8-14 | tactic 변경과 escalation 반복 | `INSPECT_INTERNAL`, `DEFEND` 반복 | Blue는 계속 막지만 방어 action이 누적된다. |
| 15 | `ESCALATE_MUTATION` | `DEFEND` | breach는 아니지만 Blue 방어 비용과 availability 감소가 커져 `RED_ATTRITION`으로 판정된다. |

### 관찰점

- 이 라운드는 Red가 Blue를 뚫은 것이 아니라, Blue가 막는 과정에서 너무 많은 비용을 쓰게 만든 사례다.
- 보고서에서는 "공격 성공"과 "방어 자원 소모 성공"을 구분해서 설명해야 한다.
- 현재 개선 방향은 Blue가 매번 무거운 `DEFEND`를 쓰지 않고, 낮은 비용의 `DOWNGRADE`, `MONITOR`, `REVALIDATE`를 더 잘 섞도록 하는 것이다.

## 6. 시나리오 E: Telemetry boundary probe로 Blue over-defense 유도

대표 라운드: 89
공격군: `TELEMETRY_FDI`
목표: `DETECTION_BOUNDARY_PROBE`
전술: `telemetry_false_data`
결과: `RED_ATTRITION / ATTRITION`
종료 이유: `red_attrition_success`

### 의도

Red는 telemetry 값을 계속 바꾸면서 Blue가 어디서 탐지하고 어디서 방어 action을 쓰는지 확인한다. 최종 목표는 breach가 아니라 Blue가 반복적으로 비용 큰 방어를 쓰게 만드는 것이다.

### Step 흐름

| Step | Red 행동 | Blue 행동 | 진행 해석 |
|---:|---|---|---|
| 1 | `PROBE_BOUNDARY` | `WAIT` | 작은 battery delta로 탐지 경계를 찔러본다. |
| 2 | `SLOW_DRIFT` | `RAISE_SUSPICION` | Blue가 battery/drain/motor 정합성 이상을 의심한다. |
| 3-4 | `SWITCH_TACTIC` | `DEFEND` | Blue는 `OBSERVE_DOMAIN`, `REQUEST_REVALIDATION`을 쓴다. |
| 5 | `SLOW_DRIFT` | `DEFEND` | Blue가 `QUARANTINE_FIELD`, `FALLBACK_TO_TRUSTED_STATE`, channel timing reset까지 같이 수행한다. 이때 containment는 높지만 비용도 커진다. |
| 6 | `SWITCH_TACTIC` | `PASSIVE_MONITOR` | Red는 잠깐 tactic을 바꾸고 Blue는 모니터링으로 내려간다. |
| 7-15 | `SLOW_DRIFT` 반복 | `WAIT`, `INSPECT_INTERNAL`, `DEFEND` 반복 | Blue는 대부분 탐지하고 containment도 높지만, defense cost가 누적된다. 마지막에 `RED_ATTRITION`으로 판정된다. |

### 관찰점

- `DETECTION_BOUNDARY_PROBE`가 많이 선택되는 이유는 이것이 단순 오류가 아니라 Red가 Blue의 방어 경계와 비용 구조를 학습하는 탐색 행동이기 때문이다.
- 다만 이 목표가 너무 강하면 Red가 "실제 breach"보다 "방어 비용 유발"만 선호할 수 있으므로, 보고서에서는 attrition과 breach를 다른 성공 유형으로 분리해야 한다.

## 7. 시나리오 F: Mission priority shift가 실패하는 경우

대표 라운드: 1
공격군: `PRIORITY_POISONING`
목표: `WRONG_TARGET_SELECTION`
전술: `mission_priority_shift`
결과: `DRAW / NO_EFFECT`
종료 이유: `red_finalized_no_effect`

### 의도

Red는 area A priority를 낮추고 C priority를 올려 Blue가 target area를 잘못 고르게 만들려 한다.

### Step 흐름

| Step | Red 행동 | Blue 행동 | 진행 해석 |
|---:|---|---|---|
| 1 | `PROBE_BOUNDARY` | `WAIT` | A를 조금 낮추고 C를 조금 올린다. 아직 top area는 바뀌지 않는다. |
| 2-7 | `SLOW_DRIFT` 반복 | `WAIT` | mission policy gate가 일부 제한을 걸지만, Blue가 직접 방어 action을 쓰지는 않는다. |
| 8 | `FINALIZE_ATTACK` | `WAIT` | 최종적으로 priority delta는 생겼지만 추천 area나 top area가 바뀌지 않아 goal effect가 없다. |

### 관찰점

- 이 사례는 "탐지되지 않았는데도 실패"한 경우다.
- Red가 수치를 바꿨더라도 임무 판단 결과가 안 바뀌면 goal success가 아니다.
- 그래서 현재 scorer가 단순 mutation 성공이 아니라 mission effect를 따로 보는 것이 중요하다.

## 8. 전체 흐름 요약

현재 공방은 대체로 다음 패턴으로 진행된다.

```text
1. Red가 PROBE_BOUNDARY로 작은 변조를 넣는다.
2. Blue는 WAIT, INSPECT_INTERNAL, RAISE_SUSPICION 중 하나로 반응한다.
3. Red가 효과가 있다고 판단하면 SLOW_DRIFT 또는 ESCALATE_MUTATION으로 키운다.
4. Blue는 domain별로 policy gate를 적용한다.
   - command: HOLD_COMMAND, QUARANTINE_FIELD, REQUEST_REVALIDATION
   - telemetry: OBSERVE_DOMAIN, REQUEST_REVALIDATION, FALLBACK_TO_TRUSTED_STATE
   - mission: OBSERVE_DOMAIN, QUARANTINE_FIELD, REQUEST_REVALIDATION
5. Red는 SWITCH_TACTIC, WAIT, ABORT, FINALIZE_ATTACK 중 하나를 고른다.
6. Scorer는 breach, containment, recovery, attrition, no effect를 분리해서 판정한다.
```

## 9. 현재 구조에서 보이는 성향

| 성향 | 해석 |
|---|---|
| `TIME_DESYNC_REPLAY`가 가장 많음 | 암호화 payload를 건드리지 않아도 metadata/timing/ACK 기반 공격 효과를 만들 수 있기 때문이다. |
| `TELEMETRY_FDI`는 탐지가 잘 됨 | 내부 observe가 telemetry trust anchor로 강하게 작동한다. |
| `PRIORITY_POISONING`은 no effect도 꽤 있음 | 수치 drift가 실제 top area 또는 recommended area를 못 바꾸면 목표 효과가 없다. |
| `RED_ATTRITION`이 반복됨 | Blue가 breach는 막지만 방어 비용이 누적되어 availability가 깎이는 경우가 있다. |
| `DETECTION_BOUNDARY_PROBE`가 중요함 | Red가 단번에 공격하기보다 Blue의 탐지 경계와 policy gate를 학습하는 과정으로 쓰인다. |

## 10. 다음 개선 포인트

1. `RED_ATTRITION`을 더 세밀하게 분해해야 한다.
   - Blue가 정말 과잉방어를 한 것인지,
   - Red가 현실적으로 싼 비용으로 Blue의 비싼 방어를 유도한 것인지,
   - 아니면 scorer가 방어 비용을 과대평가한 것인지 나눠야 한다.

2. Blue에 저비용 방어 action이 더 필요하다.
   - 지금은 `DEFEND`가 무거운 action으로 반복되는 경향이 있다.
   - `MONITOR_WITH_DOWNGRADE`, `LOW_COST_REVALIDATE`, `DEFER_DECISION` 같은 중간 action을 넣으면 더 현실적이다.

3. Red의 파생 tactic을 늘려야 한다.
   - `TIME_DESYNC_REPLAY`: replay, ack_confusion, delay, selective_drop을 더 세분화
   - `TELEMETRY_FDI`: battery, motor, drain-rate, confidence를 동시에 다루는 복합 tactic
   - `PRIORITY_POISONING`: priority vector, recommended area, confidence, stale mission cache를 함께 다루는 tactic

4. Step 로그를 프론트엔드용으로 더 압축해야 한다.
   - 학습용 로그는 지금처럼 자세히 남긴다.
   - 프론트엔드 로그는 `phase`, `red_intent`, `blue_response`, `score_delta`, `why_it_mattered` 중심으로 따로 생성하는 것이 좋다.
