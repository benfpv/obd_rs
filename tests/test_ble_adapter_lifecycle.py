import pytest

from obd_rs.ble_adapter import BleAdapter, ConnectionState, ConnectionStatus, MAX_RECONNECT_ATTEMPTS


class _FakeClient:
    def __init__(self) -> None:
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


@pytest.mark.asyncio
async def test_disconnect_clears_client_and_status() -> None:
    adapter = BleAdapter(force_stub=True)
    fake = _FakeClient()
    adapter._client = fake
    adapter._connected = True

    await adapter.disconnect()

    assert fake.disconnect_calls == 1
    assert adapter._client is None
    assert adapter._connected is False
    assert adapter.status.state == ConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_transport_error_ends_disconnected_after_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = BleAdapter(force_stub=True)
    fake = _FakeClient()
    adapter._client = fake
    adapter._connected = True
    adapter._name_hints = ["VEEPEAK"]
    adapter._device_address = "AA:BB:CC:DD:EE:FF"

    attempts = 0

    async def _no_sleep(_delay: float) -> None:
        return None

    async def _always_fail(_name_hints: list[str], device_address: str | None = None) -> ConnectionStatus:
        nonlocal attempts
        attempts += 1
        return ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="still down")

    monkeypatch.setattr("obd_rs.ble_adapter.asyncio.sleep", _no_sleep)
    monkeypatch.setattr(adapter, "_connect_ble", _always_fail)

    await adapter._handle_transport_error()

    assert fake.disconnect_calls == 1
    assert attempts == MAX_RECONNECT_ATTEMPTS
    assert adapter.status.state == ConnectionState.DISCONNECTED
    assert adapter.status.detail == "reconnect failed"
