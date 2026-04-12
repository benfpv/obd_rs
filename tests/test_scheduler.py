"""Tests for PollScheduler cadence timing, None handling, and stale marking."""

import time

import pytest

from obd_rs.ble_adapter import ConnectionStatus
from obd_rs.config import LogMode
from obd_rs.logging_policy import LoggingPolicy
from obd_rs.models import TelemetryState
from obd_rs.obd_client import HIGH_PIDS, LOW_PIDS, MEDIUM_PIDS, PID
from obd_rs.scheduler import PollScheduler


class _StubProvider:
    """Minimal provider stub returning controlled values."""

    def __init__(self, responses: dict[str, float | None] | None = None) -> None:
        self._responses = responses or {}
        self.queried: list[str] = []

    async def query_pid(self, pid: PID) -> float | None:
        self.queried.append(pid.name)
        return self._responses.get(pid.name, 42.0)

    def pid_groups(self) -> dict[str, list[PID]]:
        return {"high": HIGH_PIDS, "medium": MEDIUM_PIDS, "low": LOW_PIDS}

    def connection_status(self) -> ConnectionStatus:
        return ConnectionStatus()

    async def read_active_dtcs(self) -> list[str]:
        return []

    async def read_pending_dtcs(self) -> list[str]:
        return []

    async def read_extended_telemetry(self) -> dict[str, float | None]:
        return {}

    def extended_support(self) -> dict[str, bool]:
        return {}

    def extended_field_names(self) -> list[str]:
        return []


@pytest.mark.asyncio
async def test_tick_polls_high_group_first() -> None:
    provider = _StubProvider({"rpm": 3000.0, "speed": 60.0, "throttle": 25.0})
    state = TelemetryState()
    policy = LoggingPolicy(mode=LogMode.CRUISE)
    scheduler = PollScheduler(provider, state, policy)

    await scheduler.tick(100.0)

    assert "rpm" in provider.queried
    assert "speed" in provider.queried
    assert "throttle" in provider.queried
    assert state.rpm.value == 3000.0
    assert state.rpm.stale is False
    assert state.rpm.confidence == 1.0


@pytest.mark.asyncio
async def test_tick_cadence_skips_when_interval_not_elapsed() -> None:
    provider = _StubProvider({"rpm": 3000.0, "speed": 60.0, "throttle": 25.0})
    state = TelemetryState()
    policy = LoggingPolicy(mode=LogMode.CRUISE)
    scheduler = PollScheduler(provider, state, policy)

    await scheduler.tick(100.0)
    provider.queried.clear()

    # Tiny time increment — should not re-poll any group.
    await scheduler.tick(100.001)

    assert provider.queried == []


@pytest.mark.asyncio
async def test_none_response_marks_signal_stale() -> None:
    provider = _StubProvider({"rpm": None, "speed": 60.0, "throttle": 25.0})
    state = TelemetryState()
    policy = LoggingPolicy(mode=LogMode.CRUISE)
    scheduler = PollScheduler(provider, state, policy)

    await scheduler.tick(100.0)

    assert state.rpm.stale is True
    assert state.rpm.confidence == 0.0
    # Valid responses should still succeed.
    assert state.speed.value == 60.0
    assert state.speed.stale is False


@pytest.mark.asyncio
async def test_mark_stale_at_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _StubProvider()
    state = TelemetryState()
    policy = LoggingPolicy(mode=LogMode.CRUISE)
    scheduler = PollScheduler(provider, state, policy)

    # Simulate a signal that was updated 1 second ago.
    state.rpm.timestamp = time.monotonic() - 1.0
    state.rpm.stale = False

    scheduler.mark_stale(max_age_s=2.0)
    assert state.rpm.stale is False

    scheduler.mark_stale(max_age_s=0.5)
    assert state.rpm.stale is True


@pytest.mark.asyncio
async def test_mark_stale_zero_age_marks_all() -> None:
    provider = _StubProvider()
    state = TelemetryState()
    policy = LoggingPolicy(mode=LogMode.CRUISE)
    scheduler = PollScheduler(provider, state, policy)

    # Place timestamp slightly in the past to avoid monotonic clock granularity.
    state.rpm.timestamp = time.monotonic() - 0.1
    state.rpm.stale = False

    scheduler.mark_stale(max_age_s=0.0)
    assert state.rpm.stale is True


@pytest.mark.asyncio
async def test_cadence_switch_allows_immediate_repoll() -> None:
    provider = _StubProvider({"rpm": 3000.0, "speed": 60.0, "throttle": 25.0})
    state = TelemetryState()
    policy = LoggingPolicy(mode=LogMode.CRUISE)
    scheduler = PollScheduler(provider, state, policy)

    # First tick at t=100.
    await scheduler.tick(100.0)
    provider.queried.clear()

    # Switch to REALTIME (higher Hz → shorter interval).
    policy.set_mode(LogMode.REALTIME)

    # Tick at t=101 — should re-poll since interval elapsed for new cadence.
    await scheduler.tick(101.0)
    assert "rpm" in provider.queried
