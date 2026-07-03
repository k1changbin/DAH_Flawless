"""Rule-based raw world generator for the DAH Red Brain prototype.

The generator produces shared external battlefield reality: RF/GNSS fields,
emitted frames, weather, terrain, scene signatures, and references. It does not
produce per-platform observe values such as a UAV's computed GPS position.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random
from typing import Any


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_float(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


@dataclass(frozen=True)
class ScenarioCondition:
    """High-level condition for conditional world generation."""

    mission_phase: str = "RECON_APPROACH"
    terrain: str = "MOUNTAIN"
    weather: str = "LOW_VISIBILITY"
    enemy_presence: str = "LIKELY"
    link_context: str = "BLOS"
    area_id: str = "AO-NORTH-RIDGE"


class RuleBasedWorldGenerator:
    """Generate plausible raw-world samples from scenario conditions.

    This is the pre-VAE baseline. Later, generated samples can become training
    data for a CVAE, and this generator can remain as a constraint oracle.
    """

    def __init__(self, seed: int = 20260704) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def generate(self, condition: ScenarioCondition, sample_index: int = 0) -> dict[str, Any]:
        scenario_time_ms = 120_000 + sample_index * 1_000 + self.rng.randint(0, 500)
        center = self._area_center(condition.area_id)
        weather_field = self._weather_field(condition)
        terrain_field = self._terrain_field(condition)
        mission_space = self._mission_space(condition, center)
        gnss_field = self._gnss_field(condition, weather_field, terrain_field)
        rf_spectrum = self._rf_spectrum(condition, center)
        satcom_emissions = self._satcom_emissions(condition, weather_field, scenario_time_ms)
        physical_scene = self._physical_scene(condition, center, rf_spectrum)
        uav_c2_emissions = self._uav_c2_emissions(condition, scenario_time_ms, satcom_emissions)

        raw_world = {
            "time_reference": self._time_reference(scenario_time_ms, condition),
            "mission_space": mission_space,
            "terrain_field": terrain_field,
            "weather_field": weather_field,
            "gnss_field": gnss_field,
            "rf_spectrum": rf_spectrum,
            "uav_c2_emissions": uav_c2_emissions,
            "ugv_relay_emissions": self._ugv_relay_emissions(condition, scenario_time_ms, center),
            "satcom_emissions": satcom_emissions,
            "remote_id_broadcasts": self._remote_id_broadcasts(scenario_time_ms, physical_scene),
            "adsb_or_transponder_broadcasts": self._adsb_broadcasts(scenario_time_ms),
            "physical_scene": physical_scene,
            "eo_ir_scene": self._eo_ir_scene(weather_field, terrain_field),
            "radar_lidar_reflection_field": self._reflection_field(terrain_field, physical_scene),
            "acoustic_thermal_field": self._acoustic_thermal_field(physical_scene),
            "interference_sources": self._interference_sources(condition, center),
            "cyber_message_surface": self._cyber_message_surface(scenario_time_ms, uav_c2_emissions),
            "raw_capture_refs": self._raw_capture_refs(sample_index),
            "scenario_truth_annotations": self._scenario_truth_annotations(rf_spectrum),
        }

        raw_world_hash = self._stable_hash(raw_world)
        return {
            "schema_id": "dah.raw_world.sample.v0_1",
            "generator": {
                "name": "RuleBasedWorldGenerator",
                "seed": self.seed,
                "sample_index": sample_index,
            },
            "condition": asdict(condition),
            "raw_world": raw_world,
            "raw_world_hash": raw_world_hash,
            "world_hash": raw_world_hash,
        }

    def _time_reference(self, scenario_time_ms: int, condition: ScenarioCondition) -> dict[str, Any]:
        quality_base = 0.88
        if condition.link_context == "BLOS":
            quality_base -= 0.04
        if condition.enemy_presence in {"LIKELY", "CONFIRMED"}:
            quality_base -= 0.03
        return {
            "scenario_time_ms": scenario_time_ms,
            "utc_time_unix_ms": 1_783_203_600_000 + scenario_time_ms,
            "gnss_time_week": 2427,
            "gnss_time_tow_ms": 345_600_000 + scenario_time_ms,
            "clock_reference_quality": round_float(clamp(self.rng.gauss(quality_base, 0.04), 0.45, 0.99)),
            "time_source": "GNSS" if condition.link_context != "SATCOM_ONLY" else "SATCOM",
        }

    def _mission_space(self, condition: ScenarioCondition, center: tuple[float, float]) -> dict[str, Any]:
        lat, lon = center
        target_offsets = [(0.010, 0.008), (0.016, -0.006), (-0.008, 0.014)]
        target_names = ["TARGET-A", "TARGET-B", "TARGET-C"]
        priorities = self._mission_priorities(condition)
        targets = []
        for idx, (dlat, dlon) in enumerate(target_offsets):
            targets.append(
                {
                    "id": target_names[idx],
                    "location": [round_float(lat + dlat, 6), round_float(lon + dlon, 6), 0],
                    "physical_signature": self.rng.choice(["VISUAL", "THERMAL", "RF", "MIXED"]),
                    "priority_ground_truth": priorities[idx],
                }
            )
        return {
            "area_id": condition.area_id,
            "coordinate_frame": "WGS84",
            "mission_phase_hint": condition.mission_phase,
            "targets": targets,
            "return_bases": [
                {"id": "BASE-1", "location": [round_float(lat - 0.026, 6), round_float(lon - 0.034, 6), 0]}
            ],
            "no_fly_zones": [
                {
                    "id": "NFZ-1",
                    "geometry_ref": "geojson/nfz_01.geojson",
                    "center": [round_float(lat - 0.004, 6), round_float(lon + 0.019, 6), 0],
                    "radius_m": 480,
                }
            ],
        }

    def _terrain_field(self, condition: ScenarioCondition) -> dict[str, Any]:
        terrain = condition.terrain.upper()
        if terrain == "MOUNTAIN":
            occlusion_mean = 0.64
            multipath_mean = 0.42
            slope = 18.0
            surface = "ROCK"
        elif terrain == "URBAN":
            occlusion_mean = 0.58
            multipath_mean = 0.66
            slope = 4.0
            surface = "URBAN"
        elif terrain == "COASTAL":
            occlusion_mean = 0.24
            multipath_mean = 0.35
            slope = 2.0
            surface = "SAND"
        else:
            occlusion_mean = 0.28
            multipath_mean = 0.24
            slope = 6.0
            surface = "GRAVEL"
        return {
            "dem_ref": "terrain/dem_tile_01.tif",
            "landcover_ref": "terrain/landcover.geojson",
            "occlusion_zones": [
                {
                    "id": "OCC-RIDGE-1",
                    "geometry_ref": "geojson/occ_ridge_01.geojson",
                    "occlusion_severity": round_float(clamp(self.rng.gauss(occlusion_mean, 0.1), 0, 1)),
                }
            ],
            "multipath_zones": [
                {
                    "id": "MP-ZONE-1",
                    "affected_band": "GNSS_L1",
                    "severity": round_float(clamp(self.rng.gauss(multipath_mean, 0.12), 0, 1)),
                }
            ],
            "mobility_zones": [
                {
                    "id": "MOB-ZONE-1",
                    "slope_deg": round_float(clamp(self.rng.gauss(slope, 3.0), 0, 35), 1),
                    "surface_type": surface,
                }
            ],
        }

    def _weather_field(self, condition: ScenarioCondition) -> dict[str, Any]:
        weather = condition.weather.upper()
        if weather == "LOW_VISIBILITY":
            visibility = self.rng.gauss(2600, 700)
            fog = self.rng.gauss(0.46, 0.15)
            rain = self.rng.gauss(0.15, 0.08)
            wind = self.rng.gauss(8.0, 2.0)
        elif weather == "STORM":
            visibility = self.rng.gauss(1300, 450)
            fog = self.rng.gauss(0.55, 0.16)
            rain = self.rng.gauss(0.75, 0.14)
            wind = self.rng.gauss(15.0, 4.0)
        elif weather == "CLEAR":
            visibility = self.rng.gauss(9000, 1200)
            fog = self.rng.gauss(0.05, 0.03)
            rain = self.rng.gauss(0.02, 0.02)
            wind = self.rng.gauss(4.5, 1.6)
        else:
            visibility = self.rng.gauss(5500, 1000)
            fog = self.rng.gauss(0.18, 0.08)
            rain = self.rng.gauss(0.12, 0.07)
            wind = self.rng.gauss(7.0, 2.5)
        return {
            "wind_speed_mps": round_float(clamp(wind, 0, 28), 1),
            "wind_direction_deg": self.rng.randint(0, 359),
            "visibility_m": int(clamp(visibility, 200, 12000)),
            "precipitation_level": round_float(clamp(rain, 0, 1)),
            "fog_level": round_float(clamp(fog, 0, 1)),
            "temperature_c": round_float(self.rng.gauss(8.0, 7.0), 1),
            "pressure_hpa": round_float(self.rng.gauss(1010, 8), 1),
            "turbulence_level": round_float(clamp(wind / 25.0 + self.rng.uniform(-0.05, 0.08), 0, 1)),
        }

    def _gnss_field(
        self, condition: ScenarioCondition, weather_field: dict[str, Any], terrain_field: dict[str, Any]
    ) -> dict[str, Any]:
        sat_count = self.rng.randint(8, 14)
        multipath = terrain_field["multipath_zones"][0]["severity"]
        interference = 0.15
        if condition.enemy_presence in {"LIKELY", "CONFIRMED"}:
            interference += self.rng.uniform(0.08, 0.25)
        if condition.terrain.upper() in {"MOUNTAIN", "URBAN"}:
            interference += self.rng.uniform(0.03, 0.10)
        rain_penalty = weather_field["precipitation_level"] * 1.8
        satellites = []
        for i in range(sat_count):
            constellation = self.rng.choice(["G", "E", "C"])
            sat_id = f"{constellation}{self.rng.randint(1, 32):02d}"
            cn0 = clamp(self.rng.gauss(40.0 - multipath * 8.0 - rain_penalty, 3.5), 18, 50)
            satellites.append(
                {
                    "sat_id": sat_id,
                    "carrier_band": self.rng.choice(["L1", "L2", "L5"]),
                    "signal_power_dbw": round_float(self.rng.gauss(-158.0, 2.2), 1),
                    "cn0_dbhz_at_reference": round_float(cn0, 1),
                    "pseudorange_m_at_reference": round_float(self.rng.uniform(20_200_000, 24_200_000), 1),
                    "carrier_phase_cycles_at_reference": round_float(self.rng.uniform(90_000, 180_000), 2),
                    "doppler_hz_at_reference": round_float(self.rng.gauss(-600, 650), 1),
                    "nav_message_valid": self.rng.random() > 0.03,
                    "ephemeris_age_sec": int(clamp(self.rng.gauss(2000, 900), 60, 7200)),
                }
            )
        spoof_sources = []
        if interference > 0.32 and self.rng.random() < 0.45:
            spoof_sources.append(
                {
                    "id": "gnss-int-01",
                    "affected_band": "L1",
                    "area_ref": "geojson/north_ridge_interference.geojson",
                    "strength": round_float(clamp(interference, 0, 1)),
                    "time_bias_ns": round_float(self.rng.gauss(18, 9), 1),
                }
            )
        return {
            "constellation_mix": ["GPS", "GALILEO", "BEIDOU"],
            "satellites": satellites,
            "ionosphere_delay_ns": round_float(clamp(self.rng.gauss(7.0, 2.5), 0, 25), 1),
            "troposphere_delay_ns": round_float(clamp(self.rng.gauss(2.2, 0.8), 0, 8), 1),
            "spoofing_or_meaconing_sources": spoof_sources,
        }

    def _rf_spectrum(self, condition: ScenarioCondition, center: tuple[float, float]) -> dict[str, Any]:
        noise_floor = self.rng.gauss(-96, 4)
        emitter_count = 0
        if condition.enemy_presence == "POSSIBLE":
            emitter_count = 1 if self.rng.random() < 0.55 else 0
        elif condition.enemy_presence == "LIKELY":
            emitter_count = 1 if self.rng.random() < 0.85 else 2
        elif condition.enemy_presence == "CONFIRMED":
            emitter_count = self.rng.choice([1, 2, 2, 3])
        emitters = []
        for idx in range(emitter_count):
            c2_like = idx == 0 and condition.enemy_presence in {"LIKELY", "CONFIRMED"}
            freq = self.rng.choice([433_920_000, 868_100_000, 915_400_000, 2_405_000_000])
            period = self.rng.choice([1200, 2000, 2400, 5000]) if c2_like else self.rng.choice([None, 750, 3100])
            width = int(clamp(self.rng.gauss(180 if c2_like else 90, 35), 20, 600)) if period else None
            rssi = self.rng.gauss(-68 if c2_like else -78, 7)
            lat, lon = center
            emitters.append(
                {
                    "id": f"sig-{17 + idx}",
                    "center_freq_hz": freq,
                    "bandwidth_hz": self.rng.choice([125_000, 250_000, 1_000_000]),
                    "modulation_hint": self.rng.choice(["FSK", "FHSS", "LORA_LIKE", "UNKNOWN"]),
                    "burst_period_ms": period,
                    "burst_width_ms": width,
                    "duty_cycle": round_float(width / period if period and width else 0.0),
                    "rssi_dbm_at_reference": round_float(rssi, 1),
                    "snr_db_at_reference": round_float(clamp(rssi - noise_floor + self.rng.gauss(0, 2), 0, 45), 1),
                    "bearing_deg_at_reference": self.rng.randint(0, 359),
                    "bearing_stability": round_float(clamp(self.rng.gauss(0.84 if c2_like else 0.50, 0.12), 0, 1)),
                    "source_location_truth": [
                        round_float(lat + self.rng.uniform(-0.018, 0.018), 6),
                        round_float(lon + self.rng.uniform(-0.018, 0.018), 6),
                        round_float(self.rng.uniform(120, 450) if c2_like else self.rng.uniform(0, 450), 1),
                    ],
                    "payload_decodable": False if c2_like else self.rng.random() < 0.25,
                }
            )
        spectrum_windows = [
            {
                "id": "rfwin-915",
                "center_freq_hz": 915_400_000,
                "bandwidth_hz": 250_000,
                "sample_rate_hz": 2_000_000,
                "iq_ref": "captures/rfwin-915.sigmf-data",
                "metadata_ref": "captures/rfwin-915.sigmf-meta",
            }
        ]
        seen_window_freqs = {915_400_000}
        for emitter in emitters:
            freq = emitter["center_freq_hz"]
            if freq in seen_window_freqs:
                continue
            seen_window_freqs.add(freq)
            band_mhz = int(freq / 1_000_000)
            bandwidth_hz = max(emitter["bandwidth_hz"], 250_000)
            spectrum_windows.append(
                {
                    "id": f"rfwin-{band_mhz}",
                    "center_freq_hz": freq,
                    "bandwidth_hz": bandwidth_hz,
                    "sample_rate_hz": max(bandwidth_hz * 8, 1_000_000),
                    "iq_ref": f"captures/rfwin-{band_mhz}.sigmf-data",
                    "metadata_ref": f"captures/rfwin-{band_mhz}.sigmf-meta",
                }
            )
        return {
            "noise_floor_dbm": round_float(noise_floor, 1),
            "spectrum_windows": spectrum_windows,
            "emitters": emitters,
        }

    def _satcom_emissions(
        self, condition: ScenarioCondition, weather_field: dict[str, Any], scenario_time_ms: int
    ) -> dict[str, Any]:
        blos = condition.link_context in {"BLOS", "SATCOM_ONLY"}
        delay = self.rng.gauss(650 if blos else 90, 140 if blos else 25)
        rain_fade = clamp(weather_field["precipitation_level"] * 0.75 + self.rng.uniform(0, 0.12), 0, 1)
        availability = clamp(0.94 - rain_fade * 0.35 - (0.05 if condition.terrain == "MOUNTAIN" else 0), 0.35, 0.99)
        return {
            "link_windows": [
                {
                    "id": "satwin-01",
                    "satellite_hint": "BLOS-RELAY-A",
                    "uplink_or_downlink": "DOWNLINK",
                    "carrier_band": self.rng.choice(["Ku", "Ka", "X"]),
                    "propagation_delay_ms": round_float(clamp(delay, 40, 1400), 1),
                    "doppler_shift_hz": round_float(self.rng.gauss(120, 80), 1),
                    "rain_fade_score": round_float(rain_fade),
                    "availability_score": round_float(availability),
                }
            ],
            "frames": [
                {
                    "frame_id": "sat-frame-001",
                    "tx_time_ms": scenario_time_ms - int(clamp(delay, 40, 1400)),
                    "payload_ref": "payloads/sat_frame_001.bin",
                    "bearer_protocol_hint": "MAVLINK_TUNNEL",
                }
            ],
        }

    def _uav_c2_emissions(
        self, condition: ScenarioCondition, scenario_time_ms: int, satcom_emissions: dict[str, Any]
    ) -> dict[str, Any]:
        channel = "BLOS_SATCOM" if condition.link_context in {"BLOS", "SATCOM_ONLY"} else "LOS_RF"
        delay = satcom_emissions["link_windows"][0]["propagation_delay_ms"]
        frames = [
            self._mav_frame(
                "mav-heartbeat-001",
                scenario_time_ms - int(delay),
                "UAV",
                channel,
                "HEARTBEAT",
                0,
                1042,
                {"type": "MAV_TYPE_QUADROTOR", "autopilot": "MAV_AUTOPILOT_ARDUPILOTMEGA", "system_status": "MAV_STATE_ACTIVE"},
            ),
            self._mav_frame(
                "mav-gpsraw-001",
                scenario_time_ms - int(delay) + 80,
                "UAV",
                channel,
                "GPS_RAW_INT",
                24,
                1043,
                {
                    "fix_type": 3,
                    "satellites_visible": self.rng.randint(8, 14),
                    "eph": self.rng.randint(80, 240),
                    "epv": self.rng.randint(120, 320),
                },
            ),
            self._mav_frame(
                "mav-command-001",
                scenario_time_ms - int(delay) + 140,
                "GCS",
                channel,
                "COMMAND_LONG",
                76,
                1044,
                {"command": "MAV_CMD_NAV_CONTINUE_AND_CHANGE_ALT", "confirmation": 0},
            ),
        ]
        return {
            "default_reference_protocol": "MAVLink2_COMMON",
            "frames": frames,
        }

    def _mav_frame(
        self,
        emission_id: str,
        tx_time_ms: int,
        source_role: str,
        channel: str,
        message_name: str,
        message_id: int,
        sequence_number: int,
        decoded_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "emission_id": emission_id,
            "tx_time_ms": tx_time_ms,
            "source_role": source_role,
            "source_system_id": 1 if source_role == "UAV" else 255,
            "source_component_id": 1,
            "target_system_id": 255 if source_role == "UAV" else 1,
            "target_component_id": 0,
            "channel_hint": channel,
            "protocol": "MAVLINK2",
            "message_name": message_name,
            "message_id": message_id,
            "sequence_number": sequence_number,
            "payload_bytes_ref": f"payloads/{emission_id}.bin",
            "decoded_payload": decoded_payload,
            "checksum_or_crc_ok_at_emission": True,
            "signed": True,
            "signature_present": True,
            "link_rssi_dbm_at_reference": round_float(self.rng.gauss(-72, 6), 1),
        }

    def _ugv_relay_emissions(
        self, condition: ScenarioCondition, scenario_time_ms: int, center: tuple[float, float]
    ) -> dict[str, Any]:
        lat, lon = center
        return {
            "relay_beacons": [
                {
                    "emission_id": "ugv-beacon-001",
                    "node_id": "ugv-relay-01",
                    "tx_time_ms": scenario_time_ms - 60,
                    "center_freq_hz": 868_100_000,
                    "beacon_period_ms": 1000,
                    "rssi_dbm_at_reference": round_float(self.rng.gauss(-74, 5), 1),
                    "relay_role_hint": "MESH_NODE" if condition.link_context == "MESH" else "SATCOM_GATEWAY",
                    "source_location_truth": [round_float(lat - 0.01, 6), round_float(lon - 0.005, 6), 0],
                }
            ],
            "forwarded_frames": [
                {
                    "emission_id": "ugv-forward-001",
                    "original_frame_ref": "mav-heartbeat-001",
                    "relay_node_id": "ugv-relay-01",
                    "forward_time_ms": scenario_time_ms,
                    "channel_hint": "MESH" if condition.link_context == "MESH" else "SATCOM",
                }
            ],
        }

    def _remote_id_broadcasts(self, scenario_time_ms: int, physical_scene: dict[str, Any]) -> dict[str, Any]:
        broadcasts = []
        for obj in physical_scene["objects"]:
            if obj["object_type"] in {"FRIENDLY_UAV", "UNKNOWN_AIR"} and self.rng.random() < 0.45:
                broadcasts.append(
                    {
                        "id": f"rid-{obj['object_id']}",
                        "tx_time_ms": scenario_time_ms - self.rng.randint(0, 500),
                        "uas_id_type": "SERIAL_NUMBER",
                        "uas_id_hash_or_value": self._short_hash(obj["object_id"]),
                        "declared_location": obj["position_truth"],
                        "declared_velocity": obj["velocity_truth_mps"],
                        "declared_heading_deg": self.rng.randint(0, 359),
                        "emergency_status": None,
                    }
                )
        return {"broadcasts": broadcasts}

    def _adsb_broadcasts(self, scenario_time_ms: int) -> dict[str, Any]:
        if self.rng.random() > 0.20:
            return {"broadcasts": []}
        return {
            "broadcasts": [
                {
                    "id": "adsb-civil-01",
                    "tx_time_ms": scenario_time_ms - 300,
                    "icao_or_track_id": "7CFAKE",
                    "declared_position": [37.19, 127.21, 1400],
                    "declared_altitude_m": 1400,
                    "declared_velocity_mps": [55, -12, 0],
                }
            ]
        }

    def _physical_scene(
        self, condition: ScenarioCondition, center: tuple[float, float], rf_spectrum: dict[str, Any]
    ) -> dict[str, Any]:
        lat, lon = center
        objects = [
            {
                "object_id": "friendly-uav-01",
                "object_type": "FRIENDLY_UAV",
                "trajectory_ref": "traj/friendly_uav_01.csv",
                "position_truth": [round_float(lat + 0.004, 6), round_float(lon + 0.006, 6), 420],
                "velocity_truth_mps": [14.2, 3.1, 0.0],
                "visual_signature_score": 0.55,
                "thermal_signature_score": 0.62,
                "radar_cross_section_hint": 0.03,
                "rf_emission_refs": ["mav-heartbeat-001"],
            },
            {
                "object_id": "friendly-ugv-01",
                "object_type": "FRIENDLY_UGV",
                "trajectory_ref": "traj/friendly_ugv_01.csv",
                "position_truth": [round_float(lat - 0.010, 6), round_float(lon - 0.005, 6), 0],
                "velocity_truth_mps": [2.3, 0.4, 0.0],
                "visual_signature_score": 0.46,
                "thermal_signature_score": 0.51,
                "radar_cross_section_hint": 0.7,
                "rf_emission_refs": ["ugv-beacon-001"],
            },
        ]
        if rf_spectrum["emitters"]:
            objects.append(
                {
                    "object_id": "unknown-air-09",
                    "object_type": "UNKNOWN_AIR",
                    "trajectory_ref": "traj/unknown_air_09.csv",
                    "position_truth": rf_spectrum["emitters"][0]["source_location_truth"],
                    "velocity_truth_mps": [-12.0, 4.2, 0.0],
                    "visual_signature_score": 0.32,
                    "thermal_signature_score": 0.49,
                    "radar_cross_section_hint": 0.025,
                    "rf_emission_refs": [rf_spectrum["emitters"][0]["id"]],
                }
            )
        return {"objects": objects}

    def _eo_ir_scene(self, weather_field: dict[str, Any], terrain_field: dict[str, Any]) -> dict[str, Any]:
        visibility_score = clamp(weather_field["visibility_m"] / 10_000, 0, 1)
        return {
            "illumination_level": round_float(clamp(self.rng.gauss(0.65, 0.18), 0, 1)),
            "sun_angle_deg": round_float(self.rng.uniform(12, 60), 1),
            "obscurant_zones": [
                {
                    "id": "OBS-1",
                    "geometry_ref": "geojson/obscurant_01.geojson",
                    "obscurant_type": "FOG" if weather_field["fog_level"] > 0.35 else "DUST",
                    "severity": round_float(clamp((1 - visibility_score) * 0.8 + weather_field["fog_level"] * 0.2, 0, 1)),
                }
            ],
            "thermal_contrast_map_ref": "thermal/contrast_map_01.tif",
            "terrain_occlusion_link": terrain_field["occlusion_zones"][0]["id"],
        }

    def _reflection_field(self, terrain_field: dict[str, Any], physical_scene: dict[str, Any]) -> dict[str, Any]:
        return {
            "reflectivity_map_ref": "reflectivity/map_01.tif",
            "clutter_level": terrain_field["multipath_zones"][0]["severity"],
            "moving_reflectors": [
                {
                    "id": obj["object_id"],
                    "position_truth": obj["position_truth"],
                    "velocity_truth_mps": obj["velocity_truth_mps"],
                    "reflectivity_score": round_float(clamp((obj["radar_cross_section_hint"] or 0.1), 0, 1)),
                }
                for obj in physical_scene["objects"]
            ],
        }

    def _acoustic_thermal_field(self, physical_scene: dict[str, Any]) -> dict[str, Any]:
        acoustic = []
        thermal = []
        for obj in physical_scene["objects"]:
            if obj["object_type"] in {"FRIENDLY_UAV", "UNKNOWN_AIR"}:
                acoustic.append(
                    {
                        "id": f"aud-{obj['object_id']}",
                        "source_type": "ROTOR",
                        "location_truth": obj["position_truth"],
                        "spectral_hint": "rotor_harmonic",
                        "intensity_score": round_float(clamp(obj["visual_signature_score"] + 0.1, 0, 1)),
                    }
                )
            thermal.append(
                {
                    "id": f"thr-{obj['object_id']}",
                    "location_truth": obj["position_truth"],
                    "intensity_score": obj["thermal_signature_score"],
                }
            )
        return {"acoustic_sources": acoustic, "thermal_sources": thermal}

    def _interference_sources(self, condition: ScenarioCondition, center: tuple[float, float]) -> dict[str, Any]:
        sources = []
        if condition.enemy_presence in {"LIKELY", "CONFIRMED"}:
            lat, lon = center
            sources.append(
                {
                    "id": "int-gnss-01",
                    "source_type": self.rng.choice(["GNSS_JAMMER", "DECOY_EMITTER", "RF_JAMMER"]),
                    "affected_bands": ["GNSS_L1", "L_BAND"],
                    "location_truth": [
                        round_float(lat + self.rng.uniform(-0.015, 0.015), 6),
                        round_float(lon + self.rng.uniform(-0.015, 0.015), 6),
                        0,
                    ],
                    "active_window_ms": [175_000, 215_000],
                    "strength_score": round_float(clamp(self.rng.gauss(0.38, 0.13), 0, 1)),
                    "pattern": self.rng.choice(["BURSTY", "SWEEPING", "CONSTANT"]),
                }
            )
        return {"sources": sources}

    def _cyber_message_surface(self, scenario_time_ms: int, uav_c2_emissions: dict[str, Any]) -> dict[str, Any]:
        packets = []
        for frame in uav_c2_emissions["frames"]:
            packets.append(
                {
                    "packet_id": f"pkt-{frame['emission_id']}",
                    "tx_time_ms": frame["tx_time_ms"],
                    "medium": frame["channel_hint"],
                    "l2_hint": "CUSTOM_RADIO",
                    "l3_hint": "NONE",
                    "l4_hint": "NONE",
                    "src_addr": str(frame["source_system_id"]),
                    "dst_addr": str(frame["target_system_id"]),
                    "src_port": None,
                    "dst_port": None,
                    "app_protocol_hint": "MAVLINK",
                    "app_sequence": frame["sequence_number"],
                    "app_timestamp_ms": scenario_time_ms,
                    "payload_bytes_ref": frame["payload_bytes_ref"],
                    "decoded_summary": {
                        "message_name": frame["message_name"],
                        "signed": frame["signed"],
                        "signature_present": frame["signature_present"],
                    },
                }
            )
        return {"emitted_packets": packets}

    def _raw_capture_refs(self, sample_index: int) -> dict[str, Any]:
        return {
            "captures": [
                {
                    "id": f"sigmf-rfwin-915-{sample_index:04d}",
                    "artifact_type": "SIGMF_IQ",
                    "path_or_uri": f"captures/rfwin-915-{sample_index:04d}.sigmf-data",
                    "time_window_ms": [180_000, 185_000],
                    "notes": "Synthetic reference path for report and future replay.",
                },
                {
                    "id": f"mavlog-{sample_index:04d}",
                    "artifact_type": "MAVLINK_LOG",
                    "path_or_uri": f"logs/mavlink-{sample_index:04d}.tlog",
                    "time_window_ms": [180_000, 185_000],
                    "notes": "Synthetic MAVLink-like emission log reference.",
                },
            ]
        }

    def _scenario_truth_annotations(self, rf_spectrum: dict[str, Any]) -> dict[str, Any]:
        """Scenario labels for generator/scorer use, not Situation Tagger input."""
        labels = []
        for emitter in rf_spectrum["emitters"]:
            if emitter["id"] == "sig-17" and emitter.get("burst_period_ms"):
                labels.append(
                    {
                        "entity_ref": emitter["id"],
                        "truth_role": "enemy_uav_c2",
                        "visible_to_tagger": False,
                    }
                )
        return {"labels": labels}

    def _mission_priorities(self, condition: ScenarioCondition) -> list[float]:
        if condition.mission_phase in {"TARGET_OVERHEAD", "RECON_APPROACH"}:
            base = [0.82, 0.48, 0.36]
        else:
            base = [0.55, 0.52, 0.45]
        noise = [self.rng.uniform(-0.05, 0.05) for _ in base]
        values = [round_float(clamp(v + n, 0.05, 0.98)) for v, n in zip(base, noise)]
        return values

    def _area_center(self, area_id: str) -> tuple[float, float]:
        digest = hashlib.sha256(area_id.encode("utf-8")).digest()
        lat_offset = int.from_bytes(digest[:2], "big") / 65535 * 0.08 - 0.04
        lon_offset = int.from_bytes(digest[2:4], "big") / 65535 * 0.08 - 0.04
        return 37.112 + lat_offset, 127.104 + lon_offset

    def _stable_hash(self, value: Any) -> str:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _short_hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def generate_world(
    seed: int = 20260704,
    sample_index: int = 0,
    condition: ScenarioCondition | None = None,
) -> dict[str, Any]:
    generator = RuleBasedWorldGenerator(seed=seed)
    return generator.generate(condition or ScenarioCondition(), sample_index=sample_index)
