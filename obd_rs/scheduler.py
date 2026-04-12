import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass

from .config import SIGNAL_STALE_AGE_S
from .logging_policy import LoggingPolicy
from .models import TelemetryState
from .providers.base import TelemetryProvider

_log = logging.getLogger("obd_rs.scheduler")


@dataclass
class PollDeadlines:
    high: float = 0.0
    medium: float = 0.0
    low: float = 0.0


class PollScheduler:
    def __init__(self, provider: TelemetryProvider, state: TelemetryState, policy: LoggingPolicy) -> None:
        self.provider = provider
        self.state = state
        self.policy = policy
        self.deadlines = PollDeadlines()

    async def tick(self, now: float) -> None:
        cadence = self.policy.cadence()

        if now >= self.deadlines.high:
            await self._poll_group("high", now)
            self.deadlines.high = now + 1.0 / cadence.high_hz

        if now >= self.deadlines.medium:
            await self._poll_group("medium", now)
            self.deadlines.medium = now + 1.0 / cadence.medium_hz

        if now >= self.deadlines.low:
            await self._poll_group("low", now)
            self.deadlines.low = now + 1.0 / cadence.low_hz

    async def _poll_group(self, group_name: str, ts: float) -> None:
        groups = self.provider.pid_groups()
        for pid in groups[group_name]:
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
            except (OSError, RuntimeError) as exc:
                _log.warning("poll %s failed: %s", pid.name, exc)
            except Exception as exc:
                _log.warning("poll %s unexpected error: %s: %s", pid.name, type(exc).__name__, exc)
            await asyncio.sleep(0)

    def mark_stale(self, max_age_s: float = SIGNAL_STALE_AGE_S) -> None:
        now = time.monotonic()
        for f in dataclasses.fields(self.state):
            sig = getattr(self.state, f.name)
            # Use monotonic clock to avoid wall-clock jumps causing false stale flags.
            sig.stale = sig.timestamp == 0.0 or (now - sig.timestamp) > max_age_s
