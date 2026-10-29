"""
schedulers.py
=============
Implements the two packet scheduling policies used in Phase 1.

Policy 1 — FIFO baseline
    A single first-in-first-out queue shared by all traffic classes.
    No traffic differentiation.  Packets are served in arrival order.
    Queue capacity: FIFO_QUEUE_MAX_PACKETS (from config).

Policy 2 — Strict Priority (conventional QoS)
    Separate queues per traffic class ordered by priority:
        0 = voice (highest)   1 = video   2 = background (lowest)
    The scheduler always drains the highest-priority non-empty queue first.
    Strict priority CAN starve lower-priority classes under sustained high
    load — this is expected behaviour and is reported in the results.
    Per-class queue capacity: TRAFFIC_CLASSES[cls]["queue_max_packets"].

Both schedulers expose the same interface so they can be swapped by the
simulator without changes to the calling code.

Time model
----------
The link is modelled as a single-server transmission line.
Transmission time for packet p:
    tx_time = p["size_bytes"] * 8 / LINK_CAPACITY_BPS   (seconds)

End-to-end delay for packet p:
    delay = finish_time - p["arrive_s"]

Jitter (per class, after simulation):
    mean absolute difference between delays of consecutive delivered packets.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import config


# ---------------------------------------------------------------------------
# Delivered-packet record
# ---------------------------------------------------------------------------
@dataclass
class DeliveredPacket:
    cls: str
    size_bytes: int
    arrive_s: float
    start_tx_s: float
    finish_s: float
    priority: int

    @property
    def delay_s(self) -> float:
        return self.finish_s - self.arrive_s

    @property
    def delay_ms(self) -> float:
        return self.delay_s * 1000.0


# ---------------------------------------------------------------------------
# Simulation result container
# ---------------------------------------------------------------------------
@dataclass
class SimulationResult:
    scheduler_name: str
    duration_s: float
    delivered: list[DeliveredPacket] = field(default_factory=list)
    dropped: dict[str, int]         = field(default_factory=lambda: {"voice": 0, "video": 0, "background": 0})
    offered: dict[str, int]         = field(default_factory=lambda: {"voice": 0, "video": 0, "background": 0})
    # busy_time_s: total seconds the link was transmitting (for utilisation)
    busy_time_s: float              = 0.0


# ---------------------------------------------------------------------------
# Helper — build a merged, time-sorted event list from per-class arrivals
# ---------------------------------------------------------------------------
def _merge_arrivals(arrivals: dict[str, list[dict]]) -> list[dict]:
    all_pkts: list[dict] = []
    for pkts in arrivals.values():
        all_pkts.extend(pkts)
    all_pkts.sort(key=lambda p: p["arrive_s"])
    return all_pkts


# ---------------------------------------------------------------------------
# FIFO Baseline Scheduler
# ---------------------------------------------------------------------------
def run_fifo(
    arrivals: dict[str, list[dict]],
    duration_s: float,
    link_capacity_bps: float = config.LINK_CAPACITY_BPS,
    queue_max: int = config.FIFO_QUEUE_MAX_PACKETS,
) -> SimulationResult:
    """
    Single-server FIFO simulation.

    All packets compete in one queue, served in strict arrival order.
    Packets that arrive when the queue is full are dropped.
    """
    result = SimulationResult(scheduler_name="FIFO", duration_s=duration_s)

    # Record offered counts
    for cls, pkts in arrivals.items():
        result.offered[cls] = len(pkts)

    all_pkts = _merge_arrivals(arrivals)

    queue: deque[dict] = deque()
    link_free_at: float = 0.0   # earliest time the link becomes idle

    for pkt in all_pkts:
        t_arrive = pkt["arrive_s"]

        # Advance link: if link became free before this arrival, update
        link_free_at = max(link_free_at, t_arrive)  # server can't serve in past

        # The packet arrives; if queue is full, drop it
        if len(queue) >= queue_max:
            result.dropped[pkt["class"]] += 1
            continue

        queue.append(pkt)

        # Serve packets whose start time is now (drain queue up to t_arrive)
        # We service ONE packet per arrival event to keep the loop simple;
        # the link_free_at tracks the running finish time correctly.
        # ----------------------------------------------------------------
        # Actually: we process the incoming packet immediately if the link
        # is free, otherwise it waits.  We model this as a classic
        # work-conserving FIFO queue:
        #   start_tx = max(link_free_at_before_this_packet, t_arrive)
        # But since we already set link_free_at = max(link_free_at, t_arrive)
        # we just use link_free_at as start_tx.

        # Serve ALL packets that have now arrived and can be scheduled
        # We only serve the head-of-queue here.
        p = queue.popleft()
        tx_time = (p["size_bytes"] * 8) / link_capacity_bps
        start_tx  = link_free_at
        finish    = start_tx + tx_time

        if finish > duration_s:
            # Packet would finish after simulation end — count as in-flight/dropped
            result.dropped[p["class"]] += 1
            # Do NOT update link_free_at so the next packet can be served
            continue

        link_free_at = finish
        result.busy_time_s += tx_time
        result.delivered.append(
            DeliveredPacket(
                cls=p["class"],
                size_bytes=p["size_bytes"],
                arrive_s=p["arrive_s"],
                start_tx_s=start_tx,
                finish_s=finish,
                priority=p["priority"],
            )
        )

    # Any packets still in queue at simulation end are dropped (in-flight)
    while queue:
        p = queue.popleft()
        result.dropped[p["class"]] += 1

    return result


# ---------------------------------------------------------------------------
# Strict Priority Scheduler  (conventional QoS)
# ---------------------------------------------------------------------------
def run_priority(
    arrivals: dict[str, list[dict]],
    duration_s: float,
    link_capacity_bps: float = config.LINK_CAPACITY_BPS,
) -> SimulationResult:
    """
    Strict-priority, work-conserving, multi-queue scheduler.

    Three separate queues (voice, video, background) with per-class limits.
    The scheduler always serves the head of the highest-priority non-empty queue.
    Lower-priority classes may be starved under sustained high-priority load.
    """
    result = SimulationResult(scheduler_name="Priority", duration_s=duration_s)

    for cls, pkts in arrivals.items():
        result.offered[cls] = len(pkts)

    # Per-class queues indexed by priority (0 = highest)
    queues: dict[str, deque] = {cls: deque() for cls in config.TRAFFIC_CLASSES}
    queue_limits: dict[str, int] = {
        cls: cfg["queue_max_packets"]
        for cls, cfg in config.TRAFFIC_CLASSES.items()
    }
    # priority -> class name mapping (sorted)
    priority_order: list[str] = sorted(
        config.TRAFFIC_CLASSES.keys(),
        key=lambda c: config.TRAFFIC_CLASSES[c]["priority"],
    )

    all_pkts = _merge_arrivals(arrivals)
    link_free_at: float = 0.0
    pkt_index: int = 0
    n_pkts = len(all_pkts)

    # We use an event-driven loop:
    #  - Fast-forward time to the next arrival or to when the link becomes free,
    #    whichever is earlier.
    #  - Enqueue all packets that have arrived by current time.
    #  - Pick the highest-priority packet from non-empty queues.
    #  - Transmit it.

    current_time: float = 0.0

    while pkt_index < n_pkts or any(len(q) > 0 for q in queues.values()):
        # Enqueue all packets that have arrived by current_time
        while pkt_index < n_pkts and all_pkts[pkt_index]["arrive_s"] <= current_time:
            pkt = all_pkts[pkt_index]
            cls = pkt["class"]
            if len(queues[cls]) < queue_limits[cls]:
                queues[cls].append(pkt)
            else:
                result.dropped[cls] += 1
            pkt_index += 1

        # Find highest-priority non-empty queue
        chosen_cls: Optional[str] = None
        for cls in priority_order:
            if queues[cls]:
                chosen_cls = cls
                break

        if chosen_cls is None:
            # No packets in any queue; jump to next arrival
            if pkt_index < n_pkts:
                current_time = all_pkts[pkt_index]["arrive_s"]
            else:
                break
            continue

        pkt = queues[chosen_cls].popleft()
        tx_time  = (pkt["size_bytes"] * 8) / link_capacity_bps
        start_tx = max(link_free_at, current_time)
        finish   = start_tx + tx_time

        if finish > duration_s:
            result.dropped[pkt["class"]] += 1
            # Try to serve remaining queued packets that fit
            # by advancing current_time to duration end
            current_time = duration_s
            continue

        link_free_at = finish
        current_time = finish
        result.busy_time_s += tx_time
        result.delivered.append(
            DeliveredPacket(
                cls=pkt["class"],
                size_bytes=pkt["size_bytes"],
                arrive_s=pkt["arrive_s"],
                start_tx_s=start_tx,
                finish_s=finish,
                priority=pkt["priority"],
            )
        )

    # Drain remaining packets in queues as dropped (simulation ended)
    for cls, q in queues.items():
        result.dropped[cls] += len(q)

    # Also count any packets that never arrived by current_time as dropped
    while pkt_index < n_pkts:
        result.dropped[all_pkts[pkt_index]["class"]] += 1
        pkt_index += 1

    return result
