"""
predict_congestion.py
=====================
Congestion-prediction demonstration module.

Loads the trained Random Forest model and predicts the congestion state
from a set of current network measurements.

NOTE -- Phase 1 Advisory Mode
-----------------------------
In Phase 1 this module provides ADVISORY output only.
The prediction is displayed to the operator but does NOT automatically
adjust the scheduler.  A closed-loop AI QoS controller is planned for
Phase 2 (Option B).

Usage (command line)
--------------------
    python predict_congestion.py --scenario medium --scheduler fifo

Usage (API)
-----------
    from predict_congestion import predict_from_simulation
    result_dict = predict_from_simulation(sim_result)
"""

from __future__ import annotations
import os
import json
import joblib
import numpy as np
import pandas as pd
import argparse

import config
from dataset_generation import FEATURE_COLUMNS
from traffic_simulation import run_simulation
from metrics import (
    avg_delay_ms, avg_jitter_ms, packet_loss_pct,
    throughput_mbps, link_utilisation_pct,
)


def load_model(model_dir: str | None = None):
    """Load the trained RF model and its metadata."""
    if model_dir is None:
        model_dir = config.MODELS_DIR
    model_path = os.path.join(model_dir, "rf_model.joblib")
    meta_path  = os.path.join(model_dir, "model_metadata.json")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Model not found at {model_path}. "
            "Run train_model.py first."
        )
    model = joblib.load(model_path)
    with open(meta_path) as f:
        metadata = json.load(f)
    return model, metadata


def extract_features(sim_result, load_multiplier: float) -> dict:
    """
    Extract the same feature set used during training from a SimulationResult.

    Parameters
    ----------
    sim_result     : SimulationResult from schedulers.py
    load_multiplier: the multiplier used when generating traffic

    Returns
    -------
    dict mapping feature_name -> value
    """
    total_arrivals = sum(sim_result.offered.values())
    total_dropped  = sum(sim_result.dropped.values())
    arrival_rate   = total_arrivals / sim_result.duration_s
    queue_fill_proxy = (
        total_dropped / total_arrivals if total_arrivals > 0 else 0.0
    )

    return {
        "load_multiplier":       load_multiplier,
        "arrival_rate_pps":      round(arrival_rate, 2),
        "queue_fill_proxy":      round(queue_fill_proxy, 6),
        "voice_delay_ms":        round(avg_delay_ms(sim_result, "voice"),      4),
        "video_delay_ms":        round(avg_delay_ms(sim_result, "video"),      4),
        "bg_delay_ms":           round(avg_delay_ms(sim_result, "background"), 4),
        "voice_loss_pct":        round(packet_loss_pct(sim_result, "voice"),      4),
        "video_loss_pct":        round(packet_loss_pct(sim_result, "video"),      4),
        "bg_loss_pct":           round(packet_loss_pct(sim_result, "background"), 4),
        "voice_jitter_ms":       round(avg_jitter_ms(sim_result, "voice"),      4),
        "video_jitter_ms":       round(avg_jitter_ms(sim_result, "video"),      4),
        "throughput_total_mbps": round(
            sum(throughput_mbps(sim_result, c) for c in config.TRAFFIC_CLASSES), 6
        ),
    }


def predict_from_simulation(
    sim_result,
    load_multiplier: float,
    model=None,
    metadata: dict | None = None,
) -> dict:
    """
    Predict congestion state from a simulation result.

    Parameters
    ----------
    sim_result      : SimulationResult
    load_multiplier : the multiplier passed to generate_arrivals
    model           : pre-loaded RF model (loaded from disk if None)
    metadata        : model metadata dict (loaded from disk if None)

    Returns
    -------
    dict with keys:
      predicted_class  : str  ("normal" | "moderate" | "severe")
      probabilities    : dict label -> probability
      features         : dict of input feature values
      advice           : human-readable advisory string (Phase 1)
    """
    if model is None:
        model, metadata = load_model()
    elif metadata is None:
        # model was provided but metadata wasn't -- load metadata only
        _, metadata = load_model()

    features = extract_features(sim_result, load_multiplier)
    X = pd.DataFrame([features])[FEATURE_COLUMNS]

    pred_class   = model.predict(X)[0]
    pred_proba   = model.predict_proba(X)[0]
    label_order  = model.classes_

    probabilities = {
        label: round(float(prob), 4)
        for label, prob in zip(label_order, pred_proba)
    }

    advice_map = {
        "normal":   "[OK] Network is operating normally. No action needed.",
        "moderate": "WARN️  Moderate congestion detected. Consider adjusting priorities or reducing load.",
        "severe":   "[ALERT] Severe congestion detected. Activate QoS controls or alert the operator.",
    }

    return {
        "predicted_class": pred_class,
        "probabilities":   probabilities,
        "features":        features,
        "advice":          advice_map.get(pred_class, "Unknown state."),
        "note": (
            "[Phase 1 -- Advisory Only] This prediction is informational. "
            "No automated QoS adjustment has been applied."
        ),
    }


def _print_prediction(result: dict) -> None:
    """Pretty-print a prediction result to the console."""
    print("\n" + "=" * 58)
    print("  AI CONGESTION PREDICTION (Phase 1 -- Advisory Only)")
    print("=" * 58)
    print(f"  Predicted state : {result['predicted_class'].upper()}")
    print(f"  Advice          : {result['advice']}")
    print("\n  Probabilities:")
    for label, prob in result["probabilities"].items():
        bar = "#" * int(prob * 30)
        print(f"    {label:12s}: {prob:.4f}  {bar}")
    print("\n  Input features:")
    for k, v in result["features"].items():
        print(f"    {k:30s}: {v}")
    print(f"\n  {result['note']}")
    print("=" * 58 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run congestion prediction demo.")
    parser.add_argument("--scenario",  default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--scheduler", default="fifo",   choices=["fifo", "priority"])
    args = parser.parse_args()

    print(f"[predict_congestion] Running {args.scheduler} simulation at {args.scenario} load ...")
    sim_result = run_simulation(
        scheduler=args.scheduler,
        load_scenario=args.scenario,
    )
    multiplier = config.LOAD_SCENARIOS[args.scenario]["multiplier"]

    model, metadata = load_model()
    result = predict_from_simulation(sim_result, multiplier, model, metadata)
    _print_prediction(result)
