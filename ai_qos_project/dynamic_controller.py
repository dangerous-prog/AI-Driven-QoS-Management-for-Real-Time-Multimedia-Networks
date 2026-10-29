"""
dynamic_controller.py
=====================
Closed-loop AI-Driven QoS Controller for Option B.

Implements the control loop:
  observe(metrics) -> predict_congestion() -> choose_action() -> apply_action() -> measure_outcome()

Features:
- Uses the pre-trained Random Forest model for congestion inference.
- Enforces strict rolling-window observation (no future data).
- Incorporates hysteresis (minimum dwell time) to prevent policy oscillation.
- Returns actionable QoS configurations (queue weights & scheduling modes).
- Maintains a detailed audit trail of predictions, actions, and timestamps.
"""

from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np

import config
from dataset_generation import FEATURE_COLUMNS, LABEL_COLUMN


@dataclass
class ControllerDecision:
    timestamp_s: float
    predicted_class: str
    probabilities: Dict[str, float]
    action: str
    action_params: Dict[str, Any]
    reason: str
    telemetry: Dict[str, Any]


class DynamicQoSController:
    """
    Closed-loop Dynamic QoS Controller.

    Decides scheduling policies dynamically based on observed real-time telemetry
    and Random Forest congestion predictions.
    """

    def __init__(
        self,
        min_action_duration_s: float = config.MIN_ACTION_DURATION_S,
        model=None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.min_action_duration_s = min_action_duration_s
        self.model = model
        self.metadata = metadata

        # State tracking
        self.current_action: str = "NORMAL"
        self.last_action_change_time: float = 0.0
        self.action_history: List[ControllerDecision] = []
        self.action_change_count: int = 0

        # Load default model if not provided
        if self.model is None:
            self._load_default_model()

    def _load_default_model(self):
        """Load trained Random Forest model from config.MODELS_DIR."""
        import joblib
        model_path = os.path.join(config.MODELS_DIR, "rf_model.joblib")
        meta_path  = os.path.join(config.MODELS_DIR, "model_metadata.json")

        if os.path.exists(model_path) and os.path.exists(meta_path):
            self.model = joblib.load(model_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self.model = None
            self.metadata = None

    def predict_congestion(self, feature_dict: Dict[str, Any]) -> tuple[str, Dict[str, float]]:
        """
        Predict congestion state using the pre-trained Random Forest model.

        Parameters
        ----------
        feature_dict : dict matching FEATURE_COLUMNS.

        Returns
        -------
        (predicted_class, class_probabilities_dict)
        """
        if self.model is None:
            # Fallback heuristic if model not loaded
            util = feature_dict.get("arrival_rate_pps", 0) / 1000.0
            if util > 0.90:
                return "severe", {"severe": 1.0, "moderate": 0.0, "normal": 0.0}
            elif util > 0.70:
                return "moderate", {"severe": 0.0, "moderate": 1.0, "normal": 0.0}
            return "normal", {"severe": 0.0, "moderate": 0.0, "normal": 1.0}

        # Build single-row DataFrame matching the exact training columns
        X = pd.DataFrame([feature_dict])[FEATURE_COLUMNS]
        pred_class = self.model.predict(X)[0]
        pred_proba = self.model.predict_proba(X)[0]
        classes    = self.model.classes_

        prob_dict = {
            cls_name: round(float(prob), 4)
            for cls_name, prob in zip(classes, pred_proba)
        }
        return pred_class, prob_dict

    def decide(
        self,
        current_time_s: float,
        interval_telemetry: Dict[str, Any],
    ) -> ControllerDecision:
        """
        Core decision function executed at the end of each observation interval.

        Parameters
        ----------
        current_time_s     : current simulated time (seconds)
        interval_telemetry : observed metrics over the elapsed window

        Returns
        -------
        ControllerDecision containing the action, parameters, and rationale.
        """
        # 1. Feature extraction from interval measurements
        pred_class, probabilities = self.predict_congestion(interval_telemetry)

        # 2. Hysteresis logic: time elapsed since last policy modification
        time_since_change = current_time_s - self.last_action_change_time
        can_change = time_since_change >= self.min_action_duration_s

        proposed_action = self.current_action
        reason = "Maintaining current state"

        # 3. State transition logic
        if pred_class == "severe":
            # Emergency escalation: bypass cooldown to protect real-time flows immediately
            if self.current_action != "SEVERE_CONGESTION":
                proposed_action = "SEVERE_CONGESTION"
                reason = "Emergency escalation: severe congestion detected"
            else:
                reason = "Severe congestion persists; maintaining strict protection"

        elif pred_class == "moderate":
            if self.current_action == "NORMAL":
                proposed_action = "PROTECT_REALTIME"
                reason = "Moderate congestion detected; escalating protection"
            elif self.current_action == "SEVERE_CONGESTION":
                if can_change:
                    proposed_action = "RECOVERY"
                    reason = "Congestion easing from severe to moderate; entering recovery"
                else:
                    reason = f"Cooldown active ({time_since_change:.1f}s < {self.min_action_duration_s}s); holding SEVERE_CONGESTION"
            elif self.current_action == "RECOVERY":
                proposed_action = "PROTECT_REALTIME"
                reason = "Moderate congestion holding; settling into PROTECT_REALTIME"
            else:
                reason = "Moderate congestion persists; maintaining PROTECT_REALTIME"

        elif pred_class == "normal":
            if self.current_action == "SEVERE_CONGESTION":
                if can_change:
                    proposed_action = "RECOVERY"
                    reason = "Congestion cleared; transitioning to RECOVERY before NORMAL"
                else:
                    reason = f"Cooldown active ({time_since_change:.1f}s < {self.min_action_duration_s}s); holding SEVERE_CONGESTION"
            elif self.current_action in ("PROTECT_REALTIME", "RECOVERY"):
                if can_change:
                    proposed_action = "NORMAL"
                    reason = "Network normal and cooldown satisfied; returning to NORMAL"
                else:
                    reason = f"Cooldown active ({time_since_change:.1f}s < {self.min_action_duration_s}s); holding {self.current_action}"
            else:
                reason = "Network normal; standard balanced QoS"

        # 4. Commit action if changed
        if proposed_action != self.current_action:
            self.current_action = proposed_action
            self.last_action_change_time = current_time_s
            self.action_change_count += 1

        action_params = config.QOS_ACTIONS.get(
            self.current_action, config.QOS_ACTIONS["NORMAL"]
        )

        decision = ControllerDecision(
            timestamp_s=current_time_s,
            predicted_class=pred_class,
            probabilities=probabilities,
            action=self.current_action,
            action_params=action_params,
            reason=reason,
            telemetry=interval_telemetry,
        )
        self.action_history.append(decision)
        return decision

    def get_summary_stats(self) -> Dict[str, Any]:
        """Compute controller operational metrics."""
        if not self.action_history:
            return {
                "total_decisions": 0,
                "action_changes": 0,
                "switching_frequency_per_minute": 0.0,
                "action_distribution": {},
            }

        total_decisions = len(self.action_history)
        duration_s = self.action_history[-1].timestamp_s if total_decisions > 0 else 1.0
        duration_min = max(duration_s / 60.0, 1.0 / 60.0)

        action_counts = {}
        for d in self.action_history:
            action_counts[d.action] = action_counts.get(d.action, 0) + 1

        return {
            "total_decisions": total_decisions,
            "action_changes": self.action_change_count,
            "switching_frequency_per_minute": round(self.action_change_count / duration_min, 2),
            "action_distribution": action_counts,
        }
