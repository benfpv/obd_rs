"""Telemetry estimation helpers extracted from the UI layer."""

import math

import numpy as np

from .config import BRAKE_DECEL_SCALE, BRAKE_MIN_ACCEL_MS2, BRAKE_MIN_THROTTLE_DROP_PCT, BRAKE_THROTTLE_SCALE, MIN_RPM_FOR_TORQUE, POWER_MULTIPLIER

# rad/s → W → Nm conversion: T = P / ω = P / (rpm × 2π/60) = P × 60000 / (rpm × 2π)
_TORQUE_CONVERSION = 60_000.0 / (2.0 * math.pi)


def estimate_power_kw(rpm: float, engine_load: float) -> float:
    """Rough power estimate from RPM and load percentage."""
    return float(np.clip((rpm / 1000.0) * (engine_load / 100.0) * POWER_MULTIPLIER, 0.0, 900.0))


def estimate_torque_nm(power_kw: float, rpm: float) -> float:
    """Torque from power using P = T * omega."""
    return power_kw * _TORQUE_CONVERSION / max(MIN_RPM_FOR_TORQUE, rpm)


def estimate_accel_ms2(speed_kmh: float, prev_speed_kmh: float, dt: float) -> float:
    """Longitudinal acceleration from speed delta."""
    return ((speed_kmh - prev_speed_kmh) * (1000.0 / 3600.0)) / max(0.001, dt)


def infer_brake_pct(accel_ms2: float, throttle_drop: float) -> float:
    """Inferred brake percentage from deceleration and throttle release.
    
    Uses dead zones on both acceleration and throttle drop to filter sensor noise:
    - Only deceleration > BRAKE_MIN_ACCEL_MS2 is considered real braking
    - Only throttle drop > BRAKE_MIN_THROTTLE_DROP_PCT is considered brake intent
    """
    # Apply dead zone: only count deceleration above threshold
    significant_decel = max(0.0, -accel_ms2 - BRAKE_MIN_ACCEL_MS2)
    brake_from_decel = significant_decel * BRAKE_DECEL_SCALE
    
    # Apply throttle drop threshold to filter idle sensor noise
    significant_throttle_drop = max(0.0, throttle_drop - BRAKE_MIN_THROTTLE_DROP_PCT)
    brake_from_throttle_drop = significant_throttle_drop * BRAKE_THROTTLE_SCALE
    
    return float(np.clip(brake_from_decel + brake_from_throttle_drop, 0.0, 100.0))
