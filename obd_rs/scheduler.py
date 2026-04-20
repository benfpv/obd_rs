import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .config import SIGNAL_STALE_AGE_S
from .logging_policy import LoggingPolicy
from .models import TelemetryState
from .providers.base import TelemetryProvider

if TYPE_CHECKING:
    from .obd_client import PID

_log = logging.getLogger("obd_rs.scheduler")

_GROUP_ORDER = ("high", "medium", "low", "extended")


@dataclass
class PollDeadlines:
    next_due: dict[str, float] = field(default_factory=dict)
    last_polled: dict[str, float] = field(default_factory=dict)
    last_interval: dict[str, float] = field(default_factory=dict)


class PollScheduler:
    def __init__(self, provider: TelemetryProvider, state: TelemetryState, policy: LoggingPolicy) -> None:
        self.provider = provider
        self.state = state
        self.policy = policy
        self.deadlines = PollDeadlines()

    async def tick(self, now: float) -> None:
        groups = self.provider.pid_groups()
        for group_name in _GROUP_ORDER:
            interval = self._interval_for_group(group_name)
            pids = groups.get(group_name, [])
            if not pids:
                continue
            await self._poll_group(group_name, pids, now, interval)

    def _interval_for_group(self, group_name: str) -> float:
        cadence = self.policy.cadence()
        if group_name == "high":
            return 1.0 / cadence.high_hz
        if group_name == "medium":
            return 1.0 / cadence.medium_hz
        if group_name == "low":
            return 1.0 / cadence.low_hz
        if group_name == "extended":
            return 1.0 / cadence.extended_hz
        raise KeyError(f"unknown poll group: {group_name}")

    async def _poll_group(self, group_name: str, pids: list["PID"], ts: float, interval: float) -> None:
        group_size = max(1, len(pids))
        for idx, pid in enumerate(pids):
            if not self._pid_due(pid.name, ts, interval):
                continue
            try:
                value = await self.provider.query_pid(pid)
                signal = getattr(self.state, pid.name)
                if value is None:
                    signal.stale = True
                    signal.confidence = 0.0
                else:
                    signal.value = value
                    signal.timestamp = ts
                    signal.stale = False
                    signal.confidence = 1.0
                self._mark_polled(pid.name, ts, interval, idx, group_size)
            except (OSError, RuntimeError) as exc:
                _log.warning("poll %s failed: %s", pid.name, exc)
            except Exception as exc:
                _log.warning("poll %s unexpected error: %s: %s", pid.name, type(exc).__name__, exc)
            await asyncio.sleep(0)

    def _pid_due(self, name: str, now: float, interval: float) -> bool:
        next_due = self.deadlines.next_due.get(name, 0.0)
        prev_interval = self.deadlines.last_interval.get(name)
        last_polled = self.deadlines.last_polled.get(name)

        if prev_interval is not None and last_polled is not None and abs(prev_interval - interval) > 1e-9:
            adjusted_due = last_polled + interval
            if interval < prev_interval:
                next_due = min(next_due, adjusted_due)
            else:
                next_due = max(next_due, adjusted_due)
            self.deadlines.next_due[name] = next_due
            self.deadlines.last_interval[name] = interval

        return now >= next_due

    def _mark_polled(self, name: str, now: float, interval: float, index: int, group_size: int) -> None:
        self.deadlines.last_polled[name] = now
        self.deadlines.last_interval[name] = interval
        if name not in self.deadlines.next_due:
            phase_offset = interval * ((index + 1) / group_size)
            self.deadlines.next_due[name] = now + phase_offset
            return
        self.deadlines.next_due[name] = now + interval

    def mark_stale(self, max_age_s: float = SIGNAL_STALE_AGE_S) -> None:
        now = time.monotonic()
        for f in dataclasses.fields(self.state):
            sig = getattr(self.state, f.name)
            # Use monotonic clock to avoid wall-clock jumps causing false stale flags.
            sig.stale = sig.timestamp == 0.0 or (now - sig.timestamp) > max_age_s
