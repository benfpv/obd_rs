"""Tests for BLE command safety validation."""

import pytest

from obd_rs.ble_adapter import (
    UnsafeObdCommandError,
    ensure_safe_obd_command,
    is_safe_obd_command,
    normalize_obd_command,
)


class TestNormalize:
    def test_strips_whitespace(self):
        assert normalize_obd_command("  01 0C  ") == "010C"

    def test_uppercases(self):
        assert normalize_obd_command("atz") == "ATZ"

    def test_collapses_internal_spaces(self):
        assert normalize_obd_command("AT SP 0") == "ATSP0"


class TestIsSafe:
    def test_allowed_at_commands(self):
        for cmd in ("ATZ", "ATE0", "ATL0", "ATS0", "ATSP0"):
            assert is_safe_obd_command(cmd)

    def test_allowed_obd_modes(self):
        assert is_safe_obd_command("010C")
        assert is_safe_obd_command("0300")
        assert is_safe_obd_command("0700")

    def test_blocked_modes(self):
        assert not is_safe_obd_command("04")
        assert not is_safe_obd_command("0803")
        assert not is_safe_obd_command("1003")

    def test_empty(self):
        assert not is_safe_obd_command("")

    def test_single_char(self):
        assert not is_safe_obd_command("A")

    def test_arbitrary_at(self):
        assert not is_safe_obd_command("AT SH 7E0")


class TestEnsureSafe:
    def test_returns_normalized(self):
        assert ensure_safe_obd_command(" 01 0c ") == "010C"

    def test_raises_on_unsafe(self):
        with pytest.raises(UnsafeObdCommandError):
            ensure_safe_obd_command("04")

    def test_raises_on_empty(self):
        with pytest.raises(UnsafeObdCommandError):
            ensure_safe_obd_command("")
