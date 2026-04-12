"""Diagnostics panel – Coolant / Oil Temp / Intake / Voltage cards + trends."""

from collections import deque
from typing import Optional

import cv2
import numpy as np

from ..config import (
    DIAG_COOLANT_CAUTION_C,
    DIAG_COOLANT_CRITICAL_C,
    DIAG_VOLTAGE_HIGH_V,
    DIAG_VOLTAGE_LOW_V,
)
from ..data_processing import DerivedTelemetry
from ..models import Signal, TelemetryState
from ._helpers import (
    _card_state,
    _content_rect,
    _fit_scale,
    _fit_text,
    _plot_series,
    _series_value,
)


class _DiagnosticsPanel:
    """Diagnostic cards (Coolant / Oil Temp / Intake / Voltage) + 4 trend charts.

    _CARDS and _CHARTS are the single source of truth for what signals this
    panel tracks.  Adding or removing a signal only requires changing those
    two lists — the update() and draw() loops derive everything from them.
    """

    # (display_label, TelemetryState field, unit, caution_thresh, critical_thresh)
    _CARDS: list[tuple] = [
        ("COOLANT",  "coolant_temp",   "C", DIAG_COOLANT_CAUTION_C, DIAG_COOLANT_CRITICAL_C, False),
        ("OIL TEMP", "oil_temp",       "C", 110.0,                   125.0,                   False),
        ("INTAKE",   "intake_temp",    "C", 32.0,                    55.0,                    False),
        ("VOLTAGE",  "module_voltage", "V", DIAG_VOLTAGE_LOW_V,      DIAG_VOLTAGE_HIGH_V,      True),
    ]
    # (hist_key, TelemetryState field, chart title, color, thresholds, y_range, clip)
    _CHARTS: list[tuple] = [
        ("coolant",  "coolant_temp",   "Coolant Temp Trend",   (198, 171, 120), [DIAG_COOLANT_CAUTION_C, DIAG_COOLANT_CRITICAL_C], (40.0, 130.0), True),
        ("oil_temp", "oil_temp",       "Oil Temp Trend",       (168, 186, 230), [110.0, 125.0],                                    (40.0, 160.0), False),
        ("intake",   "intake_temp",    "Intake Temp Trend",    (140, 210, 172), [32.0,  55.0],                                     (10.0,  80.0), False),
        ("voltage",  "module_voltage", "Module Voltage Trend", (212, 184, 164), [DIAG_VOLTAGE_LOW_V, DIAG_VOLTAGE_HIGH_V],         (11.0,  15.0), True),
    ]

    def __init__(self, buf_size: int) -> None:
        self._hist: dict[str, deque] = {key: deque(maxlen=buf_size) for key, *_ in self._CHARTS}
        # (value, is_absent) per card attribute; refreshed every frame
        self._snaps: dict[str, tuple[Optional[float], bool]] = {}

    def update(self, t: TelemetryState, _derived: Optional[DerivedTelemetry]) -> None:
        for key, attr, *_ in self._CHARTS:
            sig: Signal = getattr(t, attr)
            self._hist[key].append(_series_value(sig))
        self._snaps = {
            attr: (sig.value, sig.stale or not sig.supported)
            for (_, attr, *_) in self._CARDS
            for sig in (getattr(t, attr),)
        }

    def draw(self, frame: np.ndarray, rect: tuple, theme: dict) -> None:
        x, y, w, h = _content_rect(rect)

        # ── Cards row ──────────────────────────────────────────────────────
        cards_h = min(80, int(h * 0.32))
        card_w = (w - 24) // 4
        for i, (label, attr, unit, caution, critical, low_is_caution) in enumerate(self._CARDS):
            cx = x + i * (card_w + 8)
            value, absent = self._snaps.get(attr, (None, True))
            self._draw_card(frame, (cx, y, card_w, cards_h),
                            label, value, absent, unit, caution, critical, theme, low_is_caution=low_is_caution)

        # ── Trend charts ───────────────────────────────────────────────────
        charts_y = y + cards_h + 8
        chart_gap = 5
        charts_h_total = max(40, h - cards_h - 16)
        chart_h = max(22, (charts_h_total - chart_gap * 3) // 4)
        for i, (key, _attr, title, color, thresholds, y_range, clip) in enumerate(self._CHARTS):
            cy = charts_y + i * (chart_h + chart_gap)
            _plot_series(frame, self._hist[key], (x, cy, w, chart_h), title, color,
                         thresholds=thresholds, y_range=y_range, clip_to_range=clip)

    @staticmethod
    def _draw_card(
        frame: np.ndarray,
        rect: tuple,
        label: str,
        value: Optional[float],
        absent: bool,
        unit: str,
        caution: float,
        critical: float,
        theme: dict,
        low_is_caution: bool = False,
    ) -> None:
        x, y, w, h = rect
        state = _card_state(value, absent, caution, critical, low_is_caution=low_is_caution)
        if state == "absent":
            col  = (138, 138, 138)
            glow = (46, 48, 52)
        elif state == "critical":
            col  = (198, 170, 250)
            glow = (82, 66, 92)
        elif state == "caution":
            col  = (196, 188, 234)
            glow = (78, 74, 90)
        else:
            col  = (172, 204, 188)
            glow = (70, 88, 80)

        cv2.rectangle(frame, (x, y), (x + w, y + h), theme["panel_border"], 1)
        cv2.rectangle(frame, (x + 1, y + 1), (x + w - 1, y + h - 1), glow, -1)

        label_max_w = max(8, w - 16)
        label_scale = _fit_scale(label, label_max_w, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1, 0.28)
        label_text = _fit_text(label, label_max_w, cv2.FONT_HERSHEY_SIMPLEX, label_scale, 1)
        (_, label_h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, label_scale, 1)
        cv2.putText(frame, label_text, (x + 8, y + max(18, 8 + label_h)),
                    cv2.FONT_HERSHEY_SIMPLEX, label_scale, theme["text_primary"], 1, cv2.LINE_AA)

        if absent or value is None:
            value_scale = _fit_scale("--", max(8, w - 16), cv2.FONT_HERSHEY_DUPLEX, 0.86, 1, 0.56)
            cv2.putText(frame, "--", (x + 8, y + 52),
                        cv2.FONT_HERSHEY_DUPLEX, value_scale, col, 1, cv2.LINE_AA)
        else:
            val_str = f"{value:.1f}"
            unit_scale = _fit_scale(unit, max(8, w // 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1, 0.28)
            (unit_w, _), _ = cv2.getTextSize(unit, cv2.FONT_HERSHEY_SIMPLEX, unit_scale, 1)
            value_max_w = max(8, w - 19 - unit_w)
            value_scale = _fit_scale(val_str, value_max_w, cv2.FONT_HERSHEY_DUPLEX, 0.86, 1, 0.48)
            val_text = _fit_text(val_str, value_max_w, cv2.FONT_HERSHEY_DUPLEX, value_scale, 1)
            (val_w, _), _ = cv2.getTextSize(val_text, cv2.FONT_HERSHEY_DUPLEX, value_scale, 1)
            cv2.putText(frame, val_text, (x + 8, y + 52),
                        cv2.FONT_HERSHEY_DUPLEX, value_scale, col, 1, cv2.LINE_AA)
            cv2.putText(frame, unit, (x + 8 + val_w + 3, y + 47),
                        cv2.FONT_HERSHEY_SIMPLEX, unit_scale, theme["text_dim"], 1, cv2.LINE_AA)
