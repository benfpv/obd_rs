"""Shared rendering primitives and constants used by all dashboard panels."""

from collections import deque
from typing import Optional

import cv2
import numpy as np

from cvplt import cvplt

from ..models import Signal

# ─── Layout constants ─────────────────────────────────────────────────────────
_HEADER_H = 34
_PANEL_PAD = 8


# ─── Module-level rendering primitives (shared by all panels) ─────────────────

def _v(value: Optional[float]) -> float:
    """Return float value or 0.0 when the signal has no data."""
    return float(value) if value is not None else 0.0


def _vn(value: Optional[float]) -> float:
    """Return float value or NaN when absent (preserves absence for charts)."""
    return float(value) if value is not None else float("nan")


def _fit_text(text: str, max_px: int, font: int, scale: float, thickness: int) -> str:
    if max_px <= 4:
        return ""
    width, _ = cv2.getTextSize(text, font, scale, thickness)[0]
    if width <= max_px:
        return text
    suffix = "..."
    candidate = text
    while candidate:
        candidate = candidate[:-1]
        trial = candidate + suffix
        width, _ = cv2.getTextSize(trial, font, scale, thickness)[0]
        if width <= max_px:
            return trial
    return suffix


def _fit_scale(text: str, max_px: int, font: int, scale: float, thickness: int, min_scale: float) -> float:
    if max_px <= 4:
        return min_scale
    fitted = scale
    while fitted > min_scale:
        width, _ = cv2.getTextSize(text, font, fitted, thickness)[0]
        if width <= max_px:
            return fitted
        fitted = round(fitted - 0.02, 2)
    return min_scale


def _content_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    return (
        x + _PANEL_PAD,
        y + _HEADER_H + _PANEL_PAD + 2,
        max(8, w - _PANEL_PAD * 2),
        max(8, h - _HEADER_H - _PANEL_PAD * 2 - 2),
    )


def _series_value(sig: Signal) -> float:
    """Return NaN for stale/unsupported signals so plots show gaps, not lies."""
    if sig.value is None or sig.stale or not sig.supported:
        return float("nan")
    return float(sig.value)


def _card_state(
    value: Optional[float],
    absent: bool,
    caution: float,
    critical: float,
    *,
    low_is_caution: bool = False,
) -> str:
    if absent or value is None:
        return "absent"
    if low_is_caution and value < caution:
        return "caution"
    if low_is_caution:
        if value > critical:
            return "critical"
        return "normal"
    if value > critical:
        return "critical"
    if value > caution:
        return "caution"
    return "normal"


def _plot_series(
    frame: np.ndarray,
    values: deque,
    rect: tuple[int, int, int, int],
    title: str,
    color: tuple[int, int, int],
    thresholds: Optional[list[float]] = None,
    y_range: Optional[tuple[float, float]] = None,
    clip_to_range: bool = True,
) -> None:
    """Render a sparkline.  NaN values (from absent signals) are interpolated
    rather than passed to cvplt, which cannot handle them."""
    x, y, w, h = rect
    arr = np.array(values, dtype=np.float32)
    nan_mask = np.isnan(arr)
    if nan_mask.all():
        return  # No data yet; skip to avoid rendering garbage
    if nan_mask.any():
        valid_idx = np.where(~nan_mask)[0]
        arr = np.interp(np.arange(len(arr)), valid_idx, arr[valid_idx]).astype(np.float32)
    if arr.size < 2:
        return
    if clip_to_range and y_range is not None:
        lo, hi = y_range
        if hi > lo:
            arr = np.clip(arr, lo, hi)
    frame[:] = cvplt.draw_plot(
        data=arr,
        renderArray=frame,
        plotBeginXY=[x, y],
        plotEndXY=[x + w, y + h],
        plotTitle=title,
        plotBackgroundColour=[32, 32, 32],
        plotOutlineColour=[72, 72, 72],
        plotValuesColour=list(color),
        yRange=y_range,
    )
    _draw_threshold_lines(frame, rect, thresholds, y_range)


def _draw_threshold_lines(
    frame: np.ndarray,
    rect: tuple[int, int, int, int],
    thresholds: Optional[list[float]],
    y_range: Optional[tuple[float, float]],
) -> None:
    if not thresholds or y_range is None:
        return
    x, y, w, h = rect
    lo, hi = y_range
    if hi <= lo:
        return
    for idx, thr in enumerate(thresholds):
        frac = np.clip((thr - lo) / (hi - lo), 0.0, 1.0)
        py = int(y + h - frac * h)
        col = np.array((84, 104, 132) if idx == 0 else (104, 104, 148), dtype=np.uint8)
        band_h = 5
        y0 = max(y + 1, py - band_h // 2)
        y1 = min(y + h - 1, py + band_h // 2)
        if y1 <= y0:
            continue
        region = frame[y0:y1, x + 2:x + w - 2]
        band = np.full_like(region, col)
        cv2.addWeighted(band, 0.16, region, 0.84, 0.0, region)


def _overlay_series_line(
    frame: np.ndarray,
    values: deque,
    rect: tuple[int, int, int, int],
    color: tuple[int, int, int],
    y_range: tuple[float, float],
) -> None:
    x, y, w, h = rect
    arr = np.array(values, dtype=np.float32)
    if arr.size < 2:
        return
    lo, hi = y_range
    if hi <= lo:
        return
    n = min(arr.size, w - 4)
    seg = arr[-n:]
    points = []
    for i, val in enumerate(seg):
        if np.isnan(val):
            continue
        px = x + 2 + int(i * max(1, (w - 4)) / max(1, n - 1))
        frac = np.clip((float(val) - lo) / (hi - lo), 0.0, 1.0)
        py = y + h - 1 - int(frac * (h - 2))
        points.append((px, py))
    if len(points) > 1:
        cv2.polylines(frame, [np.array(points, dtype=np.int32)], False, color, 1, cv2.LINE_AA)
