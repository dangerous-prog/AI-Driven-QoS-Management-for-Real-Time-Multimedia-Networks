"""
test_metrics.py
===============
Tests for the metrics computation module.
"""
import pytest
from schedulers import DeliveredPacket, SimulationResult
from metrics import (
    throughput_mbps, packet_loss_pct, avg_delay_ms,
    avg_jitter_ms, link_utilisation_pct, class_summary,
)


def _make_result(scheduler="FIFO", duration_s=10.0):
    """Create a minimal SimulationResult for testing."""
    r = SimulationResult(scheduler_name=scheduler, duration_s=duration_s)
    r.offered    = {"voice": 100, "video": 100, "background": 100}
    r.dropped    = {"voice": 10,  "video": 20,  "background": 5}
    r.busy_time_s = 7.0
    # Add some delivered packets for voice
    for i in range(90):
        r.delivered.append(DeliveredPacket(
            cls="voice", size_bytes=160,
            arrive_s=float(i) * 0.1,
            start_tx_s=float(i) * 0.1 + 0.001,
            finish_s=float(i) * 0.1 + 0.002,
            priority=0,
        ))
    # Add video packets with varying delays to produce jitter
    for i in range(80):
        delay = 0.002 + (i % 5) * 0.001   # alternating delays
        r.delivered.append(DeliveredPacket(
            cls="video", size_bytes=1200,
            arrive_s=float(i) * 0.1,
            start_tx_s=float(i) * 0.1 + 0.001,
            finish_s=float(i) * 0.1 + delay,
            priority=1,
        ))
    return r


class TestThroughput:
    def test_positive(self):
        r = _make_result()
        assert throughput_mbps(r, "voice") > 0

    def test_zero_delivered(self):
        r = _make_result()
        # No background delivered
        assert throughput_mbps(r, "background") == 0.0

    def test_formula(self):
        r = _make_result(duration_s=10.0)
        bits = 90 * 160 * 8   # 90 voice packets
        expected = bits / 10.0 / 1_000_000
        assert abs(throughput_mbps(r, "voice") - expected) < 1e-9


class TestPacketLoss:
    def test_normal(self):
        r = _make_result()
        assert packet_loss_pct(r, "voice") == pytest.approx(10.0, rel=1e-4)

    def test_zero_offered(self):
        r = _make_result()
        r.offered["voice"] = 0
        r.dropped["voice"] = 0
        assert packet_loss_pct(r, "voice") == 0.0

    def test_no_drops(self):
        r = _make_result()
        r.dropped["voice"] = 0
        assert packet_loss_pct(r, "voice") == 0.0

    def test_all_dropped(self):
        r = _make_result()
        r.dropped["voice"] = 100
        assert packet_loss_pct(r, "voice") == 100.0


class TestDelay:
    def test_returns_float(self):
        r = _make_result()
        d = avg_delay_ms(r, "voice")
        assert isinstance(d, float)

    def test_positive(self):
        r = _make_result()
        assert avg_delay_ms(r, "voice") > 0

    def test_no_packets(self):
        r = _make_result()
        assert avg_delay_ms(r, "background") == 0.0

    def test_delay_in_ms(self):
        r = _make_result()
        # Packets have delay ~ 0.002 s = 2.0 ms
        d = avg_delay_ms(r, "voice")
        assert 1.5 < d < 3.0   # approximately 2 ms


class TestJitter:
    def test_returns_float(self):
        r = _make_result()
        j = avg_jitter_ms(r, "video")
        assert isinstance(j, float)

    def test_single_packet_zero(self):
        r = SimulationResult(scheduler_name="FIFO", duration_s=10.0)
        r.offered = {"voice": 1, "video": 0, "background": 0}
        r.dropped = {"voice": 0, "video": 0, "background": 0}
        r.delivered.append(DeliveredPacket(
            cls="voice", size_bytes=160,
            arrive_s=0.0, start_tx_s=0.001, finish_s=0.003, priority=0
        ))
        assert avg_jitter_ms(r, "voice") == 0.0

    def test_no_packets_zero(self):
        r = _make_result()
        assert avg_jitter_ms(r, "background") == 0.0


class TestLinkUtilisation:
    def test_formula(self):
        r = _make_result(duration_s=10.0)
        r.busy_time_s = 7.0
        assert link_utilisation_pct(r) == pytest.approx(70.0, rel=1e-4)

    def test_zero_duration(self):
        r = _make_result(duration_s=0.0)
        r.duration_s = 0.0
        assert link_utilisation_pct(r) == 0.0


class TestClassSummary:
    def test_all_keys_present(self):
        r = _make_result()
        s = class_summary(r, "voice")
        for key in ["scheduler", "traffic_class", "packets_offered", "packets_delivered",
                    "packets_dropped", "packet_loss_pct", "throughput_mbps",
                    "avg_delay_ms", "avg_jitter_ms", "link_util_pct"]:
            assert key in s
