# World and Observed Model

이 문서는 프로젝트에서 사용하는 `world`, `observed`, `tag`의 의미를 정의한다. 핵심은 `world`는 실제 상태이고, `observed`는 각 주체가 받은 관측 결과라는 점이다.

## 1. 핵심 정의

```text
world
= 전장 공간에 실제로 존재하는 물리 상태, 외부 신호, 환경, 사건
= 누가 보든 현실 자체는 하나
= 하지만 모두가 반드시 동일하게 수신하거나 해석할 수 있는 것은 아님

observed
= 각 주체가 world를 자기 센서, 수신기, 필터, 계산기, AI 모델로 해석한 결과
= 노이즈, 지연, 암호화, spoofing, replay, 센서 고장, 공격자 조작에 의해 world와 달라질 수 있음
```

한 줄 요약:

```text
world는 실제로 일어난 것,
observed는 누군가가 그것을 보고 믿게 된 값.
```

## 2. World에 들어가는 것

`world`는 전장 네트워크로 직접 전달되는 메시지가 아니라, 시뮬레이션 내부의 실제 기준값이다.

| 예시 | 설명 |
|---|---|
| 실제 UAV 위치 | 실제 위도, 경도, 고도 |
| 실제 배터리 잔량 | 예: 20% |
| 실제 모터 상태 | 예: `FAULT` |
| 실제 GNSS 위성 신호 | 특정 시각에 방출된 외부 신호 |
| 실제 RF 방출 | 특정 주파수/시간에 발생한 전파 사건 |
| 실제 C2 송신 사건 | 적 또는 아군 UAV가 실제 송신한 burst |
| 실제 날씨/지형 | 기상, 산악, 건물, 전파 차폐 환경 |
| 실제 임무 우선순위 | 시뮬레이션 기준의 원래 임무 가치 |
| 실제 명령 순서 | 정상 sequence/timestamp의 기준 |

주의:

```text
world는 공통 현실이지만, 모두가 똑같이 볼 수 있는 값은 아니다.
거리, 지형, 안테나, 재밍, 암호화, 센서 품질에 따라 observed는 달라진다.
```

## 3. Observed에 들어가는 것

`observed`는 Blue 관제 AI 또는 Red 에이전트가 실제로 받은 값이다. 이 프로젝트에서는 공격 대상이 Blue의 입력이므로 구현에서는 `blue_observed`를 핵심으로 둔다.

| 예시 | 설명 |
|---|---|
| GNSS 위치 계산값 | 수신기가 GNSS 신호로 계산한 위치 |
| IMU 측정값 | 가속도, 자세, 속도 추정 |
| 카메라 인식 결과 | 표적/장애물/지형 인식 결과 |
| 배터리 보고값 | 센서 또는 텔레메트리가 보고한 배터리 |
| 모터 상태 보고값 | GCS가 수신한 모터 상태 |
| C2 파싱 결과 | command, sequence, timestamp |
| 통신 메타데이터 | latency, packet loss, queue depth |
| 인증/무결성 상태 | signature, checksum, auth result |

예시:

```text
world.battery_percent = 20
blue_observed.telemetry.battery_percent = 82
```

이 경우 실제 배터리는 20%이지만, Blue 관제 AI는 82%라고 믿는다.

## 4. Red/Blue/Scorer 접근 권한

| 주체 | 볼 수 있는 값 | 보면 안 되는 값 |
|---|---|---|
| Red Agent | `red_observed`, 일부 공격 성공/실패 피드백 | `world`, Blue 내부 로직 |
| Blue Agent | `blue_observed`, 통신/센서 meta | `world`, Red 내부 상태 |
| Scorer | `world`, `blue_observed`, attack/detection 결과 | 없음 |
| Environment | `world`, observed 생성/변형 로직 | 없음 |

설계 원칙:

```text
Red도 Blue도 world를 직접 보지 않는다.
world는 environment와 scorer에만 남는다.
Blue는 world를 제거한 redacted state만 본다.
```

## 5. 보고서용 설명 문장

```text
본 시스템에서 world는 전장 네트워크로 직접 전달되는 값이 아니라 시뮬레이션 내부의 실제 상태다. 반면 observed는 GNSS, C2 텔레메트리, 센서, 통신 메타데이터를 통해 관제 AI가 수신한 값이며 공격자에 의해 오염될 수 있다. Blue는 world를 직접 보지 않고 observed 내부의 물리 정합성, 시간 순서, 인증 상태, 임무 우선순위 변화만으로 이상을 탐지한다.
```

