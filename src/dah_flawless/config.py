"""Shared constants for the DAH Flawless MVP."""

DEFAULT_SEED = 42
DEFAULT_ROUNDS = 5

CONFIDENCE_THRESHOLD = 0.60
DETECTION_WINDOW = 2
AVAIL_FLOOR = 0.50
RECOVERY_TARGET = 0.70
RECOVERY_WINDOW = 2
AVAILABILITY_RECOVERY_PER_ROUND = 0.10
TRUST_BUDGET_RECOVERY_PER_ROUND = 0.08
ACTIVE_DEFENSE_RECOVERY_PENALTY = 0.20

TELEMETRY_BATTERY_TOLERANCE = 5.0
GNSS_IMU_DRIFT_TOLERANCE_M = 45.0
LOW_CONFIDENCE_THRESHOLD = 0.72

TRUST_RECOVERY_PER_ROUND = 0.03
TRUST_PENALTY_FACTOR = 0.16
TRUST_RESTORE_BONUS = 0.04
TRUST_ESCALATION_THRESHOLD = 0.65
TRUSTED_RESTORE_DEGRADED_COST_MULTIPLIER = 1.5

BASE_TIMESTAMP = 1_710_001_200
ROUND_SECONDS = 60

SCRIPTED_ATTACKS = (
    "PRIORITY_POISONING",
    "TELEMETRY_FDI",
    "TIME_DESYNC_REPLAY",
)

# Scenario types (README section 3 / docs/HANDOFF.md).
SCENARIOS = ("clean_start", "degraded_start")
DEFAULT_SCENARIO = "clean_start"

# Red stealth modes: off = always loud, on = always stealth,
# adaptive = switch an attack to stealth after it is detected.
# Default stays "off" so the baseline run reproduces the original loud results;
# stealth is opt-in via --red-stealth on|adaptive.
STEALTH_MODES = ("off", "on", "adaptive")
DEFAULT_STEALTH_MODE = "off"

# Capability degradation lowers Blue detection confidence (paralysis model).
# A degraded cross-check / time-validation means Blue is less sure about the
# same invariant violation, so the same attack is harder to detect.
CAPABILITY_FACTORS = {"OK": 1.0, "DEGRADED": 0.75, "UNAVAILABLE": 0.5}
