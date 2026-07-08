# Telemetry FDI Defense Notes

## Why This Was Added

The 1000-round combat run showed that `RED_BREACH` was concentrated in `TELEMETRY_FDI / TELEMETRY_TRUST_EROSION`. The failure pattern was not only loud telemetry jumps. Red could reintroduce a small positive telemetry drift after Blue had already restored the field, then end the round before another expensive defense action occurred.

This update adds a lightweight residual-based defense layer:

- compare `external_observe.telemetry` against `internal_observe.telemetry`
- treat low-battery or motor-fault internal state as safety-critical
- flag external telemetry that makes the safety-critical state look safer
- treat repeated same-direction drift as a serial residual signal
- downgrade/quarantine external telemetry usage through the ZTA-inspired policy gate

## References Used

- Bonczek and Bezzo, "Memoryless Cumulative Sign Detector for Stealthy CPS Sensor Attacks", 2020: stealthy sensor attacks can remain within ordinary thresholds, so residual sign/non-randomness and CUSUM-style monitors are useful for detecting falsified measurements. https://arxiv.org/abs/2005.07821
- Gupta, Sikdar, and Chattopadhyay, "Quickest Bayesian and non-Bayesian detection of false data injection attack in remote state estimation", 2020: FDI on remote state estimation benefits from quickest/CUSUM-style detection under false alarm constraints. https://arxiv.org/abs/2010.15785
- Anand, Hassan, and Sandberg, "Feasibility of Randomized Detector Tuning for Attack Impact Mitigation", 2025: stealthy FDI can exploit static detector thresholds; threshold/risk tuning can reduce attack impact. https://arxiv.org/abs/2503.11417
- NIST SP 800-207 Zero Trust Architecture: access/use decisions should be dynamic and not rely on implicit trust. This project applies that idea to observe authority, not network access. https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf

## Implemented Changes

### Situation Tags

New tags:

- `TELEMETRY_ANCHOR_RESIDUAL`
- `TELEMETRY_SAFETY_ANCHOR_RESIDUAL`
- `TELEMETRY_SERIAL_DRIFT`

These are observed-only tags. They do not use scorer truth.

### Threat Detection

The invariant checker now treats the new telemetry residual tags as telemetry threat evidence. `TELEMETRY_SAFETY_ANCHOR_RESIDUAL` raises the base confidence because the risk is asymmetric: if the internal anchor says low battery or motor fault but the external telemetry looks safer, Blue should not use the external value authoritatively.

### ZTA-Inspired Observe Policy Gate

The telemetry gate now weights internal-anchor agreement more heavily. In safety-critical anchor conditions, an external value that looks safer than the internal anchor is quarantined for mission-authoritative use. This does not count as `detection_success`; it appears as `policy_containment`.

## Design Boundary

This is a simulator defense abstraction. It does not implement real RF interception, real exploit payloads, or real vehicle firmware behavior. The purpose is to make the Blue agent more realistic about external telemetry authority in a UAV/UGV-style observed-data setting.
