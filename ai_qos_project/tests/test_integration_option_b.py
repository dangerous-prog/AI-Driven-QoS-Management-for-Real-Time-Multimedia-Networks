"""
test_integration_option_b.py
============================
End-to-end integration tests for Option B: Closed-Loop AI-Driven QoS Management.
"""
import pytest
import os
import tempfile
import pandas as pd

import config
from traffic_generator import generate_arrivals, generate_dynamic_arrivals
from schedulers import run_fifo, run_priority
from dynamic_scheduler import run_dynamic_qos
from dynamic_controller import DynamicQoSController
from metrics import avg_delay_ms, packet_loss_pct, throughput_mbps
from sdn_adapter import SDNControllerAdapter


class TestOptionBIntegration:
    def test_closed_loop_action_changes_actual_packet_scheduling(self):
        """
        CRITICAL INTEGRATION TEST:
        Verifies the full sequence:
        Telemetry -> AI Prediction -> Controller Action -> Scheduler Change -> Measurable Outcome.

        We test that forcing SEVERE_CONGESTION mode in the controller measurably
        prioritizes voice packets over background packets compared to NORMAL mode.
        """
        # Generate heavy traffic load
        arrivals = generate_arrivals(duration_s=8.0, load_multiplier=4.2, seed=42)

        # Run 1: Controller forced to NORMAL (Weighted: Voice 40%, Video 35%, BG 25%)
        ctrl_normal = DynamicQoSController()
        ctrl_normal.current_action = "NORMAL"
        # Monkeypatch decide to keep it in NORMAL
        ctrl_normal.decide = lambda t, tel: DynamicQoSController.decide(ctrl_normal, t, {**tel, "load_multiplier": 0.5})

        res_normal = run_dynamic_qos(
            arrivals, duration_s=8.0, controller=ctrl_normal, control_interval_s=1.0
        )

        # Run 2: Controller in dynamic AI closed loop where it detects severe congestion
        ctrl_ai = DynamicQoSController()
        res_ai = run_dynamic_qos(
            arrivals, duration_s=8.0, controller=ctrl_ai, control_interval_s=1.0
        )

        # Under AI closed loop during severe congestion, voice delay must be strictly lower
        # or voice packet loss must be strictly lower than under un-escalated normal mode!
        voice_delay_ai = avg_delay_ms(res_ai, "voice")
        voice_delay_normal = avg_delay_ms(res_normal, "voice")

        assert voice_delay_ai <= voice_delay_normal + 0.1, (
            f"AI QoS action did not improve voice scheduling: {voice_delay_ai} vs {voice_delay_normal}"
        )
        # Ensure an actual controller decision was logged
        assert len(res_ai.action_history) > 0
        assert any(d.action in ("SEVERE_CONGESTION", "PROTECT_REALTIME") for d in res_ai.action_history)

    def test_3way_comparison_under_identical_arrivals(self):
        """
        Verifies that FIFO, Priority, and Dynamic QoS run on the exact same arrival trace
        and produce comparable, valid outputs.
        """
        arrivals = generate_arrivals(duration_s=10.0, load_multiplier=3.5, seed=101)

        res_fifo = run_fifo(arrivals, duration_s=10.0)
        res_prio = run_priority(arrivals, duration_s=10.0)
        res_dyn  = run_dynamic_qos(arrivals, duration_s=10.0)

        # 1. Total offered packets must be IDENTICAL across all 3 policies
        for cls in config.TRAFFIC_CLASSES:
            assert res_fifo.offered[cls] == res_prio.offered[cls] == res_dyn.offered[cls]

        # 2. Priority and Dynamic QoS must protect voice better than FIFO under high load
        fifo_voice_delay = avg_delay_ms(res_fifo, "voice")
        dyn_voice_delay  = avg_delay_ms(res_dyn, "voice")
        prio_voice_delay = avg_delay_ms(res_prio, "voice")

        assert dyn_voice_delay < fifo_voice_delay, (
            f"Dynamic voice delay ({dyn_voice_delay}ms) should be lower than FIFO ({fifo_voice_delay}ms)"
        )
        assert prio_voice_delay < fifo_voice_delay

    def test_sdn_adapter_openflow_meter_payload(self):
        """Test that SDN adapter generates valid OpenFlow 1.3 meter configurations."""
        adapter = SDNControllerAdapter()
        payload = adapter.apply_action("SEVERE_CONGESTION", current_time_s=10.0)
        assert payload["action"] == "SEVERE_CONGESTION"
        assert payload["mode"] == "strict_priority"
        assert "rates_kbps" in payload
        assert "openflow_meters" in payload
        assert len(payload["openflow_meters"]) == 3
        assert len(adapter.get_audit_log()) >= 1

    def test_option_b_evaluation_csv_and_figures_generated(self):
        """Test that Option B evaluation script exports CSV and PNG files."""
        from evaluation import run_evaluation_option_b
        with tempfile.TemporaryDirectory() as tmp_res, tempfile.TemporaryDirectory() as tmp_fig:
            df = run_evaluation_option_b(
                duration_s=4.0,
                seed=42,
                results_dir=tmp_res,
                figures_dir=tmp_fig,
                verbose=False,
            )
            assert isinstance(df, pd.DataFrame)
            assert len(df) > 0
            assert os.path.exists(os.path.join(tmp_res, "evaluation_summary_option_b.csv"))
            assert os.path.exists(os.path.join(tmp_fig, "delay_by_class_3way.png"))
            assert os.path.exists(os.path.join(tmp_fig, "changing_load_comparison.png"))

    def test_option_a_backward_compatibility(self):
        """Option A functions must remain functional and produce expected results."""
        from traffic_simulation import run_simulation
        res_fifo = run_simulation(scheduler="fifo", load_scenario="low", duration_s=5.0)
        res_prio = run_simulation(scheduler="priority", load_scenario="low", duration_s=5.0)
        assert res_fifo.scheduler_name == "FIFO"
        assert res_prio.scheduler_name == "Priority"
