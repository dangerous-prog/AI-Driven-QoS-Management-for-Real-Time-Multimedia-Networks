"""
test_controller.py
==================
Unit tests for the Option B DynamicQoSController.
"""
import pytest
import config
from dynamic_controller import DynamicQoSController, ControllerDecision


@pytest.fixture
def dummy_telemetry():
    return {
        "load_multiplier": 3.0,
        "arrival_rate_pps": 850.0,
        "queue_fill_proxy": 0.05,
        "voice_delay_ms": 2.5,
        "video_delay_ms": 5.0,
        "bg_delay_ms": 15.0,
        "voice_loss_pct": 0.0,
        "video_loss_pct": 0.0,
        "bg_loss_pct": 2.0,
        "voice_jitter_ms": 0.5,
        "video_jitter_ms": 1.0,
        "throughput_total_mbps": 8.5,
    }


class TestDynamicController:
    def test_controller_initialization(self):
        ctrl = DynamicQoSController(min_action_duration_s=2.0)
        assert ctrl.current_action == "NORMAL"
        assert ctrl.action_change_count == 0
        assert len(ctrl.action_history) == 0

    def test_predict_congestion_returns_valid_label(self, dummy_telemetry):
        ctrl = DynamicQoSController()
        pred_class, prob_dict = ctrl.predict_congestion(dummy_telemetry)
        assert pred_class in config.CONGESTION_LABELS
        assert isinstance(prob_dict, dict)
        assert all(lbl in prob_dict for lbl in config.CONGESTION_LABELS)

    def test_emergency_escalation_to_severe(self):
        ctrl = DynamicQoSController(min_action_duration_s=5.0)
        severe_telemetry = {
            "load_multiplier": 4.5,
            "arrival_rate_pps": 1300.0,
            "queue_fill_proxy": 0.15,
            "voice_delay_ms": 50.0,
            "video_delay_ms": 100.0,
            "bg_delay_ms": 500.0,
            "voice_loss_pct": 5.0,
            "video_loss_pct": 10.0,
            "bg_loss_pct": 25.0,
            "voice_jitter_ms": 5.0,
            "video_jitter_ms": 10.0,
            "throughput_total_mbps": 10.0,
        }
        dec = ctrl.decide(current_time_s=1.0, interval_telemetry=severe_telemetry)
        assert dec.action == "SEVERE_CONGESTION"
        assert ctrl.current_action == "SEVERE_CONGESTION"
        assert ctrl.action_change_count == 1

    def test_hysteresis_prevents_premature_deescalation(self):
        ctrl = DynamicQoSController(min_action_duration_s=3.0)
        # 1. Force into SEVERE_CONGESTION at t=1.0
        ctrl.current_action = "SEVERE_CONGESTION"
        ctrl.last_action_change_time = 1.0

        # 2. At t=2.0 (only 1s elapsed < 3.0s cooldown), normal telemetry arrives
        normal_telemetry = {
            "load_multiplier": 1.0,
            "arrival_rate_pps": 300.0,
            "queue_fill_proxy": 0.0,
            "voice_delay_ms": 0.5,
            "video_delay_ms": 1.0,
            "bg_delay_ms": 2.0,
            "voice_loss_pct": 0.0,
            "video_loss_pct": 0.0,
            "bg_loss_pct": 0.0,
            "voice_jitter_ms": 0.1,
            "video_jitter_ms": 0.2,
            "throughput_total_mbps": 3.0,
        }
        dec = ctrl.decide(current_time_s=2.0, interval_telemetry=normal_telemetry)
        # Must maintain SEVERE_CONGESTION because cooldown has not elapsed
        assert dec.action == "SEVERE_CONGESTION"
        assert "Cooldown active" in dec.reason

        # 3. At t=4.5s (> 3.0s cooldown elapsed), normal telemetry allows transition to RECOVERY
        dec2 = ctrl.decide(current_time_s=4.5, interval_telemetry=normal_telemetry)
        assert dec2.action == "RECOVERY"

    def test_summary_statistics_tracking(self, dummy_telemetry):
        ctrl = DynamicQoSController()
        ctrl.decide(1.0, dummy_telemetry)
        ctrl.decide(2.0, dummy_telemetry)
        stats = ctrl.get_summary_stats()
        assert stats["total_decisions"] == 2
        assert "action_distribution" in stats
        assert "switching_frequency_per_minute" in stats
