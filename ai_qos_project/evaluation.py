"""
evaluation.py
=============
Runs performance comparisons and generates all graphs and CSVs for Option A & Option B.

Configurations evaluated:
------------------------
1. FIFO baseline           -- no QoS differentiation
2. Strict Priority QoS     -- voice > video > background
3. AI-Driven Dynamic QoS   -- closed-loop real-time adaptation (Option B)

Output files:
------------
results/evaluation_summary.csv          -- Option A summary
results/evaluation_summary_option_b.csv -- Option B 3-way comparative summary
results/figures/*.png                   -- comparison charts
"""

from __future__ import annotations
import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import config
from traffic_simulation import run_simulation, run_all_scenarios, run_changing_load_simulation
from metrics import (
    avg_delay_ms, avg_jitter_ms, packet_loss_pct,
    throughput_mbps, link_utilisation_pct,
    packets_offered_count, packets_delivered_count, packets_dropped_count,
)

# ---------------------------------------------------------------------------
# Plotting helpers & palettes
# ---------------------------------------------------------------------------
SCHED_COLORS = {
    "fifo":     "#4C72B0",
    "priority": "#DD8452",
    "dynamic":  "#55A868",
}
SCHED_LABELS = {
    "fifo":     "FIFO Baseline",
    "priority": "Priority QoS",
    "dynamic":  "AI-Driven Dynamic QoS",
}
LOAD_ORDER   = ["low", "medium", "high"]
CLASS_ORDER  = ["voice", "video", "background"]


def _save(fig: plt.Figure, name: str, figures_dir: str) -> str:
    path = os.path.join(figures_dir, name)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Option A -- Baseline Results DataFrame
# ---------------------------------------------------------------------------
def build_results_df(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
) -> pd.DataFrame:
    """
    Run both schedulers under all load scenarios and collect metrics.
    Preserves Option A compatibility.
    """
    all_results = run_all_scenarios(duration_s=duration_s, seed=seed)
    rows = []
    for scenario in config.LOAD_SCENARIOS:
        sched_dict = all_results.get(scenario, {})
        for sched_name in ("fifo", "priority"):
            if sched_name not in sched_dict:
                continue
            result = sched_dict[sched_name]
            util = link_utilisation_pct(result)
            for cls in config.TRAFFIC_CLASSES:
                rows.append({
                    "load_scenario":     scenario,
                    "scheduler":         sched_name,
                    "traffic_class":     cls,
                    "avg_delay_ms":      round(avg_delay_ms(result, cls),      4),
                    "avg_jitter_ms":     round(avg_jitter_ms(result, cls),     4),
                    "packet_loss_pct":   round(packet_loss_pct(result, cls),   4),
                    "throughput_mbps":   round(throughput_mbps(result, cls),   6),
                    "link_util_pct":     round(util,                           4),
                    "packets_offered":   packets_offered_count(result, cls),
                    "packets_delivered": packets_delivered_count(result, cls),
                    "packets_dropped":   packets_dropped_count(result, cls),
                    "duration_s":        result.duration_s,
                })
    return pd.DataFrame(rows)


def plot_metric_by_class(
    df: pd.DataFrame,
    metric_col: str,
    ylabel: str,
    title: str,
    filename: str,
    figures_dir: str,
    scenario: str = "medium",
) -> str:
    """Bar chart: metric per traffic class, grouped by scheduler."""
    sub = df[df["load_scenario"] == scenario]
    classes = CLASS_ORDER
    x = np.arange(len(classes))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    for i, sched in enumerate(["fifo", "priority"]):
        vals = [
            sub[(sub["scheduler"] == sched) & (sub["traffic_class"] == c)][metric_col].values
            for c in classes
        ]
        vals = [v[0] if len(v) > 0 else 0.0 for v in vals]
        bars = ax.bar(x + i * width, vals, width, label=SCHED_LABELS[sched],
                      color=SCHED_COLORS[sched], edgecolor="black", linewidth=0.5)
        for bar, val in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(vals) * 0.01 if max(vals) > 0 else 0.01,
                f"{val:.2f}", ha="center", va="bottom", fontsize=8,
            )

    ax.set_xticks(x + width / 2)
    ax.set_xticklabels([c.capitalize() for c in classes])
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\n(scenario: {scenario})")
    ax.legend()
    ax.set_ylim(bottom=0)
    fig.text(0.5, -0.02, "Note: results are from a Python discrete-event simulation",
             ha="center", fontsize=7, style="italic")
    plt.tight_layout()
    return _save(fig, filename, figures_dir)


def plot_metric_by_load(
    df: pd.DataFrame,
    metric_col: str,
    ylabel: str,
    title: str,
    filename: str,
    figures_dir: str,
    traffic_class: str = "voice",
) -> str:
    """Line chart: metric vs load level for a given traffic class."""
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(LOAD_ORDER))
    for sched in ["fifo", "priority"]:
        vals = []
        for scenario in LOAD_ORDER:
            row = df[
                (df["scheduler"] == sched) &
                (df["load_scenario"] == scenario) &
                (df["traffic_class"] == traffic_class)
            ]
            vals.append(row[metric_col].values[0] if len(row) > 0 else 0.0)
        ax.plot(LOAD_ORDER, vals, marker="o", label=SCHED_LABELS[sched],
                color=SCHED_COLORS[sched], linewidth=2)
        for xi, yi in zip(x, vals):
            ax.annotate(f"{yi:.2f}", (LOAD_ORDER[xi], yi),
                        textcoords="offset points", xytext=(5, 5), fontsize=8)

    ax.set_xlabel("Load Scenario")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\nTraffic class: {traffic_class.capitalize()}")
    ax.legend()
    ax.set_ylim(bottom=0)
    fig.text(0.5, -0.02, "Note: results are from a Python discrete-event simulation",
             ha="center", fontsize=7, style="italic")
    plt.tight_layout()
    return _save(fig, filename, figures_dir)


def plot_ml_metrics(ml_metrics_path: str, figures_dir: str) -> str:
    """Bar chart: RF vs Dummy precision/recall/F1 per class."""
    df = pd.read_csv(ml_metrics_path)
    df = df[df["label"] != "accuracy"]
    labels = df["label"].tolist()
    x = np.arange(len(labels))
    width = 0.14

    fig, ax = plt.subplots(figsize=(10, 5))
    metrics = ["precision", "recall", "f1"]
    colors_rf    = ["#4C72B0", "#55A868", "#C44E52"]
    colors_dummy = ["#A8C8E8", "#A8D8B8", "#F0A8A8"]

    for i, m in enumerate(metrics):
        rf_vals    = df[f"rf_{m}"].tolist()
        dummy_vals = df[f"dummy_{m}"].tolist()
        ax.bar(x + i * width * 2,       rf_vals,    width, label=f"RF {m}",    color=colors_rf[i])
        ax.bar(x + i * width * 2 + width, dummy_vals, width, label=f"Dummy {m}", color=colors_dummy[i])

    ax.set_xticks(x + width * 2.5)
    ax.set_xticklabels([lb.capitalize() for lb in labels])
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.15)
    ax.set_title("ML Classification Metrics -- Random Forest vs DummyClassifier")
    ax.legend(ncol=2, fontsize=8)
    plt.tight_layout()
    return _save(fig, "ml_metrics_comparison.png", figures_dir)


def run_evaluation(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    results_dir: str | None = None,
    figures_dir: str | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run Option A baseline evaluation.
    """
    if results_dir is None: results_dir = config.RESULTS_DIR
    if figures_dir is None: figures_dir = config.FIGURES_DIR
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    if verbose:
        print("[evaluation] Running simulations under all load scenarios ...")
    df = build_results_df(duration_s=duration_s, seed=seed)

    csv_path = os.path.join(results_dir, "evaluation_summary.csv")
    df.to_csv(csv_path, index=False)
    if verbose:
        print(f"[evaluation] Saved summary -> {csv_path}")

    plots = []
    p = plot_metric_by_class(df, "avg_delay_ms", "Avg Delay (ms)",
        "Average End-to-End Delay by Traffic Class",
        "delay_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    p = plot_metric_by_class(df, "avg_jitter_ms", "Avg Jitter (ms)",
        "Average Jitter by Traffic Class",
        "jitter_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    p = plot_metric_by_class(df, "packet_loss_pct", "Packet Loss (%)",
        "Packet Loss Percentage by Traffic Class",
        "loss_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    p = plot_metric_by_class(df, "throughput_mbps", "Throughput (Mbps)",
        "Throughput by Traffic Class",
        "throughput_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    p = plot_metric_by_load(df, "avg_delay_ms", "Avg Delay (ms)",
        "Voice Delay Under Different Load Levels",
        "delay_vs_load_voice.png", figures_dir, traffic_class="voice")
    plots.append(p)

    p = plot_metric_by_load(df, "packet_loss_pct", "Packet Loss (%)",
        "Video Packet Loss Under Different Load Levels",
        "loss_vs_load_video.png", figures_dir, traffic_class="video")
    plots.append(p)

    p = plot_metric_by_load(df, "throughput_mbps", "Throughput (Mbps)",
        "Background Throughput Under Different Load Levels",
        "throughput_vs_load_bg.png", figures_dir, traffic_class="background")
    plots.append(p)

    sub = df[(df["load_scenario"] == "medium")].groupby("scheduler")["link_util_pct"].mean()
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [SCHED_COLORS[s] for s in sub.index]
    bars = ax.bar([SCHED_LABELS[s] for s in sub.index], sub.values, color=colors, edgecolor="black")
    for bar, v in zip(bars, sub.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{v:.1f}%", ha="center", va="bottom")
    ax.set_ylabel("Link Utilisation (%)")
    ax.set_title("Link Utilisation at Medium Load")
    ax.set_ylim(0, 115)
    ax.axhline(100, color="red", linestyle="--", linewidth=1, label="100% capacity")
    ax.legend()
    plt.tight_layout()
    p = _save(fig, "link_utilisation.png", figures_dir)
    plots.append(p)

    ml_metrics_path = os.path.join(results_dir, "ml_metrics.csv")
    if os.path.exists(ml_metrics_path):
        p = plot_ml_metrics(ml_metrics_path, figures_dir)
        plots.append(p)

    return df


# ---------------------------------------------------------------------------
# Option B -- 3-Way Comparative Evaluation (FIFO vs Priority vs AI Dynamic)
# ---------------------------------------------------------------------------

def build_results_df_option_b(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
) -> pd.DataFrame:
    """
    Run FIFO, Priority, and AI-Driven Dynamic QoS across all scenarios:
    low, medium, high, changing, and sustained loads.
    """
    scenarios = list(config.LOAD_SCENARIOS.keys()) + ["changing", "sustained"]
    schedulers = ["fifo", "priority", "dynamic"]
    rows = []

    for scenario in scenarios:
        for sched in schedulers:
            res = run_simulation(
                scheduler=sched,
                load_scenario=scenario,
                duration_s=duration_s,
                seed=seed,
            )
            util = link_utilisation_pct(res)
            action_count = getattr(res, "controller_summary", {}).get("action_changes", 0)
            switching_freq = getattr(res, "controller_summary", {}).get("switching_frequency_per_minute", 0.0)

            for cls in config.TRAFFIC_CLASSES:
                rows.append({
                    "load_scenario":     scenario,
                    "scheduler":         sched,
                    "traffic_class":     cls,
                    "avg_delay_ms":      round(avg_delay_ms(res, cls),      4),
                    "avg_jitter_ms":     round(avg_jitter_ms(res, cls),     4),
                    "packet_loss_pct":   round(packet_loss_pct(res, cls),   4),
                    "throughput_mbps":   round(throughput_mbps(res, cls),   6),
                    "link_util_pct":     round(util,                        4),
                    "packets_offered":   packets_offered_count(res, cls),
                    "packets_delivered": packets_delivered_count(res, cls),
                    "packets_dropped":   packets_dropped_count(res, cls),
                    "duration_s":        res.duration_s,
                    "action_changes":    action_count,
                    "switching_freq_pm": switching_freq,
                })
    return pd.DataFrame(rows)


def plot_3way_metric_by_class(
    df: pd.DataFrame,
    metric_col: str,
    ylabel: str,
    title: str,
    filename: str,
    figures_dir: str,
    scenario: str = "medium",
) -> str:
    """3-way bar chart: FIFO vs Priority vs Dynamic QoS."""
    sub = df[df["load_scenario"] == scenario]
    classes = CLASS_ORDER
    schedulers = ["fifo", "priority", "dynamic"]
    x = np.arange(len(classes))
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, sched in enumerate(schedulers):
        vals = [
            sub[(sub["scheduler"] == sched) & (sub["traffic_class"] == c)][metric_col].values
            for c in classes
        ]
        vals = [v[0] if len(v) > 0 else 0.0 for v in vals]
        bars = ax.bar(x + (i - 1) * width, vals, width, label=SCHED_LABELS[sched],
                      color=SCHED_COLORS[sched], edgecolor="black", linewidth=0.5)
        for bar, val in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (max(vals) * 0.01 if max(vals) > 0 else 0.01),
                f"{val:.2f}", ha="center", va="bottom", fontsize=7.5,
            )

    ax.set_xticks(x)
    ax.set_xticklabels([c.capitalize() for c in classes])
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\n(scenario: {scenario.capitalize()} Load)")
    ax.legend(fontsize=8.5)
    ax.set_ylim(bottom=0)
    fig.text(0.5, -0.02, "Option B: Closed-Loop AI-Driven QoS vs Conventional Policies",
             ha="center", fontsize=7.5, style="italic")
    plt.tight_layout()
    return _save(fig, filename, figures_dir)


def plot_controller_timeline(
    action_history: list,
    figures_dir: str,
    filename: str = "controller_timeline.png",
) -> str:
    """Plot controller predictions and action transitions over simulation time."""
    if not action_history:
        return ""

    times = [d.timestamp_s for d in action_history]
    preds = [d.predicted_class for d in action_history]
    actions = [d.action for d in action_history]

    action_map = {"NORMAL": 0, "RECOVERY": 1, "PROTECT_REALTIME": 2, "SEVERE_CONGESTION": 3}
    pred_map   = {"normal": 0, "moderate": 1, "severe": 2}

    act_nums = [action_map.get(a, 0) for a in actions]
    pred_nums = [pred_map.get(p, 0) for p in preds]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    # Subplot 1: Predictions
    ax1.step(times, pred_nums, where="post", color="#D95F02", linewidth=2, marker="o", label="AI Congestion Prediction")
    ax1.set_yticks([0, 1, 2])
    ax1.set_yticklabels(["Normal", "Moderate", "Severe"])
    ax1.set_ylabel("Predicted State")
    ax1.set_title("AI Congestion Predictions and Dynamic QoS Actions Over Time (Changing Load)")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left")

    # Subplot 2: Actions
    ax2.step(times, act_nums, where="post", color="#1B9E77", linewidth=2.5, marker="s", label="Active QoS Action")
    ax2.set_yticks([0, 1, 2, 3])
    ax2.set_yticklabels(["NORMAL", "RECOVERY", "PROTECT_RT", "SEVERE_CONG"])
    ax2.set_ylabel("Applied QoS Action")
    ax2.set_xlabel("Simulation Time (seconds)")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper left")

    plt.tight_layout()
    return _save(fig, filename, figures_dir)


def plot_changing_load_comparison(
    figures_dir: str,
    duration_s: float = 30.0,
    seed: int = config.RANDOM_SEED,
) -> tuple[str, list]:
    """Run changing load simulation and plot delay and loss comparison."""
    res = run_changing_load_simulation(duration_s=duration_s, seed=seed)

    classes = CLASS_ORDER
    schedulers = ["fifo", "priority", "dynamic"]
    x = np.arange(len(classes))
    width = 0.25

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Delay chart
    for i, s in enumerate(schedulers):
        delays = [avg_delay_ms(res[s], c) for c in classes]
        ax1.bar(x + (i - 1) * width, delays, width, label=SCHED_LABELS[s], color=SCHED_COLORS[s], edgecolor="black")
    ax1.set_xticks(x)
    ax1.set_xticklabels([c.capitalize() for c in classes])
    ax1.set_ylabel("Average Delay (ms)")
    ax1.set_title("Changing Load: End-to-End Delay")
    ax1.legend(fontsize=8)
    ax1.grid(True, linestyle="--", alpha=0.3, axis="y")

    # Loss chart
    for i, s in enumerate(schedulers):
        losses = [packet_loss_pct(res[s], c) for c in classes]
        ax2.bar(x + (i - 1) * width, losses, width, label=SCHED_LABELS[s], color=SCHED_COLORS[s], edgecolor="black")
    ax2.set_xticks(x)
    ax2.set_xticklabels([c.capitalize() for c in classes])
    ax2.set_ylabel("Packet Loss (%)")
    ax2.set_title("Changing Load: Packet Loss %")
    ax2.legend(fontsize=8)
    ax2.grid(True, linestyle="--", alpha=0.3, axis="y")

    plt.tight_layout()
    plot_path = _save(fig, "changing_load_comparison.png", figures_dir)
    return plot_path, getattr(res["dynamic"], "action_history", [])


def run_evaluation_option_b(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    results_dir: str | None = None,
    figures_dir: str | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run full Option B comparative evaluation across all 3 approaches.
    Generates summary CSV and all Option B figures without overwriting Option A figures.
    """
    if results_dir is None: results_dir = config.RESULTS_DIR
    if figures_dir is None: figures_dir = config.FIGURES_DIR
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    if verbose:
        print("[evaluation_option_b] Running 3-way simulations across all load scenarios ...")
    df = build_results_df_option_b(duration_s=duration_s, seed=seed)

    csv_path = os.path.join(results_dir, "evaluation_summary_option_b.csv")
    df.to_csv(csv_path, index=False)
    if verbose:
        print(f"[evaluation_option_b] Saved Option B summary -> {csv_path}")

    # Generate 3-way comparison plots
    plots = []
    p = plot_3way_metric_by_class(df, "avg_delay_ms", "Avg Delay (ms)",
        "3-Way Delay Comparison: FIFO vs Priority vs Dynamic QoS",
        "delay_by_class_3way.png", figures_dir, scenario="medium")
    plots.append(p)

    p = plot_3way_metric_by_class(df, "avg_delay_ms", "Avg Delay (ms)",
        "High Load Delay Comparison: FIFO vs Priority vs Dynamic QoS",
        "delay_by_class_high_3way.png", figures_dir, scenario="high")
    plots.append(p)

    p = plot_3way_metric_by_class(df, "packet_loss_pct", "Packet Loss (%)",
        "3-Way Packet Loss Comparison",
        "loss_by_class_3way.png", figures_dir, scenario="high")
    plots.append(p)

    p = plot_3way_metric_by_class(df, "throughput_mbps", "Throughput (Mbps)",
        "3-Way Throughput Comparison",
        "throughput_by_class_3way.png", figures_dir, scenario="medium")
    plots.append(p)

    p = plot_3way_metric_by_class(df, "avg_jitter_ms", "Avg Jitter (ms)",
        "3-Way Jitter Comparison",
        "jitter_by_class_3way.png", figures_dir, scenario="high")
    plots.append(p)

    # Changing load simulation & timeline
    p_change, action_hist = plot_changing_load_comparison(figures_dir, seed=seed)
    plots.append(p_change)

    if action_hist:
        p_timeline = plot_controller_timeline(action_hist, figures_dir)
        plots.append(p_timeline)

    if verbose:
        print(f"[evaluation_option_b] Generated {len(plots)} Option B charts in {figures_dir}")

    return df


if __name__ == "__main__":
    run_evaluation(verbose=True)
    run_evaluation_option_b(verbose=True)
