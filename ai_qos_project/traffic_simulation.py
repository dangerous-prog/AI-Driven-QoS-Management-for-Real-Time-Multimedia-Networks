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
from traffic_generator import generate_arrivals, generate_dynamic_arrivals
from schedulers import run_fifo, run_priority, SimulationResult
from dynamic_scheduler import run_dynamic_qos, DynamicSimulationResult
from dynamic_controller import DynamicQoSController


def run_simulation(
    scheduler: str = "fifo",
    load_scenario: str = "medium",
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    link_capacity_mbps: float = config.LINK_CAPACITY_MBPS,
    controller: DynamicQoSController | None = None,
) -> SimulationResult:
    """
    Run a single simulation experiment.

    Parameters
    ----------
    scheduler        : "fifo", "priority", or "dynamic" (Option B AI-Driven QoS)
    load_scenario    : "low" | "medium" | "high" | "changing" | "sustained"
    duration_s       : override simulation duration (seconds); uses config default if None
    seed             : random seed for reproducibility
    link_capacity_mbps: override link capacity in Mbps
    controller       : optional custom DynamicQoSController instance

    Returns
    -------
    SimulationResult or DynamicSimulationResult
    """
    valid_schedulers = ("fifo", "priority", "dynamic", "ai_driven")
    if scheduler not in valid_schedulers:
        raise ValueError(
            f"Unknown scheduler '{scheduler}'. Choose from: {valid_schedulers}"
        )

    valid_scenarios = list(config.LOAD_SCENARIOS.keys()) + ["changing", "sustained"]
    if load_scenario not in valid_scenarios:
        raise ValueError(
            f"Unknown load scenario '{load_scenario}'. "
            f"Choose one of: {valid_scenarios}"
        )

    dur = duration_s if duration_s is not None else config.SIM_DURATION_S
    if dur <= 0:
        raise ValueError(f"duration_s must be positive, got {dur}")

    link_bps = link_capacity_mbps * 1_000_000

    if load_scenario == "changing":
        arrivals = generate_dynamic_arrivals(
            profile=config.CHANGING_LOAD_PROFILE,
            seed=seed,
        )
    elif load_scenario == "sustained":
        arrivals = generate_dynamic_arrivals(
            profile=config.SUSTAINED_CONGESTION_PROFILE,
            seed=seed,
        )
    else:
        multiplier = config.LOAD_SCENARIOS[load_scenario]["multiplier"]
        arrivals = generate_arrivals(
            duration_s=dur,
            load_multiplier=multiplier,
            seed=seed,
        )

    if scheduler == "fifo":
        return run_fifo(arrivals, duration_s=dur, link_capacity_bps=link_bps)
    elif scheduler == "priority":
        return run_priority(arrivals, duration_s=dur, link_capacity_bps=link_bps)
    else:  # "dynamic" or "ai_driven"
        return run_dynamic_qos(
            arrivals,
            duration_s=dur,
            link_capacity_bps=link_bps,
            controller=controller,
        )


def run_changing_load_simulation(
    duration_s: float = 30.0,
    seed: int = config.RANDOM_SEED,
    link_capacity_mbps: float = config.LINK_CAPACITY_MBPS,
) -> dict[str, SimulationResult]:
    """
    Run FIFO, Priority, and AI-Driven Dynamic QoS under the EXACT SAME changing load trace.

    Returns
    -------
    dict: { "fifo": SimulationResult, "priority": SimulationResult, "dynamic": DynamicSimulationResult }
    """
    arrivals = generate_dynamic_arrivals(
        profile=config.CHANGING_LOAD_PROFILE,
        seed=seed,
    )
    link_bps = link_capacity_mbps * 1_000_000

    # Ensure all 3 policies receive the identical arrival trace
    res_fifo = run_fifo(arrivals, duration_s=duration_s, link_capacity_bps=link_bps)
    res_prio = run_priority(arrivals, duration_s=duration_s, link_capacity_bps=link_bps)
    res_dyn  = run_dynamic_qos(arrivals, duration_s=duration_s, link_capacity_bps=link_bps)

    return {
        "fifo":     res_fifo,
        "priority": res_prio,
        "dynamic":  res_dyn,
    }


def run_all_scenarios(
    duration_s: float | None = None,
    seed: int = config.RANDOM_SEED,
    link_capacity_mbps: float = config.LINK_CAPACITY_MBPS,
) -> dict[str, dict[str, SimulationResult]]:
    """
    Run schedulers under load scenarios. Fully backward compatible with Option A.
    """
    results: dict[str, dict[str, SimulationResult]] = {}
    for scenario in config.LOAD_SCENARIOS:
        results[scenario] = {}
        for sched in ("fifo", "priority", "dynamic"):
            results[scenario][sched] = run_simulation(
                scheduler=sched,
                load_scenario=scenario,
                duration_s=duration_s,
                seed=seed,
                link_capacity_mbps=link_capacity_mbps,
            )
    return results

