"""Typed text-rendering primitives for the dashboard UI.

This module standardises the most repetitive boilerplate around
``cv2.putText``: font + scale + thickness selection, anti-aliasing flag,
and text measurement / fitting.  Adoption is incremental – panels can
mix bare ``cv2.putText`` calls with these helpers freely.

Design goals:
  * Single source of truth for canonical text styles.
  * Cheap to adopt: ``draw_text(frame, text, org, color, style=STYLES.detail)``.
  * Preserves call-site flexibility for dynamic-scale sites
    (e.g. the diagnostics card auto-fits its title), which keep using
    ``_fit_scale``/``_fit_text`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np

from ._contracts import ThemeColor


@dataclass(frozen=True)
class TextStyle:
    """Bundled font/scale/thickness for a class of text.

    ``font`` matches the OpenCV ``FONT_HERSHEY_*`` enum; ``scale`` and
    ``thickness`` are passed through unchanged.  The dataclass is frozen
    so style instances can be compared and used as dict keys.
    """

    font: int
    scale: float
    thickness: int = 1

    def measure(self, text: str) -> Tuple[int, int]:
        """Return ``(width_px, height_px)`` for *text* under this style."""
        (w, h), _baseline = cv2.getTextSize(text, self.font, self.scale, self.thickness)
        return int(w), int(h)


class _StyleRegistry:
    """Curated styles used across panels and dashboard chrome.

    Keep this small – introduce a new style only when 2+ call sites would
    use it. Sites that need dynamic scaling should keep using ``_fit_scale``
    rather than inflating this registry.
    """

    # Panel header text ("DIAGNOSTICS", "ENGINE", etc.) – dashboard chrome.
    header = TextStyle(cv2.FONT_HERSHEY_DUPLEX, 0.50)

    # Section / micro-header text inside panels (e.g. "POWER BAND", "COMM").
    section = TextStyle(cv2.FONT_HERSHEY_SIMPLEX, 0.38)

    # Primary numeric/value readouts inside panels.
    value = TextStyle(cv2.FONT_HERSHEY_DUPLEX, 0.46)

    # Secondary readouts / supporting metrics.
    detail = TextStyle(cv2.FONT_HERSHEY_SIMPLEX, 0.40)

    # Small monospaced-ish caption / stat lines.
    caption = TextStyle(cv2.FONT_HERSHEY_PLAIN, 1.0)


STYLES = _StyleRegistry()


def draw_text(
    frame: np.ndarray,
    text: str,
    org: Tuple[int, int],
    color: ThemeColor,
    style: TextStyle,
) -> None:
    """Render *text* at *org* in *color* using *style* with anti-aliasing.

    Thin wrapper around ``cv2.putText`` – exists so that:
      * Anti-aliasing is uniform across the UI.
      * Style/colour are explicit at the call site.
      * Future migration to a different text renderer (e.g. PIL) is local.
    """
    cv2.putText(
        frame,
        text,
        (int(org[0]), int(org[1])),
        style.font,
        style.scale,
        color,
        style.thickness,
        cv2.LINE_AA,
    )


def fit_text_to(text: str, max_px: int, style: TextStyle) -> str:
    """Truncate *text* with an ellipsis so it fits *max_px* under *style*."""
    # Local import to avoid a circular import at module load time.
    from ._helpers import _fit_text

    return _fit_text(text, max_px, style.font, style.scale, style.thickness)
