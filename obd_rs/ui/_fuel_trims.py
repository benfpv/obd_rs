"""Fuel trims & extended panel – STFT/LTFT readouts, extended cells, sparklines."""

from collections import deque
from typing import Optional

import cv2
import numpy as np

from ..data_processing import DerivedTelemetry
from ..models import TelemetryState
from ._helpers import _content_rect, _fit_text, _plot_series, _series_value, _v


class _FuelTrimsPanel:
    """STFT/LTFT readouts, extended metric cells (Oil/MAF/MAP), + 3 sparklines."""

    def __init__(self, buf_size: int) -> None:
        self._hist: dict[str, deque] = {
            key: deque(maxlen=buf_size) for key in ("stft", "ltft", "oil_temp")
        }
        self._stft = self._ltft = 0.0
        # (supported, stale, value, unit) snapshot per extended signal
        self._oil_snap: tuple = (False, True, None, "C")
        self._maf_snap: tuple = (False, True, None, "g/s")
        self._map_snap: tuple = (False, True, None, "kPa")
        self._stft_snap: tuple[Optional[float], bool] = (None, True)
        self._ltft_snap: tuple[Optional[float], bool] = (None, True)

    def update(self, t: TelemetryState, _derived: Optional[DerivedTelemetry]) -> None:
        self._stft_snap = (t.stft_b1.value, t.stft_b1.stale or not t.stft_b1.supported)
        self._ltft_snap = (t.ltft_b1.value, t.ltft_b1.stale or not t.ltft_b1.supported)
        self._stft = _v(t.stft_b1.value)
        self._ltft = _v(t.ltft_b1.value)
        self._hist["stft"].append(float(np.clip(_series_value(t.stft_b1), -100.0, 100.0)))
        self._hist["ltft"].append(float(np.clip(_series_value(t.ltft_b1), -100.0, 100.0)))
        self._hist["oil_temp"].append(_series_value(t.oil_temp))
        self._oil_snap = (t.oil_temp.supported, t.oil_temp.stale, t.oil_temp.value, t.oil_temp.unit)
        self._maf_snap = (t.maf_gps.supported,  t.maf_gps.stale,  t.maf_gps.value,  t.maf_gps.unit)
        self._map_snap = (t.map_kpa.supported,   t.map_kpa.stale,  t.map_kpa.value,   t.map_kpa.unit)

    def draw(self, frame: np.ndarray, rect: tuple, theme: dict) -> None:
        x, y, w, h = _content_rect(rect)
        cv2.rectangle(frame, (x, y), (x + w, y + h), theme["panel_border"], 1)

        # ── Extended metric cells ─────────────────────────────────────────
        ext_rows = [
            ("Oil Temp", self._oil_snap),
            ("MAF",      self._maf_snap),
            ("MAP",      self._map_snap),
        ]
        col_gap = 8
        row_gap = 4
        col_w  = (w - col_gap) // 2
        item_h = max(24, min(32, int(h * 0.12)))
        top_y  = y + 8
        for i, (label, snap) in enumerate(ext_rows):
            col = i % 2
            row = i // 2
            ix = x + col * (col_w + col_gap)
            iy = top_y + row * (item_h + row_gap)
            self._draw_ext_cell(frame, (ix, iy, col_w, item_h), label, snap, theme)

        # ── STFT / LTFT text ──────────────────────────────────────────────
        metrics_bottom = top_y + 2 * (item_h + row_gap) + 4
        stft_val, stft_absent = self._stft_snap
        ltft_val, ltft_absent = self._ltft_snap
        stft_text = "--" if stft_absent or stft_val is None else f"{stft_val:+5.1f}%"
        ltft_text = "--" if ltft_absent or ltft_val is None else f"{ltft_val:+5.1f}%"
        cv2.putText(frame, f"STFT {stft_text}  LTFT {ltft_text}",
                    (x + 4, metrics_bottom + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, theme["text_primary"], 1, cv2.LINE_AA)

        # ── Sparklines ────────────────────────────────────────────────────
        remain_h = max(52, h - (metrics_bottom + 22 - y) - 6)
        plot_gap = 6
        plot_h   = max(24, min(40, (remain_h - plot_gap * 2) // 3))
        first_plot_y = y + h - (plot_h * 3) - plot_gap * 2 - 2
        _plot_series(frame, self._hist["stft"],
                     (x + 2, first_plot_y, w - 4, plot_h),
                     "STFT Bank 1", (186, 196, 230), y_range=(-30.0, 30.0), clip_to_range=False)
        _plot_series(frame, self._hist["ltft"],
                     (x + 2, first_plot_y + plot_h + plot_gap, w - 4, plot_h),
                     "LTFT Bank 1", (200, 180, 200), y_range=(-30.0, 30.0), clip_to_range=False)
        _plot_series(frame, self._hist["oil_temp"],
                     (x + 2, first_plot_y + (plot_h + plot_gap) * 2, w - 4, plot_h),
                     "Oil Temp (ext)", (168, 186, 230), y_range=(40.0, 160.0), clip_to_range=False)

    @staticmethod
    def _draw_ext_cell(
        frame: np.ndarray, rect: tuple, label: str, snap: tuple, theme: dict,
    ) -> None:
        x, y, w, h = rect
        supported, stale, value, unit = snap
        cv2.rectangle(frame, (x, y), (x + w, y + h), (58, 62, 68), 1)
        state_col = (98, 188, 114) if supported else (104, 104, 118)
        cv2.circle(frame, (x + 8, y + 9), 3, state_col, -1)
        cv2.putText(frame, label, (x + 14, y + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, theme["text_dim"], 1, cv2.LINE_AA)
        value_str = "--" if (value is None or stale or not supported) else f"{value:5.1f} {unit}"
        value_str = _fit_text(value_str, max_px=max(12, w - 8),
                              font=cv2.FONT_HERSHEY_SIMPLEX, scale=0.36, thickness=1)
        cv2.putText(frame, value_str, (x + 4, y + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, theme["text_primary"], 1, cv2.LINE_AA)
