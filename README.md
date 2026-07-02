# DAH Flawless MVP 사용 설명서

이 저장소는 `docs/implementation_plan.md`를 바탕으로 만든 **Red/Blue 공격·방어 AI 시뮬레이션 MVP**입니다. 목표는 예선 보고서의 핵심 평가 항목인 ④ 공격 시나리오, ⑤ 방어 아키텍처, ⑥ AI 에이전트 설계에 넣을 실행 로그와 시각화 증거를 만드는 것입니다.

이 MVP는 실제 침투 도구가 아닙니다. 방산 운용 상황을 단순화한 시뮬레이션 안에서, 공격 AI가 Blue 관제 AI의 관측값을 오염시키고 방어 AI가 그 관측값의 불변식 위반을 탐지·격리·복구하는 구조를 보여줍니다.

---

## 1. 한 줄 요약

```text
Red Agent가 blue_observed를 공격한다.
Blue Agents는 world를 보지 않고 observed 내부 모순만으로 탐지·방어한다.
Scorer만 world와 blue_observed를 비교해 승패와 로그 증거를 만든다.
```

---

## 2. 핵심 개념

### 2.1 world

`world`는 시뮬레이션 내부의 실제 상태입니다. 실제 UAV 배터리, 모터 상태, 정상 명령 번호, 원래 임무 우선순위가 들어 있습니다.

중요한 점:

- Red Agent는 `world`를 직접 보지 않습니다.
- Blue Agents도 `world`를 직접 보지 않습니다.
- Scorer만 `world`를 볼 수 있습니다.

### 2.2 blue_observed

`blue_observed`는 Blue 관제 AI가 받은 관측값입니다. Red Agent의 공격 대상입니다.

예시:

```text
world.uav.battery_percent = 20
blue_observed.telemetry.battery_percent = 82
```

이 경우 실제 배터리는 20%지만, Blue 관제 AI는 82%라고 믿게 됩니다.

### 2.3 Red Agent

Red Agent는 공격 AI입니다.

역할:

- 현재 관측 상태와 situation tag를 본다.
- 공격 후보 중 적합한 공격을 선택한다.
- `blue_observed`만 변조한다.
- Scorer의 성공/실패 피드백으로 다음 공격 가중치를 조정한다.

현재 구현된 공격:

| 공격 | 목적 | 조작 대상 |
|---|---|---|
| `PRIORITY_POISONING` | 관제 AI가 잘못된 임무 구역을 우선하도록 유도 | `blue_observed.mission.area_priority` |
| `TELEMETRY_FDI` | 배터리·모터 상태를 거짓 보고하게 함 | `blue_observed.telemetry.*` |
| `TIME_DESYNC_REPLAY` | 과거 명령/상태를 최신처럼 처리하게 함 | `sequence_number`, `timestamp`, `command` |

현재 MVP에서는 보고서 증거를 확실히 만들기 위해 첫 3라운드는 공격 3종이 한 번씩 나오도록 고정되어 있습니다. 4라운드부터는 situation tag와 가중치 기반으로 공격을 고릅니다.

### 2.4 Blue Agents

Blue 쪽은 하나의 거대한 함수가 아니라 4개 역할로 나뉜 방어 AI입니다.

| Agent | 역할 |
|---|---|
| Threat Detection Agent | observed 기반 태그와 불변식으로 위협 탐지 |
| Mission Monitor Agent | 위협이 임무에 주는 영향 계산 |
| Defense Planner Agent | 최소 방어 action 선택 |
| Incident Report Agent | 보고서용 사건 요약 생성 |

Blue는 공격명을 직접 맞히는 방식이 아닙니다. `world`도 보지 않습니다. 대신 아래 같은 모순을 봅니다.

- 배터리 값, 소모율, 모터 상태가 물리적으로 맞는가
- 임무 우선순위가 근거 없이 급변했는가
- sequence number와 timestamp가 역행했는가
- 지연, 패킷 손실, 큐 적체가 커졌는가

### 2.5 Scorer

Scorer는 심판입니다.

역할:

- `world`와 `blue_observed`를 비교한다.
- Red 공격이 실제로 관측값 불일치를 만들었는지 확인한다.
- Blue가 탐지했는지 확인한다.
- 방어 비용 때문에 availability가 너무 낮아졌는지 확인한다.
- 라운드별 승패를 판정한다.

승패 값:

| 값 | 의미 |
|---|---|
| `RED_BREACH` | 공격 성공, 탐지 실패 |
| `RED_ATTRITION` | 방어 비용 때문에 임무 가용성 고갈 |
| `BLUE` | 탐지 성공, 임무 가용성 유지 |
| `BLUE_RECOVERY` | 탐지 후 신뢰 상태를 복구 |
| `DRAW` | 명확한 승패 없음 |

---

## 3. 폴더 구조

```text
DAH_Flawless/
  README.md
  Dockerfile
  streamlit_app.py
  requirements.txt
  pyproject.toml
  assets/
  data/
    logs/
      round_logs.jsonl
      summary.json
  dist/
    DAH2026_소스코드_DAH_Flawless.zip
  docs/
  reports/
    figures/
      scoreboard.svg
      scoreboard.png
      world_observed_diff.svg
      world_observed_diff.png
      availability.svg
      availability.png
      agent_architecture.svg
      agent_architecture.png
      detect_contain_recover.svg
      detect_contain_recover.png
      attack_flow.svg
      attack_flow.png
  scripts/
  src/
    dah_flawless/
      main.py
      config.py
      schemas.py
      attacks/
      blue/
      environment/
      scoring/
      reports/
  tests/
```

주요 파일:

| 파일 | 설명 |
|---|---|
| `streamlit_app.py` | Streamlit 대시보드 |
| `src/dah_flawless/main.py` | CLI 실행 진입점 |
| `src/dah_flawless/environment/simulator.py` | 라운드 기반 시뮬레이터 |
| `src/dah_flawless/attacks/red_agent.py` | Red Agent 공격 선택 |
| `src/dah_flawless/attacks/mutations.py` | 공격별 observed 변조 |
| `src/dah_flawless/blue/` | Blue 탐지·임무분석·방어계획 |
| `src/dah_flawless/scoring/scorer.py` | 승패 판정 |
| `src/dah_flawless/environment/hash_log.py` | JSONL 해시 체인 로그 |
| `tests/` | 재현성, redaction, scorer, 공격 E2E 테스트 |

---

## 4. 빠른 실행

터미널에서 아래 순서로 실행합니다.

```bash
cd /Users/gwonchangbin/projects/DAH_Flawless
PYTHONPATH=src python3 -m dah_flawless.main --seed 42 --rounds 5 \
  --out data/logs/round_logs.jsonl \
  --summary data/logs/summary.json
```

실행되면 아래 파일이 갱신됩니다.

```text
data/logs/round_logs.jsonl
data/logs/summary.json
```

예상 출력 예시:

```text
wrote 5 rounds to data/logs/round_logs.jsonl
wrote summary to data/logs/summary.json
```

---

## 5. Streamlit 대시보드 실행

### 5.1 최초 1회 설치

```bash
cd /Users/gwonchangbin/projects/DAH_Flawless
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 5.2 대시보드 실행

```bash
cd /Users/gwonchangbin/projects/DAH_Flawless
PYTHONPATH=src .venv/bin/streamlit run streamlit_app.py
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8501
```

### 5.3 앱 왼쪽 입력값

| 입력 | 의미 |
|---|---|
| `Seed` | 같은 결과를 재현하기 위한 난수 고정값 |
| `Rounds` | 실행할 공방 라운드 수 |
| `Log path` | JSONL 로그를 저장하고 읽을 경로 |
| `Run simulation` | 현재 seed/rounds로 시뮬레이션 실행 |

주의:

- `Run simulation`을 누르면 `data/logs/round_logs.jsonl`과 `data/logs/summary.json`이 새 결과로 덮입니다.
- 예를 들어 `Rounds=1`로 실행하면 summary도 1라운드 결과만 보여줍니다.

---

## 6. 대시보드 읽는 법

### 6.1 상단 요약 카드

| 카드 | 의미 |
|---|---|
| `라운드 수` | 실행된 공방 턴 수 |
| `Blue 탐지율` | Blue가 공격을 탐지한 비율 |
| `Red 공격 반영률` | Red가 관측값 오염을 실제로 만든 비율 |
| `임무 가용성` | 방어 비용 차감 후 남은 availability |
| `로그 무결성` | JSONL 해시 체인이 깨지지 않았는지 여부 |

### 6.2 Overview 탭

전체 결과를 빠르게 보는 화면입니다.

확인할 것:

- 라운드별 공격명
- target domain
- winner
- attack success
- detection success
- availability
- 공격 분포
- 승패 분포

### 6.3 Timeline 탭

각 라운드를 펼쳐서 사건 흐름을 봅니다.

확인할 것:

- Red가 어떤 공격을 했는지
- 어떤 situation tag가 붙었는지
- Blue가 어떤 threat를 냈는지
- 어떤 defense action을 선택했는지
- Incident Report가 어떻게 요약했는지

### 6.4 Scorer/Admin Diff 탭

이 탭은 **Blue가 보는 화면이 아닙니다.**

Scorer 또는 보고서 작성자가 증거를 확인하기 위한 관리자 화면입니다.

확인할 것:

- trusted value: `world` 기준값
- observed value: Blue가 받은 관측값
- mismatch 여부
- `blue_input_redacted`가 `true`인지 여부

보고서에는 이 탭의 정보를 “Scorer/Admin View”로 명확히 표기해야 합니다. 그렇지 않으면 Blue가 정답을 보고 탐지한 것처럼 오해될 수 있습니다.

### 6.5 Charts 탭

시각적으로 결과를 확인하는 화면입니다.

확인할 것:

- availability 곡선
- 탐지 성공/실패 수
- 공격 반영 성공/실패 수

### 6.6 Decision Logs 탭

AI Agent의 판단 로그를 보는 화면입니다.

확인할 것:

- Red Agent가 어떤 이유로 공격을 선택했는지
- Red Agent가 성공/실패 피드백으로 가중치를 어떻게 바꿨는지
- Threat Detection Agent가 어떤 태그와 불변식을 확인했는지
- Defense Planner Agent가 어떤 방어 action을 골랐는지

---

## 7. seed 설명

`seed`는 같은 결과를 다시 만들기 위한 난수 고정값입니다.

예시:

```bash
PYTHONPATH=src python3 -m dah_flawless.main --seed 42 --rounds 5
```

같은 코드와 같은 `seed`, 같은 `rounds`로 실행하면 같은 로그와 같은 summary가 나와야 합니다.

보고서에서는 이렇게 설명할 수 있습니다.

```text
본 MVP는 seed를 고정해 동일 조건에서 동일 JSONL 로그와 scorer 결과가 재현되도록 설계했다.
```

---

## 8. rounds 설명

`rounds`는 공방 라운드 수입니다.

권장:

| 목적 | 권장 rounds |
|---|---:|
| 공격 3종 증거 확보 | 3 |
| 가중치 기반 선택 관찰 | 6 이상 |
| 짧은 데모 | 3 |
| 보고서용 그래프 | 5~10 |

현재 구현상 첫 3라운드는 공격 3종을 모두 보여주기 위해 고정 순서입니다.

```text
1라운드: PRIORITY_POISONING
2라운드: TELEMETRY_FDI
3라운드: TIME_DESYNC_REPLAY
```

4라운드부터는 situation tag와 가중치 기반 선택으로 넘어갑니다.

---

## 9. CLI 옵션

```bash
PYTHONPATH=src python3 -m dah_flawless.main \
  --seed 42 \
  --rounds 5 \
  --out data/logs/round_logs.jsonl \
  --summary data/logs/summary.json
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--seed` | `42` | 재현용 seed |
| `--rounds` | `5` | 실행할 라운드 수 |
| `--out` | `data/logs/round_logs.jsonl` | 라운드 로그 저장 경로 |
| `--summary` | `data/logs/summary.json` | 요약 저장 경로 |

---

## 10. 로그 파일 해석

### 10.1 round_logs.jsonl

`data/logs/round_logs.jsonl`은 라운드별 상세 로그입니다. 한 줄이 한 라운드입니다.

주요 필드:

| 필드 | 의미 |
|---|---|
| `round` | 라운드 번호 |
| `seed` | 실행 seed |
| `situation_tags` | observed 기반 상황 태그 |
| `attack` | Red 공격 정보 |
| `threats` | Blue 탐지 결과 |
| `mission_risks` | 임무 영향 평가 |
| `defense_actions` | Blue 방어 조치 |
| `score` | Scorer 판정 |
| `incident_report` | 보고서용 사건 요약 |
| `decision_log` | Agent 판단 로그 |
| `blue_input_redacted` | Blue 입력에서 world 제거 여부 |
| `prev_hash` / `this_hash` | 해시 체인 무결성 값 |

### 10.2 summary.json

`data/logs/summary.json`은 전체 실행 요약입니다.

주요 필드:

| 필드 | 의미 |
|---|---|
| `rounds` | 총 라운드 수 |
| `winners` | 승패 판정별 개수 |
| `attacks` | 공격별 실행 횟수 |
| `detection_rate` | 탐지 성공률 |
| `attack_success_rate` | 공격 반영률 |
| `final_availability` | 마지막 라운드 availability |
| `min_availability` | 실행 중 최저 availability |

---

## 11. 그림 생성

Streamlit 외에도 보고서에 넣을 수 있는 SVG/PNG 그림을 생성할 수 있습니다.

```bash
cd /Users/gwonchangbin/projects/DAH_Flawless
PYTHONPATH=src python3 -m dah_flawless.reports.figures \
  --log data/logs/round_logs.jsonl \
  --out-dir reports/figures
```

생성물:

| 파일 | 내용 |
|---|---|
| `reports/figures/scoreboard.svg/.png` | 라운드별 공격/승패/availability |
| `reports/figures/world_observed_diff.svg/.png` | Scorer/Admin용 trusted vs observed 비교 |
| `reports/figures/availability.svg/.png` | availability 곡선 |
| `reports/figures/agent_architecture.svg/.png` | Red/Blue/Scorer 협력 구조와 truth boundary |
| `reports/figures/detect_contain_recover.svg/.png` | 공격별 Detect/Contain/Recover 증거 |
| `reports/figures/attack_flow.svg/.png` | 공격 흐름 요약 |

Pillow가 설치되어 있으면 PNG가 같이 생성됩니다. `requirements.txt` 설치 환경에서는 PNG 생성을 기본 지원합니다.

---

## 12. 테스트

```bash
cd /Users/gwonchangbin/projects/DAH_Flawless
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests
```

현재 테스트:

| 테스트 | 검증 내용 |
|---|---|
| `test_redaction.py` | Blue 입력에 `world`가 없는지 |
| `test_attacks_e2e.py` | 공격 3종 E2E와 탐지/판정 |
| `test_seed_reproducibility.py` | 같은 seed에서 같은 결과가 나오는지 |
| `test_scorer.py` | 승패 판정 규칙 |
| `test_hash_log.py` | 로그 해시 체인 변조 탐지 |

정상 출력:

```text
Ran 6 tests
OK
```

---

## 13. 보고서에 쓰는 방법

이 MVP는 보고서에서 아래 주장들의 증거로 사용할 수 있습니다.

| 보고서 주장 | 사용할 증거 |
|---|---|
| Red는 Blue 관측값을 오염시킨다 | `attack`, `score.evidence.observed_value` |
| Blue는 world를 보지 않는다 | `blue_input_redacted=true`, `test_redaction.py` |
| Blue는 공격명을 맞히지 않고 불변식으로 탐지한다 | `situation_tags`, `threats`, `decision_log` |
| 방어는 비용을 가진다 | `defense_actions.availability_cost`, `score.availability` |
| 과방어는 실패가 될 수 있다 | `RED_ATTRITION`, availability 곡선 |
| 결과는 재현 가능하다 | `seed`, `test_seed_reproducibility.py`, 해시 체인 |
| 로그는 변조 검출이 가능하다 | `prev_hash`, `this_hash`, `test_hash_log.py` |

보고서에 넣을 때 주의할 점:

- `Scorer/Admin Diff`는 Blue 화면이 아니라 채점·증거 화면이라고 명시합니다.
- `world`와 `blue_observed`를 구분해서 설명합니다.
- Streamlit 화면보다 JSONL 로그와 테스트 결과를 더 중요한 증거로 둡니다.

---

## 14. 자주 생기는 질문

### Q1. 이게 진짜 AI인가?

LLM이나 딥러닝 모델은 아닙니다. 현재 MVP는 **정책 기반 자율 에이전트**입니다.

AI Agent라고 설명할 수 있는 이유:

- 관측한다: observed state와 situation tag를 읽음
- 판단한다: 공격/탐지/방어 action을 선택함
- 행동한다: observed 변조 또는 방어 action 적용
- 피드백을 받는다: scorer 결과로 Red 가중치 조정
- 로그를 남긴다: `decision_log`

### Q2. Red가 랜덤으로 공격하는 것 아닌가?

아닙니다. Red는 situation tag와 공격별 가중치를 사용합니다.

다만 첫 3라운드는 보고서 증거 확보를 위해 공격 3종을 한 번씩 강제로 실행합니다. 4라운드부터는 현재 상황 태그와 가중치 기반으로 선택합니다.

### Q3. Blue가 정답을 보고 막는 것 아닌가?

아닙니다. Blue 입력에는 `world`가 제거됩니다.

검증 근거:

- `environment/redaction.py`
- `test_redaction.py`
- 로그의 `blue_input_redacted=true`

### Q4. Scorer/Admin Diff는 왜 world를 보여주나?

그 탭은 Blue용 화면이 아닙니다. 보고서 작성자와 scorer가 공격 성공 여부를 검증하기 위한 증거 화면입니다.

### Q5. availability는 무엇인가?

임무 가용성입니다. 방어 action은 비용을 가지며, 모든 의심 상황에서 강한 방어만 쓰면 availability가 내려갑니다. availability가 너무 낮아지면 Blue가 공격을 막아도 `RED_ATTRITION`으로 판정될 수 있습니다.

---

## 15. 문제 해결

### Streamlit이 설치되어 있지 않다고 나올 때

```bash
cd /Users/gwonchangbin/projects/DAH_Flawless
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'dah_flawless'`

`PYTHONPATH=src`를 붙여 실행합니다.

```bash
PYTHONPATH=src python3 -m dah_flawless.main
```

Streamlit도 마찬가지입니다.

```bash
PYTHONPATH=src .venv/bin/streamlit run streamlit_app.py
```

### 앱에서 값이 이상하게 보일 때

왼쪽의 `Rounds` 값과 `Seed` 값을 확인합니다. `Run simulation`을 누르면 현재 값으로 로그가 덮입니다.

### 8501 포트가 이미 사용 중일 때

다른 포트로 실행합니다.

```bash
PYTHONPATH=src .venv/bin/streamlit run streamlit_app.py --server.port 8502
```

브라우저 주소:

```text
http://127.0.0.1:8502
```

### 로그 무결성이 깨졌다고 나올 때

`round_logs.jsonl`이 수동으로 수정됐거나 일부 줄이 사라졌을 수 있습니다. 다시 실행해 로그를 재생성합니다.

```bash
PYTHONPATH=src python3 -m dah_flawless.main --seed 42 --rounds 5
```

---

## 16. 현재 MVP의 한계

현재 버전은 예선 보고서 증거용 MVP입니다.

한계:

- 실제 UAV/GCS 네트워크에 연결하지 않습니다.
- LLM 기반 추론은 사용하지 않습니다.
- 공격은 안전한 시뮬레이션 mutation으로만 구현되어 있습니다.
- 첫 3라운드는 공격 3종 증거 확보를 위해 고정 순서입니다.
- Streamlit은 데모와 분석용이며, 최종 평가는 보고서의 로그·그림·테스트 증거와 함께 설명해야 합니다.

확장 가능 항목:

- static vs coevolution 비교 실험
- 여러 seed 집계 그래프
- 더 많은 공격 카탈로그
- 방어 큐 지연/슬롯 포화 시나리오
- PDF 보고서 자동 생성

---

## 17. 추천 데모 순서

심사나 팀원 설명 때는 아래 순서로 보여주면 됩니다.

1. `Overview`에서 전체 라운드 결과를 보여준다.
2. `Timeline`에서 한 라운드를 펼쳐 Red 공격과 Blue 방어 action을 설명한다.
3. `Scorer/Admin Diff`에서 world와 observed가 어떻게 달라졌는지 보여준다.
4. 이 화면은 Blue가 보는 화면이 아니라 scorer 증거 화면이라고 설명한다.
5. `Decision Logs`에서 Agent가 판단 로그를 남긴다는 점을 보여준다.
6. 터미널에서 테스트를 실행해 `6 tests OK`를 보여준다.
7. `round_logs.jsonl`의 `prev_hash`/`this_hash`로 로그 무결성까지 설명한다.

---

## 18. 제출 ZIP에 넣을 항목

예선 부가자료 ZIP에는 최소한 아래를 넣습니다.

```text
README.md
requirements.txt
streamlit_app.py
src/
tests/
data/logs/round_logs.jsonl
data/logs/summary.json
reports/figures/
reports/evidence_trace.md
reports/submission_checklist.md
reports/prelim_report_draft.md
reports/DAH2026_prelim_report_DAH_Flawless_draft.pdf
Dockerfile
scripts/build_submission_zip.py
scripts/render_report_pdf.py
```

`.venv/`, `__pycache__/`, `.DS_Store`는 제출 ZIP에서 제외합니다.
