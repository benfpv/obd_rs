"""Startup mode chooser and device picker – rendered in the main window."""

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .config import (
    AUTO_SELECT_DELAY_S,
    BLE_SCAN_TIMEOUT_S,
    DataSource,
    DEVICE_SCORE_HINT_MATCH,
    DEVICE_SCORE_PREFIX_BONUS,
    LOG_DIR,
    REPLAY_FILE,
    VEEPEAK_NAME_HINTS,
    WINDOW_NAME,
    WINDOW_SIZE,
)
from .windowing import center_window

STARTUP_WINDOW = WINDOW_NAME
_STARTUP_PREFS_FILE = "startup_device.json"
_AUTO_SCAN_RETRY_LIMIT = 3


def _startup_prefs_path() -> Path:
    return Path(LOG_DIR) / _STARTUP_PREFS_FILE


def _load_preferred_device_address() -> Optional[str]:
    try:
        data = json.loads(_startup_prefs_path().read_text(encoding="utf-8"))
    except Exception:
        return None
    address = str(data.get("address", "")).strip()
    return address or None


def _save_preferred_device(name: str, address: str) -> None:
    path = _startup_prefs_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "name": name,
                    "address": address,
                    "saved_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        # Startup should remain usable even if preference persistence fails.
        return


def _win_closed(name: str) -> bool:
    try:
        return cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def _put_centered(
    frame: np.ndarray, text: str, cx: int, cy: int,
    font: int, scale: float, color: tuple[int, int, int], thickness: int = 1,
) -> None:
    (tw, _), _ = cv2.getTextSize(text, font, scale, thickness)
    cv2.putText(frame, text, (cx - tw // 2, cy), font, scale, color, thickness, cv2.LINE_AA)


def _ensure_window() -> tuple[int, int]:
    """Create (or reuse) the single application window at full dashboard size."""
    W, H = WINDOW_SIZE
    cv2.namedWindow(STARTUP_WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(STARTUP_WINDOW, W, H)
    center_window(STARTUP_WINDOW, W, H)
    return W, H


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def choose_mode() -> Optional[DataSource]:
    """Show a visual dialog for data source selection.

    Returns a ``DataSource`` member, or ``None`` if the user quits.
    """
    WIN = STARTUP_WINDOW
    W, H = _ensure_window()
    cx = W // 2

    choice: list[DataSource] = []

    # Adaptive card layout. Use horizontal layout when it fits; otherwise stack.
    btn_h = 108
    btn_gap = 24
    btn_w = min(280, max(200, (W - 120 - btn_gap * 2) // 3))
    row_w = btn_w * 3 + btn_gap * 2
    if row_w <= W - 40:
        start_x = (W - row_w) // 2
        btn_y = max(150, H // 2 - btn_h // 2 - 8)
        sim_rect = (start_x, btn_y, btn_w, btn_h)
        live_rect = (start_x + btn_w + btn_gap, btn_y, btn_w, btn_h)
        replay_rect = (start_x + (btn_w + btn_gap) * 2, btn_y, btn_w, btn_h)
    else:
        btn_w = min(W - 60, 420)
        start_x = (W - btn_w) // 2
        top = max(118, H // 2 - (btn_h * 3 + btn_gap * 2) // 2)
        sim_rect = (start_x, top, btn_w, btn_h)
        live_rect = (start_x, top + btn_h + btn_gap, btn_w, btn_h)
        replay_rect = (start_x, top + (btn_h + btn_gap) * 2, btn_w, btn_h)

    def _on_mouse(event: int, mx: int, my: int, _flags: int, _param: object) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        for rect, name in ((sim_rect, DataSource.SIMULATED), (live_rect, DataSource.LIVE), (replay_rect, DataSource.REPLAY)):
            rx, ry, rw, rh = rect
            if rx <= mx <= rx + rw and ry <= my <= ry + rh:
                choice.append(name)

    cv2.setMouseCallback(WIN, _on_mouse)

    while not choice:
        if _win_closed(WIN):
            return None

        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)

        _put_centered(frame, "obd_rs", cx, H // 4, cv2.FONT_HERSHEY_DUPLEX, 1.4, (232, 232, 232))
        _put_centered(frame, "Select data source", cx, H // 4 + 46,
                      cv2.FONT_HERSHEY_SIMPLEX, 0.56, (160, 164, 172))
        cv2.line(frame, (cx - 220, H // 4 + 68), (cx + 220, H // 4 + 68), (58, 62, 68), 1)

        sx, sy, sw, sh = sim_rect
        cv2.rectangle(frame, (sx, sy), (sx + sw, sy + sh), (62, 78, 52), -1)
        cv2.rectangle(frame, (sx, sy), (sx + sw, sy + sh), (98, 128, 78), 2)
        _put_centered(frame, "SIMULATE", sx + sw // 2, sy + sh // 2 + 8,
                      cv2.FONT_HERSHEY_DUPLEX, 0.82, (188, 228, 168))
        _put_centered(frame, "Synthetic telemetry", sx + sw // 2, sy + sh - 14,
                  cv2.FONT_HERSHEY_SIMPLEX, 0.40, (130, 144, 136))

        lx, ly, lw, lh = live_rect
        cv2.rectangle(frame, (lx, ly), (lx + lw, ly + lh), (56, 66, 78), -1)
        cv2.rectangle(frame, (lx, ly), (lx + lw, ly + lh), (88, 122, 176), 2)
        _put_centered(frame, "CONNECT", lx + lw // 2, ly + lh // 2 + 8,
                      cv2.FONT_HERSHEY_DUPLEX, 0.82, (178, 204, 232))
        _put_centered(frame, "BLE OBD-II adapter", lx + lw // 2, ly + lh - 14,
                  cv2.FONT_HERSHEY_SIMPLEX, 0.40, (130, 142, 156))

        rx, ry, rw, rh = replay_rect
        cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (70, 62, 48), -1)
        cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (176, 148, 104), 2)
        _put_centered(frame, "REPLAY", rx + rw // 2, ry + rh // 2 + 8,
                      cv2.FONT_HERSHEY_DUPLEX, 0.82, (236, 208, 162))
        _put_centered(frame, "Recorded session CSV", rx + rw // 2, ry + rh - 14,
                      cv2.FONT_HERSHEY_SIMPLEX, 0.40, (152, 138, 120))

        _put_centered(frame, "[S] Simulate    [C] Connect    [R] Replay    [ESC] Quit", cx, H - 40,
                      cv2.FONT_HERSHEY_SIMPLEX, 0.44, (86, 90, 98))

        cv2.imshow(WIN, frame)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return None
        if key in (ord("s"), ord("S")):
            return DataSource.SIMULATED
        if key in (ord("c"), ord("C")):
            return DataSource.LIVE
        if key in (ord("r"), ord("R")):
            return DataSource.REPLAY

    return choice[0]


# ---------------------------------------------------------------------------
# BLE device picker
# ---------------------------------------------------------------------------

@dataclass
class ScanState:
    phase: str = "scanning"           # scanning | results | error
    devices: list = field(default_factory=list)  # list of (name, address)
    error: str = ""
    hover: int = -1
    selected: Optional[int] = None
    scan_active: bool = False          # guards against overlapping scans
    auto_idx: int = -1                 # index of sole likely device (-1 = none)
    auto_start: float = 0.0           # monotonic time auto-select began
    preferred_address: Optional[str] = None
    auto_scan_attempts: int = 0
    auto_retry_pending: bool = False
    manual_refresh_mode: bool = False
    last_scan_was_auto: bool = False


def _device_score(name: str) -> int:
    upper = name.upper()
    best = 0
    for hint in VEEPEAK_NAME_HINTS:
        h = hint.upper()
        if h in upper:
            score = DEVICE_SCORE_HINT_MATCH
            if upper.startswith(h):
                score += DEVICE_SCORE_PREFIX_BONUS
            best = max(best, score)
    return best


class _BleScanner:
    """Encapsulates BLE device scanning lifecycle.

    Replaces closure-based scan management with an explicit object that owns
    the scan thread and mutates the shared ``ScanState``.
    """

    def __init__(self, state: ScanState, *, bleak_available: bool) -> None:
        self._state = state
        self._bleak_ok = bleak_available

    def start(self, *, auto: bool = False) -> None:
        st = self._state
        if st.scan_active:
            return
        if auto:
            if st.auto_scan_attempts >= _AUTO_SCAN_RETRY_LIMIT:
                st.manual_refresh_mode = True
                return
            st.auto_scan_attempts += 1
            st.last_scan_was_auto = True
        else:
            st.last_scan_was_auto = False
        st.phase = "scanning"
        st.devices = []
        st.hover = -1
        st.selected = None
        st.auto_idx = -1
        st.auto_retry_pending = False
        st.scan_active = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        st = self._state
        if not self._bleak_ok:
            st.error = "bleak not installed — pip install bleak"
            st.phase = "error"
            st.scan_active = False
            return
        try:
            import asyncio
            from bleak import BleakScanner
            found = asyncio.run(BleakScanner.discover(timeout=BLE_SCAN_TIMEOUT_S))
            dedup: dict[str, str] = {}
            for dev in found:
                if dev.address and dev.address not in dedup:
                    dedup[dev.address] = dev.name or "(unnamed)"
            ranked = [(name, addr) for addr, name in dedup.items()]
            ranked.sort(key=lambda d: (-_device_score(d[0]), d[0].upper(), d[1]))
            st.devices = ranked

            st.auto_idx = -1
            if st.preferred_address:
                preferred_upper = st.preferred_address.upper()
                for i, (_n, addr) in enumerate(ranked):
                    if addr.upper() == preferred_upper:
                        st.auto_idx = i
                        st.auto_start = time.monotonic()
                        st.manual_refresh_mode = False
                        break

                if st.auto_idx < 0 and st.last_scan_was_auto:
                    if st.auto_scan_attempts < _AUTO_SCAN_RETRY_LIMIT:
                        st.auto_retry_pending = True
                    else:
                        st.manual_refresh_mode = True

            st.phase = "results"
        except Exception as exc:
            st.error = str(exc)
            st.phase = "error"
        finally:
            st.scan_active = False


def choose_ble_device() -> Optional[tuple[str, str]]:
    """Scan for BLE devices and let the user pick one.

    Returns ``(name, address)`` for the chosen device, or ``None`` if the user
    cancels.  Requires ``bleak`` to be installed.
    """
    try:
        from bleak import BleakScanner
        _BLEAK_OK = True
    except ImportError:
        _BLEAK_OK = False

    WIN = STARTUP_WINDOW
    W, H = _ensure_window()
    cx = W // 2

    ITEM_H = 56
    LIST_W = min(600, W - 100)
    LIST_X = (W - LIST_W) // 2
    LIST_Y = 170
    MAX_VISIBLE = min(8, max(3, (H - LIST_Y - 80) // ITEM_H))

    state = ScanState()
    scanner = _BleScanner(state, bleak_available=_BLEAK_OK)

    state.preferred_address = _load_preferred_device_address()
    if state.preferred_address:
        scanner.start(auto=True)
    else:
        scanner.start()

    dot_frame = 0

    def _on_mouse(event: int, mx: int, my: int, _flags: int, _param: object) -> None:
        if state.phase != "results":
            return
        visible = state.devices[:MAX_VISIBLE]
        if event == cv2.EVENT_MOUSEMOVE:
            state.hover = -1
            for i, _ in enumerate(visible):
                iy = LIST_Y + i * ITEM_H
                if LIST_X <= mx <= LIST_X + LIST_W and iy <= my <= iy + ITEM_H - 4:
                    state.hover = i
                    break
        elif event == cv2.EVENT_LBUTTONDOWN:
            for i, _ in enumerate(visible):
                iy = LIST_Y + i * ITEM_H
                if LIST_X <= mx <= LIST_X + LIST_W and iy <= my <= iy + ITEM_H - 4:
                    state.auto_idx = -1  # cancel auto-select on manual click
                    state.selected = i
                    break

    cv2.setMouseCallback(WIN, _on_mouse)

    while state.selected is None:
        if _win_closed(WIN):
            return None

        if state.auto_retry_pending and not state.scan_active:
            state.auto_retry_pending = False
            scanner.start(auto=True)

        # Auto-select countdown.
        if state.auto_idx >= 0:
            elapsed = time.monotonic() - state.auto_start
            if elapsed >= AUTO_SELECT_DELAY_S:
                state.selected = state.auto_idx
                break

        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)

        _put_centered(frame, "obd_rs \u2014 Select Device", cx, 70,
                      cv2.FONT_HERSHEY_DUPLEX, 0.92, (232, 232, 232))
        cv2.line(frame, (LIST_X, 92), (LIST_X + LIST_W, 92), (58, 62, 68), 1)

        if state.phase == "scanning":
            dots = "." * ((dot_frame // 8) % 4)
            dot_frame += 1
            if state.last_scan_was_auto and state.preferred_address:
                _put_centered(
                    frame,
                    f"Searching for known adapter ({state.auto_scan_attempts}/{_AUTO_SCAN_RETRY_LIMIT}){dots}",
                    cx,
                    H // 2,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.62,
                    (160, 164, 172),
                )
            else:
                _put_centered(frame, f"Scanning for BLE devices{dots}", cx, H // 2,
                              cv2.FONT_HERSHEY_SIMPLEX, 0.62, (160, 164, 172))

        elif state.phase == "error":
            _put_centered(frame, "Scan failed", cx, H // 2 - 30,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.56, (80, 100, 220))
            _put_centered(frame, state.error[:70], cx, H // 2,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 144, 152))
            _put_centered(frame, "Press [R] to retry", cx, H // 2 + 34,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.46, (120, 126, 136))

        elif state.phase == "results":
            devices = state.devices
            if not devices:
                if state.manual_refresh_mode and state.preferred_address:
                    _put_centered(frame, "Auto-connect search failed (3 attempts).", cx, H // 2 - 28,
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.56, (170, 176, 190))
                    _put_centered(frame, "Manual refresh mode: press [R] to scan and wait.",
                                  cx, H // 2 + 6, cv2.FONT_HERSHEY_SIMPLEX, 0.44, (120, 126, 136))
                else:
                    _put_centered(frame, "No BLE devices found.", cx, H // 2 - 20,
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.56, (160, 164, 172))
                    _put_centered(frame, "Make sure your adapter is powered on, then press [R].",
                                  cx, H // 2 + 16, cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 126, 136))
            else:
                cv2.putText(frame, "Select your OBD adapter:", (LIST_X, LIST_Y - 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.46, (130, 136, 144), 1, cv2.LINE_AA)
                if state.manual_refresh_mode and state.preferred_address:
                    cv2.putText(frame, "Auto-connect paused. Select manually or press [R].", (LIST_X, LIST_Y - 36),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 126, 136), 1, cv2.LINE_AA)
                for i, (name, addr) in enumerate(devices[:MAX_VISIBLE]):
                    iy = LIST_Y + i * ITEM_H
                    recommended = _device_score(name) > 0
                    is_auto = state.auto_idx == i
                    if state.hover == i:
                        bg = (56, 66, 78)
                    elif is_auto:
                        bg = (50, 64, 50)
                    else:
                        bg = (46, 58, 46) if recommended else (42, 48, 56)
                    cv2.rectangle(frame, (LIST_X, iy), (LIST_X + LIST_W, iy + ITEM_H - 4), bg, -1)
                    border = (88, 138, 88) if recommended else (78, 112, 166)
                    if is_auto:
                        border = (110, 190, 110)
                    cv2.rectangle(frame, (LIST_X, iy), (LIST_X + LIST_W, iy + ITEM_H - 4), border, 2 if is_auto else 1)
                    cv2.putText(frame, f"{i + 1}.", (LIST_X + 10, iy + 22),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (150, 158, 170), 1, cv2.LINE_AA)
                    cv2.putText(frame, name[:48], (LIST_X + 38, iy + 22),
                                cv2.FONT_HERSHEY_DUPLEX, 0.54, (218, 222, 230), 1, cv2.LINE_AA)
                    cv2.putText(frame, addr, (LIST_X + 38, iy + 42),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (96, 106, 120), 1, cv2.LINE_AA)
                    if is_auto:
                        remaining = max(0.0, AUTO_SELECT_DELAY_S - (time.monotonic() - state.auto_start))
                        cv2.putText(frame, f"auto {remaining:.0f}s", (LIST_X + LIST_W - 82, iy + 22),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 220, 140), 1, cv2.LINE_AA)
                    elif recommended:
                        cv2.putText(frame, "LIKELY OBD", (LIST_X + LIST_W - 108, iy + 22),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (160, 208, 160), 1, cv2.LINE_AA)
                if len(devices) > MAX_VISIBLE:
                    extra = len(devices) - MAX_VISIBLE
                    cv2.putText(frame, f"... and {extra} more", (LIST_X, LIST_Y + MAX_VISIBLE * ITEM_H + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (86, 90, 98), 1, cv2.LINE_AA)

        # Footer — always visible.
        footer_y = H - 36
        cv2.putText(frame, "[ESC] Back", (LIST_X, footer_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (86, 90, 98), 1, cv2.LINE_AA)
        if state.phase in ("results", "error"):
            label = "[R] Retry" if state.phase == "error" else "[R] Rescan"
            cv2.putText(frame, label, (LIST_X + LIST_W - 90, footer_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (86, 90, 98), 1, cv2.LINE_AA)
        if state.phase == "results" and state.devices:
            n_sel = min(len(state.devices), MAX_VISIBLE)
            _put_centered(frame, f"Keys [1-{n_sel}] to select", cx, footer_y,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.38, (86, 90, 98))

        cv2.imshow(WIN, frame)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            return None
        if key in (ord("r"), ord("R")) and state.phase in ("results", "error"):
            scanner.start(auto=False)
        if state.phase == "results":
            for k in range(MAX_VISIBLE):
                if key == ord("1") + k and k < len(state.devices):
                    state.auto_idx = -1
                    state.selected = k
                    break

    name, address = state.devices[state.selected]
    _save_preferred_device(name, address)
    return name, address


def choose_replay_file() -> Optional[str]:
    """Choose a replay CSV session from the log directory."""
    if REPLAY_FILE:
        p = Path(REPLAY_FILE)
        if p.exists() and p.is_file():
            return str(p)

    WIN = STARTUP_WINDOW
    W, H = _ensure_window()
    cx = W // 2

    item_h = 40
    list_w = min(760, W - 100)
    list_x = (W - list_w) // 2
    list_y = 146
    max_visible = min(10, max(4, (H - list_y - 90) // item_h))

    files: list[Path] = []
    hover = -1
    selected: Optional[int] = None
    offset = 0

    def _refresh_files() -> None:
        nonlocal files, offset, selected, hover
        base = Path(LOG_DIR)
        base.mkdir(parents=True, exist_ok=True)
        files = sorted(base.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        offset = 0
        selected = None
        hover = -1

    _refresh_files()

    def _on_mouse(event: int, mx: int, my: int, _flags: int, _param: object) -> None:
        nonlocal hover, selected
        if not files:
            return
        visible = files[offset:offset + max_visible]
        if event == cv2.EVENT_MOUSEMOVE:
            hover = -1
            for i, _ in enumerate(visible):
                iy = list_y + i * item_h
                if list_x <= mx <= list_x + list_w and iy <= my <= iy + item_h - 4:
                    hover = i
                    break
        elif event == cv2.EVENT_LBUTTONDOWN:
            for i, _ in enumerate(visible):
                iy = list_y + i * item_h
                if list_x <= mx <= list_x + list_w and iy <= my <= iy + item_h - 4:
                    selected = offset + i
                    break

    cv2.setMouseCallback(WIN, _on_mouse)

    while selected is None:
        if _win_closed(WIN):
            return None

        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)

        _put_centered(frame, "obd_rs — Replay Session", cx, 68,
                      cv2.FONT_HERSHEY_DUPLEX, 0.92, (232, 232, 232))
        cv2.line(frame, (list_x, 92), (list_x + list_w, 92), (58, 62, 68), 1)

        if not files:
            _put_centered(frame, "No replay CSV files found in logs/", cx, H // 2 - 8,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.56, (160, 164, 172))
            _put_centered(frame, "Press [R] to refresh", cx, H // 2 + 24,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.44, (120, 126, 136))
        else:
            cv2.putText(frame, "Select a recording:", (list_x, list_y - 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46, (130, 136, 144), 1, cv2.LINE_AA)
            visible = files[offset:offset + max_visible]
            for i, f in enumerate(visible):
                idx = offset + i
                iy = list_y + i * item_h
                if hover == i:
                    bg = (56, 66, 78)
                else:
                    bg = (42, 48, 56)
                cv2.rectangle(frame, (list_x, iy), (list_x + list_w, iy + item_h - 4), bg, -1)
                cv2.rectangle(frame, (list_x, iy), (list_x + list_w, iy + item_h - 4), (78, 112, 166), 1)
                cv2.putText(frame, f"{idx + 1}.", (list_x + 10, iy + 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (150, 158, 170), 1, cv2.LINE_AA)
                cv2.putText(frame, f.name[:62], (list_x + 38, iy + 22),
                            cv2.FONT_HERSHEY_DUPLEX, 0.48, (218, 222, 230), 1, cv2.LINE_AA)
                cv2.putText(frame, f"{f.stat().st_size / 1024.0:.1f} KB", (list_x + list_w - 116, iy + 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 126, 136), 1, cv2.LINE_AA)

            if offset > 0:
                cv2.putText(frame, "[UP]", (list_x + list_w + 8, list_y + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 126, 136), 1, cv2.LINE_AA)
            if offset + max_visible < len(files):
                cv2.putText(frame, "[DOWN]", (list_x + list_w + 8, list_y + max_visible * item_h - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 126, 136), 1, cv2.LINE_AA)

        footer_y = H - 36
        cv2.putText(frame, "[ESC] Back", (list_x, footer_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (86, 90, 98), 1, cv2.LINE_AA)
        cv2.putText(frame, "[R] Refresh", (list_x + list_w - 100, footer_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (86, 90, 98), 1, cv2.LINE_AA)
        if files:
            n = min(max_visible, len(files) - offset)
            _put_centered(frame, f"Keys [1-{n}] select visible entries", cx, footer_y,
                          cv2.FONT_HERSHEY_SIMPLEX, 0.38, (86, 90, 98))

        cv2.imshow(WIN, frame)
        key_raw = cv2.waitKeyEx(30)
        key = key_raw & 0xFF
        if key == 27:
            return None
        if key in (ord("r"), ord("R")):
            _refresh_files()
            continue

        # Arrow keys are extended key codes with waitKeyEx on Windows.
        key_up = key_raw == 2490368
        key_down = key_raw == 2621440

        if (key in (ord("w"), ord("W")) or key_up) and offset > 0:
            offset -= 1
            continue
        if (key in (ord("s"), ord("S")) or key_down) and offset + max_visible < len(files):
            offset += 1
            continue
        if files:
            visible_count = min(max_visible, len(files) - offset)
            for k in range(visible_count):
                if key == ord("1") + k:
                    selected = offset + k
                    break

    return str(files[selected])
