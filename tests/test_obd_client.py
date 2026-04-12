"""Tests for OBD-II response decoder and DTC parser."""

import pytest

from obd_rs.obd_client import (
    PID,
    _parse_dtc_response,
    _parse_elm_response,
    ObdClient,
)
from obd_rs.ble_adapter import BleAdapter


# --- ELM response parsing ---

class TestParseElmResponse:
    def test_mode01_rpm(self):
        # 41 0C 1A F8 → RPM = (0x1A*256 + 0xF8) / 4 = 1726.0
        result = _parse_elm_response("41 0C 1A F8", "01", "0C")
        assert result == [0x1A, 0xF8]

    def test_mode01_speed(self):
        # 41 0D 3C → speed = 60
        result = _parse_elm_response("41 0D 3C", "01", "0D")
        assert result == [0x3C]

    def test_mode01_coolant(self):
        # 41 05 7B → coolant_temp = 123 - 40 = 83
        result = _parse_elm_response("41 05 7B", "01", "05")
        assert result == [0x7B]

    def test_wrong_mode_returns_none(self):
        result = _parse_elm_response("42 0C 1A F8", "01", "0C")
        assert result is None

    def test_wrong_pid_returns_none(self):
        result = _parse_elm_response("41 0D 1A F8", "01", "0C")
        assert result is None

    def test_no_data_returns_none(self):
        result = _parse_elm_response("NO DATA", "01", "0C")
        assert result is None

    def test_searching_stripped(self):
        result = _parse_elm_response("SEARCHING...\r41 0D 3C", "01", "0D")
        assert result == [0x3C]

    def test_empty_returns_none(self):
        assert _parse_elm_response("", "01", "0C") is None

    def test_garbage_returns_none(self):
        assert _parse_elm_response("NOT HEX AT ALL", "01", "0C") is None


class TestPidDecoding:
    """Integration test using ObdClient._decode_response."""

    def _make_client(self):
        adapter = BleAdapter(force_stub=True)
        return ObdClient(adapter)

    def test_rpm_decode(self):
        client = self._make_client()
        pid = PID("01", "0C", "rpm")
        val = client._decode_response(pid, "41 0C 1A F8")
        assert abs(val - 1726.0) < 0.1

    def test_speed_decode(self):
        client = self._make_client()
        pid = PID("01", "0D", "speed")
        val = client._decode_response(pid, "41 0D 3C")
        assert val == 60.0

    def test_coolant_decode(self):
        client = self._make_client()
        pid = PID("01", "05", "coolant_temp")
        val = client._decode_response(pid, "41 05 7B")
        assert val == 83.0

    def test_throttle_decode(self):
        client = self._make_client()
        pid = PID("01", "11", "throttle")
        val = client._decode_response(pid, "41 11 FF")
        assert abs(val - 100.0) < 0.1

    def test_voltage_decode(self):
        client = self._make_client()
        pid = PID("01", "42", "module_voltage")
        # 41 42 33 10 → (0x33*256 + 0x10) / 1000 = 13.072
        val = client._decode_response(pid, "41 42 33 10")
        assert abs(val - 13.072) < 0.01

    def test_stft_decode(self):
        client = self._make_client()
        pid = PID("01", "06", "stft_b1")
        # 41 06 80 → (128 - 128) * 100 / 128 = 0.0
        val = client._decode_response(pid, "41 06 80")
        assert abs(val) < 0.1

    def test_spark_decode(self):
        client = self._make_client()
        pid = PID("01", "0E", "spark_advance")
        # 41 0E 80 → 128/2 - 64 = 0.0
        val = client._decode_response(pid, "41 0E 80")
        assert abs(val) < 0.1

    def test_unknown_pid_returns_none(self):
        client = self._make_client()
        pid = PID("01", "FF", "unknown_thing")
        val = client._decode_response(pid, "41 FF 42")
        assert val is None

    def test_bad_response_returns_none(self):
        client = self._make_client()
        pid = PID("01", "0C", "rpm")
        val = client._decode_response(pid, "GARBAGE")
        assert val is None


# --- DTC parsing ---

class TestDtcParsing:
    def test_active_dtcs(self):
        result = _parse_dtc_response("43 01 03 02 10", "03")
        assert result == ["P0259", "P0528"]

    def test_no_dtcs(self):
        result = _parse_dtc_response("43 00 00 00 00", "03")
        assert result == []

    def test_pending_dtcs_mode07(self):
        result = _parse_dtc_response("47 01 03", "07")
        assert result == ["P0259"]

    def test_empty_response(self):
        assert _parse_dtc_response("", "03") == []

    def test_no_data_response(self):
        assert _parse_dtc_response("NO DATA", "03") == []

    def test_wrong_response_code(self):
        assert _parse_dtc_response("43 01 03", "07") == []

    def test_dtc_prefix_mapping(self):
        # 0x40 = 01 00 00 00 in top 2 bits → prefix "C"
        # High byte = 0x40, low byte = 0x01 → C0001
        result = _parse_dtc_response("43 40 01", "03")
        assert result == ["C0001"]

    def test_dtc_numeric_encoding_with_powertrain_prefix(self):
        # Current parser treats the payload as a compact 14-bit numeric code.
        # High byte = 0x03, low byte = 0x01 -> (0x03 << 8 | 0x01) = 769 -> P0769.
        result = _parse_dtc_response("43 03 01", "03")
        assert result == ["P0769"]

    def test_dtc_payload_for_p0301(self):
        # High byte = 0x01, low byte = 0x2D -> (0x01 << 8 | 0x2D) = 301 -> P0301.
        result = _parse_dtc_response("43 01 2D", "03")
        assert result == ["P0301"]


class TestParseElmResponseEdgeCases:
    def test_single_byte_response(self):
        result = _parse_elm_response("41", "01", "0C")
        assert result is None

    def test_mode_and_pid_only(self):
        result = _parse_elm_response("41 0C", "01", "0C")
        assert result == []
