"""
metrics.py
==========
Computes per-class and overall performance metrics from a SimulationResult.

All metrics use the mathematical definitions documented in docs/methodology.md
and in the project specification.

Metrics computed per traffic class
-----------------------------------
throughput_mbps     : delivered payload bits / duration / 1e6
packet_loss_pct     : dropped / offered × 100   (0 if offered == 0)
avg_delay_ms        : mean end-to-end delay of delivered packets (ms)
avg_jitter_ms       : mean |delay[i] - delay[i-1]| of consecutive delivered pkts
packets_offered     : total offered
packets_delivered   : total delivered
packets_dropped     : total dropped
link_utilisation_pct: busy_time / duration × 100  (same for all classes — link-level)

Time unit: milliseconds for delay/jitter, Mbps for throughput.
"""

from __future__ import annotations
import numpy as np
from schedulers import SimulationResult, DeliveredPacket


# ---------------------------------------------------------------------------
# Per-class delivery extraction
# ---------------------------------------------------------------------------
def _delivered_for_class(result: SimulationResult, cls: str) -> list[DeliveredPacket]:
    return [p for p in result.delivered if p.cls == cls]


# ---------------------------------------------------------------------------
# Individual metric functions
# ---------------------------------------------------------------------------
def throughput_mbps(result: SimulationResult, cls: str) -> float:
    """
    Throughput (Mbps) = delivered payload bits / duration_s / 1e6.
    """
    pkts = _delivered_for_class(result, cls)
    total_bits = sum(p.size_bytes * 8 for p in pkts)
    return total_bits / result.duration_s / 1_000_000


def packet_loss_pct(result: SimulationResult, cls: str) -> float:
    """
    Packet-loss (%) = dropped / offered × 100.
    Returns 0.0 if no packets were offered (avoids division by zero).
    """
    offered = result.offered.get(cls, 0)
    if offered == 0:
        return 0.0
    dropped = result.dropped.get(cls, 0)
    return dropped / offered * 100.0


def avg_delay_ms(result: SimulationResult, cls: str) -> float:
    """
    Average end-to-end delay in ms for delivered packets of the class.
    Returns 0.0 if no packets were delivered.
    End-to-end delay = finish_time - arrive_time.
    """
    pkts = _delivered_for_class(result, cls)
    if not pkts:
        return 0.0
    delays = [p.delay_ms for p in pkts]
    return float(np.mean(delays))


def avg_jitter_ms(result: SimulationResult, cls: str) -> float:
    """
    Jitter = mean absolute difference between consecutive packet delays.
    |delay[i] - delay[i-1]|  for i = 1 … N-1, packets ordered by finish time.
    Returns 0.0 if fewer than two packets were delivered.
    """
    pkts = sorted(_delivered_for_class(result, cls), key=lambda p: p.finish_s)
    if len(pkts) < 2:
        return 0.0
    delays = np.array([p.delay_ms for p in pkts])
    diffs  = np.abs(np.diff(delays))
    return float(np.mean(diffs))


def link_utilisation_pct(result: SimulationResult) -> float:
    """
    Link utilisation (%) = busy transmission time / total duration × 100.
    This is a link-level metric, not per-class.
    """
    if result.duration_s <= 0:
        return 0.0
    return result.busy_time_s / result.duration_s * 100.0


def packets_delivered_count(result: SimulationResult, cls: str) -> int:
    return len(_delivered_for_class(result, cls))


def packets_dropped_count(result: SimulationResult, cls: str) -> int:
    return result.dropped.get(cls, 0)


def packets_offered_count(result: SimulationResult, cls: str) -> int:
    return result.offered.get(cls, 0)


# ---------------------------------------------------------------------------
# Full per-class summary dict
# ---------------------------------------------------------------------------
def class_summary(result: SimulationResult, cls: str) -> dict:
    """
    Return a dict with all per-class metrics.
    """
    return {
        "scheduler":         result.scheduler_name,
        "traffic_class":     cls,
        "packets_offered":   packets_offered_count(result, cls),
        "packets_delivered": packets_delivered_count(result, cls),
        "packets_dropped":   packets_dropped_count(result, cls),
        "packet_loss_pct":   round(packet_loss_pct(result, cls), 4),
        "throughput_mbps":   round(throughput_mbps(result, cls), 6),
        "avg_delay_ms":      round(avg_delay_ms(result, cls), 4),
        "avg_jitter_ms":     round(avg_jitter_ms(result, cls), 4),
        "link_util_pct":     round(link_utilisation_pct(result), 4),
        "duration_s":        result.duration_s,
    }


def all_class_summaries(result: SimulationResult) -> list[dict]:
    """Return summaries for all three traffic classes."""
    from config import TRAFFIC_CLASSES
    return [class_summary(result, cls) for cls in TRAFFIC_CLASSES]
