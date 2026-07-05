# LLM Alignment Guide

이 문서는 DAH_Flawless를 다른 LLM이나 새 세션에서 다룰 때 용어 혼동과 방향성 이탈을 막기 위한 기준 문서다. 이 레포의 현재 방향은 **raw world 신호를 받아 특징값과 상황 태그로 바꾸고, 그 태그를 이용해 Red 공격 AI와 Blue 방어 AI가 판단하는 구조**다.

## 0. Copy-Paste Script

아래 블록은 새 LLM 세션에 그대로 붙여넣는 안내문이다.

```text
너는 DAH_Flawless 레포를 보는 보조 LLM이다. 반드시 아래 기준을 지켜라.

1. 이 프로젝트는 실제 해킹 도구가 아니다.
- 실제 UAV/GCS/RF망을 공격하지 않는다.
- 공격은 blue_observed를 바꾸는 안전한 시뮬레이션 mutation이다.
- 실제 RF/API adapter, VAE generator, RL/LLM agent는 아직 구현이 아니라 확장 설계다.

2. 세 핵심 용어를 절대 섞지 마라.
- raw_world: 현실 전장에 존재하는 원천 신호, 방출, 환경, 사건이다.
- scorer_truth: scorer/admin만 보는 채점 기준 상태다. 현재 코드 키는 state["world"]다.
- blue_observed: Blue AI가 받은 관측 입력이다. Red가 직접 조작하는 표면이다.

3. state["world"]를 raw_world라고 부르지 마라.
- state["world"]는 과거 호환 키일 뿐이고 의미상 scorer_truth다.
- Red/Blue Agent는 state["world"]를 보면 안 된다.
- Blue 입력에는 redaction을 거쳐 state["world"]가 제거되어야 한다.

4. 현재 파이프라인은 다음과 같다.
raw_world
-> Feature Extractor
-> State Adapter
-> scorer_truth(state["world"]) + blue_observed
-> Situation Tagger
-> Red Attack Selector / Blue Threat Detection
-> Mutation / Defense Action
-> Scorer/Admin 판정

5. Red AI 구조는 다음 모듈로 설명한다.
Observer -> Situation Tagger -> Goal Planner -> Attack Selector
-> Mutation Engine -> Stealth Controller -> Feedback Learner -> Decision Logger

6. Blue AI 구조는 다음 모듈로 설명한다.
Redaction Boundary -> Situation/Threat Detection -> Mission Monitor
-> Defense Planner -> Defense Action Application -> Incident Report

7. 보고서/설명에서는 이렇게 말한다.
"raw_world는 현실 원천 신호, scorer_truth는 채점용 기준 상태, blue_observed는 AI가 받은 입력이다. Red는 blue_observed를 조작하고, Blue는 scorer_truth를 보지 않은 채 observed 내부 모순과 history로 탐지한다."
```

## 1. Current Folder Boundary

현재 브랜치는 main처럼 저장소를 가볍게 유지한다. `reports/`, 생성된 그림/PDF, 제출 ZIP/PDF 생성 스크립트는 저장하지 않는다.

```text
DAH_Flawless/
  README.md
  Dockerfile
  streamlit_app.py
  requirements.txt
  pyproject.toml
  assets/
  configs/
    raw_world_schema.yaml
    mutation_policy.yaml
  docs/
    llm_alignment_guide.md
    raw_world_schema.md
    world_observed_model.md
    schema_design.md
    field_formats.md
    situation_tags.md
    attack_mapping.md
    encrypted_channel_attack_ai.md
  scripts/
    print_llm_alignment_guide.py
    run_world_generator.py
    run_feature_extractor.py
  src/dah_flawless/
    world/
    attacks/
    blue/
    environment/
      episode_runner.py
      training_scheduler.py
    scoring/
    situation_tagger.py
  tests/
```

제출용 PDF, ZIP, 보고서 그림은 이 레포 안의 고정 산출물로 두지 않는다. 필요하면 별도 작업공간에서 생성한다.

## 2. Canonical Terms

| 용어 | 정확한 의미 | 코드/문서 위치 | 주의 |
|---|---|---|---|
| `raw_world` | 현실 전장에 존재하는 원천 신호/방출/환경/사건 | `configs/raw_world_schema.yaml`, `docs/raw_world_schema.md`, `src/dah_flawless/world/generator.py` | AI가 바로 받는 예쁜 상태값이 아님 |
| `raw_world_feature` | raw_world에서 뽑은 정규화 특징값과 공격 후보 점수 | `src/dah_flawless/world/feature_extractor.py` | 태그와 공격 선택의 전단계 |
| `scorer_truth` | scorer/admin만 보는 채점 기준 상태 | 현재 코드 키 `state["world"]` | raw_world가 아님 |
| `blue_observed` | Blue AI가 받은 관측 입력 | `state["blue_observed"]` | Red mutation의 직접 대상 |
| `internal_observe` | Blue가 가진 내부 센서/로컬 상태 관측 | `blue_observed.internal_observe` | Red가 직접 mutation하면 안 됨 |
| `external_observe` | Blue가 외부 신호/통신/원격 관측으로 받은 입력 | `blue_observed.external_observe` | Red mutation의 허용 표면 |
| `redacted_state` | Red/Blue에게 넘기기 전 scorer_truth를 제거한 state | `environment/redaction.py` | 여기에 `world` 키가 있으면 설계 오류 |
| `SituationTag` | observed나 raw-world feature가 전술적으로 의미 있는 상태임을 표시한 라벨 | `situation_tagger.py`, `blue/tagger.py` | 공격명을 직접 말하지 않음 |
| `Attack` | Red가 선택하는 공격 후보 | `attacks/catalog.py`, `attacks/selector.py` | 실제 침투 명령이 아니라 mutation 정책 |
| `DefenseAction` | Blue가 선택하는 방어 조치 | `blue/defense_planner.py` | 비용이 있고 availability를 깎음 |
| `Score` | scorer가 계산한 라운드 판정 | `scoring/scorer.py`, `scoring/goal_scorer.py` | attack_success와 goal_success를 구분 |

## 3. Signal Intake And Transformation

### 3.1 Raw Signal Level

`raw_world`는 UAV/UGV/위성통신 상황에서 관측 가능하다고 가정하는 외부 원천 데이터다.

예시 영역:

| 영역 | 들어갈 수 있는 값 |
|---|---|
| RF spectrum | noise floor, emitter, burst period, duty cycle, RSSI, SNR |
| GNSS field | satellite count, C/N0, pseudorange, Doppler, interference source |
| SATCOM emissions | carrier band, propagation delay, availability, rain fade |
| UAV C2 emissions | MAVLink-like frame, msgid, sequence, tx time, signature metadata |
| Cyber message surface | encrypted payload 여부, visible metadata, ACK 흐름 |
| Physical scene | friendly UAV, unknown UAV, target, occluder 위치 |
| Weather/terrain | visibility, wind, terrain occlusion, multipath 가능성 |

현재 구현은 실제 RF 수신기를 붙이지 않는다. `RuleBasedWorldGenerator`가 안전한 synthetic sample을 만든다.

### 3.2 Feature Extraction

Feature Extractor는 raw_world를 수치/통계 특징으로 바꾼다.

입력:

```text
raw_world sample
```

출력:

```json
{
  "schema_id": "dah.raw_world.features.v0_1",
  "source_raw_world_hash": "...",
  "features": {
    "rf": {},
    "gnss": {},
    "satcom": {},
    "mavlink_c2": {},
    "mission": {},
    "scene": {},
    "environment": {},
    "composite": {}
  },
  "candidate_scores": {
    "C2_PATTERN_EXPLOIT": 0.686,
    "GNSS_DRIFT": 0.395,
    "TIME_DESYNC_REPLAY": 0.299,
    "TELEMETRY_FDI": 0.555,
    "CROSS_LAYER_BELIEF_DRIFT": 0.606
  },
  "evidence": []
}
```

중요한 점:

- Feature Extractor는 `scenario_truth_annotations`를 공격/방어 판단 근거로 쓰면 안 된다.
- 특징값은 raw signal의 관측 가능한 성질에서 나온다.
- 공격 후보 점수는 "이런 공격이 가능해 보인다"는 우선순위이며, 실제 공격 실행이 아니다.

### 3.3 State Adapter

State Adapter는 raw_world와 feature를 MVP runtime state로 바꾼다.

```text
raw_world + features
-> scorer_truth(state["world"]) + blue_observed + mission/runtime state
```

이 단계가 필요한 이유:

- raw_world는 거칠고 불친절한 원천 신호다.
- Red/Blue AI는 원천 신호 전체를 직접 읽기보다, 정규화된 observed와 tag를 보고 판단한다.
- scorer는 평가를 위해 기준 상태가 필요하므로 scorer_truth를 따로 보존한다.

### 3.4 Episode And Causal World Design

보고서용 기준에서는 한 번의 학습/평가 단위를 단일 snapshot이 아니라 **30-step episode**로 본다.

```text
1 episode = 30 consecutive timesteps
1 timestep = raw_world snapshot -> features -> tags -> Red mutation -> Blue defense -> scorer result
```

현재 코드의 `round`는 단일 simulation step이고, `EpisodeRunner`가 여러 step을 1개 episode로 묶는다. 기본 보고서 단위는 `--episodes N --steps-per-episode 30` 실행으로 만든다.

World Generator의 인과성은 전부 LLM에게 자유 생성시키지 않는다. 기본 수치 변화와 물리적 제약은 rule-based transition이 맡고, LLM은 다음 역할의 **causal supervisor**로 둔다.

| 역할 | 설명 |
|---|---|
| continuity check | 배터리, 거리, 신호세기, 지연시간 등이 비현실적으로 튀지 않는지 검수 |
| event rationale | `SATCOM_DELAY 증가 -> 명령 지연 -> 경로 수정 지연`처럼 world 변화의 원인-결과 설명 생성 |
| scenario steering | 정찰 접근, GNSS 열화, C2 패턴 노출 같은 episode-level 사건 흐름 선택 |
| contradiction reject | 같은 timestep 안에서 양립 불가능한 값 조합 거부 |

LLM은 raw RF/API payload를 생성하는 공격 도구가 아니다. 여기서의 LLM은 simulation world가 그럴듯하게 이어지는지 검수하고, mutation plan이 허용 범위 안에 있는지 설명하는 reviewer다. 특히 `Mutation Approval Reviewer`는 reviewer-only이며, 공격 선택·변조값 생성·state 수정·payload 생성 권한을 갖지 않는다.

### 3.5 Alternating Feedback Loop

Red와 Blue를 동시에 업데이트하면 서로의 정책이 계속 움직여 학습이 꼬일 수 있다. 따라서 보고서용 기준은 다음처럼 번갈아 학습한다.

```text
Blue update block: 10 episodes
  - Red policy frozen
  - Blue detection/defense weights only update

Red update block: 10 episodes
  - Blue policy frozen
  - Red attack weights/probe strategy only update

Fixed evaluation block: 3 episodes
  - Red and Blue both frozen
  - scorer evidence and decision log only collected
```

`10 episodes`는 기본값이며, 실험 시간이나 데이터 양에 따라 바꿀 수 있다. 중요한 원칙은 한쪽을 업데이트하는 동안 상대 정책을 고정해 비정상적인 동시 적응을 줄이는 것이다.

현재 구현에서는 `TrainingScheduler`가 이 cadence를 실행한다. Red policy state는 공격 weight, adaptive stealth set, telemetry probe delta를 저장한다. Blue policy state는 rule-based baseline에서 쓰는 `domain_trust`, `detection_sensitivity`, `escalation_threshold`, `feedback_counts`를 저장한다. Blue update block에서는 Red policy를 고정하고 Blue policy만 업데이트하며, Red update block에서는 Blue policy를 고정하고 Red weight/probe만 업데이트한다. Fixed evaluation block에서는 둘 다 고정한다.

현재 Blue는 rule-based baseline에 scorer feedback 기반 policy update를 붙인 형태다. 완전한 RL은 아니며, 보고서에서는 adaptive defense policy로 설명한다.

Policy Update Reviewer는 Red/Blue feedback learner가 만든 policy delta 후보를 심사한다. 외부 LLM reviewer는 선택사항이며, 대회 환경에서 외부 연결이 끊기거나 JSON/schema 검증에 실패하면 오프라인 `HeuristicPolicyUpdateReviewer`가 같은 bounded candidate 절차를 수행한다. 따라서 LLM이 없어도 전체 학습 루프는 순수 코드로 계속 실행된다.

외부 LLM 호출은 `src/dah_flawless/llm/`의 공통 adapter를 통한다. 각 역할 모듈은 JSON schema와 local fallback을 함께 제공해야 하며, LLM 응답이 invalid하거나 연결이 끊기면 fallback 결과를 decision log에 남긴다.

## 4. Red Attack AI Structure

우리가 설명할 Red AI는 아래 구조다.

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

| 모듈 | 역할 | 현재 구현 상태 |
|---|---|---|
| Observer | 현재 redacted state, blue_observed, history, raw-world feature 요약을 읽음 | redaction 경로와 simulator 입력으로 구현 |
| Situation Tagger | observed/feature에서 상황 태그 생성 | `situation_tagger.py`, `blue/tagger.py` |
| Goal Planner | 어떤 cyber-effect 목표를 노릴지 선택. 예: 오표적 선택, 명령 stale 처리, telemetry trust erosion | `attacks/goal_planner.py`. 현재 context와 이전 로그를 함께 보는 contextual UCB-style scoring |
| Attack Selector | tag와 후보 점수로 공격 선택 | `attacks/selector.py`, `red_agent.py` |
| Mutation Engine | blue_observed에 안전한 변조 적용 | `attacks/mutations.py` |
| Stealth Controller | 변조 폭을 줄여 탐지 회피 시도 | `red_agent.py`, tactic `boundary_probe` |
| Feedback Learner | scorer 결과로 공격 weight/probe_delta 업데이트 | `red_agent.update_weight()` |
| Decision Logger | 왜 이 공격을 골랐는지 로그화 | `decision_log`, `red_tactic`, `candidate_scores` |

### 4.1 Allowed Red Attack Surface

Red의 공격은 실제 시스템 침투가 아니라 **Blue가 받는 external observe를 오염시키는 simulator mutation**이다. `internal_observe`는 내부 센서/로컬 상태이므로 Red가 직접 바꾸지 않는다. 특수한 아군 C2 명령처럼 외부 입력이 내부 판단에 영향을 주는 경우만 간접 영향으로 설명한다.

현재 구현은 호환성을 위해 `blue_observed.telemetry`, `blue_observed.c2_message` 같은 flat key를 유지한다. 이 flat key들은 canonical 구조의 `blue_observed.external_observe.*`에 대응하는 compatibility view다. 새 설계 문서에서는 `external_observe`를 기준으로 말한다.

대회/보고서에서는 아래 범위까지를 공격 표면으로 설명한다.

| 범위 | Red가 할 수 있는 일 | 실제 의미 |
|---|---|---|
| observed telemetry mutation | 위치, 속도, 배터리, health, confidence를 작게 편향하거나 stale 처리 | Blue가 받는 관측값을 신뢰하기 어렵게 만듦 |
| mission/target belief mutation | 표적 confidence, area priority, route hint를 왜곡 | Blue의 임무 판단을 느리거나 틀리게 유도 |
| C2/message metadata mutation | timestamp, sequence, ACK 상태, freshness를 지연/누락/재정렬된 것처럼 표현 | 통신 계층 이상이 판단 계층에 주는 영향을 실험 |
| channel-level effect | delay, drop, jitter, reorder, loss burst를 시뮬레이션 | RF/SATCOM/API 통신 품질 저하를 추상화 |
| stealth/probe adjustment | mutation 크기와 빈도를 줄여 탐지 임계값 근처를 탐색 | 방어 AI가 어느 지점에서 탐지하는지 관찰 |

허용하지 않는 설명:

- 실제 네트워크 침투 명령, credential 탈취, malware, exploit payload
- 실제 RF 송신 파라미터나 장비 운용 절차
- 실제 API endpoint 공격 방법
- 특정 시스템을 대상으로 한 우회/침투 절차

`Mutation Approval Reviewer`는 Red 내부 reviewer다. 이 reviewer는 공격을 실행하는 모델이 아니라, 후보 mutation이 대회 시뮬레이션 범위 안에 있는지 검토한다. 허용되는 출력은 `approve`, `clamp`, `reject`, `explain`뿐이며, 실제 변조 적용은 항상 `Mutation Engine`이 한다.

검토 출력 예:

```json
{
  "approved": true,
  "reason": "C2 timestamp jitter is allowed because it only changes simulated blue_observed metadata.",
  "allowed_fields": ["blue_observed.c2_message.timestamp", "blue_observed.channel.delay_ms"],
  "max_delta_hint": "keep below current detector threshold unless attack_selector requests a probe",
  "safety_boundary": "no real RF/API instruction, no exploit payload"
}
```

### Red AI Input

Red가 볼 수 있는 값:

- `blue_observed`
- `mission`
- `capabilities`
- `defense_runtime` 중 redacted된 정보
- situation tags
- 제한적 feedback: 성공/탐지 여부, winner

Red가 보면 안 되는 값:

- `state["world"]`
- scorer 내부 계산
- Blue의 비공개 내부 정답

### Red AI Output

Red는 직접 시스템을 해킹하지 않는다. 출력은 다음 둘이다.

```text
Attack choice
Mutation plan for blue_observed
```

예:

```json
{
  "attack": "TIME_DESYNC_REPLAY",
  "target_domain": "command",
  "tactic": {
    "strategy": "ack_confusion",
    "matched_tags": ["ACK_CHANNEL_VISIBLE", "REPLAY_WINDOW_OPEN"]
  }
}
```

## 5. Situation Tagging Rules

태그는 "공격명"이 아니라 "관측된 상황의 의미"다.

좋은 태그:

- `C2_ENCRYPTED`
- `PAYLOAD_HIDDEN`
- `SEQUENCE_VISIBLE`
- `ACK_CHANNEL_VISIBLE`
- `REPLAY_WINDOW_OPEN`
- `GNSS_DEGRADED`
- `C2_PATTERN_EXPLOIT`
- `MISSION_PRIORITY_CHANGED`
- `BATTERY_ENERGY_IMPOSSIBLE`

나쁜 태그:

- `ATTACK_TIME_DESYNC_REPLAY`
- `RED_IS_ATTACKING`
- `HACK_SUCCESS`

태그는 Red와 Blue 모두에게 유용해야 한다.

- Red: 어떤 공격이 먹힐지 고름.
- Blue: 어떤 불변식을 의심할지 고름.

## 6. Blue Defense AI Structure

Blue AI는 하나의 거대한 if문이 아니라 역할별 agent pipeline이다.

```text
Redaction Boundary
-> Situation/Threat Detection
-> Mission Monitor
-> Defense Planner
-> Defense Action Application
-> Incident Report
```

| 모듈 | 역할 | 현재 구현 위치 |
|---|---|---|
| Redaction Boundary | Blue 입력에서 scorer_truth 제거 | `environment/redaction.py` |
| Situation Tagger | observed 기반 상황 태그 생성 | `blue/tagger.py`, `situation_tagger.py` |
| Threat Detection | 태그와 불변식으로 위협 생성 | `blue/threat_detection.py`, `blue/invariants.py` |
| Goal Consistency Checker | observed-only cyber-effect hypothesis 생성 | `blue/goal_consistency.py` |
| Mission Monitor | 위협이 임무에 미치는 영향 계산 | `blue/mission_monitor.py` |
| Defense Planner | 비용을 고려해 방어 action 선택 | `blue/defense_planner.py` |
| Action Application | observed를 격리/복구/검증 요청 | `blue/defense_planner.py` |
| Feedback Learner | scorer 결과로 domain trust/sensitivity/threshold 업데이트 | `blue/feedback_learner.py` |
| Incident Report | 보고서/운영자용 요약 생성 | `blue/incident_report.py` |

Blue의 기본 원칙:

- scorer_truth를 보지 않는다.
- 공격명을 직접 맞히려고 하지 않는다.
- Red가 고른 `red_goal`을 보지 않는다. 대신 internal/external observe, history, tags로 `EFFECT_*` hypothesis를 추정한다.
- observed 내부 모순, history, capability, communication metadata로 판단한다.
- 모든 강한 방어는 availability cost를 가진다.
- 너무 강한 방어는 `RED_ATTRITION`으로 이어질 수 있다.

### 6.1 Blue Baseline Policy

현재 보고서용 설계에서 Blue는 먼저 rule-based baseline으로 둔다. 이유는 방어 AI까지 처음부터 학습형으로 만들면 Red와 Blue가 동시에 변해 scorer feedback의 원인을 해석하기 어려워지기 때문이다.

현재 구현된 Blue Feedback Learner는 완전한 강화학습이 아니라 scorer feedback 기반 adaptive policy update다. `RED_BREACH`처럼 공격을 놓치면 target domain의 `detection_sensitivity`를 올리고 `escalation_threshold`를 낮춘다. false positive나 큰 availability cost가 발생하면 sensitivity를 낮추고 threshold를 올려 과방어를 줄인다. 이 업데이트는 `TrainingScheduler`의 Blue update block에서만 적용된다.

초기 Blue rule은 다음 정보를 사용한다.

| 입력 | 사용 방식 |
|---|---|
| blue_observed | Blue가 실제로 받았다고 가정하는 관측값 |
| observed history | 최근 30-step episode 안의 변화율, 누락, 지연, stale 여부 |
| situation tags | `GNSS_DEGRADED`, `ACK_CHANNEL_VISIBLE`, `C2_PATTERN_EXPLOIT` 같은 의미 태그 |
| capability/mission context | 어떤 방어 action이 가능한지, mission availability 비용은 얼마인지 |

Blue Goal Consistency Checker는 다음과 같은 observed-only hypothesis를 만든다.

| hypothesis tag | 근거 |
|---|---|
| `EFFECT_TELEMETRY_TRUST_EROSION` | internal telemetry와 external telemetry의 battery/motor 불일치 |
| `EFFECT_WRONG_TARGET_SELECTION` | history 대비 mission priority/recommended area drift |
| `EFFECT_COMMAND_STALE_ACCEPTANCE` | sequence/timestamp lag, replay-like tags |
| `EFFECT_ACK_CAUSAL_CONFUSION` | ACK sequence gap, ACK delay, accepted-with-gap |
| `EFFECT_CHANNEL_STATE_SUPPRESSION` | packet loss, heartbeat gap, latency/jitter 상승 |
| `EFFECT_DETECTION_BOUNDARY_PROBE` | 낮은 amplitude의 단일 effect 징후와 detector feedback 확보 가능성 |

Defense Planner는 이 effect tag를 이용해 같은 command domain threat도 다르게 대응한다. 예를 들어 ACK 혼란은 `HOLD_COMMAND`와 ACK field quarantine을 우선하고, channel suppression은 `RESET_CHANNEL_TIMING`과 revalidation을 우선한다. 이 단계도 실제 네트워크 차단 명령이 아니라 simulator 내부 observed 복구/검증 요청이다.

Blue가 절대 보면 안 되는 정보:

- raw_world 원본 전체
- scorer_truth/state["world"]
- Red가 고른 attack name
- scorer 내부 판정식

학습형 Blue는 이 baseline이 안정화된 뒤 붙인다. 그때도 Blue는 observed-only 원칙을 유지해야 한다.

## 7. Scorer Judgement

Scorer는 Red/Blue 어느 쪽에도 속하지 않는 admin/evaluator다. scorer만 scorer_truth와 blue_observed를 함께 볼 수 있다.

### 7.1 Attack Success

공격 성공은 target domain에서 scorer_truth와 observed가 의미 있게 벌어졌는지로 본다.

| target domain | trusted value | observed value |
|---|---|---|
| telemetry | `state["world"].uav.battery_percent`, `motor_status` | `blue_observed.telemetry.*` |
| mission | `state["world"].mission.area_priority` | `blue_observed.mission.area_priority` |
| command | `state["world"].command.*`, `time.true_timestamp` | `blue_observed.c2_message.*`, `time.received_timestamp` |

### 7.1.1 Goal Success

`attack_success`는 domain mismatch 판정이고, `goal_success`는 Red Goal Planner가 선택한 cyber-effect 목표 달성 판정이다. 둘은 일부러 분리한다.

예:

| goal_id | goal_success evidence |
|---|---|
| `WRONG_TARGET_SELECTION` | truth top area와 observed/recommended area 불일치, priority drift |
| `TELEMETRY_TRUST_EROSION` | battery/motor mismatch, energy consistency conflict |
| `COMMAND_STALE_ACCEPTANCE` | sequence lag, timestamp lag, command mismatch |
| `ACK_CAUSAL_CONFUSION` | ACK sequence gap, ACK delay, accepted-with-gap |
| `CHANNEL_STATE_SUPPRESSION` | packet loss, heartbeat gap, latency/jitter 상승 |
| `BLUE_OVERDEFENSE_ATTRITION` | defense action cost, availability drop, high-cost action count |
| `DETECTION_BOUNDARY_PROBE` | detector feedback 확보와 low-cost probe 여부 |

`score.goal_reward`는 Red Goal Planner/Feedback Learner가 목표별 가중치를 업데이트할 때 우선 사용하는 reward다. 외부 LLM이 이 값을 직접 생성하면 안 되고, scorer가 계산한 값을 해석하거나 reviewer로만 다룬다.

### 7.2 Detection Success

Blue가 attack target domain에 대해 confidence threshold 이상 threat를 냈으면 탐지 성공이다.

현재 scorer는 `DETECTION_WINDOW`와 `RECOVERY_WINDOW`를 evidence에 남겨, 현재 라운드뿐 아니라 최근 탐지/복구 맥락을 설명할 수 있게 한다.

### 7.3 Recovery Success

방어 후 observed가 scorer_truth에 다시 맞거나, target domain이 last known good/trusted restore로 복구되면 recovery success다.

### 7.4 Winner

| winner | 의미 |
|---|---|
| `RED_BREACH` | 공격은 성공했고 Blue가 탐지하지 못함 |
| `RED_ATTRITION` | 방어 비용 때문에 mission availability가 바닥남 |
| `BLUE` | Blue가 탐지했고 availability도 유지됨 |
| `BLUE_RECOVERY` | Blue가 탐지 후 신뢰 상태를 복구함 |
| `DRAW` | 명확한 승패 없음 |

판정 우선순위는 대체로 다음 흐름이다.

```text
attack_success and not detection_success -> RED_BREACH
availability < AVAIL_FLOOR -> RED_ATTRITION
recovery_success and availability >= RECOVERY_TARGET -> BLUE_RECOVERY
detection_success and availability >= AVAIL_FLOOR -> BLUE
else -> DRAW
```

### 7.5 Score Components And Feedback

Scorer는 단순히 승패만 주지 않는다. Red와 Blue가 각각 업데이트할 수 있도록 세부 점수를 나눠야 한다.

| component | 의미 | Red feedback | Blue feedback |
|---|---|---|---|
| `attack_effect` | scorer_truth와 blue_observed 사이의 임무상 의미 있는 차이 | 높을수록 선택한 attack weight 증가 | 높으면 해당 domain 방어 강화 |
| `stealth_score` | Blue가 탐지하지 못한 정도 | 높을수록 stealth/probe 전략 보상 | 낮으면 detector threshold/feature 개선 |
| `detection_score` | Blue가 올바른 domain 이상을 탐지한 정도 | 높으면 해당 공격 weight 감소 | 높을수록 탐지 rule 보상 |
| `containment_score` | Blue가 오염 확산을 막은 정도 | 높으면 우회 tactic 탐색 | 높을수록 방어 action 보상 |
| `recovery_score` | Blue가 정상 관측/임무 상태로 복구한 정도 | 높으면 장기 교란 전략 감소 | 높을수록 recovery action 보상 |
| `availability_cost` | 방어 때문에 임무 수행성이 떨어진 정도 | 높으면 attrition tactic 보상 | 높으면 과잉 방어 penalty |
| `false_positive_cost` | 공격이 약하거나 없는데 Blue가 과민 반응한 정도 | 높으면 decoy/probe 보상 | 높으면 threshold 조정 penalty |

Feedback Learner는 scorer 결과를 그대로 "정답"으로 외우면 안 된다. update는 attack family, target domain, situation tag 조합 단위의 weight를 조금씩 조정하는 방식이 좋다.

```text
feedback_key = attack_family + target_domain + matched_tags
new_weight = old_weight + learning_rate * normalized_reward
```

보고서에서는 이 식을 "완전한 강화학습 구현"이라고 부르지 말고, **scorer feedback 기반 adaptive weight update**라고 설명한다.

## 8. Logging Contract

중요 로그 필드:

| 필드 | 의미 |
|---|---|
| `raw_world_source_hash` | raw_world sample 출처 hash |
| `raw_world_feature_scores` | raw_world feature 기반 후보 점수 |
| `red_situation_tags` | Red가 공격 전 본 태그 |
| `red_situation_tag_details` | 태그별 confidence/evidence/meaning |
| `attack` | 선택된 공격 |
| `red_tactic` | 세부 tactic과 후보 점수 |
| `threats` | Blue threat list |
| `defense_actions` | Blue action list |
| `score.evidence.trusted_value` | scorer_truth 기준값 |
| `score.evidence.observed_value` | Blue가 받은 값 |
| `score.goal_success` | selected cyber-effect 목표 달성 여부 |
| `score.goal_reward` | Goal Planner/Feedback Learner용 목표별 reward |
| `score.evidence.goal_score` | goal_id별 evidence와 effect_score |
| `episode` | EpisodeRunner 실행 시 현재 episode 번호 |
| `episode_step` | episode 안에서의 step 번호 |
| `global_step` | 전체 episode 실행을 통틀어 증가하는 step 번호 |
| `block` | TrainingScheduler 실행 시 `BLUE_UPDATE`, `RED_UPDATE`, `FIXED_EVAL` 중 현재 block |
| `red_policy_state` | Red 공격 weight/probe 상태 |
| `blue_policy_state` | Blue domain trust, detection sensitivity, escalation threshold, feedback counts |
| `policy_update_review` | policy delta 후보, selected scale, rejection count, fallback reason |
| `feedback` | scorer 결과를 policy update에 넘기는 요약 |
| `red_input_redacted` | Red 입력에서 `world` 제거 여부 |
| `blue_input_redacted` | Blue 입력에서 `world` 제거 여부 |

main 브랜치와 병합할 때는 `red_policy_state`, `blue_policy_state`, `feedback` 로그도 보존하는 것이 좋다. 이 세 필드는 adaptive 공방성을 설명하는 데 강하다.

## 9. Implementation Status

| 구성요소 | 상태 |
|---|---|
| raw_world schema | 구현 |
| rule-based raw_world generator | 구현 |
| feature extractor | 구현 |
| state adapter | 구현 |
| situation tagger | 구현 |
| goal planner | 구현 |
| goal-aware scorer | 구현 |
| blue goal consistency checker | 구현 |
| attack selector | 구현 |
| mutation policy docs/config | 구현 |
| mutation profile routing | 구현 |
| mutation engine | 구현 |
| stealth/probe controller | 기본 구현 |
| feedback learner | Red/Blue 기본 구현 |
| LLM adapter | 구현 |
| policy update reviewer | 구현 |
| blue invariant defense | 구현 |
| scorer | 구현 |
| 30-step EpisodeRunner | 구현 |
| Alternating TrainingScheduler | 구현 |
| Mutation Approval Reviewer | 구현 |
| Mutation Policy field-level enforcement | 핵심 필드 구현, YAML config 자동 로딩 구현 |
| VAE world generator | 미구현 |
| 실제 RF/API adapter | 미구현 |
| 실제 침투/익스플로잇 실행 | 범위 밖 |
| 보고서 PDF/ZIP 생성 스크립트 | 현재 브랜치에서 제거 |

## 10. Do And Do Not

해야 할 것:

- raw_world와 scorer_truth를 분리해서 말한다.
- 공격은 안전한 observed mutation이라고 말한다.
- Red/Blue가 scorer_truth를 보지 않는다고 명시한다.
- raw_world feature와 situation tag가 공격 선택의 근거라고 설명한다.
- 방어 비용과 availability를 반드시 함께 설명한다.

하지 말 것:

- `state["world"]`를 raw_world라고 부르기.
- Blue가 정답지를 보고 탐지한다고 암시하기.
- 실제 해킹, 실제 RF 송신, 실제 API adapter가 구현됐다고 쓰기.
- VAE/RL/LLM이 이미 구현됐다고 과장하기.
- 보고서/PDF/ZIP 산출물이 repo에 있다고 가정하기.

## 11. One-Sentence Rule

`raw_world`는 현실 원천 신호, `state["world"]`는 scorer-only 정답지, `blue_observed`는 Blue가 받은 조작 가능 입력이다.
