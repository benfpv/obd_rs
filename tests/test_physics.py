"""Tests for physics estimation helpers."""

from obd_rs.physics import (
    estimate_accel_ms2,
    estimate_power_kw,
    estimate_torque_nm,
    infer_brake_pct,
)


class TestEstimatePower:
    def test_zero_rpm_zero_power(self):
        assert estimate_power_kw(0.0, 50.0) == 0.0

    def test_zero_load_zero_power(self):
        assert estimate_power_kw(3000.0, 0.0) == 0.0

    def test_typical_values(self):
        # 3000 RPM, 50% load → 3.0 * 0.5 * 11.5 = 17.25 kW
        assert abs(estimate_power_kw(3000.0, 50.0) - 17.25) < 0.01

    def test_clamps_to_900(self):
        assert estimate_power_kw(100000.0, 100.0) == 900.0


class TestEstimateTorque:
    def test_typical_values(self):
        power = 17.25
        rpm = 3000.0
        torque = estimate_torque_nm(power, rpm)
        # T = P * 9549 / RPM = 17.25 * 9549 / 3000 ≈ 54.9
        assert abs(torque - 54.9) < 0.1

    def test_low_rpm_floor(self):
        # Should use 800 RPM floor, not 0
        torque = estimate_torque_nm(10.0, 0.0)
        expected = 10.0 * 9549.0 / 800.0
        assert abs(torque - expected) < 0.1


class TestEstimateAccel:
    def test_positive_acceleration(self):
        # 0 → 36 km/h in 1 second = 10 m/s²
        accel = estimate_accel_ms2(36.0, 0.0, 1.0)
        assert abs(accel - 10.0) < 0.01

    def test_deceleration(self):
        accel = estimate_accel_ms2(0.0, 36.0, 1.0)
        assert abs(accel - (-10.0)) < 0.01

    def test_zero_dt_clamped(self):
        # Should not raise ZeroDivisionError
        accel = estimate_accel_ms2(36.0, 0.0, 0.0)
        assert accel > 0


class TestInferBrake:
    def test_no_decel_no_brake(self):
        assert infer_brake_pct(0.0, 0.0) == 0.0

    def test_deceleration_infers_brake(self):
        pct = infer_brake_pct(-5.0, 0.0)
        assert pct > 0.0

    def test_throttle_drop_adds_brake(self):
        pct = infer_brake_pct(0.0, 50.0)
        assert pct > 0.0

    def test_clamps_to_100(self):
        pct = infer_brake_pct(-100.0, 200.0)
        assert pct == 100.0
