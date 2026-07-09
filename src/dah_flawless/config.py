"""Shared constants for the DAH Flawless MVP."""

DEFAULT_SEED = 42
DEFAULT_ROUNDS = 5
DEFAULT_EPISODES = 1
DEFAULT_STEPS_PER_EPISODE = 30
DEFAULT_BLUE_UPDATE_EPISODES = 10
DEFAULT_RED_UPDATE_EPISODES = 10
DEFAULT_EVAL_EPISODES = 3
DEFAULT_BLUE_READINESS_GATE_ENABLED = True
DEFAULT_BLUE_READINESS_THRESHOLD = 0.40
DEFAULT_BLUE_READINESS_MIN_SAMPLES = 10
DEFAULT_BLUE_READINESS_WINDOW = 20

CONFIDENCE_THRESHOLD = 0.60
DETECTION_WINDOW = 2
AVAIL_FLOOR = 0.50
RECOVERY_TARGET = 0.70
RECOVERY_WINDOW = 2
AVAILABILITY_RECOVERY_PER_ROUND = 0.10
TRUST_BUDGET_RECOVERY_PER_ROUND = 0.08
ACTIVE_DEFENSE_RECOVERY_PENALTY = 0.20
BLUE_MAINTENANCE_CYCLE_ROUNDS = 5
BLUE_MAINTENANCE_AVAILABILITY_BONUS = 0.06
BLUE_MAINTENANCE_TRUST_BONUS = 0.04
BLUE_MAX_AVAILABILITY_RECOVERY_PER_ROUND = 0.18
BLUE_MAX_TRUST_RECOVERY_PER_ROUND = 0.14

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

# Scenario types used by the simulator and replay selectors.
SCENARIOS = (
    "clean_start",
    "degraded_start",
    "satcom_delay",
    "gnss_degraded",
    "c2_metadata_noisy",
    "telemetry_conflict",
    "low_trust_start",
)
DEFAULT_SCENARIO = "clean_start"

# Red stealth modes: off = non-stealth mutation profile, on = always stealth,
# adaptive = switch an attack to stealth after it is detected.
# Default stays "off" so the baseline run uses the configured mutation profile;
# stealth is opt-in via --red-stealth on|adaptive.
STEALTH_MODES = ("off", "on", "adaptive")
DEFAULT_STEALTH_MODE = "off"

# Mutation profiles define the amplitude of safe simulator mutations.
# stealth is the low-amplitude boundary-probe profile, aggressive is the
# default report/training profile, and loud_demo keeps the old large demo values
# isolated from normal training.
MUTATION_PROFILES = ("stealth", "aggressive", "loud_demo")
DEFAULT_MUTATION_PROFILE = "aggressive"

# Contract-compatible tactic exploration keeps Red from collapsing to a single
# tactic while preserving the attack-effect contract boundary.
DEFAULT_TACTIC_EXPLORATION_RATE = 0.18

# Capability degradation lowers Blue detection confidence (paralysis model).
# A degraded cross-check / time-validation means Blue is less sure about the
# same invariant violation, so the same attack is harder to detect.
CAPABILITY_FACTORS = {"OK": 1.0, "DEGRADED": 0.75, "UNAVAILABLE": 0.5}
