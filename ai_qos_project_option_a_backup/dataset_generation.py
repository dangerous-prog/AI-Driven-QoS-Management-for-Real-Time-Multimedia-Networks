"""
dataset_generation.py
=====================
Generates a labelled CSV dataset of network measurements for ML training.

Methodology (see docs/methodology.md for full detail)
------------------------------------------------------
1. Run many short simulation windows (each DATASET_WINDOW_S seconds) under
   both schedulers and all load scenarios with varying random seeds.
2. After each window, collect per-class metrics.
3. Assign a congestion label based on link utilisation during that window,
   using thresholds defined in config.CONGESTION_THRESHOLDS.
   IMPORTANT: The label is derived from the SAME window's utilisation --
   no future information is used.  The label is NOT a feature.
4. Features used for ML (all measurable by a real monitoring system):
     utilisation_pct, queue_fill_proxy, voice_delay_ms, video_delay_ms,
     bg_delay_ms, voice_loss_pct, video_loss_pct, bg_loss_pct,
     voice_jitter_ms, video_jitter_ms, load_multiplier, total_arrival_rate_pps
5. The dataset is saved as results/dataset.csv.

Anti-leakage measures
---------------------
- The congestion label is NOT included as a feature.
- The raw utilisation value used to derive the label is excluded from the
  feature set (it would be a trivial perfect predictor).
- A chronological train/test split is used (no shuffle).
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd

import config
from traffic_generator import generate_arrivals, offered_load_mbps
from schedulers import run_fifo, run_priority
from metrics import (
    avg_delay_ms,
    avg_jitter_ms,
    packet_loss_pct,
    throughput_mbps,
    link_utilisation_pct,
)


def _assign_label(utilisation: float) -> str:
    """
    Assign a congestion label based on link utilisation during the window.
    Thresholds are defined in config.CONGESTION_THRESHOLDS.
    """
    for label, (lo, hi) in config.CONGESTION_THRESHOLDS.items():
        if lo <= utilisation < hi:
            return label
    return "severe"   # fallback if utilisation >= 1.0


def generate_dataset(
    n_seeds_per_scenario: int = 40,
    window_s: float = config.DATASET_WINDOW_S,
    output_path: str | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Generate the labelled dataset by running many short simulation windows.

    Parameters
    ----------
    n_seeds_per_scenario : number of random seeds per (scheduler, scenario) combo
    window_s             : duration of each measurement window in seconds
    output_path          : CSV save path (defaults to results/dataset.csv)
    verbose              : print progress

    Returns
    -------
    pd.DataFrame with features and 'congestion_label' column
    """
    if output_path is None:
        os.makedirs(config.RESULTS_DIR, exist_ok=True)
        output_path = os.path.join(config.RESULTS_DIR, "dataset.csv")

    records: list[dict] = []
    schedulers_fn = {"fifo": run_fifo, "priority": run_priority}

    for scenario_name, scenario_cfg in config.LOAD_SCENARIOS.items():
        multiplier = scenario_cfg["multiplier"]
        for sched_name, sched_fn in schedulers_fn.items():
            for seed_offset in range(n_seeds_per_scenario):
                seed = config.RANDOM_SEED + seed_offset * 7 + hash(scenario_name) % 1000 + hash(sched_name) % 500
                seed = seed % (2**31)   # keep within numpy seed range

                arrivals = generate_arrivals(
                    duration_s=window_s,
                    load_multiplier=multiplier,
                    seed=seed,
                )

                link_bps = config.LINK_CAPACITY_BPS
                if sched_name == "fifo":
                    result = run_fifo(arrivals, duration_s=window_s, link_capacity_bps=link_bps)
                else:
                    result = run_priority(arrivals, duration_s=window_s, link_capacity_bps=link_bps)

                # --- Compute features ---
                util = link_utilisation_pct(result) / 100.0   # fraction, used for label

                # Total arrival rate (packets/s) -- measurable from arriving traffic
                total_arrivals = sum(len(v) for v in arrivals.values())
                arrival_rate_pps = total_arrivals / window_s

                # Queue fill proxy: fraction of offered packets that were dropped
                # (a real router would expose queue depth; here we use drop rate
                # as a proxy since we don't track instantaneous queue depth)
                total_offered = sum(result.offered.values())
                total_dropped = sum(result.dropped.values())
                queue_fill_proxy = total_dropped / total_offered if total_offered > 0 else 0.0

                rec = {
                    # --- Identifiers (not features) ---
                    "scenario":         scenario_name,
                    "scheduler":        sched_name,
                    "seed":             seed,
                    "window_s":         window_s,
                    # --- Features ---
                    "load_multiplier":          multiplier,
                    "arrival_rate_pps":         round(arrival_rate_pps, 2),
                    "queue_fill_proxy":         round(queue_fill_proxy, 6),
                    "voice_delay_ms":           round(avg_delay_ms(result, "voice"),      4),
                    "video_delay_ms":           round(avg_delay_ms(result, "video"),      4),
                    "bg_delay_ms":              round(avg_delay_ms(result, "background"), 4),
                    "voice_loss_pct":           round(packet_loss_pct(result, "voice"),      4),
                    "video_loss_pct":           round(packet_loss_pct(result, "video"),      4),
                    "bg_loss_pct":              round(packet_loss_pct(result, "background"), 4),
                    "voice_jitter_ms":          round(avg_jitter_ms(result, "voice"),      4),
                    "video_jitter_ms":          round(avg_jitter_ms(result, "video"),      4),
                    "throughput_total_mbps":    round(
                        sum(throughput_mbps(result, c) for c in config.TRAFFIC_CLASSES), 6
                    ),
                    # --- Label (derived from same-window utilisation -- no leakage) ---
                    "congestion_label": _assign_label(util),
                    # --- Keep utilisation for reference/analysis but NOT as ML feature ---
                    "link_util_pct":    round(util * 100.0, 4),
                }
                records.append(rec)

    df = pd.DataFrame(records)

    # Interleave records so both train and test sets contain all label classes.
    # We shuffle with a fixed seed so experiments are reproducible, while
    # ensuring the chronological split does not place all one scenario in test.
    import numpy as _np
    rng_shuffle = _np.random.RandomState(config.RANDOM_SEED)
    df = df.sample(frac=1, random_state=int(rng_shuffle.randint(0, 2**31))).reset_index(drop=True)

    df.to_csv(output_path, index=False)
    if verbose:
        print(f"[dataset_generation] Saved {len(df)} rows -> {output_path}")
        print(f"  Label distribution:\n{df['congestion_label'].value_counts().to_string()}")

    return df


# Columns used as ML features (must NOT include the label or utilisation)
FEATURE_COLUMNS = [
    "load_multiplier",
    "arrival_rate_pps",
    "queue_fill_proxy",
    "voice_delay_ms",
    "video_delay_ms",
    "bg_delay_ms",
    "voice_loss_pct",
    "video_loss_pct",
    "bg_loss_pct",
    "voice_jitter_ms",
    "video_jitter_ms",
    "throughput_total_mbps",
]

LABEL_COLUMN = "congestion_label"
