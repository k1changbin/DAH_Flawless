# DAH 2026 AI Agent Battle 통합 플래닝

> 목적: `docs` 폴더에 흩어진 대회 분석, 팀 리서치, 공격/방어 시나리오, 구현 설계, 현실성 검토를 하나의 실행용 플래닝 문서로 통합한다.
>
> 통합 출처:
> - `docs/DAH2026_PLAN.md`
> - `docs/team_research_digest.md`
> - `docs/codex_planning_review.md`
> - `docs/chatgpt_DAH2026_AI_Agent_Battle_정리.md`

기준일: 2026-06-27  
목표: 예선 보고서와 부가자료 ZIP에 넣을 수 있는 자체 시뮬레이터 기반 Red/Blue AI Agent 공방 MVP 완성

---

## 1. 한눈 요약

- 예선은 온라인 보고서 심사이며, 핵심 제출물은 보고서 PDF와 소스코드/실행매뉴얼 ZIP이다.
- 본선 환경은 아직 미공개이므로, 예선에서는 자체 시뮬레이터 + 추상화된 환경 인터페이스로 구현한다.
- 프로젝트 핵심은 Red Agent가 무인 정찰체계 관제 AI의 판단 입력을 오염시키고, Blue Team Multi-Agent System이 이를 탐지, 격리, 복구, 보고하는 자율 공방 시뮬레이션이다.
- 차별점은 “상황 인지형 Red Agent”다. Red는 무작위 공격이 아니라 `situation_tags`를 읽고 현재 상황에서 가장 효과적인 공격 표면을 선택한다.
- 공격 목표는 두 축이다.
  - 오판 유도: 데이터 무결성, 인증, 시간 순서, 모델/정책 신뢰도 오염
  - 판단/자원 포화: Blue Agent 큐, 추론, 방어 처리 슬롯, 가용성 압박
- 방어는 즉시 무한 적용되지 않는다. 각 방어 action은 처리 시간, 자원 비용, 우선순위를 가지며 제한된 슬롯에서 큐 기반으로 처리된다.
- MVP는 Python CLI 기반 N라운드 공방, JSONL 라운드 로그, 요약 점수판, Streamlit 대시보드까지를 목표로 한다.

---

## 2. 대회/제출 전략

### 2.1 예선 제출물

1. 예선 보고서 PDF
   - 파일명: `DAH2026_예선보고서_[팀명].pdf`
   - 본문 25~40p 권장
   - 필수 목차 순서 준수
2. 부가자료 ZIP
   - 파일명: `DAH2026_소스코드_[팀명].zip`
   - 소스코드, 실행 매뉴얼, README, Dockerfile 또는 requirements 포함
   - 외부 클라우드 링크로 제출

### 2.2 보고서 8항목

1. 표지
2. 목차
3. 팀 구성 및 역할 분배·전문성
4. 방산 분야 공격 시나리오 설계
5. 공격 시나리오 대응 방어 아키텍처 수립
6. AI 에이전트 설계 및 구현
7. 결론 및 향후 계획
8. 참고문헌

### 2.3 평가 배점 대응

| 평가 항목 | 배점 | 대응 전략 |
|---|---:|---|
| 공격 시나리오 설계 | 30 | Red Agent가 실제로 생성한 조작 데이터와 공격 로그 제시 |
| 방어 전략 수립 | 25 | Blue Agent의 탐지·격리·복구 로그와 정책 테이블 제시 |
| AI 에이전트 아키텍처 | 25 | Red/Blue/Orchestrator 구조, 라운드 루프, 로그, 대시보드 제시 |
| 팀 역량 | 10 | 역할 분배를 코드 모듈 소유권과 연결 |
| 문서 완성도 | 10 | 표/그림/코드 출처, 한계, 재현 방법 명확화 |

전략적 결론: 코드 자체가 직접 점수를 받는 항목은 ③이지만, 돌아가는 MVP와 로그는 ①·②의 기술적 완성도와 실현 가능성 근거가 된다. 따라서 “보고서만 그럴듯한 기획”보다 “실행 가능한 시뮬레이터 + 라운드 로그 + 점수판”이 중요하다.

---

## 3. 핵심 시나리오 정의

### 3.1 프로젝트 한 문장

Red Team Agent가 무인 정찰체계 관제 AI의 임무 우선순위, 텔레메트리, 시간값, 노드 신원, 무결성 정보를 오염시키고, Blue Team Multi-Agent System이 이를 탐지·격리·복구·보고하는 자율 공방 시뮬레이션.

### 3.2 방어 범위

이 프로젝트는 실제 RF, GNSS, C2 프로토콜을 직접 공격하지 않는다. 대신 본선 인터페이스가 공개되지 않은 예선 단계에 맞춰, 방산 시스템에서 AI가 판단에 사용하는 추상 데이터 계층을 공격 대상으로 둔다.

방어 범위:

- 데이터/행위 무결성 검증
- 명령 순서와 시간값 검증
- 텔레메트리 물리 정합성 검증
- 아군 노드 신원 검증
- 모델/정책/임무파일 버전 검증
- Agent DoS와 방어 처리 과부하 완화

범위 밖:

- 실제 암호 키 탈취 이후의 암호학적 방어
- 실제 RF 재밍 구현
- 실제 UAV 비행제어기 펌웨어 공격
- 본선 클라우드 전용 인터페이스 최적화

---

## 4. 시스템 아키텍처

### 4.1 구성요소

```text
+------------------------------+
| Orchestrator / Simulator     |
| - round loop                 |
| - state transition           |
| - defense task queue         |
| - logging/scoring            |
+---------------+--------------+
                |
     +----------+----------+
     |                     |
+----v-----+         +-----v------------------+
| Red Agent|         | Blue Team Agents       |
|          |         | - Threat Detection     |
| 상황 인지 |         | - Mission Monitor       |
| 공격 선택 |         | - Defense Planner       |
| 데이터 변조|        | - Incident Reporter     |
+----------+         +------------------------+
```

### 4.2 기본 파일 구조

```text
DAH/
├─ README.md
├─ requirements.txt
├─ Dockerfile
├─ src/
│  ├─ main.py
│  ├─ config.py
│  ├─ schemas.py
│  ├─ environment/
│  │  ├─ base.py
│  │  └─ simulator.py
│  ├─ agents/
│  │  ├─ red_agent.py
│  │  ├─ threat_detection_agent.py
│  │  ├─ mission_monitor_agent.py
│  │  ├─ defense_planner_agent.py
│  │  └─ incident_report_agent.py
│  ├─ attacks/
│  │  ├─ telemetry_fdi.py
│  │  ├─ priority_poisoning.py
│  │  ├─ time_desync_replay.py
│  │  ├─ fake_ally_sybil.py
│  │  ├─ integrity_tamper.py
│  │  └─ agent_dos.py
│  ├─ defenses/
│  │  ├─ policy_table.py
│  │  └─ defense_runtime.py
│  ├─ scoring/
│  │  └─ scorer.py
│  └─ dashboard.py
├─ data/
│  ├─ initial_state.json
│  └─ scenarios/
├─ logs/
│  ├─ round_logs.jsonl
│  └─ summary.json
├─ tests/
└─ docs/
```

---

## 5. 핵심 메커니즘

### 5.1 라운드 루프

```python
state = load_initial_state("data/initial_state.json")

for rnd in range(1, N_ROUNDS + 1):
    attack = red_agent.choose_attack(state)
    state = env.apply_attack(state, attack)

    threat = threat_detection_agent.analyze(state)
    mission = mission_monitor_agent.analyze(state)
    defense = defense_planner_agent.plan(threat, mission)

    state = env.enqueue_defense_tasks(state, defense)
    state = env.advance_defense_tasks(state)

    report = incident_report_agent.write(threat, mission, defense)
    score = scorer.update(attack, threat, defense, state)
    save_round_log(rnd, attack, threat, mission, defense, report, score)
```

### 5.2 방어 처리 레이턴시와 큐

Blue의 방어 조치는 즉시 적용되지 않는다. 각 defense action은 다음 속성을 가진 작업으로 큐에 들어간다.

- `priority`: 긴급도
- `duration_ticks`: 적용까지 걸리는 시간
- `resource_cost`: CPU/GPU/분석 큐/가용성 비용
- `status`: `pending`, `active`, `completed`, `failed`, `interrupted`

동시에 처리 가능한 방어 수는 `active_defense_slots`로 제한한다. 예를 들어 슬롯이 2개인데 방어 action이 5개 발생하면 2개는 active, 3개는 pending queue에 남는다.

Red가 방어 처리 중 새 공격을 수행하면 결과는 다음 중 하나다.

- 기존 active defense가 같은 공격면을 보호 중이면 피해가 일부 완화된다.
- 큐에 여유가 있으면 새 방어 task로 등록된다.
- 큐가 포화되면 `detection_latency_ticks`, `defense_latency_ticks`, `defense_queue_depth`가 증가한다.
- 안전 위험이 높으면 낮은 위험 방어를 중단하고 긴급 방어로 선점한다.

기본 우선순위:

```text
safety_risk > mission_impact > confidence > availability_cost
```

### 5.3 상태 스키마 핵심

```json
{
  "round": 0,
  "mission_phase": "RECON_APPROACH",
  "situation_tags": ["RECON_APPROACH", "GNSS_PRIMARY"],
  "world": {
    "battery_percent": 35,
    "position": [120.5, 301.2],
    "motor": "FAULT"
  },
  "observed": {
    "battery_percent": 35,
    "position": [120.5, 301.2],
    "motor": "OK",
    "telemetry_timestamp": "00:01:20"
  },
  "comms": {
    "packet_loss": 0.02,
    "latency_ms": 80,
    "message_queue_depth": 12,
    "request_rate": 20
  },
  "command": {
    "signature_valid": true,
    "sequence_number": 1021,
    "approval_status": "approved"
  },
  "integrity": {
    "model_hash": "ok",
    "mission_file_hash": "ok",
    "firmware_hash": "ok",
    "log_hash_chain_valid": true
  },
  "swarm": {
    "swarm_node_count": 5,
    "leader_id": "UAV-02",
    "join_request_rate": 0,
    "node_trust": {}
  },
  "resource": {
    "cpu_usage": 0.30,
    "gpu_usage": 0.25,
    "battery_drain_rate": 1.0
  },
  "defense_runtime": {
    "active_defense_slots": 2,
    "defense_queue_depth": 0,
    "active_defenses": [],
    "completed_defenses": [],
    "detection_latency_ticks": 0,
    "defense_latency_ticks": 0,
    "availability_cost": 0.0
  },
  "logs": []
}
```

### 5.4 에이전트 I/O 계약

- Red → `{round, attack_type, mutated_state, injected_logs[]}`
- Threat → `{threat_detected, threats:[{type,severity,evidence,confidence}]}`
- Mission → `{mission_status, risks:[{risk,detail,mission_impact,safety_risk}]}`
- Defense → `{defense_actions:[{action,reason,recovery,priority,duration_ticks,resource_cost,status}]}`
- Report → 관제자용 텍스트와 근거 링크

---

## 6. Red Agent 설계

### 6.1 상황 인지형 공격 선택

Red Agent는 현재 상태를 보고 상황 태그를 만든 뒤, 공격 표면을 선택한다.

```python
tags = situation_tagger(state)
surface = select_attack_surface(tags)
attack = attack_catalog[surface].craft(state)
```

예시:

| 상황 태그 | Red Agent 선택 경향 |
|---|---|
| `GNSS_PRIMARY` | telemetry FDI, navigation spoofing |
| `C2_DEGRADED` | time desync, replay |
| `RESOURCE_PRESSURE` | Agent DoS, staggered pressure |
| `SWARM_CONSENSUS` | fake ally, Sybil |
| `MISSION_REPLAN_PENDING` | priority poisoning |

### 6.2 MVP 공격 6종

| 코드 | 조작 필드 | 성공 조건 | 방어 포인트 |
|---|---|---|---|
| `PRIORITY_POISONING` | `ai`, priority/threshold | Blue가 잘못된 표적 우선순위 채택 | 점수 급변, 근거 부재 탐지 |
| `TELEMETRY_FDI` | `world`와 `observed` 괴리, battery/motor | 지휘소가 실제와 다른 상태 신뢰 | 물리 정합성 교차검증 |
| `TIME_DESYNC_REPLAY` | `sequence_number`, `telemetry_timestamp` | 과거 명령/상태가 최신처럼 처리 | 시퀀스/단계 일관성 검증 |
| `FAKE_ALLY_SYBIL` | `swarm_node_count`, certificate/trust | 미인증 노드 보고를 합의에 반영 | 등록/인증/이력 대조 |
| `INTEGRITY_TAMPER` | `*_hash=mismatch`, `approval=missing` | 변조 임무/모델을 정상 수행 | 해시/승인/버전 검증 |
| `AGENT_DOS` | `message_queue_depth`, `request_rate`, `cpu_usage` | Blue 탐지 큐 포화/지연 | 레이트리밋, 저위험 이벤트 병합 |

### 6.3 확장 후보

| 코드 | 설명 | 우선순위 |
|---|---|---|
| `STAGGERED_DEFENSE_PRESSURE` | 공격을 시간차로 반복해 Blue 방어 상태가 꺼지지 않게 만들고 방어 유지 비용/탐지 지연 누적 | 높음 |
| `DEFENSE_SELF_DESTRUCT` | 가짜 이상 신호로 자동귀환/격리/임무중단 남발 유도 | 높음 |
| `EVASION_BELOW_THRESHOLD` | 임계값 이하로 공격 강도를 조절해 정상 판정 받으며 지속 피해 | 중간 |
| `STEGO_PROMPT_INJECTION` | 이미지/메타데이터/로그에 숨겨진 지시문을 넣어 LLM 보고/탐지 교란 | 여유 시 |
| 복구지점 오염 | 마지막 정상 복구 지점 자체를 오염 | 여유 시 |
| 정상패턴 세탁 | 점진적으로 정상 분포를 오염 | 여유 시 |

### 6.4 시간차 공격과 방어 과부하

`STAGGERED_DEFENSE_PRESSURE`는 `AGENT_DOS`와 연결되는 확장 공격이다. 공격을 한 번에 몰아넣지 않고 짧은 간격으로 나누면 Blue의 방어 상태가 계속 유지된다.

측정 지표:

- `availability_cost`
- `message_queue_depth`
- `detection_latency_ticks`
- `defense_latency_ticks`
- `defense_queue_depth`

밸런스 장치:

- 연속 방어 성공 후 안정화 시간 부여
- 저위험 이벤트 병합
- 레이트리밋
- 재검증 우선순위
- 긴급 방어 선점 처리

---

## 7. Blue Team 방어 설계

### 7.1 Blue Agent 구성

| Agent | 역할 |
|---|---|
| Threat Detection Agent | 조작된 데이터와 이상 신호 탐지 |
| Mission Monitor Agent | 임무 영향도, 안전 위험, 가용성 손실 평가 |
| Defense Planner Agent | 방어 action 선택, 큐 등록, 우선순위 결정 |
| Incident Report Agent | 관제자용 설명 보고서 생성 |

### 7.2 방어 정책 매핑

| 공격 | 탐지 | 차단/격리 | 복구 |
|---|---|---|---|
| `PRIORITY_POISONING` | 점수 급변 + 근거 부재 | 해당 업데이트 격리 | 원 임무목표 유지 |
| `TELEMETRY_FDI` | 배터리/비행시간/모터 상태 물리 정합성 검증 | 신뢰도 낮음 태깅 | 백업 링크 상태 채택 |
| `TIME_DESYNC_REPLAY` | 시퀀스/단계/타임스탬프 일관성 검증 | 미검증 명령 보류 | 마지막 정상 명령 유지 |
| `FAKE_ALLY_SYBIL` | 등록/인증/이력 대조 | 미인증 노드 격리 | 관제 승인 전 협업망 제외 |
| `INTEGRITY_TAMPER` | 해시/승인/버전 정합성 검증 | 변조 파일·모델 격리 | 마지막 정상 버전 복구 |
| `AGENT_DOS` | 발생률/중복/큐길이 분석 | 저위험 통합·레이트리밋 | 위협탐지 큐 우선 보호 |

### 7.3 공통 방어 원칙

- 전체 정지보다 격리 우선
- 데이터 값뿐 아니라 출처와 신뢰도 추적
- 복구 지점 자체를 재검증
- 경보 피로 방지를 위해 반복 경고를 묶어서 판단
- Agent 의견 충돌 시 최소 방어 디폴트 수행
- mission continuity와 security를 함께 고려

### 7.4 최소 방어 원칙

Defense Planner는 다음 기준으로 방어 강도를 조절한다.

- `confidence`: 공격이라고 판단하는 확신도
- `mission_impact`: 임무 영향도
- `reversibility`: 되돌릴 수 있는 조치인지
- `safety_risk`: 안전 위험도
- `availability_cost`: 방어 조치로 인한 가용성 손실

| 조건 | 조치 |
|---|---|
| 낮은 confidence | monitor, request validation |
| 중간 confidence | suspicious field quarantine |
| 높은 confidence | command hold, trusted rollback |
| critical risk | safe mode |

### 7.5 ACID식 트랜잭션 무결성 프레임

Blue Team의 방어 설계는 금융결제·주문 처리 시스템의 트랜잭션 무결성 보장 원칙에서 착안한다. ACID를 그대로 구현한다는 뜻이 아니라, 방산 AI가 판단에 사용하는 명령·텔레메트리·임무파일·노드 신원 정보를 하나의 상태 전이로 보고, 제약조건을 깨는 전이를 공격 또는 이상 상태로 탐지한다는 의미다.

| ACID 개념 | 보안/방어 적용 |
|---|---|
| Atomicity | 명령 실행, 방어 action, 복구 action은 부분 적용되면 안 된다. 중간 검증 실패 시 보류하거나 rollback한다. |
| Consistency | 입력값, 센서융합 결과, 명령 순서, 해시/승인 상태가 사전에 정의한 제약조건을 만족해야 한다. |
| Isolation | 동시에 들어오는 공격, 방어 task, 센서 업데이트가 서로의 판단 상태를 오염시키지 않도록 큐와 우선순위로 격리한다. |
| Durability | 탐지, 방어, 복구, 보고 판단은 로그로 남겨 장애 후에도 감사와 재현이 가능해야 한다. |

보안 프레임워크와의 대응:

| 보안 프레임워크 | ACID식 해석 |
|---|---|
| 입력 검증 | Consistency |
| 센서융합 이상탐지 | Consistency + Isolation |
| 명령 일관성 검증 | Atomicity + Consistency |
| 자동 복구 | Durability + Rollback |

이 관점에서 공격자는 정상 트랜잭션 중간에 끼어들어 상태 전이를 오염시키려는 존재다. Blue는 입력 검증으로 잘못된 명령을 차단하고, 센서 검증으로 현재 상태를 재확인하며, 명령 검증으로 트랜잭션 무결성을 보장하고, 실패 시 마지막 정상 상태로 rollback한다.


### 7.6 금융권 고신뢰 시스템 접근법 후보

아래 항목들은 당장 모두 구현한다는 뜻이 아니라, 금융결제·주문·트랜잭션 시스템에서 쓰이는 고신뢰 설계 사고방식을 방산 AI 방어 아키텍처에 비유적으로 차용할 수 있는 후보들이다. MVP에서는 ACID식 상태 검증, 교차 대사, 감사 로그 정도를 우선 반영하고, 나머지는 보고서의 설계 원칙 또는 향후 확장으로 둔다.

| 금융권 접근법 | 방산 AI 방어 적용 아이디어 | 구현 우선순위 |
|---|---|---|
| Maker-Checker / 4-Eyes Principle | 중요 명령은 생성 주체와 승인 주체를 분리 검증한다. `command_source`, `source_role`, `approval_status`, `signature_valid`가 맞지 않으면 보류한다. | P2/P3 |
| Transaction / Risk Limit | 라운드별 명령 변경 횟수, 노드 가입 요청 수, 재계획 횟수, 요청률에 한도를 둔다. 한도 초과 시 추가 검증 또는 레이트리밋을 적용한다. | P2 |
| Fraud Detection / 이상거래탐지 | 형식상 정상인 명령도 평소 패턴, 임무 단계, 물리 상태와 맞지 않으면 의심한다. 정상처럼 보이는 값이 지나치게 완벽한 경우도 조작 가능성으로 본다. | P1/P2 |
| Reconciliation / 대사 검증 | `world`와 `observed`, 텔레메트리와 명령 로그, 센서 간 상태를 서로 맞춰본다. 불일치가 크면 신뢰도를 낮춘다. | P1 |
| Immutable Audit Log / 감사 로그 | 공격, 탐지, 방어, 복구, 보고 판단을 JSONL로 남기고 `log_hash_chain_valid` 같은 필드로 변조 가능성을 추적한다. | P1/P2 |
| Idempotency / 중복 처리 방지 | 같은 `command_id`, `sequence_number`, 방어 action이 반복 들어와도 한 번만 처리하거나 병합한다. Replay와 Agent DoS 완화에 사용한다. | P2 |
| Circuit Breaker | 특정 링크, 노드, 데이터 소스에서 오류율이나 요청률이 급증하면 전체 정지가 아니라 해당 경로만 임시 격리한다. | P2/P3 |

현재 구현 불확실성: 위 원칙을 전부 에이전트 코드에 넣으면 범위가 커진다. 따라서 1차 구현은 `Reconciliation`, `Fraud Detection`, `Immutable Audit Log`처럼 로그와 규칙 기반으로 바로 보이는 항목부터 적용하고, `Maker-Checker`, `Circuit Breaker`는 방어 정책 테이블과 보고서 설명으로 먼저 둔다.

---

## 8. 로그, 점수판, 대시보드

### 8.1 점수 지표

- `attack_success`
- `detection_success`
- `detection_latency_ticks`
- `defense_latency_ticks`
- `defense_queue_depth`
- `active_defense_slots`
- `mission_degradation`
- `recovery_success`
- `false_positive`
- `availability_cost`

### 8.2 라운드 로그 스키마

```json
{
  "round": 1,
  "timestamp": "2026-07-01T12:00:00",
  "situation_tags": ["RECON_APPROACH", "GNSS_PRIMARY"],
  "attack": {
    "type": "TELEMETRY_FDI",
    "target_fields": ["battery_percent", "motor"],
    "success": true,
    "reason": "Blue agent trusted manipulated telemetry before cross-check."
  },
  "blue": {
    "threat_detected": true,
    "confidence": 0.86,
    "evidence": [
      "battery drain rate inconsistent with reported battery",
      "motor status conflicts with vibration signal"
    ],
    "defense_action": "QUARANTINE_FIELD",
    "recovery_action": "FALLBACK_TO_TRUSTED_STATE",
    "defense_runtime": {
      "active_defense_slots": 2,
      "defense_queue_depth": 1,
      "active_defenses": [
        {
          "action": "QUARANTINE_FIELD",
          "status": "active",
          "remaining_ticks": 1,
          "priority": "high"
        }
      ],
      "pending_defenses": [
        {
          "action": "REQUEST_REVALIDATION",
          "status": "pending",
          "duration_ticks": 2,
          "priority": "medium"
        }
      ]
    }
  },
  "scores": {
    "data_trust_score": 0.42,
    "mission_risk": 0.68,
    "attack_confidence": 0.86,
    "detection_latency_ticks": 1,
    "defense_latency_ticks": 2,
    "defense_queue_depth": 1,
    "availability_cost": 0.15,
    "recovery_score": 0.74
  },
  "winner": "BLUE"
}
```

### 8.3 Streamlit 대시보드

대시보드는 선택이 아니라 예선 설득력 향상을 위한 권장 요소다.

권장 화면:

- 현재 라운드 요약
- Red 공격 타임라인
- World vs Observed 비교표
- Blue 탐지 근거
- Defense task queue 상태
- 점수판과 누적 그래프
- Incident Report 텍스트

실행 방식:

```bash
python -m src.main --rounds 10 --scenario default
streamlit run src/dashboard.py
```

---

## 9. LLM 사용 전략

기본 실행 경로는 룰베이스로 둔다. 이유는 Docker 재현성, API 키 의존성 제거, 심사 환경 안정성 때문이다.

LLM은 선택 모듈로 둔다.

우선순위:

1. Incident Report Agent의 자연어 보고서 생성
2. Threat Detection Agent의 애매한 케이스 판단 보조
3. 데모 영상 또는 캐시 로그로 LLM 사용 효과 제시

보고서 문구:

> 본 시스템은 재현성을 위해 기본 실행 경로에서는 외부 LLM API에 의존하지 않으며, LLM 기반 보고서 생성은 선택 모듈로 분리하였다.

---

## 10. 개발 로드맵

| 단계 | 기간 | 산출물 |
|---|---|---|
| P0 합의 | 6/26~6/27 | 통합 플랜 확정, I/O 스키마 확정, GitHub 레포 정리 |
| P1 수직 슬라이스 | 6/28~7/1 | `PRIORITY_POISONING` 1종으로 Red→Blue→Report→log 1라운드 E2E |
| P2 공격/방어 확장 | 7/2~7/5 | MVP 공격 6종, 방어 정책, N라운드, scorer, tests |
| P3 대시보드/LLM | 7/5~7/7 | Streamlit 대시보드, 선택적 LLM 보고서, 데모 캡처 |
| P4 보고서 | 7/6~7/9 | 8항목 보고서 작성, 로그/그림/코드 스니펫 삽입 |
| P5 제출 | 7/9~7/10 | Docker 재현 확인, ZIP/PDF 제출, 파일명 규칙 점검 |

---

## 11. 역할 분배

4인 기준 권장:

| 역할 | 코드 소유권 | 보고서 담당 |
|---|---|---|
| A. Red/공격 | `agents/red_agent.py`, `attacks/`, `data/scenarios/` | 공격 시나리오 설계 |
| B. Blue 탐지/임무 | `threat_detection_agent.py`, `mission_monitor_agent.py` | 탐지 근거, 임무 영향 분석 |
| C. Defense/Orchestrator | `main.py`, `environment/`, `defenses/`, Docker | 방어 아키텍처, 실행 재현성 |
| D. Report/Dashboard/문서 | `incident_report_agent.py`, `dashboard.py`, `docs/` | 구현 결과, 대시보드, 보고서 완성 |

2~3인 개발이면 A와 C를 우선 분리하고, B/D를 합치는 방식이 현실적이다.

---

## 12. 보고서에 넣을 핵심 문장

> 본 시스템은 사람이 각 공격·방어 행동을 수동으로 선택하는 방식이 아니라, Red Team Agent와 Blue Team Multi-Agent System이 라운드 기반으로 상호작용하는 자율 공방 구조로 설계된다.

> Red Team Agent는 현재 임무 단계, 통신 상태, 항법 의존도, 군집 합의 상태, 자원 압박 상태를 상황 태그로 해석하고, 그 상황에서 가장 효과적인 공격 표면을 선택한다.

> Blue Team은 단순히 공격 타입을 맞히는 것이 아니라, AI Agent가 의사결정에 사용하는 데이터의 신뢰도를 동적으로 평가하고 오염된 관측값을 임무 판단에서 격리한다.

> 방어 조치는 즉시 무한 적용되지 않으며, 처리 시간과 자원 비용을 가진 작업으로 큐에 등록된다. 따라서 본 시스템은 방어 레이턴시, 방어 큐 깊이, 가용성 손실을 함께 측정해 시간차 공격과 Agent DoS의 효과를 검증한다.

> 본 방어 설계는 금융결제·주문 시스템의 ACID식 트랜잭션 무결성 사고방식에서 착안하였다. 명령, 텔레메트리, 임무파일, 노드 신원 정보를 하나의 상태 전이로 보고, Atomicity·Consistency·Isolation·Durability 관점에서 잘못된 입력 차단, 상태 일관성 검증, 동시 이벤트 격리, 장애 후 복구 로그 보존을 수행한다.

> 본 프로젝트는 실제 RF·GNSS·C2 프로토콜 공격을 구현하는 것이 아니라, 예선 단계에서 공개되지 않은 본선 환경을 고려해 방산 AI가 신뢰하는 추상 데이터 계층을 공격·방어하는 폐쇄형 시뮬레이션으로 범위를 한정한다.

---

## 13. 리스크와 한계

| 리스크 | 대응 |
|---|---|
| 공격 종류가 많아 구현이 얕아질 수 있음 | P1에서 1종 E2E를 먼저 완성하고 6종으로 확장 |
| 룰베이스가 단순 if문처럼 보일 수 있음 | 상황 태그, 신뢰도 모델, 방어 큐, 점수판으로 차별화 |
| 방어 정책이 공격별 1:1 암기처럼 보일 수 있음 | invariant violation 기반 탐지와 공통 defense action 사용 |
| LLM API 의존성으로 재현성이 낮아질 수 있음 | LLM 기본 off, 선택 모듈화, 데모 로그 캐시 |
| 실제 방산 프로토콜 구현이 아님 | 추상화 이유와 본선 어댑터 가능성을 보고서에 명확히 설명 |
| 방어가 너무 강하면 Red가 의미 없어짐 | defense latency, queue depth, availability cost로 균형 조정 |
| 방어가 너무 약하면 Blue가 장식이 됨 | 최소 방어 원칙과 우선순위 선점 처리 구현 |

---

## 14. 즉시 실행 체크리스트

1. `schemas.py`에 상태, 공격, 탐지, 방어, 점수 로그 모델 정의
2. `environment/simulator.py`에 `apply_attack`, `enqueue_defense_tasks`, `advance_defense_tasks` 구현
3. `PRIORITY_POISONING` 1종으로 수직 슬라이스 완성
4. `round_logs.jsonl`과 `summary.json` 저장
5. `scorer.py`에 detection/defense latency와 availability cost 반영
6. MVP 공격 6종 추가
7. 방어 정책 테이블 코드화
8. Streamlit 대시보드에서 world/observed, defense queue, score 표시
9. Docker 또는 requirements 기반 재현성 확인
10. 보고서 8항목에 실제 로그/스크린샷 삽입

---

## 15. 최종 판단

이 플랜의 핵심은 많은 공격을 나열하는 것이 아니라, “AI가 신뢰하는 데이터 계층을 공격하고, Blue가 값 자체가 아니라 신뢰도·시간순서·출처·처리 가능성을 방어한다”는 메시지를 구현으로 증명하는 것이다.

따라서 우선순위는 다음과 같다.

1. 돌아가는 1라운드 E2E
2. 라운드 로그와 점수판
3. 방어 큐/레이턴시 모델
4. MVP 공격 6종 확장
5. 대시보드와 보고서 캡처
6. 선택적 LLM 보고서 생성
