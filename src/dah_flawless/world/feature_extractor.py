"""Feature extraction from DAH raw world samples.

The extractor converts shared raw-world signals and emissions into normalized
numeric features for the Situation Tagger. It intentionally ignores
`scenario_truth_annotations` so downstream tags are derived from observable
signal properties rather than generator truth labels.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from statistics import mean, pstdev
from typing import Any


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def round_float(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def normalize(value: float, low: float, high: float) -> float:
    if high == low:
        return 0.0
    return clamp((float(value) - low) / (high - low))


def inverse_normalize(value: float, low: float, high: float) -> float:
    return 1.0 - normalize(value, low, high)


def safe_mean(values: list[float], default: float = 0.0) -> float:
    return mean(values) if values else default


def safe_pstdev(values: list[float], default: float = 0.0) -> float:
    return pstdev(values) if len(values) > 1 else default


def vector_speed(values: list[float] | tuple[float, ...] | None) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(float(v) ** 2 for v in values))


def geometric_mean(scores: list[float]) -> float:
    clean = [clamp(score, 0.001, 1.0) for score in scores]
    if not clean:
        return 0.0
    return math.prod(clean) ** (1 / len(clean))


@dataclass(frozen=True)
class FeatureBundle:
    """Extracted feature output."""

    schema_id: str
    source_raw_world_hash: str | None
    condition: dict[str, Any]
    features: dict[str, Any]
    candidate_scores: dict[str, float]
    evidence: list[dict[str, Any]]


class RawWorldFeatureExtractor:
    """Extract normalized features from a raw world sample."""

    def extract(self, sample: dict[str, Any]) -> dict[str, Any]:
        raw_world = sample.get("raw_world", sample)
        features: dict[str, Any] = {
            "rf": self._extract_rf(raw_world),
            "gnss": self._extract_gnss(raw_world),
            "satcom": self._extract_satcom(raw_world),
            "mavlink_c2": self._extract_mavlink_c2(raw_world),
            "mission": self._extract_mission(raw_world),
            "scene": self._extract_scene(raw_world),
            "environment": self._extract_environment(raw_world),
        }
        features["composite"] = self._extract_composite(features)

        evidence = self._build_evidence(features)
        candidate_scores = self._candidate_scores(features)
        bundle = FeatureBundle(
            schema_id="dah.raw_world.features.v0_1",
            source_raw_world_hash=sample.get("raw_world_hash", sample.get("world_hash")),
            condition=sample.get("condition", {}),
            features=features,
            candidate_scores=candidate_scores,
            evidence=evidence,
        )
        return {
            "schema_id": bundle.schema_id,
            "source_raw_world_hash": bundle.source_raw_world_hash,
            "condition": bundle.condition,
            "features": bundle.features,
            "candidate_scores": bundle.candidate_scores,
            "evidence": bundle.evidence,
        }

    def _extract_rf(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        rf = raw_world.get("rf_spectrum", {})
        emitters = rf.get("emitters", [])
        noise_floor = float(rf.get("noise_floor_dbm", -100.0))

        emitter_features = []
        for emitter in emitters:
            period = emitter.get("burst_period_ms")
            width = emitter.get("burst_width_ms")
            duty_cycle = float(emitter.get("duty_cycle") or 0.0)
            rssi = float(emitter.get("rssi_dbm_at_reference", -120.0))
            snr = float(emitter.get("snr_db_at_reference", 0.0))
            bearing_stability = float(emitter.get("bearing_stability") or 0.0)
            payload_decodable = bool(emitter.get("payload_decodable"))
            periodicity_score = self._periodicity_score(period, duty_cycle)
            signal_strength_score = normalize(rssi, -100, -55)
            snr_score = normalize(snr, 6, 28)
            opacity_score = 0.0 if payload_decodable else 1.0
            c2_pattern_score = clamp(
                0.34 * periodicity_score
                + 0.24 * bearing_stability
                + 0.18 * snr_score
                + 0.14 * signal_strength_score
                + 0.10 * opacity_score
            )
            emitter_features.append(
                {
                    "id": emitter.get("id"),
                    "center_freq_hz": emitter.get("center_freq_hz"),
                    "burst_period_ms": period,
                    "burst_width_ms": width,
                    "duty_cycle": round_float(duty_cycle),
                    "rssi_dbm": round_float(rssi, 1),
                    "snr_db": round_float(snr, 1),
                    "bearing_stability": round_float(bearing_stability),
                    "payload_decodable": payload_decodable,
                    "periodicity_score": round_float(periodicity_score),
                    "signal_strength_score": round_float(signal_strength_score),
                    "snr_score": round_float(snr_score),
                    "c2_pattern_score": round_float(c2_pattern_score),
                }
            )

        best = max(emitter_features, key=lambda item: item["c2_pattern_score"], default=None)
        strongest = max(emitter_features, key=lambda item: item["rssi_dbm"], default=None)
        periodic_count = sum(1 for item in emitter_features if item["periodicity_score"] >= 0.5)
        return {
            "noise_floor_dbm": round_float(noise_floor, 1),
            "spectrum_window_count": len(rf.get("spectrum_windows", [])),
            "emitter_count": len(emitter_features),
            "periodic_emitter_count": periodic_count,
            "best_c2_candidate_id": best["id"] if best else None,
            "best_c2_pattern_score": best["c2_pattern_score"] if best else 0.0,
            "strongest_emitter_id": strongest["id"] if strongest else None,
            "strongest_rssi_dbm": strongest["rssi_dbm"] if strongest else None,
            "avg_bearing_stability": round_float(safe_mean([item["bearing_stability"] for item in emitter_features])),
            "payload_decodable_rate": round_float(
                safe_mean([1.0 if item["payload_decodable"] else 0.0 for item in emitter_features])
            ),
            "emitters": emitter_features,
        }

    def _periodicity_score(self, period_ms: int | float | None, duty_cycle: float) -> float:
        if not period_ms:
            return 0.0
        period = float(period_ms)
        period_window_score = 1.0 if 800 <= period <= 6000 else normalize(period, 100, 800) * inverse_normalize(period, 6000, 12000)
        duty_score = 1.0 - abs(clamp(duty_cycle, 0.0, 0.6) - 0.08) / 0.52
        return clamp(0.72 * period_window_score + 0.28 * duty_score)

    def _extract_gnss(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        gnss = raw_world.get("gnss_field", {})
        sats = gnss.get("satellites", [])
        cn0_values = [float(sat.get("cn0_dbhz_at_reference", 0.0)) for sat in sats]
        doppler_values = [float(sat.get("doppler_hz_at_reference", 0.0)) for sat in sats]
        pseudorange_values = [float(sat.get("pseudorange_m_at_reference", 0.0)) for sat in sats]
        nav_valid_values = [1.0 if sat.get("nav_message_valid") else 0.0 for sat in sats]
        spoof_sources = gnss.get("spoofing_or_meaconing_sources", [])
        interference_strengths = [float(source.get("strength", 0.0)) for source in spoof_sources]
        avg_cn0 = safe_mean(cn0_values)
        min_cn0 = min(cn0_values) if cn0_values else 0.0
        satellite_count = len(sats)
        cn0_weak_score = inverse_normalize(avg_cn0, 28, 43)
        satellite_visibility_score = normalize(satellite_count, 5, 14)
        doppler_spread_hz = safe_pstdev(doppler_values)
        doppler_inconsistency_score = normalize(doppler_spread_hz, 400, 1600)
        pseudorange_span_m = max(pseudorange_values) - min(pseudorange_values) if len(pseudorange_values) > 1 else 0.0
        interference_score = clamp(max(interference_strengths, default=0.0) + (0.10 if spoof_sources else 0.0))
        nav_valid_rate = safe_mean(nav_valid_values, default=1.0)
        gnss_quality_score = clamp(
            0.40 * normalize(avg_cn0, 25, 45)
            + 0.25 * satellite_visibility_score
            + 0.20 * nav_valid_rate
            + 0.15 * (1 - interference_score)
        )
        return {
            "satellite_count": satellite_count,
            "avg_cn0_dbhz": round_float(avg_cn0, 1),
            "min_cn0_dbhz": round_float(min_cn0, 1),
            "cn0_weak_score": round_float(cn0_weak_score),
            "satellite_visibility_score": round_float(satellite_visibility_score),
            "nav_message_valid_rate": round_float(nav_valid_rate),
            "doppler_spread_hz": round_float(doppler_spread_hz, 1),
            "doppler_inconsistency_score": round_float(doppler_inconsistency_score),
            "pseudorange_span_m": round_float(pseudorange_span_m, 1),
            "interference_source_count": len(spoof_sources),
            "interference_score": round_float(interference_score),
            "ionosphere_delay_ns": gnss.get("ionosphere_delay_ns"),
            "troposphere_delay_ns": gnss.get("troposphere_delay_ns"),
            "gnss_quality_score": round_float(gnss_quality_score),
            "gnss_degradation_score": round_float(1 - gnss_quality_score),
        }

    def _extract_satcom(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        satcom = raw_world.get("satcom_emissions", {})
        windows = satcom.get("link_windows", [])
        delays = [float(window.get("propagation_delay_ms", 0.0)) for window in windows]
        availability = [float(window.get("availability_score", 1.0)) for window in windows]
        rain_fade = [float(window.get("rain_fade_score", 0.0)) for window in windows]
        max_delay = max(delays, default=0.0)
        avg_availability = safe_mean(availability, 1.0)
        max_rain_fade = max(rain_fade, default=0.0)
        delay_score = normalize(max_delay, 250, 900)
        instability_score = clamp(0.45 * delay_score + 0.35 * (1 - avg_availability) + 0.20 * max_rain_fade)
        return {
            "link_window_count": len(windows),
            "frame_count": len(satcom.get("frames", [])),
            "max_propagation_delay_ms": round_float(max_delay, 1),
            "delay_score": round_float(delay_score),
            "avg_availability_score": round_float(avg_availability),
            "max_rain_fade_score": round_float(max_rain_fade),
            "satcom_instability_score": round_float(instability_score),
            "carrier_bands": sorted({window.get("carrier_band") for window in windows if window.get("carrier_band")}),
        }

    def _extract_mavlink_c2(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        emissions = raw_world.get("uav_c2_emissions", {})
        frames = emissions.get("frames", [])
        seqs = [int(frame["sequence_number"]) for frame in frames if frame.get("sequence_number") is not None]
        sorted_seqs = sorted(seqs)
        expected_gaps = max(len(sorted_seqs) - 1, 0)
        actual_gap_count = sum(1 for prev, curr in zip(sorted_seqs, sorted_seqs[1:]) if curr - prev != 1)
        sequence_gap_rate = actual_gap_count / expected_gaps if expected_gaps else 0.0
        signing_values = [1.0 if frame.get("signature_present") else 0.0 for frame in frames]
        signed_values = [1.0 if frame.get("signed") else 0.0 for frame in frames]
        times = [int(frame.get("tx_time_ms", 0)) for frame in frames]
        time_span_ms = max(times) - min(times) if len(times) > 1 else 0
        command_count = sum(1 for frame in frames if str(frame.get("message_name", "")).startswith("COMMAND"))
        mission_count = sum(1 for frame in frames if str(frame.get("message_name", "")).startswith("MISSION"))
        return {
            "frame_count": len(frames),
            "message_names": [frame.get("message_name") for frame in frames],
            "channels": sorted({frame.get("channel_hint") for frame in frames if frame.get("channel_hint")}),
            "source_roles": sorted({frame.get("source_role") for frame in frames if frame.get("source_role")}),
            "sequence_numbers": sorted_seqs,
            "sequence_gap_rate": round_float(sequence_gap_rate),
            "time_span_ms": time_span_ms,
            "command_count": command_count,
            "mission_count": mission_count,
            "command_density": round_float(command_count / max(len(frames), 1)),
            "signing_presence_rate": round_float(safe_mean(signing_values)),
            "signed_rate": round_float(safe_mean(signed_values)),
            "heartbeat_present": "HEARTBEAT" in {frame.get("message_name") for frame in frames},
            "gps_raw_present": "GPS_RAW_INT" in {frame.get("message_name") for frame in frames},
            "mavlink_activity_score": round_float(clamp(len(frames) / 8.0 + command_count * 0.12)),
        }

    def _extract_mission(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        mission = raw_world.get("mission_space", {})
        targets = mission.get("targets", [])
        priorities = sorted([float(target.get("priority_ground_truth", 0.0)) for target in targets], reverse=True)
        priority_gap = priorities[0] - priorities[1] if len(priorities) >= 2 else 0.0
        return {
            "area_id": mission.get("area_id"),
            "mission_phase_hint": mission.get("mission_phase_hint"),
            "target_count": len(targets),
            "priority_gap": round_float(priority_gap),
            "priority_ambiguity_score": round_float(inverse_normalize(priority_gap, 0.08, 0.42)),
            "no_fly_zone_count": len(mission.get("no_fly_zones", [])),
            "return_base_count": len(mission.get("return_bases", [])),
        }

    def _extract_scene(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        objects = raw_world.get("physical_scene", {}).get("objects", [])
        unknown_air = [obj for obj in objects if obj.get("object_type") == "UNKNOWN_AIR"]
        friendly_uav = [obj for obj in objects if obj.get("object_type") == "FRIENDLY_UAV"]
        rf_linked_unknown = [obj for obj in unknown_air if obj.get("rf_emission_refs")]
        speeds = [vector_speed(obj.get("velocity_truth_mps")) for obj in unknown_air]
        altitudes = [float(obj.get("position_truth", [0, 0, 0])[2]) for obj in unknown_air if obj.get("position_truth")]
        thermal_scores = [float(obj.get("thermal_signature_score", 0.0)) for obj in unknown_air]
        return {
            "object_count": len(objects),
            "unknown_air_count": len(unknown_air),
            "friendly_uav_count": len(friendly_uav),
            "rf_linked_unknown_air_count": len(rf_linked_unknown),
            "unknown_air_max_speed_mps": round_float(max(speeds, default=0.0), 1),
            "unknown_air_min_altitude_m": round_float(min(altitudes, default=0.0), 1),
            "unknown_air_avg_thermal_signature": round_float(safe_mean(thermal_scores)),
            "air_contact_score": round_float(clamp(len(unknown_air) * 0.45 + len(rf_linked_unknown) * 0.35)),
        }

    def _extract_environment(self, raw_world: dict[str, Any]) -> dict[str, Any]:
        weather = raw_world.get("weather_field", {})
        terrain = raw_world.get("terrain_field", {})
        eo_ir = raw_world.get("eo_ir_scene", {})
        occlusion = max(
            [float(zone.get("occlusion_severity", 0.0)) for zone in terrain.get("occlusion_zones", [])],
            default=0.0,
        )
        terrain_multipath = max(
            [float(zone.get("severity", 0.0)) for zone in terrain.get("multipath_zones", [])],
            default=0.0,
        )
        obscurant = max(
            [float(zone.get("severity", 0.0)) for zone in eo_ir.get("obscurant_zones", [])],
            default=0.0,
        )
        visibility_m = float(weather.get("visibility_m", 10_000))
        wind_mps = float(weather.get("wind_speed_mps", 0.0))
        return {
            "visibility_m": int(visibility_m),
            "visibility_low_score": round_float(inverse_normalize(visibility_m, 1200, 8000)),
            "wind_speed_mps": round_float(wind_mps, 1),
            "wind_high_score": round_float(normalize(wind_mps, 6, 18)),
            "fog_level": weather.get("fog_level", 0.0),
            "precipitation_level": weather.get("precipitation_level", 0.0),
            "turbulence_level": weather.get("turbulence_level", 0.0),
            "terrain_occlusion_score": round_float(occlusion),
            "terrain_multipath_score": round_float(terrain_multipath),
            "obscurant_score": round_float(obscurant),
        }

    def _extract_composite(self, features: dict[str, Any]) -> dict[str, Any]:
        rf_c2 = float(features["rf"]["best_c2_pattern_score"])
        gnss_degraded = float(features["gnss"]["gnss_degradation_score"])
        satcom_unstable = float(features["satcom"]["satcom_instability_score"])
        mav_activity = float(features["mavlink_c2"]["mavlink_activity_score"])
        air_contact = float(features["scene"]["air_contact_score"])
        environment_friction = clamp(
            0.34 * features["environment"]["visibility_low_score"]
            + 0.24 * features["environment"]["terrain_occlusion_score"]
            + 0.22 * features["environment"]["terrain_multipath_score"]
            + 0.20 * features["environment"]["wind_high_score"]
        )
        c2_exploit_window = clamp(0.42 * rf_c2 + 0.22 * air_contact + 0.20 * satcom_unstable + 0.16 * mav_activity)
        cross_layer_drift_opportunity = geometric_mean([max(rf_c2, 0.01), max(gnss_degraded, 0.01), max(satcom_unstable, 0.01)])
        return {
            "environment_friction_score": round_float(environment_friction),
            "c2_exploit_window_score": round_float(c2_exploit_window),
            "cross_layer_drift_opportunity": round_float(cross_layer_drift_opportunity),
            "belief_attack_surface_score": round_float(
                clamp(0.35 * c2_exploit_window + 0.30 * cross_layer_drift_opportunity + 0.20 * environment_friction + 0.15 * air_contact)
            ),
        }

    def _candidate_scores(self, features: dict[str, Any]) -> dict[str, float]:
        return {
            "C2_PATTERN_EXPLOIT": round_float(features["composite"]["c2_exploit_window_score"]),
            "GNSS_DRIFT": round_float(
                clamp(
                    0.45 * features["gnss"]["gnss_degradation_score"]
                    + 0.35 * features["environment"]["terrain_multipath_score"]
                    + 0.20 * features["satcom"]["satcom_instability_score"]
                )
            ),
            "TIME_DESYNC_REPLAY": round_float(
                clamp(
                    0.50 * features["satcom"]["delay_score"]
                    + 0.30 * features["mavlink_c2"]["mavlink_activity_score"]
                    + 0.20 * features["mavlink_c2"]["sequence_gap_rate"]
                )
            ),
            "TELEMETRY_FDI": round_float(
                clamp(
                    0.40 * features["mavlink_c2"]["mavlink_activity_score"]
                    + 0.25 * features["satcom"]["satcom_instability_score"]
                    + 0.20 * features["environment"]["visibility_low_score"]
                    + 0.15 * features["scene"]["air_contact_score"]
                )
            ),
            "CROSS_LAYER_BELIEF_DRIFT": round_float(features["composite"]["belief_attack_surface_score"]),
        }

    def _build_evidence(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = []
        rf = features["rf"]
        if rf["best_c2_candidate_id"]:
            evidence.append(
                {
                    "feature": "rf.best_c2_pattern_score",
                    "value": rf["best_c2_pattern_score"],
                    "source": rf["best_c2_candidate_id"],
                    "reason": "periodic burst, stable bearing, SNR, and undecoded payload support C2-pattern suspicion",
                }
            )
        gnss = features["gnss"]
        evidence.append(
            {
                "feature": "gnss.gnss_degradation_score",
                "value": gnss["gnss_degradation_score"],
                "source": "gnss_field",
                "reason": "derived from C/N0, satellite count, nav validity, and interference sources",
            }
        )
        satcom = features["satcom"]
        evidence.append(
            {
                "feature": "satcom.satcom_instability_score",
                "value": satcom["satcom_instability_score"],
                "source": "satcom_emissions",
                "reason": "derived from propagation delay, availability, and rain fade",
            }
        )
        evidence.append(
            {
                "feature": "composite.belief_attack_surface_score",
                "value": features["composite"]["belief_attack_surface_score"],
                "source": "composite",
                "reason": "combines RF C2 evidence, GNSS degradation, SATCOM instability, and environmental friction",
            }
        )
        return evidence


def extract_features(sample: dict[str, Any]) -> dict[str, Any]:
    return RawWorldFeatureExtractor().extract(sample)


def summarize_features(feature_row: dict[str, Any]) -> str:
    features = feature_row["features"]
    candidates = feature_row["candidate_scores"]
    best_attack = max(candidates, key=candidates.get)
    return (
        f"raw_world={feature_row.get('source_raw_world_hash', '')[:8]} "
        f"rf_c2={features['rf']['best_c2_pattern_score']} "
        f"gnss_deg={features['gnss']['gnss_degradation_score']} "
        f"satcom_inst={features['satcom']['satcom_instability_score']} "
        f"best={best_attack}:{candidates[best_attack]}"
    )
