# 마지막 Git 버전 대비 변경사항 요약

기준 커밋: `1c6e2a3`  
기준 커밋 메시지: `Merge remote-tracking branch 'origin/main' into jisung-review`  
비교 대상: 마지막 커밋(`HEAD`)과 현재 작업 트리

## 한 줄 요약

이번 변경의 핵심은 **Blue AI 안에 Zero Trust Observe/Command Policy Gate를 추가하고, 그 판단을 방어 결정, 점수, 로그, Streamlit 대시보드, 테스트까지 연결한 것**입니다.

이전 버전은 주로 Threat Detection 결과를 보고 방어했습니다.  
현재 버전은 그 앞뒤에 ZTA-inspired 정책 판단을 추가해서, Blue가 외부 관측값을 그냥 믿지 않고 `ALLOW`, `DOWNGRADE`, `REVALIDATE`, `QUARANTINE`, `DENY` 같은 단계로 신뢰도를 판단합니다.

## 새로 추가된 파일

| 파일 | 역할 |
|---|---|
| `ZTA적용.md` | ZTA를 전체 시스템에 과하게 도입하지 않고, Blue 내부의 Observe/Command Policy Gate로 부분 적용해야 한다는 설계 문서입니다. |
| `src/dah_flawless/blue/zero_trust_gate.py` | 실제 ZTA Policy Gate 구현입니다. command, telemetry, mission 관측값의 신뢰도를 계산하고 정책 결정을 만듭니다. |
| `tests/test_zero_trust_gate.py` | ZTA Gate 단위 테스트와 runner/simulator 연동 테스트입니다. |

## 핵심 동작 변화

### 이전 흐름

```text
Red mutation
-> Blue threat detection
-> Mission risk
-> Defense planner
-> Scorer
-> Log / Dashboard
```

### 현재 흐름

```text
Red mutation
-> Blue threat detection
-> Zero Trust Observe Gate
-> Mission risk + Defense planner
-> Scorer
-> Log / Dashboard
```

즉, Blue가 관측값을 사용하기 전에 다음 질문을 한 번 더 합니다.

```text
이 외부 관측값을 임무 판단에 그대로 써도 되는가?
아니면 낮은 신뢰도, 재검증, 격리, 차단으로 다뤄야 하는가?
```

## ZTA Gate가 실제로 판단하는 것

대상 도메인은 3개입니다.

| 도메인 | 예시 관측값 | 판단 목적 |
|---|---|---|
| `command` | C2 command, sequence, ACK, timestamp | stale/replay command를 그대로 실행하지 않게 함 |
| `telemetry` | battery, motor status, drain rate | 외부 telemetry와 내부 anchor가 충돌하는지 확인 |
| `mission` | recommended_area, area_priority | mission priority poisoning을 낮은 신뢰도로 처리 |

각 도메인은 아래 feature를 합쳐 `trust_score`를 계산합니다.

| feature | 의미 |
|---|---|
| `identity_auth` | auth, signature, checksum, encrypted channel 등 |
| `freshness` | sequence/timestamp/priority drift 등 최신성 |
| `internal_consistency` | 내부 관측 anchor와 외부 관측값의 일치 여부 |
| `domain_trust` | Blue feedback learner가 관리하는 도메인별 신뢰도 |
| `channel_health` | latency, packet loss, heartbeat gap 등 |
| `capability` | cross-check, restore, time validation capability 상태 |

결과 decision은 다음 중 하나입니다.

| decision | 의미 |
|---|---|
| `ALLOW` | 정상 사용 |
| `ALLOW_WITH_LOW_CONFIDENCE` | 사용은 하되 낮은 신뢰도로 취급 |
| `DOWNGRADE` | 임무 판단에서 비권위적 참고값으로만 사용 |
| `REVALIDATE` | 재검증 전까지 보류 |
| `QUARANTINE` | 탐지 근거로만 쓰고 운영 판단에서는 격리 |
| `DENY` | 사용 금지 |

## 파일별 변경사항

### `src/dah_flawless/blue/zero_trust_gate.py`

새 ZTA Gate입니다.

주요 기능:

- Blue가 볼 수 있는 입력만 사용합니다. `scorer_truth`는 보지 않습니다.
- command/telemetry/mission 도메인별로 신뢰도를 계산합니다.
- 위협 confidence가 높으면 trust score에 penalty를 줍니다.
- restrictive decision을 Defense Planner가 이해할 수 있는 action 후보로 바꿉니다.
- 라운드 전체 기준으로 `policy_decision_correctness`를 계산합니다.

중요한 점:

- ZTA가 scorer availability를 직접 깎지는 않습니다.
- Gate의 availability cost는 보고/설명용 정보이고, 실제 방어 비용은 Defense Planner 쪽에서 제한된 비용으로 반영됩니다.
- 전체 시스템을 ZTA로 바꾼 것이 아니라, Blue의 observe 사용 정책 계층만 추가한 구조입니다.

### `src/dah_flawless/blue/defense_planner.py`

Defense Planner가 ZTA decision을 받을 수 있게 바뀌었습니다.

이전:

- threat/risk 기반 defense action만 생성

현재:

- ZTA Gate가 `DOWNGRADE`, `REVALIDATE`, `QUARANTINE`, `DENY` 같은 판단을 내리면, 이를 defense action 후보로 변환합니다.
- 이미 같은 domain을 threat 기반 방어가 커버하고 있으면 중복 action을 만들지 않습니다.
- 로그에 `zta_policy_candidates`, `zta_policy_actions`를 남깁니다.

예시:

| ZTA decision | Defense action 후보 |
|---|---|
| command `REVALIDATE` | `REQUEST_REVALIDATION` |
| command `DENY` | `HOLD_COMMAND` |
| telemetry `QUARANTINE` | `QUARANTINE_FIELD` |
| mission `DOWNGRADE` | `OBSERVE_DOMAIN` |

### `src/dah_flawless/blue/mission_monitor.py`

Mission Monitor가 ZTA restrictive decision도 mission risk로 볼 수 있게 바뀌었습니다.

이전:

- threat list를 기준으로 mission risk 생성

현재:

- threat가 명시적으로 없더라도 ZTA Gate가 특정 domain을 제한하면 mission risk에 반영합니다.
- 예를 들어 telemetry가 `QUARANTINE`이면 “telemetry는 비권위적 증거로만 사용해야 한다”는 risk가 생깁니다.
- 로그의 `before` 구조가 기존 threat list에서 `{ threats, zta_restrictive_decisions }` 형태로 확장됐습니다.

### `src/dah_flawless/environment/simulator.py`

Classic round simulation 경로에 ZTA Gate가 들어갔습니다.

추가된 흐름:

```text
detect_threats
-> apply_detection_policy
-> evaluate_zero_trust
-> estimate_mission_risk
-> plan_defense
-> score_round
```

로그에 새로 들어가는 값:

- `zta_decisions`
- `zta_policy`
- decision log 안의 `ZeroTrustObserveGate` 이벤트
- score summary의 `policy_decision_correctness`

### `src/dah_flawless/environment/round_combat_runner.py`

Dynamic combat runner에도 같은 ZTA 흐름이 들어갔습니다.

변경점:

- combat step마다 `evaluate_zero_trust`를 실행합니다.
- ZTA restrictive decision이 있으면 Blue suspicion 계산에도 반영합니다.
- 각 combat step에 `zta_decisions`를 저장합니다.
- 라운드 종료 시 step별 decision을 모아서 `zta_policy`를 만듭니다.
- summary에 `policy_decision_correctness`를 추가합니다.

쉽게 말하면, dynamic combat replay에서 이제 매 step마다 Blue가 어떤 관측값을 얼마나 믿었는지 볼 수 있습니다.

### `src/dah_flawless/scoring/scorer.py`

Scorer evidence에 ZTA decision이 들어갑니다.

추가된 evidence:

```text
score.evidence.zta_policy_decisions
```

이 값은 Blue가 어떤 domain을 어떤 이유로 downgrade/quarantine/revalidate 했는지 보고서나 dashboard에서 설명할 때 쓰입니다.

### `src/dah_flawless/scoring/metrics.py`

전체 simulation summary에 ZTA 지표가 추가됐습니다.

추가된 summary 값:

| 값 | 의미 |
|---|---|
| `avg_policy_decision_correctness` | 공격 대상 domain은 제한하고, 깨끗한 domain은 과도하게 막지 않았는지의 평균 점수 |
| `zta_decision_counts` | `ALLOW`, `DOWNGRADE`, `QUARANTINE` 등 decision 개수 |

### `src/dah_flawless/reporting/frontend_log.py`

프론트엔드용 compact replay log에 ZTA 정보가 추가됐습니다.

추가된 값:

- top-level `zero_trust`
- summary의 `avg_policy_decision_correctness`
- round별 `zta_policy`
- timeline step별 `zta`
- filter의 `zta_decisions`

또한 `_sorted_unique`가 중복값을 제거하도록 바뀌어서 filter 목록이 더 깔끔해졌습니다.

### `streamlit_app.py`

Streamlit 대시보드에 ZTA 시각화가 추가됐습니다.

추가된 화면 요소:

| 위치 | 추가 내용 |
|---|---|
| KPI 영역 | `ZTA POLICY` 카드 |
| Operator Brief | 선택 round의 policy correctness 표시 |
| Overview | `Zero Trust policy` 테이블 |
| Timeline | `Policy decision timeline` 테이블 |
| Combat steps | `zta_min_trust`, `zta_restrictive` 컬럼 |
| Charts | ZTA policy correctness 라인 차트 |
| Charts | ZTA decision count bar chart |

이제 발표/시연 때 “Blue가 왜 이 값을 믿지 않았는지”를 대시보드에서 바로 설명할 수 있습니다.

### `tests/test_zero_trust_gate.py`

새 ZTA Gate 테스트입니다.

검증하는 내용:

- 깨끗한 상태에서는 모든 domain이 `ALLOW`
- telemetry false data injection은 telemetry만 제한
- command replay/auth 문제는 command 제한
- domain trust가 낮으면 trust score가 내려감
- ZTA restrictive decision이 Defense Planner action 후보로 이어짐
- simulator와 round combat runner가 ZTA 로그와 score evidence를 실제로 배출함

### `tests/test_frontend_log.py`

프론트엔드 projection 테스트가 강화됐습니다.

추가 검증:

- frontend log에 `zero_trust`가 존재하는지
- summary에 `avg_policy_decision_correctness`가 들어가는지
- filter에 `zta_decisions`가 들어가는지
- timeline step에 ZTA 정보가 들어가는지

### `tests/test_mutation_policy.py`

Mutation policy 설정이 커질 때 깨질 수 있는 부분을 막는 테스트가 추가됐습니다.

추가 검증:

- 서로 다른 policy가 같은 runtime path를 동시에 잡지 않는지
- 모든 field policy가 `stealth`, `aggressive`, `loud_demo` profile을 다 갖는지
- runtime policy가 `internal_observe`, `state.world`, `raw_world` 같은 금지 scope를 직접 mutate 대상으로 잡지 않는지
- 허용된 mutation kind만 쓰는지

이 변경은 Gemini 피드백의 “룰 충돌 방지 테스트” 제안을 반영한 것입니다.

## 실제 효과

### 1. Blue 판단 설명력이 좋아짐

이전에는 “Blue가 threat를 감지했고 방어했다” 정도의 설명이 중심이었습니다.

현재는 다음처럼 말할 수 있습니다.

```text
Blue는 telemetry domain의 trust_score를 0.38로 평가했다.
이유는 internal/external telemetry gap과 threat confidence penalty 때문이다.
따라서 telemetry를 운영 판단에서 authoritative하게 쓰지 않고 quarantine했다.
```

### 2. 과방어를 줄이는 구조가 생김

ZTA Gate는 무조건 `DENY`만 하지 않습니다.  
`ALLOW_WITH_LOW_CONFIDENCE`, `DOWNGRADE`, `REVALIDATE` 같은 중간 단계를 둡니다.

그래서 “조금 이상하면 전부 차단”이 아니라, 신뢰도에 따라 비용이 낮은 판단부터 할 수 있습니다.

### 3. 보고서/시연용 evidence가 강해짐

대시보드와 frontend log에 policy decision timeline이 들어갔습니다.

이제 발표에서 다음을 보여줄 수 있습니다.

- 어느 step에서 trust score가 떨어졌는지
- 어떤 domain이 제한됐는지
- 제한 이유가 무엇인지
- 공격 target domain과 정책 판단이 맞았는지

### 4. 테스트 범위가 넓어짐

기존 테스트뿐 아니라 ZTA Gate, frontend projection, mutation policy conflict까지 확인합니다.

현재 전체 테스트 결과:

```text
151 passed
```

## 바뀌지 않은 것

중요하게, 아래는 바뀌지 않았습니다.

- Red가 실제 네트워크/RF/API를 해킹하는 구조가 아닙니다.
- Red는 여전히 simulator 안의 `external_observe`만 안전하게 mutation합니다.
- Blue는 여전히 `scorer_truth`를 보지 않습니다.
- `internal_observe`는 Blue trust anchor로 유지됩니다.
- LLM reviewer/fallback 구조는 그대로입니다.
- 전체 시스템을 ZTA 제품/네트워크 아키텍처로 갈아엎은 것이 아닙니다.

## 주의할 점

### 1. ZTA correctness는 보조 지표입니다

`policy_decision_correctness`는 “공격당한 domain은 제한하고, 깨끗한 domain은 과도하게 막지 않았는가”를 보는 지표입니다.

이 값이 높다고 해서 전체 mission success를 보장하는 것은 아닙니다.  
기존 `attack_success`, `goal_success`, `availability`, `recovery_success`, `mission_impact_score`와 같이 봐야 합니다.

### 2. Gate cost는 직접 availability를 깎지 않습니다

ZTA Gate의 `availability_cost`는 reporting/audit용입니다.  
실제 mission availability를 깎는 비용은 Defense Planner와 기존 attrition model 쪽에서 관리합니다.

이렇게 한 이유는 ZTA Gate만 추가했는데 기존 RED_ATTRITION 밸런스를 갑자기 망가뜨리지 않기 위해서입니다.

### 3. 설정 파일이 커질수록 테스트가 중요합니다

`configs/mutation_policy.yaml`이 더 커지면 policy path 충돌이나 profile 누락이 생길 수 있습니다.  
이번에 추가한 mutation policy 테스트가 그 부분을 조기에 잡도록 만들어졌습니다.

## 검증 결과

실행한 검증:

```text
python -m py_compile streamlit_app.py src/dah_flawless/blue/zero_trust_gate.py tests/test_mutation_policy.py
python -m pytest tests/test_zero_trust_gate.py tests/test_mutation_policy.py tests/test_frontend_log.py
python -m pytest
```

결과:

```text
151 passed
```

참고:

- pytest 실행 중 `.pytest_cache` 쓰기 권한 경고가 1개 있었지만, 테스트 실패는 아닙니다.
- `git status` 실행 중 홈 디렉터리의 global git ignore 접근 권한 경고가 있었지만, 프로젝트 코드 변경과는 무관합니다.

## 결론

마지막 Git 버전과 비교했을 때, 현재 작업 트리는 단순한 문서 수정이 아니라 **ZTA-inspired Blue policy layer를 실제 simulation loop에 연결한 상태**입니다.

핵심 변화는 다음 4가지입니다.

1. Blue가 외부 관측값을 domain별로 신뢰도 평가합니다.
2. 그 평가가 Mission Monitor와 Defense Planner에 실제 action 후보로 들어갑니다.
3. Scorer, summary, frontend log, Streamlit dashboard에서 정책 판단을 볼 수 있습니다.
4. ZTA Gate와 mutation policy 충돌 방지를 테스트로 검증합니다.

따라서 현재 버전은 Gemini 피드백 중 다음 항목을 반영한 상태입니다.

- ZTA Policy Gate 우선 구현
- Policy Decision Timeline 시각화
- 과방어를 줄이기 위한 단계적 decision 구조
- mutation policy rule 충돌 방지 테스트

