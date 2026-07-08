# Blue Availability Episode Budget Model

이 문서는 Blue의 `mission.availability`와 `mission.trust_budget`을 어떻게
해석하고, 왜 라운드 사이에 누적 회복을 하지 않는지 설명한다.

## 1. 현재 기준

`mission.availability`는 UAV 배터리 자체가 아니라 Blue가 임무를 계속 수행할 수
있는 추상 예산이다. 격리, 명령 보류, 재검증, fallback, 채널 재설정 같은 방어
행동은 이 예산을 깎는다.

현재 모델의 핵심 규칙은 다음과 같다.

```text
라운드 시작:
  availability = scenario episode initial availability
  trust_budget = scenario episode initial trust_budget

라운드 내부 combat step:
  방어 action cost만큼 availability/trust_budget 감소
  Red/Blue는 이 한 episode 안에서만 attrition combat 수행

라운드 종료:
  score와 feedback은 남기지만 availability/trust_budget 손상은 다음 라운드로 이월하지 않음
```

즉, availability 전투는 한 round-level combat episode 내부에서만 수행된다.
라운드 사이에 Blue가 서서히 회복하는 모델은 사용하지 않는다.

## 2. 왜 리셋하는가

이 프로젝트의 목적은 장기 운용 피로도 모델이 아니라 Red/Blue 공격·방어 판단
구조를 비교하는 것이다. availability가 라운드 사이에 누적되면 다음 문제가 생긴다.

- 이전 라운드 방어 비용 때문에 다음 라운드가 이미 낮은 availability에서 시작한다.
- `RED_ATTRITION`이 현재 공격의 효과인지, 과거 누적 피로 때문인지 흐려진다.
- readiness gate와 Blue feedback learner가 현재 episode 방어 성능을 과소평가한다.
- 100라운드 이상 학습에서 availability floor가 자주 0에 붙어 학습 신호가 둔해진다.

따라서 현재 구조에서는 라운드 시작마다 시나리오 초기 예산으로 리셋한다. 예를 들어
`clean_start`는 1.0/1.0, `degraded_start`는 0.55/0.72,
`low_trust_start`는 0.70/0.58에서 매 라운드를 시작한다.

## 3. 코드 위치

| 목적 | 위치 |
|---|---|
| 시나리오 초기 예산 저장 | `state_factory.py`의 `episode_initial_budget` |
| 라운드 시작 예산 리셋 | `environment/simulator.py::_reset_round_operational_budget` |
| 동적 combat runner 연결 | `environment/round_combat_runner.py` |
| summary 집계 | `scoring/metrics.py`의 `episode_budget_reset_count` |

로그 호환성을 위해 기존 `availability_recovery` 필드를 계속 사용하지만, 알고리즘은
`round_episode_budget_reset_v1`로 기록한다. 이 값은 회복량이 아니라 round episode
초기화 기록이다.

```json
{
  "algorithm": "round_episode_budget_reset_v1",
  "scope": "round_episode",
  "availability_after": 1.0,
  "trust_after": 1.0,
  "availability_recovery_applied": 0.0,
  "trust_recovery_applied": 0.0
}
```

`availability_recovery_applied`와 `trust_recovery_applied`는 0.0으로 둔다. summary의
`total_availability_recovery`도 0.0이어야 한다.

## 4. Scoring 해석

`RED_ATTRITION`은 이제 "이번 episode 안에서 Blue 방어 비용이 Red 공격 비용보다
크고, 그 결과 availability floor를 깎았다"는 뜻이다. 이전 라운드에서 이미 낮아진
availability 때문에 Red가 이기는 경우는 줄어든다.

따라서 1000라운드 학습 결과를 볼 때는 다음 값을 함께 본다.

- `episode_budget_reset_count`: 각 라운드가 독립 episode 예산으로 시작했는가
- `min_availability`: 어떤 episode 안에서 얼마나 심하게 바닥났는가
- `avg_attrition_defense_to_attack_ratio`: Blue 방어 비용이 Red 비용보다 컸는가
- `avg_containment_score`: 비용을 쓰고도 실제 effect를 줄였는가

## 5. 보고서용 문장

```text
본 모델에서 Blue availability는 장기 체력이 아니라 단일 round-level combat episode
내 임무 지속성 예산이다. 각 라운드는 시나리오가 정의한 초기 availability/trust_budget에서
시작하며, 방어 행동으로 인한 가용성 손실은 해당 episode 안에서만 scoring된다.
따라서 RED_ATTRITION은 과거 라운드의 누적 피로가 아니라 현재 episode에서 Red가
Blue의 방어 비용을 유도해 임무 지속성을 떨어뜨린 경우로 해석한다.
```

## 6. 참고 자료

- NIST SP 800-160 Vol. 2 Rev. 1, *Developing Cyber-Resilient Systems*:
  https://csrc.nist.gov/pubs/sp/800/160/v2/r1/final
- NIST SP 800-61 Rev. 3, *Incident Response Recommendations and Considerations*:
  https://csrc.nist.gov/pubs/sp/800/61/r3/final
- MITRE ATT&CK, Impact tactic TA0040:
  https://attack.mitre.org/tactics/TA0040/
