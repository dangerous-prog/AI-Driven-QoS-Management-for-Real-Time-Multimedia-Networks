"""
evaluation.py
=============
Runs the full performance comparison and generates all graphs and CSVs.

Configurations evaluated
------------------------
1. FIFO baseline          -- no QoS differentiation
2. Strict Priority QoS    -- voice > video > background
3. AI Advisory prediction -- evaluated alongside networking metrics
   (the AI model does NOT control the scheduler in Phase 1)

Output files
------------
results/evaluation_summary.csv   -- per-class metrics for all configs / loads
results/figures/*.png             -- comparison charts

Fair comparison guarantee
-------------------------
Both schedulers use IDENTICAL arrivals (same seed, same multiplier, same duration).
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
from traffic_simulation import run_simulation, run_all_scenarios
from metrics import (
    avg_delay_ms, avg_jitter_ms, packet_loss_pct,
    throughput_mbps, link_utilisation_pct,
    packets_offered_count, packets_delivered_count, packets_dropped_count,
)


# ---------------------------------------------------------------------------
# Build per-class results DataFrame
# ---------------------------------------------------------------------------
def build_results_df(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
) -> pd.DataFrame:
    """
    Run both schedulers under all load scenarios and collect metrics.
    Returns a wide-format DataFrame.
    """
    all_results = run_all_scenarios(duration_s=duration_s, seed=seed)
    rows = []
    for scenario, sched_dict in all_results.items():
        for sched_name, result in sched_dict.items():
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


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------
SCHED_COLORS = {"fifo": "#4C72B0", "priority": "#DD8452"}
SCHED_LABELS = {"fifo": "FIFO Baseline", "priority": "Priority QoS"}
LOAD_ORDER   = ["low", "medium", "high"]
CLASS_ORDER  = ["voice", "video", "background"]


def _save(fig: plt.Figure, name: str, figures_dir: str) -> str:
    path = os.path.join(figures_dir, name)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


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


# ---------------------------------------------------------------------------
# Full evaluation pipeline
# ---------------------------------------------------------------------------
def run_evaluation(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    results_dir: str | None = None,
    figures_dir: str | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run the complete evaluation: simulations -> metrics -> graphs -> CSV.

    Returns the results DataFrame.
    """
    if results_dir is None: results_dir = config.RESULTS_DIR
    if figures_dir is None: figures_dir = config.FIGURES_DIR
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    if verbose:
        print("[evaluation] Running simulations under all load scenarios ...")
    df = build_results_df(duration_s=duration_s, seed=seed)

    # Save summary CSV
    csv_path = os.path.join(results_dir, "evaluation_summary.csv")
    df.to_csv(csv_path, index=False)
    if verbose:
        print(f"[evaluation] Saved summary -> {csv_path}")

    # --- Plots ---
    plots = []

    # 1. Average delay by traffic class (medium load)
    p = plot_metric_by_class(df, "avg_delay_ms", "Avg Delay (ms)",
        "Average End-to-End Delay by Traffic Class",
        "delay_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    # 2. Average jitter by traffic class (medium load)
    p = plot_metric_by_class(df, "avg_jitter_ms", "Avg Jitter (ms)",
        "Average Jitter by Traffic Class",
        "jitter_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    # 3. Packet loss by traffic class (medium load)
    p = plot_metric_by_class(df, "packet_loss_pct", "Packet Loss (%)",
        "Packet Loss Percentage by Traffic Class",
        "loss_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    # 4. Throughput by traffic class (medium load)
    p = plot_metric_by_class(df, "throughput_mbps", "Throughput (Mbps)",
        "Throughput by Traffic Class",
        "throughput_by_class.png", figures_dir, scenario="medium")
    plots.append(p)

    # 5. Voice delay vs load (all scenarios)
    p = plot_metric_by_load(df, "avg_delay_ms", "Avg Delay (ms)",
        "Voice Delay Under Different Load Levels",
        "delay_vs_load_voice.png", figures_dir, traffic_class="voice")
    plots.append(p)

    # 6. Packet loss vs load for video
    p = plot_metric_by_load(df, "packet_loss_pct", "Packet Loss (%)",
        "Video Packet Loss Under Different Load Levels",
        "loss_vs_load_video.png", figures_dir, traffic_class="video")
    plots.append(p)

    # 7. Throughput vs load for background
    p = plot_metric_by_load(df, "throughput_mbps", "Throughput (Mbps)",
        "Background Throughput Under Different Load Levels",
        "throughput_vs_load_bg.png", figures_dir, traffic_class="background")
    plots.append(p)

    # 8. Combined bar: link utilisation at medium load
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

    if verbose:
        print(f"[evaluation] Saved {len(plots)} figures to {figures_dir}")

    # Try to plot ML metrics if file exists
    ml_metrics_path = os.path.join(results_dir, "ml_metrics.csv")
    if os.path.exists(ml_metrics_path):
        p = plot_ml_metrics(ml_metrics_path, figures_dir)
        plots.append(p)
        if verbose:
            print(f"[evaluation] Saved ML metrics chart -> {p}")

    return df


if __name__ == "__main__":
    run_evaluation(verbose=True)
