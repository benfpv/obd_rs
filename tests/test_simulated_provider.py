"""Tests for provider contract, PlaybackCapable mixin, and comm_stats tracking."""

import pytest

from obd_rs.ble_adapter import ConnectionState
from obd_rs.obd_client import HIGH_PIDS, EXTENDED_PIDS
from obd_rs.providers.base import PlaybackCapable, TelemetryProvider
from obd_rs.providers.simulated_provider import SimulatedTelemetryProvider
from obd_rs.providers.live_provider import LiveTelemetryProvider
from obd_rs.providers.replay_provider import ReplayTelemetryProvider


class TestABCInheritance:
    def test_simulated_is_telemetry_provider(self):
        assert issubclass(SimulatedTelemetryProvider, TelemetryProvider)

    def test_live_is_telemetry_provider(self):
        assert issubclass(LiveTelemetryProvider, TelemetryProvider)

    def test_replay_is_telemetry_provider(self):
        assert issubclass(ReplayTelemetryProvider, TelemetryProvider)

    def test_replay_is_playback_capable(self):
        assert issubclass(ReplayTelemetryProvider, PlaybackCapable)

    def test_simulated_is_not_playback_capable(self):
        assert not issubclass(SimulatedTelemetryProvider, PlaybackCapable)

    def test_live_is_not_playback_capable(self):
        assert not issubclass(LiveTelemetryProvider, PlaybackCapable)


class TestSimulatedCommStats:
    @pytest.mark.asyncio
    async def test_comm_stats_persist_across_calls(self):
        provider = SimulatedTelemetryProvider()
        stats1 = provider.comm_stats()
        stats2 = provider.comm_stats()
        assert stats1 is stats2

    @pytest.mark.asyncio
    async def test_query_pid_records_tx_and_rx(self):
        provider = SimulatedTelemetryProvider()
        assert provider.comm_stats().tx_count == 0

        await provider.query_pid(HIGH_PIDS[0])

        stats = provider.comm_stats()
        assert stats.tx_count == 1
        assert stats.rx_count == 1
        assert stats.timeout_count == 0

    @pytest.mark.asyncio
    async def test_multiple_queries_accumulate_stats(self):
        provider = SimulatedTelemetryProvider()
        for pid in HIGH_PIDS:
            await provider.query_pid(pid)

        stats = provider.comm_stats()
        assert stats.tx_count == len(HIGH_PIDS)
        assert stats.rx_count == len(HIGH_PIDS)

    @pytest.mark.asyncio
    async def test_recent_log_populated(self):
        provider = SimulatedTelemetryProvider()
        await provider.query_pid(HIGH_PIDS[0])

        stats = provider.comm_stats()
        assert len(stats.recent_log) == 1
        entry = stats.recent_log[0]
        assert entry[3] == "RX"


class TestSimulatedBasicContract:
    @pytest.mark.asyncio
    async def test_start_sets_ready(self):
        provider = SimulatedTelemetryProvider()
        await provider.start()
        assert provider.connection_status().state == ConnectionState.READY

    @pytest.mark.asyncio
    async def test_stop_sets_disconnected(self):
        provider = SimulatedTelemetryProvider()
        await provider.stop()
        assert provider.connection_status().state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_extended_support_all_true(self):
        provider = SimulatedTelemetryProvider()
        support = provider.extended_support()
        assert all(support.values())
        assert len(support) == len(EXTENDED_PIDS)

    @pytest.mark.asyncio
    async def test_all_standard_pids_return_values(self):
        provider = SimulatedTelemetryProvider()
        for pid in HIGH_PIDS:
            value = await provider.query_pid(pid)
            assert value is not None
