# AI-Driven QoS Management for Real-Time Multimedia Networks (Phase 1 Prototype)

---

## 1. Problem Statement
In modern packet-switched IP networks, real-time multimedia services (VoIP calls, video conferencing) compete for limited link bandwidth alongside best-effort elastic traffic (bulk file transfers, downloads). 

When network congestion occurs:
- Traditional **First-In-First-Out (FIFO)** scheduling treats all packets equally, resulting in high queuing delay, excessive jitter, and packet loss for delay-sensitive voice and video streams.
- **Conventional Strict Priority (SP)** scheduling protects real-time traffic but risks severe starvation of background traffic under heavy loads.
- Static QoS configurations cannot anticipate rapid load surges or adapt proactively before queue saturation degrades application Quality of Experience (QoE).

---

## 2. Objectives
1. **Model Differentiated Traffic**: Simulate voice, video, and background traffic with distinct packet sizes, generation frequencies, and delay sensitivities.
2. **Evaluate Queuing Policies**: Compare a fair FIFO baseline against Strict Priority QoS across varying traffic loads (Low, Medium, High).
3. **Automate Dataset Generation**: Formulate a time-windowed network telemetry dataset without data leakage.
4. **Train AI Congestion Predictor**: Train a Random Forest classifier to predict congestion states (`normal`, `moderate`, `severe`) based on non-leaking network features.
5. **Interactive Demonstration**: Provide both CLI and interactive Streamlit web dashboard interfaces for live simulation and prediction inspection.
6. **Architect for Phase 2**: Maintain a modular, decoupled codebase ready for closed-loop dynamic QoS and SDN control.

---

## 3. Proposed Solution
The project implements a discrete-event network queueing simulator in Python with explicit physical link constraints (10 Mbps bottleneck link, customizable queue limits, Poisson arrivals).

```
   [Voice Generator]      ---> [ Voice Queue (Priority 0) ]  \
   [Video Generator]      ---> [ Video Queue (Priority 1) ]   --> [ Link Scheduler ] --> [ 10 Mbps Link ]
   [Background Generator] ---> [ BG Queue    (Priority 2) ]  /     (FIFO / Priority)
                                         |
                                         v
                                [ Telemetry Collector ]
                                         |
                                         v
                                [ Random Forest Classifier ] ---> [ Congestion State: Normal/Mod/Severe ]
                                                                  (Advisory in Phase 1)
```

The system operates in two core evaluation modes:
- **Baseline (FIFO)**: All incoming packets share a single 300-packet buffer and are served in arrival order.
- **Conventional QoS (Priority)**: High-priority voice packets jump to the head of the service queue, followed by video, with background traffic served only when higher-priority queues are idle.
- **AI Advisory Prediction**: A trained Random Forest model monitors recent network telemetry metrics and predicts congestion levels to advise network administrators.

---

## 4. System Architecture

```
ai_qos_project/
|-- config.py                 # Central configuration (link speed, packet sizes, thresholds)
|-- traffic_generator.py      # Poisson arrival generator per traffic class
|-- schedulers.py             # FIFO and Strict Priority queue scheduling engines
|-- metrics.py                # Throughput, loss %, end-to-end delay, and jitter calculators
|-- traffic_simulation.py     # High-level simulation runner across scenarios
|-- dataset_generation.py     # Multi-seed simulation runner exporting results/dataset.csv
|-- train_model.py            # Random Forest and DummyClassifier training and evaluation
|-- predict_congestion.py     # Live advisory congestion inference module
|-- evaluation.py             # Batch benchmark comparing FIFO vs Priority across loads
|-- dashboard.py              # Streamlit interactive dashboard
|-- main.py                   # Master CLI dispatcher
|-- requirements.txt          # Python dependencies
|-- data/                     # Raw and cached data files
|-- models/                   # Saved joblib models and metadata JSON
|-- results/                  # Generated CSVs and evaluation figures
|   `-- figures/              # Matplotlib comparison charts and confusion matrices
|-- docs/
|   |-- methodology.md        # Mathematical definitions, equations, and experimental setups
|   `-- limitations.md        # Assumptions and Phase 1 vs real-network differences
`-- tests/                    # Pytest test suite (63 unit and integration tests)
    |-- test_simulation.py
    |-- test_metrics.py
    |-- test_scheduler.py
    |-- test_dataset.py
    `-- test_model.py
```

---

## 5. Technology Stack
- **Language**: Python 3.11+
- **Data & Computation**: NumPy, Pandas
- **Machine Learning**: Scikit-Learn (Random Forest, DummyClassifier), Joblib
- **Visualization**: Matplotlib
- **Web Interface**: Streamlit
- **Testing**: Pytest

---

## 6. Installation Instructions

### Windows (PowerShell or Command Prompt)
```powershell
# Navigate to the workspace directory
cd "c:\Users\EIILADMIN\CN PRO\ai_qos_project"

# Ensure pip is up to date
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### Linux / macOS (Bash / Zsh)
```bash
cd ai_qos_project
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
```

---

## 7. Virtual Environment Setup (Recommended)

### Windows
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux / macOS
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 8. Exact Commands to Run the Simulation

Run a single simulation experiment directly via `main.py`:
```powershell
# Run FIFO simulation at medium load
python main.py simulate --scheduler fifo --load medium

# Run Strict Priority QoS simulation at high load
python main.py simulate --scheduler priority --load high

# Specify custom duration (e.g., 20 seconds)
python main.py simulate --scheduler priority --load high --duration 20.0
```

---

## 9. Exact Commands to Train the Model

Generate a fresh training dataset and train the Random Forest classifier:
```powershell
# Step A: Generate dataset from 40 independent seeds per load/scheduler
python main.py dataset --seeds 40

# Step B: Train Random Forest model and compare against Dummy baseline
python main.py train
```
This produces:
- `results/dataset.csv` (240 samples across low, medium, and high loads)
- `models/rf_model.joblib` (Trained model)
- `models/model_metadata.json` (Feature schema and training parameters)
- `results/ml_report.txt` (Classification performance report)
- `results/ml_metrics.csv` (Per-class precision, recall, and F1 scores)
- `results/figures/confusion_matrix.png` (Confusion matrix plot)

---

## 10. Exact Commands to Generate Evaluation Results

Run the full comparative benchmark across all load scenarios and generate all publication-ready graphs:
```powershell
python main.py evaluate
```
To run the complete end-to-end pipeline in one command:
```powershell
python main.py all
```

---

## 11. Exact Commands to Launch the Dashboard

Launch the interactive Streamlit GUI:
```powershell
streamlit run dashboard.py
```
Open your browser at `http://localhost:8501`.

The dashboard allows you to:
- Adjust link capacity (Mbps) and simulation duration in real time.
- Switch between Low, Medium, and High traffic scenarios.
- Inspect KPI cards for Delay, Jitter, Packet Loss %, and Throughput.
- Interactively plot comparative bar charts (FIFO vs Priority).
- Train/retrain the Random Forest model and inspect the confusion matrix.
- Test real-time advisory congestion predictions with probability bars.
- Export comparison tables directly as CSV.

---

## 12. Expected Files and Outputs

| File | Purpose |
|------|---------|
| `results/dataset.csv` | 240 simulation measurement windows with 12 features & congestion label |
| `results/evaluation_summary.csv` | Full metric results comparing FIFO vs Priority across all loads |
| `results/ml_metrics.csv` | Random Forest vs DummyClassifier precision/recall/F1 metrics |
| `results/ml_report.txt` | Detailed text summary of test set classification report |
| `models/rf_model.joblib` | Serialized scikit-learn Random Forest model |
| `models/model_metadata.json` | Feature names, class order, hyperparameters, and accuracies |
| `results/figures/delay_by_class.png` | End-to-end delay per traffic class |
| `results/figures/jitter_by_class.png` | Packet jitter per traffic class |
| `results/figures/loss_by_class.png` | Packet loss percentage per traffic class |
| `results/figures/throughput_by_class.png` | Delivered throughput per traffic class |
| `results/figures/delay_vs_load_voice.png` | Voice latency scaling across Low, Medium, High load |
| `results/figures/loss_vs_load_video.png` | Video packet loss scaling across loads |
| `results/figures/throughput_vs_load_bg.png` | Background throughput scaling across loads |
| `results/figures/link_utilisation.png` | Bottleneck link utilization bar chart |
| `results/figures/confusion_matrix.png` | Random Forest multi-class confusion matrix |
| `results/figures/ml_metrics_comparison.png` | Bar chart comparing RF precision/recall/F1 with Dummy baseline |

---

## 13. Troubleshooting Common Errors

1. **`UnicodeEncodeError: 'charmap' codec can't encode character ...`**:
   - Cause: Windows Command Prompt / PowerShell defaults to `cp1252` encoding which cannot render certain Unicode symbols or arrows.
   - Solution: All scripts in this project use ASCII text fallback (`[OK]`, `[WARN]`, `->`). You can also run `chcp 65001` in PowerShell to enable UTF-8 mode.

2. **`Matplotlib created a temporary cache directory at ... [WinError 5] Access is denied`**:
   - Cause: Matplotlib attempts to write font cache to a restricted Windows system directory.
   - Solution: This warning is harmless and automatically handled by Matplotlib falling back to temporary directories. To silence it, set an environment variable: `$env:MPLCONFIGDIR = "$env:TEMP\matplotlib"`.

3. **`ModuleNotFoundError: No module named 'config'`**:
   - Cause: Running scripts outside the `ai_qos_project` directory without setting `PYTHONPATH`.
   - Solution: Always run scripts from inside `ai_qos_project/`, or install in editable mode.

---

## 14. How to Explain the Project During a Viva or Presentation

When presenting this project to your professor or examiner, structure your explanation in 4 clear steps:

### 1. The Core Problem
> *"In unmanaged networks under heavy load, voice calls break up and video freezes because standard FIFO routers treat latency-sensitive 160-byte voice packets with the same priority as 1,500-byte background downloads."*

### 2. What We Implemented
> *"We built a discrete-event simulation of a 10 Mbps bottleneck link with Poisson arrivals. We implemented two scheduling mechanisms: a baseline FIFO queue and a multi-queue Strict Priority scheduler dividing traffic into Voice (Priority 0), Video (Priority 1), and Background (Priority 2)."*

### 3. The Experimental Findings
> *"Under high network load (113% link capacity):*
> - *Under FIFO, voice suffers **~998 ms delay** and **~12% packet loss**, rendering VoIP unusable.*
> - *Under Priority QoS, voice delay drops to **< 1 ms** with **0.0% packet loss**.*
> - *The trade-off is background traffic starvation, where background loss rises to **~19%**.*
> - *We rigorously proved packet conservation: for all classes, Offered Packets = Delivered Packets + Dropped Packets."*

### 4. The Machine Learning Component
> *"We collected 240 non-leaking simulation windows and trained a Random Forest classifier to predict congestion (Normal, Moderate, Severe). The model achieved **100% test accuracy**, significantly outperforming the Dummy baseline (30.6%). In this Phase 1 prototype, the AI serves as an advisory monitor to alert operators before queue overflows occur."*

---

## 15. Future Upgrade Path: Option A to Option B (Phase 2)

Phase 1 provides the core discrete-event simulator and advisory AI model. Upgrading to Phase 2 (Option B) involves:

1. **Closed-Loop AI Control (`control_loop.py`)**:
   - Transition AI output from passive advisor to an active controller modifying scheduler queue weights (e.g., dynamically adjusting Deficit Round Robin quantum).
2. **Starvation Prevention**:
   - Replace strict priority with **Weighted Fair Queueing (WFQ)** or **Deficit Round Robin (DRR)** so that background traffic is throttled rather than completely starved.
3. **SDN Controller Integration**:
   - Connect the AI controller via REST API to an SDN controller (e.g., Ryu or ONOS) running over a Mininet virtual topology of OpenFlow switches.
4. **Sequence & Reinforcement Learning**:
   - Replace or augment the Random Forest model with LSTM networks for time-series congestion forecasting, or Deep Q-Learning (DQN) for real-time dynamic queue weight adjustment.
