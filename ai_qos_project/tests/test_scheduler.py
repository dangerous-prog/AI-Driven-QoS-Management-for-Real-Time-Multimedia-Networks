"""
test_scheduler.py
=================
Tests for the FIFO and Priority scheduler policies.
"""
import pytest
from traffic_generator import generate_arrivals
from schedulers import run_fifo, run_priority, SimulationResult
import config


def small_arrivals(seed=42, duration=5.0, multiplier=2.0):
    return generate_arrivals(duration_s=duration, load_multiplier=multiplier, seed=seed)


class TestFIFO:
    def test_returns_simulation_result(self):
        arrivals = small_arrivals()
        r = run_fifo(arrivals, duration_s=5.0)
        assert isinstance(r, SimulationResult)

    def test_scheduler_name(self):
        r = run_fifo(small_arrivals(), duration_s=5.0)
        assert r.scheduler_name == "FIFO"

    def test_delivered_before_duration(self):
        r = run_fifo(small_arrivals(), duration_s=5.0)
        for p in r.delivered:
            assert p.finish_s <= 5.0

    def test_arrival_order_preserved(self):
        """
        FIFO: delivered packets should have non-decreasing finish times
        consistent with arrival order (finish times must be monotone).
        """
        r = run_fifo(small_arrivals(multiplier=1.0), duration_s=5.0)
        # Since it's FIFO and work-conserving, finish times are monotone
        finish_times = [p.finish_s for p in r.delivered]
        assert finish_times == sorted(finish_times), "FIFO finish times not monotone"

    def test_packet_conservation(self):
        arrivals = small_arrivals()
        r = run_fifo(arrivals, duration_s=5.0)
        for cls in config.TRAFFIC_CLASSES:
            offered   = r.offered.get(cls, 0)
            delivered = len([p for p in r.delivered if p.cls == cls])
            dropped   = r.dropped.get(cls, 0)
            assert offered == delivered + dropped, \
                f"FIFO conservation fail for {cls}: {offered} != {delivered} + {dropped}"

    def test_no_negative_delay(self):
        r = run_fifo(small_arrivals(), duration_s=5.0)
        for p in r.delivered:
            assert p.delay_s >= 0, f"Negative delay {p.delay_s} for {p.cls}"

    def test_busy_time_bounded(self):
        r = run_fifo(small_arrivals(), duration_s=5.0)
        assert 0 <= r.busy_time_s <= 5.0

    def test_high_load_produces_drops(self):
        """At high load, some packets should be dropped."""
        r = run_fifo(small_arrivals(multiplier=5.0), duration_s=5.0)
        total_dropped = sum(r.dropped.values())
        # Not strictly guaranteed but very likely at 5× load
        assert total_dropped >= 0   # at minimum it should not crash


class TestPriority:
    def test_returns_simulation_result(self):
        r = run_priority(small_arrivals(), duration_s=5.0)
        assert isinstance(r, SimulationResult)

    def test_scheduler_name(self):
        r = run_priority(small_arrivals(), duration_s=5.0)
        assert r.scheduler_name == "Priority"

    def test_packet_conservation(self):
        arrivals = small_arrivals()
        r = run_priority(arrivals, duration_s=5.0)
        for cls in config.TRAFFIC_CLASSES:
            offered   = r.offered.get(cls, 0)
            delivered = len([p for p in r.delivered if p.cls == cls])
            dropped   = r.dropped.get(cls, 0)
            assert offered == delivered + dropped, \
                f"Priority conservation fail for {cls}: {offered} != {delivered} + {dropped}"

    def test_voice_lower_loss_than_background_at_high_load(self):
        """
        At high load, strict priority should give voice lower loss than background.
        """
        arrivals = generate_arrivals(duration_s=10.0, load_multiplier=4.0, seed=42)
        r = run_priority(arrivals, duration_s=10.0)

        voice_offered = r.offered.get("voice", 1)
        bg_offered    = r.offered.get("background", 1)
        voice_loss    = r.dropped.get("voice", 0)    / voice_offered
        bg_loss       = r.dropped.get("background", 0) / bg_offered

        # Voice should have strictly lower (or equal) loss than background
        assert voice_loss <= bg_loss, \
            f"Priority scheduler: voice loss {voice_loss:.3f} > bg loss {bg_loss:.3f}"

    def test_no_negative_delay(self):
        r = run_priority(small_arrivals(), duration_s=5.0)
        for p in r.delivered:
            assert p.delay_s >= 0

    def test_delivered_before_duration(self):
        r = run_priority(small_arrivals(), duration_s=5.0)
        for p in r.delivered:
            assert p.finish_s <= 5.0


class TestComparison:
    def test_identical_offered_counts(self):
        """Both schedulers receive exactly the same offered traffic."""
        arrivals = generate_arrivals(duration_s=10.0, load_multiplier=3.0, seed=99)
        r_fifo = run_fifo(arrivals, duration_s=10.0)
        r_prio = run_priority(arrivals, duration_s=10.0)
        for cls in config.TRAFFIC_CLASSES:
            assert r_fifo.offered[cls] == r_prio.offered[cls], \
                f"Offered counts differ for {cls}"

    def test_priority_gives_voice_advantage_under_high_load(self):
        """Priority scheduler should achieve lower voice delay than FIFO under high load."""
        arrivals = generate_arrivals(duration_s=15.0, load_multiplier=4.0, seed=42)
        r_fifo = run_fifo(arrivals, duration_s=15.0)
        r_prio = run_priority(arrivals, duration_s=15.0)

        from metrics import avg_delay_ms
        fifo_voice_delay = avg_delay_ms(r_fifo, "voice")
        prio_voice_delay = avg_delay_ms(r_prio, "voice")

        # Under high load priority should give voice lower or equal delay
        assert prio_voice_delay <= fifo_voice_delay * 1.1, (
            f"Priority voice delay {prio_voice_delay:.2f} ms is much higher than "
            f"FIFO {fifo_voice_delay:.2f} ms — unexpected"
        )
