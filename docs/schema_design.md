# World and Observed Schema Design

이 문서는 예선 MVP에서 사용할 `world`와 `blue_observed`의 JSON schema 초안이다. 공개 GNSS 규격, MAVLink 메시지 구조, 메시지 서명/인증 개념을 바탕으로 관측 가능한 값만 포함한다.

## 1. 설계 원칙

```text
world
= 실제 상태, scorer only

blue_observed
= Blue 관제 AI가 수신한 값
= 공격, 지연, replay, 센서 오류로 world와 달라질 수 있음

meta
= observed가 어떤 경로와 품질로 들어왔는지 판단하는 신뢰 단서
```

## 2. World Schema

```json
{
  "world": {
    "time": {
      "true_timestamp": 1710001200,
      "round": 3
    },
    "environment": {
      "weather": "CLEAR",
      "terrain": "LOW_MOUNTAIN",
      "rf_noise_level": 0.21,
      "gnss_interference": "NONE"
    },
    "uav": {
      "position": {
        "lat": 37.123,
        "lon": 127.456,
        "altitude_m": 180
      },
      "speed_mps": 42,
      "heading_deg": 91,
      "battery_percent": 20,
      "battery_drain_rate": 1.0,
      "motor_status": "FAULT",
      "imu_accel": {
        "x": 0.1,
        "y": 0.0,
        "z": 9.8
      }
    },
    "mission": {
      "current_area": "A",
      "area_priority": {
        "A": 0.9,
        "B": 0.4,
        "C": 0.2
      },
      "return_required": true
    },
    "command": {
      "expected_sequence_number": 1021,
      "last_valid_command": "RETURN_TO_BASE"
    }
  }
}
```

## 3. Blue Observed Schema

```json
{
  "blue_observed": {
    "time": {
      "received_timestamp": 1710000800,
      "local_clock_offset_ms": 430
    },
    "telemetry": {
      "battery_percent": 82,
      "battery_drain_rate": 1.0,
      "motor_status": "OK",
      "altitude_m": 180,
      "speed_mps": 42,
      "heading_deg": 91
    },
    "navigation": {
      "gnss_position": {
        "lat": 37.128,
        "lon": 127.460,
        "altitude_m": 181
      },
      "gnss_fix_quality": "DEGRADED",
      "satellite_count": 4,
      "hdop": 6.2,
      "cn0_avg": 22.5,
      "imu_position_estimate": {
        "lat": 37.123,
        "lon": 127.456
      }
    },
    "mission": {
      "area_priority": {
        "A": 0.2,
        "B": 0.4,
        "C": 0.95
      },
      "recommended_area": "C"
    },
    "c2_message": {
      "sequence_number": 1008,
      "command": "CONTINUE_MISSION",
      "sysid": 1,
      "compid": 1,
      "msgid": 76,
      "checksum_valid": true,
      "signature_present": true,
      "auth_valid": true
    },
    "comms": {
      "channel": "SATCOM",
      "encrypted": true,
      "payload_visible": false,
      "latency_ms": 850,
      "packet_loss": 0.12,
      "message_queue_depth": 12,
      "request_rate": 20
    }
  }
}
```

## 4. 필드별 출처 연결

각 필드의 타입, 단위, 범위, enum 값은 [field_formats.md](field_formats.md)를 기준으로 한다.

| 필드 그룹 | 대표 필드 | 근거 |
|---|---|---|
| GNSS/PNT | `gnss_position`, `satellite_count`, `hdop`, `cn0_avg`, `received_timestamp` | NAVCEN GPS Interface Specification |
| UAV telemetry | `battery_percent`, `motor_status`, `altitude_m`, `speed_mps` | MAVLink 메시지/텔레메트리 구조 |
| C2 message | `sequence_number`, `sysid`, `compid`, `msgid`, `checksum_valid` | MAVLink Packet Serialization |
| Signing/Auth | `signature_present`, `auth_valid`, `timestamp` | MAVLink Message Signing |
| Network meta | `latency_ms`, `packet_loss`, `message_queue_depth`, `request_rate` | 통신 관측 메타데이터 |
| Mission | `area_priority`, `recommended_area`, `return_required` | 프로젝트 공격 시나리오 |

## 5. MVP에서 반드시 필요한 필드

최소 구현은 아래 필드만 있어도 공격 3종을 증명할 수 있다.

```text
world.uav.battery_percent
world.uav.motor_status
world.mission.area_priority
world.command.expected_sequence_number
world.time.true_timestamp

blue_observed.telemetry.battery_percent
blue_observed.telemetry.motor_status
blue_observed.mission.area_priority
blue_observed.c2_message.sequence_number
blue_observed.time.received_timestamp
blue_observed.comms.latency_ms
blue_observed.c2_message.auth_valid
```
