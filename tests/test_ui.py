import math

import cv2
import numpy as np

from obd_rs.ble_adapter import CommStats
from obd_rs.ble_adapter import ConnectionState, ConnectionStatus
from obd_rs.config import DataSource, LogMode
from obd_rs.logging_policy import LoggingPolicy
from obd_rs.models import Signal
from obd_rs.ui._diagnostics import _DiagnosticsPanel
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


def test_diagnostics_card_shows_stale_badge_with_last_known_value(monkeypatch) -> None:
    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    monkeypatch.setattr(cv2, "putText", _capture_text)
    frame = np.zeros((160, 240, 3), dtype=np.uint8)
    theme = {
        "panel_border": (68, 66, 64),
        "text_primary": (232, 232, 232),
        "text_dim": (174, 174, 174),
    }

    _DiagnosticsPanel._draw_card(
        frame=frame,
        rect=(8, 8, 120, 72),
        label="COOLANT",
        value=97.5,
        stale=True,
        supported=True,
        unit="C",
        caution=95.0,
        critical=112.0,
        theme=theme,
        low_is_caution=False,
    )

    assert "STALE" in texts
    assert any("97.5" in t for t in texts)


def test_diagnostics_card_shows_na_for_unsupported_signal(monkeypatch) -> None:
    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    monkeypatch.setattr(cv2, "putText", _capture_text)
    frame = np.zeros((160, 240, 3), dtype=np.uint8)
    theme = {
        "panel_border": (68, 66, 64),
        "text_primary": (232, 232, 232),
        "text_dim": (174, 174, 174),
    }

    _DiagnosticsPanel._draw_card(
        frame=frame,
        rect=(8, 8, 120, 72),
        label="OIL TEMP",
        value=None,
        stale=True,
        supported=False,
        unit="C",
        caution=110.0,
        critical=125.0,
        theme=theme,
        low_is_caution=False,
    )

    assert "N/A" in texts


def test_diagnostics_card_shows_live_badge_for_fresh_value(monkeypatch) -> None:
    texts: list[str] = []

    def _capture_text(_frame, text, *_args, **_kwargs):
        texts.append(text)
        return _frame

    monkeypatch.setattr(cv2, "putText", _capture_text)
    frame = np.zeros((160, 240, 3), dtype=np.uint8)
    theme = {
        "panel_border": (68, 66, 64),
        "text_primary": (232, 232, 232),
        "text_dim": (174, 174, 174),
    }

    _DiagnosticsPanel._draw_card(
        frame=frame,
        rect=(8, 8, 120, 72),
        label="COOLANT",
        value=85.0,
        stale=False,
        supported=True,
        unit="C",
        caution=95.0,
        critical=112.0,
        theme=theme,
        low_is_caution=False,
    )

    assert "LIVE" in texts
    assert "STALE" not in texts


def test_diagnostics_card_layout_avoids_header_and_value_overlap(monkeypatch) -> None:
    calls: list[dict] = []

    def _capture_text(_frame, text, org, font_face, font_scale, color, thickness, line_type):
        calls.append(
            {
                "text": text,
                "org": org,
                "font": font_face,
                "scale": font_scale,
                "thickness": thickness,
            }
        )
        return _frame

    monkeypatch.setattr(cv2, "putText", _capture_text)
    frame = np.zeros((160, 260, 3), dtype=np.uint8)
    theme = {
        "panel_border": (68, 66, 64),
        "text_primary": (232, 232, 232),
        "text_dim": (174, 174, 174),
    }

    _DiagnosticsPanel._draw_card(
        frame=frame,
        rect=(8, 8, 132, 76),
        label="COOLANT",
        value=97.5,
        stale=True,
        supported=True,
        unit="C",
        caution=95.0,
        critical=112.0,
        theme=theme,
        low_is_caution=False,
    )

    label_call = next(c for c in calls if c["text"] == "COOLANT")
    badge_call = next(c for c in calls if c["text"] == "STALE")
    value_call = next(c for c in calls if c["text"].startswith("97.5"))

    (label_w, label_h), _ = cv2.getTextSize(
        label_call["text"],
        label_call["font"],
        label_call["scale"],
        label_call["thickness"],
    )
    (badge_w, badge_h), _ = cv2.getTextSize(
        badge_call["text"],
        badge_call["font"],
        badge_call["scale"],
        badge_call["thickness"],
    )
    (value_w, value_h), _ = cv2.getTextSize(
        value_call["text"],
        value_call["font"],
        value_call["scale"],
        value_call["thickness"],
    )

    label_left = label_call["org"][0]
    badge_left = badge_call["org"][0]
    value_left = value_call["org"][0]

    # Horizontal placement: each row should be centered to avoid clipping.
    assert abs((label_left + (label_w / 2)) - (8 + (132 / 2))) <= 4
    assert abs((badge_left + (badge_w / 2)) - (8 + (132 / 2))) <= 4
    assert abs((value_left + (value_w / 2)) - (8 + (132 / 2))) <= 4

    label_top = label_call["org"][1] - label_h
    badge_top = badge_call["org"][1] - badge_h
    value_top = value_call["org"][1] - value_h

    # Vertical stack ordering with clear non-overlapping separation.
    assert badge_top >= label_call["org"][1] + 3
    assert value_top >= badge_call["org"][1] + 3

    # Ensure all text remains inside the card bounds.
    assert label_left >= 8
    assert badge_left >= 8
    assert value_left >= 8
    assert label_left + label_w <= 8 + 132
    assert badge_left + badge_w <= 8 + 132
    assert value_left + value_w <= 8 + 132
    assert label_top >= 8
    assert badge_top >= 8
    assert value_top >= 8
    assert value_call["org"][1] <= 8 + 76