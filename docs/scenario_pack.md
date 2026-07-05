# Scenario Pack

이 문서는 `src/dah_flawless/environment/state_factory.py`의 scenario pack을 설명한다.

시나리오는 실제 공격 절차가 아니라 Red/Blue 학습과 holdout 평가에 쓰는 안전한 초기 전장 조건이다. 각 시나리오는 scorer truth, Blue observe, mission budget, Blue capability, Blue policy state 중 일부를 조정한다.

| scenario | 목적 | 핵심 변화 |
|---|---|---|
| `clean_start` | 기준선 | healthy capability, availability 1.0 |
| `degraded_start` | 방어 복구 능력 약화 | 낮은 availability, degraded cross-check, degraded trusted restore, GNSS degraded |
| `satcom_delay` | 통신 지연/손실/ACK 타이밍 스트레스 | `world.link_profile`과 observe comms에 high latency, packet loss, jitter, queue depth, heartbeat gap |
| `gnss_degraded` | 항법 신뢰도 저하 | weak GNSS signal, low satellite count, high HDOP, degraded telemetry cross-check |
| `c2_metadata_noisy` | 암호화 채널의 metadata 기반 판단 스트레스 | invalid auth/checksum, high request rate, weak crypto metadata hint |
| `telemetry_conflict` | 물리적으로 수상한 telemetry 운영점 | high battery + high drain + OK motor 조합으로 consistency tag 유도 |
| `low_trust_start` | 과방어/가용성 압박 | 낮은 mission trust budget, 낮은 domain trust, degraded trusted restore |

`satcom_delay`는 단순히 `blue_observed.comms`만 바꾸지 않고 `state["world"]["link_profile"]`도 설정한다. simulator가 매 round 시작 때 comms 값을 `world.link_profile`에서 다시 채우기 때문이다.

Holdout 평가는 기본적으로 전체 `SCENARIOS` 목록을 사용한다. 따라서 학습 후 `--holdout-eval`을 켜면 clean/degraded뿐 아니라 통신, GNSS, C2 metadata, telemetry, low-trust 조건에서 frozen policy를 평가한다.
