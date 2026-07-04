# DAH Flawless 구현 계획서

기준일: 2026-07-04 KST  
목표: 현재 저장소를 **실행 가능한 adaptive Red-Blue multi-agent 시뮬레이터**로 유지한다. GitHub에는 실행 코드와 설계 문서만 올린다.

---

## 1. 현재 포지셔닝

본 시스템은 단순 룰 기반 탐지기가 아니라, 공격 성공/탐지 피드백을 이용해 전략을 조정하는 **adaptive Red-Blue multi-agent architecture**이다.

정확한 표현:

```text
policy-based adaptive multi-agent simulation
```

과장하지 않을 표현:

```text
강화학습 AI, 딥러닝 AI, 실제 침투 도구
```

---

## 2. 유지할 핵심 구조

```text
Red Agent
  -> observed-only attack mutation
  -> detection feedback 기반 weight / stealth tactic 조정

Blue Agents
  -> observed-only invariant detection
  -> confidence / domain trust 기반 staged defense

Scorer
  -> world와 observed 비교
  -> attack / detection / recovery / availability 판정

Simulator
  -> 라운드 진행, 로그 생성, hash chain 부여
```

핵심 제약:

```text
Red는 world를 보지 않는다.
Blue도 world를 보지 않는다.
Scorer만 world를 본다.
```

---

## 3. 현재 디렉터리 기준

```text
README.md
Dockerfile
requirements.txt
pyproject.toml
streamlit_app.py
assets/
docs/
src/
tests/
tmp/pdfs/
```

실행에 필요한 코드는 `src/`, 검증은 `tests/`, 설명은 `README.md`와 `docs/`에 둔다.

---

## 4. 실행 흐름

```text
1. Environment가 world와 blue_observed를 만든다.
2. Red Agent가 redacted observed state와 situation tag를 보고 공격을 선택한다.
3. attack mutation은 blue_observed만 바꾼다.
4. Blue Agents는 redacted observed state와 history만 보고 threat를 만든다.
5. Defense Planner가 confidence와 domain trust에 따라 방어 action을 고른다.
6. Scorer가 world와 observed를 비교해 승패와 피드백을 만든다.
7. Simulator가 JSONL hash-chain 로그를 남긴다.
8. Red는 detection feedback으로 weight와 tactic을 조정한다.
```

---

## 5. 구현된 공격

| 공격 | 목적 | 조작 대상 |
|---|---|---|
| `PRIORITY_POISONING` | 임무 우선순위 오염 | `blue_observed.mission.area_priority` |
| `TELEMETRY_FDI` | 배터리/모터 텔레메트리 오염 | `blue_observed.telemetry.*` |
| `TIME_DESYNC_REPLAY` | sequence/timestamp 기반 replay | `blue_observed.c2_message`, `blue_observed.time` |

직접 복호화나 시스템 장악은 범위 밖으로 둔다.

---

## 6. 구현된 방어

| 방어 개념 | 구현 |
|---|---|
| observed-only detection | `blue/tagger.py`, `blue/invariants.py` |
| threat confidence | 불변식 증거 수와 capability 상태로 계산 |
| domain trust | 반복 의심 도메인의 신뢰도 하향 |
| staged defense | 낮은 확신은 관찰/재검증, 높은 확신은 격리/복구 |
| availability cost | 방어 비용이 임무 가용성을 낮춤 |
| hash-chain evidence | 로그 변조 검출 |

---

## 7. adaptive 증거

현재 로그에는 아래 필드가 들어간다.

```text
feedback
red_policy_state
blue_policy_state
decision_log
```

이 필드들이 보여주는 것:

- Red는 공격별 weight와 시도/탐지 통계를 가진다.
- Red는 detection feedback에 따라 weight를 올리거나 내린다.
- adaptive stealth 모드에서는 탐지된 공격을 stealth tactic으로 전환한다.
- `TELEMETRY_FDI`는 `probe_delta`를 조절하며 탐지 경계를 탐색한다.
- Blue는 confidence, domain trust, availability cost를 근거로 action을 고른다.

---

## 8. 검증 명령

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

대표 실행:

```bash
PYTHONPATH=src python3 -m dah_flawless.main --seed 42 --rounds 5
```

대시보드:

```bash
PYTHONPATH=src streamlit run streamlit_app.py
```

---

## 9. GitHub 업로드 기준

올릴 것:

```text
README.md
Dockerfile
requirements.txt
pyproject.toml
streamlit_app.py
assets/
docs/
src/
tests/
```

올리지 않을 것:

```text
.venv/
__pycache__/
.DS_Store
data/
dist/
local runtime outputs
generated archives
```

`tmp/pdfs/`는 예선 안내서 이미지이므로 공개 repo에는 선택 사항이다. 실행에는 필요 없다.

---

## 10. 다음 개선 후보

1. `tmp/pdfs/` 삭제 여부 결정
2. README에 `red_policy_state`, `blue_policy_state` 예시 추가
3. Streamlit에 policy state 전용 탭 추가
4. 여러 seed batch evaluator 추가
5. Docker 실행 확인
