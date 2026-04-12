import logging
from typing import Optional

from ..ble_adapter import BleAdapter, CommStats, ConnectionState, ConnectionStatus
from ..config import VEEPEAK_NAME_HINTS
from ..obd_client import EXTENDED_PIDS, ObdClient, PID
from .base import TelemetryProvider

_log = logging.getLogger("obd_rs.live")

class LiveTelemetryProvider(TelemetryProvider):
    """Live adapter provider. Uses BLE transport + OBD protocol client."""

    def __init__(self, adapter: BleAdapter, client: ObdClient, device_address: Optional[str] = None) -> None:
        self.adapter = adapter
        self.client = client
        self._device_address = device_address
        self._extended_support: dict[str, bool] = {}

    async def start(self) -> None:
        """Attempt connection. Safe to call multiple times. Does not raise."""
        if self.adapter.status.state == ConnectionState.READY:
            return
        try:
            status = await self.adapter.connect(VEEPEAK_NAME_HINTS, device_address=self._device_address)
            if status.state == ConnectionState.READY:
                await self.client.initialize()
                self._extended_support = await self._probe_extended_support()
            else:
                _log.warning("connection not established: %s", status.detail)
        except Exception as exc:
            _log.error("provider start failed: %s", exc)

    async def stop(self) -> None:
        await self.adapter.disconnect()

    async def query_pid(self, pid: PID) -> Optional[float]:
        return await self.client.query_pid(pid)

    async def read_active_dtcs(self) -> list[str]:
        return await self.client.read_active_dtcs()

    async def read_pending_dtcs(self) -> list[str]:
        return await self.client.read_pending_dtcs()

    def pid_groups(self) -> dict[str, list[PID]]:
        return self.client.pid_groups()

    def connection_status(self) -> ConnectionStatus:
        return self.adapter.status

    async def read_extended_telemetry(self) -> dict[str, Optional[float]]:
        values: dict[str, Optional[float]] = {}
        for pid in EXTENDED_PIDS:
            if self._extended_support.get(pid.name, False):
                values[pid.name] = await self.client.try_query_pid(pid)
            else:
                values[pid.name] = None
        return values

    def extended_support(self) -> dict[str, bool]:
        return dict(self._extended_support)

    def extended_field_names(self) -> list[str]:
        return [pid.name for pid in EXTENDED_PIDS]

    def comm_stats(self) -> CommStats:
        return self.adapter.comm_stats

    async def _probe_extended_support(self) -> dict[str, bool]:
        """Probe which extended PIDs are supported by the ECU."""
        support: dict[str, bool] = {}
        for pid in EXTENDED_PIDS:
            result = await self.client.try_query_pid(pid)
            support[pid.name] = result is not None
            _log.info("extended PID %s: %s", pid.name, "supported" if support[pid.name] else "unsupported")
        return support
