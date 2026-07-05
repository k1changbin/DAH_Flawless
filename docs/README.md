# DAH Flawless Design Notes

이 폴더는 예선 보고서와 MVP 구현에 바로 연결되는 설계 문서를 모은다.

| 파일 | 내용 |
|---|---|
| `llm_alignment_guide.md` | 다른 LLM/새 세션용 용어 정렬 안내 스크립트 |
| `world_observed_model.md` | raw_world, scorer_truth, blue_observed 접근 권한 정의 |
| `raw_world_schema.md` | 현실 원천 신호(raw_world) schema와 generator/extractor 흐름 |
| `schema_design.md` | runtime state의 scorer_truth(`state["world"]`)와 blue_observed schema |
| `field_formats.md` | 각 schema 필드의 타입, 단위, 범위, 예시 |
| `mutation_policy.md` | Red가 변조할 수 있는 external observe 필드와 profile별 max delta |
| `attack_effect_contracts.md` | 공격 후보와 기대 cyber-effect/성공 evidence를 묶는 contract |
| `scenario_pack.md` | holdout 평가용 scenario pack과 각 scenario의 초기 조건 |
| `situation_tags.md` | observed 기반 situation tag 정의 |
| `attack_mapping.md` | 공격 3종과 schema/tag/방어 매핑 |
| `encrypted_channel_attack_ai.md` | 암호화 통신 환경에서 Red AI가 공격 방법을 선택하는 설계 |
| `reference_sources.md` | 신뢰 가능한 공개 출처와 사용 목적 |

읽는 순서:

```text
llm_alignment_guide.md
→ world_observed_model.md
→ raw_world_schema.md
→ schema_design.md
→ field_formats.md
→ mutation_policy.md
→ attack_effect_contracts.md
→ situation_tags.md
→ attack_mapping.md
→ encrypted_channel_attack_ai.md
→ reference_sources.md
```

보고서에 넣을 때는 `world_observed_model.md`의 정의 문장, `schema_design.md`의 표, `field_formats.md`의 필드 형식 표, `attack_mapping.md`의 공격별 Detect/Contain/Recover 표를 우선 사용한다.

용어 주의:

- `raw_world`는 현실 원천 신호다.
- `scorer_truth`는 현재 코드에서 `state["world"]` 키에 저장되는 채점용 기준 상태다.
- `blue_observed`는 Blue AI가 받은 입력이며 Red mutation의 직접 대상이다.
