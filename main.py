import cv2

from obd_rs.app import run
from obd_rs.config import DATA_SOURCE, DataSource
from obd_rs.startup import choose_ble_device, choose_mode, choose_replay_file


if __name__ == "__main__":
    mode = DataSource(DATA_SOURCE) if DATA_SOURCE in ("simulated", "live", "replay") else choose_mode()

    device_address = None
    replay_file = None
    if mode == DataSource.LIVE and not DATA_SOURCE:
        result = choose_ble_device()
        if result is not None:
            device_address = result[1]
        else:
            mode = None
    elif mode == DataSource.REPLAY and not DATA_SOURCE:
        replay_file = choose_replay_file()
        if replay_file is None:
            mode = None

    if mode is not None:
        run(mode, device_address=device_address, replay_file=replay_file)

    cv2.destroyAllWindows()
    cv2.waitKey(1)
