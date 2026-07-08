# DAH_Flawless 설계 가치 정리

이 문서는 현재 DAH_Flawless가 왜 이런 환경, 공격/방어 구조, 학습 방식을 택했는지 보고서용으로 정리한 것이다. 실제 침투 절차나 실제 통신망 공격법을 구현하는 문서가 아니라, UAV/UGV/SATCOM 환경에서 관측값 오염과 방어 판단을 안전하게 시뮬레이션하기 위한 아키텍처 설명이다.

## 1. 환경 설계

### 1.1 왜 `raw_world`, `world`, `observe`를 분리했는가

| 개념 | 의미 | 누가 볼 수 있는가 | 설계 이유 |
|---|---|---|---|
| `raw_world` | RF, GNSS, SATCOM, MAVLink-like C2, 날씨, 지형처럼 현실 전장에 존재하는 원천 신호/방출/환경 | World Generator, Feature Extractor | 현실의 신호는 바로 AI가 읽기 좋은 JSON 판단값이 아니므로, 먼저 원천 데이터에 가까운 형태로 만든다. |
| `state["world"]` | 채점기가 쓰는 정답 상태, 즉 scorer truth | Scorer/Admin only | Red/Blue가 정답지를 보는 치팅을 막고, 공격 성공 여부를 일관되게 평가한다. |
| `blue_observed.internal_observe` | Blue 내부 기준점. 기체 내부 센서, 내부 C2 상태, 로컬 추정값에 해당 | Blue | 현재 MVP에서는 신뢰 기준점이다. Red가 직접 변조하지 못한다. |
| `blue_observed.external_observe` | 외부 통신/원격 관측/수신 telemetry처럼 Red가 시뮬레이션 범위 안에서 오염시킬 수 있는 값 | Blue, Red의 mutation surface | 실제 전장에서 외부 입력은 지연, 누락, 재전송, spoofing, metadata 왜곡 등에 노출될 수 있으므로 공격 표면으로 둔다. |

핵심은 "현실의 진실", "채점용 정답", "방어 AI가 실제로 받는 값"을 같은 변수로 섞지 않는 것이다. 이 분리가 있어야 Blue가 정답을 몰라도 방어하고, Scorer는 정답을 기준으로 냉정하게 평가할 수 있다.

### 1.2 현재 환경 흐름

```text
raw_world
-> Feature Extractor
-> State Adapter
-> Situation Tagger
-> Red/Blue Agent
-> Mutation / Defense
-> Scorer
-> Feedback Learner
-> Decision / Frontend Logs
```

| 단계 | 역할 | 현재 구현 |
|---|---|---|
| Raw World Schema | 가능한 전장 원천 신호 도메인 정의 | `docs/raw_world_schema.md`, `configs/raw_world_schema.yaml` |
| World Generator | 랜덤하지만 인과성이 있는 환경 샘플 생성 | `src/dah_flawless/world/generator.py` |
| Feature Extractor | raw world에서 통신/신호/환경 특징값 추출 | `src/dah_flawless/world/feature_extractor.py` |
| State Adapter | 특징값을 agent가 읽을 수 있는 상태로 변환 | `src/dah_flawless/world/state_adapter.py` |
| Situation Tagger | 수치와 신호 특징을 전술 태그로 변환 | `src/dah_flawless/situation_tagger.py` |

### 1.3 UAV/UGV/SATCOM 환경값을 이렇게 잡은 근거

MAVLink는 UAV의 명령, telemetry, heartbeat, mission, parameter, command, time synchronization 같은 메시지 계층을 제공하는 대표적인 오픈 프로토콜이므로 UAV C2/telemetry의 기본 참조점으로 적절하다. 공식 MAVLink 문서도 message signing, routing, packet loss, command/mission/heartbeat protocol, high latency protocol 등을 별도 항목으로 다룬다.

그래서 raw world에는 다음 도메인을 둔다.

| 도메인 | 예시 데이터 | 공격/방어에서 중요한 이유 |
|---|---|---|
| RF spectrum | noise floor, unknown periodic emitter, burst interval | 정체불명 주기 신호, C2 후보, 재밍/간섭 가능성 판단 |
| GNSS field | CN0, satellite visibility, interference, multipath | 위치 계산 전의 원천 신호 조건을 표현 |
| UAV C2 emissions | MAVLink-like frame metadata, sequence, msgid, timestamp, signing flag | 암호화되어도 sequence/timing/ACK 같은 metadata는 판단 근거가 될 수 있음 |
| SATCOM emissions | latency, packet loss, BLOS active, rain fade | 지연/재전송/링크 품질 저하와 replay 오판 위험 |
| mission space | target area, no-fly zone, return base, priority | priority poisoning이나 wrong target selection의 평가 기준 |
| weather/terrain | wind, occlusion, multipath, visibility | 센서 신뢰도와 통신 품질의 인과 배경 |

참고 문서:

- MAVLink Guide: https://mavlink.io/en/guide/
- NIST SP 800-207, Zero Trust Architecture: https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf
- NIST SP 800-162, Attribute Based Access Control: https://csrc.nist.gov/pubs/sp/800/162/upd2/final
- BAZAM, multi-UAV wireless zero-trust authentication: https://arxiv.org/abs/2407.00630

## 2. 공격/방어 원리

### 2.1 Red AI 구조

Red는 실제 해킹 payload를 실행하는 코드가 아니라, 시뮬레이터 안에서 Blue가 받는 `external_observe`를 제한된 mutation policy 안에서 오염시키는 공격 의사결정 AI다.

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

| 모듈 | 역할 | 현재 상태 |
|---|---|---|
| Observer | 필요한 world/observe 특징만 읽음 | 구현됨 |
| Situation Tagger | 수치와 신호 상태를 태그로 변환 | 구현됨 |
| Goal Planner | 현재 태그, 이전 로그, 성공률을 보고 공격 목표 선택 | 구현됨 |
| Attack Selector | 계약에 맞는 공격 후보 선택 | 구현됨 |
| Mutation Engine | 허용 필드와 max delta 안에서 external observe 변조 | 구현됨 |
| Stealth Controller | 탐지 가능성을 고려해 mutation 폭 조정 | 부분 구현 |
| Feedback Learner | 성공/실패/탐지/보상 기반 가중치 업데이트 | 구현됨 |
| Decision Logger | 왜 이 목표와 공격을 골랐는지 기록 | 구현됨 |

현재 공격 대분류는 세 가지다.

| 공격군 | 의미 | 목표 예시 |
|---|---|---|
| `TELEMETRY_FDI` | 외부 telemetry 값에 false data injection을 가정 | telemetry trust erosion, boundary probing |
| `PRIORITY_POISONING` | mission priority, recommended area 같은 임무 판단값 오염 | wrong target selection |
| `TIME_DESYNC_REPLAY` | 암호화 payload가 보이지 않아도 sequence/timestamp/ACK/link metadata가 흔들리는 상황 | stale command acceptance, ACK causal confusion, channel suppression |

이 공격군은 실제 침투 절차가 아니라 "외부 관측값이 오염되었을 때 방어 AI가 어떻게 대응하는가"를 학습시키기 위한 안전한 추상화다.

### 2.2 Blue AI 구조

Blue는 `state["world"]`를 볼 수 없고, 내부/외부 observe만 보고 판단한다.

```text
Observe Intake
-> Invariant / Consistency Check
-> Goal Consistency
-> Observe Policy Gate
-> Defense Planner
-> Defense-Effect Contract
-> Scorer Feedback
-> Blue Feedback Learner
```

| 모듈 | 역할 | 현재 상태 |
|---|---|---|
| Invariants | 내부/외부 observe의 물리/시간/임무 정합성 검사 | 구현됨 |
| Goal Consistency | Red 목표 효과가 실제 임무 판단에 영향을 주었는지 검사 | 구현됨 |
| Observe Policy Gate | external observe를 어느 수준으로 사용할지 결정 | 구현됨 |
| Defense Planner | quarantine, revalidate, hold command, fallback 등 방어 action 선택 | 구현됨 |
| Defense-Effect Contract | 탐지와 완전 복구 사이의 containment를 평가 | 구현됨 |
| Feedback Learner | domain trust, sensitivity, threshold 조정 | 구현됨 |

### 2.3 ZTA-inspired Observe Policy Gate

현재 구현은 ZTA 전체 구현이 아니라, Red 변조 표면인 `external_observe`에 대한 경량 policy gate다. `internal_observe`는 trust anchor로 둔다.

Gate는 각 observe domain에 대해 다음 결정을 내린다.

```text
ALLOW
ALLOW_WITH_MONITOR
DOWNGRADE
REVALIDATE
QUARANTINE
DENY
```

이 결정은 공격 탐지 성공 여부를 직접 바꾸는 값이 아니라, "이 observe를 임무 판단에 얼마나 권위 있게 사용할 것인가"를 조절한다. 예를 들어 완전 복구는 못 했더라도 오염 가능성이 있는 telemetry를 `QUARANTINE`하면 Blue는 그 값을 임무 판단의 핵심 근거로 쓰지 않게 된다. 그래서 recovery와 containment를 분리했다.

근거:

- NIST SP 800-207은 네트워크 위치만으로 암묵적 신뢰를 주지 말고, resource 접근을 지속적으로 판단하는 zero trust 원칙을 제시한다.
- NIST SP 800-162의 ABAC는 subject/object/action/environment attribute를 평가해 권한을 결정한다.
- RAdAC 계열 연구는 상황 인식과 동적 위험도에 따라 접근 결정을 바꾸는 방식을 다룬다.

현재 적용 방식:

| 원칙 | 우리 코드 적용 |
|---|---|
| no implicit trust | external observe는 들어왔다고 바로 authoritative하게 쓰지 않음 |
| attribute-based policy | provenance, integrity, freshness, anchor agreement, history consistency, capability를 점수화 |
| dynamic/risk-adaptive decision | mission criticality, availability, 과거 불일치, domain별 trust에 따라 결정 변경 |
| containment over binary detection | 탐지/미탐지만 보지 않고 downgrade/quarantine으로 피해 제한 |

참고 문서:

- NIST SP 800-207, Zero Trust Architecture
- NIST SP 800-162, ABAC
- Situational Awareness based Risk-Adaptable Access Control in Enterprise Networks: https://arxiv.org/abs/1710.09696

### 2.4 학습 원리

현재 학습은 완전한 딥러닝 end-to-end 모델이 아니라, 룰 기반 판단과 로그 기반 policy update가 결합된 경량 adversarial learning 구조다.

```text
1 round = 하나의 동적 combat episode
episode 내부 step = Red/Blue가 각자 행동 또는 대기
최대 step = 100
종료 = Red/Blue가 충분히 성공/실패/안정/중단을 판단하거나 max step 도달
```

Red 행동 예시:

- `WAIT`
- `PROBE_BOUNDARY`
- `SLOW_DRIFT`
- `ESCALATE_MUTATION`
- `SWITCH_TACTIC`
- `FINALIZE_ATTACK`
- `ABORT`

Blue 행동 예시:

- `WAIT`
- `PASSIVE_MONITOR`
- `INSPECT_INTERNAL`
- `RAISE_SUSPICION`
- `DEFEND`

Scorer는 다음을 분리해서 본다.

| 평가값 | 의미 |
|---|---|
| `attack_success` | mutation 자체가 목표 observe에 영향을 주었는가 |
| `goal_success` | 선택한 공격 목표에 맞는 임무 효과가 생겼는가 |
| `detection_success` | Blue가 공격 domain/effect를 잡았는가 |
| `containment_score` | 탐지 이후 피해 제한, 격리, 권위 하향, revalidation이 되었는가 |
| `recovery_success` | 오염 observe가 trusted anchor 또는 truth에 가깝게 복구되었는가 |
| `mission_impact_score` | 공격/방어가 실제 임무 판단, 안전, 가용성에 미친 정도 |
| `availability` | 방어 action 비용까지 포함한 임무 지속 가능성 |

학습 방향은 단순히 "Red 성공률 vs Blue 성공률"이 아니라 다음을 동시에 추구한다.

- Red: 어떤 상황 태그와 world 조건에서 어떤 공격 목표/전술이 효과적인지 학습
- Blue: 어떤 domain/effect에서 탐지 민감도, escalation threshold, trust budget을 조정해야 하는지 학습
- Scorer: 공격 성공, 방어 성공, containment, attrition, mission impact를 분리해서 평가

### 2.5 탐지/방어 근거 문헌과 적용점

| 문헌/자료 | 핵심 아이디어 | 우리 시스템 적용 |
|---|---|---|
| CUSIGN detector for stealthy CPS sensor attacks | 작은 false data injection도 residual sign의 비정상 패턴으로 탐지 가능 | telemetry residual, 내부/외부 anchor 차이, safety anchor residual 태그 |
| Quickest detection of FDI attack in remote state estimation | FDI를 빨리 잡기 위해 belief/threshold 기반 탐지 사용 | Blue effect threshold, detection sensitivity 업데이트 |
| Randomized Detector Tuning for Attack Impact Mitigation | 고정 threshold는 공격자가 학습할 수 있으므로 threshold switching이 유리할 수 있음 | Blue threshold/sensitivity를 로그 기반으로 동적으로 조정 |
| NIST SP 800-184, cybersecurity event recovery | 복구는 원상복구뿐 아니라 mission function continuity 관점에서 봐야 함 | recovery와 containment 분리 |
| NIST SP 800-160 Vol.2, cyber resiliency | withstand, recover, adapt를 분리해 사이버 회복탄력성 평가 | containment, availability, feedback learner |

참고 문서:

- Memoryless Cumulative Sign Detector for Stealthy CPS Sensor Attacks: https://arxiv.org/abs/2005.07821
- Quickest Bayesian and non-Bayesian detection of false data injection attack: https://arxiv.org/abs/2010.15785
- Feasibility of Randomized Detector Tuning for Attack Impact Mitigation: https://arxiv.org/abs/2503.11417
- NIST SP 800-184: https://csrc.nist.gov/pubs/sp/800/184/final
- NIST SP 800-160 Vol. 2 Rev. 1: https://csrc.nist.gov/pubs/sp/800/160/v2/r1/final

## 3. 궁극적인 장점과 단점

### 3.1 장점

| 장점 | 설명 |
|---|---|
| 전장형 관측 구조에 맞음 | 클라우드 API 환경이 아니라 UAV/UGV/SATCOM의 신호, 지연, metadata, 외부 관측 오염을 중심으로 설계했다. |
| Blue가 정답을 보지 않음 | 실제 방어 AI처럼 observe만 보고 판단하므로 평가가 더 정직하다. |
| 공격과 방어가 동시에 설명 가능 | 공격 목표, 공격 후보, mutation 근거, Blue 방어 action, scorer 결과가 로그로 남는다. |
| 실제 데이터 부족 문제를 완화 | 방어 AI를 바로 학습시킬 실제 공격 데이터가 적어도, Red AI가 공격 상황을 생성해 training signal을 만든다. |
| 탐지와 복구 사이를 평가 가능 | 완전 복구만 성공으로 보지 않고, quarantine/downgrade/revalidate 같은 부분 containment도 평가한다. |
| 탑재형 AI로 축소 가능 | LLM 없이도 룰 기반 fallback과 policy update가 돌아가므로 드론 같은 제한된 컴퓨터에 맞게 경량화할 여지가 있다. |
| 보고서 설득력이 있음 | MAVLink, ZTA/ABAC/RAdAC, CPS FDI detection, cyber resiliency 문헌과 코드 구조가 연결된다. |

### 3.2 단점

| 단점 | 설명 | 보완 방향 |
|---|---|---|
| 아직 실제 RF/통신 물리 계층은 아님 | 현재는 signal/metadata를 시뮬레이션한 것이다. 실제 SDR, RF capture, flight log와 직접 연결되지는 않았다. | SigMF/RINEX/PCAP/MAVLink log replay adapter 추가 |
| 공격군이 좁음 | 현재 구현 공격은 `TELEMETRY_FDI`, `PRIORITY_POISONING`, `TIME_DESYNC_REPLAY` 중심이다. | 같은 대분류 안의 파생 tactic 확대, scenario pack 확장 |
| 학습이 딥러닝이라기보다 policy learning에 가까움 | Qwen 같은 LLM은 reviewer/보조판단으로 붙일 수 있지만 현재 핵심은 룰과 가중치 업데이트다. | LLM reviewer, learned causal model, lightweight RL을 단계적으로 추가 |
| Scorer 수식 편향 가능 | 어떤 값을 보상으로 크게 주느냐에 따라 Red가 특정 목표에 몰릴 수 있다. | holdout scenario, diversity penalty, causal checker 강화 |
| Sim-to-real gap | 시뮬레이터에서 먹히는 공격/방어가 실제 드론에서 그대로 유효하다는 보장은 없다. | 실제 MAVLink log, PX4/ArduPilot SITL, Hardware-in-the-loop 검증 |
| ZTA가 만능은 아님 | 과도한 DENY/QUARANTINE은 오히려 가용성을 깎을 수 있다. | DENY보다 DOWNGRADE/REVALIDATE 중심, mission criticality 기반 적용 |

### 3.3 드론 탑재 AI 사이버전 코드로서의 가치

이 시스템은 "드론에 실어 실제 침투를 수행하는 공격 코드"보다는 다음 가치가 더 크다.

1. 탑재형 방어 의사결정 브레인
   - 외부 observe를 무조건 믿지 않고, 내부 기준점과 history를 비교해 사용할지 말지 결정한다.
   - 링크 지연, replay 의심, telemetry 오염, mission priority 오염을 각각 다른 방식으로 다룬다.

2. 사전 학습용 adversarial simulator
   - 실제 공격 데이터가 적어도 Red가 오염 상황을 만들고 Blue가 방어하면서 방어 정책을 개선한다.
   - 대회 환경에서는 이 부분이 가장 설득력 있는 AI적 가치다.

3. 작전 후 분석/설명 도구
   - 왜 Red가 그 공격을 골랐는지, Blue가 왜 격리했는지, Scorer가 왜 성공/실패로 봤는지 남긴다.
   - 블랙박스 신경망보다 보고서와 심사에서 설명하기 쉽다.

4. LLM 보조판단 확장 가능
   - 온라인 LLM이 있으면 mutation approval reviewer, goal planner reviewer, log summarizer로 사용한다.
   - 외부 연결이 끊기면 rule-based fallback으로 계속 동작한다.
   - LLM은 직접 공격 payload 생성기가 아니라, 허용 범위/인과성/가중치 변화가 말이 되는지 검토하는 reviewer로 두는 것이 안전하다.

### 3.4 최근 1000 round 실험 기준 현재 상태

최근 `RoundCombatRunner` 1000 round 결과는 다음 경향을 보였다.

| 지표 | 값 |
|---|---:|
| Blue 승리 | 648 |
| Red breach | 7 |
| Red attrition | 166 |
| Draw | 179 |
| detection rate | 0.816 |
| attack success rate | 0.889 |
| goal success rate | 0.782 |
| average containment score | 0.5933 |
| average causal consistency | 0.9652 |
| observe policy restricted rounds | 400 |
| 평균 step 수 | 16.329 |

해석:

- ZTA-inspired observe policy gate와 telemetry/mission gate 보강 이후 `RED_BREACH`는 크게 줄었다.
- 대신 `RED_ATTRITION`이 남아 있다. 이는 Blue가 공격을 막기 위해 많은 방어 비용을 쓰는 경우가 여전히 있다는 뜻이다.
- 즉 현재 Blue는 "뚫리는 것"은 줄였지만, "비용 효율적으로 막는 것"은 아직 개선 여지가 있다.
- 다음 개선은 방어 성공률을 단순히 올리는 것이 아니라, 낮은 비용의 monitor/quarantine/revalidate action을 더 잘 선택하게 하는 쪽이 맞다.

## 4. 한 문장 요약

DAH_Flawless의 현재 가치는 UAV/UGV/SATCOM 환경에서 외부 관측값이 오염되는 상황을 안전하게 생성하고, Red/Blue가 동적 episode 안에서 공격과 방어를 반복하며, Scorer가 탐지/containment/recovery/mission impact를 분리 평가해 탑재형 방어 AI의 의사결정 구조를 훈련하고 설명할 수 있게 만든다는 점이다.
