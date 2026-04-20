"""Tests for LiveTelemetryProvider lifecycle, delegation, and extended support."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from obd_rs.ble_adapter import CommStats, ConnectionState, ConnectionStatus
from obd_rs.obd_client import EXTENDED_PIDS, HIGH_PIDS, LOW_PIDS, MEDIUM_PIDS, PID
from obd_rs.providers.live_provider import LiveTelemetryProvider


def _make_provider(
    adapter_state: ConnectionState = ConnectionState.DISCONNECTED,
) -> tuple[LiveTelemetryProvider, MagicMock, MagicMock]:
    adapter = MagicMock()
    adapter.status = ConnectionStatus(state=adapter_state)
    adapter.connect = AsyncMock(
        return_value=ConnectionStatus(state=ConnectionState.READY, detail="ok"),
    )
    adapter.disconnect = AsyncMock()
    adapter.send = AsyncMock(return_value=None)
    adapter.comm_stats = CommStats()

    client = MagicMock()
    client.initialize = AsyncMock()
    client.query_pid = AsyncMock(return_value=42.0)
    client.try_query_pid = AsyncMock(return_value=None)
    client.read_active_dtcs = AsyncMock(return_value=[])
    client.read_pending_dtcs = AsyncMock(return_value=[])
    client.pid_groups = MagicMock(
        return_value={
            "high": HIGH_PIDS,
            "medium": MEDIUM_PIDS,
            "low": LOW_PIDS,
            "extended": EXTENDED_PIDS,
        },
    )

    provider = LiveTelemetryProvider(adapter, client)
    return provider, adapter, client


@pytest.mark.asyncio
async def test_start_connects_initializes_and_probes() -> None:
    provider, adapter, client = _make_provider()
    await provider.start()

    adapter.connect.assert_awaited_once()
    client.initialize.assert_awaited_once()
    # Probe fires try_query_pid for each extended PID.
    assert client.try_query_pid.await_count == len(EXTENDED_PIDS)


@pytest.mark.asyncio
async def test_start_skips_when_already_ready() -> None:
    provider, adapter, client = _make_provider(adapter_state=ConnectionState.READY)
    await provider.start()

    adapter.connect.assert_not_awaited()
    client.initialize.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_handles_connection_failure() -> None:
    provider, adapter, client = _make_provider()
    adapter.connect = AsyncMock(
        return_value=ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="no device"),
    )

    await provider.start()  # Should not raise.

    client.initialize.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_handles_init_exception() -> None:
    provider, adapter, client = _make_provider()
    client.initialize = AsyncMock(side_effect=ConnectionError("init failed"))

    await provider.start()  # Should not raise.


@pytest.mark.asyncio
async def test_stop_always_disconnects() -> None:
    provider, adapter, _client = _make_provider()
    await provider.stop()
    adapter.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_pid_delegates_to_client() -> None:
    provider, _adapter, client = _make_provider()
    pid = HIGH_PIDS[0]
    result = await provider.query_pid(pid)

    client.query_pid.assert_awaited_once_with(pid)
    assert result == 42.0


@pytest.mark.asyncio
async def test_query_pid_returns_none_on_client_none() -> None:
    provider, _adapter, client = _make_provider()
    client.query_pid = AsyncMock(return_value=None)

    result = await provider.query_pid(HIGH_PIDS[0])
    assert result is None


@pytest.mark.asyncio
async def test_extended_support_reflects_probe() -> None:
    provider, adapter, client = _make_provider()

    # Make try_query_pid return a value only for the first extended PID.
    first_name = EXTENDED_PIDS[0].name

    async def _probe_side_effect(pid: PID) -> float | None:
        return 1.0 if pid.name == first_name else None

    client.try_query_pid = AsyncMock(side_effect=_probe_side_effect)

    await provider.start()

    support = provider.extended_support()
    assert support[first_name] is True
    for pid in EXTENDED_PIDS[1:]:
        assert support[pid.name] is False


def test_pid_groups_filter_extended_support() -> None:
    provider, _adapter, client = _make_provider()

    # Manually set support — first supported, rest not.
    first = EXTENDED_PIDS[0]
    provider._extended_support = {first.name: True}
    for pid in EXTENDED_PIDS[1:]:
        provider._extended_support[pid.name] = False

    groups = provider.pid_groups()

    assert groups["high"] == HIGH_PIDS
    assert groups["medium"] == MEDIUM_PIDS
    assert groups["low"] == LOW_PIDS
    assert groups["extended"] == [first]


def test_comm_stats_delegates_to_adapter() -> None:
    provider, adapter, _client = _make_provider()
    adapter.comm_stats.record_tx("010C", 5)
    adapter.comm_stats.record_rx("41 0C 1A F8")
    stats = provider.comm_stats()
    assert stats.tx_count == 1
    assert stats.rx_count == 1
