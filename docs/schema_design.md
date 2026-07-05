# Scorer Truth and Observed Schema Design

이 문서는 MVP runtime state의 JSON 구조를 설명한다. raw world의 원천 schema는 별도 문서인 [raw_world_schema.md](raw_world_schema.md)와 [../configs/raw_world_schema.yaml](../configs/raw_world_schema.yaml)을 기준으로 한다.

## 1. 설계 원칙

```text
raw_world
= 현실 원천 신호/환경/방출
= generator/extractor/adapter 입력

scorer_truth
= scorer/admin만 보는 채점 기준 상태
= 현재 코드에서는 호환성 때문에 state["world"]에 저장

blue_observed
= Blue AI가 받은 관측 입력
= Red mutation, 지연, replay, 센서 오류로 scorer_truth와 달라질 수 있음
```

## 2. Runtime State Top Level

```json
{
  "round": 1,
  "seed": 42,
  "scenario": "raw_world_start",
  "world": {},
  "blue_observed": {},
  "mission": {},
  "capabilities": {},
  "defense_runtime": {},
  "last_known_good": {}
}
```

주의: 위의 `world` 키는 historical compatibility key다. 문서와 보고서에서는 `scorer_truth(state["world"])`라고 부른다.

## 3. Scorer Truth Schema

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
      "motor_status": "FAULT"
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
    },
    "raw_world_hash": "optional_raw_world_sample_hash",
    "raw_world_feature_scores": {}
  }
}
```

## 4. Blue Observed Schema

Blue가 받는 observe는 이제 두 층으로 정의한다.

```text
blue_observed
  internal_observe  # 내부 센서/로컬 상태. Red가 직접 바꾸면 안 됨.
  external_observe  # 외부 신호/통신/원격 관측. Red mutation의 허용 표면.
  legacy flat view  # 현재 MVP 코드 호환용 telemetry/navigation/mission/c2_message/comms 키.
```

### 4.1 Canonical Observe Model

```json
{
  "blue_observed": {
    "observe_schema_version": "dah.observe.v0_2",
    "internal_observe": {
      "time": {
        "true_timestamp": 1710001200,
        "round": 3,
        "local_clock_offset_ms": 430
      },
      "telemetry": {
        "battery_percent": 20,
        "battery_drain_rate": 1.0,
        "motor_status": "FAULT"
      },
      "inertial_navigation": {
        "position_estimate": {
          "lat": 37.123,
          "lon": 127.456,
          "altitude_m": 180
        },
        "speed_mps": 42,
        "heading_deg": 91,
        "altitude_m": 180
      },
      "health": {
        "source": "internal_observe",
        "red_direct_mutation_allowed": false
      }
    },
    "external_observe": {
      "time": {},
      "telemetry": {},
      "navigation": {},
      "mission": {},
      "c2_message": {},
      "comms": {}
    },
    "observe_access": {
      "red_direct_mutation": {
        "internal_observe": false,
        "external_observe": true,
        "allowed_external_domains": ["time", "telemetry", "navigation", "mission", "c2_message", "comms"]
      },
      "blue_can_read": {
        "internal_observe": true,
        "external_observe": true
      }
    }
  }
}
```

### 4.2 Compatibility Flat View

현재 MVP 코드와 테스트는 아직 `blue_observed.telemetry`, `blue_observed.navigation` 같은 flat key를 읽는다. 이 flat key들은 canonical 구조에서 `external_observe`의 alias다. 새 설계와 보고서에서는 `external_observe.telemetry`가 Red mutation 대상이라고 설명하고, 기존 flat key는 구현 호환용 view라고 설명한다.

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
      "message_role": "COMMAND",
      "sequence_visible": true,
      "timestamp_visible": true,
      "metadata_plaintext": true,
      "checksum_valid": true,
      "signature_present": true,
      "auth_valid": true,
      "ack": {
        "visible": true,
        "sequence_number": 1008,
        "status": "ACCEPTED"
      }
    },
    "comms": {
      "channel": "SATCOM",
      "encrypted": true,
      "payload_visible": false,
      "latency_ms": 850,
      "packet_loss": 0.12,
      "message_queue_depth": 12,
      "packet_interval_ms": 1000,
      "ack_visible": true,
      "ack_delay_ms": 210,
      "anti_replay_window_s": 180
    }
  }
}
```

위 flat view 예시의 `battery_percent: 82`, `area_priority.C: 0.95` 같은 큰 변조값은 `loud_demo` profile 예시다. 기본 학습/보고서 실행 profile은 `aggressive`이며, 일반 실행에서는 더 작은 delta를 사용한다.

## 5. 공격 3종이 반드시 쓰는 필드

| 공격 | scorer_truth 기준 | observed 조작 대상 |
|---|---|---|
| `TELEMETRY_FDI` | `state["world"].uav.battery_percent`, `motor_status` | `blue_observed.telemetry.*` |
| `PRIORITY_POISONING` | `state["world"].mission.area_priority` | `blue_observed.mission.area_priority` |
| `TIME_DESYNC_REPLAY` | `state["world"].command.*`, `state["world"].time.true_timestamp` | `blue_observed.c2_message.*`, `blue_observed.time.received_timestamp` |

## 6. Raw World 시작 상태

raw world sample을 사용하면 아래 흐름으로 runtime state가 만들어진다.

```text
scripts/run_world_generator.py
-> src/dah_flawless/world/feature_extractor.py
-> src/dah_flawless/world/state_adapter.py
-> run_simulation(initial_state=...)
```

로그에는 `raw_world_source_hash`, `raw_world_feature_scores`, `truth_model`, `truth_storage_key`가 남는다.
