"""Alerts panel – scrolling list of active alert events."""

import cv2
import numpy as np

from ..models import AlertEvent, Severity
from ._helpers import _content_rect, _fit_text


class _AlertsPanel:
    """Scrolling list of active alert events."""

    def __init__(self) -> None:
        self._alerts: list[AlertEvent] = []

    def update(self, alerts: list[AlertEvent]) -> None:
        self._alerts = alerts

    def draw(self, frame: np.ndarray, rect: tuple, theme: dict) -> None:
        x, y, w, h = _content_rect(rect)
        if not self._alerts:
            cv2.putText(frame, "none", (x + 2, y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (136, 148, 160), 1, cv2.LINE_AA)
            return
        max_lines = max(1, (h - 2) // 26)
        for i, alert in enumerate(self._alerts[:max_lines]):
            ay = y + i * 26
            if alert.severity == Severity.CRITICAL:
                bg, edge = (70, 66, 110), (184, 176, 224)
            elif alert.severity == Severity.CAUTION:
                bg, edge = (62, 86, 94), (178, 202, 210)
            else:
                bg, edge = (50, 60, 70), (162, 178, 190)
            cv2.rectangle(frame, (x + 2, ay), (x + w - 2, ay + 21), bg, -1)
            cv2.rectangle(frame, (x + 2, ay), (x + w - 2, ay + 21), edge, 1)
            txt = _fit_text(f"{alert.title} | {alert.detail}", max_px=max(24, w - 10),
                            font=cv2.FONT_HERSHEY_PLAIN, scale=1.0, thickness=1)
            cv2.putText(frame, txt, (x + 6, ay + 14),
                        cv2.FONT_HERSHEY_PLAIN, 1.0, theme["text_primary"], 1, cv2.LINE_AA)
