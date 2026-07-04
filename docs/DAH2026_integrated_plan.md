# DAH 2026 통합 플래닝

기준일: 2026-07-04 KST  
현재 방향: 실행 가능한 **adaptive Red-Blue multi-agent simulation** 중심으로 저장소를 정리한다.

---

## 1. 중심 주장

```text
본 시스템은 단순 룰 기반 탐지기가 아니라, 공격 성공/탐지 피드백을 이용해 전략을 조정하는 adaptive Red-Blue multi-agent architecture이다.
```

이 표현은 현재 구현과 맞는다.

- Red Agent는 탐지 여부에 따라 공격 weight를 조정한다.
- adaptive stealth 모드에서 탐지된 공격을 stealth tactic으로 전환한다.
- Blue는 threat confidence와 domain trust로 방어 강도를 조절한다.
- Scorer는 공격 성공, 탐지 성공, 복구 성공, availability를 판정한다.
- Simulator는 이 과정을 hash-chain JSONL 로그로 남긴다.

---

## 2. 설계 원칙

| 원칙 | 내용 |
|---|---|
| 진실 분리 | Red와 Blue는 `world`를 보지 않는다 |
| observed-only attack | Red는 `blue_observed`만 바꾼다 |
| invariant-based defense | Blue는 공격명을 맞히지 않고 observed 내부 모순을 본다 |
| feedback adaptation | Red/Blue는 scorer 결과와 domain trust로 다음 판단을 조정한다 |
| mission-aware defense | 방어 action은 availability cost를 가진다 |
| reproducibility | seed와 hash-chain log로 결과를 재현한다 |

---

## 3. 에이전트 구성

| Agent | 입력 | 판단 | 출력 |
|---|---|---|---|
| Red Agent | redacted observed state, situation tags | attack weight, stealth tactic | observed mutation |
| Threat Detection Agent | observed state, history | invariant confidence | threats |
| Mission Monitor Agent | threats | mission impact | risks |
| Defense Planner Agent | threats, trust, availability | staged defense | defense actions |
| Incident Report Agent | threats, risks, score | event summary | incident report |
| Scorer | world, observed | objective verdict | feedback |

---

## 4. 공격 시나리오

| 공격 | 방산 운용상 의미 | Blue 탐지 단서 |
|---|---|---|
| `PRIORITY_POISONING` | 관제 AI가 잘못된 정찰 구역을 고르게 함 | 임무 우선순위 급변 |
| `TELEMETRY_FDI` | 복귀/안전모드 판단을 늦춤 | 배터리/모터/소모율 모순 |
| `TIME_DESYNC_REPLAY` | 과거 명령을 최신 명령처럼 보이게 함 | sequence regression, timestamp skew |

---

## 5. 방어 전략

Blue는 threat confidence와 domain trust를 함께 본다.

```text
낮은 confidence + 높은 trust
  -> OBSERVE_DOMAIN + REQUEST_REVALIDATION

높은 confidence 또는 낮은 trust
  -> QUARANTINE_FIELD / HOLD_COMMAND / FALLBACK_TO_TRUSTED_STATE
```

이 구조는 모든 이상을 무조건 차단하지 않기 때문에 과방어로 인한 `RED_ATTRITION`을 줄인다.

---

## 6. 실행/검증 계획

기본 실행:

```bash
PYTHONPATH=src python3 -m dah_flawless.main --seed 42 --rounds 5
```

강한 공방 시나리오:

```bash
PYTHONPATH=src python3 -m dah_flawless.main \
  --seed 42 \
  --rounds 5 \
  --scenario degraded_start \
  --red-stealth adaptive
```

테스트:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

대시보드:

```bash
PYTHONPATH=src streamlit run streamlit_app.py
```

---

## 7. 현재 저장소 구성

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

현재 GitHub 저장소에는 실행 가능한 시뮬레이터와 설계 문서만 둔다. 최종 제출물은 나중에 별도 작업으로 준비한다.

---

## 8. 공개 repo 체크리스트

- README의 실행 명령이 맞는가
- `requirements.txt`가 실제 의존성만 담는가
- `Dockerfile`이 존재하지 않는 폴더를 복사하지 않는가
- 생성 산출물이나 로컬 실행 결과가 git에 올라가지 않는가
- 테스트가 통과하는가
- `data/`, `.venv/`, `__pycache__/`, `.DS_Store`가 git에 올라가지 않는가

---

## 9. 보고서 작성 시 사용할 표현

```text
policy-based adaptive Red-Blue multi-agent architecture
```

사용하지 않을 표현:

```text
딥러닝 AI
강화학습 AI
실제 해킹 도구
실전 침투 자동화
```
