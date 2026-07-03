# Encrypted Channel Attack AI Design

이 문서는 암호화된 통신 환경에서 Red AI가 직접 복호화에 의존하지 않고, 관측 가능한 시간성, 순서성, 중복성, 누락, 메타데이터, 응답 패턴을 이용해 공격 방법을 선택하는 설계를 정리한다.

용어 주의: 현재 구현에서 `state["world"]`는 raw_world가 아니라 scorer-only 기준 상태(`scorer_truth`)다. 현실 원천 신호는 `raw_world`, Blue가 받은 입력은 `blue_observed`라고 구분한다.

핵심 전제는 다음과 같다.

```text
Red는 암호문 본문을 해독하지 않는다.
Red는 observed channel의 외형, 순서, 시간, 반복, 누락, 응답 패턴만 관찰한다.
Red는 상황 태그를 기반으로 공격 후보를 점수화하고 선택한다.
Blue는 공격명을 직접 알지 못하고, 불변식 위반과 임무 영향으로 탐지한다.
Scorer만 scorer_truth와 observed를 비교해 공격 성공 여부를 판정한다.
```

## 1. 방향성

초기 아이디어는 두 가지였다.

| 구분 | 설명 | 평가 |
|---|---|---|
| 직접 암호화 해독 | 암호화된 데이터를 직접 풀어서 명령이나 상태를 조작 | 현실 난도가 높고 예선 보고서에서 가능성을 증명하기 어려움 |
| 복호화 없는 교란 | 암호문을 해독하지 않고 일정 시간 유지, 재전송, 지연, 순서 변경 등으로 AI 판단을 흔듦 | 현실적이고 방산 운용 시나리오와 잘 맞음 |

따라서 주력 방향은 **암호를 깨는 AI**가 아니라, **암호화된 통신의 시간·순서·가용성·메타데이터를 공격하는 Red AI**로 둔다. 직접 암호화 해독은 주력 공격이 아니라 고난도/비현실 공격 카탈로그에 남긴다.

## 2. 공격 방법 10종

| # | 공격명 | 핵심 아이디어 | 복호화 필요 | 보고서 내 위치 |
|---:|---|---|---|---|
| 1 | `DIRECT_DECRYPTION` | 암호화된 데이터를 직접 복호화하거나 키 취약점을 이용 | 필요 | 고난도/비현실 카탈로그 |
| 2 | `REPLAY_ATTACK` | 과거 정상 암호문 패킷을 다시 보내 과거 상태나 명령을 최신처럼 보이게 함 | 불필요 | 주력 후보 |
| 3 | `DELAY_ATTACK` | 정상 패킷을 일정 시간 늦게 전달해 오래된 상태로 판단하게 함 | 불필요 | 주력 후보 |
| 4 | `REORDERING_ATTACK` | 패킷 도착 순서를 바꿔 상태 전이를 꼬이게 함 | 불필요 | 주력 후보 |
| 5 | `SELECTIVE_DROP` | 특정 구간이나 중요해 보이는 패킷만 누락시킴 | 불필요 | 주력 후보 |
| 6 | `DUPLICATE_INJECTION` | 정상 암호문 패킷을 여러 번 반복해 중복 적용을 유도 | 불필요 | 확장 후보 |
| 7 | `TIMING_PATTERN_MANIPULATION` | 패킷 도착 주기와 응답 시간을 조작해 AI 판단을 흔듦 | 불필요 | 확장 후보 |
| 8 | `METADATA_POISONING` | 암호문 밖의 timestamp, sequence, sender id, priority, routing 정보 등을 조작 | 부분적 불필요 | 주력 후보 |
| 9 | `TRAFFIC_SHAPING_LOAD` | 통신량을 특정 시간대에 몰아 처리 지연과 가용성 저하를 유도 | 불필요 | 확장 후보 |
| 10 | `ACK_CONFIRMATION_CONFUSION` | 확인 응답 흐름을 교란해 명령 적용 여부를 잘못 믿게 함 | 불필요 | 확장 후보 |

보고서에서는 `DIRECT_DECRYPTION`을 낮은 feasibility로 분류하고, 나머지 공격을 암호화 환경에서도 가능한 현실적 공격으로 제시한다.

## 3. Red AI 선택 구조

Red AI는 매 라운드 현재 관측 상태를 보고 10개 공격 중 가장 적절한 방법을 선택한다.

```text
관측 상태 입력
→ 상황 태그 추출
→ 공격 후보 10개 점수화
→ 제약조건 필터링
→ 공격 선택
→ observed channel에 변조 적용
→ scorer가 성공/실패 피드백
→ 다음 라운드 가중치 조정
```

이 구조는 완전한 강화학습으로 과장하지 않고, **상황 태그 기반 정책 선택 Red Agent + 성공/실패 피드백 기반 가중치 업데이트**로 설명한다.

## 4. 상황 태그와 공격 매핑

| 관측 상황 태그 | 의미 | 우선 공격 후보 |
|---|---|---|
| `SEQUENCE_VISIBLE` | sequence number 또는 순서 정보가 관찰됨 | `REPLAY_ATTACK`, `REORDERING_ATTACK`, `DUPLICATE_INJECTION` |
| `TIMESTAMP_VISIBLE` | timestamp 또는 수신 시간이 관찰됨 | `DELAY_ATTACK`, `TIMING_PATTERN_MANIPULATION`, `METADATA_POISONING` |
| `REGULAR_PACKET_INTERVAL` | 패킷 주기가 일정함 | `DELAY_ATTACK`, `TRAFFIC_SHAPING_LOAD` |
| `ACK_CHANNEL_VISIBLE` | 명령 확인 응답 흐름이 관찰됨 | `ACK_CONFIRMATION_CONFUSION`, `DELAY_ATTACK` |
| `PACKET_SIZE_PATTERN` | 패킷 크기나 주기로 중요도를 추정할 수 있음 | `SELECTIVE_DROP`, `TRAFFIC_SHAPING_LOAD` |
| `METADATA_PLAINTEXT` | 본문 외 메타데이터가 평문 또는 조작 가능 | `METADATA_POISONING` |
| `STATE_UPDATE_DEPENDENT` | Blue 판단이 최신 상태 업데이트에 강하게 의존 | `STALE_STATE_ATTACK`, `DELAY_ATTACK`, `SELECTIVE_DROP` |
| `CRYPTO_WEAKNESS_HINT` | 암호 설정 취약점 단서가 있음 | `DIRECT_DECRYPTION` |
| `REPLAY_WINDOW_OPEN` | anti-replay 허용창이 넓고 sequence/time이 관찰됨 | `REPLAY_ATTACK`, `DUPLICATE_INJECTION` |
| `ACK_TIMING_ANOMALY` | ACK sequence 또는 delay가 명령 흐름과 불일치 | `ACK_CONFIRMATION_CONFUSION`, `DELAY_ATTACK` |
| `HEARTBEAT_GAP` | 정상 heartbeat 주기보다 긴 공백이 생김 | `SELECTIVE_DROP`, `DELAY_ATTACK` |
| `PACKET_INTERVAL_ANOMALY` | 패킷 도착 주기가 평소보다 크게 흔들림 | `TIMING_PATTERN_MANIPULATION`, `TRAFFIC_SHAPING_LOAD` |

`STALE_STATE_ATTACK`은 독립 공격명으로 둘 수도 있지만, 본 문서에서는 `REPLAY_ATTACK`, `DELAY_ATTACK`, `SELECTIVE_DROP`의 목적형 변형으로 취급한다.

## 5. 공격 점수화 기준

각 공격 후보는 다음 기준으로 점수화한다.

| 기준 | 설명 |
|---|---|
| `feasibility` | 현재 관측 정보만으로 실행 가능한가 |
| `impact` | 성공 시 임무 판단을 얼마나 흔드는가 |
| `detectability` | Blue에게 탐지될 가능성이 얼마나 높은가 |
| `past_success` | 이전 라운드에서 같은 공격 계열이 성공했는가 |
| `cost` | 공격 수행으로 노출되거나 가용성을 소모하는 정도 |
| `situation_match` | 현재 situation tag와 공격 조건이 맞는가 |

예시 점수식:

```text
attack_score
= base_weight
+ situation_match_bonus
+ impact_score
+ past_success_bonus
- detectability_penalty
- execution_cost
```

기본 방향은 다음과 같다.

```text
성공한 공격은 다음 라운드 가중치 증가
탐지된 공격은 다음 라운드 가중치 감소
가용성 피해가 큰 공격은 impact 점수 증가
반복 사용한 공격은 detectability penalty 증가
DIRECT_DECRYPTION은 crypto weakness hint가 없으면 큰 penalty 적용
```

## 6. Attack Selector 구현 형태

현재 구현은 두 단계로 나뉜다.

```text
Situation Tagger
→ attack 후보 점수화
→ 선택된 attack 내부 tactic 후보 점수화
→ Mutation Engine에 tactic 전달
```

`TIME_DESYNC_REPLAY`는 하나의 공격명으로 유지하되 내부 tactic을 다음처럼 나눈다.

| tactic | 우선 태그 | 의미 |
|---|---|---|
| `replay` | `SEQUENCE_VISIBLE`, `TIMESTAMP_VISIBLE`, `REPLAY_WINDOW_OPEN` | 과거 명령/상태를 최신처럼 보이게 함 |
| `delay` | `TIMESTAMP_VISIBLE`, `REGULAR_PACKET_INTERVAL`, `HIGH_LATENCY` | 정상 메시지를 늦게 반영시켜 stale state 유도 |
| `selective_drop` | `PACKET_SIZE_PATTERN`, `HEARTBEAT_GAP`, `PACKET_LOSS_HIGH` | heartbeat/state update 공백을 만듦 |
| `ack_confusion` | `ACK_CHANNEL_VISIBLE`, `ACK_TIMING_ANOMALY` | 명령과 ACK의 인과관계를 꼬이게 함 |
| `metadata_poisoning` | `METADATA_PLAINTEXT`, `SEQUENCE_VISIBLE`, `TIMESTAMP_VISIBLE` | 암호문 밖 메타데이터를 오염시킴 |

selector log 예시:

```json
{
  "attack": "TIME_DESYNC_REPLAY",
  "tactic": {
    "strategy": "replay",
    "selector": "tag_scored_tactic_policy",
    "matched_tags": ["C2_ENCRYPTED", "PAYLOAD_HIDDEN", "REPLAY_WINDOW_OPEN"],
    "score_breakdown": {
      "base_score": 1.9,
      "impact": 2.1,
      "tag_bonus": 5.515,
      "detectability_penalty": 0.9,
      "execution_cost": 0.4
    }
  }
}
```

구현 위치:

```text
src/dah_flawless/attacks/selector.py
src/dah_flawless/attacks/red_agent.py
src/dah_flawless/attacks/mutations.py
```

## 7. 간단한 정책 예시

```text
if SEQUENCE_VISIBLE:
    score(REPLAY_ATTACK) += 5
    score(REORDERING_ATTACK) += 4
    score(DUPLICATE_INJECTION) += 3

if TIMESTAMP_VISIBLE:
    score(DELAY_ATTACK) += 5
    score(TIMING_PATTERN_MANIPULATION) += 4

if ACK_CHANNEL_VISIBLE:
    score(ACK_CONFIRMATION_CONFUSION) += 5

if PACKET_SIZE_PATTERN:
    score(SELECTIVE_DROP) += 4
    score(TRAFFIC_SHAPING_LOAD) += 3

if METADATA_PLAINTEXT:
    score(METADATA_POISONING) += 6

if not CRYPTO_WEAKNESS_HINT:
    score(DIRECT_DECRYPTION) -= 10
```

## 8. Blue 방어 관점

Blue는 Red가 어떤 공격명을 선택했는지 알 필요가 없다. 대신 observed state에서 다음 불변식 위반을 탐지한다.

| 공격 계열 | Blue 탐지 단서 | 방어 조치 |
|---|---|---|
| Replay / Duplicate | sequence 재사용, timestamp 역행, 메시지 반복 패턴 | 중복 메시지 격리, 마지막 정상 명령 유지 |
| Delay / Stale State | 수신 시간 지연, 센서 상태와 명령 시점 불일치 | command hold, 재검증 요청 |
| Reordering | sequence 역전, 상태 전이 순서 위반 | out-of-order 메시지 격리 |
| Selective Drop | 예상 heartbeat 누락, 상태 업데이트 공백 | degraded mode, fallback state 사용 |
| Timing Manipulation | 패킷 간격 급변, 응답 시간 이상 | 신뢰도 하향, 추가 검증 |
| Metadata Poisoning | priority, sender, route, timestamp의 정합성 위반 | 오염 메타데이터 격리 |
| Traffic Shaping | 처리 큐 증가, 가용성 저하, 지연 집중 | rate limit, 우선순위 큐 분리 |
| Ack Confusion | 명령과 확인 응답의 인과관계 불일치 | ack 재검증, 명령 적용 보류 |
| Direct Decryption | 비정상적으로 정밀한 조작, integrity 위반 | 키 회전, 인증 실패 처리, safe mode |

## 9. 보고서용 핵심 문장

```text
본 설계의 Red Agent는 암호문을 직접 해독하는 대신, 암호화 통신에서도 외부에서 관찰 가능한 시간성, 순서성, 중복성, 누락, 메타데이터, 확인 응답 패턴을 기반으로 공격 방법을 선택한다. 이는 실제 방산 운용망에서 암호 자체가 유지되더라도 AI 관제 판단이 교란될 수 있음을 보여준다.
```

```text
Red Agent는 매 라운드 observed channel에서 상황 태그를 추출하고, 10개 공격 후보를 feasibility, impact, detectability, past success 기준으로 점수화한다. 이후 가장 높은 기대효과를 갖는 공격을 적용하고, scorer의 성공/실패 피드백을 이용해 다음 라운드의 공격 가중치를 조정한다.
```

```text
Blue Agent는 공격명을 맞히는 방식이 아니라, sequence, timestamp, heartbeat, ack, metadata, mission state 간의 불변식 위반을 탐지한다. 따라서 Red가 replay, delay, reordering처럼 복호화 없는 공격을 사용하더라도 Blue는 관측 정합성 기반으로 탐지·격리·복구를 수행한다.
```

## 10. 프로젝트 내 반영 우선순위

| 우선순위 | 항목 | 이유 |
|---|---|---|
| Must | `TIME_DESYNC_REPLAY`에 replay, delay, sequence regression 포함 | 기존 공격 3종과 가장 잘 맞음 |
| Must | Red Agent의 상황 태그 기반 공격 선택 | AI가 스스로 적절한 공격을 고른다는 증거 |
| Must | Blue의 sequence/timestamp/ack 불변식 탐지 | 공격명 비의존 방어 구조 증명 |
| Should | 공격 10종 카탈로그와 가중치 표 | 설계 커버리지와 전략성 증명 |
| Should | 성공/실패 피드백 기반 weight update | 자율 에이전트 루프 증명 |
| Nice | 실제 강화학습 또는 LLM 기반 선택 | 예선 핵심은 아님 |

결론적으로, 예선 보고서에서는 **직접 암호화 해독**보다 **암호화된 통신의 외형적 속성을 이용한 AI 교란**을 주력 공격 모델로 제시하는 것이 더 안전하고 설득력 있다.
