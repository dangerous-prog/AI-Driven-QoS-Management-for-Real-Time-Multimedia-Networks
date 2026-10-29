"""
dashboard.py
============
Streamlit interactive dashboard for the AI-Driven QoS Management project.

Run:
    streamlit run dashboard.py

The dashboard caches heavy computations (simulations, model training) so
results are not recomputed on every widget interaction.
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
    page_title="AI-Driven QoS Management",
    page_icon="[NET]",
    layout="wide",
)

st.title("[NET] AI-Driven QoS Management for Real-Time Multimedia Networks")
st.caption(
    "Phase 1 Prototype -- Python discrete-event simulation + "
    "Random Forest congestion prediction"
)
st.info(
    "**Note:** All results in this dashboard come from a Python-based discrete-event "
    "simulation. They are **simulated results**, not measurements from a live network."
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
run_btn = st.sidebar.button("[>>] Run Simulation", type="primary")

st.sidebar.markdown("---")
train_btn = st.sidebar.button("[ML] Train / Evaluate Model")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Results are cached. Change parameters and re-run to update."
)


# ---------------------------------------------------------------------------
# Cached simulation runner
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Running simulations ...")
def cached_run_all(link_mbps: float, dur: float):
    from traffic_simulation import run_all_scenarios
    return run_all_scenarios(duration_s=dur, link_capacity_mbps=link_mbps)


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
        os.makedirs(model_dir); os.makedirs(res_dir); os.makedirs(fig_dir)

        generate_dataset(n_seeds_per_scenario=n_seeds, window_s=1.0,
                         output_path=csv_path, verbose=False)
        r = train_and_evaluate(
            dataset_path=csv_path,
            model_dir=model_dir,
            results_dir=res_dir,
            figures_dir=fig_dir,
            verbose=False,
        )
        # Read CM image bytes before tmpdir is deleted
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
        "Avg Delay (ms)":  round(avg_delay_ms(result, cls),    3),
        "Avg Jitter (ms)": round(avg_jitter_ms(result, cls),   3),
        "Packet Loss (%)": round(packet_loss_pct(result, cls), 3),
        "Throughput (Mbps)": round(throughput_mbps(result, cls), 4),
    }


def bar_chart(fifo_vals, prio_vals, labels, ylabel, title):
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(labels))
    ax.bar(x - 0.2, fifo_vals, 0.35, label="FIFO Baseline", color="#4C72B0")
    ax.bar(x + 0.2, prio_vals, 0.35, label="Priority QoS",  color="#DD8452")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel); ax.set_title(title)
    ax.legend(); ax.set_ylim(bottom=0)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_baseline, tab_qos, tab_compare, tab_ai, tab_predict, tab_about = st.tabs([
    "FIFO Baseline",
    "Priority QoS",
    "Comparison",
    "AI Model",
    "Congestion Predictor",
    "About",
])

# Keep state
if "sim_results" not in st.session_state:
    st.session_state.sim_results = None
if "ml_results" not in st.session_state:
    st.session_state.ml_results = None


# Run simulation when button pressed
if run_btn:
    st.session_state.sim_results = cached_run_all(link_cap, sim_dur)

# Train model when button pressed
if train_btn:
    st.session_state.ml_results = cached_train(n_seeds=40)


# ---------------------------------------------------------------------------
# FIFO Baseline tab
# ---------------------------------------------------------------------------
with tab_baseline:
    st.subheader("FIFO Baseline Results")
    st.write(
        "Single shared queue, packets served in strict arrival order. "
        "No traffic differentiation applied."
    )
    if st.session_state.sim_results is None:
        st.info("Press **Run Simulation** in the sidebar to generate results.")
    else:
        result = st.session_state.sim_results[load_choice]["fifo"]
        from metrics import link_utilisation_pct
        util = link_utilisation_pct(result)
        st.metric("Link Utilisation", f"{util:.1f}%")

        classes = ["voice", "video", "background"]
        rows = [metrics_for(result, c) for c in classes]
        df = pd.DataFrame(rows, index=classes)
        st.dataframe(df, use_container_width=True)

        # KPI cards
        cols = st.columns(3)
        for i, cls in enumerate(classes):
            m = rows[i]
            with cols[i]:
                st.metric(f"{cls.capitalize()} Delay", f"{m['Avg Delay (ms)']} ms")
                st.metric(f"{cls.capitalize()} Loss",  f"{m['Packet Loss (%)']}%")


# ---------------------------------------------------------------------------
# Priority QoS tab
# ---------------------------------------------------------------------------
with tab_qos:
    st.subheader("Priority QoS Results")
    st.write(
        "Three separate queues: Voice (priority 0) > Video (1) > Background (2). "
        "Strict priority scheduling -- background traffic may be starved under high load."
    )
    if st.session_state.sim_results is None:
        st.info("Press **Run Simulation** in the sidebar to generate results.")
    else:
        result = st.session_state.sim_results[load_choice]["priority"]
        from metrics import link_utilisation_pct
        util = link_utilisation_pct(result)
        st.metric("Link Utilisation", f"{util:.1f}%")

        classes = ["voice", "video", "background"]
        rows = [metrics_for(result, c) for c in classes]
        df = pd.DataFrame(rows, index=classes)
        st.dataframe(df, use_container_width=True)

        cols = st.columns(3)
        for i, cls in enumerate(classes):
            m = rows[i]
            with cols[i]:
                st.metric(f"{cls.capitalize()} Delay", f"{m['Avg Delay (ms)']} ms")
                st.metric(f"{cls.capitalize()} Loss",  f"{m['Packet Loss (%)']}%")

        st.warning(
            "**Note on strict priority:** Under sustained high load, background traffic "
            "may receive zero service and suffer 100% packet loss. "
            "This is expected behaviour of strict priority scheduling."
        )


# ---------------------------------------------------------------------------
# Comparison tab
# ---------------------------------------------------------------------------
with tab_compare:
    st.subheader("FIFO vs Priority QoS Comparison")
    if st.session_state.sim_results is None:
        st.info("Press **Run Simulation** in the sidebar to generate results.")
    else:
        results = st.session_state.sim_results[load_choice]
        classes = ["voice", "video", "background"]
        metrics_list = ["Avg Delay (ms)", "Avg Jitter (ms)",
                        "Packet Loss (%)", "Throughput (Mbps)"]
        fifo_rows = [metrics_for(results["fifo"],     c) for c in classes]
        prio_rows = [metrics_for(results["priority"], c) for c in classes]

        metric_choice = st.selectbox("Metric to visualize", metrics_list)
        fifo_vals = [r[metric_choice] for r in fifo_rows]
        prio_vals = [r[metric_choice] for r in prio_rows]
        fig = bar_chart(fifo_vals, prio_vals,
                        [c.capitalize() for c in classes],
                        metric_choice,
                        f"{metric_choice} by Traffic Class ({load_choice} load)")
        st.pyplot(fig)

        st.write("**Detailed comparison table:**")
        combined = []
        for cls, fr, pr in zip(classes, fifo_rows, prio_rows):
            combined.append({
                "class": cls,
                **{f"FIFO {k}": v for k, v in fr.items()},
                **{f"Priority {k}": v for k, v in pr.items()},
            })
        st.dataframe(pd.DataFrame(combined).set_index("class"), use_container_width=True)

        # Download CSV
        csv_buf = io.StringIO()
        pd.DataFrame(combined).to_csv(csv_buf, index=False)
        st.download_button(
            "Download Comparison CSV",
            csv_buf.getvalue().encode(),
            file_name=f"comparison_{load_choice}.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# AI Model tab
# ---------------------------------------------------------------------------
with tab_ai:
    st.subheader("AI Congestion Prediction -- Model Evaluation")
    st.write(
        "A Random Forest classifier trained on simulation measurements to predict "
        "network congestion level: **normal**, **moderate**, or **severe**."
    )
    if st.session_state.ml_results is None:
        st.info("Press **Train / Evaluate Model** in the sidebar.")
    else:
        ml = st.session_state.ml_results
        c1, c2 = st.columns(2)
        c1.metric("RF Accuracy", f"{ml['rf_accuracy']:.4f}")
        c2.metric("DummyClassifier Accuracy", f"{ml['dummy_accuracy']:.4f}")

        st.image(ml["cm_bytes"], caption="Confusion Matrix", width=400)

        from sklearn.metrics import classification_report
        report_str = classification_report(
            ml["y_test"], ml["y_pred"],
            labels=config.CONGESTION_LABELS,
            target_names=config.CONGESTION_LABELS,
            zero_division=0,
        )
        st.code(report_str, language="text")
        st.caption(
            "The model is trained and tested on simulated data only. "
            "Accuracy may differ on real network measurements."
        )


# ---------------------------------------------------------------------------
# Congestion Predictor tab
# ---------------------------------------------------------------------------
with tab_predict:
    st.subheader("Live Congestion Predictor (Advisory Mode)")
    st.info(
        "**Phase 1 Advisory Only:** The prediction is displayed for the operator "
        "but does NOT automatically adjust the scheduler."
    )

    pred_load  = st.selectbox("Load scenario for prediction",
                              list(config.LOAD_SCENARIOS.keys()), index=1)
    pred_sched = st.selectbox("Scheduler", ["fifo", "priority"])
    pred_btn   = st.button("Predict Congestion State")

    if pred_btn:
        if st.session_state.ml_results is None:
            st.warning("Train the model first (sidebar button).")
        else:
            from traffic_simulation import run_simulation
            from predict_congestion import predict_from_simulation

            with st.spinner("Simulating ..."):
                sim_r = run_simulation(
                    scheduler=pred_sched,
                    load_scenario=pred_load,
                    duration_s=sim_dur,
                    link_capacity_mbps=link_cap,
                )
            multiplier = config.LOAD_SCENARIOS[pred_load]["multiplier"]
            result_dict = predict_from_simulation(
                sim_r, multiplier,
                model=st.session_state.ml_results["model"],
                metadata=st.session_state.ml_results["metadata"],
            )
            pred_class = result_dict["predicted_class"]
            color_map = {"normal": "green", "moderate": "orange", "severe": "red"}
            st.markdown(
                f"### Predicted State: "
                f"<span style='color:{color_map.get(pred_class, 'black')}'>"
                f"**{pred_class.upper()}**</span>",
                unsafe_allow_html=True,
            )
            st.write(result_dict["advice"])
            st.write("**Probabilities:**")
            prob_df = pd.DataFrame(
                list(result_dict["probabilities"].items()),
                columns=["Label", "Probability"],
            )
            st.bar_chart(prob_df.set_index("Label"))

            st.write("**Input features:**")
            st.json(result_dict["features"])
            st.caption(result_dict["note"])


# ---------------------------------------------------------------------------
# About tab
# ---------------------------------------------------------------------------
with tab_about:
    st.subheader("About this Project")
    st.markdown("""
**Title:** AI-Driven QoS Management for Real-Time Multimedia Networks

**Phase:** 1 -- Lightweight Python simulation prototype

**Technology Stack:**
- Python 3.11
- NumPy, Pandas -- data handling
- Scikit-learn -- Random Forest classifier
- Matplotlib -- charts
- Streamlit -- this dashboard

**Traffic Classes Simulated:**
| Class | Packet Size | Priority |
|-------|------------|---------|
| Voice | 160 bytes | Highest (0) |
| Video | 1200 bytes | Medium (1) |
| Background | 1500 bytes | Lowest (2) |

**Schedulers:**
- **FIFO Baseline** -- single queue, no differentiation
- **Strict Priority** -- separate queues, voice served first

**ML Model:** Random Forest (100 trees, max_depth=10)

**Congestion Labels:**
- Normal: utilisation < 70%
- Moderate: 70% <= utilisation < 90%
- Severe: utilisation >= 90%

**Disclaimer:** This is a simulated prototype for educational purposes.
Results do not represent real network measurements.

**Phase 2 Extensions (planned):**
- Closed-loop AI QoS controller
- Adaptive bandwidth allocation
- Optional Mininet/Ryu/NS-3 integration
- LSTM or reinforcement learning
    """)
