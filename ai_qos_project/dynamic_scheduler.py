"""
dynamic_scheduler.py
====================
Closed-loop, AI-controlled dynamic packet scheduler for Option B.

Implements an adaptive work-conserving queue scheduler where the scheduling
policy (quanta weights and priority enforcement) is updated dynamically at
discrete control intervals based on AI controller decisions.

Policies enforced:
- NORMAL: Weighted service (Voice: 40%, Video: 35%, Background: 25%) ensuring fair
  latency and high throughput for background traffic when network is healthy.
- PROTECT_REALTIME: Real-time biased weights (Voice: 60%, Video: 30%, Background: 10%).
- SEVERE_CONGESTION: Strict Priority (Voice > Video > Background) where latency-critical
  traffic is protected unconditionally against heavy background floods.
- RECOVERY: Hysteresis transition weights (Voice: 50%, Video: 30%, Background: 20%).
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import numpy as np

import config
from schedulers import DeliveredPacket, SimulationResult, _merge_arrivals
from dynamic_controller import DynamicQoSController, ControllerDecision


@dataclass
class DynamicSimulationResult(SimulationResult):
    """Extends SimulationResult to include closed-loop control telemetry."""
    action_history: List[ControllerDecision] = field(default_factory=list)
    controller_summary: Dict[str, Any] = field(default_factory=dict)
    interval_telemetry: List[Dict[str, Any]] = field(default_factory=list)


def _compute_interval_features(
    interval_arrivals: List[dict],
    interval_delivered: List[DeliveredPacket],
    interval_dropped: Dict[str, int],
    interval_dur: float,
    current_time: float,
) -> Dict[str, Any]:
    """
    Extract feature dictionary for the completed control interval.
    Uses strictly measurements from the elapsed interval (no future info).
    """
    total_offered = len(interval_arrivals)
    total_dropped = sum(interval_dropped.values())
    arrival_rate_pps = total_offered / interval_dur if interval_dur > 0 else 0.0
    queue_fill_proxy = total_dropped / total_offered if total_offered > 0 else 0.0

    # Class-specific delivered packets
    by_class = {cls: [p for p in interval_delivered if p.cls == cls] for cls in config.TRAFFIC_CLASSES}

    def _mean_delay(pkts):
        return float(np.mean([p.delay_ms for p in pkts])) if pkts else 0.0

    def _mean_jitter(pkts):
        if len(pkts) < 2:
            return 0.0
        sorted_p = sorted(pkts, key=lambda p: p.finish_s)
        delays = np.array([p.delay_ms for p in sorted_p])
        return float(np.mean(np.abs(np.diff(delays))))

    def _loss_pct(cls):
        offered = len([p for p in interval_arrivals if p["class"] == cls])
        if offered == 0:
            return 0.0
        dropped = interval_dropped.get(cls, 0)
        return float(dropped / offered * 100.0)

    # Estimate load multiplier from arrival rate relative to base rates
    base_total_rate = sum(cfg["base_arrival_rate"] for cfg in config.TRAFFIC_CLASSES.values())
    estimated_mult = round(arrival_rate_pps / base_total_rate, 2) if base_total_rate > 0 else 1.0

    total_bits = sum(p.size_bytes * 8 for p in interval_delivered)
    total_throughput_mbps = total_bits / interval_dur / 1e6 if interval_dur > 0 else 0.0

    return {
        "load_multiplier":       max(estimated_mult, 0.5),
        "arrival_rate_pps":      round(arrival_rate_pps, 2),
        "queue_fill_proxy":      round(queue_fill_proxy, 6),
        "voice_delay_ms":        round(_mean_delay(by_class["voice"]), 4),
        "video_delay_ms":        round(_mean_delay(by_class["video"]), 4),
        "bg_delay_ms":           round(_mean_delay(by_class["background"]), 4),
        "voice_loss_pct":        round(_loss_pct("voice"), 4),
        "video_loss_pct":        round(_loss_pct("video"), 4),
        "bg_loss_pct":           round(_loss_pct("background"), 4),
        "voice_jitter_ms":       round(_mean_jitter(by_class["voice"]), 4),
        "video_jitter_ms":       round(_mean_jitter(by_class["video"]), 4),
        "throughput_total_mbps": round(total_throughput_mbps, 6),
    }


def run_dynamic_qos(
    arrivals: dict[str, list[dict]],
    duration_s: float,
    link_capacity_bps: float = config.LINK_CAPACITY_BPS,
    controller: Optional[DynamicQoSController] = None,
    control_interval_s: float = config.CONTROL_INTERVAL_S,
) -> DynamicSimulationResult:
    """
    Run closed-loop AI-driven dynamic QoS simulation.

    Parameters
    ----------
    arrivals           : dict mapping class name -> list of packet dicts
    duration_s         : simulation duration in seconds
    link_capacity_bps  : link speed in bits per second
    controller         : DynamicQoSController instance (created if None)
    control_interval_s : control loop step in seconds (default 1.0s)

    Returns
    -------
    DynamicSimulationResult with packet delivery records, drops, and control history.
    """
    if controller is None:
        controller = DynamicQoSController()

    result = DynamicSimulationResult(
        scheduler_name="AI-Driven Dynamic QoS",
        duration_s=duration_s,
    )

    for cls, pkts in arrivals.items():
        result.offered[cls] = len(pkts)

    # Separate queues per class
    queues: Dict[str, deque] = {cls: deque() for cls in config.TRAFFIC_CLASSES}
    queue_limits: Dict[str, int] = {
        cls: cfg["queue_max_packets"] for cls, cfg in config.TRAFFIC_CLASSES.items()
    }

    all_pkts = _merge_arrivals(arrivals)
    n_pkts = len(all_pkts)
    pkt_index = 0

    link_free_at = 0.0
    current_time = 0.0

    # Active QoS action and scheduling mode
    active_action = controller.current_action
    active_params = config.QOS_ACTIONS.get(active_action, config.QOS_ACTIONS["NORMAL"])

    # Deficit / Byte Quotas for Weighted Modes (base quantum = 1500 bytes)
    BASE_QUANTUM_BYTES = 3000
    def _compute_quanta(weights_dict):
        return {
            "voice":      int(weights_dict["voice_weight"] * BASE_QUANTUM_BYTES * 2),
            "video":      int(weights_dict["video_weight"] * BASE_QUANTUM_BYTES * 2),
            "background": int(weights_dict["bg_weight"]    * BASE_QUANTUM_BYTES * 2),
        }

    current_quanta = _compute_quanta(active_params)
    quanta_remaining = dict(current_quanta)

    # Tracking per interval for closed-loop observation
    next_control_time = control_interval_s
    interval_arrivals: List[dict] = []
    interval_delivered: List[DeliveredPacket] = []
    interval_dropped: Dict[str, int] = {cls: 0 for cls in config.TRAFFIC_CLASSES}

    priority_order = sorted(
        config.TRAFFIC_CLASSES.keys(),
        key=lambda c: config.TRAFFIC_CLASSES[c]["priority"],
    )

    while pkt_index < n_pkts or any(len(q) > 0 for q in queues.values()):

        # Check if we crossed into a new control interval
        if current_time >= next_control_time and next_control_time <= duration_s:
            # 1. Observe completed interval telemetry
            telemetry = _compute_interval_features(
                interval_arrivals=interval_arrivals,
                interval_delivered=interval_delivered,
                interval_dropped=interval_dropped,
                interval_dur=control_interval_s,
                current_time=next_control_time,
            )
            result.interval_telemetry.append(telemetry)

            # 2. Controller decides action
            decision = controller.decide(next_control_time, telemetry)

            # 3. Apply action to scheduler
            active_action = decision.action
            active_params = decision.action_params
            current_quanta = _compute_quanta(active_params)
            quanta_remaining = dict(current_quanta)

            # Reset interval monitors
            interval_arrivals = []
            interval_delivered = []
            interval_dropped = {cls: 0 for cls in config.TRAFFIC_CLASSES}
            next_control_time += control_interval_s

        # Enqueue packets that have arrived by current_time
        while pkt_index < n_pkts and all_pkts[pkt_index]["arrive_s"] <= current_time:
            p = all_pkts[pkt_index]
            cls = p["class"]
            interval_arrivals.append(p)
            if len(queues[cls]) < queue_limits[cls]:
                queues[cls].append(p)
            else:
                result.dropped[cls] += 1
                interval_dropped[cls] += 1
            pkt_index += 1

        # Select next packet based on active scheduling mode
        chosen_cls: Optional[str] = None

        if active_params["mode"] == "strict_priority":
            # Strict Priority Mode (used in SEVERE_CONGESTION)
            for cls in priority_order:
                if queues[cls]:
                    chosen_cls = cls
                    break
        else:
            # Weighted Mode (used in NORMAL, PROTECT_REALTIME, RECOVERY)
            # Find class that has packets and remaining quantum
            for cls in priority_order:
                if queues[cls] and quanta_remaining.get(cls, 0) > 0:
                    chosen_cls = cls
                    break

            # If all queues with packets have exhausted quanta, reset quanta round
            if chosen_cls is None:
                quanta_remaining = dict(current_quanta)
                for cls in priority_order:
                    if queues[cls]:
                        chosen_cls = cls
                        break

        # If all queues are empty, advance time to next arrival
        if chosen_cls is None:
            if pkt_index < n_pkts:
                current_time = all_pkts[pkt_index]["arrive_s"]
            else:
                break
            continue

        # Transmit selected packet
        pkt = queues[chosen_cls].popleft()
        if active_params["mode"] != "strict_priority":
            quanta_remaining[chosen_cls] = max(0, quanta_remaining.get(chosen_cls, 0) - pkt["size_bytes"])

        tx_time = (pkt["size_bytes"] * 8) / link_capacity_bps
        start_tx = max(link_free_at, current_time)
        finish = start_tx + tx_time

        if finish > duration_s:
            result.dropped[pkt["class"]] += 1
            interval_dropped[pkt["class"]] += 1
            current_time = duration_s
            continue

        link_free_at = finish
        current_time = finish
        result.busy_time_s += tx_time

        deliv_pkt = DeliveredPacket(
            cls=pkt["class"],
            size_bytes=pkt["size_bytes"],
            arrive_s=pkt["arrive_s"],
            start_tx_s=start_tx,
            finish_s=finish,
            priority=pkt["priority"],
        )
        result.delivered.append(deliv_pkt)
        interval_delivered.append(deliv_pkt)

    # Simulation termination: drop in-flight packets in queues
    for cls, q in queues.items():
        result.dropped[cls] += len(q)

    # Any arrivals after simulation end
    while pkt_index < n_pkts:
        result.dropped[all_pkts[pkt_index]["class"]] += 1
        pkt_index += 1

    result.action_history = controller.action_history
    result.controller_summary = controller.get_summary_stats()
    return result
