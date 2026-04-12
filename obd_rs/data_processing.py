from dataclasses import dataclass

import numpy as np

from .config import BRAKE_MIN_ACCEL_MS2, BRAKE_MIN_SPEED_KMH
from .models import TelemetryState
from .physics import estimate_accel_ms2, estimate_power_kw, estimate_torque_nm, infer_brake_pct


@dataclass
class DerivedTelemetry:
    est_power_kw: float
    est_torque_nm: float
    accel_ms2: float
    inferred_brake: float
    brake_plot_value: float
    brake_observable: bool


class TelemetryProcessor:
    """Centralized processing for derived telemetry used by UI and logger.

    This keeps all derivative calculations in one place so plotting and logging
    see exactly the same values.
    """

    def __init__(self) -> None:
        self._last_speed_sample_ts = 0.0
        self._last_speed_sample = 0.0
        self._last_throttle_sample_ts = 0.0
        self._last_throttle_sample = 0.0
        self._held_accel = 0.0
        self._held_brake = 0.0

    @staticmethod
    def _signal_value(value: float | None, low: float, high: float) -> float:
        if value is None:
            return 0.0
        return float(np.clip(value, low, high))

    def process(self, state: TelemetryState) -> DerivedTelemetry:
        rpm_val = state.rpm.value if not state.rpm.stale else None
        speed_val = state.speed.value if not state.speed.stale else None
        throttle_val = state.throttle.value if not state.throttle.stale else None
        load_val = state.engine_load.value if not state.engine_load.stale else None

        rpm = self._signal_value(rpm_val, 0.0, 9000.0)
        speed = self._signal_value(speed_val, 0.0, 320.0)
        throttle = self._signal_value(throttle_val, 0.0, 100.0)
        load = self._signal_value(load_val, 0.0, 100.0)

        speed_ts = state.speed.timestamp
        throttle_ts = state.throttle.timestamp
        speed_updated = speed_ts > self._last_speed_sample_ts and speed_val is not None
        throttle_updated = throttle_ts > self._last_throttle_sample_ts and throttle_val is not None

        if speed_updated:
            speed_dt = 0.2 if self._last_speed_sample_ts == 0.0 else max(0.05, speed_ts - self._last_speed_sample_ts)
            self._held_accel = estimate_accel_ms2(speed, self._last_speed_sample, speed_dt)

            throttle_drop = 0.0
            if throttle_updated:
                throttle_drop = max(0.0, self._last_throttle_sample - throttle)
                self._last_throttle_sample = throttle
                self._last_throttle_sample_ts = throttle_ts

            inferred_brake = infer_brake_pct(self._held_accel, throttle_drop)
            brake_observable = speed > BRAKE_MIN_SPEED_KMH or abs(self._held_accel) > BRAKE_MIN_ACCEL_MS2
            self._held_brake = float(inferred_brake) if brake_observable else 0.0

            self._last_speed_sample = speed
            self._last_speed_sample_ts = speed_ts
        elif throttle_updated:
            self._last_throttle_sample = throttle
            self._last_throttle_sample_ts = throttle_ts

        brake_observable = self._last_speed_sample_ts > 0.0
        brake_plot_value = self._held_brake if brake_observable else float("nan")

        est_power_kw = float(np.clip(estimate_power_kw(rpm, load), 0.0, 300.0))
        est_torque_nm = float(np.clip(estimate_torque_nm(est_power_kw, rpm), 0.0, 600.0))

        return DerivedTelemetry(
            est_power_kw=est_power_kw,
            est_torque_nm=est_torque_nm,
            accel_ms2=self._held_accel,
            inferred_brake=self._held_brake,
            brake_plot_value=brake_plot_value,
            brake_observable=brake_observable,
        )
