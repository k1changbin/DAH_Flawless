# Reference Sources for Preliminary Report

이 문서는 예선 보고서에서 world/observed/schema/tag 설계의 근거로 사용할 공개 자료를 정리한다. 목적은 실제 침투 방법을 학습하는 것이 아니라, 공개 표준과 보안 프레임워크를 바탕으로 관측 가능한 값과 탐지 태그를 정의하는 것이다.

## 1. GPS/GNSS 신호 근거

| 항목 | 내용 |
|---|---|
| 사이트 | NAVCEN, U.S. Coast Guard Navigation Center |
| 문서 | GPS Interface Specification IS-GPS-200N |
| 링크 | <https://www.navcen.uscg.gov/sites/default/files/pdf/gps/IS-GPS-200N.pdf> |
| 사용 목적 | GNSS 신호, 위치/시간, PNT, 위성 신호 구조의 공식 근거 |

보고서 활용:

- GNSS는 위치, 항법, 시각(Positioning, Navigation, Timing) 판단의 핵심 입력이다.
- GNSS 기반 관측값은 `position`, `timestamp`, `satellite_count`, `hdop`, `cn0_avg`, `fix_quality` 같은 observed 필드로 모델링할 수 있다.
- GNSS 품질 저하나 위치/시간 불일치는 `GNSS_DEGRADED`, `TIMESTAMP_SKEW`, `GNSS_IMU_MISMATCH` 태그로 연결한다.

## 2. UAV/GCS 텔레메트리 메시지 근거

| 항목 | 내용 |
|---|---|
| 사이트 | MAVLink 공식 문서 |
| 문서 | Packet Serialization |
| 링크 | <https://mavlink.io/en/guide/serialization.html> |
| 사용 목적 | UAV-GCS 메시지의 over-the-wire 구조, sequence, system id, component id, message id, payload, checksum 근거 |

보고서 활용:

- MAVLink는 군 전용 프로토콜은 아니지만, 공개적으로 설명 가능한 UAV/GCS 텔레메트리 예시로 적합하다.
- `seq`, `sysid`, `compid`, `msgid`, `payload`, `checksum` 구조를 참고해 `c2_message` schema를 정의한다.
- sequence 역행, packet loss, checksum 실패는 `SEQUENCE_REGRESSION`, `PACKET_LOSS_HIGH`, `CHECKSUM_INVALID` 태그로 연결한다.

## 3. 메시지 인증/Replay 판단 근거

| 항목 | 내용 |
|---|---|
| 사이트 | MAVLink 공식 문서 |
| 문서 | Message Signing |
| 링크 | <https://mavlink.io/en/guide/message_signing.html> |
| 사용 목적 | 메시지 서명, 인증 상태, timestamp 기반 replay 판단 근거 |

보고서 활용:

- 메시지 서명이 있으면 송신 출처 신뢰성을 검증할 수 있다.
- signed message의 `timestamp`는 replay 탐지 단서가 된다.
- `signature_present`, `auth_valid`, `timestamp`, `sequence_number`를 observed meta에 포함한다.
- 인증 실패나 시간 역행은 `AUTH_INVALID`, `TIMESTAMP_SKEW`, `REPLAY_SUSPECTED` 태그로 연결한다.

## 4. 위협모델링/위험평가 근거

| 항목 | 내용 |
|---|---|
| 사이트 | NIST CSRC |
| 문서 | SP 800-30 Rev. 1, Guide for Conducting Risk Assessments |
| 링크 | <https://csrc.nist.gov/pubs/sp/800/30/r1/final> |
| 사용 목적 | 위협원, 취약점, 영향도, 위험평가, 대응 전략의 근거 |

보고서 활용:

- 본 프로젝트는 실제 침투 실습이 아니라 제한 권한 공격자 모델을 둔 위험평가 기반 시뮬레이션이다.
- Red의 능력은 GCS/AI 장악이 아니라 observed 데이터 경로 일부 오염으로 제한한다.
- Blue는 observed 내부의 정합성, 인증 상태, 시간 순서, 임무 영향도를 평가해 최소 방어를 선택한다.

## 5. 공격/방어 태그 분류 근거

| 항목 | 내용 |
|---|---|
| 사이트 | MITRE ATT&CK for ICS |
| 링크 | <https://attack.mitre.org/matrices/ics/> |
| 사용 목적 | 공격 행위와 방어 태그를 표준화된 전술/기술 관점으로 분류 |

보고서 활용:

- `Wireless Compromise`, `Unauthorized Message`, `Manipulation of View`, `Loss of View`, `Loss of Availability` 같은 개념을 공격/피해 태그 설계에 참고한다.
- 실제 공격 도구나 exploit 절차를 재현하지 않고, 공격 효과와 관측 단서를 안전하게 분류한다.

## 6. 예선 보고서용 출처 전략

예선 보고서에서는 아래 조합을 기본 출처로 사용한다.

| 목적 | 추천 출처 |
|---|---|
| GNSS/world/observe 근거 | NAVCEN GPS Interface Specification |
| UAV 텔레메트리 구조 | MAVLink Packet Serialization |
| 서명, 인증, replay 근거 | MAVLink Message Signing |
| 위협모델/권한 범위 | NIST SP 800-30 |
| 공격 태그화 | MITRE ATT&CK for ICS |

비추천 자료:

- 실제 침투 튜토리얼
- exploit 실습 사이트
- 블로그 단독 인용
- 위키피디아 단독 인용
- 군 기밀 자료처럼 보이는 비공식 문서

