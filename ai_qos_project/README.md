# AI-Driven QoS Management for Real-Time Multimedia Networks
## Option A (Phase 1 Baseline) & Option B (Closed-Loop Dynamic Control)

---

## 1. Overview & Comparison: Option A vs Option B

This project implements an end-to-end Computer Networks case study exploring how Machine Learning can optimize Quality of Service (QoS) for real-time multimedia traffic (Voice, Video) alongside best-effort Background downloads.

### Comparison Table: Option A vs Option B

| Architectural Feature | Option A (Phase 1 Prototype) | Option B (Upgraded System) |
|---|---|---|
| **Role of AI** | **Open-Loop Advisory**: Random Forest model predicted congestion for human operator display. | **Closed-Loop Control**: AI predictions actively drive the dynamic queue scheduler in real time. |
| **Scheduler Types** | Static FIFO Baseline and Fixed Strict Priority QoS. | FIFO, Fixed Priority, and **AI-Driven Dynamic QoS** (adaptive weights & modes). |
| **Starvation Handling** | Background traffic experienced severe starvation (19-100% loss) even under light load in Priority mode. | Under healthy conditions (`NORMAL`), background traffic receives proportional service without starvation. |
| **Traffic Scenarios** | Static loads only (Low, Medium, High). | Static loads + **Changing Load** (Low -> Surge -> Recovery) + **Sustained Congestion**. |
| **Stability / Anti-Oscillation** | None (instantaneous window predictions). | **Hysteresis Cooldown** (`min_action_duration_s = 2.0s`) to prevent rapid policy oscillation. |
| **SDN Integration** | None (planned placeholder). | **OpenFlow 1.3 Adapter** (`sdn_adapter.py`) translating QoS actions to OpenFlow meters & queues. |
| **Evaluation Metrics** | Networking metrics (delay, jitter, loss %, throughput). | Networking metrics + **Controller Metrics** (action counts, switching frequency, state distribution). |
| **Automated Tests** | 63 tests. | **78 tests** (unit tests, integration tests, closed-loop validation). |

---

## 2. Problem Statement
In unmanaged networks under heavy traffic surges, real-time multimedia services (VoIP calls, video conferencing) compete directly with bulk elastic file downloads. 
- **FIFO Baseline**: Treats all packets identically. Latency-sensitive 160-byte voice packets get queued behind huge 1,500-byte file download chunks, causing **~998 ms latency** and high packet loss.
- **Fixed Strict Priority**: Unconditionally prioritizes voice and video over background traffic. While voice is protected, background traffic suffers severe starvation even during minor traffic dips.
- **Option B Dynamic QoS**: Dynamically balances fairness during normal periods and enforces strict emergency protection during traffic surges, returning gracefully via a recovery state.

---

## 3. Option B Closed-Loop Control Architecture

```
   [Voice Generator]      ---> [ Voice Queue (Priority 0) ]  \
   [Video Generator]      ---> [ Video Queue (Priority 1) ]   --> [ Adaptive Link Scheduler ] --> [ 10 Mbps Link ]
   [Background Generator] ---> [ BG Queue    (Priority 2) ]  /     (NORMAL / PROTECT_RT / SEVERE_CONG / RECOVERY)
                                         |                                  ^
                                         |                                  |
                                 Telemetry Observation                      Apply Action Parameters
                                 (pps, delay, loss, jitter)                 (Quanta & Mode)
                                         |                                  |
                                         v                                  |
                             [ Feature Vector (12 features) ]               |
                                         |                                  |
                                         v                                  |
                             [ Random Forest Classifier ]                   |
                                         |                                  |
                                 Predicted State                            |
                             (normal, moderate, severe)                     |
                                         |                                  |
                                         v                                  |
                             [ Dynamic QoS Controller ] --------------------+
                               - Hysteresis Cooldown (2.0s)
                               - Emergency Escalation
                               - OpenFlow Meter Translation (SDN)
```

### Dynamic Controller Actions

| QoS Action | Mode | Voice Weight | Video Weight | Background Weight | Trigger Condition |
|---|---|---|---|---|---|
| **NORMAL** | Weighted | 40% | 35% | 25% | Link is healthy (<70% util). Low latency for all; no starvation. |
| **PROTECT_REALTIME** | Weighted | 60% | 30% | 10% | Moderate congestion (70-90% util). Voice/video guarantees elevated. |
| **SEVERE_CONGESTION** | Strict Priority | 70% | 25% | 5% | Severe congestion (>90% util). Emergency voice protection engaged. |
| **RECOVERY** | Weighted | 50% | 30% | 20% | Congestion subsided; stabilizes network before returning to NORMAL. |

---

## 4. System File Structure

```
ai_qos_project/
├── config.py                 # Central parameters, link capacity, QoS actions, load profiles
├── traffic_generator.py      # Poisson arrivals + multi-phase dynamic changing-load generator
├── schedulers.py             # Option A FIFO baseline & Fixed Strict Priority schedulers
├── dynamic_scheduler.py      # Option B adaptive work-conserving closed-loop packet scheduler
├── dynamic_controller.py     # Option B AI-driven QoS controller with hysteresis stability
├── sdn_adapter.py            # Option B OpenFlow 1.3 SDN controller adapter (Ryu REST API)
├── metrics.py                # Throughput, loss %, end-to-end delay, and jitter calculators
├── traffic_simulation.py     # High-level runner supporting FIFO, Priority, and Dynamic QoS
├── dataset_generation.py     # Multi-seed batch runner outputting leak-free telemetry datasets
├── train_model.py            # Random Forest and DummyClassifier training, scoring, & export
├── predict_congestion.py     # Live advisory congestion inference module
├── evaluation.py             # 3-way benchmark comparing FIFO vs Priority vs Dynamic QoS
├── dashboard.py              # Interactive Streamlit web dashboard with Option B tabs
├── main.py                   # Master CLI dispatcher supporting Option A & Option B commands
├── requirements.txt          # Python dependencies
├── docs/
│   ├── methodology.md        # Mathematical definitions, equations, control loop, & SDN mapping
│   └── limitations.md        # Explicit documentation of assumptions, simplifications, & scope
├── tests/                    # 78 automated Pytest unit and integration tests
│   ├── conftest.py
│   ├── test_simulation.py    # Traffic generation, schemas, seeds, packet conservation
│   ├── test_metrics.py       # Delay, jitter, loss %, throughput, zero-division edge cases
│   ├── test_scheduler.py     # FIFO ordering, priority queueing, priority advantages
│   ├── test_dataset.py       # Dataset generation, feature schemas, no label leakage
│   ├── test_model.py         # RF training, Dummy comparison, inference validation
│   ├── test_controller.py    # Controller decision logic, emergency escalation, hysteresis
│   ├── test_dynamic_scheduler.py # Dynamic scheduler quanta, packet conservation, changing load
│   └── test_integration_option_b.py # Full closed-loop integration: Telemetry -> AI -> Action -> Outcome
├── models/
│   ├── rf_model.joblib       # Trained Random Forest classifier
│   └── model_metadata.json   # Model hyperparameters, feature schema, class labels
└── results/
    ├── dataset.csv           # 240 simulation telemetry windows
    ├── evaluation_summary.csv # Option A 2-way summary
    ├── evaluation_summary_option_b.csv # Option B 3-way comparative summary
    ├── ml_metrics.csv        # Classification performance metrics
    ├── ml_report.txt         # Scikit-learn classification report text
    └── figures/              # Matplotlib publication figures (.png)
        ├── delay_by_class_3way.png          # [Option B] 3-way delay comparison
        ├── delay_by_class_high_3way.png     # [Option B] High-load delay comparison
        ├── loss_by_class_3way.png           # [Option B] 3-way packet loss comparison
        ├── throughput_by_class_3way.png     # [Option B] 3-way throughput comparison
        ├── jitter_by_class_3way.png         # [Option B] 3-way jitter comparison
        ├── changing_load_comparison.png     # [Option B] Delay & loss under surge profile
        ├── controller_timeline.png          # [Option B] AI predictions & actions over time
        ├── delay_by_class.png               # [Option A] Delay by class
        ├── jitter_by_class.png              # [Option A] Jitter by class
        ├── loss_by_class.png                # [Option A] Loss % by class
        ├── throughput_by_class.png          # [Option A] Throughput by class
        ├── delay_vs_load_voice.png          # [Option A] Voice latency scaling
        ├── loss_vs_load_video.png           # [Option A] Video loss scaling
        ├── throughput_vs_load_bg.png        # [Option A] Background throughput scaling
        ├── link_utilisation.png             # [Option A] Link utilization
        ├── confusion_matrix.png             # [Option A] RF confusion matrix
        └── ml_metrics_comparison.png        # [Option A] RF vs Dummy metrics bar chart
```

---

## 5. Installation Instructions

### Setup Environment
```powershell
# Navigate to the project directory
cd "c:\Users\EIILADMIN\CN PRO\ai_qos_project"

# Ensure pip is up to date and install requirements
pip install -r requirements.txt
```

---

## 6. Exact Commands to Run the Project

### Option B: Closed-Loop AI-Driven QoS Commands
```powershell
# 1. Run closed-loop Dynamic QoS simulation at medium load
python main.py dynamic --load medium

# 2. Run closed-loop Dynamic QoS simulation at high load
python main.py dynamic --load high

# 3. Run the Changing-Load Benchmark comparing FIFO, Priority, and Dynamic QoS
python main.py changing_load

# 4. Run the full Option B 3-Way Comparative Evaluation (generates all 3-way figures & CSV)
python main.py evaluate_b

# 5. Run the complete pipeline end-to-end (dataset + train + evaluate Option A + evaluate Option B + changing load)
python main.py all
```

### Option A: Baseline Workflows (Fully Preserved)
```powershell
# Run FIFO baseline simulation
python main.py simulate --scheduler fifo --load medium

# Run Fixed Strict Priority QoS simulation
python main.py simulate --scheduler priority --load high

# Generate training dataset
python main.py dataset --seeds 40

# Train the Random Forest classifier
python main.py train

# Run Option A 2-way evaluation
python main.py evaluate

# Run advisory congestion prediction inference
python main.py predict --load high --scheduler priority
```

---

## 7. Interactive Streamlit Web Dashboard

Launch the upgraded interactive dashboard:
```powershell
streamlit run dashboard.py
```
Open your browser at `http://localhost:8501`.

The upgraded dashboard features:
- **AI Dynamic QoS Tab**: Live execution of the closed-loop controller, KPI cards, and recent decisions audit trail.
- **Changing-Load Experiment Tab**: Interactive visualization of network performance during a non-stationary traffic surge, plus the controller state transition timeline.
- **3-Way Comparison Tab**: Interactive bar charts and data tables comparing FIFO, Fixed Priority, and AI-Driven QoS with CSV download.
- **SDN Integration Tab**: Live Ryu controller connection status, OpenFlow 1.3 meter translation table, and interactive meter push simulator.
- **Option A Baseline Tabs**: Original FIFO, Priority, AI Model, and Advisory Predictor tabs preserved.

---

## 8. Exact Commands to Run Tests

Run the full automated test suite (78 tests):
```powershell
cd "c:\Users\EIILADMIN\CN PRO\ai_qos_project"
python -m pytest tests/ -v
```

---

## 9. Key Experimental Findings

### 1. High Load Experiment (113% Link Saturation)
- **FIFO Baseline**: All classes suffer equally. Voice delay surges to **~998 ms** with **12.0% loss**, rendering VoIP calls unusable.
- **Fixed Strict Priority**: Voice delay drops to **~0.68 ms** with **0.0% loss**, but background traffic experiences severe starvation (**19.3% loss**, delay ~376 ms).
- **AI-Driven Dynamic QoS**: Voice delay drops to **~0.60 ms** with **0.0% loss**, matching Priority QoS protection while dynamically allocating quanta.

### 2. Changing Load Experiment (Low -> Surge -> Recovery)
- Under low load (0-10s), the controller maintains **`NORMAL`** (weighted sharing), allowing background downloads to achieve high throughput and low delay.
- When the 4.2× surge arrives at $t=10\text{s}$, the AI detects congestion and immediately escalates to **`SEVERE_CONGESTION`**, slashing voice delay from 633 ms (FIFO) down to **0.54 ms**.
- When the surge subsides at $t=20\text{s}$, the controller holds for a 2-second hysteresis cooldown in **`RECOVERY`** before returning cleanly to **`NORMAL`**, preventing policy flapping (switching frequency: 6.2 switches/minute).

### 3. Packet Conservation Verification
Across all experiments and tests:
$$\text{Offered Packets} \equiv \text{Delivered Packets} + \text{Dropped Packets}$$
strictly holds for every traffic class with zero discrepancy.

---

## 10. How to Explain Option B in a Presentation / Viva

1. **Option A Foundation**:
   > *"In Option A, we proved that fixed Strict Priority protects voice latency (<1ms) compared to FIFO (~1000ms), but it unconditionally starves background downloads. We also trained a Random Forest model that predicted congestion with 100% accuracy as an open-loop advisory monitor."*
2. **The Option B Upgrade**:
   > *"In Option B, we closed the loop. We integrated the Random Forest model into a live dynamic controller that samples network telemetry every 1 second and adjusts the packet scheduler's active service quanta in real time."*
3. **The Anti-Oscillation Mechanism**:
   > *"To prevent stochastic packet bursts from causing rapid policy flapping, we engineered a hysteresis stability mechanism with a 2-second cooldown on de-escalation, while allowing instant emergency escalation on severe congestion."*
4. **The Results**:
   > *"Under non-stationary surge traffic, AI Dynamic QoS automatically provided the best of both worlds: fair service for background traffic during quiet periods, and instant sub-millisecond protection for voice calls during traffic spikes."*
