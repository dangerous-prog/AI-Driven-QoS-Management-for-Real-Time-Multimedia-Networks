"""
main.py
=======
Command-line entry point for the AI-Driven QoS Management project.

Commands
--------
    python main.py simulate            -- run a quick simulation demo
    python main.py dataset             -- generate the ML dataset
    python main.py train               -- train the congestion model
    python main.py evaluate            -- run full evaluation + graphs
    python main.py predict             -- run congestion prediction demo
    python main.py all                 -- run all steps in order

Use --help for full options.
"""

import argparse
import sys
import os


def cmd_simulate(args):
    from traffic_simulation import run_simulation
    from metrics import all_class_summaries
    import config

    print(f"\n{'='*60}")
    print(f"  Simulation: {args.scheduler.upper()} | Load: {args.load}")
    print(f"{'='*60}")

    result = run_simulation(
        scheduler=args.scheduler,
        load_scenario=args.load,
        duration_s=args.duration,
    )

    summaries = all_class_summaries(result)
    for s in summaries:
        print(f"\n  [{s['traffic_class'].upper()}]")
        print(f"    Offered   : {s['packets_offered']} pkts")
        print(f"    Delivered : {s['packets_delivered']} pkts")
        print(f"    Dropped   : {s['packets_dropped']} pkts")
        print(f"    Loss      : {s['packet_loss_pct']:.2f}%")
        print(f"    Throughput: {s['throughput_mbps']:.4f} Mbps")
        print(f"    Avg Delay : {s['avg_delay_ms']:.4f} ms")
        print(f"    Avg Jitter: {s['avg_jitter_ms']:.4f} ms")
        print(f"    Link Util : {s['link_util_pct']:.2f}%")


def cmd_dataset(args):
    from dataset_generation import generate_dataset
    generate_dataset(n_seeds_per_scenario=args.seeds, verbose=True)


def cmd_train(args):
    from train_model import train_and_evaluate
    r = train_and_evaluate(verbose=True)
    print(f"\n[OK] RF Accuracy: {r['rf_accuracy']:.4f} | Dummy: {r['dummy_accuracy']:.4f}")


def cmd_evaluate(args):
    from evaluation import run_evaluation
    df = run_evaluation(duration_s=args.duration, verbose=True)
    print(f"\n[OK] Evaluation complete. {len(df)} rows of results.")


def cmd_predict(args):
    from predict_congestion import (
        load_model, predict_from_simulation, _print_prediction
    )
    from traffic_simulation import run_simulation
    import config

    sim_result = run_simulation(
        scheduler=args.scheduler,
        load_scenario=args.load,
        duration_s=args.duration,
    )
    multiplier = config.LOAD_SCENARIOS[args.load]["multiplier"]
    model, metadata = load_model()
    result = predict_from_simulation(sim_result, multiplier, model, metadata)
    _print_prediction(result)


def cmd_all(args):
    print("\n[>>] Running full pipeline ...\n")
    cmd_dataset(args)
    cmd_train(args)
    cmd_evaluate(args)
    cmd_predict(args)
    print("\n[OK] All steps completed successfully.")


def main():
    parser = argparse.ArgumentParser(
        description="AI-Driven QoS Management for Real-Time Multimedia Networks"
    )
    parser.add_argument("command",
        choices=["simulate", "dataset", "train", "evaluate", "predict", "all"],
        help="Action to perform"
    )
    parser.add_argument("--scheduler", default="fifo", choices=["fifo", "priority"],
        help="Scheduler type (default: fifo)")
    parser.add_argument("--load", default="medium", choices=["low", "medium", "high"],
        help="Traffic load scenario (default: medium)")
    parser.add_argument("--duration", type=float, default=None,
        help="Simulation duration in seconds (default from config)")
    parser.add_argument("--seeds", type=int, default=40,
        help="Seeds per scenario for dataset generation (default: 40)")

    args = parser.parse_args()

    # Ensure output directories exist
    import config
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    os.makedirs(config.FIGURES_DIR, exist_ok=True)
    os.makedirs(config.MODELS_DIR,  exist_ok=True)
    os.makedirs(config.DATA_DIR,    exist_ok=True)

    dispatch = {
        "simulate": cmd_simulate,
        "dataset":  cmd_dataset,
        "train":    cmd_train,
        "evaluate": cmd_evaluate,
        "predict":  cmd_predict,
        "all":      cmd_all,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
