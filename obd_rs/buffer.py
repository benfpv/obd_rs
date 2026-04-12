from collections import deque
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class TelemetrySample:
    ts: float
    values: dict[str, float]
    signal_supported: dict[str, bool] = field(default_factory=dict)
    signal_stale: dict[str, bool] = field(default_factory=dict)
    signal_confidence: dict[str, float] = field(default_factory=dict)
    connection_state: str = ""
    connection_detail: str = ""
    device_name: str = ""
    log_mode: str = ""
    dtcs_active: list[str] = field(default_factory=list)
    dtcs_pending: list[str] = field(default_factory=list)


class SampleRingBuffer:
    """In-memory sample ring buffer with read access."""

    def __init__(self, capacity: int = 6000) -> None:
        self._buf: deque[TelemetrySample] = deque(maxlen=capacity)

    def push(self, sample: TelemetrySample) -> None:
        self._buf.append(sample)

    def latest(self) -> Optional[TelemetrySample]:
        return self._buf[-1] if self._buf else None

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self) -> Iterator[TelemetrySample]:
        return iter(self._buf)

    def window(self, last_n: int) -> list[TelemetrySample]:
        """Return the most recent *last_n* samples."""
        if last_n >= len(self._buf):
            return list(self._buf)
        return list(self._buf)[-last_n:]

    def since(self, ts: float) -> list[TelemetrySample]:
        """Return all samples with timestamp >= *ts*."""
        return [s for s in self._buf if s.ts >= ts]
