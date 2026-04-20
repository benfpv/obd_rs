import math
import time
from typing import Optional

from ..ble_adapter import CommStats, ConnectionState, ConnectionStatus
from ..obd_client import EXTENDED_PIDS, HIGH_PIDS, LOW_PIDS, MEDIUM_PIDS, PID
from .base import TelemetryProvider


class SimulatedTelemetryProvider(TelemetryProvider):
    """Synthetic telemetry source, isolated from transport/protocol layers."""

    def __init__(self) -> None:
        self._status = ConnectionStatus(
            state=ConnectionState.READY,
            device_name="SIMULATION",
            detail="synthetic data",
        )
        self._stats = CommStats()

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        self._status = ConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            device_name="SIMULATION",
            detail="stopped",
        )

    async def query_pid(self, pid: PID) -> Optional[float]:
        t = time.time()
        name = pid.name
        cmd = f"{pid.mode}{pid.code}"
        self._stats.record_tx(cmd, len(cmd))
        value: float
        if name == "rpm":
            value = 2200.0 + 1400.0 * (0.5 + 0.5 * math.sin(t * 1.6))
        elif name == "speed":
            value = 55.0 + 60.0 * (0.5 + 0.5 * math.sin(t * 0.35))
        elif name == "throttle":
            value = 12.0 + 82.0 * (0.5 + 0.5 * math.sin(t * 1.2))
        elif name == "engine_load":
            value = 20.0 + 78.0 * (0.5 + 0.5 * math.sin(t * 0.85))
        elif name == "coolant_temp":
            value = 86.0 + 26.0 * (0.5 + 0.5 * math.sin(t * 0.1))
        elif name == "intake_temp":
            value = 26.0 + 14.0 * (0.5 + 0.5 * math.sin(t * 0.27))
        elif name == "stft_b1":
            value = -7.0 + 14.0 * (0.5 + 0.5 * math.sin(t * 1.15))
        elif name == "ltft_b1":
            value = -4.0 + 8.0 * (0.5 + 0.5 * math.sin(t * 0.25))
        elif name == "spark_advance":
            value = 6.0 + 24.0 * (0.5 + 0.5 * math.sin(t * 0.7))
        elif name == "module_voltage":
            value = 13.0 + 1.3 * (0.5 + 0.5 * math.sin(t * 0.2))
        elif name == "maf_gps":
            value = 7.0 + 68.0 * (0.5 + 0.5 * math.sin(t * 0.72))
        elif name == "map_kpa":
            value = 28.0 + 72.0 * (0.5 + 0.5 * math.sin(t * 0.55))
        elif name == "oil_temp":
            value = 84.0 + 40.0 * (0.5 + 0.5 * math.sin(t * 0.08))
        else:
            value = 0.0
        self._stats.record_rx(f"{value:.3f}")
        return value

    async def read_active_dtcs(self) -> list[str]:
        return []

    async def read_pending_dtcs(self) -> list[str]:
        return []

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
        return {
            "maf_gps": True,
            "map_kpa": True,
            "oil_temp": True,
        }

    def comm_stats(self) -> CommStats:
        return self._stats
