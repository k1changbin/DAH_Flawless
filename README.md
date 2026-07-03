# DAH Flawless MVP

DAH_Flawless는 DAH 예선 보고서용 Red/Blue 사이버 AI 시뮬레이션 MVP입니다. 실제 침투 도구가 아니라, UAV/UGV/위성통신 환경을 단순화한 안전한 시뮬레이션 안에서 Red AI가 Blue 관측 입력을 오염시키고 Blue AI가 관측값의 모순을 탐지·격리·복구하는 구조를 증명합니다.

## 핵심 요약

```text
raw_world -> Feature Extractor -> State Adapter
          -> scorer_truth(state["world"]) + blue_observed
          -> Situation Tagger -> Red/Blue Agents -> Scorer/Admin
```

가장 중요한 용어 경계는 아래와 같습니다.

| 용어 | 의미 | 접근 권한 |
|---|---|---|
| `raw_world` | 현실 전장에 존재하는 원천 신호·방출·환경·사건. 예: RF, GNSS, SATCOM, MAVLink-like C2 emission, 날씨, 지형 | generator/extractor/adapter |
| `scorer_truth` | scorer가 채점에 쓰는 기준 상태. 현재 코드에서는 호환성 때문에 `state["world"]` 키에 저장 | environment/scorer/admin only |
| `blue_observed` | Blue 관제 AI가 받은 관측 입력. Red의 직접 조작 대상 | Red/Blue |

`state["world"]`는 이름 때문에 헷갈리지만 raw world가 아닙니다. 현재 MVP에서는 scorer-only 정답지이며, Red/Blue 입력에서는 redaction으로 제거됩니다.

## 현재 구현

| 모듈 | 파일 | 상태 |
|---|---|---|
| Raw World Schema | `configs/raw_world_schema.yaml`, `docs/raw_world_schema.md` | 구현 |
| World Generator | `src/dah_flawless/world/generator.py` | rule-based 구현 |
| Feature Extractor | `src/dah_flawless/world/feature_extractor.py` | 구현 |
| State Adapter | `src/dah_flawless/world/state_adapter.py` | raw_world를 scorer_truth/blue_observed로 변환 |
| Situation Tagger | `src/dah_flawless/situation_tagger.py` | 통신/텔레메트리/임무 태그 구현 |
| Attack Selector | `src/dah_flawless/attacks/selector.py` | 태그 기반 후보 점수화 |
| Mutation Engine | `src/dah_flawless/attacks/mutations.py` | 안전한 observed 변조 |
| Blue Defense | `src/dah_flawless/blue/` | 탐지, 임무위험, 단계방어 |
| Scorer | `src/dah_flawless/scoring/scorer.py` | 승패, evidence, detection/recovery window |
| Dashboard | `streamlit_app.py` | raw_world sample 입력, 로그 분석 |

아직 구현하지 않은 것은 VAE 기반 world generator, 실제 RF/API adapter, 실제 네트워크 공격 실행입니다. 보고서에서는 “확장 가능 설계”로만 설명해야 합니다.

## 빠른 실행

PowerShell 기준:

```powershell
cd C:\Users\jisun\Documents\Codex\2026-06-29\sjs\work\DAH_Flawless
$env:PYTHONPATH='src'
python -m dah_flawless.main --seed 42 --rounds 5 --out data/logs/round_logs.jsonl --summary data/logs/summary.json
```

Raw world 샘플부터 시작하려면:

```powershell
$env:PYTHONPATH='src'
python scripts/run_world_generator.py --count 1 --out tmp/world/raw_world.jsonl
python scripts/run_feature_extractor.py --input tmp/world/raw_world.jsonl --out tmp/world/features.jsonl
python -m dah_flawless.main --seed 42 --rounds 3 --raw-world-sample tmp/world/raw_world.jsonl
```

대시보드:

```powershell
$env:PYTHONPATH='src'
streamlit run streamlit_app.py
```

## 테스트

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

현재 기준으로 `38 tests OK`를 확인했다. 테스트가 확인하는 핵심은 Red/Blue redaction, 공격 3종 E2E, raw_world pipeline, Situation Tagger, Attack Selector, scorer window, 로그 해시 체인, seed 재현성입니다.

## 로그에서 볼 것

| 필드 | 의미 |
|---|---|
| `raw_world_source_hash` | raw_world generator sample 해시 |
| `raw_world_feature_scores` | raw_world에서 뽑힌 공격 후보 점수 |
| `truth_model` | 현재는 `scorer_truth` |
| `truth_storage_key` | 현재 호환 키 `state["world"]` |
| `blue_input_redacted` | Blue 입력에서 scorer truth가 제거됐는지 |
| `score.evidence.trusted_value` | scorer_truth 기준값 |
| `score.evidence.observed_value` | Blue가 받은 값 |
| `red_situation_tag_details` | Red가 공격 선택 전에 본 상황 태그 근거 |

## 문서 읽는 순서

```text
docs/llm_alignment_guide.md
-> docs/world_observed_model.md
-> docs/raw_world_schema.md
-> docs/schema_design.md
-> docs/field_formats.md
-> docs/situation_tags.md
-> docs/attack_mapping.md
-> docs/encrypted_channel_attack_ai.md
```

다른 LLM에게 레포를 맡길 때는 먼저 아래 명령 출력물을 붙여넣습니다.

```powershell
python scripts/print_llm_alignment_guide.py
```

## 보고서 표현 원칙

- `raw_world`는 현실 원천 신호, `scorer_truth`는 채점용 기준 상태, `blue_observed`는 AI가 받은 입력이라고 설명합니다.
- `Scorer/Admin Diff`는 Blue 화면이 아니라 증거/채점 화면이라고 명시합니다.
- Red는 암호를 깨거나 시스템을 장악하지 않고, `blue_observed`의 값·시간·순서·메타데이터를 안전한 mutation으로 변조한다고 설명합니다.
- 실제 RF/API adapter와 VAE/RL/LLM 기반 고도화는 현재 구현이 아니라 다음 단계 설계로 구분합니다.
