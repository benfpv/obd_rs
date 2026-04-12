import pytest

from obd_rs.ble_adapter import ConnectionState
from obd_rs.obd_client import HIGH_PIDS
from obd_rs.providers.replay_provider import ReplayTelemetryProvider


def _write_csv(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_replay_provider_loads_and_reads_pid(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(
        csv_path,
        [
            "timestamp,rpm,speed,throttle,dtcs_active,dtcs_pending",
            "1000.0,1200,10,5,P0300,",
            "1001.0,1300,12,6,,P0420",
        ],
    )

    provider = ReplayTelemetryProvider(str(csv_path))
    await provider.start()

    rpm = await provider.query_pid(HIGH_PIDS[0])
    speed = await provider.query_pid(HIGH_PIDS[1])
    dtc_active = await provider.read_active_dtcs()
    dtc_pending = await provider.read_pending_dtcs()

    assert rpm == 1200.0
    assert speed == 10.0
    assert dtc_active == ["P0300"]
    assert dtc_pending == []


@pytest.mark.asyncio
async def test_replay_controls_seek_and_pause(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(
        csv_path,
        [
            "timestamp,rpm,speed,throttle",
            "1000.0,1000,10,5",
            "1002.0,2000,20,15",
            "1004.0,3000,30,25",
        ],
    )

    provider = ReplayTelemetryProvider(str(csv_path))
    await provider.start()

    provider.toggle_pause()
    provider.seek_relative(3.0)

    rpm = await provider.query_pid(HIGH_PIDS[0])
    assert rpm == 2000.0

    provider.stop_replay()
    rpm_reset = await provider.query_pid(HIGH_PIDS[0])
    assert rpm_reset == 1000.0


def test_replay_provider_requires_timestamp(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(csv_path, ["rpm,speed", "1000,10"])

    with pytest.raises(ValueError, match="timestamp"):
        ReplayTelemetryProvider(str(csv_path))


@pytest.mark.asyncio
async def test_replay_status_detail_transitions(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(
        csv_path,
        [
            "timestamp,rpm,speed,throttle",
            "1000.0,1200,10,5",
            "1001.0,1300,12,6",
        ],
    )

    provider = ReplayTelemetryProvider(str(csv_path))
    await provider.start()

    status = provider.connection_status()
    assert status.state == ConnectionState.READY
    assert status.detail.startswith("playing ")

    provider.toggle_pause()
    assert provider.connection_status().detail.startswith("paused ")

    provider.stop_replay()
    assert provider.connection_status().detail == "stopped 0.0s"


@pytest.mark.asyncio
async def test_replay_comm_stats_counts_tx_rx_and_timeouts(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(
        csv_path,
        [
            "timestamp,rpm,speed,throttle",
            "1000.0,1200,10,5",
            "1001.0,,12,6",
        ],
    )

    provider = ReplayTelemetryProvider(str(csv_path))
    await provider.start()

    # First row has rpm value => RX
    _ = await provider.query_pid(HIGH_PIDS[0])
    provider.toggle_pause()
    provider.seek_relative(5.0)
    provider.toggle_pause()
    # Second row missing rpm => timeout path
    _ = await provider.query_pid(HIGH_PIDS[0])

    stats = provider.comm_stats()
    assert stats.tx_count >= 2
    assert stats.rx_count >= 1
    assert stats.timeout_count >= 1


@pytest.mark.asyncio
async def test_skip_to_speed_stays_put_when_no_match(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(
        csv_path,
        [
            "timestamp,rpm,speed,throttle",
            "1000.0,1000,2,5",
            "1001.0,1100,3,6",
            "1002.0,1200,4,7",
        ],
    )
    provider = ReplayTelemetryProvider(str(csv_path))
    await provider.start()

    provider.toggle_pause()
    original_speed = await provider.query_pid(HIGH_PIDS[1])
    provider.skip_to_speed_threshold(50.0)
    after_speed = await provider.query_pid(HIGH_PIDS[1])
    assert after_speed == original_speed


@pytest.mark.asyncio
async def test_skip_to_speed_uses_ge_threshold(tmp_path):
    csv_path = tmp_path / "session.csv"
    _write_csv(
        csv_path,
        [
            "timestamp,rpm,speed,throttle",
            "1000.0,1000,0,5",
            "1001.0,1100,5,6",
            "1002.0,1200,10,7",
        ],
    )
    provider = ReplayTelemetryProvider(str(csv_path))
    await provider.start()

    provider.toggle_pause()
    provider.skip_to_speed_threshold(5.0)
    speed = await provider.query_pid(HIGH_PIDS[1])
    assert speed == 5.0
