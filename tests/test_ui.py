import math

import cv2
import numpy as np
import pytest

from obd_rs.ble_adapter import CommStats
from obd_rs.ble_adapter import ConnectionState, ConnectionStatus
from obd_rs.config import DataSource, LogMode
from obd_rs.logging_policy import LoggingPolicy
from obd_rs.models import Signal
from obd_rs.ui._diagnostics import _DiagnosticsPanel
from obd_rs.ui import DashboardUI, _SystemPanel, _card_state, _fit_scale, _series_value
from obd_rs.ui import (
    THEME_KEYS,
    PanelContract,
    assert_panel_theme_compatible,
    validate_theme,
)
from obd_rs.ui._alerts_panel import _AlertsPanel
from obd_rs.ui._engine import _EnginePowerPanel
from obd_rs.ui._fuel_trims import _FuelTrimsPanel
from obd_rs.ui._racing import _RacingInputsPanel
from obd_rs.ui._text import STYLES, TextStyle, draw_text, fit_text_to


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


# ---------------------------------------------------------------------------
# Phase 1: panel/theme contract tests
# ---------------------------------------------------------------------------

ALL_PANEL_CLASSES = [
    _DiagnosticsPanel,
    _RacingInputsPanel,
    _EnginePowerPanel,
    _AlertsPanel,
    _SystemPanel,
    _FuelTrimsPanel,
]


@pytest.mark.parametrize("panel_cls", ALL_PANEL_CLASSES)
def test_every_panel_declares_required_theme_keys(panel_cls) -> None:
    keys = panel_cls.required_theme_keys()
    assert isinstance(keys, frozenset)
    assert keys, f"{panel_cls.__name__} declared an empty theme key set"
    unknown = keys - THEME_KEYS
    assert not unknown, (
        f"{panel_cls.__name__} declares unknown theme keys: {sorted(unknown)}"
    )


@pytest.mark.parametrize("panel_cls", ALL_PANEL_CLASSES)
def test_every_panel_satisfies_panel_contract_protocol(panel_cls) -> None:
    if panel_cls in (_DiagnosticsPanel, _RacingInputsPanel, _EnginePowerPanel, _FuelTrimsPanel):
        panel = panel_cls(64)
    else:
        panel = panel_cls()

    # Validate structural protocol compliance using real panel objects.
    assert isinstance(panel, PanelContract)

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    rect = (0, 0, 320, 240)
    theme = {key: (128, 128, 128) for key in THEME_KEYS}

    if panel_cls is _SystemPanel:
        panel.update(
            conn=ConnectionStatus(state=ConnectionState.READY, device_name="SIM", detail="ok"),
            policy=LoggingPolicy(mode=LogMode.REALTIME),
            comm_stats=CommStats(),
            data_source=DataSource.SIMULATED,
        )
    elif panel_cls is _AlertsPanel:
        panel.update([])
    else:
        from obd_rs.models import TelemetryState

        panel.update(TelemetryState(), None)

    panel.draw(frame, rect, theme)


def _patch_cv2_windowing(monkeypatch) -> None:
    monkeypatch.setattr(cv2, "namedWindow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "resizeWindow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "moveWindow", lambda *_a, **_kw: None)


def test_dashboard_theme_satisfies_every_panel_contract(monkeypatch) -> None:
    _patch_cv2_windowing(monkeypatch)
    dashboard = DashboardUI()
    for panel_cls in ALL_PANEL_CLASSES:
        assert_panel_theme_compatible(dashboard._theme, panel_cls)


def test_dashboard_theme_provides_every_canonical_key(monkeypatch) -> None:
    _patch_cv2_windowing(monkeypatch)
    dashboard = DashboardUI()
    missing = THEME_KEYS - set(dashboard._theme.keys())
    assert not missing, f"Dashboard theme missing canonical keys: {sorted(missing)}"
    validate_theme(dashboard._theme, THEME_KEYS)


def test_validate_theme_raises_for_missing_keys() -> None:
    with pytest.raises(KeyError):
        validate_theme({"text_primary": (0, 0, 0)}, {"text_primary", "text_dim"})


def test_validate_theme_raises_for_invalid_color_value() -> None:
    with pytest.raises(ValueError):
        validate_theme({"text_primary": (0, 0, 999)}, {"text_primary"})
    with pytest.raises(ValueError):
        validate_theme({"text_primary": "not-a-color"}, {"text_primary"})
    with pytest.raises(ValueError):
        validate_theme({"text_primary": (0, 0)}, {"text_primary"})


def test_assert_panel_theme_compatible_names_panel_in_error() -> None:
    bad_theme = {key: (0, 0, 0) for key in THEME_KEYS if key != "text_primary"}
    with pytest.raises(KeyError) as exc_info:
        assert_panel_theme_compatible(bad_theme, _DiagnosticsPanel)
    assert "_DiagnosticsPanel" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Phase 0/1: dashboard lifecycle baseline
# ---------------------------------------------------------------------------

def _build_simulated_telemetry():
    from obd_rs.models import TelemetryState

    state = TelemetryState()
    fresh = {
        "rpm": 3200.0,
        "speed": 90.0,
        "throttle": 35.0,
        "engine_load": 45.0,
        "coolant_temp": 88.0,
        "intake_temp": 28.0,
        "stft_b1": 0.5,
        "ltft_b1": -1.2,
        "spark_advance": 12.0,
        "module_voltage": 14.1,
    }
    for attr, val in fresh.items():
        sig = getattr(state, attr)
        sig.value = val
        sig.stale = False
        sig.supported = True
        sig.confidence = 1.0
    return state


def test_dashboard_full_draw_lifecycle_is_exception_free(monkeypatch) -> None:
    """Baseline: drive DashboardUI.draw() once with realistic data, headlessly."""
    _patch_cv2_windowing(monkeypatch)
    monkeypatch.setattr(cv2, "imshow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *_a, **_kw: 0)

    from obd_rs.data_logger import LoggerStatus

    dashboard = DashboardUI()
    telemetry = _build_simulated_telemetry()
    conn = ConnectionStatus(state=ConnectionState.READY, device_name="SIM", detail="ok")
    policy = LoggingPolicy(mode=LogMode.REALTIME)
    logger_status = LoggerStatus(
        active=True,
        session_name="test",
        rows_written=0,
        rows_pending_flush=0,
        retention_pruned=0,
        collision_avoided=False,
    )

    keep_running = dashboard.draw(
        telemetry=telemetry,
        derived=None,
        issues=[],
        possible=[],
        conn=conn,
        policy=policy,
        logger_status=logger_status,
        comm_stats=None,
        data_source=DataSource.SIMULATED,
        on_key=None,
        logging_enabled=True,
    )
    assert keep_running is True


# ---------------------------------------------------------------------------
# Phase 2: text style registry
# ---------------------------------------------------------------------------

CANONICAL_STYLE_NAMES = ("header", "section", "value", "detail", "caption")


@pytest.mark.parametrize("name", CANONICAL_STYLE_NAMES)
def test_canonical_text_styles_are_well_formed(name) -> None:
    style = getattr(STYLES, name)
    assert isinstance(style, TextStyle)
    # OpenCV font enums are small non-negative ints; bound them defensively.
    assert isinstance(style.font, int) and 0 <= style.font <= 16
    # Scale must be positive and within a sane drawing range.
    assert 0.1 <= style.scale <= 4.0
    assert isinstance(style.thickness, int) and 1 <= style.thickness <= 4


def test_text_style_is_frozen_and_hashable() -> None:
    style = TextStyle(cv2.FONT_HERSHEY_SIMPLEX, 0.5)
    with pytest.raises(AttributeError):
        style.scale = 1.0  # type: ignore[misc]
    # Hashable so it can be used as a dict key / set member.
    assert hash(style) == hash(TextStyle(cv2.FONT_HERSHEY_SIMPLEX, 0.5))


def test_text_style_measure_matches_cv2_get_text_size() -> None:
    style = STYLES.value
    text = "RPM 3200"
    expected, _ = cv2.getTextSize(text, style.font, style.scale, style.thickness)
    assert style.measure(text) == (int(expected[0]), int(expected[1]))


def test_draw_text_writes_with_anti_aliasing(monkeypatch) -> None:
    captured: dict = {}

    def fake_put(frame, text, org, font, scale, color, thickness, line):
        captured.update(
            text=text, org=org, font=font, scale=scale,
            color=color, thickness=thickness, line=line,
        )

    monkeypatch.setattr(cv2, "putText", fake_put)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    draw_text(frame, "hi", (1, 2), (10, 20, 30), STYLES.detail)

    assert captured["text"] == "hi"
    assert captured["org"] == (1, 2)
    assert captured["font"] == STYLES.detail.font
    assert captured["scale"] == STYLES.detail.scale
    assert captured["color"] == (10, 20, 30)
    assert captured["thickness"] == STYLES.detail.thickness
    assert captured["line"] == cv2.LINE_AA


def test_fit_text_to_truncates_with_ellipsis_when_too_wide() -> None:
    style = STYLES.caption
    full = "x" * 200
    fitted = fit_text_to(full, max_px=20, style=style)
    assert fitted != full
    assert fitted.endswith("...") or fitted == ""
    w, _ = style.measure(fitted)
    assert w <= 20 or fitted == "..."


def test_fit_text_to_returns_original_when_already_fits() -> None:
    fitted = fit_text_to("ok", max_px=400, style=STYLES.caption)
    assert fitted == "ok"


# ---------------------------------------------------------------------------
# Phase 6: bounded-layout & lifecycle hardening
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frame_size", [(800, 600), (1280, 720), (1920, 1080)])
def test_dashboard_draw_lifecycle_at_multiple_frame_sizes(monkeypatch, frame_size) -> None:
    """DashboardUI must render and produce bounded, non-overlapping panel rects."""
    _patch_cv2_windowing(monkeypatch)
    monkeypatch.setattr(cv2, "imshow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *_a, **_kw: 0)
    monkeypatch.setattr(cv2, "resize", lambda img, _size: img)
    text_calls: list[tuple[str, int, int]] = []

    def _capture_text(_frame, text, org, *_args, **_kwargs):
        text_calls.append((str(text), int(org[0]), int(org[1])))
        return _frame

    monkeypatch.setattr(cv2, "putText", _capture_text)

    from obd_rs.data_logger import LoggerStatus

    dashboard = DashboardUI()
    width, height = frame_size
    # Override the dashboard's canvas size so each panel is forced to layout
    # against the requested resolution rather than the default.
    dashboard._w = width  # noqa: SLF001 - intentional test-only injection
    dashboard._h = height  # noqa: SLF001

    telemetry = _build_simulated_telemetry()
    conn = ConnectionStatus(state=ConnectionState.READY, device_name="SIM", detail="ok")
    policy = LoggingPolicy(mode=LogMode.REALTIME)
    logger_status = LoggerStatus(
        active=True, session_name="t", rows_written=0,
        rows_pending_flush=0, retention_pruned=0, collision_avoided=False,
    )

    keep_running = dashboard.draw(
        telemetry=telemetry, derived=None, issues=[], possible=[],
        conn=conn, policy=policy, logger_status=logger_status,
        comm_stats=None, data_source=DataSource.SIMULATED,
        on_key=None, logging_enabled=True,
    )
    assert keep_running is True

    panels = dashboard._layout(width, height)  # noqa: SLF001 - intentional test-only assertion

    # Every panel must be fully within the frame and have positive area.
    for _name, (x, y, w, h) in panels.items():
        assert w > 0 and h > 0
        assert x >= 0 and y >= 0
        assert x + w <= width
        assert y + h <= height

    # No panel rectangles should overlap each other.
    rects = list(panels.values())
    for i, (ax, ay, aw, ah) in enumerate(rects):
        for bx, by, bw, bh in rects[i + 1:]:
            overlap = (ax < bx + bw) and (bx < ax + aw) and (ay < by + bh) and (by < ay + ah)
            assert not overlap

    # UX-critical dashboard labels should always stay inside the frame.
    dashboard_labels = {
        "DIAGNOSTICS",
        "INPUTS",
        "ENGINE / POWER",
        "ALERTS",
        "SYSTEM",
        "FUEL TRIMS & EXTENDED",
        "RACE DASH READY",
    }
    label_calls = [(txt, tx, ty) for txt, tx, ty in text_calls if txt in dashboard_labels]
    assert {txt for txt, _x, _y in label_calls} == dashboard_labels
    for _txt, tx, ty in label_calls:
        assert 0 <= tx < width
        assert 0 <= ty < height


def _build_stale_telemetry():
    state = _build_simulated_telemetry()
    # Mark every signal stale to exercise the "last-known but stale" code paths.
    for attr in ("rpm", "speed", "throttle", "engine_load", "coolant_temp",
                 "intake_temp", "stft_b1", "ltft_b1", "spark_advance",
                 "module_voltage"):
        getattr(state, attr).stale = True
    return state


def _build_unsupported_telemetry():
    from obd_rs.models import TelemetryState

    state = TelemetryState()
    # All fields default to unsupported / no value – matches the cold-start
    # case where no PIDs have been confirmed yet.
    return state


def test_dashboard_draw_with_stale_telemetry_is_exception_free(monkeypatch) -> None:
    _patch_cv2_windowing(monkeypatch)
    monkeypatch.setattr(cv2, "imshow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *_a, **_kw: 0)

    from obd_rs.data_logger import LoggerStatus

    dashboard = DashboardUI()
    conn = ConnectionStatus(state=ConnectionState.READY, device_name="SIM", detail="stale")
    policy = LoggingPolicy(mode=LogMode.REALTIME)
    logger_status = LoggerStatus(
        active=True, session_name="t", rows_written=0,
        rows_pending_flush=0, retention_pruned=0, collision_avoided=False,
    )

    assert dashboard.draw(
        telemetry=_build_stale_telemetry(), derived=None, issues=[], possible=[],
        conn=conn, policy=policy, logger_status=logger_status,
        comm_stats=None, data_source=DataSource.SIMULATED,
        on_key=None, logging_enabled=True,
    ) is True


def test_dashboard_draw_with_unsupported_telemetry_is_exception_free(monkeypatch) -> None:
    _patch_cv2_windowing(monkeypatch)
    monkeypatch.setattr(cv2, "imshow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *_a, **_kw: 0)

    from obd_rs.data_logger import LoggerStatus

    dashboard = DashboardUI()
    conn = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="cold start")
    policy = LoggingPolicy(mode=LogMode.REALTIME)
    logger_status = LoggerStatus(
        active=False, session_name="", rows_written=0,
        rows_pending_flush=0, retention_pruned=0, collision_avoided=False,
    )

    assert dashboard.draw(
        telemetry=_build_unsupported_telemetry(), derived=None, issues=[], possible=[],
        conn=conn, policy=policy, logger_status=logger_status,
        comm_stats=None, data_source=DataSource.SIMULATED,
        on_key=None, logging_enabled=False,
    ) is True


def test_dashboard_draw_with_logger_error_does_not_crash(monkeypatch) -> None:
    """Logger error must surface in the indicator strip without blowing up."""
    _patch_cv2_windowing(monkeypatch)
    monkeypatch.setattr(cv2, "imshow", lambda *_a, **_kw: None)
    monkeypatch.setattr(cv2, "waitKey", lambda *_a, **_kw: 0)

    from obd_rs.data_logger import LoggerStatus

    dashboard = DashboardUI()
    conn = ConnectionStatus(state=ConnectionState.READY, device_name="SIM", detail="ok")
    policy = LoggingPolicy(mode=LogMode.REALTIME)
    logger_status = LoggerStatus(
        active=False, session_name="t", rows_written=0,
        rows_pending_flush=0, retention_pruned=0, collision_avoided=False,
        last_error="disk full: /var is at 100%",
    )

    assert dashboard.draw(
        telemetry=_build_simulated_telemetry(), derived=None, issues=[], possible=[],
        conn=conn, policy=policy, logger_status=logger_status,
        comm_stats=None, data_source=DataSource.SIMULATED,
        on_key=None, logging_enabled=True,
    ) is True


def test_alerts_panel_draws_active_alerts_without_crash() -> None:
    from obd_rs.models import AlertEvent, Severity

    panel = _AlertsPanel()
    panel.update([
        AlertEvent(key="coolant", title="Coolant", detail="98 C rising",
                   severity=Severity.CAUTION, source="test"),
        AlertEvent(key="knock", title="Knock", detail="repeated retard",
                   severity=Severity.CRITICAL, source="test"),
        AlertEvent(key="voltage", title="Voltage", detail="12.1 V",
                   severity=Severity.INFO, source="test"),
    ])
    frame = np.zeros((400, 600, 3), dtype=np.uint8)
    theme = {key: (200, 200, 200) for key in THEME_KEYS}
    panel.draw(frame, (0, 0, 600, 400), theme)
    # Some non-zero pixels must exist (alerts were drawn).
    assert int(frame.sum()) > 0
