"""
dashboard.py
============
Streamlit interactive dashboard for AI-Driven QoS Management (Option A & Option B).

Run:
    streamlit run dashboard.py

Features:
- Option A: FIFO baseline and Fixed-Priority QoS evaluation.
- Option B: Closed-loop AI-Driven Dynamic QoS controller & scheduling.
- Changing-load experiment viewer (low -> surge -> recovery).
- Real-time controller decision audit log and timeline plots.
- Optional SDN OpenFlow meter configuration inspector.
"""

import sys
import os

# Allow importing project modules when running from the project directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import io

import config


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI-Driven QoS Management (Option B)",
    page_icon="[NET]",
    layout="wide",
)

st.title("[NET] AI-Driven QoS Management for Real-Time Multimedia Networks")
st.caption(
    "Option B: Integrated Closed-Loop AI-Driven QoS Controller & Adaptive Packet Scheduler"
)
st.info(
    "**Note:** All results in this dashboard come from a Python-based discrete-event "
    "simulation. They are **simulated results**, not measurements from a live physical network."
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.header("Simulation Parameters")
link_cap = st.sidebar.slider(
    "Link Capacity (Mbps)", 1.0, 100.0, float(config.LINK_CAPACITY_MBPS), 1.0
)
sim_dur = st.sidebar.slider(
    "Simulation Duration (s)", 5.0, 120.0, float(config.SIM_DURATION_S), 5.0
)
load_choice = st.sidebar.selectbox(
    "Traffic Load Scenario", list(config.LOAD_SCENARIOS.keys()), index=1
)
run_btn = st.sidebar.button("[>>] Run Static Simulation", type="primary")

st.sidebar.markdown("---")
st.sidebar.subheader("Option B Dynamic Experiments")
run_dynamic_btn = st.sidebar.button("[AI] Run Changing-Load Experiment")

st.sidebar.markdown("---")
train_btn = st.sidebar.button("[ML] Train / Evaluate Model")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Results are cached. Adjust parameters and re-run to update."
)


# ---------------------------------------------------------------------------
# Cached simulation runners
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Running 3-way simulations ...")
def cached_run_all(link_mbps: float, dur: float):
    from traffic_simulation import run_all_scenarios
    return run_all_scenarios(duration_s=dur, link_capacity_mbps=link_mbps)


@st.cache_data(show_spinner="Running changing-load experiment ...")
def cached_run_changing(link_mbps: float, dur: float):
    from traffic_simulation import run_changing_load_simulation
    return run_changing_load_simulation(duration_s=dur, link_capacity_mbps=link_mbps)


@st.cache_data(show_spinner="Training ML model ...")
def cached_train(n_seeds: int = 40):
    from dataset_generation import generate_dataset
    from train_model import train_and_evaluate
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path  = os.path.join(tmpdir, "ds.csv")
        model_dir = os.path.join(tmpdir, "models")
        res_dir   = os.path.join(tmpdir, "results")
        fig_dir   = os.path.join(tmpdir, "figures")
        os.makedirs(model_dir)
        os.makedirs(res_dir)
        os.makedirs(fig_dir)

        generate_dataset(n_seeds_per_scenario=n_seeds, window_s=1.0,
                         output_path=csv_path, verbose=False)
        r = train_and_evaluate(
            dataset_path=csv_path,
            model_dir=model_dir,
            results_dir=res_dir,
            figures_dir=fig_dir,
            verbose=False,
        )
        with open(r["cm_path"], "rb") as f:
            cm_bytes = f.read()
        import joblib, json
        model = joblib.load(r["model_path"])
        with open(os.path.join(model_dir, "model_metadata.json")) as f:
            metadata = json.load(f)

    return {
        "rf_accuracy":    r["rf_accuracy"],
        "dummy_accuracy": r["dummy_accuracy"],
        "cm_bytes":       cm_bytes,
        "X_test":         r["X_test"],
        "y_test":         r["y_test"],
        "y_pred":         r["y_pred"],
        "model":          model,
        "metadata":       metadata,
    }


def metrics_for(result, cls):
    from metrics import avg_delay_ms, avg_jitter_ms, packet_loss_pct, throughput_mbps
    return {
        "Avg Delay (ms)":    round(avg_delay_ms(result, cls),    3),
        "Avg Jitter (ms)":   round(avg_jitter_ms(result, cls),   3),
        "Packet Loss (%)":   round(packet_loss_pct(result, cls), 3),
        "Throughput (Mbps)": round(throughput_mbps(result, cls), 4),
    }


def bar_chart_3way(fifo_vals, prio_vals, dyn_vals, labels, ylabel, title):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(labels))
    width = 0.25
    ax.bar(x - width, fifo_vals, width, label="FIFO Baseline", color="#4C72B0")
    ax.bar(x,         prio_vals, width, label="Priority QoS",  color="#DD8452")
    ax.bar(x + width, dyn_vals,  width, label="AI Dynamic QoS", color="#55A868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_dynamic, tab_changing, tab_compare, tab_baseline, tab_qos, tab_ai, tab_predict, tab_sdn, tab_about = st.tabs([
    "AI Dynamic QoS (Option B)",
    "Changing-Load Experiment",
    "3-Way Comparison",
    "FIFO Baseline",
    "Priority QoS",
    "AI Model",
    "Live Predictor",
    "SDN Integration",
    "About",
])

# Initialize session state
if "sim_results" not in st.session_state:
    st.session_state.sim_results = None
if "changing_results" not in st.session_state:
    st.session_state.changing_results = None
if "ml_results" not in st.session_state:
    st.session_state.ml_results = None

if run_btn:
    st.session_state.sim_results = cached_run_all(link_cap, sim_dur)

if run_dynamic_btn:
    st.session_state.changing_results = cached_run_changing(link_cap, sim_dur)

if train_btn:
    st.session_state.ml_results = cached_train(n_seeds=40)


# ---------------------------------------------------------------------------
# Tab 1: AI Dynamic QoS (Option B Core)
# ---------------------------------------------------------------------------
with tab_dynamic:
    st.subheader("Option B: Closed-Loop AI-Driven Dynamic QoS Controller")
    st.write(
        "The controller continuously monitors real-time network telemetry (delay, loss, arrival rate), "
        "uses the pre-trained Random Forest model to predict congestion, and adapts the scheduler's "
        "active queue weights at 1-second intervals with hysteresis stability."
    )
    if st.session_state.sim_results is None:
        st.info("Press **Run Static Simulation** in the sidebar to generate results.")
    else:
        res_dyn = st.session_state.sim_results[load_choice]["dynamic"]
        from metrics import link_utilisation_pct
        util = link_utilisation_pct(res_dyn)
        st.metric("Link Utilisation", f"{util:.1f}%")

        classes = ["voice", "video", "background"]
        rows = [metrics_for(res_dyn, c) for c in classes]
        df = pd.DataFrame(rows, index=classes)
        st.dataframe(df, use_container_width=True)

        cols = st.columns(3)
        for i, cls in enumerate(classes):
            m = rows[i]
            with cols[i]:
                st.metric(f"{cls.capitalize()} Delay", f"{m['Avg Delay (ms)']} ms")
                st.metric(f"{cls.capitalize()} Loss",  f"{m['Packet Loss (%)']}%")

        st.subheader("Controller Action Summary")
        ctrl_summary = getattr(res_dyn, "controller_summary", {})
        if ctrl_summary:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Decisions", ctrl_summary.get("total_decisions", 0))
            c2.metric("Action Changes", ctrl_summary.get("action_changes", 0))
            c3.metric("Switching Frequency", f"{ctrl_summary.get('switching_frequency_per_minute', 0.0)} /min")
            st.write("**Action Distribution:**", ctrl_summary.get("action_distribution", {}))

        # Action history audit trail
        action_hist = getattr(res_dyn, "action_history", [])
        if action_hist:
            st.subheader("Recent Controller Decisions Audit Trail")
            hist_rows = [
                {
                    "Time (s)": d.timestamp_s,
                    "Predicted Congestion": d.predicted_class.upper(),
                    "Applied Action": d.action,
                    "Reason": d.reason,
                    "Voice Pkts/s": d.telemetry.get("arrival_rate_pps", 0),
                }
                for d in action_hist[-10:]
            ]
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 2: Changing-Load Experiment
# ---------------------------------------------------------------------------
with tab_changing:
    st.subheader("Changing-Load Dynamic Experiment (Low -> Surge -> Recovery)")
    st.write(
        "Demonstrates dynamic adaptation under non-stationary traffic: "
        "Phase 1 (0-10s): Low Load (1.5x) | Phase 2 (10-20s): Severe Surge (4.2x) | Phase 3 (20-30s): Recovery (1.5x)."
    )
    if st.session_state.changing_results is None:
        st.info("Press **Run Changing-Load Experiment** in the sidebar to simulate.")
    else:
        c_res = st.session_state.changing_results
        classes = ["voice", "video", "background"]
        metrics_list = ["Avg Delay (ms)", "Avg Jitter (ms)", "Packet Loss (%)", "Throughput (Mbps)"]

        fifo_rows = [metrics_for(c_res["fifo"], c) for c in classes]
        prio_rows = [metrics_for(c_res["priority"], c) for c in classes]
        dyn_rows  = [metrics_for(c_res["dynamic"], c) for c in classes]

        metric_choice = st.selectbox("Select metric for changing load", metrics_list, key="c_metric")
        f_vals = [r[metric_choice] for r in fifo_rows]
        p_vals = [r[metric_choice] for r in prio_rows]
        d_vals = [r[metric_choice] for r in dyn_rows]

        fig = bar_chart_3way(f_vals, p_vals, d_vals, [c.capitalize() for c in classes],
                             metric_choice, f"{metric_choice} Under Changing Load Profile")
        st.pyplot(fig)

        # Plot controller timeline if available
        act_hist = getattr(c_res["dynamic"], "action_history", [])
        if act_hist:
            st.subheader("Controller State Transitions Over Time")
            from evaluation import plot_controller_timeline
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_f:
                p_chart = plot_controller_timeline(act_hist, tmp_f)
                if p_chart and os.path.exists(p_chart):
                    st.image(p_chart, caption="Timeline: AI Predictions and Dynamic QoS Actions Over Time", use_column_width=True)


# ---------------------------------------------------------------------------
# Tab 3: 3-Way Comparison
# ---------------------------------------------------------------------------
with tab_compare:
    st.subheader("3-Way Performance Comparison: FIFO vs Priority vs Dynamic QoS")
    if st.session_state.sim_results is None:
        st.info("Press **Run Static Simulation** in the sidebar.")
    else:
        results = st.session_state.sim_results[load_choice]
        classes = ["voice", "video", "background"]
        metrics_list = ["Avg Delay (ms)", "Avg Jitter (ms)", "Packet Loss (%)", "Throughput (Mbps)"]

        fifo_rows = [metrics_for(results["fifo"],     c) for c in classes]
        prio_rows = [metrics_for(results["priority"], c) for c in classes]
        dyn_rows  = [metrics_for(results["dynamic"],  c) for c in classes]

        sel_metric = st.selectbox("Metric to compare", metrics_list, key="3way_metric")
        f_v = [r[sel_metric] for r in fifo_rows]
        p_v = [r[sel_metric] for r in prio_rows]
        d_v = [r[sel_metric] for r in dyn_rows]

        fig_3way = bar_chart_3way(f_v, p_v, d_v, [c.capitalize() for c in classes],
                                  sel_metric, f"{sel_metric} ({load_choice.capitalize()} Load)")
        st.pyplot(fig_3way)

        # Combined comparison table
        comb = []
        for cls, fr, pr, dr in zip(classes, fifo_rows, prio_rows, dyn_rows):
            comb.append({
                "Traffic Class": cls.capitalize(),
                "FIFO Delay (ms)": fr["Avg Delay (ms)"],
                "Priority Delay (ms)": pr["Avg Delay (ms)"],
                "Dynamic Delay (ms)": dr["Avg Delay (ms)"],
                "FIFO Loss (%)": fr["Packet Loss (%)"],
                "Priority Loss (%)": pr["Packet Loss (%)"],
                "Dynamic Loss (%)": dr["Packet Loss (%)"],
            })
        st.dataframe(pd.DataFrame(comb).set_index("Traffic Class"), use_container_width=True)

        csv_buf = io.StringIO()
        pd.DataFrame(comb).to_csv(csv_buf, index=False)
        st.download_button(
            "Download 3-Way Comparison CSV",
            csv_buf.getvalue().encode(),
            file_name=f"comparison_3way_{load_choice}.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# Tab 4: FIFO Baseline
# ---------------------------------------------------------------------------
with tab_baseline:
    st.subheader("FIFO Baseline (No QoS Differentiation)")
    if st.session_state.sim_results is not None:
        res = st.session_state.sim_results[load_choice]["fifo"]
        classes = ["voice", "video", "background"]
        rows = [metrics_for(res, c) for c in classes]
        st.dataframe(pd.DataFrame(rows, index=classes), use_container_width=True)
    else:
        st.info("Run simulation first.")


# ---------------------------------------------------------------------------
# Tab 5: Priority QoS
# ---------------------------------------------------------------------------
with tab_qos:
    st.subheader("Fixed Strict Priority QoS")
    if st.session_state.sim_results is not None:
        res = st.session_state.sim_results[load_choice]["priority"]
        classes = ["voice", "video", "background"]
        rows = [metrics_for(res, c) for c in classes]
        st.dataframe(pd.DataFrame(rows, index=classes), use_container_width=True)
        st.warning("Notice background traffic starvation under high load.")
    else:
        st.info("Run simulation first.")


# ---------------------------------------------------------------------------
# Tab 6: AI Model
# ---------------------------------------------------------------------------
with tab_ai:
    st.subheader("Random Forest Congestion Classifier")
    if st.session_state.ml_results is None:
        st.info("Press **Train / Evaluate Model** in the sidebar.")
    else:
        ml = st.session_state.ml_results
        c1, c2 = st.columns(2)
        c1.metric("RF Accuracy", f"{ml['rf_accuracy']:.4f}")
        c2.metric("Dummy Accuracy", f"{ml['dummy_accuracy']:.4f}")
        st.image(ml["cm_bytes"], caption="Confusion Matrix", width=400)


# ---------------------------------------------------------------------------
# Tab 7: Live Predictor (Advisory Inference)
# ---------------------------------------------------------------------------
with tab_predict:
    st.subheader("Live Advisory Congestion Inference")
    pred_load = st.selectbox("Inference Load", list(config.LOAD_SCENARIOS.keys()), index=1, key="pl")
    pred_sched = st.selectbox("Inference Scheduler", ["fifo", "priority", "dynamic"], key="ps")
    if st.button("Run Inference"):
        if st.session_state.ml_results is None:
            st.warning("Train the model first.")
        else:
            from traffic_simulation import run_simulation
            from predict_congestion import predict_from_simulation

            sim_r = run_simulation(
                scheduler=pred_sched,
                load_scenario=pred_load,
                duration_s=sim_dur,
                link_capacity_mbps=link_cap,
            )
            mult = config.LOAD_SCENARIOS[pred_load]["multiplier"]
            res_dict = predict_from_simulation(
                sim_r, mult,
                model=st.session_state.ml_results["model"],
                metadata=st.session_state.ml_results["metadata"],
            )
            st.success(f"Predicted State: **{res_dict['predicted_class'].upper()}**")
            st.write(res_dict["advice"])
            st.json(res_dict["probabilities"])


# ---------------------------------------------------------------------------
# Tab 8: SDN Controller Integration (Option B Extension)
# ---------------------------------------------------------------------------
with tab_sdn:
    st.subheader("Software-Defined Networking (SDN) Controller Adapter")
    st.write(
        "Demonstrates how the closed-loop controller interacts with an OpenFlow SDN controller "
        "(e.g., Ryu REST API on port 8080). Translates AI QoS actions into OpenFlow 1.3 meters and queues."
    )
    from sdn_adapter import SDNControllerAdapter
    adapter = SDNControllerAdapter()
    status_color = "green" if adapter.live_connected else "orange"
    status_text  = "Connected to Live Ryu Controller" if adapter.live_connected else "Operating in Simulated SDN Mode"
    st.markdown(f"**SDN Status:** <span style='color:{status_color}'>**{status_text}**</span>", unsafe_allow_html=True)

    st.write("**OpenFlow QoS Meter Translation Table:**")
    meter_df = pd.DataFrame([
        {"Action": "NORMAL",            "Voice Meter": "4.0 Mbps (40%)", "Video Meter": "3.5 Mbps (35%)", "BG Meter": "2.5 Mbps (25%)", "Mode": "Weighted"},
        {"Action": "PROTECT_REALTIME",  "Voice Meter": "6.0 Mbps (60%)", "Video Meter": "3.0 Mbps (30%)", "BG Meter": "1.0 Mbps (10%)", "Mode": "Weighted"},
        {"Action": "SEVERE_CONGESTION", "Voice Meter": "7.0 Mbps (70%)", "Video Meter": "2.5 Mbps (25%)", "BG Meter": "0.5 Mbps (5%)",  "Mode": "Strict Priority"},
        {"Action": "RECOVERY",          "Voice Meter": "5.0 Mbps (50%)", "Video Meter": "3.0 Mbps (30%)", "BG Meter": "2.0 Mbps (20%)", "Mode": "Weighted"},
    ])
    st.dataframe(meter_df, use_container_width=True)

    if st.button("Simulate SDN Meter Push"):
        payload = adapter.apply_action("SEVERE_CONGESTION", current_time_s=15.0)
        st.success("OpenFlow QoS Meter modification generated and logged!")
        st.json(payload)


# ---------------------------------------------------------------------------
# Tab 9: About
# ---------------------------------------------------------------------------
with tab_about:
    st.subheader("About Option B Architecture")
    st.markdown("""
**Title:** AI-Driven QoS Management for Real-Time Multimedia Networks

**Phase:** Option B -- Integrated Closed-Loop AI-Driven QoS Controller

**Core Upgrades in Option B:**
1. **Dynamic Closed-Loop Controller**: Real-time telemetry monitoring + Random Forest inference + dynamic action dispatch.
2. **Hysteresis & Cooldown**: Enforces stability intervals to prevent rapid policy oscillation.
3. **Adaptive Scheduling**: Dynamically shifts between fair weighted queueing and strict priority real-time protection.
4. **Changing-Load Scenarios**: Benchmarked under non-stationary traffic surge profiles.
5. **OpenFlow SDN Adapter**: Translation layer for Ryu/OpenFlow meter and queue configuration.
    """)
