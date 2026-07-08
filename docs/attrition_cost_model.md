# Attrition Cost Model

This project treats `RED_ATTRITION` as a simulator-level cyber effect, not as a
real attack procedure. The label should mean that Red induced Blue to spend
defense resources in a way that materially degraded mission availability.

## Design Sources

- NIST SP 800-160 Vol. 2 Rev. 1 frames cyber resiliency around the ability to
  anticipate, withstand, recover from, and adapt to adverse cyber conditions.
  This supports scoring defense by mission continuity, not only detection.
- Moving-target-defense and attacker-defender game papers model defense as a
  limited-resource optimization problem. A defense that detects everything but
  spends too much budget can still be strategically poor.
- MITRE ATT&CK Impact treats availability disruption and data manipulation as
  distinct operational effects. We therefore separate `BREACH`, `ATTRITION`,
  `PARTIAL_BREACH`, and `NO_EFFECT`.
- MAVLink signing documentation highlights sequence/timestamp monotonicity,
  link IDs, and replay rejection. Our `TIME_DESYNC_REPLAY` variants operate
  only on simulated visible metadata fields such as sequence, timestamp, ACK,
  latency, packet loss, jitter, and heartbeat gap.
- MAVLink security literature and UAV spoofing simulation work motivate false
  data injection and metadata manipulation as simulator effects, while this
  repository avoids real exploitation steps.

## Scoring Rule

`RED_ATTRITION` now requires all of the following:

1. Blue availability crosses the configured floor.
2. The floor breach is fresh, not inherited from an already-low state.
3. There is current, sustained, or consecutive Blue defense pressure.
4. Blue's accumulated defense cost is meaningfully larger than Red's accumulated
   simulated attack cost.
5. The mission impact is non-trivial, or availability loss itself is large.

The scorer records:

- `red_round_attack_cost`
- `round_defense_cost`
- `net_defense_cost`
- `defense_to_attack_cost_ratio`
- `cost_effective`
- `mission_meaningful`

This prevents the model from learning that any Blue cost is automatically a Red
win. If Red spends more than Blue loses, the event can still be useful training
feedback, but it should not be a decisive attrition victory.

## Blue Cost Control

The combat runner now charges active defense against Blue compute and power
budgets. If Blue repeatedly defends while recovery is already working, it backs
off into internal inspection or passive monitoring. This models adaptive
response: Blue should preserve mission availability when the marginal defense
benefit is low.

Blue availability is now scoped to a single round-level combat episode. At the
start of each round, `round_episode_budget_reset_v1` resets
`mission.availability` and `mission.trust_budget` to the scenario's episode
initial budget. This prevents stale availability loss from making a later
`RED_ATTRITION` victory look stronger than the current episode actually
justifies. The detailed procedure is in `docs/blue_availability_recovery_model.md`.

## Red Policy Effectiveness

The three current Red policy families remain simulator-safe effect families:

- `TIME_DESYNC_REPLAY`: strengthened through metadata variants for replay,
  delay, selective drop, ACK confusion, heartbeat gap, jitter, and latency.
- `TELEMETRY_FDI`: strengthened through battery drift plus adjacent plausibility
  fields such as drain-rate shaping and internal/external gap shaping.
- `PRIORITY_POISONING`: strengthened by treating `recommended_area` as a
  decision-support field, not only raw priority vector drift.

These changes make the policies better aligned with the fields that the scorer,
Blue detector, and frontend replay already understand.
