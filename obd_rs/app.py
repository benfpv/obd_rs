import asyncio
import dataclasses
import logging
import time
from typing import Callable, Optional

import cv2

from .alerts import AlertEngine
from .ble_adapter import BleAdapter, ConnectionState, ConnectionStatus
from .buffer import SampleRingBuffer, TelemetrySample
from .config import (
    DTC_READ_INTERVAL_S,
    DataSource,
    EXTENDED_READ_INTERVAL_S,
    FPS,
    LOG_MIN_SIGNAL_FIELDS,
    LogMode,
    RECONNECT_INTERVAL_S,
    SIGNAL_STALE_AGE_S,
)
from .data_processing import DerivedTelemetry, TelemetryProcessor
from .data_logger import DataLogger
from .logging_policy import LoggingPolicy
from .models import TelemetryState
from .obd_client import ObdClient
from .providers import LiveTelemetryProvider, ReplayTelemetryProvider, SimulatedTelemetryProvider
from .providers.base import PlaybackCapable, TelemetryProvider
from .scheduler import PollScheduler
from .ui import DashboardUI

_log = logging.getLogger("obd_rs.app")

_TELEMETRY_FIELDS = {f.name for f in dataclasses.fields(TelemetryState)}



class ObdDashboardApp:
    def __init__(self, mode: DataSource = DataSource.SIMULATED, device_address: Optional[str] = None, replay_file: Optional[str] = None) -> None:
        self.mode = mode
        self.telemetry = TelemetryState()
        self._log_to_csv = mode == DataSource.LIVE
        self.policy = LoggingPolicy(mode=LogMode.CRUISE)
        self.provider: TelemetryProvider = self._build_provider(mode, device_address, replay_file)
        self.scheduler = PollScheduler(self.provider, self.telemetry, self.policy)
        self.alerts = AlertEngine()
        self.ui = DashboardUI()
        self.samples = SampleRingBuffer(capacity=12000)
        self.data_logger = DataLogger()
        self.running = True
        self._extended_applied = False
        self._connect_task: Optional[asyncio.Task] = None
        self.processor = TelemetryProcessor()
        self._dtcs_active: list[str] = []
        self._dtcs_pending: list[str] = []
        self._next_dtc_read = 0.0
        self._next_extended_read = 0.0
        self._next_reconnect = 0.0

    @staticmethod
    def _build_provider(mode: DataSource, device_address: Optional[str] = None, replay_file: Optional[str] = None) -> TelemetryProvider:
        if mode == DataSource.LIVE:
            adapter = BleAdapter()
            client = ObdClient(adapter)
            return LiveTelemetryProvider(adapter=adapter, client=client, device_address=device_address)
        if mode == DataSource.REPLAY:
            if not replay_file:
                raise ValueError("replay mode requires replay_file")
            return ReplayTelemetryProvider(replay_file)
        return SimulatedTelemetryProvider()

    def _handle_runtime_key(self, key: int) -> None:
        if not isinstance(self.provider, PlaybackCapable):
            return

        if key in (ord("p"), ord("P")):
            self.provider.toggle_pause()
        elif key in (ord("o"), ord("O")):
            self.provider.stop_replay()
        elif key in (ord("j"), ord("J")):
            self.provider.seek_relative(-5.0)
        elif key in (ord("l"), ord("L")):
            self.provider.seek_relative(5.0)
        elif key in (ord("s"), ord("S")):
            self.provider.skip_to_speed_threshold(5.0)

    async def start(self) -> None:
        self._begin_connect()
        frame_dt = 1.0 / FPS

        try:
            while self.running:
                frame_start = time.monotonic()
                now = time.monotonic()
                conn = self.provider.connection_status()

                self._maintain_connection(now, conn)
                await self._acquire(now, conn)
                derived = self._process(time.time(), conn)

                try:
                    keep_running = self.ui.draw(
                        telemetry=self.telemetry,
                        derived=derived,
                        issues=self.alerts.issues(),
                        possible=self.alerts.possible_issues(),
                        conn=conn,
                        policy=self.policy,
                        logger_status=self.data_logger.status(),
                        comm_stats=self.provider.comm_stats(),
                        data_source=self.mode,
                        on_key=self._handle_runtime_key,
                        logging_enabled=self._log_to_csv,
                    )
                except cv2.error as exc:
                    _log.warning("UI draw error (window closed?): %s", exc)
                    self.running = False
                    break
                if not keep_running:
                    self.running = False
                    break

                elapsed = time.monotonic() - frame_start
                sleep_s = max(0.0, frame_dt - elapsed)
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
        finally:
            if self._connect_task and not self._connect_task.done():
                self._connect_task.cancel()
                try:
                    await self._connect_task
                except asyncio.CancelledError:
                    pass
            await self.provider.stop()
            self.data_logger.close()
            cv2.destroyAllWindows()

    def _maintain_connection(self, now: float, conn: ConnectionStatus) -> None:
        if conn.state == ConnectionState.READY and not self._extended_applied:
            self._apply_extended_support(self.provider.extended_support())
            self._extended_applied = True
        if conn.state == ConnectionState.DISCONNECTED and now >= self._next_reconnect:
            self._begin_connect()
            self._next_reconnect = now + RECONNECT_INTERVAL_S

    async def _acquire(self, now: float, conn: ConnectionStatus) -> None:
        if conn.state != ConnectionState.READY:
            self._dtcs_active = []
            self._dtcs_pending = []
            self.scheduler.mark_stale(max_age_s=0.0)
            return

        try:
            await self.scheduler.tick(now)
        except (OSError, RuntimeError) as exc:
            _log.error("scheduler tick failed: %s", exc)
        except Exception as exc:
            _log.error("scheduler tick unexpected error: %s: %s", type(exc).__name__, exc)
        self.scheduler.mark_stale(max_age_s=SIGNAL_STALE_AGE_S)

        if now >= self._next_dtc_read:
            try:
                self._dtcs_active = await self.provider.read_active_dtcs()
                self._dtcs_pending = await self.provider.read_pending_dtcs()
            except (OSError, RuntimeError) as exc:
                _log.error("DTC read failed: %s", exc)
            except Exception as exc:
                _log.error("DTC read unexpected error: %s: %s", type(exc).__name__, exc)
            self._next_dtc_read = now + DTC_READ_INTERVAL_S

        if now >= self._next_extended_read:
            try:
                extended = await self.provider.read_extended_telemetry()
                self._apply_extended_values(now, extended)
            except (OSError, RuntimeError) as exc:
                _log.error("extended telemetry read failed: %s", exc)
                self._mark_extended_stale()
            except Exception as exc:
                _log.error("extended read unexpected error: %s: %s", type(exc).__name__, exc)
                self._mark_extended_stale()
            self._next_extended_read = now + EXTENDED_READ_INTERVAL_S

    def _process(self, now_wall: float, conn: ConnectionStatus) -> DerivedTelemetry:
        self.alerts.update_from_state(self.telemetry, self._dtcs_active, self._dtcs_pending)
        derived = self.processor.process(self.telemetry)
        self._capture_sample(now_wall, conn, derived)
        return derived

    def _begin_connect(self) -> None:
        """Initiate provider connection in the background."""
        if self._connect_task is not None and not self._connect_task.done():
            return
        self._extended_applied = False
        self._connect_task = asyncio.create_task(self._safe_connect())

    async def _safe_connect(self) -> None:
        try:
            await self.provider.start()
        except Exception as exc:
            _log.error("connection attempt failed: %s", exc)

    def _apply_extended_support(self, support_map: dict[str, bool]) -> None:
        for key, supported in support_map.items():
            if key in _TELEMETRY_FIELDS:
                sig = getattr(self.telemetry, key)
                sig.supported = bool(supported)

    def _apply_extended_values(self, ts: float, values: dict[str, Optional[float]]) -> None:
        for key, value in values.items():
            if key not in _TELEMETRY_FIELDS:
                continue
            sig = getattr(self.telemetry, key)
            if value is None:
                sig.value = None
                sig.stale = True
                continue
            sig.value = float(value)
            sig.timestamp = ts
            sig.stale = False
            sig.confidence = 1.0

    def _mark_extended_stale(self) -> None:
        """Mark all extended-group signals stale after a read failure."""
        for name in self.provider.extended_field_names():
            if name in _TELEMETRY_FIELDS:
                sig = getattr(self.telemetry, name)
                sig.stale = True

    def _capture_sample(self, ts: float, conn: ConnectionStatus, derived: DerivedTelemetry) -> None:
        values: dict[str, float] = {}
        signal_supported: dict[str, bool] = {}
        signal_stale: dict[str, bool] = {}
        signal_confidence: dict[str, float] = {}
        for name in _TELEMETRY_FIELDS:
            sig = getattr(self.telemetry, name)
            signal_supported[name] = bool(sig.supported)
            signal_stale[name] = bool(sig.stale)
            signal_confidence[name] = float(sig.confidence)
            if sig.value is not None:
                values[name] = float(sig.value)

        raw_signal_count = len(values)
        values["est_power_kw"] = derived.est_power_kw
        values["est_torque_nm"] = derived.est_torque_nm
        values["accel_ms2"] = derived.accel_ms2
        values["inferred_brake"] = derived.inferred_brake

        sample = TelemetrySample(
            ts=ts,
            values=values,
            signal_supported=signal_supported,
            signal_stale=signal_stale,
            signal_confidence=signal_confidence,
            connection_state=conn.state.value,
            connection_detail=conn.detail,
            device_name=conn.device_name,
            log_mode=self.policy.mode.value,
            dtcs_active=list(self._dtcs_active),
            dtcs_pending=list(self._dtcs_pending),
        )
        self.samples.push(sample)
        should_log = (
            self._log_to_csv
            and conn.state == ConnectionState.READY
            and raw_signal_count >= LOG_MIN_SIGNAL_FIELDS
        )
        if should_log:
            self.data_logger.log(sample)


def run(mode: DataSource = DataSource.SIMULATED, device_address: Optional[str] = None, replay_file: Optional[str] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = ObdDashboardApp(mode=mode, device_address=device_address, replay_file=replay_file)
    asyncio.run(app.start())
