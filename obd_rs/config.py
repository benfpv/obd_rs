import os
from dataclasses import dataclass
from enum import Enum


class LogMode(str, Enum):
    REALTIME = "realtime"
    CRUISE = "cruise"


class DataSource(str, Enum):
    SIMULATED = "simulated"
    LIVE = "live"
    REPLAY = "replay"

    def __str__(self) -> str:
        return self.value


class PollProfile(str, Enum):
    CORE = "core"
    BALANCED = "balanced"
    FULL = "full"


@dataclass(frozen=True)
class PollCadence:
    high_hz: float
    medium_hz: float
    low_hz: float
    extended_hz: float


def _env_true(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


# ---------------------------------------------------------------------------
# Window / display
# ---------------------------------------------------------------------------

WINDOW_NAME = os.environ.get("OBD_RS_WINDOW_NAME", "obd_rs")
WINDOW_MIN_SIZE = (800, 600)


def _clamp_window_size(width: int, height: int) -> tuple[int, int]:
    """Clamp configured window size to a minimum usable dashboard footprint."""
    min_w, min_h = WINDOW_MIN_SIZE
    return (max(min_w, width), max(min_h, height))


WINDOW_SIZE = _clamp_window_size(_env_int("OBD_RS_WINDOW_W", 1200), _env_int("OBD_RS_WINDOW_H", 760))
FPS = _env_int("OBD_RS_FPS", 20)

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------

# Use "simulated" for UI development and "live" for real adapter polling.
DATA_SOURCE = os.environ.get("OBD_RS_DATA_SOURCE", "")
REPLAY_FILE = os.environ.get("OBD_RS_REPLAY_FILE", "")

# ---------------------------------------------------------------------------
# BLE adapter
# ---------------------------------------------------------------------------

VEEPEAK_NAME_HINTS = [
    s.strip()
    for s in os.environ.get("OBD_RS_NAME_HINTS", "VEEPEAK,OBD,OBDII,ELM327").split(",")
    if s.strip()
]

MINIMAL_WRITES = _env_true("OBD_RS_MINIMAL_WRITES", "1")
MIN_WRITE_INTERVAL_S = _env_float("OBD_RS_MIN_WRITE_INTERVAL_S", 0.08)

# BLE connection / reconnect timing
BLE_SCAN_TIMEOUT_S = _env_float("OBD_RS_BLE_SCAN_TIMEOUT_S", 5.0)
BLE_NOTIFY_TIMEOUT_S = _env_float("OBD_RS_BLE_NOTIFY_TIMEOUT_S", 8.0)
BLE_NOTIFY_RETRY_TIMEOUT_S = _env_float("OBD_RS_BLE_NOTIFY_RETRY_TIMEOUT_S", 5.0)
BLE_RESPONSE_CHUNK_TIMEOUT_S = _env_float("OBD_RS_BLE_RESPONSE_CHUNK_TIMEOUT_S", 0.06)
MAX_RECONNECT_ATTEMPTS = _env_int("OBD_RS_MAX_RECONNECT_ATTEMPTS", 3)
RECONNECT_DELAY_S = _env_float("OBD_RS_RECONNECT_DELAY_S", 2.0)

# ---------------------------------------------------------------------------
# Poll cadence
# ---------------------------------------------------------------------------

# BLE ELM327 readers have limited command throughput, so cadence values are
# profile-based. "balanced" is the default for smooth core gauges while still
# refreshing diagnostics and extended telemetry.
_POLL_PROFILE_RAW = os.environ.get("OBD_RS_POLL_PROFILE", PollProfile.BALANCED.value).strip().lower()
try:
    POLL_PROFILE = PollProfile(_POLL_PROFILE_RAW)
except ValueError:
    POLL_PROFILE = PollProfile.BALANCED

_PROFILE_CADENCE: dict[PollProfile, dict[LogMode, PollCadence]] = {
    PollProfile.CORE: {
        LogMode.REALTIME: PollCadence(high_hz=3.0, medium_hz=0.25, low_hz=0.02, extended_hz=0.01),
        LogMode.CRUISE: PollCadence(high_hz=1.0, medium_hz=0.10, low_hz=0.01, extended_hz=0.01),
    },
    PollProfile.BALANCED: {
        LogMode.REALTIME: PollCadence(high_hz=2.8, medium_hz=0.50, low_hz=0.10, extended_hz=0.08),
        LogMode.CRUISE: PollCadence(high_hz=1.0, medium_hz=0.20, low_hz=0.03, extended_hz=0.02),
    },
    PollProfile.FULL: {
        LogMode.REALTIME: PollCadence(high_hz=3.0, medium_hz=0.60, low_hz=0.12, extended_hz=0.08),
        LogMode.CRUISE: PollCadence(high_hz=1.2, medium_hz=0.30, low_hz=0.05, extended_hz=0.03),
    },
}

LOG_MODE_CADENCE = _PROFILE_CADENCE[POLL_PROFILE]

# ---------------------------------------------------------------------------
# App loop timing
# ---------------------------------------------------------------------------

RECONNECT_INTERVAL_S = _env_float("OBD_RS_RECONNECT_INTERVAL_S", 10.0)
DTC_READ_INTERVAL_S = _env_float("OBD_RS_DTC_READ_INTERVAL_S", 5.0)
SIGNAL_STALE_AGE_S = _env_float("OBD_RS_SIGNAL_STALE_AGE_S", 2.0)

# ---------------------------------------------------------------------------
# UI / dashboard
# ---------------------------------------------------------------------------

RPM_REDLINE = _env_int("OBD_RS_RPM_REDLINE", 8000)
G_METER_RANGE = _env_float("OBD_RS_G_RANGE", 0.8)
HISTORY_BUFFER_SIZE = _env_int("OBD_RS_HISTORY_BUFFER_SIZE", 260)

# Diagnostic card thresholds (caution, critical)
DIAG_COOLANT_CAUTION_C = _env_float("OBD_RS_DIAG_COOLANT_CAUTION_C", 95.0)
DIAG_COOLANT_CRITICAL_C = _env_float("OBD_RS_DIAG_COOLANT_CRITICAL_C", 112.0)
DIAG_VOLTAGE_LOW_V = _env_float("OBD_RS_DIAG_VOLTAGE_LOW_V", 12.2)
DIAG_VOLTAGE_HIGH_V = _env_float("OBD_RS_DIAG_VOLTAGE_HIGH_V", 14.8)

# Plot thresholds (trigger lines on sparklines)
SPEED_ALERT_KMH = _env_float("OBD_RS_SPEED_ALERT_KMH", 120.0)
THROTTLE_HIGH_PCT = _env_float("OBD_RS_THROTTLE_HIGH_PCT", 70.0)

# Brake inference observable thresholds
BRAKE_MIN_SPEED_KMH = _env_float("OBD_RS_BRAKE_MIN_SPEED_KMH", 2.0)
BRAKE_MIN_ACCEL_MS2 = _env_float("OBD_RS_BRAKE_MIN_ACCEL_MS2", 0.35)

# ---------------------------------------------------------------------------
# Alert thresholds
# ---------------------------------------------------------------------------

COOLANT_CAUTION_C = _env_float("OBD_RS_COOLANT_CAUTION_C", 110.0)
STFT_ALERT_PCT = _env_float("OBD_RS_STFT_ALERT_PCT", 15.0)
LTFT_ALERT_PCT = _env_float("OBD_RS_LTFT_ALERT_PCT", 12.0)
# DTC prefixes that indicate critical (rather than caution) severity.
CRITICAL_DTC_PREFIXES = set(
    os.environ.get("OBD_RS_CRITICAL_DTC_PREFIXES", "P03").split(",")
)

# ---------------------------------------------------------------------------
# Physics estimation constants
# ---------------------------------------------------------------------------

# Rough power estimate: (rpm / 1000) * (load / 100) * POWER_MULTIPLIER → kW
POWER_MULTIPLIER = _env_float("OBD_RS_POWER_MULTIPLIER", 11.5)
# Minimum RPM floor for torque calculation (avoids division by near-zero)
MIN_RPM_FOR_TORQUE = _env_float("OBD_RS_MIN_RPM_FOR_TORQUE", 800.0)
# Brake inference from deceleration: -accel_m_s2 * BRAKE_DECEL_SCALE → pct
BRAKE_DECEL_SCALE = _env_float("OBD_RS_BRAKE_DECEL_SCALE", 18.0)
# Contribution of throttle drop to inferred brake percentage
BRAKE_THROTTLE_SCALE = _env_float("OBD_RS_BRAKE_THROTTLE_SCALE", 0.5)
# Minimum throttle drop to avoid sensor noise at idle
BRAKE_MIN_THROTTLE_DROP_PCT = _env_float("OBD_RS_BRAKE_MIN_THROTTLE_DROP_PCT", 0.5)

# ---------------------------------------------------------------------------
# Startup UI
# ---------------------------------------------------------------------------

AUTO_SELECT_DELAY_S = _env_float("OBD_RS_AUTO_SELECT_DELAY_S", 2.0)
DEVICE_SCORE_HINT_MATCH = _env_int("OBD_RS_DEVICE_SCORE_HINT_MATCH", 10)
DEVICE_SCORE_PREFIX_BONUS = _env_int("OBD_RS_DEVICE_SCORE_PREFIX_BONUS", 5)

# ---------------------------------------------------------------------------
# Logging / telemetry persistence
# ---------------------------------------------------------------------------

LOG_DIR = os.environ.get("OBD_RS_LOG_DIR", "logs")
LOG_MAX_BYTES = _env_int("OBD_RS_LOG_MAX_BYTES", 10 * 1024 * 1024)
LOG_FLUSH_ROWS = _env_int("OBD_RS_LOG_FLUSH_ROWS", 100)
LOG_FLUSH_INTERVAL_S = _env_float("OBD_RS_LOG_FLUSH_INTERVAL_S", 5.0)
LOG_MIN_SIGNAL_FIELDS = _env_int("OBD_RS_LOG_MIN_SIGNAL_FIELDS", 1)


