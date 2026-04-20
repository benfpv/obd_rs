"""Dashboard UI package for obd_rs.

Architecture
────────────
Each dashboard section is an isolated panel class with two responsibilities:

    update(telemetry, derived)  – extract the data this panel needs and
                                  append history; called once per frame.
    draw(frame, rect, theme)    – render into *frame* using only stored
                                  state; never touches TelemetryState.

This separation means a change to one panel cannot accidentally break
another, and every mode (simulation / live / replay) goes through exactly
the same code path — the panels are mode-agnostic.

Module layout:
    _helpers.py      – shared rendering primitives (_v, _fit_text, …)
    _diagnostics.py  – Coolant / Oil Temp / Intake / Voltage panel
    _racing.py       – Rev strip, speed bar, pedals, G-meter panel
    _engine.py       – Power band, RPM/Load readouts, sparklines
    _alerts_panel.py – Scrolling alert list
    _system.py       – Connection state, cadence bars, comm stats
    _fuel_trims.py   – STFT/LTFT, extended metrics, sparklines
    _dashboard.py    – DashboardUI coordinator (drives update→draw)
    _contracts.py    – Typed theme keys, panel protocol, validators
    _text.py         – TextStyle dataclass, STYLES registry, draw_text helper
"""

# Re-export public API for backward-compatible ``from obd_rs.ui import …``
from ._contracts import (
    Rect,
    THEME_KEYS,
    PanelContract,
    ThemeColor,
    assert_panel_theme_compatible,
    validate_theme,
)
from ._dashboard import DashboardUI
from ._helpers import _card_state, _fit_scale, _series_value
from ._system import _SystemPanel
from ._text import STYLES, TextStyle, draw_text, fit_text_to

__all__ = [
    "DashboardUI",
    "PanelContract",
    "Rect",
    "STYLES",
    "TextStyle",
    "THEME_KEYS",
    "ThemeColor",
    "assert_panel_theme_compatible",
    "draw_text",
    "fit_text_to",
    "validate_theme",
    "_SystemPanel",
    "_card_state",
    "_fit_scale",
    "_series_value",
]
