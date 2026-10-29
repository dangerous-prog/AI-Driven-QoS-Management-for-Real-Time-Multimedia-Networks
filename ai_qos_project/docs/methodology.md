# Methodology (Option A & Option B)

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

### Non-Stationary (Changing-Load) Profile (Option B)
To evaluate dynamic controller responsiveness, the simulator implements multi-phase load traces:
- **Phase 1 (0 to 10s)**: Low Load (1.5× base multiplier)
- **Phase 2 (10 to 20s)**: Sudden Congestion Surge (4.2× base multiplier)
- **Phase 3 (20 to 30s)**: Post-Congestion Recovery (1.5× base multiplier)

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

## 3. QoS Policies & Schedulers

### FIFO Baseline (Policy 1)
- Single shared queue (max 300 packets)
- Arrival order strictly preserved
- No class differentiation

### Strict Priority QoS (Policy 2)
- Three separate queues (per-class limits: 50 / 100 / 200 packets)
- Scheduler always drains the highest-priority non-empty queue
- Expected behaviour: background traffic is starved under sustained high load

### AI-Driven Closed-Loop Dynamic QoS (Option B / Policy 3)
An adaptive multi-queue scheduler whose service policy is updated at discrete control intervals (1.0s) by the AI controller:

| QoS Action | Mode | Voice Weight | Video Weight | Background Weight | Description |
|---|---|---|---|---|---|
| **NORMAL** | Weighted | 40% | 35% | 25% | Fair sharing; prevents background starvation when link is healthy |
| **PROTECT_REALTIME** | Weighted | 60% | 30% | 10% | Elevates voice and video guarantees; throttles background share |
| **SEVERE_CONGESTION** | Strict Priority | 70% | 25% | 5% | Strict priority for voice/video; background gets lowest priority |
| **RECOVERY** | Weighted | 50% | 30% | 20% | Intermediate stabilization state to prevent premature de-escalation |

---

## 4. Closed-Loop Control Architecture (Option B)

```
+-------------------------------------------------------------------------+
|                         Discrete-Event Simulator                        |
|                                                                         |
|  [Packet Arrivals] ---> [Class Queues] ---> [Link Scheduler] ---> [Tx] |
|                                                    ^                    |
+----------------------------------------------------|--------------------+
           |                                         |
           | Telemetry over interval [t-1, t]        | Apply Action Params
           v                                         | (Quanta & Mode)
+----------------------------------------------------+--------------------+
|                    Closed-Loop Dynamic QoS Controller                   |
|                                                                         |
| 1. Feature Extraction (pps, delay, loss, jitter, throughput, fill proxy)|
| 2. Machine Learning Inference: Random Forest -> [Normal/Mod/Severe]     |
| 3. Hysteresis Check: Cooldown timer (min_action_duration_s = 2.0s)      |
| 4. State Transition: NORMAL -> PROTECT_RT -> SEVERE_CONG -> RECOVERY    |
+-------------------------------------------------------------------------+
```

### Hysteresis Formulation
To prevent rapid policy oscillation between consecutive 1-second intervals caused by stochastic Poisson noise:
$$\Delta t_{\text{action}} = t_{\text{current}} - t_{\text{last\_change}}$$
- **Severe Escalation**: Bypasses cooldown immediately ($\Delta t \ge 0$) to guarantee emergency protection of voice calls.
- **De-escalation / Recovery**: Only permitted when $\Delta t_{\text{action}} \ge T_{\text{cooldown}}$ ($2.0\text{ seconds}$).

---

## 5. Dataset Features

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

## 6. Congestion-Label Definitions

Labels are derived from link utilisation during the **same measurement window**.
No future information is used.

| Label    | Utilisation Range |
|----------|-------------------|
| normal   | < 70 %            |
| moderate | 70 % – 90 %       |
| severe   | >= 90 %           |

Utilisation = `busy_transmission_time / window_duration × 100`

---

## 7. Machine-Learning Methodology

- Model: `RandomForestClassifier(n_estimators=100, max_depth=10)`
- Split: first 70% of shuffled dataset → train; remaining 30% → test
- Baseline: `DummyClassifier(strategy="most_frequent")`
- Test Accuracy: 100.0% (vs 30.6% Dummy baseline)

---

## 8. Software-Defined Networking (SDN) Translation (Option B)

The `sdn_adapter.py` module maps dynamic QoS actions directly into OpenFlow 1.3 switch configurations:
- **Voice Meter (Meter ID 1)**: Rate bounded according to active action weight (4.0 to 7.0 Mbps).
- **Video Meter (Meter ID 2)**: Rate bounded according to active action weight (2.5 to 3.5 Mbps).
- **Background Meter (Meter ID 3)**: Rate bounded according to active action weight (0.5 to 2.5 Mbps).
- In live SDN environments, pushes via REST API to Ryu (`http://127.0.0.1:8080/stats/meterentry/add`).
- When no live controller is running, operates in Simulated SDN Mode and logs full OpenFlow flow-mod commands.
