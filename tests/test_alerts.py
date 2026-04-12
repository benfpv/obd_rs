"""Tests for AlertEngine persistence and thresholds."""

import time
from unittest.mock import patch

from obd_rs.alerts import AlertEngine
from obd_rs.models import Severity, Signal, TelemetryState


def _state(**overrides) -> TelemetryState:
    s = TelemetryState()
    for k, v in overrides.items():
        sig = getattr(s, k)
        sig.value = v
        sig.stale = False
    return s


class TestAlertThresholds:
    def test_no_alerts_on_normal_state(self):
        engine = AlertEngine()
        state = _state(coolant_temp=85.0, stft_b1=3.0, ltft_b1=2.0)
        engine.update_from_state(state, [], [])
        assert engine.issues() == []
        assert engine.possible_issues() == []

    def test_high_coolant_triggers_caution(self):
        engine = AlertEngine()
        state = _state(coolant_temp=115.0)
        engine.update_from_state(state, [], [])
        possible = engine.possible_issues()
        assert any(a.key == "thermal" for a in possible)
        assert all(a.severity == Severity.CAUTION for a in possible if a.key == "thermal")

    def test_active_dtc_creates_issue(self):
        engine = AlertEngine()
        state = _state()
        engine.update_from_state(state, ["P0301"], [])
        issues = engine.issues()
        assert len(issues) == 1
        assert "P0301" in issues[0].title

    def test_p03_prefix_is_critical(self):
        engine = AlertEngine()
        state = _state()
        engine.update_from_state(state, ["P0301"], [])
        assert engine.issues()[0].severity == Severity.CRITICAL

    def test_non_p03_dtc_is_caution(self):
        engine = AlertEngine()
        state = _state()
        engine.update_from_state(state, ["P0171"], [])
        assert engine.issues()[0].severity == Severity.CAUTION

    def test_pending_dtc_is_possible_issue(self):
        engine = AlertEngine()
        state = _state()
        engine.update_from_state(state, [], ["P0420"])
        assert len(engine.possible_issues()) == 1
        assert len(engine.issues()) == 0

    def test_stft_oscillation_alert(self):
        engine = AlertEngine()
        state = _state(stft_b1=18.0)
        engine.update_from_state(state, [], [])
        possible = engine.possible_issues()
        assert any(a.key == "stft" for a in possible)

    def test_ltft_drift_alert(self):
        engine = AlertEngine()
        state = _state(ltft_b1=-14.0)
        engine.update_from_state(state, [], [])
        possible = engine.possible_issues()
        assert any(a.key == "ltft" for a in possible)


class TestAlertPersistence:
    def test_first_seen_preserved_across_ticks(self):
        engine = AlertEngine()
        state = _state(coolant_temp=115.0)

        with patch("obd_rs.alerts.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            engine.update_from_state(state, [], [])
            first_seen = engine.possible_issues()[0].first_seen

            mock_time.monotonic.return_value = 1005.0
            engine.update_from_state(state, [], [])
            assert engine.possible_issues()[0].first_seen == first_seen
            assert engine.possible_issues()[0].last_seen == 1005.0

    def test_cleared_alert_resets_first_seen(self):
        engine = AlertEngine()

        with patch("obd_rs.alerts.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            engine.update_from_state(_state(coolant_temp=115.0), [], [])
            first_first_seen = engine.possible_issues()[0].first_seen

            mock_time.monotonic.return_value = 1002.0
            engine.update_from_state(_state(coolant_temp=85.0), [], [])
            assert engine.possible_issues() == []

            mock_time.monotonic.return_value = 1005.0
            engine.update_from_state(_state(coolant_temp=115.0), [], [])
            assert engine.possible_issues()[0].first_seen == 1005.0


class TestStaleSignalGuards:
    def test_stale_coolant_does_not_trigger_alert(self):
        engine = AlertEngine()
        s = TelemetryState()
        s.coolant_temp.value = 115.0
        s.coolant_temp.stale = True
        engine.update_from_state(s, [], [])
        assert engine.possible_issues() == []

    def test_stale_stft_does_not_trigger_alert(self):
        engine = AlertEngine()
        s = TelemetryState()
        s.stft_b1.value = 18.0
        s.stft_b1.stale = True
        engine.update_from_state(s, [], [])
        assert not any(a.key == "stft" for a in engine.possible_issues())

    def test_stale_ltft_does_not_trigger_alert(self):
        engine = AlertEngine()
        s = TelemetryState()
        s.ltft_b1.value = -14.0
        s.ltft_b1.stale = True
        engine.update_from_state(s, [], [])
        assert not any(a.key == "ltft" for a in engine.possible_issues())
