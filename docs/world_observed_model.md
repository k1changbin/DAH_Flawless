# Raw World, Scorer Truth, Observed Model

이 문서는 DAH_Flawless에서 가장 자주 헷갈리는 세 값을 분리한다.

```text
raw_world      = 현실 전장에 존재하는 원천 신호·방출·환경·사건
scorer_truth   = scorer가 채점에 쓰는 기준 상태, 현재 코드 키는 state["world"]
blue_observed  = Blue AI가 받은 관측 입력, Red가 조작하는 공격 표면
```

## 1. raw_world

`raw_world`는 UAV/UGV/위성통신 환경에서 모두가 원칙적으로 접할 수 있는 외부 현실이다. 사람이 보기 좋게 정리된 상태값이 아니라, 수신·해석·특징 추출이 필요한 원천 데이터에 가깝다.

예시:

| raw_world 영역 | 예시 |
|---|---|
| RF spectrum | 주파수별 전력, noise floor, 정체불명 주기 신호 |
| GNSS field | 위성 수신 상태, CN0, interference source, spoofing/jamming 단서 |
| SATCOM emissions | link availability, propagation delay, rain fade |
| UAV C2 emissions | MAVLink-like frame, sequence, msgid, tx time, signature 여부 |
| cyber message surface | encrypted payload 여부, visible metadata, ACK 흐름 |
| physical scene | friendly UAV, unknown UAV, target, occluder 위치 |
| weather/terrain | 가시거리, 강수, 지형 차폐, multipath 가능성 |

현재 구현:

```text
configs/raw_world_schema.yaml
docs/raw_world_schema.md
src/dah_flawless/world/generator.py
src/dah_flawless/world/feature_extractor.py
```

## 2. scorer_truth

`scorer_truth`는 시뮬레이션과 scorer가 판정에 쓰는 기준 상태다. 현재 MVP 코드에서는 기존 호환성 때문에 `state["world"]`라는 키에 저장된다.

중요:

- `state["world"]`는 raw_world가 아니다.
- `state["world"]`는 scorer/admin only 정답지다.
- Red Agent와 Blue Agent는 `state["world"]`를 직접 보면 안 된다.
- `score.evidence.trusted_value`는 이 scorer_truth에서 나온다.

예시:

```text
state["world"]["uav"]["battery_percent"] = 20
state["world"]["command"]["expected_sequence_number"] = 1021
```

## 3. blue_observed

`blue_observed`는 Blue 관제/방어 AI가 실제로 받은 관측 입력이다. Red의 직접 공격 대상이다.

예시:

```text
state["world"]["uav"]["battery_percent"] = 20
state["blue_observed"]["telemetry"]["battery_percent"] = 82
```

이 경우 scorer_truth 기준 배터리는 20%지만, Blue가 받은 입력은 82%다. Blue는 scorer_truth를 보지 않고 `blue_observed` 내부 모순, history, metadata, 불변식 위반으로 이상을 판단한다.

## 4. 변환 흐름

```mermaid
flowchart LR
  A["raw_world<br/>RF/GNSS/SATCOM/C2/scene"] --> B["Feature Extractor"]
  B --> C["State Adapter"]
  C --> D["scorer_truth<br/>state[\"world\"]"]
  C --> E["blue_observed"]
  E --> F["Situation Tagger"]
  F --> G["Red/Blue Agents"]
  D --> H["Scorer/Admin"]
  E --> H
```

## 5. 접근 권한

| 주체 | 볼 수 있는 값 | 보면 안 되는 값 |
|---|---|---|
| Red Agent | redacted state, `blue_observed`, tag, 제한적 feedback | `state["world"]`, Blue 내부 로직 |
| Blue Agent | redacted state, `blue_observed`, history, capabilities | `state["world"]`, Red 내부 상태 |
| Scorer/Admin | `state["world"]`, `blue_observed`, attack/threat/action logs | 없음 |
| World pipeline | raw_world sample, feature row, adapter output | 실제 운영망 제어권 |

## 6. 보고서 문장

```text
본 시스템은 raw world, scorer truth, observed를 분리한다. raw world는 RF/GNSS/SATCOM/C2 방출처럼 현실에서 수신 가능한 원천 신호이고, scorer truth는 그 원천 신호를 시뮬레이션 채점에 쓰도록 해석한 기준 상태다. Blue AI는 scorer truth를 보지 않고 blue_observed만 받으며, Red AI는 이 observed 입력의 값·시간·순서·메타데이터를 조작해 판단 오류를 유도한다.
```
