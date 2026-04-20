"""System panel – connection state, cadence bars, comm stats, command log."""

from typing import Optional

import cv2
import numpy as np

from ..ble_adapter import CommStats, ConnectionState, ConnectionStatus
from ..config import DataSource, LogMode
from ..logging_policy import LoggingPolicy
from ._helpers import _content_rect, _fit_text


class _SystemPanel:
    """Connection state, poll cadence bars, comm stats, recent command log."""

    def __init__(self) -> None:
        self._conn = ConnectionStatus(state=ConnectionState.DISCONNECTED)
        self._policy: Optional[LoggingPolicy] = None
        self._comm_stats: Optional[CommStats] = None
        self._data_source: Optional[DataSource] = None

    @classmethod
    def required_theme_keys(cls) -> frozenset[str]:
        return frozenset({"panel_border", "text_primary", "text_dim", "system"})

    def update(self, conn: ConnectionStatus, policy: LoggingPolicy,
               comm_stats: Optional[CommStats], data_source: Optional[DataSource] = None) -> None:
        self._conn       = conn
        self._policy     = policy
        self._comm_stats = comm_stats
        self._data_source = data_source

    def draw(self, frame: np.ndarray, rect: tuple, theme: dict) -> None:
        x, y, w, h = _content_rect(rect)
        cad = self._policy.cadence()

        # ── Connection info ────────────────────────────────────────────────
        line_step = 16
        line_top  = y + 6
        poll_label = "HIGH" if self._policy.mode == LogMode.REALTIME else "LOW"
        info_lines = [
            ("State",   self._conn.state.value),
            ("Device",  self._conn.device_name or "-"),
            ("Detail",  self._conn.detail or "-"),
            ("Source",  self._data_source.value if self._data_source else "-"),
            ("Polling", f"{poll_label} ({self._policy.mode.value})"),
        ]
        for i, (k, v) in enumerate(info_lines):
            yy = line_top + i * line_step
            cv2.putText(frame, k, (x + 4, yy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, theme["text_dim"], 1, cv2.LINE_AA)
            clipped_v = _fit_text(str(v), max_px=max(20, w - 68),
                                  font=cv2.FONT_HERSHEY_DUPLEX, scale=0.36, thickness=1)
            cv2.putText(frame, clipped_v, (x + 56, yy),
                        cv2.FONT_HERSHEY_DUPLEX, 0.36, theme["text_primary"], 1, cv2.LINE_AA)

        # ── Cadence bars ──────────────────────────────────────────────────
        bars_top = line_top + len(info_lines) * line_step + 4
        cv2.line(frame, (x + 2, bars_top - 4), (x + w - 2, bars_top - 4), (50, 54, 60), 1)
        bar_h, bar_step = 10, 16
        self._mini_rate(frame, (x + 2, bars_top,              w - 4, bar_h), "High", cad.high_hz,   12.0, (198, 170, 128), theme)
        self._mini_rate(frame, (x + 2, bars_top + bar_step,   w - 4, bar_h), "Mid",  cad.medium_hz, 12.0, (182, 202, 140), theme)
        self._mini_rate(frame, (x + 2, bars_top + bar_step*2, w - 4, bar_h), "Low",  cad.low_hz,    12.0, (194, 176, 164), theme)

        # ── Comm stats ────────────────────────────────────────────────────
        comm_top = bars_top + bar_step * 3 + 6
        cv2.line(frame, (x + 2, comm_top - 4), (x + w - 2, comm_top - 4), (50, 54, 60), 1)
        cv2.putText(frame, "COMM", (x + 4, comm_top + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, theme["system"], 1, cv2.LINE_AA)
        stats = self._comm_stats or CommStats()
        stat_y, stat_step = comm_top + 14, 14
        cv2.putText(frame, f"TX {stats.tx_count}  RX {stats.rx_count}",
                    (x + 4, stat_y + stat_step),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, theme["text_primary"], 1, cv2.LINE_AA)
        err_col = (92, 92, 212) if (stats.timeout_count + stats.error_count) > 0 else theme["text_dim"]
        cv2.putText(frame, f"TMO {stats.timeout_count}  ERR {stats.error_count}",
                    (x + 4, stat_y + stat_step * 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, err_col, 1, cv2.LINE_AA)
        cv2.putText(frame, f"{stats.tx_bytes}B out  {stats.rx_bytes}B in",
                    (x + 4, stat_y + stat_step * 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, theme["text_dim"], 1, cv2.LINE_AA)

        # ── Recent command log ────────────────────────────────────────────
        log_top = stat_y + stat_step * 4 + 4
        cv2.line(frame, (x + 2, log_top - 4), (x + w - 2, log_top - 4), (50, 54, 60), 1)
        cv2.putText(frame, "RECENT", (x + 4, log_top + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, theme["system"], 1, cv2.LINE_AA)
        log_entry_h = 13
        log_y = log_top + 14
        avail_h = y + h - log_y - 2
        max_entries = max(1, avail_h // log_entry_h)
        entries = list(stats.recent_log)
        visible = entries[-max_entries:] if len(entries) > max_entries else entries
        for i, entry in enumerate(visible):
            ey = log_y + i * log_entry_h
            if ey + log_entry_h > y + h:
                break
            _ts, _dir_tx, cmd, result_type, result_val = entry
            if result_type == "RX":
                tag_col = (120, 188, 120)
            elif result_type == "TIMEOUT":
                tag_col = (96, 168, 230)
            else:
                tag_col = (92, 92, 212)
            cv2.putText(frame, cmd, (x + 4, ey),
                        cv2.FONT_HERSHEY_PLAIN, 0.82, theme["text_dim"], 1, cv2.LINE_AA)
            tag = result_type
            if result_val:
                tag = _fit_text(f"{result_type} {result_val}", max_px=max(20, w - 60),
                                font=cv2.FONT_HERSHEY_PLAIN, scale=0.76, thickness=1)
            (tw, _), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_PLAIN, 0.76, 1)
            cv2.putText(frame, tag, (x + w - tw - 4, ey),
                        cv2.FONT_HERSHEY_PLAIN, 0.76, tag_col, 1, cv2.LINE_AA)

    @staticmethod
    def _mini_rate(
        frame: np.ndarray, rect: tuple, name: str,
        value: float, vmax: float, color: tuple, theme: dict,
    ) -> None:
        x, y, w, h = rect
        bar_x = x + 38
        bar_w = w - 110
        cv2.putText(frame, name, (x + 1, y + h - 2),
                    cv2.FONT_HERSHEY_PLAIN, 1.0, theme["text_dim"], 1, cv2.LINE_AA)
        cv2.rectangle(frame, (bar_x, y), (bar_x + bar_w, y + h), theme["panel_border"], 1)
        fill = int(np.clip(value / vmax, 0.0, 1.0) * max(1, bar_w - 1))
        cv2.rectangle(frame, (bar_x + 1, y + 1), (bar_x + fill, y + h - 1), color, -1)
        cv2.putText(frame, f"{value:3.1f} Hz", (x + w - 66, y + h - 2),
                    cv2.FONT_HERSHEY_PLAIN, 1.0, theme["text_primary"], 1, cv2.LINE_AA)
