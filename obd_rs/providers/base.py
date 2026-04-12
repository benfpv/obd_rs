from abc import ABC, abstractmethod
from typing import Optional

from ..ble_adapter import CommStats, ConnectionStatus
from ..obd_client import PID


class TelemetryProvider(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def query_pid(self, pid: PID) -> Optional[float]: ...

    @abstractmethod
    async def read_active_dtcs(self) -> list[str]: ...

    @abstractmethod
    async def read_pending_dtcs(self) -> list[str]: ...

    @abstractmethod
    def pid_groups(self) -> dict[str, list[PID]]: ...

    @abstractmethod
    def connection_status(self) -> ConnectionStatus: ...

    @abstractmethod
    async def read_extended_telemetry(self) -> dict[str, Optional[float]]: ...

    @abstractmethod
    def extended_support(self) -> dict[str, bool]: ...

    @abstractmethod
    def extended_field_names(self) -> list[str]: ...

    @abstractmethod
    def comm_stats(self) -> CommStats: ...


class PlaybackCapable(ABC):
    """Mixin for providers that support playback controls."""

    @abstractmethod
    def toggle_pause(self) -> None: ...

    @abstractmethod
    def stop_replay(self) -> None: ...

    @abstractmethod
    def seek_relative(self, delta_s: float) -> None: ...

    @abstractmethod
    def skip_to_speed_threshold(self, speed_kmh: float) -> None: ...
