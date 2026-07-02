# DAH Flawless 구현 계획서

기준일: 2026-07-01 KST  
제출 마감: 2026-07-10 23:59 KST  
목표: 예선 보고서 8항목 중 ④ 공격 시나리오, ⑤ 방어 아키텍처, ⑥ AI 에이전트 설계를 구현 로그와 그림으로 증명한다.

---

## 1. 현재 저장소 판독 결과

현재 저장소는 실행 가능한 코드보다 보고서와 MVP 설계를 위한 문서가 중심이다. 핵심 방향은 이미 정리되어 있고, 지금 필요한 일은 아이디어 추가가 아니라 구현 가능한 최소 시스템으로 고정하는 것이다.

읽은 파일과 용도는 다음과 같다.

| 파일 | 계획에서의 역할 |
|---|---|
| `README.md` | 전체 전략, 배점 대응, MVP 합격선, 즉시 실행 체크리스트 |
| `docs/README.md` | 설계 문서 읽는 순서와 보고서 반영 우선순위 |
| `docs/world_observed_model.md` | `world`와 `blue_observed` 분리 원칙, Red/Blue/Scorer 접근 권한 |
| `docs/schema_design.md` | MVP 상태 JSON 구조의 기준 |
| `docs/field_formats.md` | 필드 타입, 단위, enum, 로그 형식 |
| `docs/situation_tags.md` | observed 기반 태그 규칙, Red/Blue 공통 입력 |
| `docs/attack_mapping.md` | 공격 3종과 Detect/Contain/Recover 매핑 |
| `docs/encrypted_channel_attack_ai.md` | 암호를 깨지 않는 시간·순서·메타데이터 기반 Red Agent 설계 |
| `docs/reference_sources.md` | 보고서 참고문헌과 설계 근거 |
| `assets/overview.svg` | 보고서/README에 넣을 전체 아키텍처 요약 그림 |
| `tmp/pdfs/dah_prelim-*.png` | 예선 안내서 이미지: 제출 마감, 보고서 8항목, 배점, 제출 형식 확인용 |
| `.gitignore` | Python/Node 산출물, 생성 보고서, 로컬 파일 제외 기준 |

`.DS_Store`와 `docs/.DS_Store`는 macOS 메타데이터이며 `.gitignore` 대상이므로 설계 대상에서 제외한다.

---

## 2. 최종 산출물

제출물은 두 덩어리로 만든다.

1. 예선 보고서 PDF
   - 8항목 순서 준수
   - 25~40쪽 목표
   - 50MB 이하
   - 표, 그림, 코드, 로그 출처 표기

2. 부가자료 ZIP
   - `README.md`: 실행 방법, seed, 출력물 설명
   - `src/`: Red/Blue/Environment/Scorer 구현
   - `tests/`: 진실 분리, seed 재현성, 공격 3종 검증
   - `reports/figures/`: 보고서 삽입용 PNG
   - `data/logs/`: seed 고정 JSONL 로그
   - `requirements.txt` 또는 `Dockerfile`

파일명은 예선 안내서 기준에 맞춘다.

```text
DAH2026_예선보고서_[팀명].pdf
DAH2026_소스코드_[팀명].zip
```

---

## 3. 구현 원칙

### 3.1 Must 우선

예선 점수는 구현의 규모가 아니라 보고서 안의 증거 연결성에서 나온다. 따라서 아래 항목을 먼저 끝낸다.

| 우선순위 | 내용 |
|---|---|
| Must | 공격 3종 E2E, `world`/`blue_observed` 분리, 불변식 탐지, 방어 로그, scorer, seed 재현, 보고서 그림 |
| Should | 공진화 그래프, availability 곡선, 방어 큐 타임라인, 5 seed 집계 |
| Nice | Streamlit 대시보드, 데모 영상, LLM 보고서, 공격 4종 이상 |

### 3.2 Blue는 정답을 보면 안 된다

가장 중요한 검증 조건은 이것이다.

```text
Blue Agent 입력에는 world가 절대 들어가지 않는다.
world는 Environment와 Scorer만 접근한다.
```

이 조건은 문서 주장으로 끝내지 않고 테스트로 강제한다.

### 3.3 공격명 맞히기가 아니라 불변식 탐지

Blue는 `TELEMETRY_FDI` 같은 공격명을 직접 조건문으로 맞히면 안 된다. Blue는 아래처럼 관측값 내부의 모순을 본다.

| 탐지 영역 | 불변식 예시 |
|---|---|
| telemetry | 배터리, 소모율, 모터 상태가 물리적으로 맞는가 |
| mission | 임무 우선순위가 근거 없이 급변했는가 |
| command/time | sequence와 timestamp가 단조 증가하는가 |
| comms | 지연, 손실, 큐 적체가 임무 판단을 훼손하는가 |

---

## 4. 권장 디렉터리 구조

현재 저장소에 구현 폴더가 없으므로 아래 구조로 시작한다.

```text
src/
  dah_flawless/
    __init__.py
    config.py
    schemas.py
    main.py
    environment/
      simulator.py
      state_factory.py
      redaction.py
      hash_log.py
    attacks/
      catalog.py
      red_agent.py
      mutations.py
    blue/
      tagger.py
      invariants.py
      threat_detection.py
      mission_monitor.py
      defense_planner.py
      incident_report.py
    scoring/
      scorer.py
      metrics.py
    reports/
      figures.py
      summary.py
tests/
  test_redaction.py
  test_seed_reproducibility.py
  test_attacks_e2e.py
  test_scorer.py
data/
  scenarios/
  logs/
reports/
  figures/
```

구현 언어는 Python 3.11을 기준으로 한다. 코어는 표준 라이브러리 중심으로 만들고, 보고서 PNG 생성을 위해 `matplotlib`만 필수 의존성으로 둔다.

---

## 5. 시스템 설계

### 5.1 라운드 루프

MVP는 라운드 기반 시뮬레이터로 만든다.

```text
1. Environment가 world와 blue_observed를 가진 state를 만든다.
2. Red Agent가 blue_observed와 situation_tags만 보고 공격을 선택한다.
3. Environment가 공격 mutation을 blue_observed에만 적용한다.
4. Environment가 world를 제거한 redacted state를 Blue에 넘긴다.
5. Blue 4-Agent가 태그, 위협, 임무 영향, 최소 방어를 계산한다.
6. Defense Planner가 방어 큐에 action을 넣고 availability/trust_budget을 차감한다.
7. Scorer가 world와 blue_observed를 비교해 승패를 판정한다.
8. Hash log가 라운드 로그를 JSONL로 남긴다.
9. Red/Blue는 scorer 피드백만 받아 다음 라운드 가중치나 임계값을 조정한다.
```

### 5.2 데이터 모델

`docs/schema_design.md`와 `docs/field_formats.md`를 기준으로 최소 필드를 먼저 구현한다.

| 영역 | 최소 필드 |
|---|---|
| world | `uav.battery_percent`, `uav.motor_status`, `mission.area_priority`, `command.expected_sequence_number`, `time.true_timestamp` |
| blue_observed | `telemetry.battery_percent`, `telemetry.motor_status`, `mission.area_priority`, `c2_message.sequence_number`, `time.received_timestamp`, `comms.latency_ms`, `c2_message.auth_valid` |
| runtime | `mission.availability`, `mission.trust_budget`, `defense_runtime.active_defenses`, `defense_runtime.pending_defenses` |
| log | `round`, `seed`, `prev_hash`, `this_hash`, `attack`, `threats`, `defense_actions`, `score`, `decision_log` |

처음부터 큰 스키마를 모두 구현하지 말고, 공격 3종을 증명하는 필드부터 고정한다.

---

## 6. 공격 3종 구현 계획

### 6.1 TELEMETRY_FDI

| 항목 | 구현 |
|---|---|
| 조작 대상 | `blue_observed.telemetry.battery_percent`, `blue_observed.telemetry.motor_status` |
| 예시 mutation | 실제 배터리 20%, 모터 `FAULT` 상황에서 observed를 82%, `OK`로 변경 |
| Blue 탐지 | 배터리 높음, drain rate 높음, 모터 상태/임무 판단 충돌 |
| 방어 | 오염 telemetry 필드 격리, 마지막 정상 상태 fallback, 복귀 판단 복원 |
| 보고서 증거 | World vs Observed diff, round log, Detect/Contain/Recover 표 |

### 6.2 PRIORITY_POISONING

| 항목 | 구현 |
|---|---|
| 조작 대상 | `blue_observed.mission.area_priority` |
| 예시 mutation | 실제 A=0.9, C=0.2인데 observed는 A=0.2, C=0.95 |
| Blue 탐지 | 우선순위 급변, 근거 이벤트 부재, 이전 라운드와 불연속 |
| 방어 | priority update 격리, 기존 임무 목표 유지, 재검증 요청 |
| 보고서 증거 | 임무 오판 흐름도, priority diff, round log |

### 6.3 TIME_DESYNC_REPLAY

| 항목 | 구현 |
|---|---|
| 조작 대상 | `blue_observed.c2_message.sequence_number`, `blue_observed.time.received_timestamp`, `blue_observed.c2_message.command` |
| 예시 mutation | expected sequence 1021인데 observed sequence 1008과 `CONTINUE_MISSION` 주입 |
| Blue 탐지 | sequence 역행, timestamp skew, replay pattern |
| 방어 | command hold, 마지막 정상 명령 유지, 재검증 요청 |
| 보고서 증거 | sequence timeline, replay 탐지 로그, command hold 로그 |

---

## 7. Blue Agent 구현 계획

Blue는 4개 역할로 나눈다.

| Agent | 책임 | 입력 | 출력 |
|---|---|---|---|
| Threat Detection | 태그와 불변식으로 위협 탐지 | redacted state, history | threats |
| Mission Monitor | 위협이 임무에 주는 영향 계산 | threats, observed mission | risks |
| Defense Planner | 최소 방어 선택 | threats, risks, trust budget | defense actions |
| Incident Report | 보고서용 사건 요약 생성 | threats, actions, score | report entry |

Blue 내부 판단은 모두 `decision_log`에 남긴다.

```json
{
  "agent": "DefensePlanner",
  "event": "action_selected",
  "reason": "sequence_regression_confidence_0.84",
  "after": "HOLD_COMMAND"
}
```

---

## 8. Scorer와 승패 판정

Scorer는 `world`를 볼 수 있는 유일한 판정자다. 보고서에서 자의적 판정이라는 비판을 피하기 위해 승패 조건을 코드와 문서에서 동일하게 유지한다.

| 판정 | 조건 |
|---|---|
| `RED_BREACH` | 공격 성공, 탐지 실패 |
| `RED_ATTRITION` | 방어 비용 때문에 `availability`가 임계값 아래로 하락 |
| `BLUE` | 탐지 성공, 가용성 임계값 이상 유지 |
| `BLUE_RECOVERY` | degraded 시작 후 신뢰 상태와 가용성을 목표 이상으로 복구 |
| `DRAW` | 위 조건에 명확히 들지 않음 |

기본값은 다음으로 시작한다.

```text
DETECTION_WINDOW = 2
CONFIDENCE_THRESHOLD = 0.6
AVAIL_FLOOR = 0.5
RECOVERY_TARGET = 0.7
RECOVERY_WINDOW = 2
```

---

## 9. 로그와 그림

### 9.1 JSONL 로그

각 라운드는 한 줄 JSON으로 남긴다.

```json
{
  "round": 3,
  "seed": 42,
  "prev_hash": "a0b1...",
  "this_hash": "f9e8...",
  "situation_tags": ["TELEMETRY_CONFLICT"],
  "attack": {"name": "TELEMETRY_FDI", "target_domain": "telemetry"},
  "threats": [{"target": "telemetry", "confidence": 0.82}],
  "defense_actions": [{"action": "QUARANTINE_FIELD", "target": "blue_observed.telemetry.battery_percent"}],
  "score": {"winner": "BLUE", "attack_success": true, "detection_success": true}
}
```

`prev_hash`와 `this_hash`로 로그 변조 여부를 확인할 수 있게 한다.

### 9.2 보고서 필수 그림

`reports/figures.py`가 로그를 읽어 아래 PNG를 생성해야 한다.

| 그림 | 목적 | 우선순위 |
|---|---|---|
| 협력 다이어그램 | Red/Blue/Scorer와 world 분리 설명 | Must |
| World vs Observed diff | 공격별 조작 필드 증명 | Must |
| 공격 흐름도 | 작전상황 → 조작 → 오판 → 피해 | Must |
| Detect/Contain/Recover | 방어 아키텍처 증명 | Must |
| 라운드별 점수판 | scorer 결과 증명 | Must |
| availability 곡선 | 과방어가 실패가 될 수 있음을 증명 | Should |
| 공진화 그래프 | Red/Blue 적응 루프 증명 | Should |

`assets/overview.svg`는 협력 다이어그램의 초안으로 그대로 활용할 수 있다.

---

## 10. 개발 일정

오늘이 2026-07-01 KST이므로, 마감까지 구현·보고서·제출 검증을 모두 끝내려면 Must를 7월 6일까지 닫아야 한다.

| 기간 | 목표 | 산출물 |
|---|---|---|
| 7/1 | 프로젝트 뼈대 생성, 스키마, state factory, redaction | `src/`, `schemas.py`, `test_redaction.py` |
| 7/2 | PRIORITY_POISONING 1종 E2E | 1 seed JSONL, scorer 1차, README 실행법 |
| 7/3 | TELEMETRY_FDI, TIME_DESYNC_REPLAY 추가 | 공격 3종 E2E, `test_attacks_e2e.py` |
| 7/4 | Blue 불변식, Defense Planner, 방어 큐 | Detect/Contain/Recover 로그 |
| 7/5 | scorer 고정, hash log, seed 재현성 테스트 | `test_seed_reproducibility.py`, round logs |
| 7/6 | 보고서 PNG 생성기 | World vs Observed, score board, D/C/R 그림 |
| 7/7 | 보고서 8항목 초안 | 25쪽 이상 초안, 증거 추적표 |
| 7/8 | Should 가능분: availability, 공진화 집계 | 가능하면 그래프 추가, 아니면 보고서에서 제외 |
| 7/9 | 최종 PDF, ZIP, 링크 권한 점검 | 제출 후보본 |
| 7/10 | 재현 실행, 용량, 파일명, 링크 최종 확인 | 제출본 |

---

## 11. 작업 순서

실제 구현은 아래 순서로 진행한다.

1. `schemas.py`에 상태, 공격, threat, defense action, score 타입을 만든다.
2. `state_factory.py`에 baseline scenario를 만든다.
3. `redaction.py`에서 `world` 제거를 구현하고 테스트한다.
4. `catalog.py`에 공격 3종과 feasibility/weight/preferred_tags를 등록한다.
5. `mutations.py`에 공격 3종의 observed-only 변조를 구현한다.
6. `tagger.py`에 observed 기반 situation tag를 구현한다.
7. `invariants.py`에 공격명 비의존 탐지 규칙을 구현한다.
8. `defense_planner.py`에 최소 방어와 availability cost를 구현한다.
9. `scorer.py`에 승패 판정을 고정한다.
10. `hash_log.py`에 JSONL 해시 체인 로그를 구현한다.
11. `main.py`에서 seed 고정 라운드 루프를 실행한다.
12. `figures.py`에서 보고서용 PNG를 생성한다.
13. `README.md`에 실행 방법과 결과 파일 위치를 정리한다.
14. Docker 또는 `requirements.txt`로 재현성을 닫는다.

---

## 12. 테스트 계획

| 테스트 | 검증 내용 |
|---|---|
| `test_redaction.py` | Blue 입력에 `world`가 없고 scorer만 world 접근 |
| `test_seed_reproducibility.py` | 같은 seed에서 같은 JSONL과 summary 생성 |
| `test_attacks_e2e.py` | 공격 3종이 각각 target domain mismatch를 만든다 |
| `test_invariants.py` | Blue가 공격명을 보지 않고 위협을 탐지한다 |
| `test_scorer.py` | `RED_BREACH`, `RED_ATTRITION`, `BLUE`, `DRAW` 판정이 고정 조건대로 나온다 |
| `test_hash_log.py` | 로그 한 줄 변경 시 해시 체인 검증 실패 |

---

## 13. 보고서 구성 계획

예선 보고서는 안내서의 8항목 순서를 그대로 따른다.

| 항목 | 페이지 목표 | 넣을 증거 |
|---|---:|---|
| 1. 표지 | 1 | 팀명, 제목, 제출일 |
| 2. 목차 | 1 | 8항목 목차 |
| 3. 팀 구성 및 역할 | 2~3 | 팀원 전문성, 코드 소유권, 보고서 담당 |
| 4. 방산 분야 공격 시나리오 | 8~10 | 공격 3종 8필드, world/observed diff, 실행 로그 |
| 5. 공격 대응 방어 아키텍처 | 7~8 | 불변식, D/C/R 표, 방어 큐, availability |
| 6. AI 에이전트 설계 및 구현 | 7~8 | Red/Blue/Scorer 협력 구조, agent loop, decision_log |
| 7. 결론 및 향후 계획 | 2~3 | 기대효과, 한계, 본선 확장 |
| 8. 참고문헌 | 1~2 | NAVCEN, MAVLink, NIST, MITRE |

주장마다 반드시 로그, 코드, 그림 중 하나와 연결한다.

---

## 14. 리스크와 절단선

| 리스크 | 대응 |
|---|---|
| 구현 범위 과다 | 공격 3종, scorer, 그림 생성까지를 Must로 고정 |
| Blue가 world를 보는 설계 오류 | `test_redaction.py`를 첫날 작성 |
| 공격이 단순 기능 목록처럼 보임 | 보고서에서는 8필드 운용 서사로 설명 |
| 채점이 자의적으로 보임 | scorer 수식을 코드와 보고서에 동일하게 공개 |
| 대시보드에 시간 소모 | Streamlit은 Nice로 미루고 정적 PNG 먼저 |
| 공진화 증거 부족 | static vs coevolution 비교가 안 되면 보고서에서 주장 제외 |
| 참고문헌 약함 | `reference_sources.md`의 공식 출처만 기본 인용 |
| 제출 실수 | 7/9에 파일명, 용량, 링크 권한, ZIP 구성 점검 |

---

## 15. 완료 기준

아래가 모두 충족되면 예선 제출 가능한 상태로 본다.

1. 공격 3종이 모두 실행되고 `world`와 `blue_observed`의 차이를 만든다.
2. Blue 입력에 `world`가 없음을 테스트로 증명한다.
3. Blue가 공격명을 직접 보지 않고 불변식으로 탐지한다.
4. Detect/Contain/Recover action이 JSONL 로그에 남는다.
5. scorer가 승패를 고정 규칙으로 판정한다.
6. 동일 seed에서 동일 결과가 재현된다.
7. 보고서용 PNG가 자동 생성된다.
8. 보고서 8항목이 안내서 순서와 배점을 따른다.
9. 참고문헌과 표/그림/코드 출처가 들어간다.
10. ZIP 안에서 실행 방법이 재현된다.

---

## 16. 결론

이 프로젝트는 “AI가 믿는 관측값을 방어한다”는 컨셉과 “과잉 방어도 임무 실패”라는 차별점이 이미 강하다. 따라서 지금부터는 기능을 넓히기보다 아래 순서로 깊게 만든다.

```text
world/observed 분리
→ 공격 3종 E2E
→ 불변식 탐지와 최소 방어
→ scorer와 seed 로그
→ 보고서 PNG
→ 8항목 보고서
→ 제출 ZIP 재현성
```

핵심은 구현 자체가 아니라, 구현 결과가 보고서의 ④⑤⑥ 점수 근거로 직접 연결되게 만드는 것이다.
