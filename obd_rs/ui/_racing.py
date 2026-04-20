"""Racing inputs panel – Rev strip, speed bar, pedal bars, sparklines, G-meter."""

from collections import deque
from typing import Optional

import cv2
import numpy as np

from ..config import G_METER_RANGE, RPM_REDLINE, SPEED_ALERT_KMH, THROTTLE_HIGH_PCT
from ..data_processing import DerivedTelemetry
from ..models import TelemetryState
from ._helpers import _content_rect, _overlay_series_line, _plot_series, _v


class _RacingInputsPanel:
    """Rev-strip, speed bar, pedal bars, speed/throttle sparklines, G-meter."""

    def __init__(self, buf_size: int) -> None:
        self._hist: dict[str, deque] = {
            key: deque(maxlen=buf_size) for key in ("speed", "throttle", "accel", "brake")
        }
        self._rpm = 0.0
        self._speed = 0.0
        self._throttle = 0.0

    @classmethod
    def required_theme_keys(cls) -> frozenset[str]:
        return frozenset({"panel_border"})

    def update(self, t: TelemetryState, derived: Optional[DerivedTelemetry]) -> None:
        self._rpm      = float(np.clip(_v(t.rpm.value),      0.0, 9000.0))
        self._speed    = float(np.clip(_v(t.speed.value),    0.0, 320.0))
        self._throttle = float(np.clip(_v(t.throttle.value), 0.0, 100.0))
        self._hist["speed"].append(self._speed)
        self._hist["throttle"].append(self._throttle)
        if derived is None:
            self._hist["accel"].append(0.0)
            self._hist["brake"].append(float("nan"))
        else:
            self._hist["accel"].append(float(derived.accel_ms2))
            self._hist["brake"].append(float(derived.brake_plot_value))

    def draw(self, frame: np.ndarray, rect: tuple, theme: dict) -> None:
        x, y, w, h = _content_rect(rect)
        rpm      = self._rpm
        speed    = self._speed
        throttle = self._throttle
        brake_raw  = self._hist["brake"][-1] if self._hist["brake"] else float("nan")
        brake_known = not np.isnan(brake_raw)
        brake = 0.0 if not brake_known else float(brake_raw)
        accel = self._hist["accel"][-1] if self._hist["accel"] else 0.0

        # ── Rev-light strip ────────────────────────────────────────────────
        lights = 12
        rpm_frac = float(np.clip(rpm / RPM_REDLINE, 0.0, 1.0))
        lit = int(rpm_frac * lights)
        cell_w = max(8, (w - 11) // lights)
        flash_on = (cv2.getTickCount() // int(cv2.getTickFrequency() * 0.09)) % 2 == 0
        stage_colors = [(72, 188, 88), (86, 220, 220), (74, 164, 245), (70, 78, 240)]
        for i in range(lights):
            cx0 = x + i * (cell_w + 1)
            stage = min(3, int(i * 4 / lights))
            base_col = stage_colors[stage]
            if i < lit:
                head_boost = 1.0 if i < lit - 1 else 1.18
                if rpm_frac > 0.90 and stage == 3 and not flash_on:
                    col: tuple = (34, 42, 74)
                else:
                    col = tuple(int(np.clip(c * head_boost, 0, 255)) for c in base_col)
            else:
                col = tuple(int(c * 0.25) for c in base_col)
            cv2.rectangle(frame, (cx0, y + 2), (cx0 + cell_w, y + 16), col, -1)
            cv2.rectangle(frame, (cx0, y + 2), (cx0 + cell_w, y + 16), (52, 58, 70), 1)

        # ── RPM readout + speed bar ────────────────────────────────────────
        cv2.putText(frame, f"RPM {rpm:7.0f}", (x + 2, y + 38),
                    cv2.FONT_HERSHEY_DUPLEX, 0.56, (214, 214, 222), 1, cv2.LINE_AA)
        self._draw_speed_bar(frame, (x + 2, y + 44, w - 4, 22), speed, theme)

        # ── G-meter (footer) ───────────────────────────────────────────────
        meter_bar_h = 20
        meter_y = y + h - meter_bar_h - 2
        self._draw_longitudinal_meter(frame, (x + 2, meter_y, w - 4, meter_bar_h), accel)

        # ── Pedal bars + sparklines (middle) ──────────────────────────────
        top_block_bottom = y + max(124, int(h * 0.36))
        avail_chart_h = max(68, (meter_y - 6) - top_block_bottom)
        chart_gap = 6
        band_h = max(30, (avail_chart_h - chart_gap) // 2)
        pedal_h = band_h * 2 + chart_gap

        self._draw_vertical_pedal(frame, (x + 2,  top_block_bottom, 24, pedal_h), "THR", throttle, (64, 182, 94), theme)
        self._draw_vertical_pedal(frame, (x + 32, top_block_bottom, 24, pedal_h), "BRK", brake, (56, 56, 210), theme, known=brake_known)

        graph_x = x + 64
        graph_w = w - 64
        _plot_series(frame, self._hist["speed"],
                     (graph_x, top_block_bottom, graph_w, band_h),
                     "Speed Ribbon", (228, 191, 118),
                     thresholds=[SPEED_ALERT_KMH], y_range=(0.0, 260.0))
        _plot_series(frame, self._hist["throttle"],
                     (graph_x, top_block_bottom + band_h + chart_gap, graph_w, band_h),
                     "Throttle + Brake", (106, 186, 130),
                     thresholds=[THROTTLE_HIGH_PCT], y_range=(0.0, 100.0))
        _overlay_series_line(frame, self._hist["brake"],
                             (graph_x, top_block_bottom + band_h + chart_gap, graph_w, band_h),
                             color=(56, 56, 210), y_range=(0.0, 100.0))

    @staticmethod
    def _draw_speed_bar(frame: np.ndarray, rect: tuple, speed_kmh: float, theme: dict) -> None:
        x, y, w, h = rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), theme["panel_border"], 1)
        cv2.rectangle(frame, (x + 1, y + 1), (x + w - 1, y + h - 1), (30, 34, 40), -1)
        frac = float(np.clip(speed_kmh / 260.0, 0.0, 1.0))
        fill_w = int(frac * max(1, w - 2))
        cv2.rectangle(frame, (x + 1, y + 1), (x + fill_w, y + h - 1), (92, 132, 184), -1)
        for tick in range(6):
            tx = x + 1 + int(tick * (w - 2) / 5)
            cv2.line(frame, (tx, y + 2), (tx, y + h - 2), (58, 64, 74), 1)
        cv2.line(frame, (x + 1 + fill_w, y + 1), (x + 1 + fill_w, y + h - 1), (180, 224, 252), 2)
        cv2.putText(frame, f"SPEED {speed_kmh:6.1f} km/h", (x + 6, y + h - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (236, 212, 156), 1, cv2.LINE_AA)

    @staticmethod
    def _draw_vertical_pedal(
        frame: np.ndarray, rect: tuple, label: str,
        value: float, color: tuple, theme: dict, known: bool = True,
    ) -> None:
        x, y, w, h = rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), theme["panel_border"], 1)
        if known:
            fill = int(np.clip(value, 0.0, 100.0) / 100.0 * (h - 2))
            cv2.rectangle(frame, (x + 1, y + h - 1 - fill), (x + w - 1, y + h - 1), color, -1)
        else:
            cv2.rectangle(frame, (x + 1, y + 1), (x + w - 1, y + h - 1), (44, 44, 44), -1)
        cv2.putText(frame, label[:3], (x + 2, y + 12),
                    cv2.FONT_HERSHEY_PLAIN, 0.75, (110, 114, 124), 1, cv2.LINE_AA)
        if known:
            cv2.putText(frame, f"{value:.0f}", (x + 2, y + h - 4),
                        cv2.FONT_HERSHEY_PLAIN, 0.75, (170, 176, 184), 1, cv2.LINE_AA)
        else:
            cv2.putText(frame, "N/A", (x + 2, y + h - 4),
                        cv2.FONT_HERSHEY_PLAIN, 0.75, (90, 94, 102), 1, cv2.LINE_AA)

    @staticmethod
    def _draw_longitudinal_meter(frame: np.ndarray, rect: tuple, accel_ms2: float) -> None:
        x, y, w, h = rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), (68, 68, 78), 1)
        cv2.rectangle(frame, (x + 1, y + 1), (x + w - 1, y + h - 1), (34, 38, 44), -1)
        cx = x + w // 2
        cv2.line(frame, (cx, y + 2), (cx, y + h - 2), (90, 98, 112), 1)
        g_val = float(accel_ms2 / 9.80665)
        frac = float(np.clip(g_val / G_METER_RANGE, -1.0, 1.0))
        px = int(frac * ((w - 6) * 0.5))
        if px < 0:
            cv2.rectangle(frame, (cx + px, y + 3), (cx, y + h - 3), (68, 78, 220), -1)
        elif px > 0:
            cv2.rectangle(frame, (cx, y + 3), (cx + px, y + h - 3), (86, 186, 120), -1)
        label_y = y + h - 4
        cv2.putText(frame, "DECEL", (x + 4, label_y),
                    cv2.FONT_HERSHEY_PLAIN, 0.7, (66, 72, 86), 1, cv2.LINE_AA)
        cv2.putText(frame, "ACCEL", (x + w - 42, label_y),
                    cv2.FONT_HERSHEY_PLAIN, 0.7, (66, 72, 86), 1, cv2.LINE_AA)
        g_text = f"{g_val:+.2f}g"
        (tw, _), _ = cv2.getTextSize(g_text, cv2.FONT_HERSHEY_PLAIN, 0.8, 1)
        cv2.putText(frame, g_text, (cx - tw // 2, label_y),
                    cv2.FONT_HERSHEY_PLAIN, 0.8, (130, 138, 156), 1, cv2.LINE_AA)
