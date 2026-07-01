# Situation Tag Design

이 문서는 `blue_observed`에서 자동으로 추출할 situation tag를 정의한다. 태그는 Red 공격 선택 가중치와 Blue 불변식 탐지의 공통 입력으로 사용한다.

## 1. 태그 설계 원칙

```text
tag는 world를 보지 않고 observed만으로 계산한다.
tag는 공격명을 직접 말하지 않고, 관측된 이상 상태를 표현한다.
tag는 Red 공격 선택과 Blue 방어 판단에 모두 쓰인다.
```

## 2. Navigation / GNSS Tags

| 태그 | 조건 예시 | 의미 |
|---|---|---|
| `GNSS_PRIMARY` | GNSS fix가 정상이고 주항법으로 사용 중 | GNSS 의존도가 높은 상태 |
| `GNSS_DEGRADED` | `satellite_count < 5` 또는 `hdop > 5.0` | GNSS 품질 저하 |
| `GNSS_IMU_MISMATCH` | GNSS 위치와 IMU 추정 위치 차이가 임계값 초과 | 항법 교차검증 불일치 |
| `TIMESTAMP_SKEW` | 수신 timestamp가 로컬 시간 또는 이전 값과 불일치 | 시간 동기 이상 |

## 3. C2 / Telemetry Tags

| 태그 | 조건 예시 | 의미 |
|---|---|---|
| `C2_ENCRYPTED` | `comms.encrypted == true` | payload 직접 확인 제한 |
| `PAYLOAD_HIDDEN` | `payload_visible == false` | 내용 대신 메타데이터 기반 판단 필요 |
| `SIGNATURE_PRESENT` | `signature_present == true` | 메시지 서명 존재 |
| `AUTH_VALID` | `auth_valid == true` | 인증 통과 |
| `AUTH_INVALID` | `auth_valid == false` | 인증 실패 |
| `CHECKSUM_INVALID` | `checksum_valid == false` | 메시지 손상 또는 형식 불일치 |
| `SEQUENCE_REGRESSION` | 현재 `sequence_number`가 이전보다 작음 | replay 또는 순서 역행 의심 |
| `REPLAY_SUSPECTED` | sequence/timestamp가 과거 패턴과 일치 | 과거 메시지 재사용 의심 |

## 4. Network / Resource Tags

| 태그 | 조건 예시 | 의미 |
|---|---|---|
| `HIGH_LATENCY` | `latency_ms > 500` | 지연 증가 |
| `PACKET_LOSS_HIGH` | `packet_loss > 0.1` | 패킷 손실 증가 |
| `QUEUE_DEPTH_HIGH` | `message_queue_depth > 10` | 큐 적체 |
| `REQUEST_RATE_HIGH` | `request_rate`가 기준 초과 | 요청 폭주 또는 DoS 징후 |

## 5. Mission / Telemetry Consistency Tags

| 태그 | 조건 예시 | 의미 |
|---|---|---|
| `TELEMETRY_CONFLICT` | 배터리/모터/소모율이 물리적으로 맞지 않음 | 텔레메트리 정합성 위반 |
| `BATTERY_MOTOR_INCONSISTENT` | 배터리는 높고 모터는 OK인데 drain/fault 단서가 충돌 | FDI 의심 단서 |
| `MISSION_PRIORITY_CHANGED` | 우선순위가 단기간에 급변 | 임무 우선순위 오염 의심 |
| `CROSS_CHECK_UNAVAILABLE` | 교차검증 센서 또는 링크 사용 불가 | 탐지 신뢰도 저하 |

## 6. 예시 Tagger Rule

```python
def derive_tags(obs, history):
    tags = []

    if obs["navigation"]["satellite_count"] < 5 or obs["navigation"]["hdop"] > 5.0:
        tags.append("GNSS_DEGRADED")

    if obs["c2_message"]["sequence_number"] < history["last_sequence_number"]:
        tags.append("SEQUENCE_REGRESSION")
        tags.append("REPLAY_SUSPECTED")

    if obs["time"]["received_timestamp"] < history["last_received_timestamp"]:
        tags.append("TIMESTAMP_SKEW")

    if obs["comms"]["latency_ms"] > 500:
        tags.append("HIGH_LATENCY")

    if obs["comms"]["packet_loss"] > 0.1:
        tags.append("PACKET_LOSS_HIGH")

    if not obs["c2_message"]["auth_valid"]:
        tags.append("AUTH_INVALID")

    if obs["telemetry"]["battery_percent"] > 70 and obs["telemetry"]["battery_drain_rate"] > 0.8:
        tags.append("TELEMETRY_CONFLICT")

    return tags
```

## 7. 공격 선택과의 연결

| 공격 | 선호 태그 |
|---|---|
| `TELEMETRY_FDI` | `GNSS_PRIMARY`, `C2_ENCRYPTED`, `CROSS_CHECK_UNAVAILABLE` |
| `PRIORITY_POISONING` | `MISSION_PRIORITY_CHANGED`, `PAYLOAD_HIDDEN` |
| `TIME_DESYNC_REPLAY` | `HIGH_LATENCY`, `PACKET_LOSS_HIGH`, `C2_ENCRYPTED` |
| `AGENT_DOS` | `QUEUE_DEPTH_HIGH`, `REQUEST_RATE_HIGH` |

