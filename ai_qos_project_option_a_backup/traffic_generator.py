"""
traffic_generator.py
====================
Generates packet-arrival events for each traffic class.

Each packet is represented as a dictionary:
    {
        "class"      : str   — "voice" | "video" | "background"
        "size_bytes" : int   — payload size
        "arrive_s"   : float — simulated arrival time in seconds
        "priority"   : int   — 0 (highest) … 2 (lowest)
    }

Arrivals follow a Poisson process (exponentially distributed inter-arrival
times), which is a standard model for network traffic in introductory courses.
The arrival rate is:
    lambda = base_arrival_rate × load_multiplier   (packets / second)

All randomness is seeded via a numpy RandomState so experiments are
reproducible when the same seed is used.
"""

import numpy as np
from config import TRAFFIC_CLASSES, RANDOM_SEED


def generate_arrivals(
    duration_s: float,
    load_multiplier: float = 1.0,
    seed: int = RANDOM_SEED,
) -> dict[str, list[dict]]:
    """
    Generate Poisson-process packet arrivals for all traffic classes.

    Parameters
    ----------
    duration_s      : simulated time window in seconds
    load_multiplier : scales every class's base arrival rate
    seed            : numpy random seed for reproducibility

    Returns
    -------
    dict mapping traffic-class name -> sorted list of packet dicts
    """
    if duration_s <= 0:
        raise ValueError(f"duration_s must be positive, got {duration_s}")
    if load_multiplier <= 0:
        raise ValueError(f"load_multiplier must be positive, got {load_multiplier}")

    rng = np.random.RandomState(seed)
    arrivals: dict[str, list[dict]] = {}

    for cls_name, cfg in TRAFFIC_CLASSES.items():
        lam = cfg["base_arrival_rate"] * load_multiplier  # packets / s
        # Draw inter-arrival times from Exponential(1/lambda)
        # We over-generate then truncate at duration_s to avoid boundary bias.
        n_estimate = int(lam * duration_s * 3) + 100
        inter_arrivals = rng.exponential(scale=1.0 / lam, size=n_estimate)
        times = np.cumsum(inter_arrivals)
        times = times[times < duration_s]

        packets = [
            {
                "class": cls_name,
                "size_bytes": cfg["packet_size_bytes"],
                "arrive_s": float(t),
                "priority": cfg["priority"],
            }
            for t in times
        ]
        arrivals[cls_name] = packets

    return arrivals


def offered_load_mbps(
    arrivals: dict[str, list[dict]],
    duration_s: float,
) -> float:
    """
    Compute the total offered load in Mbps for the generated arrivals.

    offered_load_Mbps = Σ(packet_size_bytes × 8) / duration_s / 1e6
    """
    total_bits = sum(
        p["size_bytes"] * 8
        for pkts in arrivals.values()
        for p in pkts
    )
    return total_bits / duration_s / 1_000_000


def total_packets(arrivals: dict[str, list[dict]]) -> int:
    """Return total number of offered packets across all classes."""
    return sum(len(v) for v in arrivals.values())
