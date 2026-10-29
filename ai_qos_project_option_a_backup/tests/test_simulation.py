"""
test_simulation.py
==================
Tests for traffic generation and basic simulation runs.
"""
import pytest
import config
from traffic_generator import generate_arrivals, offered_load_mbps, total_packets
from traffic_simulation import run_simulation


class TestTrafficGenerator:
    def test_returns_all_classes(self):
        arrivals = generate_arrivals(duration_s=5.0)
        assert set(arrivals.keys()) == set(config.TRAFFIC_CLASSES.keys())

    def test_packets_within_duration(self):
        dur = 5.0
        arrivals = generate_arrivals(duration_s=dur)
        for cls, pkts in arrivals.items():
            for p in pkts:
                assert p["arrive_s"] < dur, f"{cls} packet arrives after duration"

    def test_packet_fields(self):
        arrivals = generate_arrivals(duration_s=2.0)
        for cls, pkts in arrivals.items():
            for p in pkts:
                assert "arrive_s"    in p
                assert "size_bytes"  in p
                assert "priority"    in p
                assert "class"       in p
                assert p["size_bytes"] == config.TRAFFIC_CLASSES[cls]["packet_size_bytes"]

    def test_reproducibility(self):
        a1 = generate_arrivals(duration_s=5.0, seed=42)
        a2 = generate_arrivals(duration_s=5.0, seed=42)
        for cls in config.TRAFFIC_CLASSES:
            assert len(a1[cls]) == len(a2[cls])

    def test_different_seeds_differ(self):
        a1 = generate_arrivals(duration_s=5.0, seed=1)
        a2 = generate_arrivals(duration_s=5.0, seed=2)
        total_same = sum(
            len(a1[c]) == len(a2[c]) for c in config.TRAFFIC_CLASSES
        )
        assert total_same < len(config.TRAFFIC_CLASSES)  # at least one differs

    def test_offered_load_positive(self):
        arrivals = generate_arrivals(duration_s=5.0)
        load = offered_load_mbps(arrivals, 5.0)
        assert load > 0

    def test_invalid_duration_raises(self):
        with pytest.raises(ValueError):
            generate_arrivals(duration_s=-1.0)

    def test_invalid_multiplier_raises(self):
        with pytest.raises(ValueError):
            generate_arrivals(duration_s=5.0, load_multiplier=0)


class TestSimulationRun:
    def test_fifo_runs(self):
        result = run_simulation(scheduler="fifo", load_scenario="low", duration_s=5.0)
        assert result.scheduler_name == "FIFO"

    def test_priority_runs(self):
        result = run_simulation(scheduler="priority", load_scenario="low", duration_s=5.0)
        assert result.scheduler_name == "Priority"

    def test_invalid_scheduler_raises(self):
        with pytest.raises(ValueError):
            run_simulation(scheduler="bogus", load_scenario="medium")

    def test_invalid_scenario_raises(self):
        with pytest.raises(ValueError):
            run_simulation(scheduler="fifo", load_scenario="ultra")

    def test_invalid_duration_raises(self):
        with pytest.raises(ValueError):
            run_simulation(scheduler="fifo", load_scenario="low", duration_s=-5.0)

    def test_packet_conservation_fifo(self):
        """offered = delivered + dropped (all classes combined)."""
        result = run_simulation(scheduler="fifo", load_scenario="medium", duration_s=5.0)
        for cls in config.TRAFFIC_CLASSES:
            offered   = result.offered.get(cls, 0)
            delivered = len([p for p in result.delivered if p.cls == cls])
            dropped   = result.dropped.get(cls, 0)
            assert offered == delivered + dropped, (
                f"Class {cls}: offered={offered}, delivered={delivered}, dropped={dropped}"
            )

    def test_packet_conservation_priority(self):
        result = run_simulation(scheduler="priority", load_scenario="medium", duration_s=5.0)
        for cls in config.TRAFFIC_CLASSES:
            offered   = result.offered.get(cls, 0)
            delivered = len([p for p in result.delivered if p.cls == cls])
            dropped   = result.dropped.get(cls, 0)
            assert offered == delivered + dropped, (
                f"Class {cls}: offered={offered}, delivered={delivered}, dropped={dropped}"
            )

    def test_throughput_non_negative(self):
        from metrics import throughput_mbps
        result = run_simulation(scheduler="fifo", load_scenario="low", duration_s=5.0)
        for cls in config.TRAFFIC_CLASSES:
            assert throughput_mbps(result, cls) >= 0
