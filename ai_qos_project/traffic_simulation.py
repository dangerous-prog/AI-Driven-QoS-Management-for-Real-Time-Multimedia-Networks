"""
traffic_simulation.py
=====================
High-level simulation runner.

Wraps the traffic generator and schedulers into a single function call.
Returns SimulationResult objects for downstream metrics and dataset generation.

This module is the main entry point used by:
  - dataset_generation.py
  - evaluation.py
  - main.py
  - dashboard.py
  - tests/
"""

from __future__ import annotations
import config
from traffic_generator import generate_arrivals
from schedulers import run_fifo, run_priority, SimulationResult


def run_simulation(
    scheduler: str = "fifo",
    load_scenario: str = "medium",
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    link_capacity_mbps: float = config.LINK_CAPACITY_MBPS,
) -> SimulationResult:
    """
    Run a single simulation experiment.

    Parameters
    ----------
    scheduler        : "fifo" or "priority"
    load_scenario    : "low" | "medium" | "high"  (from config.LOAD_SCENARIOS)
    duration_s       : override simulation duration (seconds); uses config default if None
    seed             : random seed for reproducibility
    link_capacity_mbps: override link capacity in Mbps

    Returns
    -------
    SimulationResult — use metrics.py to extract performance indicators
    """
    if scheduler not in ("fifo", "priority"):
        raise ValueError(f"Unknown scheduler '{scheduler}'. Choose 'fifo' or 'priority'.")
    if load_scenario not in config.LOAD_SCENARIOS:
        raise ValueError(
            f"Unknown load scenario '{load_scenario}'. "
            f"Choose one of: {list(config.LOAD_SCENARIOS.keys())}"
        )

    dur = duration_s if duration_s is not None else config.SIM_DURATION_S
    if dur <= 0:
        raise ValueError(f"duration_s must be positive, got {dur}")

    multiplier = config.LOAD_SCENARIOS[load_scenario]["multiplier"]
    link_bps   = link_capacity_mbps * 1_000_000

    arrivals = generate_arrivals(
        duration_s=dur,
        load_multiplier=multiplier,
        seed=seed,
    )

    if scheduler == "fifo":
        return run_fifo(arrivals, duration_s=dur, link_capacity_bps=link_bps)
    else:
        return run_priority(arrivals, duration_s=dur, link_capacity_bps=link_bps)


def run_all_scenarios(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    link_capacity_mbps: float = config.LINK_CAPACITY_MBPS,
) -> dict[str, dict[str, SimulationResult]]:
    """
    Run both schedulers under all three load scenarios.

    Returns
    -------
    dict: { load_scenario -> { scheduler_name -> SimulationResult } }

    Example
    -------
    results = run_all_scenarios()
    r = results["medium"]["fifo"]   # SimulationResult for FIFO at medium load
    """
    results: dict[str, dict[str, SimulationResult]] = {}
    for scenario in config.LOAD_SCENARIOS:
        results[scenario] = {}
        for sched in ("fifo", "priority"):
            results[scenario][sched] = run_simulation(
                scheduler=sched,
                load_scenario=scenario,
                duration_s=duration_s,
                seed=seed,
                link_capacity_mbps=link_capacity_mbps,
            )
    return results
