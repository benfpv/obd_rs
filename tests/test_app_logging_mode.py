import pytest

from obd_rs.app import ObdDashboardApp
from obd_rs.ble_adapter import ConnectionState, ConnectionStatus
from obd_rs.config import DataSource
from obd_rs.data_processing import DerivedTelemetry
from obd_rs.providers.base import PlaybackCapable

_ZERO_DERIVED = DerivedTelemetry(est_power_kw=0.0, est_torque_nm=0.0, accel_ms2=0.0, inferred_brake=0.0, brake_plot_value=0.0, brake_observable=False)


def _ready_conn(name: str = "TEST") -> ConnectionStatus:
    return ConnectionStatus(state=ConnectionState.READY, device_name=name, detail="ready")


def test_simulated_mode_does_not_log_to_csv(monkeypatch: pytest.MonkeyPatch):
    app = ObdDashboardApp(mode=DataSource.SIMULATED)
    calls: list[object] = []

    monkeypatch.setattr(app.data_logger, "log", lambda sample: calls.append(sample))
    app._capture_sample(1.0, _ready_conn("SIMULATION"), _ZERO_DERIVED)

    assert calls == []
    app.data_logger.close()


def test_live_mode_logs_to_csv(monkeypatch: pytest.MonkeyPatch):
    app = ObdDashboardApp(mode=DataSource.LIVE)
    calls: list[object] = []
    app.telemetry.rpm.value = 2500.0

    monkeypatch.setattr(app.data_logger, "log", lambda sample: calls.append(sample))
    app._capture_sample(1.0, _ready_conn("VEEPEAK"), _ZERO_DERIVED)

    assert len(calls) == 1
    app.data_logger.close()


def test_live_mode_skips_log_when_disconnected(monkeypatch: pytest.MonkeyPatch):
    app = ObdDashboardApp(mode=DataSource.LIVE)
    calls: list[object] = []
    app.telemetry.rpm.value = 2500.0

    monkeypatch.setattr(app.data_logger, "log", lambda sample: calls.append(sample))
    app._capture_sample(1.0, ConnectionStatus(state=ConnectionState.DISCONNECTED, device_name="VEEPEAK", detail="lost"), _ZERO_DERIVED)

    assert calls == []
    app.data_logger.close()


def test_live_mode_skips_log_when_no_signals(monkeypatch: pytest.MonkeyPatch):
    app = ObdDashboardApp(mode=DataSource.LIVE)
    calls: list[object] = []

    monkeypatch.setattr(app.data_logger, "log", lambda sample: calls.append(sample))
    app._capture_sample(1.0, _ready_conn("VEEPEAK"), _ZERO_DERIVED)

    assert calls == []
    app.data_logger.close()


def test_simulated_provider_is_not_playback_capable():
    app = ObdDashboardApp(mode=DataSource.SIMULATED)
    assert not isinstance(app.provider, PlaybackCapable)
    app.data_logger.close()


def test_datasource_enum_values():
    assert DataSource.SIMULATED == "simulated"
    assert DataSource.LIVE == "live"
    assert DataSource.REPLAY == "replay"
    assert str(DataSource.REPLAY) == "replay"
