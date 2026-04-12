"""Tests for SampleRingBuffer."""

from obd_rs.buffer import SampleRingBuffer, TelemetrySample


class TestSampleRingBuffer:
    def test_empty_buffer(self):
        buf = SampleRingBuffer(capacity=10)
        assert len(buf) == 0
        assert buf.latest() is None

    def test_push_and_latest(self):
        buf = SampleRingBuffer(capacity=10)
        s = TelemetrySample(ts=1.0, values={"rpm": 3000.0})
        buf.push(s)
        assert len(buf) == 1
        assert buf.latest() is s

    def test_capacity_limit(self):
        buf = SampleRingBuffer(capacity=3)
        for i in range(5):
            buf.push(TelemetrySample(ts=float(i), values={"x": float(i)}))
        assert len(buf) == 3
        assert buf.latest().ts == 4.0

    def test_iteration(self):
        buf = SampleRingBuffer(capacity=10)
        for i in range(5):
            buf.push(TelemetrySample(ts=float(i), values={}))
        timestamps = [s.ts for s in buf]
        assert timestamps == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_window(self):
        buf = SampleRingBuffer(capacity=10)
        for i in range(5):
            buf.push(TelemetrySample(ts=float(i), values={}))
        w = buf.window(3)
        assert len(w) == 3
        assert w[0].ts == 2.0

    def test_window_larger_than_buffer(self):
        buf = SampleRingBuffer(capacity=10)
        buf.push(TelemetrySample(ts=1.0, values={}))
        w = buf.window(100)
        assert len(w) == 1

    def test_since(self):
        buf = SampleRingBuffer(capacity=10)
        for i in range(5):
            buf.push(TelemetrySample(ts=float(i), values={}))
        result = buf.since(3.0)
        assert len(result) == 2
        assert result[0].ts == 3.0
        assert result[1].ts == 4.0
