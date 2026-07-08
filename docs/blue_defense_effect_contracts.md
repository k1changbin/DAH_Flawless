# Blue Defense-Effect Contracts

이 문서는 Blue 방어 action이 Red cyber-effect를 얼마나 줄였는지 평가하는
`containment_score` 기준을 설명한다. 여기서 containment는 완전 복구가 아니다.
공격 효과가 남아 있어도 Blue가 피해 확산을 줄이고 임무 기능을 유지했다면 부분 성공으로
기록한다.

## 왜 추가했는가

기존 구조는 `detection_success`와 `recovery_success` 사이가 너무 비어 있었다.

```text
탐지함 -> 아직 scorer_truth와 완전히 같지는 않음 -> recovery_success false
```

이렇게 되면 Blue가 실제로 명령을 보류하거나, 오염 field를 격리하거나, 채널 timing을
복구해 피해를 줄여도 학습상 성공으로 거의 인정되지 않는다. 그래서
`Blue Defense-Effect Contract`를 추가해 아래 중간 지표를 둔다.

```text
detection_success
-> containment_score
-> recovery_success
```

## 문헌/문서 근거

- NIST SP 800-184는 사이버 이벤트 복구에서 조직 자원 식별/우선순위화, 현실적인
  테스트 시나리오, 과거 사건에서 배운 교훈, 중요한 mission function의 continuity를
  강조한다. 따라서 복구는 단순히 원래 값과 완전히 같아지는 것이 아니라, 중요한 기능을
  지속하고 영향을 최소화하는 과정으로 보아야 한다.
- NIST SP 800-61 Rev. 3은 incident detection, response, recovery 활동의 효율성과
  효과성을 개선하는 것을 incident response의 목표로 설명한다. 이 관점에서는
  detection과 full recovery 사이의 containment/response 품질이 별도 평가 대상이 된다.
- NIST SP 800-160 Vol. 2 Rev. 1은 cyber resiliency를 adverse condition, attack,
  compromise를 anticipate, withstand, recover, adapt하는 능력으로 본다. `withstand`와
  `recover`는 서로 다르므로, 완전 복구 전에도 견딘 정도를 점수화하는 것이 타당하다.

## 구현 위치

| 항목 | 위치 |
|---|---|
| contract 정의와 containment 계산 | `src/dah_flawless/blue/defense_effects.py` |
| scorer 연결 | `src/dah_flawless/scoring/scorer.py` |
| readiness gate 점수화 | `src/dah_flawless/environment/readiness.py` |
| summary 지표 | `src/dah_flawless/scoring/metrics.py` |
| frontend projection | `src/dah_flawless/reporting/frontend_log.py` |

## Contract 구조

각 contract는 특정 Red effect에 대해 Blue가 쓸 수 있는 방어 action과 target hint를
정의한다.

| effect | target domain | 대표 방어 |
|---|---|---|
| `EFFECT_TELEMETRY_TRUST_EROSION` | telemetry | `QUARANTINE_FIELD`, `FALLBACK_TO_TRUSTED_STATE`, `REQUEST_REVALIDATION` |
| `EFFECT_WRONG_TARGET_SELECTION` | mission | `QUARANTINE_FIELD`, `REQUEST_REVALIDATION` |
| `EFFECT_COMMAND_STALE_ACCEPTANCE` | command | `HOLD_COMMAND`, `REQUEST_REVALIDATION`, `QUARANTINE_FIELD` |
| `EFFECT_ACK_CAUSAL_CONFUSION` | command | `HOLD_COMMAND`, ACK quarantine, ACK revalidation |
| `EFFECT_CHANNEL_STATE_SUPPRESSION` | command/comms | `RESET_CHANNEL_TIMING`, `REQUEST_REVALIDATION`, `OBSERVE_DOMAIN` |

## Containment Score

`containment_score`는 0.0~1.0 값이다.

```text
containment_score =
  0.22 * detection_component
+ 0.30 * effect_reduction_ratio
+ 0.20 * action_coverage
+ 0.18 * operational_safety
+ 0.08 * recovery_component
+ 0.02 * low_cost_bonus
+ 0.38 * policy_containment_score
```

| 구성요소 | 의미 |
|---|---|
| `detection_component` | Blue가 target domain/effect를 탐지했는가 |
| `effect_reduction_ratio` | 방어 전후 공격 effect pressure가 얼마나 줄었는가 |
| `action_coverage` | contract에 맞는 방어 action을 썼는가 |
| `operational_safety` | availability/trust_budget을 얼마나 보존했는가 |
| `recovery_component` | 엄격한 full recovery까지 달성했는가 |
| `low_cost_bonus` | 낮은 비용으로 containment를 달성했는가 |

해석:

| 점수/상태 | 의미 |
|---|---|
| `RECOVERED` | 엄격한 `recovery_success`와 높은 containment를 동시에 달성 |
| `CONTAINED` | full recovery는 아니어도 contract 기준 containment 성공 |
| `PARTIAL_CONTAINMENT` | 일부 피해 억제는 했지만 성공 기준 미달 |
| `UNCONTAINED` | 탐지/방어/효과 감소가 부족 |

## Readiness Gate 변경

기존 readiness gate는 최근 round를 거의 boolean으로 보았다.

```text
Blue winner or recovery -> success
Red winner or goal success -> failure
```

이제는 `blue_defense_score`가 연속 점수를 계산한다.

- `BLUE`, `BLUE_RECOVERY`는 1.0
- `RED_BREACH`는 최대 0.16
- `RED_ATTRITION`은 containment가 높아도 최대 0.38
- `DRAW + detection + containment`는 부분 성공으로 인정
- `DRAW + no effect + availability preserved`는 안정적인 방어 샘플로 일부 인정

이렇게 하면 Blue가 탐지와 containment를 학습했는데도 완전 복구가 아니었다는 이유만으로
Red 업데이트가 무기한 막히는 현상을 줄일 수 있다. 동시에 RED_ATTRITION은 상한을 낮게
둬서 “가용성 붕괴를 방어 성공으로 착각”하지 않게 했다.

## Recovery 기준은 왜 유지했는가

`recovery_success` 자체는 계속 엄격하게 유지한다.

```text
recovery_success = observed가 scorer_truth/trusted anchor와 다시 일치함
```

이유:

- 완전 복구와 피해 억제를 섞으면 scorer 해석이 흐려진다.
- 보고서에서 `recovery_success`는 trusted restore를 달성한 강한 지표로 남겨야 한다.
- 대신 `containment_score`가 full recovery 전 단계의 의미 있는 방어를 설명한다.

즉 구조는 다음처럼 분리한다.

```text
detection_success: 알아차림
containment_score: 피해 억제/격리/보류/재검증 품질
recovery_success: trusted state로 완전 복원
availability: 방어 과정에서 임무 지속성을 얼마나 보존했는가
```

## 참고 자료

- NIST SP 800-184, *Guide for Cybersecurity Event Recovery*: https://csrc.nist.gov/pubs/sp/800/184/final
- NIST SP 800-61 Rev. 3, *Incident Response Recommendations and Considerations for Cybersecurity Risk Management*: https://csrc.nist.gov/pubs/sp/800/61/r3/final
- NIST SP 800-160 Vol. 2 Rev. 1, *Developing Cyber-Resilient Systems*: https://csrc.nist.gov/pubs/sp/800/160/v2/r1/final

## ZTA-Inspired Policy Containment

`policy_containment_score`는 `external_observe`에 대한 ZTA-inspired observe policy gate가 해당 domain을 `DOWNGRADE`, `REVALIDATE`, `QUARANTINE`, `DENY`로 낮췄을 때만 올라간다. 이는 탐지 성공이 아니라 authoritative use 제한으로 해석한다.

세부 기준 문서는 `docs/zta_observe_policy_gate.md`를 따른다.
