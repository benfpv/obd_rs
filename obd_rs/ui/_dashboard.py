"""DashboardUI coordinator – drives update→draw for each panel, owns overlays."""

from typing import Callable, Optional

import cv2
import numpy as np

from ..ble_adapter import CommStats, ConnectionState, ConnectionStatus
from ..config import DataSource, HISTORY_BUFFER_SIZE, LogMode, WINDOW_NAME, WINDOW_SIZE
from ..data_processing import DerivedTelemetry
from ..data_logger import LoggerStatus
from ..logging_policy import LoggingPolicy
from ..models import AlertEvent, Severity, TelemetryState
from ..windowing import center_window
from ._alerts_panel import _AlertsPanel
from ._contracts import THEME_KEYS, assert_panel_theme_compatible, validate_theme
from ._diagnostics import _DiagnosticsPanel
from ._engine import _EnginePowerPanel
from ._fuel_trims import _FuelTrimsPanel
from ._helpers import _HEADER_H, _fit_text
from ._racing import _RacingInputsPanel
from ._system import _SystemPanel


class DashboardUI:
    def __init__(self) -> None:
        """Thin coordinator: creates panels, drives update→draw each frame.

        Adding a new panel: create a class in a new module, instantiate
        it here, and wire it into draw().  Nothing else needs to change.
        """
        self.win_name = WINDOW_NAME
        self._w, self._h = WINDOW_SIZE
        cv2.namedWindow(self.win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.win_name, self._w, self._h)
        center_window(self.win_name, self._w, self._h)

        self._theme = {
            "bg_top":          (44, 37, 30),
            "bg_bottom":       (30, 30, 30),
            "grid":            (40, 40, 40),
            "panel_border":    (68, 66, 64),
            "panel_header":    (48, 45, 42),
            "text_primary":    (232, 232, 232),
            "text_dim":        (174, 174, 174),
            "diag":            (255, 193, 79),
            "inputs":          (181, 206, 78),
            "power":           (212, 174, 156),
            "issue":           (255, 134, 86),
            "possible":        (204, 162, 156),
            "system":          (255, 193, 79),
            "reserved":        (130, 130, 130),
            "ok_banner":       (82, 122, 77),
            "caution_banner":  (108, 114, 190),
            "critical_banner": (92, 92, 212),
        }

        self._diagnostics   = _DiagnosticsPanel(HISTORY_BUFFER_SIZE)
        self._racing        = _RacingInputsPanel(HISTORY_BUFFER_SIZE)
        self._engine        = _EnginePowerPanel(HISTORY_BUFFER_SIZE)
        self._alerts_panel  = _AlertsPanel()
        self._system_panel  = _SystemPanel()
        self._fuel_trims    = _FuelTrimsPanel(HISTORY_BUFFER_SIZE)
        self._validate_theme_contracts()

    def _validate_theme_contracts(self) -> None:
        """Fail fast if dashboard theme does not satisfy panel contracts."""
        validate_theme(self._theme, THEME_KEYS)
        for panel_type in (
            type(self._diagnostics),
            type(self._racing),
            type(self._engine),
            type(self._alerts_panel),
            type(self._system_panel),
            type(self._fuel_trims),
        ):
            assert_panel_theme_compatible(self._theme, panel_type)

    def draw(
        self,
        telemetry: TelemetryState,
        derived: Optional[DerivedTelemetry],
        issues: list[AlertEvent],
        possible: list[AlertEvent],
        conn: ConnectionStatus,
        policy: LoggingPolicy,
        logger_status: LoggerStatus,
        comm_stats: Optional[CommStats] = None,
        data_source: Optional[DataSource] = None,
        on_key: Optional[Callable[[int], None]] = None,
        logging_enabled: bool = True,
    ) -> bool:
        w, h = self._w, self._h
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        self._paint_background(frame)
        panels = self._layout(w, h)

        # Update all panels with current frame data
        self._diagnostics.update(telemetry, derived)
        self._racing.update(telemetry, derived)
        self._engine.update(telemetry, derived)
        self._alerts_panel.update(issues + possible)
        self._system_panel.update(conn, policy, comm_stats, data_source=data_source)
        self._fuel_trims.update(telemetry, derived)

        # Draw panel shells
        self._draw_section_shell(frame, panels["DIAGNOSTICS"],    "DIAGNOSTICS",           self._theme["diag"])
        self._draw_section_shell(frame, panels["RACING INPUTS"],  "INPUTS",                self._theme["inputs"])
        self._draw_section_shell(frame, panels["ENGINE / POWER"], "ENGINE / POWER",         self._theme["power"])
        self._draw_section_shell(frame, panels["ALERTS"],         "ALERTS",                self._theme["issue"])
        self._draw_section_shell(frame, panels["SYSTEM"],         "SYSTEM",                self._theme["system"])
        self._draw_section_shell(frame, panels["RESERVED"],       "FUEL TRIMS & EXTENDED", self._theme["reserved"])

        # Draw panel contents
        self._diagnostics.draw(frame,  panels["DIAGNOSTICS"],    self._theme)
        self._racing.draw(frame,       panels["RACING INPUTS"],  self._theme)
        self._engine.draw(frame,       panels["ENGINE / POWER"], self._theme)
        self._alerts_panel.draw(frame, panels["ALERTS"],         self._theme)
        self._system_panel.draw(frame, panels["SYSTEM"],         self._theme)
        self._fuel_trims.draw(frame,   panels["RESERVED"],       self._theme)

        crit = any(a.severity == Severity.CRITICAL for a in issues + possible)
        caut = any(a.severity == Severity.CAUTION for a in issues + possible)
        if crit:
            self._banner(frame, "CRITICAL VEHICLE ALERT", self._theme["critical_banner"])
        elif caut:
            self._banner(frame, "CAUTION - INVESTIGATE", self._theme["caution_banner"])
        else:
            self._banner(frame, "RACE DASH READY", self._theme["ok_banner"])
        self._draw_logging_indicator(frame, logger_status, logging_enabled=logging_enabled)

        if data_source == DataSource.REPLAY:
            self._draw_replay_controls_overlay(frame, conn)

        self._draw_connection_overlay(frame, conn, data_source=data_source)

        cv2.imshow(self.win_name, frame)
        key = cv2.waitKey(1) & 0xFF
        if on_key is not None:
            on_key(key)
        if key == ord('m'):
            if policy.mode == LogMode.CRUISE:
                policy.set_mode(LogMode.REALTIME)
            else:
                policy.set_mode(LogMode.CRUISE)
        return key != 27

    def _paint_background(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        top = np.array(self._theme["bg_top"], dtype=np.float32)
        bottom = np.array(self._theme["bg_bottom"], dtype=np.float32)
        alpha = np.linspace(0.0, 1.0, h, dtype=np.float32).reshape(h, 1, 1)
        gradient = ((1.0 - alpha) * top + alpha * bottom).astype(np.uint8)
        np.copyto(frame, np.broadcast_to(gradient, (h, w, 3)))

        # Subtle grid for motorsport telemetry feel.
        for x in range(0, w, 48):
            cv2.line(frame, (x, 28), (x, h), self._theme["grid"], 1)
        for y in range(28, h, 48):
            cv2.line(frame, (0, y), (w, y), self._theme["grid"], 1)
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), self._theme["panel_border"], 1)

    def _layout(self, w: int, h: int) -> dict[str, tuple[int, int, int, int]]:
        top = 38
        margin = 12
        top_h = int((h - top - margin * 3) * 0.60)
        bottom_h = h - top - top_h - margin * 3

        col_w = (w - margin * 4) // 3
        x0 = margin
        x1 = x0 + col_w + margin
        x2 = x1 + col_w + margin

        y0 = top
        y1 = y0 + top_h + margin

        bottom_total_w = w - margin * 5
        alerts_w = int(bottom_total_w * 0.44)  # 75% of previous combined issue+possible width (~58%)
        system_w = int(bottom_total_w * 0.24)
        reserved_w = bottom_total_w - alerts_w - system_w

        bx0 = margin
        bx1 = bx0 + alerts_w + margin
        bx2 = bx1 + system_w + margin
        return {
            "DIAGNOSTICS": (x0, y0, col_w, top_h),
            "RACING INPUTS": (x1, y0, col_w, top_h),
            "ENGINE / POWER": (x2, y0, col_w, top_h),
            "ALERTS": (bx0, y1, alerts_w, bottom_h),
            "SYSTEM": (bx1, y1, system_w, bottom_h),
            "RESERVED": (bx2, y1, reserved_w, bottom_h),
        }

    def _draw_section_shell(
        self,
        frame: np.ndarray,
        rect: tuple[int, int, int, int],
        title: str,
        accent: tuple[int, int, int],
    ) -> None:
        x, y, w, h = rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), self._theme["panel_border"], 1)
        cv2.rectangle(frame, (x + 1, y + 1), (x + w - 1, y + _HEADER_H), self._theme["panel_header"], -1)
        cv2.line(frame, (x + 1, y + _HEADER_H), (x + w - 1, y + _HEADER_H), accent, 1)
        cv2.putText(frame, title, (x + 11, y + 24), cv2.FONT_HERSHEY_DUPLEX, 0.50, accent, 1, cv2.LINE_AA)


    def _banner(self, frame: np.ndarray, text: str, color: tuple[int, int, int]) -> None:
        w = frame.shape[1]
        cv2.rectangle(frame, (0, 0), (w, 28), color, -1)
        cv2.putText(frame, text, (12, 19), cv2.FONT_HERSHEY_DUPLEX, 0.54, (242, 246, 250), 1, cv2.LINE_AA)

    def _draw_logging_indicator(self, frame: np.ndarray, logger_status: LoggerStatus, logging_enabled: bool = True) -> None:
        h, w = frame.shape[:2]
        del h
        pad = 8
        box_w = 308
        box_h = 22
        x = w - box_w - pad
        y = 3
        bg = (26, 28, 34)
        border = (104, 110, 120)
        text_primary = (236, 240, 244)
        text_dim = (166, 172, 180)
        dot = (74, 214, 122)

        if not logging_enabled:
            state_text = "LOG OFF"
            detail_text = "disabled in this mode"
            dot = (120, 124, 136)
        elif logger_status.last_error:
            state_text = "LOG ERROR"
            detail_text = _fit_text(logger_status.last_error, 210, cv2.FONT_HERSHEY_PLAIN, 0.85, 1)
            dot = (92, 92, 212)
        elif not logger_status.active:
            state_text = "LOG ARMED"
            detail_text = "awaiting first sample"
            dot = (230, 188, 96)
        elif logger_status.retention_pruned > 0:
            state_text = "REC PRUNE"
            detail_text = f"{logger_status.rows_written} rows | pruned {logger_status.retention_pruned} old log"
            if logger_status.retention_pruned != 1:
                detail_text += "s"
            dot = (230, 188, 96)
        elif logger_status.collision_avoided:
            state_text = "REC SAFE"
            detail_text = f"{logger_status.rows_written} rows | renamed, no overwrite"
        else:
            state_text = "REC CLEAN"
            detail_text = f"{logger_status.rows_written} rows | new file"

        if logger_status.rows_pending_flush > 0 and logger_status.active and not logger_status.last_error:
            detail_text += f" | {logger_status.rows_pending_flush} pending"
        detail_text = _fit_text(detail_text, box_w - 88, cv2.FONT_HERSHEY_PLAIN, 0.82, 1)

        cv2.rectangle(frame, (x, y), (x + box_w, y + box_h), bg, -1)
        cv2.rectangle(frame, (x, y), (x + box_w, y + box_h), border, 1)
        cv2.circle(frame, (x + 10, y + 11), 4, dot, -1, cv2.LINE_AA)
        cv2.putText(frame, state_text, (x + 22, y + 10), cv2.FONT_HERSHEY_DUPLEX, 0.33, text_primary, 1, cv2.LINE_AA)
        cv2.putText(frame, detail_text, (x + 22, y + 19), cv2.FONT_HERSHEY_PLAIN, 0.82, text_dim, 1, cv2.LINE_AA)

    def _draw_replay_controls_overlay(self, frame: np.ndarray, conn: ConnectionStatus) -> None:
        """Persistent replay strip so timeline controls are always visible."""
        h, _w = frame.shape[:2]
        x = 10
        y = h - 58
        box_w = 430
        box_h = 44

        cv2.rectangle(frame, (x, y), (x + box_w, y + box_h), (24, 28, 34), -1)
        cv2.rectangle(frame, (x, y), (x + box_w, y + box_h), (96, 106, 120), 1)
        cv2.putText(frame, "REPLAY CONTROLS", (x + 10, y + 14), cv2.FONT_HERSHEY_DUPLEX, 0.36, (238, 214, 168), 1, cv2.LINE_AA)
        cv2.putText(frame, "P pause/resume   O stop/reset   J/L seek -/+5s   S skip >5km/h", (x + 10, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (188, 196, 206), 1, cv2.LINE_AA)
        detail = _fit_text(conn.detail or "", max_px=180, font=cv2.FONT_HERSHEY_SIMPLEX, scale=0.38, thickness=1)
        cv2.putText(frame, detail, (x + box_w - 190, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (156, 166, 178), 1, cv2.LINE_AA)

    def _draw_connection_overlay(self, frame: np.ndarray, conn: ConnectionStatus, data_source: Optional[DataSource] = None) -> None:
        """Draw a prominent full-screen overlay when the provider is not connected."""
        if conn.state == ConnectionState.READY:
            return

        h, w = frame.shape[:2]
        frame //= 3

        _LABELS = {
            ConnectionState.DISCONNECTED: "NOT CONNECTED",
            ConnectionState.SCANNING: "SCANNING FOR ADAPTER",
            ConnectionState.CONNECTING: "CONNECTING",
            ConnectionState.INITIALIZING: "INITIALIZING",
            ConnectionState.RECOVERING: "RECONNECTING",
        }
        label = _LABELS.get(conn.state, conn.state.value.upper())

        if conn.state != ConnectionState.DISCONNECTED:
            tick = cv2.getTickCount() / cv2.getTickFrequency()
            label += "." * (1 + int(tick * 2) % 3)

        (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.92, 1)
        ty = h // 2 - 8
        cv2.putText(frame, label, ((w - tw) // 2, ty),
                    cv2.FONT_HERSHEY_DUPLEX, 0.92, (220, 226, 234), 1, cv2.LINE_AA)

        if conn.detail:
            (dw, _), _ = cv2.getTextSize(conn.detail, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            cv2.putText(frame, conn.detail, ((w - dw) // 2, ty + 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (148, 154, 166), 1, cv2.LINE_AA)

        if conn.state == ConnectionState.DISCONNECTED:
            if data_source == DataSource.REPLAY:
                hint = "press Esc to exit"
            elif data_source == DataSource.SIMULATED:
                hint = "starting up"
            else:
                hint = "will retry automatically"
            (hw, _), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
            cv2.putText(frame, hint, ((w - hw) // 2, ty + 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (108, 114, 126), 1, cv2.LINE_AA)
