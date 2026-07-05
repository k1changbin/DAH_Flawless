# DAH Flawless Implementation Plan

기준일: 2026-07-04 KST

## 1. 현재 목표

현재 브랜치의 목표는 생성 산출물을 많이 들고 있는 제출 패키지가 아니라, **raw world 기반 Red/Blue AI brain prototype**을 가볍고 재현 가능하게 유지하는 것이다.

```text
raw_world
-> Feature Extractor
-> State Adapter
-> scorer_truth(state["world"]) + blue_observed
-> Situation Tagger
-> Red Attack Selector / Blue Threat Detection
-> Mutation / Defense Action
-> Scorer
```

## 2. 확정된 보고서용 설계 기준

현재 목표는 "완성된 실전 공격 시스템"이 아니라 **대회 보고서에서 설명 가능한 Red/Blue 학습형 시뮬레이션 구조**다.

| 항목 | 기준 |
|---|---|
| episode 단위 | 1 episode = 30 consecutive timesteps |
| world 생성 | rule-based transition + LLM causal supervisor |
| Red attack scope | observed mutation + channel-level delay/drop/jitter/reorder/loss abstraction |
| Blue 입력 | internal_observe, external_observe, observed history, tags, mission/capability context only |
| Blue 초기 정책 | rule-based baseline + scorer feedback 기반 domain policy update |
| scorer 권한 | scorer만 scorer_truth/state["world"]와 blue_observed를 동시에 봄 |
| 학습 cadence | Blue-only 10 episodes -> Red-only 10 episodes -> fixed evaluation 3 episodes |
| 현재 우선순위 | 코드 완성보다 보고서용 구조와 용어 명료화 우선 |

현재 코드의 `round`는 단일 step이고, `EpisodeRunner`가 30 step을 하나의 episode로 묶는다. `TrainingScheduler`는 Blue-only/Red-only/fixed-eval update block을 관리한다.

## 3. 저장소 구조 원칙

- `reports/`는 repo에 두지 않는다.
- 생성된 그림/PDF/ZIP은 repo에 두지 않는다.
- 제출 ZIP/PDF 생성 스크립트도 현재 브랜치 범위에서 제거한다.
- raw-world schema와 실행 가능한 brain pipeline은 유지한다.
- 새 LLM/팀원이 들어오면 `docs/llm_alignment_guide.md`를 먼저 읽게 한다.

## 4. 유지할 코어 구조

```text
configs/
  raw_world_schema.yaml
  mutation_policy.yaml
docs/
  llm_alignment_guide.md
  raw_world_schema.md
  world_observed_model.md
  schema_design.md
  field_formats.md
  mutation_policy.md
  situation_tags.md
  attack_mapping.md
scripts/
  print_llm_alignment_guide.py
  run_world_generator.py
  run_feature_extractor.py
src/dah_flawless/
  world/
    generator.py
    feature_extractor.py
    state_adapter.py
  situation_tagger.py
  attacks/
    catalog.py
    selector.py
    red_agent.py
    mutations.py
  blue/
  environment/
  scoring/
tests/
```

## 5. 핵심 용어

| 용어 | 의미 |
|---|---|
| `raw_world` | 현실 전장에 존재하는 원천 신호/방출/환경/사건 |
| `raw_world_feature` | raw_world에서 뽑은 정규화 특징값과 후보 공격 점수 |
| `scorer_truth` | scorer/admin만 보는 채점 기준 상태. 현재 코드 키는 `state["world"]` |
| `blue_observed` | Blue AI가 받은 관측 입력. Red의 직접 mutation 대상 |
| `internal_observe` | Blue의 내부 센서/로컬 상태 관측. Red 직접 mutation 금지 |
| `external_observe` | 외부 신호/통신/원격 관측. Red mutation 허용 표면 |
| `redacted_state` | Red/Blue에게 주기 전 `world` 키를 제거한 state |

## 6. Red AI 구현 계획

Red AI는 아래 구조로 설명하고 구현한다.

```text
Observer
-> Situation Tagger
-> Goal Planner
-> Attack Selector
-> Mutation Engine
-> Stealth Controller
-> Feedback Learner
-> Decision Logger
```

현재 구현 상태:

| 모듈 | 현재 구현 |
|---|---|
| Observer | redacted state와 tag 입력 |
| Situation Tagger | `src/dah_flawless/situation_tagger.py` |
| Goal Planner | 경량/설명 수준. target domain으로 대체 |
| Attack Selector | `src/dah_flawless/attacks/selector.py` |
| Mutation Policy | `configs/mutation_policy.yaml`, `docs/mutation_policy.md` |
| Mutation Engine | `src/dah_flawless/attacks/mutations.py` |
| Stealth Controller | `red_agent.py`의 stealth/tactic |
| Feedback Learner | scorer feedback 기반 weight/probe 업데이트 |
| Decision Logger | `decision_log`, `red_tactic`, candidate scores |

## 7. Raw World 처리 계획

1. `run_world_generator.py`로 synthetic raw_world JSONL을 만든다.
2. `run_feature_extractor.py`로 feature row와 candidate scores를 만든다.
3. `state_adapter.py`가 raw_world를 MVP runtime state로 변환한다.
4. runtime state는 scorer_truth와 blue_observed를 분리한다.
5. Situation Tagger가 observed와 feature 기반 태그를 만든다.

추가 구현 목표:

- `CausalWorldSupervisor`: 30-step episode 안에서 world 값의 비현실적 점프와 모순을 검수한다.
- `EpisodeWorldGenerator`: 단일 sample이 아니라 원인-결과가 이어지는 30개 timestep을 생성한다.
- LLM은 raw payload 생성기가 아니라 causal explanation/reviewer로 제한한다. `Mutation Approval Reviewer`는 reviewer-only로 두며 공격 선택, 변조값 생성, state 직접 수정 권한을 주지 않는다.

## 8. Blue 방어 계획

Blue는 공격명을 맞히는 모델이 아니라 observed-only 방어 pipeline이다.

```text
Redaction Boundary
-> Situation/Threat Detection
-> Mission Monitor
-> Defense Planner
-> Defense Action Application
-> Incident Report
```

핵심 원칙:

- Blue는 scorer_truth를 보지 않는다.
- observed 내부 모순, history, capability, comms metadata를 본다.
- defense action에는 availability cost가 있다.
- 과방어는 `RED_ATTRITION`으로 이어질 수 있다.

현재 Blue Feedback Learner는 `blue_policy_state`를 업데이트한다. 이 상태는 domain별 `domain_trust`, `detection_sensitivity`, `escalation_threshold`, `feedback_counts`로 구성된다. missed attack이면 해당 domain의 sensitivity를 올리고 escalation threshold를 낮추며, false positive나 과방어 비용이 크면 sensitivity를 낮추고 threshold를 올린다.

Policy Update Reviewer는 Red/Blue feedback learner가 만든 정책 변동 후보를 심사한다. 외부 LLM reviewer는 `configs/policy_update_reviewer.json`으로 켤 수 있지만 기본값은 off이며, 외부 연결 실패나 invalid JSON이 발생하면 오프라인 heuristic reviewer가 같은 인터페이스로 즉시 대체된다.

공통 LLM Adapter는 `src/dah_flawless/llm/`에 있다. 각 역할 모듈은 이 계층을 통해 외부 OpenAI-compatible JSON 응답을 요청하고, 실패하면 역할별 순수 코드 fallback으로 계속 진행한다.

Mutation Approval Reviewer는 `src/dah_flawless/mutation_review/`에 있다. Attack Selector와 deterministic Mutation Policy가 만든 후보 observe mutation만 심사하며, 외부 LLM이 있어도 approve/clamp/reject 범위를 넘지 못한다.

## 9. Scorer 계획

Scorer만 scorer_truth와 blue_observed를 동시에 본다.

| 판정 | 의미 |
|---|---|
| `RED_BREACH` | 공격 성공, 탐지 실패 |
| `RED_ATTRITION` | 방어 비용으로 availability 고갈 |
| `BLUE` | 탐지 성공, availability 유지 |
| `BLUE_RECOVERY` | 탐지 후 신뢰 상태 복구 |
| `DRAW` | 명확한 승패 없음 |

scorer evidence에는 trusted value, observed value, mismatch, detection/recovery window, defense actions를 남긴다.

## 10. 학습 루프 계획

보고서 기준 학습 루프는 다음 순서로 설명한다.

```text
for block in training_schedule:
    if block == BLUE_UPDATE:
        freeze(red_policy)
        run 10 episodes, 30 steps each
        update blue rule weights / thresholds from scorer feedback

    if block == RED_UPDATE:
        freeze(blue_policy)
        run 10 episodes, 30 steps each
        update red attack weights / stealth probe parameters

    if block == FIXED_EVAL:
        freeze(red_policy)
        freeze(blue_policy)
        run 3 episodes, 30 steps each
        write scorer evidence and decision logs
```

필요한 모듈:

| 모듈 | 역할 | 현재 상태 |
|---|---|---|
| `EpisodeRunner` | 30 timestep을 하나의 episode로 묶음 | 구현 |
| `TrainingScheduler` | Blue-only/Red-only/fixed-eval block 전환 | 구현 |
| `BlueFeedbackLearner` | scorer 결과로 Blue domain trust/sensitivity/threshold 업데이트 | 구현 |
| `LLMAdapter` | 역할별 외부 LLM JSON 호출, 검증, fallback 공통 처리 | 구현 |
| `PolicyUpdateReviewer` | Red/Blue policy delta 후보 심사, 외부 LLM 실패 시 fallback | 구현 |
| `MutationApprovalReviewer` | proposed observe mutation의 허용 범위 심사, 외부 LLM 실패 시 fallback | 구현 |
| `MutationPolicy` | external_observe 허용 필드와 profile별 max delta 기준 | 핵심 필드 runtime enforcement 구현 |
| `MutationProfile routing` | stealth/aggressive/loud_demo profile별 params 선택 | 구현 |
| `MutationEngine handlers` | 공격별 handler가 MutationOutcome(before/after/delta)을 반환 | 구현 |
| `FeedbackLearner` | scorer component를 Red attack weight와 Blue domain policy에 반영 | 구현 |
| `DecisionLogger` | episode별 공격 선택, 방어 결과, scorer evidence 기록 | 기본 로그 확장 필요 |

## 11. 현재 미구현/확장 후보

| 항목 | 상태 |
|---|---|
| VAE/CVAE world generator | 미구현 |
| 30-step EpisodeRunner | 구현 |
| Alternating TrainingScheduler | 구현 |
| MutationApprovalReviewer | reviewer-only 구현 |
| MutationPolicy field-level enforcement | 핵심 필드 구현, YAML config 자동 로딩 구현 |
| 실제 RF/API adapter | 미구현 |
| 실제 공격 실행 | 범위 밖 |
| main 브랜치의 adaptive policy log와 완전 병합 | 추후 병합 대상 |
| 보고서 PDF/ZIP 생성 자동화 | 현재 브랜치에서는 제거 |

## 12. 검증 명령

PowerShell 기준:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

Raw-world pipeline:

```powershell
$env:PYTHONPATH='src'
python scripts/run_world_generator.py --count 1 --out tmp/world/raw_world.jsonl
python scripts/run_feature_extractor.py --in tmp/world/raw_world.jsonl --out tmp/world/features.jsonl --summary
python -m dah_flawless.main --seed 42 --rounds 3 --raw-world-sample tmp/world/raw_world.jsonl
```
