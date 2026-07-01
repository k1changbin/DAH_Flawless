# DAH Flawless Design Notes

이 폴더는 예선 보고서와 MVP 구현에 바로 연결되는 설계 문서를 모은다.

| 파일 | 내용 |
|---|---|
| `reference_sources.md` | 신뢰 가능한 공개 출처와 사용 목적 |
| `world_observed_model.md` | world, observed, scorer, Red/Blue 접근 권한 정의 |
| `schema_design.md` | world와 blue_observed JSON schema 초안 |
| `field_formats.md` | 각 schema 필드의 타입, 단위, 범위, 예시 |
| `situation_tags.md` | observed 기반 situation tag 정의 |
| `attack_mapping.md` | 공격 3종과 schema/tag/방어 매핑 |

읽는 순서:

```text
reference_sources.md
→ world_observed_model.md
→ schema_design.md
→ field_formats.md
→ situation_tags.md
→ attack_mapping.md
```

보고서에 넣을 때는 `world_observed_model.md`의 정의 문장, `schema_design.md`의 표, `field_formats.md`의 필드 형식 표, `attack_mapping.md`의 공격별 Detect/Contain/Recover 표를 우선 사용한다.
