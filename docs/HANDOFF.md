# DAH Flawless Handoff

최종 갱신: 2026-07-10 (Codex 이어받음: 60R 밸런스 리플레이 + seed/scenario 선택 UI + 2000R 대응 학습 스냅샷 레일, `docker` 브랜치)

## 2026-07-10 Codex 이어받은 세션 — 밸런스 리플레이 재생성 완료

### 한 줄 현황
`data/frontend/combat_replay.json`을 seed 42, 60라운드, `max_steps=30`, `min_steps=4`로 재생성했고 `frontend/dist/index.html`을 다시 빌드했다. 백엔드 파이썬·스코어링·JSON 스키마는 건드리지 않았다.

### 실행 결과
- 생성 명령:
  `PYTHONPATH=src python -c "from pathlib import Path; from dah_flawless.environment.round_combat_runner import run_combat_rounds; run_combat_rounds(seed=42, rounds=60, max_steps=30, min_steps=4, log_path=Path('data/logs/round_logs.jsonl'), summary_path=Path('data/logs/summary.json'), frontend_log_path=Path('data/frontend/combat_replay.json'))"`
- 전체 승패: BLUE 22 / RED 29 / DRAW 9.
- 구간 흐름: R1-R10 BLUE 1 / RED 7 / DRAW 2, R41-R50 BLUE 7 / RED 2 / DRAW 1, R51-R60 BLUE 4 / RED 4 / DRAW 2. 초반 Red 우세 후 후반 Blue 학습 반전이 화면에서 보인다.
- `npm.cmd run build` 통과. PowerShell에서는 `npm.ps1` 실행 정책 때문에 `npm run build` 대신 `npm.cmd run build` 사용.
- Playwright 검증 통과:
  - `node scripts/verify.mjs tmp\verify-60r.png --round 45 --step 3 --focus BLUE` → console clean.
  - `node scripts/verify.mjs tmp\verify-landing-60r.png --landing` → console clean.
- 랜딩 ROUNDS는 60으로 표시되고, 상단 라운드 네비는 기존 `overflow-x-auto` 스크롤로 정상 동작한다.

### seed+시나리오 드롭다운 완료
- 랜딩 화면에 Seed/Scenario select를 추가했다.
- 포함된 run:
  - seed 42 / clean_start: 60R, BLUE 22 / RED 29 / DRAW 9.
  - seed 42 / satcom_delay: 30R.
  - seed 42 / telemetry_conflict: 30R.
  - seed 99 / clean_start: 30R.
  - seed 99 / satcom_delay: 30R.
  - seed 99 / telemetry_conflict: 30R.
- `frontend/src/data.ts`는 단일 replay export에서 `RUNS`, `getReplay(runId)`, `getRound(runId, roundIdx)`, `getStep(runId, roundIdx, stepIdx)` 구조로 확장했다.
- `frontend/src/store/useReplayStore.ts`는 `runId`, `seed`, `scenario`, `setRunSelection()`을 가진다. run 전환 시 round/step/play/focus를 초기화한다.
- `CommandBar`, `Landing`, `Mugyeol`, `CenterScene`, `SidePanel`, `Satellites`, `TimelineLane`, `BattlefieldScene`은 현재 runId를 기준으로 데이터를 읽는다.
- 추가 검증:
  - `node scripts/verify.mjs tmp\verify-multirun-default.png --round 45 --step 3 --focus BLUE` → console clean.
  - seed 99 / satcom_delay 선택 후 진입하는 Playwright 체크 → `tmp\verify-multirun-s99-satcom.png`, console clean.

### 2000R 대응 학습 스냅샷 레일 완료
- `frontend/src/learning.ts` 추가. `MAX_LEARNING_ROUNDS = 2000`으로 두고, 전체 라운드를 그대로 버튼화하지 않고 대표 스냅샷을 자동 선택한다.
- 샘플링 기준: 시작/초반/구간 샘플/끝 + 첫 BLUE 승리 + rolling window 기준 BLUE 우세 전환점 + 현재 라운드.
- `CommandBar`의 전체 라운드 버튼 목록을 `LearningPath`로 교체했다. 상단에는 승패 밀도 바, 대표 라운드 버튼, `first BLUE`, `shift` 요약, 현재 phase(`RED PRESSURE`, `BLUE LEARNING`, `BLUE MOMENTUM`)가 표시된다.
- 대표 버튼에 없는 임의 라운드도 볼 수 있도록 `R` 직접 이동 입력을 넣었다. 기존 `scripts/verify.mjs --round N`도 이 입력을 사용하도록 수정했다.
- 랜딩에 선택 run의 `Learning arc` 프리뷰를 추가했다.
- 검증:
  - `npm.cmd run build` 통과.
  - `node scripts/verify.mjs tmp\verify-learning-landing.png --landing` → console clean.
  - `node scripts/verify.mjs tmp\verify-learning-r45.png --round 45 --step 3 --focus BLUE` → console clean.
  - seed 99 / satcom_delay 선택 + R20 직접 이동 Playwright 체크 → console clean.
  - 390x844 모바일 폭 + R45 직접 이동 Playwright 체크 → console clean.

### 다음 할 일
1. 커밋 시 주의: `frontend/dist/index.html`은 gitignore 대상이라 `git add -f frontend/dist/index.html` 필요. `data/frontend/combat_replay.json`과 `data/frontend/runs/*.json`은 `.gitignore` 예외로 추적 가능하게 열어두었다.
2. 선택 run을 더 늘릴 경우 번들 크기 확인. 현재 다중 run 포함 후 `frontend/dist/index.html`은 약 8.36MB.
3. 실제 1000~2000R full combat replay를 번들에 넣으면 HTML이 커질 수 있다. 장기적으로는 full timeline JSON 대신 summary/bin + selected detail rounds 형태로 projection을 분리하는 것이 좋다.
4. 남은 폴리시 후보는 아래 "남은 폴리시" 섹션 참고.

## 2026-07-10 세션 — docker 배포 + 프론트 최적화 + 밸런스 진단 (`docker` 브랜치)

> **다음 세션은 Codex에서 이어감. 아래 "다음 할 일"의 밸런스 재생성부터 시작하면 됨.**

### 한 줄 현황
docker로 최신 React 대시보드가 뜨게 배포 완료(`docker compose up frontend` → :8080). 렉·화질 수정 끝. **밸런스 문제(리플레이에서 Blue가 안 이김)는 원인 진단 + 무위험 해법(라운드 늘리기)까지 확인했고, 실제 재생성은 아직 안 함.**

### 이번 세션 커밋 (origin/docker, 순서대로)
- `a1e3dfb` — docker `frontend` 서비스(:8080) 추가. React 단일 번들 서빙.
- `4e182cb` — 렉 최적화: backdrop-blur xl→md, 캔버스 resize debounce 200.
- `4c1b881` — README 전면 재작성(심사용, docker frontend 우선). 하드코딩 경로·테스트수(150→185) 수정.
- `e7e924c` — 3D 화질 복원(antialias 재활성, dpr [1,2]) + 랜딩 헤딩 줄바꿈.

### docker 배포 구조 (중요)
- 한 이미지 `dah-flawless:local` 공유, 서비스 3개: `frontend`(:8080, 권장, `python -m http.server`로 `frontend/dist` 서빙) / `dashboard`(:8501, 백업 streamlit, 라이브 재실행) / `dah`(CLI 1회).
- **`frontend/dist/index.html`은 gitignore라 `git add -f`로 강제 커밋해야 clone→docker 빌드가 됨** (Dockerfile이 COPY). dist는 빌드 시 `combat_replay.json`을 인라인 → 데이터 바꾸면 반드시 `cd frontend && npm run build` 후 `git add -f dist`.
- `.dockerignore`에 frontend/node_modules 추가. **클린룸(GitHub 재클론 no-cache 빌드→실행) 검증 통과** = 남이 클론해서 docker로 돌리면 됨.
- 옛날 대시보드 = streamlit(창빈이 본 R2000 렉은 그의 data 볼륨에 쌓인 옛 로그였음). 지금것 = React 프론트.

### 렉/화질 수정 상세 (`frontend/src`)
- `scene/BattlefieldScene.tsx`: `dpr=[1,2]`, `antialias:true`(화질 핵심), `performance.min:0.5`(부하 시 자동 강등), `resize={{debounce:200}}`(패널 width 스프링 중 WebGL 버퍼 재할당 방지 = 창 전환 렉 해소), `powerPreference:high-performance`. `preserveDrawingBuffer:true`는 유지(verify 스크린샷용, 성능 여지 있음).
- `HudFrame.tsx`/`SidePanel.tsx`/`CommandBar.tsx`: `backdrop-blur-xl`→`backdrop-blur-md`(상시 렌더 캔버스 위 재합성 비용 절반).
- `SidePanel.tsx`: RedContent/BlueContent 중복 zustand 구독 제거(`round`를 prop으로).
- `Landing.tsx`: "월드값 기반 송출/수신 흐름을 / 분리해서 보여줍니다" 헤딩에 `<br/>`.
- 참고: 헤드리스 Playwright는 rAF를 1Hz throttle해서 실제 FPS 측정 불가(정확히 ~1000ms 규칙적 = 아티팩트). 실 GPU는 Intel Arc(하드웨어 가속 정상).

### 밸런스 진단 (다음 세션 핵심)
- **증상:** `combat_replay.json`(seed 42, 6R)에서 Blue 승 0 (RED 4 / DRAW 2 / BLUE 0). seed·시나리오 무관하게 Red 편향(6 seed 36R 중 BLUE 0; 시나리오는 telemetry_conflict만 BLUE 1).
- **근본 원인:** `scoring/scorer.py:336 _classify_outcome`이 **맨 처음 `if attrition["triggered"]: return RED_ATTRITION`으로 단락** → Blue가 탐지·복구·격리(0.96) 다 성공해도 무시. 방어비용이 공격의 **18~31배**라 combat 라운드 내 누적으로 가용성 1.0→0.47(0.50 floor 아래)로 폭락 → 승리 문턱(복구 0.70/격리·탐지 0.50) 다 미달 + attrition 발동. 개별 방어 action은 0.005~0.03(`blue/defense_planner.py`)인데 스텝×행동 누적이 문제. 시스템도 `over_defense=action_cost>=0.10`으로 인식(`feedback_learner.py:391`) → attrition은 원래 과방어를 처벌해 Blue가 경제적 방어를 **학습하게** 하는 장치. 즉 6R 리플레이는 학습 안 된 cold Blue라 나쁘게 보임.
- **무위험 해법 확인(실측):** 라운드를 늘리면 Blue가 학습해서 이김. seed 42 기준 — 20R: Blue 첫 승 R9, 뒤 1/3에 BLUE 등장 / 60R: 뒤 1/3 **BLUE 11 vs RED 6**(역전) / 120R: BLUE 46. → "초반 Red 우세 → 후반 Blue 역전" 학습 아크. **스코어링·185 테스트 안 건드림.**

### 다음 할 일 (Codex에서 이어서, 순서대로)
1. **밸런스: 리플레이를 더 많은 라운드로 재생성** (사용자가 라운드 수 결정 대기 중 — 추천 24~30, 확실한 역전 원하면 40~60). 명령:
   `PYTHONPATH=src python -c "from pathlib import Path; from dah_flawless.environment.round_combat_runner import run_combat_rounds; run_combat_rounds(seed=42, rounds=N, max_steps=30, min_steps=4, log_path=Path('data/logs/round_logs.jsonl'), summary_path=Path('data/logs/summary.json'), frontend_log_path=Path('data/frontend/combat_replay.json'))"`
   → `cd frontend && npm run build` → `git add -f frontend/dist/index.html` → 커밋·푸시.
   주의: 라운드 20+면 `CommandBar.tsx` 라운드 네비(이미 `overflow-x-auto`라 스크롤은 됨)가 버튼 많아짐 — 필요시 compact 처리.
2. **seed+시나리오 드롭다운** (사용자 확정: 둘 다, 밸런스 다음). 리플레이를 seed 여러 개 + 시나리오별로 미리 구워 번들에 넣고 랜딩에서 선택. `data.ts`(단일 replay import → 다중 RUNS 배열)와 `store/useReplayStore.ts`(activeSeed/replay 전환)·`Landing.tsx`(드롭다운) 리팩터 필요. 여러 컴포넌트가 `getRound(roundIdx)` 패턴이라 active replay 배선 주의.
3. (선택) 밸런스를 더 근본적으로 원하면: Blue defense_planner 과방어 억제 OR `_classify_outcome`에서 attrition을 recovery/containment 뒤로 — 단 팀 백엔드·185 테스트 영향, 사용자 미결정.

### 불변식/주의 (이번 세션에도 유지)
- 백엔드 파이썬·스코어링·JSON 스키마 안 건드림(이번 세션 프론트+docker+README만). 밸런스도 진단만, 코드 미수정.
- Blue는 truth 못 봄. 프론트는 blue_observed 계열만 표시.
- 프론트는 리플레이(뷰)지 라이브 아님. 실시간 원하면 API 서버(B안) 별도 작업.

## 프론트엔드 리디자인 (2026-07-08, front-end 브랜치)

**스펙 문서: `docs/FRONTEND_DESIGN_SPEC.md` — 후속 작업 전 반드시 정독. 모든 디자인/기술 결정의 단일 기준.**

### 완료 상태 (P0~P5 전부 구현·검증됨)

- 위치: `frontend/` (React 19 + Vite 8 + TS + Tailwind v4 + R3F + motion + zustand)
- 빌드: `cd frontend && npm run build` → `dist/index.html` 단일 파일 4.5MB (vite-plugin-singlefile, 폰트·3D·데이터 전부 인라인, file:// 구동 확인)
- 데이터: `data/frontend/combat_replay.json` (seed 42, 6라운드, combat_steps 포함). 재생성:
  `PYTHONPATH=src python -c "from pathlib import Path; from dah_flawless.environment.round_combat_runner import run_combat_rounds; run_combat_rounds(seed=42, rounds=6, max_steps=30, min_steps=6, log_path=Path('data/frontend/replay_rounds.jsonl'), summary_path=Path('data/frontend/replay_summary.json'), frontend_log_path=Path('data/frontend/combat_replay.json'))"`
  주의: 스텝 타임라인은 `run_combat_rounds` 직접 호출로만 생성됨 (`scripts/generate_frontend_log.py`는 combat_steps 없는 JSONL이면 timeline이 빈다).
- 검증: `cd frontend && node scripts/verify.mjs 출력.png [--step N] [--focus RED|BLUE] [--mugyeol] [--play]` — Playwright 스크린샷+콘솔 에러 수집. 매 수정 후 실행할 것.
- 구현물: 커맨드 바(라운드/재생/승패), RED-BLUE 듀얼 패널 스프링 스위칭(레일 축소·확장 상세·키보드 접근), R3F 3D 전장 씬(SATCOM/UAV/UGV/C2 노드, 공격 대시 흐름 라인, 탐지 링 펄스, 포커스 카메라 도브, WebGL 폴백), 위성 창 4종(창-밖-창: suspicion 스파크라인·ZTA 정책 레인·텔레메트리·이벤트 로그), 무결이(오로라 블롭, Web Speech ko-KR 명령 매핑, TTS, 볼륨 반응 꿈틀, 텍스트 폴백), 부팅 스태거 시퀀스, prefers-reduced-motion 전역.
- 키보드: Space 재생, ←/→ 스텝, Esc 포커스 해제.

### 2026-07-08 추가분 (커밋 508d1e2)

- **랜딩 페이지**: 게임 런처식 스플릿 히어로 (`Landing.tsx`). 좌 RED/우 BLUE 호버 밀당, "시뮬레이션 진입" CTA → 대시보드 부팅 시퀀스, 커맨드 바 우측 SignOut 버튼으로 복귀. 상태는 store `entered/enter/exitToLanding`.
- **먹통(남색 빈 화면) 버그 2건 해결**: ① R2+에서 `defense_actions`가 객체 배열({action,cost,status,target})이라 React error #31 크래시 → `defenseLabel()` 포매터(SidePanel.tsx, Satellites에서 재사용). ② WAIT 스텝에서 `delta.applied`가 null → RED 확장 패널 가드. 재발 방지로 `ErrorBoundary.tsx`(HUD 폴트 패널) 추가. **교훈: 이 JSON은 라운드마다 필드 형태가 달라질 수 있으니 새 필드 소비 전 6라운드 전체 스캔 필수.**
- **노드 호버 콜아웃**: e71 레퍼런스 스타일 리더 라인+HUD 카드 (`NodeCallout` in BattlefieldScene.tsx). 자산별 `callout: "right"|"top"` 배치(UGV는 EVENT LOG 겹침 회피로 top). 보이지 않는 히트 스피어로 호버 판정.
- verify.mjs 확장: 랜딩 자동 진입, `--landing`, `--round N`, `--hover "x,y"`.

### 남은 폴리시 (다음 세션 후보, 스펙 대비 미완)

1. 위성 창 드래그 이동·더블클릭 접기 (스펙 4.1 선택 항목)
2. 1440px 미만 도킹 컬럼·1024px 미만 탭 시트 수렴 (현재 오프셋 축소만)
3. 프레임 SVG 스트로크 draw-in 부팅 연출 (현재 opacity+y 스태거로 대체)
4. Bloom 포스트프로세싱 (성능·용량 이유로 의도적 미탑재, 스펙 5장 탈출경로 적용)
5. 음성 인식 실기기 Chrome 테스트 (헤드리스는 마이크 불가라 텍스트 명령으로만 검증됨)
6. DENY 판정 마커 pop 애니메이션 (현재 ZTA 레인 셀 색상으로 표현)

### 불변식 (프론트에서도 유지 중, 위반 금지)

- Blue 패널·위성 창은 blue_observed 계열 데이터만 표시 (truth 노출 없음)
- 백엔드 파이썬·JSON 스키마 수정 금지, `streamlit_app.py`·`scripts/build_static_site.py` 삭제·수정 금지
- 색 규율: 시안=포커스, red/blue=진영 전용, 무결이 3색(`--mugyeol-*`)은 무결이 밖 사용 금지

## 현재 방향

이 브랜치는 main처럼 저장소를 가볍게 유지하되, 우리가 추가한 **raw_world -> feature -> tag -> Red/Blue decision** 방향을 보존한다.

```text
raw_world
-> Feature Extractor
-> State Adapter
-> scorer_truth(state["world"]) + blue_observed
-> Situation Tagger
-> Red Attack Selector / Blue Threat Detection
-> Mutation / Defense
-> Scorer
```

## 확정된 설계 기준

- 보고서용 기준에서 1 episode는 30 consecutive timesteps다.
- 현재 코드의 `round`는 단일 step이고, `EpisodeRunner`가 30 step을 하나의 episode로 묶는다.
- `RoundCombatRunner`는 실험용 동적 공방 runner다. 여기서는 1 round가 하나의 variable-length combat episode이며, Red/Blue가 `WAIT`, `PROBE_BOUNDARY`, `SLOW_DRIFT`, `INSPECT_INTERNAL`, `DEFEND`, `ABORT` 같은 decision step을 반복하다가 종료 조건이나 max step에 도달하면 끝난다. 기존 `run_simulation` 기본 흐름은 아직 유지한다.
- Blue readiness gate는 Blue의 최근 방어 성공률이 기준에 도달하기 전까지 Red policy/goal weight 업데이트를 막고 Blue 업데이트를 계속 허용한다. 이 게이트는 `TrainingScheduler`와 `RoundCombatRunner` 양쪽에 적용된다.
- World Generator는 rule-based transition을 기본으로 하고, LLM은 causal supervisor/reviewer로만 사용한다.
- Mutation Approval Reviewer는 reviewer-only다. approve/clamp/reject/explain만 가능하고, 공격 선택·변조값 생성·state 수정·payload 생성은 하지 않는다.
- Red 공격 범위는 simulated observe mutation과 channel-level delay/drop/jitter/reorder/loss abstraction까지 포함한다.
- Blue observe는 `internal_observe`와 `external_observe`로 나뉜다. Red는 `external_observe`만 직접 mutation할 수 있다.
- 현재 MVP의 `blue_observed.telemetry` 같은 flat key는 `external_observe` 호환 view다.
- `configs/mutation_policy.yaml`와 `docs/mutation_policy.md`가 external_observe 허용 필드와 profile별 max delta를 정의한다. 현재 핵심 공격 필드의 runtime clamp/reject는 `attacks/mutation_policy.py`로 구현됐고, runtime은 YAML config를 자동 로딩한다.
- 실제 RF/API 침투 절차, exploit payload, malware, credential 탈취 방식은 이 repo 범위가 아니다.
- Blue는 raw_world와 scorer_truth/state["world"]를 볼 수 없다.
- Blue는 우선 rule-based baseline으로 두고, 구조 확정 뒤 학습형 정책을 붙인다.
- Blue Goal Consistency Checker는 scorer의 `red_goal`을 보지 않고 observed/internal/history/tags만으로 cyber-effect hypothesis를 만든다.
- Blue availability는 임무 지속성 예산이다. 방어 action은 availability/trust_budget을 소모하지만, 그 손상은 한 round-level combat episode 안에서만 유효하다. 라운드 시작마다 `round_episode_budget_reset_v1`이 시나리오 초기 예산으로 리셋한다. 근거와 수식은 `docs/blue_availability_recovery_model.md`에 있다.
- Blue Defense-Effect Contract는 완전 복구 전 단계의 피해 억제를 `containment_score`로 기록한다. `recovery_success`는 엄격한 trusted restore로 유지하고, readiness gate는 detection/containment/availability를 반영한 연속 점수로 Blue 준비도를 판단한다. 근거와 수식은 `docs/blue_defense_effect_contracts.md`에 있다.
- Blue Feedback Learner는 scorer feedback으로 domain policy와 effect policy(`effect_sensitivity`, `effect_threshold`, `effect_feedback_counts`)를 업데이트한다. 또한 scorer의 mission-impact를 effect별 EMA로 기록하고, 고영향 effect를 놓치거나 탐지 후 복구하지 못하면 해당 effect 민감도/threshold 보정을 더 강하게 적용한다.
- `DETECTION_BOUNDARY_PROBE`는 학습용 meta goal이다. Blue Feedback Learner는 이를 독립 effect로 누적하지 않고 mission-impact component나 실제 감지된 하위 `EFFECT_*`로 remap해 detector가 허상 목표에 과적합되지 않게 한다.
- `HOLD_COMMAND` 복구는 stale last-known-good보다 현재 `internal_observe.c2_message`를 우선한다. 내부 C2 anchor가 없을 때만 last-known-good/history로 fallback한다.
- Goal Planner는 이전 로그와 현재 observed context를 함께 보고 Red의 cyber-effect 목표를 고른다. 최근 목표/domain 반복에는 diversity penalty를 주고, 덜 시도한 목표에는 작은 보너스를 준다.
- Attack-Effect Contract는 공격 후보와 지원 goal/effect/evidence를 묶는다. Attack Selector는 contract alignment를 점수에 반영하고, Goal-aware Scorer는 unsupported attack-goal pair를 low-reward 실패로 clamp한다.
- Attack Selector는 attack-level diversity penalty, contract-compatible repeat guard, tactic exploration rate로 같은 attack/tactic 반복을 줄인다.
- Goal-aware Scorer는 기존 `attack_success`와 별도로 `goal_success`, `goal_reward`, `score.evidence.goal_score`를 기록한다. Mission-impact scorer는 임무판단/안전/명령 freshness/가용성 영향을 별도 evidence로 남기고, contract-supported goal reward에만 제한적으로 섞는다.
- Causal Consistency Monitor는 attack -> mutation -> tag/effect -> scorer evidence 체인을 검사하고, summary에 causal/entropy metrics를 남긴다.
- Blue policy saturation guard는 domain trust가 0으로 붕괴하지 않도록 floor를 적용한다.
- Policy Update Reviewer는 Red/Blue policy delta를 심사한다. 외부 OpenAI-compatible LLM reviewer는 선택사항이며, 연결 실패/잘못된 JSON/검증 실패 시 오프라인 heuristic reviewer로 즉시 fallback한다.
- Mutation Approval Reviewer는 Red observe mutation 후보를 심사한다. 외부 OpenAI-compatible LLM reviewer는 선택사항이며, 연결 실패/잘못된 JSON/검증 실패 시 오프라인 heuristic reviewer로 즉시 fallback한다.
- `src/dah_flawless/llm/`의 LLM Adapter가 역할별 외부 JSON 호출, schema 검증, 순수 코드 fallback을 공통 처리한다.
- 학습 cadence는 Blue-only 10 episodes -> Red-only 10 episodes -> fixed evaluation 3 episodes를 기본값으로 두며, `TrainingScheduler`로 구현되어 있다.
- Holdout 평가는 학습이 끝난 Red/Blue policy를 frozen 상태로 복사한 뒤 별도 seed/scenario grid에서 돌린다. 이때 MVP coverage용 scripted attack은 꺼서 정책 자체의 일반화 성능을 본다. policy update는 계속 frozen으로 유지하지만, 이전 holdout case 로그를 selector context로 넘겨 cross-case attack diversity penalty가 작동하게 한다.
- Rolling Log Memory는 긴 round-mode run에서 Red planning context가 원 로그 전체에 과적합되지 않도록 일정 라운드마다 로그를 압축해 proxy logs로 바꾼다. 출력 JSONL audit log는 유지하고, `previous_logs` 입력만 `proxy_logs + recent_logs`로 줄인다.
- Scenario Pack은 `clean_start`, `degraded_start`, `satcom_delay`, `gnss_degraded`, `c2_metadata_noisy`, `telemetry_conflict`, `low_trust_start`를 제공한다. 기본 holdout은 전체 scenario pack을 사용한다.
- Report Generator는 training/holdout summary와 optional JSONL logs를 읽어 보고서용 Markdown/JSON을 만든다. `main.py --report-out` 또는 `scripts/generate_training_report.py`로 실행한다.
- Frontend combat log는 학습/감사용 JSONL에서 파생되는 별도 JSON projection이다. `src/dah_flawless/reporting/frontend_log.py` 또는 `scripts/generate_frontend_log.py`를 사용한다. 학습 로그는 `combat_steps`, `decision_log`, policy/scorer evidence를 유지하고, 프론트엔드 로그는 `schema`, `summary`, `filters`, `rounds[].timeline`, `highlights`, `action_runs` 중심으로 화면용 필드만 남긴다.

## 구조 원칙

- `reports/`, 생성된 그림/PDF, 제출 ZIP/PDF 스크립트는 repo에 두지 않는다.
- raw-world schema, generator, feature extractor, state adapter는 유지한다.
- LLM/팀원이 이어받을 때는 `docs/llm_alignment_guide.md`를 먼저 읽는다.
- `state["world"]`는 raw_world가 아니라 scorer-only truth다.
- Red/Blue 입력은 redaction을 거쳐 `world` 키를 포함하지 않아야 한다.

## 주요 파일

| 위치 | 역할 |
|---|---|
| `configs/raw_world_schema.yaml` | raw_world machine-readable schema |
| `configs/mutation_policy.yaml` | Red mutation 허용 필드와 profile별 max delta |
| `docs/llm_alignment_guide.md` | 용어/방향성/AI 구조 기준 문서 |
| `docs/raw_world_schema.md` | raw_world 설명 |
| `docs/mutation_policy.md` | Mutation Policy 설명과 구현 단계 |
| `docs/attack_effect_contracts.md` | 실제 문헌/문서 기반 Attack-Effect Contract와 비판적 평가 |
| `docs/blue_availability_recovery_model.md` | Blue 방어 절차, availability/trust_budget 회복 수식, 문헌 근거 |
| `docs/blue_defense_effect_contracts.md` | Blue 방어 action별 containment_score와 readiness gate 근거 |
| `src/dah_flawless/world/generator.py` | rule-based raw_world generator |
| `src/dah_flawless/world/feature_extractor.py` | raw_world feature extractor |
| `src/dah_flawless/world/state_adapter.py` | raw_world -> MVP runtime state 변환 |
| `src/dah_flawless/situation_tagger.py` | 공용 Situation Tagger |
| `src/dah_flawless/attacks/goal_planner.py` | previous-log feedback 기반 Red cyber-effect goal planner와 diversity guard |
| `src/dah_flawless/attacks/effect_contracts.py` | attack-goal-effect 정합성 contract |
| `src/dah_flawless/attacks/selector.py` | Attack/Tactic scoring |
| `src/dah_flawless/attacks/mutations.py` | handler 기반 observed mutation engine |
| `src/dah_flawless/blue/goal_consistency.py` | Blue observed-only cyber-effect hypothesis checker |
| `src/dah_flawless/blue/defense_effects.py` | Blue Defense-Effect Contract와 containment scoring |
| `src/dah_flawless/blue/feedback_learner.py` | Blue scorer feedback learner |
| `src/dah_flawless/llm/` | shared role-scoped external LLM adapter and offline fallback boundary |
| `src/dah_flawless/mutation_review/` | mutation approval reviewer and external-LLM fallback |
| `src/dah_flawless/policy_review/` | bounded policy update reviewer and external-LLM fallback |
| `src/dah_flawless/environment/episode_runner.py` | 30-step episode runner |
| `src/dah_flawless/environment/round_combat_runner.py` | variable-length round-level Red/Blue combat episode runner |
| `src/dah_flawless/environment/training_scheduler.py` | alternating Blue/Red update scheduler |
| `src/dah_flawless/environment/log_memory.py` | round-mode rolling log memory compression and proxy context |
| `src/dah_flawless/environment/holdout_evaluator.py` | frozen-policy seed/scenario holdout evaluator, cross-case diversity context |
| `docs/scenario_pack.md` | scenario pack 목적과 초기 조건 |
| `src/dah_flawless/reporting/report_generator.py` | training/holdout report generator |
| `src/dah_flawless/reporting/frontend_log.py` | frontend replay log projection for RoundCombatRunner outputs |
| `docs/report_generator.md` | report generator 사용법 |
| `src/dah_flawless/blue/` | Blue detection/mission/defense/report agents |
| `src/dah_flawless/scoring/scorer.py` | scorer 판정 |
| `src/dah_flawless/scoring/goal_scorer.py` | Red cyber-effect 목표별 goal_success/goal_reward 판정 |
| `src/dah_flawless/scoring/mission_impact.py` | observe 오염이 임무 판단/안전/명령 freshness/가용성에 준 영향을 점수화 |
| `src/dah_flawless/scoring/causal_consistency.py` | causal chain consistency monitor |

## 실행

PowerShell 기준:

```powershell
$env:PYTHONPATH='src'
python scripts/run_world_generator.py --count 1 --out tmp/world/raw_world.jsonl
python scripts/run_feature_extractor.py --in tmp/world/raw_world.jsonl --out tmp/world/features.jsonl --summary
python -m dah_flawless.main --seed 42 --rounds 3 --raw-world-sample tmp/world/raw_world.jsonl
```

기본 시뮬레이션:

```powershell
$env:PYTHONPATH='src'
python -m dah_flawless.main --seed 42 --rounds 5
```

30-step episode 시뮬레이션:

```powershell
$env:PYTHONPATH='src'
python -m dah_flawless.main --seed 42 --episodes 2 --steps-per-episode 30
```

## ZTA-Inspired Observe Policy Gate

- 현재 구현 범위는 `external_observe` 대상 사용권한 판단이다.
- `internal_observe`는 Blue의 trust anchor로만 사용한다.
- 이 모듈은 공격 탐지기가 아니라 외부 관측값을 임무 판단에 어느 수준으로 사용할지 결정하는 policy gate다.
- `detection_success`는 직접 올리지 않고, `mission_impact.observe_policy_gate`와 `containment.policy_containment` evidence로만 반영한다.
- 문서와 수식은 `docs/zta_observe_policy_gate.md`를 기준으로 한다.

학습 schedule 시뮬레이션:

```powershell
$env:PYTHONPATH='src'
python -m dah_flawless.main --seed 42 --training-schedule --steps-per-episode 30
```

테스트:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

## main과 병합할 때 주의

원격 main은 `red_policy_state`, `blue_policy_state`, `feedback` 로그를 강조한다. 이 브랜치의 raw-world 확장을 main과 합칠 때는 아래를 보존한다.

1. main의 adaptive policy log
2. 이 브랜치의 raw_world generator/extractor/adapter
3. 이 브랜치의 상세 SituationTag와 Attack Selector
4. `state["world"]`는 scorer_truth라는 용어 기준
5. `reports/`와 생성 산출물을 repo에 다시 넣지 않는 구조
