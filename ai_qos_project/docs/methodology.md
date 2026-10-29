# Methodology

## 1. Traffic-Generation Assumptions

Packet arrivals for each traffic class follow a **Poisson process** modelled with
exponentially distributed inter-arrival times (mean = 1 / λ seconds).

Arrival rate:

    λ = base_arrival_rate × load_multiplier   [packets / second]

Fixed packet sizes are used per traffic class:

| Class      | Packet Size | Base Rate | Priority |
|------------|-------------|-----------|----------|
| Voice      | 160 bytes   | 50 pps    | 0 (highest) |
| Video      | 1 200 bytes | 100 pps   | 1        |
| Background | 1 500 bytes | 150 pps   | 2 (lowest) |

All randomness is seeded (default: 42) for reproducibility.

---

## 2. Network and Queueing Model

The bottleneck link is modelled as a **single-server transmission line** (M/D/1
approximation with fixed packet sizes).

- Link capacity: 10 Mbps (configurable)
- Transmission time per packet: `(size_bytes × 8) / link_capacity_bps` seconds
- End-to-end delay: `finish_time - arrive_time`
- Packets that would finish after simulation end are counted as dropped (in-flight)

Queue model: discrete-event simulation stepping through packet arrivals in order.
No propagation delay is modelled (local network assumption).

---

## 3. QoS Policies

### FIFO Baseline
- Single shared queue (max 300 packets)
- Arrival order strictly preserved
- No class differentiation

### Strict Priority QoS
- Three separate queues (per-class limits: 50 / 100 / 200 packets)
- Scheduler always drains the highest-priority non-empty queue
- Expected behaviour: background traffic may be starved under high load

---

## 4. Dataset Features

All features can be measured from network monitoring without future information:

| Feature | Description |
|---------|-------------|
| `load_multiplier` | Applied arrival rate multiplier |
| `arrival_rate_pps` | Total packets/s observed during window |
| `queue_fill_proxy` | Dropped / offered ratio (proxy for queue depth) |
| `voice_delay_ms` | Avg end-to-end delay for voice (ms) |
| `video_delay_ms` | Avg end-to-end delay for video (ms) |
| `bg_delay_ms` | Avg end-to-end delay for background (ms) |
| `voice_loss_pct` | Voice packet-loss percentage |
| `video_loss_pct` | Video packet-loss percentage |
| `bg_loss_pct` | Background packet-loss percentage |
| `voice_jitter_ms` | Voice jitter (ms) |
| `video_jitter_ms` | Video jitter (ms) |
| `throughput_total_mbps` | Total delivered throughput (Mbps) |

**Excluded from features:** `congestion_label`, `link_util_pct` (used to derive label).

---

## 5. Congestion-Label Definitions

Labels are derived from link utilisation during the **same measurement window**.
No future information is used.

| Label    | Utilisation Range |
|----------|-------------------|
| normal   | < 70 %            |
| moderate | 70 % – 90 %       |
| severe   | >= 90 %           |

Utilisation = `busy_transmission_time / window_duration × 100`

---

## 6. Machine-Learning Methodology

- Model: `RandomForestClassifier(n_estimators=100, max_depth=10)`
- Split: first 70% of shuffled dataset → train; remaining 30% → test
  (shuffled with fixed seed before splitting to ensure all classes appear in both sets)
- Baseline: `DummyClassifier(strategy="most_frequent")`
- Metrics: accuracy, precision, recall, F1, confusion matrix

---

## 7. Experimental Setup

240 measurement windows generated from:
- 3 load scenarios × 2 schedulers × 40 random seeds = 240 rows
- Window duration: 1 second each
- Link capacity: 10 Mbps

Load scenarios (total offered vs 10 Mbps link):
- Low (1.5×): ~42% utilisation
- Medium (3.0×): ~85% utilisation
- High (4.0×): ~113% utilisation (overloaded)

---

## 8. Performance Metrics

| Metric | Formula |
|--------|---------|
| Throughput (Mbps) | delivered_bits / duration / 1e6 |
| Packet loss (%) | dropped / offered × 100 |
| End-to-end delay (ms) | (finish_time − arrive_time) × 1000 |
| Jitter (ms) | mean |delay[i] − delay[i−1]| for consecutive packets |
| Link utilisation (%) | busy_time / duration × 100 |

---

## 9. Fair Comparison Procedure

Both FIFO and Priority schedulers receive **identical offered traffic** (same
arrival times, same packet sizes, same random seed, same link capacity, same
simulation duration). The only difference is the scheduling policy.
