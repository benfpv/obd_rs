"""Rolling telemetry logger — persists samples to CSV in a logs directory."""

import csv
import dataclasses
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .buffer import TelemetrySample
from .config import LOG_DIR, LOG_FLUSH_INTERVAL_S, LOG_FLUSH_ROWS, LOG_MAX_BYTES
from .models import TelemetryState

_log = logging.getLogger("obd_rs.logger")

_SIGNAL_FIELDS = sorted(f.name for f in dataclasses.fields(TelemetryState))
_DERIVED_FIELDS = ["est_power_kw", "est_torque_nm", "accel_ms2", "inferred_brake"]
_ALL_FIELDS = _SIGNAL_FIELDS + _DERIVED_FIELDS
_SIGNAL_SUPPORTED_FIELDS = [f"{name}__supported" for name in _SIGNAL_FIELDS]
_SIGNAL_STALE_FIELDS = [f"{name}__stale" for name in _SIGNAL_FIELDS]
_SIGNAL_CONFIDENCE_FIELDS = [f"{name}__confidence" for name in _SIGNAL_FIELDS]
_SESSION_FIELDS = ["connection_state", "connection_detail", "device_name", "log_mode"]


@dataclass(frozen=True)
class LoggerStatus:
    active: bool
    session_name: str
    rows_written: int
    rows_pending_flush: int
    retention_pruned: int
    collision_avoided: bool
    last_error: str = ""


class DataLogger:
    """Append-only CSV logger with rolling size enforcement."""

    def __init__(
        self,
        log_dir: str = LOG_DIR,
        max_bytes: int = LOG_MAX_BYTES,
    ) -> None:
        self._dir = Path(log_dir)
        self._max_bytes = max_bytes
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file: Optional[object] = None
        self._writer: Optional[csv.writer] = None
        self._session_path: Optional[Path] = None
        self._session_name = "pending"
        self._rows_since_flush = 0
        self._rows_written = 0
        self._last_flush = time.monotonic()
        self._retention_pruned = 0
        self._collision_avoided = False
        self._last_error = ""

    def log(self, sample: TelemetrySample) -> None:
        if self._file is None:
            self._open()
        self._write_row(sample)

    def status(self) -> LoggerStatus:
        return LoggerStatus(
            active=self._file is not None,
            session_name=self._session_name,
            rows_written=self._rows_written,
            rows_pending_flush=self._rows_since_flush,
            retention_pruned=self._retention_pruned,
            collision_avoided=self._collision_avoided,
            last_error=self._last_error,
        )

    def _open(self) -> None:
        self._retention_pruned = self._enforce_size_limit()
        path, collision_avoided = self._next_session_path()
        self._collision_avoided = collision_avoided
        self._session_path = path
        self._session_name = path.name
        fh = open(path, "x", newline="", encoding="utf-8")  # noqa: SIM115
        try:
            writer = csv.writer(fh)
            writer.writerow(
                ["timestamp"]
                + _ALL_FIELDS
                + _SIGNAL_SUPPORTED_FIELDS
                + _SIGNAL_STALE_FIELDS
                + _SIGNAL_CONFIDENCE_FIELDS
                + _SESSION_FIELDS
                + ["dtcs_active", "dtcs_pending"]
            )
        except Exception:
            fh.close()
            path.unlink(missing_ok=True)
            raise
        self._file = fh
        self._writer = writer
        _log.info("logging telemetry to %s", path)

    def _next_session_path(self) -> tuple[Path, bool]:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = self._dir / f"session_{stamp}.csv"
        if not base.exists():
            return base, False
        for index in range(1, 1000):
            candidate = self._dir / f"session_{stamp}_{index:02d}.csv"
            if not candidate.exists():
                return candidate, True
        raise RuntimeError("unable to allocate unique session log filename")

    def _write_row(self, sample: TelemetrySample) -> None:
        if self._writer is None:
            return
        row = [f"{sample.ts:.3f}"]
        for field in _ALL_FIELDS:
            val = sample.values.get(field)
            row.append(f"{val:.4f}" if val is not None else "")
        for field in _SIGNAL_FIELDS:
            row.append("1" if sample.signal_supported.get(field, False) else "0")
        for field in _SIGNAL_FIELDS:
            row.append("1" if sample.signal_stale.get(field, True) else "0")
        for field in _SIGNAL_FIELDS:
            row.append(f"{sample.signal_confidence.get(field, 0.0):.4f}")
        row.append(sample.connection_state)
        row.append(sample.connection_detail)
        row.append(sample.device_name)
        row.append(sample.log_mode)
        row.append(";".join(sample.dtcs_active) if sample.dtcs_active else "")
        row.append(";".join(sample.dtcs_pending) if sample.dtcs_pending else "")
        self._writer.writerow(row)
        self._rows_written += 1
        self._rows_since_flush += 1
        now = time.monotonic()
        if self._rows_since_flush >= LOG_FLUSH_ROWS or now - self._last_flush >= LOG_FLUSH_INTERVAL_S:
            self._flush()

    def _flush(self) -> None:
        if self._file is not None:
            self._file.flush()
        self._rows_since_flush = 0
        self._last_flush = time.monotonic()

    def _enforce_size_limit(self) -> int:
        try:
            files = sorted(
                self._dir.glob("session_*.csv"),
                key=lambda p: p.stat().st_mtime,
            )
        except OSError:
            return 0
        total = sum(f.stat().st_size for f in files)
        pruned = 0
        while total > self._max_bytes and files:
            oldest = files.pop(0)
            size = oldest.stat().st_size
            try:
                oldest.unlink()
                total -= size
                pruned += 1
                _log.info("pruned old log %s (%d bytes)", oldest.name, size)
            except OSError as exc:
                _log.warning("failed to prune %s: %s", oldest.name, exc)
                continue
        return pruned

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except OSError:
                pass
            self._file = None
            self._writer = None
