"""Tests for TelemetryProcessor stale-signal handling."""

from obd_rs.data_processing import TelemetryProcessor
from obd_rs.models import TelemetryState


def _fresh_state(**overrides) -> TelemetryState:
    s = TelemetryState()
    for k, v in overrides.items():
        sig = getattr(s, k)
        sig.value = v
        sig.stale = False
        sig.timestamp = 1.0
    return s


class TestStaleSignalGuard:
    def test_stale_rpm_produces_zero_power(self):
        proc = TelemetryProcessor()
        state = _fresh_state(rpm=3000.0, engine_load=50.0)
        state.rpm.stale = True
        derived = proc.process(state)
        assert derived.est_power_kw == 0.0
        assert derived.est_torque_nm == 0.0

    def test_stale_speed_does_not_update_accel(self):
        proc = TelemetryProcessor()
        # First tick with fresh data to prime the processor.
        state1 = _fresh_state(speed=60.0, throttle=20.0)
        state1.speed.timestamp = 1.0
        state1.throttle.timestamp = 1.0
        proc.process(state1)

        # Second tick with stale speed — accel should not be recalculated.
        state2 = _fresh_state(speed=80.0, throttle=20.0)
        state2.speed.stale = True
        state2.speed.timestamp = 2.0
        state2.throttle.timestamp = 2.0
        derived = proc.process(state2)
        # Accel stays at the value from the first transition (0 → 60).
        # It should NOT reflect 60 → 80 because speed is stale.
        assert derived.accel_ms2 == proc._held_accel

    def test_fresh_signals_produce_nonzero_derived(self):
        proc = TelemetryProcessor()
        state = _fresh_state(rpm=3000.0, engine_load=50.0, speed=60.0, throttle=30.0)
        derived = proc.process(state)
        assert derived.est_power_kw > 0.0
        assert derived.est_torque_nm > 0.0
