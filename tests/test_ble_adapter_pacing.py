import asyncio
import math
from types import SimpleNamespace

import pytest

from obd_rs.ble_adapter import BleAdapter
from obd_rs.config import MIN_WRITE_INTERVAL_S


class _FakeClient:
    def __init__(self, adapter: BleAdapter, clock: dict[str, float]) -> None:
        self._adapter = adapter
        self._clock = clock
        self.write_times: list[float] = []
        self.commands: list[str] = []

    async def write_gatt_char(self, _char, payload: bytes, response: bool = False) -> None:
        del response
        self.write_times.append(self._clock["now"])
        command = payload.decode("ascii").strip()
        self.commands.append(command)
        self._adapter._response_buf = f"41 {command[2:]} 00 >"
        self._adapter._response_event.set()


@pytest.mark.asyncio
async def test_send_ble_enforces_minimum_write_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    adapter = BleAdapter(force_stub=True)
    adapter._force_stub = False
    adapter._connected = True
    adapter._write_char = object()
    adapter._client = _FakeClient(adapter, clock)

    async def _sleep(delay: float) -> None:
        clock["now"] += delay

    monkeypatch.setattr("obd_rs.ble_adapter.asyncio.sleep", _sleep)
    monkeypatch.setattr(
        "obd_rs.ble_adapter.asyncio.get_running_loop",
        lambda: SimpleNamespace(time=lambda: clock["now"]),
    )

    first = await adapter._send_ble("010C", timeout_s=0.2)
    second = await adapter._send_ble("010D", timeout_s=0.2)

    fake_client = adapter._client
    assert first is not None
    assert second is not None
    assert math.isclose(
        fake_client.write_times[1] - fake_client.write_times[0],
        MIN_WRITE_INTERVAL_S,
        rel_tol=0.0,
        abs_tol=1e-9,
    ) or fake_client.write_times[1] - fake_client.write_times[0] > MIN_WRITE_INTERVAL_S


@pytest.mark.asyncio
async def test_send_ble_serializes_concurrent_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 200.0}
    adapter = BleAdapter(force_stub=True)
    adapter._force_stub = False
    adapter._connected = True
    adapter._write_char = object()
    release_first = asyncio.Event()
    first_started = asyncio.Event()
    write_order: list[str] = []

    class _BlockingClient:
        async def write_gatt_char(self, _char, payload: bytes, response: bool = False) -> None:
            del response
            command = payload.decode("ascii").strip()
            write_order.append(command)
            if command == "010C":
                first_started.set()
                await release_first.wait()
            adapter._response_buf = f"41 {command[2:]} 00 >"
            adapter._response_event.set()

    async def _sleep(delay: float) -> None:
        clock["now"] += delay

    adapter._client = _BlockingClient()
    monkeypatch.setattr("obd_rs.ble_adapter.asyncio.sleep", _sleep)
    monkeypatch.setattr(
        "obd_rs.ble_adapter.asyncio.get_running_loop",
        lambda: SimpleNamespace(time=lambda: clock["now"]),
    )

    first_task = asyncio.create_task(adapter._send_ble("010C", timeout_s=0.2))
    await first_started.wait()
    second_task = asyncio.create_task(adapter._send_ble("010D", timeout_s=0.2))
    await asyncio.sleep(0)

    assert write_order == ["010C"]

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert write_order == ["010C", "010D"]
