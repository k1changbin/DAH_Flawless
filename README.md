# DAH Flawless — Red/Blue 사이버 AI 시뮬레이션

UAV·UGV·위성통신(SATCOM) 환경을 안전하게 추상화한 시뮬레이션 안에서 **Red AI가 Blue의 관측 입력을 오염**시키고 **Blue AI가 그 모순을 탐지·격리·복구**하는 적대적 공방을 재현한다. 실제 침투 도구가 아니라, "관측을 믿을 수 있는가(observe-integrity)"라는 문제를 AI 대 AI로 증명하는 연구용 시뮬레이터다.

- **Red**: `external_observe`(외부 신호/통신/메타데이터)의 값·시간·순서를 안전한 범위로 변조해 Blue의 임무 판단을 흔든다. 암호를 깨거나 시스템을 장악하지 않는다.
- **Blue**: `internal_observe`(Red가 못 건드리는 내부 앵커)와 관측 이력만으로 오염을 추정하고, ZTA(Zero Trust) 정책으로 오염 도메인을 제한·복구한다. 정답지(scorer truth)는 절대 못 본다.

---

## 빠른 시작 (심사·데모용)

전제: **Docker Desktop 실행 중.**

```bash
docker compose up frontend
```

→ 브라우저에서 **http://localhost:8080**

브라우저로 연 뒤에는 `F11`을 눌러 전체 화면으로 보는 것을 권장한다.

랜딩(시작) 화면 → **"시뮬레이션 진입"** → 3D 전술 대시보드가 뜬다.

| 영역 | 내용 |
|---|---|
| 좌측 RED OPS | 공격 벡터·현재 행동·mutation·목표/보상 |
| 중앙 3D 전장 | UAV·UGV·CMD LINK·BLUE C2 노드, 공격 흐름 라인, 탐지 펄스 |
| 우측 BLUE DEF | 의심도·ZTA 게이트 판정·방어 행동·예산 |
| 위성 창 | Suspicion 추이·ZTA 정책 히트맵·텔레메트리·이벤트 로그 |
| 하단 | 스텝 타임라인 + 스크러버 |

조작: `Space` 재생/정지, `←/→` 스텝 이동, 상단 라운드 입력/타임라인으로 라운드 이동, 배속 버튼으로 긴 흐름 스캔, `결과보기`로 승패·공격 선택·정책 분포 요약 확인. 종료는 `docker compose down`.

> 대시보드는 실제 백엔드 시뮬레이션 결과를 **재현 가능한 리플레이**로 시각화한다. `seed=42`, `clean_start`는 로컬에서 2000R까지 생성해 긴 학습 흐름을 볼 수 있고, 다른 seed/scenario는 가벼운 샘플 리플레이로 동작한다.

---

## 2000R 데이터 정책

2000R 원본 로그는 약 700MB, 프론트용 JSON도 약 80MB라 Git에 올리지 않는다. 저장소에는 생성 스크립트만 두고, 데모 머신에서 필요할 때 같은 seed/scenario로 다시 뽑는다.

```powershell
$env:PYTHONPATH='src'
python scripts/generate_2000_replay.py --rounds 2000 --seed 42 --scenario clean_start
```

생성 위치:

- `data/logs/round_2000_logs.jsonl`
- `data/logs/round_2000_summary.json`
- `data/frontend/runs/seed42_clean_start_2000.json`

새로 뽑은 뒤 프론트 번들과 Docker 서빙 파일을 갱신하려면:

```powershell
cd frontend
npm run build
cd ..
docker compose up -d --build frontend
```

---

## 아키텍처

```text
raw_world (규칙기반 생성, seed 고정)
  -> Feature Extractor -> State Adapter
  -> scorer_truth(state["world"])  +  blue_observed(internal/external)
  -> Situation Tagger
  -> Red Attack Selector / Blue Threat Detection
  -> Mutation(Red) / Defense·ZTA Gate(Blue)
  -> Scorer (승패·goal reward·mission impact·containment)
  -> Feedback -> Red/Blue 정책 가중치 업데이트 (다음 라운드에 반영)
```

핵심 용어 경계(위반 금지):

| 용어 | 의미 | 접근 권한 |
|---|---|---|
| `raw_world` | 현실 전장의 원천 신호·환경(RF·GNSS·SATCOM·C2 emission·날씨·지형) | generator/extractor/adapter |
| `scorer_truth` | 채점 기준 정답 상태. 호환성 때문에 `state["world"]` 키에 저장 | environment/scorer/admin 전용 |
| `blue_observed` | Blue AI가 받은 관측 입력 (내부+외부) | Red/Blue |
| `internal_observe` | 내부 센서/로컬 상태. **Red가 직접 조작 불가** → Blue의 신뢰 앵커 | Blue trust anchor |
| `external_observe` | 외부 신호/통신/원격 관측. **Red mutation 허용 표면** | Red mutation surface |

**불변식:** Blue는 `raw_world`와 `scorer_truth`를 절대 볼 수 없다. Red/Blue 입력에서 정답지는 redaction으로 제거된다. Red는 `external_observe`만 변조할 수 있다.

공격 3종(scripted 커버리지) + Goal Planner 기반 동적 목표 선택:
`TIME_DESYNC_REPLAY`(command), `TELEMETRY_FDI`(telemetry), `PRIORITY_POISONING`(mission).

---

## 실행 방식 요약

| 목적 | 명령 | 접근 |
|---|---|---|
| **최신 3D 대시보드 (권장)** | `docker compose up frontend` | http://localhost:8080 |
| 라이브 재실행 콘솔 (백업) | `docker compose up dashboard` | http://localhost:8501 (Streamlit) |
| CLI 시뮬레이션 1회 | `docker compose run --rm dah` | 로그 파일 출력 |

- `frontend` = 미리 빌드된 리플레이 대시보드(오프라인, 단일 파일).
- `dashboard` = Streamlit 콘솔. seed/라운드/시나리오를 바꿔 **실제로 다시 시뮬을 돌리고** 라운드별로 그려준다.
- `dah` = 배치 CLI. `data/logs/`에 JSONL 로그와 요약을 남긴다.

첫 실행은 이미지 빌드로 몇 분 걸리고, 이후엔 바로 뜬다.

---

## 로컬(파이썬)에서 직접 돌리기

전제: Python 3.11+ (개발은 3.12에서 확인).

```powershell
# 저장소 루트에서
$env:PYTHONPATH='src'

# 기본 5라운드 시뮬레이션
python -m dah_flawless.main --seed 42 --rounds 5 --reset-logs `
  --out data/logs/round_logs.jsonl --summary data/logs/summary.json

# 동적 combat 리플레이 + 프론트엔드 JSON 재생성 (대시보드 데이터)
python -c "from pathlib import Path; from dah_flawless.environment.round_combat_runner import run_combat_rounds; run_combat_rounds(seed=42, rounds=6, max_steps=30, log_path=Path('data/logs/round_logs.jsonl'), summary_path=Path('data/logs/summary.json'), frontend_log_path=Path('data/frontend/combat_replay.json'))"

# Streamlit 대시보드 (로컬)
streamlit run streamlit_app.py
```

기타 실행 옵션:

```powershell
# 30-step 에피소드
python -m dah_flawless.main --seed 42 --episodes 2 --steps-per-episode 30

# 학습 cadence (Blue-only -> Red-only -> fixed-eval) + holdout 일반화 평가
python -m dah_flawless.main --seed 42 --training-schedule --steps-per-episode 30 --holdout-eval

# 특정 시나리오 (clean_start / degraded_start / satcom_delay / gnss_degraded /
#                c2_metadata_noisy / telemetry_conflict / low_trust_start)
python -m dah_flawless.main --seed 42 --rounds 5 --scenario satcom_delay
```

프론트엔드를 수정할 경우:

```powershell
cd frontend
npm install
npm run dev        # 개발 서버
npm run build      # dist/index.html 단일 번들 재생성 (Docker가 이걸 서빙)
```

## 프로젝트 구조

```text
src/dah_flawless/
  world/          raw_world generator·feature extractor·state adapter
  attacks/        goal planner·attack selector·mutation engine·mutation policy
  blue/           threat detection·goal consistency·defense·ZTA gate·feedback learner
  scoring/        scorer·goal scorer·mission impact·causal consistency
  environment/    round combat runner·episode runner·training scheduler·holdout evaluator
  reporting/      report generator·frontend_log projection
  llm/            역할별 외부 LLM 어댑터 + 순수코드 fallback
frontend/         React 19 + Vite + R3F 3D 대시보드 (dist/index.html 단일 번들)
streamlit_app.py  라이브 재실행 콘솔 (백업)
```

주요 로그 필드 대표:

| 필드 | 의미 |
|---|---|
| `blue_input_redacted` | Blue 입력에서 scorer truth가 제거됐는지(불변식 검증) |
| `red_policy_state` / `blue_policy_state` | Red/Blue 정책 가중치·민감도·신뢰·피드백 카운트 |
| `red_goal` / `score.goal_success` / `score.goal_reward` | Red가 고른 cyber-effect 목표와 달성·보상 |
| `combat_steps` | 스텝별 Red/Blue action·suspicion·budget·중간 score |
| `score.containment_score` | Blue가 완전 복구 전 단계에서 effect를 억제한 정도 |
| `score.winner_side` / `winner_detail` | 승패 주체와 세부 결과(BREACH·RECOVERY·CONTAINMENT 등) |
| `score.evidence.mission_impact` | 오염이 임무 판단/안전/명령 freshness/가용성에 준 영향 |
| `zta_policy.per_domain` | 도메인별 ZTA 판정과 정답 여부 |

---

## 구현 범위 (정직한 경계)

**구현됨:** 규칙기반 raw_world 생성, observe mutation 엔진·정책(clamp/reject), Red goal planner·attack selector, Blue 탐지·ZTA 게이트·단계 방어·feedback 학습, goal-aware/mission-impact scorer, 라운드별 정책 coevolution, 학습 스케줄·holdout 일반화 평가, 로그 해시 체인, 3D 리플레이 대시보드.

**아직 아님(다음 단계 설계):** VAE 기반 world generator, 실제 RF/API adapter, 실제 네트워크 공격 실행, 신경망 기반 정책. 외부 LLM 리뷰어는 선택 사항이며 실패 시 오프라인 heuristic으로 fallback한다.

**표현 원칙:** Red는 관측값·시간·순서·메타데이터를 안전하게 변조할 뿐 시스템을 장악하지 않는다. `scorer_truth`는 채점용 정답지이지 Blue 화면이 아니다. 실제 RF/exploit과 학습형 고도화는 "현재 구현"이 아니라 "확장 설계"로 구분해 설명한다.
