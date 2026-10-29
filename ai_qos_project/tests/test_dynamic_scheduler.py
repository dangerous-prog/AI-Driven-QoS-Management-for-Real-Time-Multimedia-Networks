"""
test_dynamic_scheduler.py
=========================
Unit tests for Option B closed-loop dynamic packet scheduling.
"""
import pytest
import config
from traffic_generator import generate_arrivals, generate_dynamic_arrivals
from dynamic_scheduler import run_dynamic_qos, DynamicSimulationResult
from dynamic_controller import DynamicQoSController
from metrics import avg_delay_ms, packet_loss_pct, throughput_mbps


class TestDynamicScheduler:
    def test_returns_dynamic_simulation_result(self):
        arrivals = generate_arrivals(duration_s=5.0, load_multiplier=2.0)
        res = run_dynamic_qos(arrivals, duration_s=5.0)
        assert isinstance(res, DynamicSimulationResult)
        assert res.scheduler_name == "AI-Driven Dynamic QoS"
        assert hasattr(res, "action_history")
        assert hasattr(res, "controller_summary")

    def test_packet_conservation_dynamic_scheduler(self):
        """Strict accounting: offered == delivered + dropped for all classes."""
        arrivals = generate_arrivals(duration_s=10.0, load_multiplier=3.5, seed=42)
        res = run_dynamic_qos(arrivals, duration_s=10.0)
        for cls in config.TRAFFIC_CLASSES:
            offered = res.offered.get(cls, 0)
            delivered = len([p for p in res.delivered if p.cls == cls])
            dropped = res.dropped.get(cls, 0)
            assert offered == delivered + dropped, (
                f"Class {cls} packet conservation violated: {offered} != {delivered} + {dropped}"
            )

    def test_no_negative_delay_or_jitter(self):
        arrivals = generate_arrivals(duration_s=6.0, load_multiplier=3.0, seed=123)
        res = run_dynamic_qos(arrivals, duration_s=6.0)
        for p in res.delivered:
            assert p.delay_s >= 0.0
            assert p.finish_s >= p.arrive_s

        for cls in config.TRAFFIC_CLASSES:
            assert avg_delay_ms(res, cls) >= 0.0

    def test_dynamic_arrivals_profile_structure(self):
        profile = [
            (0.0, 5.0, 1.5, "Low Phase"),
            (5.0, 10.0, 4.0, "High Surge"),
        ]
        dyn_arr = generate_dynamic_arrivals(profile=profile, seed=99)
        assert set(dyn_arr.keys()) == set(config.TRAFFIC_CLASSES.keys())
        for cls, pkts in dyn_arr.items():
            for p in pkts:
                assert 0.0 <= p["arrive_s"] < 10.0

    def test_changing_load_triggers_action_escalation(self):
        """Under a changing load surge, the controller must escalate actions."""
        arrivals = generate_dynamic_arrivals(
            profile=config.CHANGING_LOAD_PROFILE,
            seed=42,
        )
        ctrl = DynamicQoSController()
        res = run_dynamic_qos(arrivals, duration_s=30.0, controller=ctrl)

        actions_taken = [d.action for d in res.action_history]
        # Should record transitions during the surge
        assert "SEVERE_CONGESTION" in actions_taken or "PROTECT_REALTIME" in actions_taken
        assert res.controller_summary["action_changes"] >= 1
