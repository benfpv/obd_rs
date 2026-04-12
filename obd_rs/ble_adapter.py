import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .config import (
    BLE_NOTIFY_RETRY_TIMEOUT_S,
    BLE_NOTIFY_TIMEOUT_S,
    BLE_RESPONSE_CHUNK_TIMEOUT_S,
    BLE_SCAN_TIMEOUT_S,
    MAX_RECONNECT_ATTEMPTS,
    MIN_WRITE_INTERVAL_S,
    RECONNECT_DELAY_S,
)

try:
    from bleak import BleakClient, BleakScanner

    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False


ALLOWED_AT_COMMANDS = {
    "ATZ",
    "ATE0",
    "ATL0",
    "ATS0",
    "ATSP0",
}

ALLOWED_OBD_MODES = {
    "01",
    "03",
    "07",
}


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    INITIALIZING = "initializing"
    READY = "ready"
    RECOVERING = "recovering"


@dataclass
class ConnectionStatus:
    state: ConnectionState = ConnectionState.DISCONNECTED
    device_name: str = ""
    detail: str = "idle"


@dataclass
class CommStats:
    """Rolling communication statistics between software and OBD reader."""
    tx_count: int = 0
    rx_count: int = 0
    timeout_count: int = 0
    error_count: int = 0
    tx_bytes: int = 0
    rx_bytes: int = 0
    last_cmd: str = ""
    last_response: str = ""
    recent_log: deque = field(default_factory=lambda: deque(maxlen=8))

    def record_tx(self, cmd: str, payload_len: int) -> None:
        self.tx_count += 1
        self.tx_bytes += payload_len
        self.last_cmd = cmd

    def record_rx(self, response: str) -> None:
        self.rx_count += 1
        self.rx_bytes += len(response)
        self.last_response = response[:40]
        self.recent_log.append((time.monotonic(), "TX", self.last_cmd, "RX", self.last_response))

    def record_timeout(self, cmd: str) -> None:
        self.timeout_count += 1
        self.recent_log.append((time.monotonic(), "TX", cmd, "TIMEOUT", ""))

    def record_error(self, cmd: str, err: str) -> None:
        self.error_count += 1
        self.recent_log.append((time.monotonic(), "TX", cmd, "ERR", err[:30]))


class UnsafeObdCommandError(ValueError):
    pass


# ELM327 BLE UART service/characteristic UUIDs (Veepeak oBDCheck BLE+).
# These are tried first; if the characteristic doesn't support notify we
# fall back to dynamic discovery.
ELM327_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
ELM327_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

_log = logging.getLogger("obd_rs.ble")


def normalize_obd_command(command: str) -> str:
    return "".join(command.strip().upper().split())


def is_safe_obd_command(command: str) -> bool:
    normalized = normalize_obd_command(command)
    if not normalized:
        return False
    if normalized in ALLOWED_AT_COMMANDS:
        return True
    if len(normalized) < 2:
        return False
    return normalized[:2] in ALLOWED_OBD_MODES


def ensure_safe_obd_command(command: str) -> str:
    normalized = normalize_obd_command(command)
    if not is_safe_obd_command(normalized):
        raise UnsafeObdCommandError(f"blocked unsafe OBD command: {normalized or '<empty>'}")
    return normalized


class BleAdapter:
    """BLE transport for Veepeak oBDCheck BLE+.

    Uses bleak for real GATT transport when available.  Falls back to a
    stub that returns ``SIM:<cmd>`` responses when bleak is not installed
    or ``force_stub=True`` is set, allowing UI development without hardware.
    """

    def __init__(self, *, force_stub: bool = False) -> None:
        self.status = ConnectionStatus()
        self._force_stub = force_stub
        self._client: Optional[object] = None
        self._response_buf = ""
        self._response_event = asyncio.Event()
        self._connected = False
        self._device_address: Optional[str] = None
        self._name_hints: list[str] = []
        self._notify_uuid: str = ELM327_CHAR_UUID
        self._write_uuid: str = ELM327_CHAR_UUID
        self._notify_char: Optional[object] = None
        self._write_char: Optional[object] = None
        self._write_with_response: bool = False
        self._send_lock = asyncio.Lock()
        self._last_send_ts: float = 0.0
        self.comm_stats = CommStats()

    # --- public API ---

    async def connect(self, name_hints: list[str], device_address: Optional[str] = None) -> ConnectionStatus:
        self._name_hints = name_hints
        if device_address:
            self._device_address = device_address
        if self._force_stub:
            return await self._connect_stub(name_hints)
        if not BLEAK_AVAILABLE:
            _log.error("bleak package not installed — cannot connect to BLE device")
            self.status = ConnectionStatus(
                state=ConnectionState.DISCONNECTED,
                detail="bleak not installed",
            )
            return self.status
        return await self._connect_ble(name_hints, device_address=self._device_address)

    async def disconnect(self) -> None:
        self._connected = False
        if self._client is not None:
            try:
                client = self._client
                self._client = None
                await client.disconnect()  # type: ignore[union-attr]
            except Exception as exc:
                _log.warning("disconnect error: %s", exc)
        self.status = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="disconnected")

    async def send(self, command: str, timeout_s: float = 0.8) -> Optional[str]:
        command = ensure_safe_obd_command(command)
        if not self._connected:
            return None
        if self._force_stub or not BLEAK_AVAILABLE or self._client is None:
            return await self._send_stub(command)
        return await self._send_ble(command, timeout_s)

    # --- BLE transport ---

    async def _connect_ble(self, name_hints: list[str], device_address: Optional[str] = None) -> ConnectionStatus:
        try:
            if device_address:
                address = device_address
                dev_name = device_address
            else:
                self.status = ConnectionStatus(state=ConnectionState.SCANNING, detail="scanning for OBD adapter")
                device = await self._scan(name_hints)
                if device is None:
                    self.status = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="no device found")
                    return self.status
                address = device.address
                dev_name = device.name or "unknown"

            self._device_address = address
            self.status = ConnectionStatus(
                state=ConnectionState.CONNECTING,
                device_name=dev_name,
                detail="connecting",
            )

            client = BleakClient(address)
            await client.connect()
            self._client = client

            self.status = ConnectionStatus(
                state=ConnectionState.INITIALIZING,
                device_name=dev_name,
                detail="discovering characteristics",
            )

            notify_char, write_char, write_with_response = await self._discover_uart_char(client)
            notify_uuid = str(getattr(notify_char, "uuid", ""))
            write_uuid = str(getattr(write_char, "uuid", ""))
            self._notify_uuid = notify_uuid
            self._write_uuid = write_uuid
            self._notify_char = notify_char
            self._write_char = write_char
            self._write_with_response = write_with_response
            _log.info(
                "using notify=%s  write=%s  response=%s",
                notify_uuid,
                write_uuid,
                write_with_response,
            )

            self.status = ConnectionStatus(
                state=ConnectionState.INITIALIZING,
                device_name=dev_name,
                detail="subscribing to notifications",
            )
            try:
                await asyncio.wait_for(
                    client.start_notify(self._notify_char, self._on_notify),
                    timeout=BLE_NOTIFY_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                _log.warning("start_notify timed out — retrying with forced indicate")
                # Some Windows BLE stacks need the indicate path.
                try:
                    await asyncio.wait_for(
                        client.start_notify(
                            self._notify_char, self._on_notify,
                        ),
                        timeout=BLE_NOTIFY_RETRY_TIMEOUT_S,
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"start_notify on {self._notify_uuid} timed out twice"
                    )

            self._connected = True
            self.status = ConnectionStatus(
                state=ConnectionState.READY,
                device_name=dev_name,
                detail="ready",
            )
            return self.status
        except Exception as exc:
            _log.error("BLE connect failed: %s", exc)
            # Clean up so the adapter releases the device.
            if self._client is not None:
                try:
                    await self._client.disconnect()  # type: ignore[union-attr]
                except Exception:
                    pass
                self._client = None
            self.status = ConnectionStatus(
                state=ConnectionState.DISCONNECTED,
                detail=f"connect failed: {exc}",
            )
            return self.status

    @staticmethod
    async def _scan(name_hints: list[str]) -> Optional[object]:
        upper_hints = [h.upper() for h in name_hints]
        devices = await BleakScanner.discover(timeout=BLE_SCAN_TIMEOUT_S)
        for device in devices:
            name = (device.name or "").upper()
            if any(hint in name for hint in upper_hints):
                return device
        return None

    @staticmethod
    async def _discover_uart_char(client: object) -> tuple[object, object, bool]:
        """Find the best notify + write characteristic on the connected device.

        Strategy:
        1. Try the well-known ELM327 UUID if it supports notify.
        2. Prefer notify + write-without-response on the same service.
        3. Then prefer notify + write on the same service.
        4. Finally use best available notify/write globally.
        """
        from bleak import BleakClient as _BC
        assert isinstance(client, _BC)

        # Log full GATT table for debugging.
        for svc in client.services:
            for char in svc.characteristics:
                _log.info(
                    "  svc=%s  char=%s  props=%s",
                    svc.uuid, char.uuid, char.properties,
                )

        def _is_cccd(uuid: str) -> bool:
            return uuid.lower().startswith("00002902-")

        def _can_notify(props: list[str]) -> bool:
            return "notify" in props or "indicate" in props

        def _can_write_wr(props: list[str]) -> bool:
            return "write" in props

        def _can_write_cmd(props: list[str]) -> bool:
            return "write-without-response" in props

        def _service_rank(svc_uuid: str) -> int:
            u = svc_uuid.lower()
            # Prefer classic transparent UART service first.
            if u.startswith("0000fff0-"):
                return 0
            # Keep 0x6287 as second preference.
            if u.startswith("00006287-"):
                return 1
            return 2

        # 1. Try the default UUID.
        for svc in client.services:
            for char in svc.characteristics:
                if char.uuid == ELM327_CHAR_UUID:
                    if _can_notify(char.properties) and _can_write_cmd(char.properties):
                        return char, char, False
                    if _can_notify(char.properties) and _can_write_wr(char.properties):
                        return char, char, True
                    _log.warning(
                        "default char %s properties=%s — no notify; will discover",
                        char.uuid, char.properties,
                    )

        services = sorted(list(client.services), key=lambda s: _service_rank(s.uuid))

        # 2. Prefer same-service notify + write-without-response.
        for svc in services:
            notify_chars: list[object] = []
            cmd_write_chars: list[object] = []
            req_write_chars: list[object] = []
            for char in svc.characteristics:
                if _is_cccd(char.uuid):
                    continue
                if _can_notify(char.properties):
                    notify_chars.append(char)
                if _can_write_cmd(char.properties):
                    cmd_write_chars.append(char)
                if _can_write_wr(char.properties):
                    req_write_chars.append(char)
            if notify_chars and cmd_write_chars:
                return notify_chars[0], cmd_write_chars[0], False

        # 3. Prefer same-service notify + write-with-response.
        for svc in services:
            notify_chars: list[object] = []
            req_write_chars: list[object] = []
            for char in svc.characteristics:
                if _is_cccd(char.uuid):
                    continue
                if _can_notify(char.properties):
                    notify_chars.append(char)
                if _can_write_wr(char.properties):
                    req_write_chars.append(char)
            if notify_chars and req_write_chars:
                return notify_chars[0], req_write_chars[0], True

        # 4. Global fallback across services.
        notify_char: Optional[object] = None
        cmd_write_char: Optional[object] = None
        req_write_char: Optional[object] = None
        for svc in services:
            for char in svc.characteristics:
                if _is_cccd(char.uuid):
                    continue
                if not notify_char and _can_notify(char.properties):
                    notify_char = char
                if not cmd_write_char and _can_write_cmd(char.properties):
                    cmd_write_char = char
                if not req_write_char and _can_write_wr(char.properties):
                    req_write_char = char
        if notify_char and cmd_write_char:
            return notify_char, cmd_write_char, False
        if notify_char and req_write_char:
            return notify_char, req_write_char, True

        raise RuntimeError("no suitable notify/write characteristics found on device")

    def _on_notify(self, _sender: int, data: bytearray) -> None:
        self._response_buf += data.decode("ascii", errors="replace")
        # Some adapters do not emit a trailing '>' prompt reliably.
        # Wake waiters on any incoming chunk.
        self._response_event.set()

    async def _send_ble(self, command: str, timeout_s: float) -> Optional[str]:
        async with self._send_lock:
            self._response_buf = ""
            self._response_event.clear()
            try:
                now = asyncio.get_running_loop().time()
                dt = now - self._last_send_ts
                if dt < MIN_WRITE_INTERVAL_S:
                    await asyncio.sleep(MIN_WRITE_INTERVAL_S - dt)

                payload = (command + "\r").encode("ascii")
                self.comm_stats.record_tx(command, len(payload))
                await self._client.write_gatt_char(  # type: ignore[union-attr]
                    self._write_char,
                    payload,
                    response=self._write_with_response,
                )
                self._last_send_ts = asyncio.get_running_loop().time()

                # Wait for first response bytes.
                await asyncio.wait_for(self._response_event.wait(), timeout=timeout_s)

                # Then allow short bursts to accumulate full payload.
                deadline = asyncio.get_running_loop().time() + timeout_s
                while ">" not in self._response_buf and asyncio.get_running_loop().time() < deadline:
                    self._response_event.clear()
                    try:
                        await asyncio.wait_for(self._response_event.wait(), timeout=BLE_RESPONSE_CHUNK_TIMEOUT_S)
                    except asyncio.TimeoutError:
                        break

                response = self._response_buf.strip().rstrip(">").strip()
                if response:
                    self.comm_stats.record_rx(response)
                    return response
                return None
            except asyncio.TimeoutError:
                _log.warning("send timeout for command: %s", command)
                self.comm_stats.record_timeout(command)
                return None
            except Exception as exc:
                _log.error("send error: %s", exc)
                self.comm_stats.record_error(command, str(exc))
                await self._handle_transport_error()
                return None

    async def _handle_transport_error(self) -> None:
        self.status = ConnectionStatus(state=ConnectionState.RECOVERING, detail="recovering connection")
        self._connected = False
        if self._client is not None:
            try:
                await self._client.disconnect()  # type: ignore[union-attr]
            except Exception:
                pass
            self._client = None

        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            _log.info("reconnect attempt %d/%d", attempt, MAX_RECONNECT_ATTEMPTS)
            await asyncio.sleep(RECONNECT_DELAY_S)
            # Try stored address first; fall back to re-scan if not found.
            result = await self._connect_ble(self._name_hints, device_address=self._device_address)
            if result.state == ConnectionState.READY:
                return
            if "was not found" in (result.detail or ""):
                _log.info("device not found at %s — will re-scan", self._device_address)
                result = await self._connect_ble(self._name_hints, device_address=None)
                if result.state == ConnectionState.READY:
                    return

        self.status = ConnectionStatus(state=ConnectionState.DISCONNECTED, detail="reconnect failed")

    # --- stub transport (used when bleak is unavailable or force_stub=True) ---

    async def _connect_stub(self, name_hints: list[str]) -> ConnectionStatus:
        self.status = ConnectionStatus(state=ConnectionState.SCANNING, detail="scanning")
        await asyncio.sleep(0.1)
        self.status = ConnectionStatus(state=ConnectionState.CONNECTING, detail="connecting")
        await asyncio.sleep(0.1)
        self.status = ConnectionStatus(
            state=ConnectionState.INITIALIZING,
            device_name=name_hints[0] if name_hints else "VEEPEAK",
            detail="initializing",
        )
        await asyncio.sleep(0.1)
        self._connected = True
        self.status = ConnectionStatus(
            state=ConnectionState.READY,
            device_name=self.status.device_name,
            detail="ready (stub)",
        )
        return self.status

    async def _send_stub(self, command: str) -> Optional[str]:
        await asyncio.sleep(0.01)
        payload = (command + "\r").encode("ascii")
        self.comm_stats.record_tx(command, len(payload))
        response = f"SIM:{command}"
        self.comm_stats.record_rx(response)
        return response
