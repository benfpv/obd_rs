from pathlib import Path

from obd_rs.buffer import TelemetrySample
from obd_rs.data_logger import DataLogger


def test_logger_avoids_overwriting_existing_session_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("obd_rs.data_logger.time.strftime", lambda _fmt: "20260411_120000")
    existing = tmp_path / "session_20260411_120000.csv"
    existing.write_text("keep-me\n", encoding="utf-8")

    logger = DataLogger(log_dir=str(tmp_path), max_bytes=10_000)
    logger.log(TelemetrySample(ts=1.0, values={"rpm": 3000.0}))

    status = logger.status()
    logger.close()

    assert existing.read_text(encoding="utf-8") == "keep-me\n"
    assert (tmp_path / "session_20260411_120000_01.csv").exists()
    assert status.collision_avoided is True
    assert status.rows_written == 1
    assert status.session_name == "session_20260411_120000_01.csv"


def test_logger_reports_retention_pruning(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("obd_rs.data_logger.time.strftime", lambda _fmt: "20260411_120001")
    old_a = tmp_path / "session_20260411_115959.csv"
    old_b = tmp_path / "session_20260411_120000.csv"
    old_a.write_text("a" * 80, encoding="utf-8")
    old_b.write_text("b" * 80, encoding="utf-8")

    logger = DataLogger(log_dir=str(tmp_path), max_bytes=100)
    logger.log(TelemetrySample(ts=1.0, values={"rpm": 3200.0}))

    status = logger.status()
    logger.close()

    assert status.retention_pruned >= 1
    assert not old_a.exists() or not old_b.exists()
    assert (tmp_path / status.session_name).exists()


def test_logger_includes_signal_state_and_connection_context(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("obd_rs.data_logger.time.strftime", lambda _fmt: "20260411_120002")

    logger = DataLogger(log_dir=str(tmp_path), max_bytes=10_000)
    logger.log(
        TelemetrySample(
            ts=1.25,
            values={"rpm": 3000.0, "est_power_kw": 42.5},
            signal_supported={"rpm": True, "oil_temp": False},
            signal_stale={"rpm": False, "oil_temp": True},
            signal_confidence={"rpm": 1.0, "oil_temp": 0.0},
            connection_state="ready",
            connection_detail="ready",
            device_name="VEEPEAK",
            log_mode="cruise",
            dtcs_active=["P0300"],
            dtcs_pending=["P0420"],
        )
    )
    logger.close()

    contents = (tmp_path / "session_20260411_120002.csv").read_text(encoding="utf-8").splitlines()
    header = contents[0].split(",")
    row = contents[1].split(",")
    lookup = dict(zip(header, row))

    assert lookup["rpm"] == "3000.0000"
    assert lookup["est_power_kw"] == "42.5000"
    assert lookup["rpm__supported"] == "1"
    assert lookup["oil_temp__supported"] == "0"
    assert lookup["rpm__stale"] == "0"
    assert lookup["oil_temp__stale"] == "1"
    assert lookup["rpm__confidence"] == "1.0000"
    assert lookup["oil_temp__confidence"] == "0.0000"
    assert lookup["connection_state"] == "ready"
    assert lookup["connection_detail"] == "ready"
    assert lookup["device_name"] == "VEEPEAK"
    assert lookup["log_mode"] == "cruise"
    assert lookup["dtcs_active"] == "P0300"
    assert lookup["dtcs_pending"] == "P0420"