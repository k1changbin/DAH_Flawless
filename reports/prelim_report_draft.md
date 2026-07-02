# DAH 2026 Preliminary Report Draft

Team: DAH Flawless  
Submission date: 2026-07-10  
Report status: draft source. Fill final team-member names and export to PDF before submission.

## 1. Cover

Title: Defense AI Cyber Security Hackathon - Red/Blue Agent Simulation for Trusted Defense AI  
Team: DAH Flawless  
Main thesis: We defend the AI system's belief, not only its network perimeter. Over-defense can also become mission failure.

## 2. Table of Contents

1. Cover  
2. Table of contents  
3. Team composition and roles  
4. Defense-domain attack scenario design  
5. Defense architecture for attack scenarios  
6. AI agent architecture and implementation  
7. Conclusion and future plan  
8. References

## 3. Team Composition and Roles

Fill the final member names before PDF export.

| Role | Technical responsibility | Code/report ownership |
|---|---|---|
| Attack scenario lead | Defense-domain threat modeling, Red Agent scenario design | `src/dah_flawless/attacks/`, report section 4 |
| Defense architecture lead | Invariant detection, containment and recovery design | `src/dah_flawless/blue/`, report section 5 |
| Simulation/reproducibility lead | State model, scorer, hash-chain logs, tests | `src/dah_flawless/environment/`, `src/dah_flawless/scoring/`, tests |
| Documentation/visualization lead | Figures, evidence trace, final report packaging | `src/dah_flawless/reports/`, `reports/figures/` |

## 4. Defense-Domain Attack Scenario Design

### 4.1 Operational Setting

The simulation models a reconnaissance UAV controlled by a ground control station. The UAV relies on telemetry, C2 messages, timestamps, and mission-priority values to decide whether to continue reconnaissance or return to base. The Red Agent does not compromise the full platform. Instead, it pollutes the observation layer that the Blue control AI uses for decision-making.

The implementation separates `world` from `blue_observed`. `world` is the simulator's true state and remains available only to the Environment and Scorer. `blue_observed` is the state received by the Blue AI. This makes the game a partial-observation defense problem rather than a trivial "look up the answer" task.

Evidence: `world_observed_diff.png`, `agent_architecture.png`, `data/logs/round_logs.jsonl`.

### 4.2 Attack 1 - PRIORITY_POISONING

| Field | Description |
|---|---|
| Operational situation | The UAV is assigned to area A, but mission priorities arrive through the observed mission layer. |
| Attack surface | `blue_observed.mission.area_priority`, `blue_observed.mission.recommended_area` |
| Red mutation | A remains true priority in `world`, but observed priority is shifted toward area C. |
| AI misjudgment | The control AI may select a lower-value or adversary-preferred reconnaissance area. |
| Mission damage | Mission value falls even if the platform remains available. |
| Blue detection clue | Priority jumps beyond allowed delta without supporting mission event. |
| Defense result | Quarantine priority update and request revalidation. |
| Evidence | Round log attack `PRIORITY_POISONING`, `detect_contain_recover.png` |

### 4.3 Attack 2 - TELEMETRY_FDI

| Field | Description |
|---|---|
| Operational situation | The UAV has low battery and a motor fault, but telemetry is trusted by the control AI. |
| Attack surface | `blue_observed.telemetry.battery_percent`, `blue_observed.telemetry.motor_status` |
| Red mutation | Observed battery is raised to 82 and motor status becomes OK. |
| AI misjudgment | Return-to-base or safe-mode decisions can be delayed. |
| Mission damage | UAV loss risk and availability degradation. |
| Blue detection clue | Battery, drain rate, and motor status violate physical consistency. |
| Defense result | Quarantine telemetry fields and fall back to last trusted state. |
| Evidence | Round log attack `TELEMETRY_FDI`, `world_observed_diff.png` |

### 4.4 Attack 3 - TIME_DESYNC_REPLAY

| Field | Description |
|---|---|
| Operational situation | C2 messages use sequence and timestamp metadata. |
| Attack surface | `blue_observed.c2_message.sequence_number`, `blue_observed.time.received_timestamp`, `blue_observed.c2_message.command` |
| Red mutation | A stale command is replayed with older sequence and timestamp values. |
| AI misjudgment | A previous continue-mission command can override a safer return command. |
| Mission damage | Unsafe command acceptance under high latency and packet loss. |
| Blue detection clue | Sequence regression, timestamp skew, replay indicators. |
| Defense result | Hold command and request revalidation. |
| Evidence | Round log attack `TIME_DESYNC_REPLAY`, `attack_flow.png` |

## 5. Defense Architecture for Attack Scenarios

The Blue side is implemented as four cooperating agents: Threat Detection, Mission Monitor, Defense Planner, and Incident Report. Threat Detection reads only redacted observed state and prior observed history. It emits target-domain threats from invariant violations rather than attack-name matching.

| Attack | Detect | Contain | Recover |
|---|---|---|---|
| `PRIORITY_POISONING` | Mission priority changed beyond allowed delta | Quarantine mission priority update | Request revalidation and keep trusted mission basis |
| `TELEMETRY_FDI` | Telemetry conflict and battery/motor inconsistency | Quarantine telemetry fields | Fall back to last trusted telemetry |
| `TIME_DESYNC_REPLAY` | Sequence regression and timestamp skew | Hold command | Request revalidation and keep trusted command |

Defense actions carry availability cost. This prevents a naive design where every anomaly triggers full shutdown. The Scorer can emit `RED_ATTRITION` when defensive cost drops mission availability below the floor, which directly supports the report claim that over-defense can also cause mission failure.

Evidence: `src/dah_flawless/blue/invariants.py`, `src/dah_flawless/blue/defense_planner.py`, `availability.png`, `detect_contain_recover.png`.

## 6. AI Agent Architecture and Implementation

### 6.1 Agent Loops

| Agent | Observe | Decide | Act | Feedback |
|---|---|---|---|---|
| Red Agent | Redacted observed state and situation tags | Weighted attack selection | Observed-only mutation | Scorer detection feedback updates weights |
| Threat Detection Agent | Redacted observed state and history | Invariant violation confidence | Emits threats | Logged in `decision_log` |
| Mission Monitor Agent | Threats and observed mission state | Mission risk estimate | Emits mission risks | Logged in `decision_log` |
| Defense Planner Agent | Threats, risks, availability | Minimal action set | Quarantine, hold, fallback, revalidation | Availability/trust budget updated |
| Incident Report Agent | Threats, risks, score | Operator summary | Writes incident report entry | Used as report evidence |

### 6.2 Scorer and Audit Log

The Scorer is the only component that compares `world` and `blue_observed`. It computes attack success, detection success, false positives, recovery success, availability, and winner. Every JSONL entry is chained with `prev_hash` and `this_hash` so manual tampering can be detected.

Verification tests:

- `tests/test_redaction.py`
- `tests/test_attacks_e2e.py`
- `tests/test_seed_reproducibility.py`
- `tests/test_scorer.py`
- `tests/test_hash_log.py`

## 7. Conclusion and Future Plan

The MVP demonstrates the three high-value scoring areas of the preliminary round: concrete defense-domain attack scenarios, a feasible defense architecture, and a cooperative AI-agent implementation. Its strongest design point is the explicit truth boundary: Red and Blue do not receive `world`, while Scorer uses `world` only for objective evaluation.

Future extensions:

- Add multi-UAV and UGV relay nodes.
- Add multiple seeds and aggregate confidence intervals.
- Add defense queue saturation experiments.
- Add more low-feasibility attacks only as coverage stress tests.
- Export the final report PDF after the team roster and final references are frozen.

## 8. References

Use the source list in `../docs/reference_sources.md` for final citation formatting:

- NAVCEN GPS Interface Specification IS-GPS-200N
- MAVLink Packet Serialization
- MAVLink Message Signing
- NIST SP 800-30 Rev. 1
- MITRE ATT&CK for ICS
