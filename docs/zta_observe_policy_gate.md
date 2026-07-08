# ZTA-Inspired Observe Usage Policy Gate

## 적용 범위

본 MVP에서는 Red 변조 표면인 `external_observe`에 대해 ZTA-inspired policy gate를 우선 적용한다. `internal_observe`는 현재 Blue의 신뢰 기준점(trust anchor)으로 사용하며, 실제 UAV/UGV 운용 환경에서는 내부 센서, 비행제어장치, 통신 모듈 간 데이터 플로우에도 동일한 정책 판단 구조를 확장 적용할 수 있다.

이 모듈은 공격 탐지기가 아니다. Blue Threat Detection은 "공격/effect가 발생했는가"를 판단하고, Observe Policy Gate는 "이 외부 관측값을 임무 판단에 어느 권한 수준으로 사용할 수 있는가"를 판단한다. Scorer는 여전히 scorer truth 기준으로 결과를 평가한다.

## 근거

- NIST SP 800-207 Zero Trust Architecture는 고정 경계에 대한 암묵적 신뢰를 줄이고, 리소스 접근마다 동적 정책 판단을 수행하는 구조를 설명한다. 본 구현은 이를 관측값 사용 권한 판단으로 축소 적용한다.
- NIST SP 800-162 ABAC는 subject/object/action/environment 속성을 정책과 비교해 접근 결정을 내리는 모델이다. 본 구현은 `external_observe` domain, 요청 action, freshness, integrity/auth, 내부 기준점 일치도, 과거 패턴을 속성으로 사용한다.
- RAdAC 계열 접근은 상황 위험도와 임무 맥락을 반영해 접근 결정을 조절한다. 본 구현은 command 실행, 저전력/고장 상태 같은 mission criticality가 높을수록 필요한 보증수준을 올린다.

참조:
- NIST SP 800-207: https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf
- NIST SP 800-162: https://csrc.nist.gov/pubs/sp/800/162/upd2/final
- RAdAC/ZTN survey: https://arxiv.org/abs/1710.09696

## 알고리즘

각 external observe domain에 대해 다음 속성 점수를 0.0~1.0으로 계산한다.

| 속성 | 의미 |
| --- | --- |
| `provenance` | 외부 observe 출처와 식별 메타데이터 신뢰도 |
| `integrity_auth` | checksum, signature, auth, encryption 등 무결성/인증 힌트 |
| `freshness` | timestamp, sequence, latency, packet loss, heartbeat 기반 최신성 |
| `anchor_agreement` | `internal_observe` 기준점 또는 domain 내부 정합성과의 일치도 |
| `history_consistency` | 직전 history 대비 급격한 회귀/점프 여부 |
| `capability` | Blue의 cross-check/time validation/trusted restore 능력 |

가중합으로 `trust_score`를 만들고, domain/action별 `required_assurance`와 비교한다.

```text
trust_score = sum(attribute_score_i * weight_i)
margin = trust_score - required_assurance
```

결정 라벨과 사용 가중치는 다음과 같다.

| 결정 | use_weight | 의미 |
| --- | ---: | --- |
| `ALLOW` | 1.00 | 임무 판단에 authoritative하게 사용 |
| `ALLOW_WITH_MONITOR` | 0.80 | 사용하되 모니터링 유지 |
| `DOWNGRADE` | 0.45 | 임무 판단에는 참고값으로만 사용 |
| `REVALIDATE` | 0.25 | authoritative 사용 전 재검증 요구 |
| `QUARANTINE` | 0.05 | 탐지/분석에는 쓰되 임무 판단에서는 격리 |
| `DENY` | 0.00 | 실행/사용 차단. 현재 command 실행처럼 고위험 action에서만 제한적으로 사용 |

## 현재 코드 연결

- 구현: `src/dah_flawless/blue/observe_policy_gate.py`
- 단일 tick simulator: `src/dah_flawless/environment/simulator.py`
- 동적 round combat runner: `src/dah_flawless/environment/round_combat_runner.py`
- mission impact 반영: `src/dah_flawless/scoring/mission_impact.py`
- partial containment 반영: `src/dah_flawless/blue/defense_effects.py`
- frontend projection: `src/dah_flawless/reporting/frontend_log.py`

## 평가상 의미

`trust_score`는 공격 여부를 단독 판정하는 값이 아니라, 관측값을 임무 판단에 어느 수준으로 사용할지 결정하기 위한 보조 정책 점수다.

복구 해석은 세 단계로 분리한다.

| 상태 | 의미 |
| --- | --- |
| 완전 복구 | 오염된 값을 원래 정상값으로 restore |
| 부분 복구/containment | 값은 아직 완전히 복구하지 못했지만 `DOWNGRADE`, `REVALIDATE`, `QUARANTINE`으로 피해를 제한 |
| 미복구 | 오염된 값을 계속 authoritative하게 사용 |

따라서 ZTA-inspired gate는 `detection_success`를 직접 올리지 않고, `policy_containment`와 `mission_impact`에 별도 evidence로 반영된다.
