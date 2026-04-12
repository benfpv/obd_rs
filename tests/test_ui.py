import math

import cv2
import numpy as np

from obd_rs.ble_adapter import CommStats
from obd_rs.ble_adapter import ConnectionState, ConnectionStatus
from obd_rs.config import DataSource, LogMode
from obd_rs.logging_policy import LoggingPolicy
from obd_rs.models import Signal
from obd_rs.ui import DashboardUI, _SystemPanel, _card_state, _fit_scale, _series_value


def test_series_value_returns_nan_for_absent_stale_or_unsupported_signal() -> None:
    assert math.isnan(_series_value(Signal(value=None, supported=True, stale=False)))
    assert math.isnan(_series_value(Signal(value=42.0, supported=True, stale=True)))
    assert math.isnan(_series_value(Signal(value=42.0, supported=False, stale=False)))
    assert _series_value(Signal(value=42.0, supported=True, stale=False)) == 42.0


def test_card_state_marks_low_voltage_as_caution() -> None:
    assert _card_state(12.0, False, 12.2, 14.8, low_is_caution=True) == "caution"
    assert _card_state(13.5, False, 12.2, 14.8, low_is_caution=True) == "normal"
    assert _card_state(15.0, False, 12.2, 14.8, low_is_caution=True) == "critical"


def test_card_state_for_temperature_remains_high_side_only() -> None:
    assert _card_state(85.0, False, 95.0, 110.0) == "normal"
    assert _card_state(100.0, False, 95.0, 110.0) == "caution"
    assert _card_state(115.0, False, 95.0, 110.0) == "critical"


def test_fit_scale_reduces_scale_when_text_would_overflow() -> None:
    original = 0.86
    reduced = _fit_scale("MODULE VOLTAGE", 40, cv2.FONT_HERSHEY_SIMPLEX, original, 1, 0.28)
    unchanged = _fit_scale("OK", 200, cv2.FONT_HERSHEY_SIMPLEX, original, 1, 0.28)

    assert reduced < original
    assert unchanged == original


def test_connection_overlay_hint_for_replay(monkeypatch) -> None:
    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    frame = np.zeros((120, 240, 3), dtype=np.uint8)
    conn = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="idle")

    monkeypatch.setattr(cv2, "putText", _capture_text)
    DashboardUI._draw_connection_overlay(object(), frame, conn, data_source=DataSource.REPLAY)

    assert "press Esc to exit" in texts


def test_connection_overlay_hint_for_live(monkeypatch) -> None:
    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    frame = np.zeros((120, 240, 3), dtype=np.uint8)
    conn = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="idle")

    monkeypatch.setattr(cv2, "putText", _capture_text)
    DashboardUI._draw_connection_overlay(object(), frame, conn, data_source=DataSource.LIVE)

    assert "will retry automatically" in texts


def test_connection_overlay_hint_for_simulated(monkeypatch) -> None:
    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    frame = np.zeros((120, 240, 3), dtype=np.uint8)
    conn = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="idle")

    monkeypatch.setattr(cv2, "putText", _capture_text)
    DashboardUI._draw_connection_overlay(object(), frame, conn, data_source=DataSource.SIMULATED)

    assert "starting up" in texts


def test_system_panel_renders_data_source_line(monkeypatch) -> None:
    panel = _SystemPanel()
    panel.update(
        conn=ConnectionStatus(state=ConnectionState.READY, device_name="REPLAY:test", detail="playing"),
        policy=LoggingPolicy(mode=LogMode.CRUISE),
        comm_stats=CommStats(),
        data_source=DataSource.REPLAY,
    )

    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    monkeypatch.setattr(cv2, "putText", _capture_text)
    frame = np.zeros((260, 420, 3), dtype=np.uint8)
    theme = {
        "text_dim": (174, 174, 174),
        "text_primary": (232, 232, 232),
        "system": (255, 193, 79),
        "panel_border": (68, 66, 64),
    }
    panel.draw(frame, (0, 0, 420, 260), theme)

    assert "Source" in texts
    assert "replay" in texts