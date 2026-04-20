import csv
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..ble_adapter import CommStats, ConnectionState, ConnectionStatus
from ..obd_client import EXTENDED_PIDS, HIGH_PIDS, LOW_PIDS, MEDIUM_PIDS, PID
from .base import PlaybackCapable, TelemetryProvider

_log = logging.getLogger("obd_rs.replay")


@dataclass
class _ReplayFrame:
    ts: float
    values: dict[str, Optional[float]]
    dtcs_active: list[str]
    dtcs_pending: list[str]


class ReplayTelemetryProvider(TelemetryProvider, PlaybackCapable):
    """Telemetry provider backed by recorded CSV sessions."""

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        self._frames: list[_ReplayFrame] = []
        self._idx = 0
        self._playing = True
        self._playback_speed = 1.0
        self._playback_base_mono = 0.0
        self._playback_base_ts = 0.0
        self._stats = CommStats()
        self._status = ConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            device_name=f"REPLAY:{self._path.name}",
            detail="idle",
        )
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"replay file not found: {self._path}")

        with self._path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise ValueError("replay CSV has no header")
            if "timestamp" not in reader.fieldnames:
                raise ValueError("replay CSV missing required column: timestamp")

            for row in reader:
                ts_raw = row.get("timestamp", "")
                if not ts_raw:
                    continue
                try:
                    ts = float(ts_raw)
                except ValueError:
                    continue

                values: dict[str, Optional[float]] = {}
                for pid in HIGH_PIDS + MEDIUM_PIDS + LOW_PIDS + EXTENDED_PIDS:
                    raw = (row.get(pid.name) or "").strip()
                    if raw == "":
                        values[pid.name] = None
                        continue
                    try:
                        values[pid.name] = float(raw)
                    except ValueError:
                        values[pid.name] = None

                active = [c for c in (row.get("dtcs_active") or "").split(";") if c]
                pending = [c for c in (row.get("dtcs_pending") or "").split(";") if c]
                self._frames.append(
                    _ReplayFrame(
                        ts=ts,
                        values=values,
                        dtcs_active=active,
                        dtcs_pending=pending,
                    )
                )

        if not self._frames:
            raise ValueError("replay CSV has no valid data rows")

        self._frames.sort(key=lambda f: f.ts)
        self._playback_base_ts = self._frames[0].ts
        self._idx = 0

    def _status_detail(self) -> str:
        elapsed = max(0.0, self._frames[self._idx].ts - self._frames[0].ts)
        total = max(0.0, self._frames[-1].ts - self._frames[0].ts)
        if self._playing:
            prefix = "playing"
        else:
            prefix = "paused"
        return f"{prefix} {elapsed:.1f}s/{total:.1f}s"

    async def start(self) -> None:
        self._playback_base_mono = time.monotonic()
        self._playback_base_ts = self._frames[self._idx].ts
        self._status = ConnectionStatus(
            state=ConnectionState.READY,
            device_name=f"REPLAY:{self._path.name}",
            detail=self._status_detail(),
        )

    async def stop(self) -> None:
        self._status = ConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            device_name=f"REPLAY:{self._path.name}",
            detail="stopped",
        )

    def _sync_cursor(self) -> None:
        if not self._playing:
            return
        elapsed = max(0.0, time.monotonic() - self._playback_base_mono)
        target_ts = self._playback_base_ts + elapsed * self._playback_speed
        while self._idx + 1 < len(self._frames) and self._frames[self._idx + 1].ts <= target_ts:
            self._idx += 1
        if self._status.state == ConnectionState.READY:
            self._status.detail = self._status_detail()

    def _current_frame(self) -> _ReplayFrame:
        self._sync_cursor()
        return self._frames[self._idx]

    async def query_pid(self, pid: PID) -> Optional[float]:
        frame = self._current_frame()
        cmd = f"{pid.mode}{pid.code}"
        self._stats.record_tx(cmd, len(cmd))
        value = frame.values.get(pid.name)
        if value is None:
            self._stats.record_timeout(cmd)
        else:
            self._stats.record_rx(f"{value:.3f}")
        return value

    async def read_active_dtcs(self) -> list[str]:
        return list(self._current_frame().dtcs_active)

    async def read_pending_dtcs(self) -> list[str]:
        return list(self._current_frame().dtcs_pending)

    def pid_groups(self) -> dict[str, list[PID]]:
        return {
            "high": HIGH_PIDS,
            "medium": MEDIUM_PIDS,
            "low": LOW_PIDS,
            "extended": EXTENDED_PIDS,
        }

    def connection_status(self) -> ConnectionStatus:
        return self._status

    def extended_support(self) -> dict[str, bool]:
        names = [pid.name for pid in EXTENDED_PIDS]
        return {name: any(f.values.get(name) is not None for f in self._frames) for name in names}

    def comm_stats(self) -> CommStats:
        return self._stats

    # Playback controls (driven by runtime key handling in app).
    def toggle_pause(self) -> None:
        self._playing = not self._playing
        self._playback_base_mono = time.monotonic()
        self._playback_base_ts = self._frames[self._idx].ts
        self._status.detail = self._status_detail()

    def stop_replay(self) -> None:
        self._playing = False
        self._idx = 0
        self._playback_base_mono = time.monotonic()
        self._playback_base_ts = self._frames[0].ts
        self._status.detail = "stopped 0.0s"

    def seek_relative(self, delta_s: float) -> None:
        cur_ts = self._frames[self._idx].ts
        target = cur_ts + delta_s
        if target <= self._frames[0].ts:
            self._idx = 0
        elif target >= self._frames[-1].ts:
            self._idx = len(self._frames) - 1
        else:
            while self._idx > 0 and self._frames[self._idx].ts > target:
                self._idx -= 1
            while self._idx + 1 < len(self._frames) and self._frames[self._idx + 1].ts <= target:
                self._idx += 1
        self._playback_base_mono = time.monotonic()
        self._playback_base_ts = self._frames[self._idx].ts
        if self._status.state == ConnectionState.READY:
            self._status.detail = self._status_detail()

    def skip_to_speed_threshold(self, speed_kmh: float = 5.0) -> None:
        """Skip forward to first frame where speed meets or exceeds threshold."""
        for i in range(self._idx + 1, len(self._frames)):
            speed = self._frames[i].values.get("speed")
            if speed is not None and speed >= speed_kmh:
                self._idx = i
                self._playback_base_mono = time.monotonic()
                self._playback_base_ts = self._frames[self._idx].ts
                if self._status.state == ConnectionState.READY:
                    self._status.detail = self._status_detail()
                return
        _log.debug("no frames with speed >= %.1f kmh found ahead", speed_kmh)
