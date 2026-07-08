# DAH Flawless Handoff

최종 갱신: 2026-07-07

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
