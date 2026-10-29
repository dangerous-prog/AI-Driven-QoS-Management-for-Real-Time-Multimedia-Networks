"""
config.py
=========
Central configuration for the AI-Driven QoS Management simulation.
All physical constants, default parameters, and paths are defined here.
To extend for Phase 2 add new sections at the bottom without modifying
existing keys so all dependent modules stay compatible.
"""

import os

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR  = os.path.join(PROJECT_ROOT, "results")
FIGURES_DIR  = os.path.join(RESULTS_DIR,  "figures")
MODELS_DIR   = os.path.join(PROJECT_ROOT, "models")
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Bottleneck link
# ---------------------------------------------------------------------------
LINK_CAPACITY_MBPS = 10.0          # Mbps — total link bandwidth
LINK_CAPACITY_BPS  = LINK_CAPACITY_MBPS * 1_000_000  # bits per second

# ---------------------------------------------------------------------------
# Simulation defaults
# ---------------------------------------------------------------------------
SIM_DURATION_S  = 30.0    # seconds of simulated time
TIME_STEP_S     = 0.001   # 1 ms time steps

# ---------------------------------------------------------------------------
# Traffic classes
# ---------------------------------------------------------------------------
# Each class is described by:
#   packet_size_bytes  : fixed packet size in bytes
#   base_arrival_rate  : packets/second at "medium" load
#   priority           : 0 = highest (voice), 2 = lowest (background)
#   queue_max_packets  : per-class queue limit (priority scheduler only)

TRAFFIC_CLASSES = {
    "voice": {
        "packet_size_bytes": 160,     # G.711 ~64 kbps => 160 B @ 50 pps
        "base_arrival_rate": 50,      # packets / second
        "priority": 0,
        "queue_max_packets": 50,
    },
    "video": {
        "packet_size_bytes": 1200,    # typical RTP video chunk
        "base_arrival_rate": 100,     # packets / second
        "priority": 1,
        "queue_max_packets": 100,
    },
    "background": {
        "packet_size_bytes": 1500,    # TCP MSS for file transfer
        "base_arrival_rate": 150,     # packets / second
        "priority": 2,
        "queue_max_packets": 200,
    },
}

# ---------------------------------------------------------------------------
# Load multipliers (applied to base_arrival_rate of every class)
# These multipliers are chosen so that the total offered load at "medium"
# is roughly equal to link capacity, creating genuine queuing behaviour.
#
# Offered load calculation at medium (multiplier=1.0):
#   voice:      50 pps × 160 B × 8 = 640 000 bps = 0.64 Mbps
#   video:     100 pps × 1200 B × 8 = 960 000 bps = 0.96 Mbps   -- wait, re-read
# Actually let's compute carefully:
#   voice:      50 × 160 × 8 =  64 000 bps  = 0.064 Mbps
#   video:     100 × 1200× 8 = 960 000 bps  = 0.960 Mbps
#   background:150 × 1500× 8 = 1 800 000 bps= 1.800 Mbps
#   Total medium offered = ~2.824 Mbps  (< 10 Mbps link)
#
# So we scale up the base rates to achieve ~50% / ~100% / ~120% utilisation:
#   low    multiplier ≈ 1.5  =>  ~4.2 Mbps  => ~42% util
#   medium multiplier ≈ 3.0  =>  ~8.5 Mbps  => ~85% util
#   high   multiplier ≈ 4.0  => ~11.3 Mbps  => ~113% util  (overloaded)
# ---------------------------------------------------------------------------
LOAD_SCENARIOS = {
    "low":    {"multiplier": 1.5,  "label": "Low Load (~42% utilisation)"},
    "medium": {"multiplier": 3.0,  "label": "Medium Load (~85% utilisation)"},
    "high":   {"multiplier": 4.0,  "label": "High Load (~113% utilisation)"},
}

# ---------------------------------------------------------------------------
# FIFO global queue limit (baseline scheduler)
# ---------------------------------------------------------------------------
FIFO_QUEUE_MAX_PACKETS = 300

# ---------------------------------------------------------------------------
# Dataset / ML
# ---------------------------------------------------------------------------
DATASET_WINDOW_S      = 1.0   # measurement window in seconds
CONGESTION_THRESHOLDS = {
    # Based on utilisation of the bottleneck link during the window.
    # These thresholds are documented in docs/methodology.md.
    "normal":   (0.0,  0.70),   # utilisation < 70 %
    "moderate": (0.70, 0.90),   # 70 % <= utilisation < 90 %
    "severe":   (0.90, 1.01),   # utilisation >= 90 %
}
CONGESTION_LABELS = ["normal", "moderate", "severe"]

# Train / test split fraction (chronological — no shuffle)
TRAIN_FRACTION = 0.70

# ---------------------------------------------------------------------------
# Phase 2 extension hooks (placeholders — do not implement in Phase 1)
# ---------------------------------------------------------------------------
# DYNAMIC_QOS_ENABLED   = False   # set True in Phase 2
# CONTROL_LOOP_INTERVAL = 1.0     # seconds between AI-driven adjustments
# SDN_CONTROLLER_URL    = None    # Ryu REST API endpoint
