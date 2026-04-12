from pathlib import Path

from obd_rs import startup


def test_load_preferred_device_missing_file_returns_none(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "startup_device.json"
    monkeypatch.setattr(startup, "_startup_prefs_path", lambda: prefs_path)

    assert startup._load_preferred_device_address() is None


def test_save_then_load_preferred_device_roundtrip(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "startup_device.json"
    monkeypatch.setattr(startup, "_startup_prefs_path", lambda: prefs_path)

    startup._save_preferred_device("VEEPEAK", "AA:BB:CC:DD:EE:FF")

    assert startup._load_preferred_device_address() == "AA:BB:CC:DD:EE:FF"


def test_load_preferred_device_invalid_json_returns_none(monkeypatch, tmp_path: Path) -> None:
    prefs_path = tmp_path / "startup_device.json"
    prefs_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(startup, "_startup_prefs_path", lambda: prefs_path)

    assert startup._load_preferred_device_address() is None
