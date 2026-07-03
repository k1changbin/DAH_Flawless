# LLM Alignment Guide

이 문서는 DAH_Flawless를 다른 LLM이나 새 세션에서 다룰 때 용어 혼동을 막기 위한 안내 스크립트다. 아래 블록을 그대로 붙여넣고 작업을 시작하면 된다.

## Copy-Paste Script

```text
너는 DAH_Flawless 레포를 보는 보조 LLM이다. 아래 용어를 반드시 지켜라.

1. raw_world
- 현실 전장에 존재하는 외부 원천 신호/방출/환경/사건이다.
- 예: RF spectrum, GNSS field, SATCOM emissions, MAVLink-like C2 emissions, weather, terrain, physical scene.
- raw_world는 docs/raw_world_schema.md와 configs/raw_world_schema.yaml의 대상이다.
- raw_world 자체는 Blue AI가 받는 정리된 입력이 아니다.

2. scorer_truth
- 시뮬레이터와 scorer가 채점에 쓰는 신뢰 기준 상태다.
- 현재 MVP 코드에서는 호환성 때문에 state["world"] 키에 저장된다.
- state["world"]를 raw_world라고 부르지 말고 scorer_truth 또는 scorer-only truth라고 불러라.
- Red/Blue Agent는 state["world"]를 보면 안 된다.

3. blue_observed
- Blue 관제/방어 AI가 실제로 받는 관측 입력이다.
- Red 공격의 직접 조작 대상은 blue_observed의 값, 순서, 시간, 메타데이터다.
- Blue는 blue_observed 내부 모순과 history만으로 탐지한다.

4. 파이프라인
raw_world
-> Feature Extractor
-> State Adapter
-> scorer_truth(state["world"]) + blue_observed
-> Situation Tagger
-> Red/Blue decision
-> Scorer/Admin 판정

5. 금지 표현
- "world는 현실 raw signal이다"라고 쓰지 마라. 현재 코드의 world 키는 scorer_truth다.
- "Blue가 world를 본다"라고 쓰지 마라. Blue 입력은 redaction을 거쳐 world 키가 제거된다.
- "실제 해킹 도구"라고 쓰지 마라. 현재 공격은 안전한 simulation mutation이다.
- VAE, RL, LLM, API adapter가 구현되어 있다고 과장하지 마라. 지금 구현된 것은 raw-world generator/extractor/adapter, situation tagger, selector, mutation, defense/scorer다.

6. 로그 필드
- raw_world_source_hash: raw_world generator sample의 해시다.
- raw_world_feature_scores: raw_world에서 추출된 공격 후보 점수다.
- truth_model: "scorer_truth"이면 scorer-only 기준 상태를 뜻한다.
- truth_storage_key: 현재 호환 키인 state["world"]를 뜻한다.

7. 보고서 표현
- "raw world는 현실 원천 신호, scorer truth는 채점용 기준 상태, observed는 AI가 받은 입력"이라고 설명한다.
- Scorer/Admin Diff는 Blue 화면이 아니라 증거/채점 화면이라고 반드시 명시한다.
```

## Current Implementation Boundary

| 개념 | 현재 구현 위치 | 구현 상태 |
|---|---|---|
| raw_world schema | `configs/raw_world_schema.yaml`, `docs/raw_world_schema.md` | 구현 |
| raw_world generator | `src/dah_flawless/world/generator.py` | rule-based 구현 |
| feature extractor | `src/dah_flawless/world/feature_extractor.py` | 구현 |
| state adapter | `src/dah_flawless/world/state_adapter.py` | raw_world를 MVP state로 변환 |
| scorer_truth | `state["world"]` | 호환 키, scorer/admin only |
| blue_observed | `state["blue_observed"]` | Red mutation/Blue detection 대상 |
| Situation Tagger | `src/dah_flawless/situation_tagger.py` | 구현 |
| Attack Selector | `src/dah_flawless/attacks/selector.py` | 구현 |
| Mutation Engine | `src/dah_flawless/attacks/mutations.py` | 안전한 시뮬레이션 변조 |
| Stealth/Feedback | `red_agent.py`, `selector.py`, `scorer.py` | 기본 구현 |
| VAE world generator | 없음 | 설계 후보, 미구현 |
| 실제 RF/API adapter | 없음 | 보고서 확장 가능성, 미구현 |

## One-Sentence Rule

`raw_world`는 현실 원천 신호, `state["world"]`는 scorer-only 정답지, `blue_observed`는 Blue가 받은 조작 가능 입력이다.
