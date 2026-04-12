import argparse
import asyncio

from obd_rs.ble_adapter import BleAdapter, ConnectionState
from obd_rs.config import VEEPEAK_NAME_HINTS


async def _disconnect_once(device_address: str | None) -> int:
    adapter = BleAdapter()
    try:
        status = await adapter.connect(VEEPEAK_NAME_HINTS, device_address=device_address)
        if status.state == ConnectionState.READY:
            print(f"Connected to {status.device_name or 'device'}; disconnecting...")
        else:
            print(f"Connection not ready: {status.detail}")
    finally:
        await adapter.disconnect()
        print("Adapter disconnect attempted.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Best-effort BLE disconnect for the OBD adapter.",
    )
    parser.add_argument(
        "--address",
        default=None,
        help="Optional BLE MAC/address to target directly.",
    )
    args = parser.parse_args()
    return asyncio.run(_disconnect_once(args.address))


if __name__ == "__main__":
    raise SystemExit(main())
