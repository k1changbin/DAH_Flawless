# DAH Raw World Schema v0.1

This document defines `raw_world` as the shared external battlefield reality:
signals, emissions, physical fields, transmitted frames, terrain, weather, and
scene signatures that multiple actors could receive. It is intentionally not a
friendly AI state object.

## Boundary

- `raw_world`: external reality and emitted data as it exists in the battlespace.
- `observe`: what a specific UAV, UGV, GCS, Red agent, or Blue agent receives,
  decodes, filters, estimates, or computes from `raw_world`.
- `feature`: a numeric/statistical summary extracted from `raw_world` or observe.
- `tag`: tactical meaning assigned by the Situation Tagger.

## MAVLink Assumption

MAVLink is a good default reference for UAV command and telemetry emissions.
In this schema, a MAVLink message is part of `raw_world` only as an emitted frame:
who transmitted it, when, over what channel, and what bytes/payload were
transmitted. The payload value is not treated as private ground truth. For
example, a `BATTERY_STATUS` payload is "the value sent over the air", not the
true electrochemical state of the battery.

## Main Domains

1. `time_reference`: shared timing and clock references.
2. `mission_space`: targets, return bases, no-fly zones, mission geometry.
3. `terrain_field`: terrain, occlusion, multipath and mobility zones.
4. `weather_field`: wind, visibility, precipitation, turbulence.
5. `gnss_field`: GNSS signal and propagation environment before receiver solve.
6. `rf_spectrum`: I/Q windows, unknown emitters, burst patterns, noise.
7. `uav_c2_emissions`: MAVLink/MAVLink-like UAV and GCS frames.
8. `ugv_relay_emissions`: relay beacons and forwarded frames.
9. `satcom_emissions`: BLOS/SATCOM carrier windows and frames.
10. `remote_id_broadcasts`: drone identification broadcasts.
11. `adsb_or_transponder_broadcasts`: cooperative airspace broadcasts.
12. `physical_scene`: physical objects and emission/reflection sources.
13. `eo_ir_scene`: visible/thermal scene before camera sampling.
14. `radar_lidar_reflection_field`: reflectivity before point-cloud creation.
15. `acoustic_thermal_field`: optional acoustic/thermal signatures.
16. `interference_sources`: GNSS/RF jammer, spoofer, decoy emitters.
17. `cyber_message_surface`: packet/message fields transmitted over a medium.
18. `raw_capture_refs`: evidence artifacts such as SigMF, RINEX, PCAP, logs.

The machine-readable catalog is in `configs/raw_world_schema.yaml`.

## First MVP Subset

For the first Red Brain demo, use only these domains:

1. `rf_spectrum`
2. `gnss_field`
3. `uav_c2_emissions`
4. `satcom_emissions`
5. `mission_space`
6. `weather_field`

That subset is enough to produce tags such as:

- `UNKNOWN_PERIODIC_EMITTER`
- `C2_PATTERN_CANDIDATE`
- `GNSS_MULTIPATH_RISK`
- `BLOS_ACTIVE`
- `SATCOM_DELAYED`
- `RECON_APPROACH_WINDOW`

## Pipeline Fit

```text
raw_world_schema
-> synthetic/raw world sample
-> feature extractor
-> raw-world state adapter
-> situation tagger
-> red brain
-> attack intent
-> mutation engine
```

## Repository Layout

```text
configs/raw_world_schema.yaml
src/dah_flawless/world/generator.py
src/dah_flawless/world/feature_extractor.py
src/dah_flawless/world/state_adapter.py
scripts/run_world_generator.py
scripts/run_feature_extractor.py
```

Generated JSONL evidence is written under `tmp/world/` by default and is not
tracked in git.

Example:

```powershell
python scripts/run_world_generator.py --count 2
python scripts/run_feature_extractor.py --summary
python -m dah_flawless.main --raw-world-sample tmp/world/raw_world_samples.jsonl
```
