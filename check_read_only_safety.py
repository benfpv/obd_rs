import asyncio
from typing import Iterable

from obd_rs.ble_adapter import BleAdapter, UnsafeObdCommandError, ensure_safe_obd_command
from obd_rs.obd_client import ObdClient


EXPECTED_UNSAFE_COMMANDS = [
    "04",
    "08",
    "10 03",
    "11 01",
    "14 FFFF",
    "AT SH 7E0",
    "AT CRA 7E8",
    "2E F1 90 01",
    "31 01 00 00",
]


class RecordingBleAdapter(BleAdapter):
    def __init__(self) -> None:
        super().__init__(force_stub=True)
        self.commands: list[str] = []

    async def send(self, command: str, timeout_s: float = 0.8):
        response = await super().send(command, timeout_s)
        if response is not None:
            self.commands.append(command)
        return response


def _assert_safe(commands: Iterable[str]) -> None:
    for command in commands:
        ensure_safe_obd_command(command)


def _assert_unsafe_rejected(commands: Iterable[str]) -> None:
    for command in commands:
        try:
            ensure_safe_obd_command(command)
        except UnsafeObdCommandError:
            continue
        raise AssertionError(f"unsafe command was incorrectly allowed: {command}")


async def _exercise_live_client() -> list[str]:
    adapter = RecordingBleAdapter()
    client = ObdClient(adapter)

    await adapter.connect(["VEEPEAK TEST"])
    await client.initialize()
    for group in client.pid_groups().values():
        for pid in group:
            await client.query_pid(pid)
    await client.read_active_dtcs()
    await client.read_pending_dtcs()
    await adapter.disconnect()

    return adapter.commands


def main() -> None:
    runtime_commands = asyncio.run(_exercise_live_client())
    _assert_safe(runtime_commands)
    _assert_unsafe_rejected(EXPECTED_UNSAFE_COMMANDS)

    print("read-only safety check passed")
    print("allowed runtime commands:")
    for command in runtime_commands:
        print(f"  {command}")
    print("blocked unsafe command examples:")
    for command in EXPECTED_UNSAFE_COMMANDS:
        print(f"  {command}")


if __name__ == "__main__":
    main()