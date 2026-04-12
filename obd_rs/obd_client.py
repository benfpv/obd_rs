import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from .ble_adapter import BleAdapter
from .config import MINIMAL_WRITES

_log = logging.getLogger("obd_rs.obd")


@dataclass(frozen=True)
class PID:
    mode: str
    code: str
    name: str


HIGH_PIDS = [
    PID("01", "0C", "rpm"),
    PID("01", "0D", "speed"),
    PID("01", "11", "throttle"),
]

MEDIUM_PIDS = [
    PID("01", "04", "engine_load"),
    PID("01", "05", "coolant_temp"),
    PID("01", "0F", "intake_temp"),
    PID("01", "06", "stft_b1"),
    PID("01", "07", "ltft_b1"),
    PID("01", "0E", "spark_advance"),
]

LOW_PIDS = [
    PID("01", "42", "module_voltage"),
]

EXTENDED_PIDS = [
    PID("01", "10", "maf_gps"),
    PID("01", "0B", "map_kpa"),
    PID("01", "5C", "oil_temp"),
]


# Standard OBD-II PID decode formulas.
# Each decoder receives (A, B) where A is the first data byte and B the second
# (defaulting to 0 when the PID returns a single byte).
_PID_DECODERS: dict[str, Callable[[int, int], float]] = {
    "rpm": lambda a, b: ((a * 256) + b) / 4.0,
    "speed": lambda a, _b: float(a),
    "throttle": lambda a, _b: a * 100.0 / 255.0,
    "engine_load": lambda a, _b: a * 100.0 / 255.0,
    "coolant_temp": lambda a, _b: float(a - 40),
    "intake_temp": lambda a, _b: float(a - 40),
    "stft_b1": lambda a, _b: (a - 128.0) * 100.0 / 128.0,
    "ltft_b1": lambda a, _b: (a - 128.0) * 100.0 / 128.0,
    "spark_advance": lambda a, _b: a / 2.0 - 64.0,
    "module_voltage": lambda a, b: ((a * 256) + b) / 1000.0,
    "maf_gps": lambda a, b: ((a * 256) + b) / 100.0,
    "map_kpa": lambda a, _b: float(a),
    "oil_temp": lambda a, _b: float(a - 40),
}

# DTC category lookup from first two bits of byte 1.
_DTC_PREFIX = {0: "P", 1: "C", 2: "B", 3: "U"}


class ObdClient:
    """ELM327/OBD protocol boundary for live adapter data."""

    def __init__(self, adapter: BleAdapter) -> None:
        self.adapter = adapter

    async def initialize(self) -> None:
        if MINIMAL_WRITES:
            init_cmds = ["ATE0", "ATSP0"]
        else:
            init_cmds = ["ATZ", "ATE0", "ATL0", "ATS0", "ATSP0"]
        for cmd in init_cmds:
            response = await self.adapter.send(cmd)
            if response is None:
                raise ConnectionError(f"ELM327 init failed: no response to {cmd}")
            _log.debug("init %s -> %s", cmd, response[:40])

    async def query_pid(self, pid: PID) -> Optional[float]:
        cmd = f"{pid.mode}{pid.code}"
        response = await self.adapter.send(cmd)
        if response is None:
            return None
        return self._decode_response(pid, response)

    async def try_query_pid(self, pid: PID) -> Optional[float]:
        """Query a PID, returning None if the ECU doesn't support it."""
        cmd = f"{pid.mode}{pid.code}"
        response = await self.adapter.send(cmd)
        if response is None:
            return None
        if "NO DATA" in response.upper():
            return None
        return self._decode_response(pid, response)

    def _decode_response(self, pid: PID, response: str) -> Optional[float]:
        data_bytes = _parse_elm_response(response, pid.mode, pid.code)
        if data_bytes is None:
            return None
        decoder = _PID_DECODERS.get(pid.name)
        if decoder is None:
            _log.warning("no decoder for PID %s", pid.name)
            return None
        a = data_bytes[0] if len(data_bytes) > 0 else 0
        b = data_bytes[1] if len(data_bytes) > 1 else 0
        return decoder(a, b)

    async def read_active_dtcs(self) -> list[str]:
        response = await self.adapter.send("03")
        if response is None:
            return []
        return _parse_dtc_response(response, "03")

    async def read_pending_dtcs(self) -> list[str]:
        response = await self.adapter.send("07")
        if response is None:
            return []
        return _parse_dtc_response(response, "07")

    def pid_groups(self) -> dict[str, list[PID]]:
        return {"high": HIGH_PIDS, "medium": MEDIUM_PIDS, "low": LOW_PIDS}

    def extended_pid_list(self) -> list[PID]:
        return list(EXTENDED_PIDS)


def _parse_elm_response(response: str, mode: str, code: str) -> Optional[list[int]]:
    """Parse an ELM327 hex response into data bytes.

    Expected format: ``41 0C XX YY`` for mode 01, PID 0C.
    Returns the data bytes after the mode+PID echo, or None on error.
    """
    cleaned = response.replace("SEARCHING...", "").replace("NO DATA", "").strip()
    if not cleaned:
        return None

    try:
        tokens = cleaned.split()
        hex_bytes = [int(t, 16) for t in tokens]
    except ValueError:
        return None

    if len(hex_bytes) < 2:
        return None

    expected_mode = int(mode, 16) + 0x40
    expected_code = int(code, 16)

    if hex_bytes[0] != expected_mode or hex_bytes[1] != expected_code:
        return None

    return hex_bytes[2:]


def _parse_dtc_response(response: str, mode: str) -> list[str]:
    """Parse a mode 03/07 DTC response into DTC code strings."""
    cleaned = response.replace("SEARCHING...", "").replace("NO DATA", "").strip()
    if not cleaned:
        return []

    try:
        tokens = cleaned.split()
        hex_bytes = [int(t, 16) for t in tokens]
    except ValueError:
        return []

    expected_response = int(mode, 16) + 0x40
    if not hex_bytes or hex_bytes[0] != expected_response:
        return []

    data = hex_bytes[1:]
    dtcs: list[str] = []
    for i in range(0, len(data) - 1, 2):
        high, low = data[i], data[i + 1]
        if high == 0 and low == 0:
            continue
        prefix = _DTC_PREFIX.get((high >> 6) & 0x03, "P")
        code_num = ((high & 0x3F) << 8) | low
        dtcs.append(f"{prefix}{code_num:04d}")

    return dtcs
