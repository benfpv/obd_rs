"""Engine / Power panel – Power band, RPM/Load/Spark readouts, sparklines."""

from collections import deque
from typing import Optional

import cv2
import numpy as np

from ..config import RPM_REDLINE
from ..data_processing import DerivedTelemetry
from ..models import TelemetryState
from ._helpers import _content_rect, _fit_text, _plot_series, _v


class _EnginePowerPanel:
    """Power-band bar, RPM/Load/Spark/MAF/MAP readouts, power+torque sparklines."""

    def __init__(self, buf_size: int) -> None:
        self._hist: dict[str, deque] = {
            key: deque(maxlen=buf_size) for key in ("power", "torque")
        }
        self._rpm = self._load = self._spark = self._maf = self._map_kpa = 0.0
        self._power = self._torque = 0.0

    def update(self, t: TelemetryState, derived: Optional[DerivedTelemetry]) -> None:
        self._rpm     = _v(t.rpm.value)
        self._load    = _v(t.engine_load.value)
        self._spark   = _v(t.spark_advance.value)
        self._maf     = _v(t.maf_gps.value)
        self._map_kpa = _v(t.map_kpa.value)
        if derived is None:
            self._power = self._torque = 0.0
        else:
            self._power  = float(np.clip(derived.est_power_kw,  0.0, 300.0))
            self._torque = float(np.clip(derived.est_torque_nm, 0.0, 600.0))
        self._hist["power"].append(self._power)
        self._hist["torque"].append(self._torque)

    def draw(self, frame: np.ndarray, rect: tuple, theme: dict) -> None:
        x, y, w, h = _content_rect(rect)

        # ── Power band ────────────────────────────────────────────────────
        band_y, band_h = y + 18, 24
        cv2.rectangle(frame, (x, band_y), (x + w, band_y + band_h), theme["panel_border"], 1)
        fill = int(np.clip(self._rpm / RPM_REDLINE, 0.0, 1.0) * (w - 2))
        cv2.rectangle(frame, (x + 1, band_y + 1), (x + fill, band_y + band_h - 1), (196, 168, 132), -1)
        cv2.putText(frame, "POWER BAND", (x + 2, y + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, theme["text_dim"], 1, cv2.LINE_AA)
        rpm_label = _fit_text(f"{self._rpm:7.0f} rpm", max_px=w - 110,
                              font=cv2.FONT_HERSHEY_DUPLEX, scale=0.46, thickness=1)
        cv2.putText(frame, rpm_label, (x + 106, y + 12),
                    cv2.FONT_HERSHEY_DUPLEX, 0.44, theme["text_primary"], 1, cv2.LINE_AA)

        # ── Readouts ──────────────────────────────────────────────────────
        cv2.putText(frame, f"Est Power  {self._power:6.1f} kW",  (x + 2, y + 74),
                    cv2.FONT_HERSHEY_DUPLEX, 0.52, theme["text_primary"], 1, cv2.LINE_AA)
        cv2.putText(frame, f"Est Torque {self._torque:6.1f} Nm", (x + 2, y + 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.47, (200, 192, 220), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Load {self._load:5.1f}%   Spark {self._spark:5.1f} deg", (x + 2, y + 114),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.43, theme["text_dim"], 1, cv2.LINE_AA)
        cv2.putText(frame, f"MAF {self._maf:5.1f} g/s  MAP {self._map_kpa:5.1f} kPa", (x + 2, y + 132),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, theme["text_dim"], 1, cv2.LINE_AA)

        # ── Sparklines ────────────────────────────────────────────────────
        charts_y = y + 144
        chart_h = max(40, (h - (charts_y - y) - 8) // 2)
        _plot_series(frame, self._hist["power"],
                     (x, charts_y, w, chart_h), "Estimated Power Curve", (198, 172, 138),
                     y_range=(0.0, 300.0))
        _plot_series(frame, self._hist["torque"],
                     (x, charts_y + chart_h + 8, w, chart_h), "Estimated Torque Curve", (186, 164, 206),
                     y_range=(0.0, 600.0))
