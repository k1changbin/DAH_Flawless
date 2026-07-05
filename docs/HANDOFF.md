# DAH Flawless Handoff

최종 갱신: 2026-07-06

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
- World Generator는 rule-based transition을 기본으로 하고, LLM은 causal supervisor/reviewer로만 사용한다.
- Mutation Approval Reviewer는 reviewer-only다. approve/clamp/reject/explain만 가능하고, 공격 선택·변조값 생성·state 수정·payload 생성은 하지 않는다.
- Red 공격 범위는 simulated observe mutation과 channel-level delay/drop/jitter/reorder/loss abstraction까지 포함한다.
- Blue observe는 `internal_observe`와 `external_observe`로 나뉜다. Red는 `external_observe`만 직접 mutation할 수 있다.
- 현재 MVP의 `blue_observed.telemetry` 같은 flat key는 `external_observe` 호환 view다.
- `configs/mutation_policy.yaml`와 `docs/mutation_policy.md`가 external_observe 허용 필드와 profile별 max delta를 정의한다. 현재 핵심 공격 필드의 runtime clamp/reject는 `attacks/mutation_policy.py`로 구현됐고, runtime은 YAML config를 자동 로딩한다.
- 실제 RF/API 침투 절차, exploit payload, malware, credential 탈취 방식은 이 repo 범위가 아니다.
- Blue는 raw_world와 scorer_truth/state["world"]를 볼 수 없다.
- Blue는 우선 rule-based baseline으로 두고, 구조 확정 뒤 학습형 정책을 붙인다.
- Blue Feedback Learner는 scorer feedback으로 `domain_trust`, `detection_sensitivity`, `escalation_threshold`, `feedback_counts`를 업데이트한다.
- Goal Planner는 이전 로그와 현재 observed context를 함께 보고 Red의 cyber-effect 목표를 고른다.
- Policy Update Reviewer는 Red/Blue policy delta를 심사한다. 외부 OpenAI-compatible LLM reviewer는 선택사항이며, 연결 실패/잘못된 JSON/검증 실패 시 오프라인 heuristic reviewer로 즉시 fallback한다.
- Mutation Approval Reviewer는 Red observe mutation 후보를 심사한다. 외부 OpenAI-compatible LLM reviewer는 선택사항이며, 연결 실패/잘못된 JSON/검증 실패 시 오프라인 heuristic reviewer로 즉시 fallback한다.
- `src/dah_flawless/llm/`의 LLM Adapter가 역할별 외부 JSON 호출, schema 검증, 순수 코드 fallback을 공통 처리한다.
- 학습 cadence는 Blue-only 10 episodes -> Red-only 10 episodes -> fixed evaluation 3 episodes를 기본값으로 두며, `TrainingScheduler`로 구현되어 있다.

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
| `src/dah_flawless/world/generator.py` | rule-based raw_world generator |
| `src/dah_flawless/world/feature_extractor.py` | raw_world feature extractor |
| `src/dah_flawless/world/state_adapter.py` | raw_world -> MVP runtime state 변환 |
| `src/dah_flawless/situation_tagger.py` | 공용 Situation Tagger |
| `src/dah_flawless/attacks/goal_planner.py` | previous-log feedback 기반 Red cyber-effect goal planner |
| `src/dah_flawless/attacks/selector.py` | Attack/Tactic scoring |
| `src/dah_flawless/attacks/mutations.py` | handler 기반 observed mutation engine |
| `src/dah_flawless/blue/feedback_learner.py` | Blue scorer feedback learner |
| `src/dah_flawless/llm/` | shared role-scoped external LLM adapter and offline fallback boundary |
| `src/dah_flawless/mutation_review/` | mutation approval reviewer and external-LLM fallback |
| `src/dah_flawless/policy_review/` | bounded policy update reviewer and external-LLM fallback |
| `src/dah_flawless/environment/episode_runner.py` | 30-step episode runner |
| `src/dah_flawless/environment/training_scheduler.py` | alternating Blue/Red update scheduler |
| `src/dah_flawless/blue/` | Blue detection/mission/defense/report agents |
| `src/dah_flawless/scoring/scorer.py` | scorer 판정 |

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
