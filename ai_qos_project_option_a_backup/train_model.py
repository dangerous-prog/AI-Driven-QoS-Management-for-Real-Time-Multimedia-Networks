"""
train_model.py
==============
Trains a Random Forest congestion-level classifier and evaluates it.

Workflow
--------
1. Load (or regenerate) the labelled dataset from dataset_generation.py.
2. Split using a CHRONOLOGICAL split (first 70% train, last 30% test).
   This avoids data leakage because the dataset is ordered by scenario/seed.
3. Train a Random Forest classifier.
4. Compare with a DummyClassifier baseline (most-frequent strategy).
5. Report accuracy, precision, recall, F1, and confusion matrix.
6. Save the trained model + metadata to models/.

Output files
------------
models/rf_model.joblib         -- trained RandomForestClassifier
models/model_metadata.json     -- feature list, label order, training params
results/ml_report.txt          -- text classification report
results/confusion_matrix.png   -- confusion-matrix heatmap
results/ml_metrics.csv         -- per-class precision/recall/F1
"""

from __future__ import annotations
import os
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")   # non-interactive backend for script use

from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    ConfusionMatrixDisplay,
)

import config
from dataset_generation import FEATURE_COLUMNS, LABEL_COLUMN


def load_or_generate_dataset(dataset_path: str | None = None) -> pd.DataFrame:
    """Load existing dataset or generate a fresh one."""
    if dataset_path is None:
        dataset_path = os.path.join(config.RESULTS_DIR, "dataset.csv")

    if os.path.exists(dataset_path):
        print(f"[train_model] Loading existing dataset from {dataset_path}")
        return pd.read_csv(dataset_path)
    else:
        print("[train_model] Dataset not found -- generating now ...")
        from dataset_generation import generate_dataset
        return generate_dataset(output_path=dataset_path)


def chronological_split(df: pd.DataFrame, train_frac: float = config.TRAIN_FRACTION):
    """
    Split the dataset chronologically (first train_frac rows -> train,
    remainder -> test).  No shuffle to prevent leakage between similar windows.
    """
    n_train = int(len(df) * train_frac)
    return df.iloc[:n_train].copy(), df.iloc[n_train:].copy()


def train_and_evaluate(
    dataset_path: str | None = None,
    model_dir: str | None = None,
    results_dir: str | None = None,
    figures_dir: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    Full train + evaluate pipeline.

    Returns a dict with accuracy, per-class metrics, and file paths.
    """
    if model_dir   is None: model_dir   = config.MODELS_DIR
    if results_dir is None: results_dir = config.RESULTS_DIR
    if figures_dir is None: figures_dir = config.FIGURES_DIR

    os.makedirs(model_dir,   exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    df = load_or_generate_dataset(dataset_path)

    X = df[FEATURE_COLUMNS]
    y = df[LABEL_COLUMN]

    train_df, test_df = chronological_split(df)
    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df[LABEL_COLUMN]
    X_test  = test_df[FEATURE_COLUMNS]
    y_test  = test_df[LABEL_COLUMN]

    if verbose:
        print(f"[train_model] Train size: {len(X_train)}, Test size: {len(X_test)}")
        print(f"  Train label dist:\n{y_train.value_counts().to_string()}")
        print(f"  Test label dist:\n{y_test.value_counts().to_string()}")

    # -----------------------------------------------------------------------
    # Random Forest
    # -----------------------------------------------------------------------
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=config.RANDOM_SEED,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    y_pred_rf = rf.predict(X_test)

    acc_rf   = accuracy_score(y_test, y_pred_rf)
    report_rf = classification_report(
        y_test, y_pred_rf,
        labels=config.CONGESTION_LABELS,
        target_names=config.CONGESTION_LABELS,
        output_dict=True,
    )

    # -----------------------------------------------------------------------
    # DummyClassifier baseline
    # -----------------------------------------------------------------------
    dummy = DummyClassifier(strategy="most_frequent", random_state=config.RANDOM_SEED)
    dummy.fit(X_train, y_train)
    y_pred_dummy = dummy.predict(X_test)
    acc_dummy = accuracy_score(y_test, y_pred_dummy)
    report_dummy = classification_report(
        y_test, y_pred_dummy,
        labels=config.CONGESTION_LABELS,
        target_names=config.CONGESTION_LABELS,
        output_dict=True,
        zero_division=0,
    )

    if verbose:
        print(f"\n[train_model] Random Forest accuracy : {acc_rf:.4f}")
        print(f"[train_model] DummyClassifier accuracy: {acc_dummy:.4f}")
        print("\nRandom Forest Classification Report:")
        print(classification_report(
            y_test, y_pred_rf,
            labels=config.CONGESTION_LABELS,
            target_names=config.CONGESTION_LABELS,
            zero_division=0,
        ))

    # -----------------------------------------------------------------------
    # Save confusion matrix plot
    # -----------------------------------------------------------------------
    cm = confusion_matrix(y_test, y_pred_rf, labels=config.CONGESTION_LABELS)
    fig, ax = plt.subplots(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=config.CONGESTION_LABELS)
    disp.plot(ax=ax, colorbar=True, cmap="Blues")
    ax.set_title("Confusion Matrix -- Random Forest Congestion Classifier\n(simulated data)")
    plt.tight_layout()
    cm_path = os.path.join(figures_dir, "confusion_matrix.png")
    fig.savefig(cm_path, dpi=120)
    plt.close(fig)

    # -----------------------------------------------------------------------
    # Save ML metrics CSV
    # -----------------------------------------------------------------------
    rows = []
    for cls in config.CONGESTION_LABELS:
        rf_row    = report_rf.get(cls,    {})
        dummy_row = report_dummy.get(cls, {})
        rows.append({
            "label":            cls,
            "rf_precision":     round(rf_row.get("precision", 0), 4),
            "rf_recall":        round(rf_row.get("recall",    0), 4),
            "rf_f1":            round(rf_row.get("f1-score",  0), 4),
            "rf_support":       rf_row.get("support", 0),
            "dummy_precision":  round(dummy_row.get("precision", 0), 4),
            "dummy_recall":     round(dummy_row.get("recall",    0), 4),
            "dummy_f1":         round(dummy_row.get("f1-score",  0), 4),
        })
    rows.append({
        "label": "accuracy",
        "rf_precision": round(acc_rf, 4),
        "rf_recall":    round(acc_rf, 4),
        "rf_f1":        round(acc_rf, 4),
        "rf_support":   len(y_test),
        "dummy_precision": round(acc_dummy, 4),
        "dummy_recall":    round(acc_dummy, 4),
        "dummy_f1":        round(acc_dummy, 4),
    })
    metrics_df = pd.DataFrame(rows)
    metrics_path = os.path.join(results_dir, "ml_metrics.csv")
    metrics_df.to_csv(metrics_path, index=False)

    # -----------------------------------------------------------------------
    # Save text report
    # -----------------------------------------------------------------------
    report_path = os.path.join(results_dir, "ml_report.txt")
    with open(report_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("AI-Driven QoS -- ML Congestion Prediction Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Train samples: {len(X_train)}\n")
        f.write(f"Test  samples: {len(X_test)}\n\n")
        f.write("--- Random Forest ---\n")
        f.write(f"Accuracy: {acc_rf:.4f}\n")
        f.write(classification_report(
            y_test, y_pred_rf,
            labels=config.CONGESTION_LABELS,
            target_names=config.CONGESTION_LABELS,
            zero_division=0,
        ))
        f.write("\n--- DummyClassifier (most_frequent) ---\n")
        f.write(f"Accuracy: {acc_dummy:.4f}\n")
        f.write(classification_report(
            y_test, y_pred_dummy,
            labels=config.CONGESTION_LABELS,
            target_names=config.CONGESTION_LABELS,
            zero_division=0,
        ))

    # -----------------------------------------------------------------------
    # Save model + metadata
    # -----------------------------------------------------------------------
    model_path = os.path.join(model_dir, "rf_model.joblib")
    joblib.dump(rf, model_path)

    metadata = {
        "feature_columns":    FEATURE_COLUMNS,
        "label_column":       LABEL_COLUMN,
        "congestion_labels":  config.CONGESTION_LABELS,
        "n_estimators":       rf.n_estimators,
        "max_depth":          rf.max_depth,
        "random_state":       config.RANDOM_SEED,
        "train_accuracy":     round(float(accuracy_score(y_train, rf.predict(X_train))), 4),
        "test_accuracy":      round(float(acc_rf), 4),
        "dummy_accuracy":     round(float(acc_dummy), 4),
    }
    meta_path = os.path.join(model_dir, "model_metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    if verbose:
        print(f"\n[train_model] Saved model  -> {model_path}")
        print(f"[train_model] Saved meta   -> {meta_path}")
        print(f"[train_model] Saved CM     -> {cm_path}")
        print(f"[train_model] Saved report -> {report_path}")
        print(f"[train_model] Saved metrics-> {metrics_path}")

    return {
        "rf_accuracy":    acc_rf,
        "dummy_accuracy": acc_dummy,
        "report_rf":      report_rf,
        "cm":             cm,
        "model_path":     model_path,
        "cm_path":        cm_path,
        "metrics_path":   metrics_path,
        "report_path":    report_path,
        "X_test":         X_test,
        "y_test":         y_test,
        "y_pred":         y_pred_rf,
    }


if __name__ == "__main__":
    train_and_evaluate()
