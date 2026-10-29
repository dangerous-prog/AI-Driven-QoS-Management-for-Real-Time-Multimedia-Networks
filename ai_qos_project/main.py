"""
main.py
=======
Command-line entry point for the AI-Driven QoS Management project (Option A & Option B).

Commands
--------
    python main.py simulate            -- run a quick simulation demo (FIFO / Priority)
    python main.py dynamic             -- run Option B closed-loop AI-Driven QoS simulation
    python main.py changing_load       -- run changing-load simulation comparing all 3 policies
    python main.py dataset             -- generate the ML dataset
    python main.py train               -- train the congestion model
    python main.py evaluate            -- run Option A evaluation
    python main.py evaluate_b          -- run Option B 3-way comparative evaluation
    python main.py predict             -- run advisory congestion prediction demo
    python main.py all                 -- run complete end-to-end pipeline

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


def cmd_dynamic(args):
    from traffic_simulation import run_simulation
    from metrics import all_class_summaries

    print(f"\n{'='*65}")
    print(f"  Option B: Closed-Loop AI-Driven QoS Simulation | Load: {args.load}")
    print(f"{'='*65}")

    result = run_simulation(
        scheduler="dynamic",
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

    ctrl_summary = getattr(result, "controller_summary", {})
    if ctrl_summary:
        print(f"\n  [CONTROLLER METRICS]")
        print(f"    Total Decisions: {ctrl_summary.get('total_decisions', 0)}")
        print(f"    Action Changes : {ctrl_summary.get('action_changes', 0)}")
        print(f"    Switching Freq : {ctrl_summary.get('switching_frequency_per_minute', 0.0)} switches/min")
        print(f"    Distribution   : {ctrl_summary.get('action_distribution', {})}")


def cmd_changing_load(args):
    from traffic_simulation import run_changing_load_simulation
    from metrics import avg_delay_ms, packet_loss_pct, throughput_mbps

    print(f"\n{'='*70}")
    print(f"  Option B: Changing-Load Benchmark (Low -> Surge -> Recovery)")
    print(f"{'='*70}")

    dur = args.duration if args.duration is not None else 30.0
    res = run_changing_load_simulation(duration_s=dur)

    print(f"\n{'Scheduler':<25} {'Class':<12} {'Delay (ms)':<12} {'Loss (%)':<10} {'Throughput (Mbps)':<18}")
    print("-" * 75)
    for sched in ["fifo", "priority", "dynamic"]:
        sched_name = res[sched].scheduler_name
        for cls in ["voice", "video", "background"]:
            d = avg_delay_ms(res[sched], cls)
            l = packet_loss_pct(res[sched], cls)
            t = throughput_mbps(res[sched], cls)
            print(f"{sched_name:<25} {cls:<12} {d:<12.2f} {l:<10.2f} {t:<18.4f}")
        print("-" * 75)


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
    print(f"\n[OK] Option A evaluation complete. {len(df)} rows of results.")


def cmd_evaluate_b(args):
    from evaluation import run_evaluation_option_b
    df = run_evaluation_option_b(duration_s=args.duration, verbose=True)
    print(f"\n[OK] Option B 3-Way evaluation complete. {len(df)} rows of results.")


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
    multiplier = config.LOAD_SCENARIOS.get(args.load, {}).get("multiplier", 1.0)
    model, metadata = load_model()
    result = predict_from_simulation(sim_result, multiplier, model, metadata)
    _print_prediction(result)


def cmd_all(args):
    print("\n[>>] Running complete Option A & Option B pipeline ...\n")
    cmd_dataset(args)
    cmd_train(args)
    cmd_evaluate(args)
    cmd_evaluate_b(args)
    cmd_changing_load(args)
    cmd_predict(args)
    print("\n[OK] All steps completed successfully.")


def main():
    parser = argparse.ArgumentParser(
        description="AI-Driven QoS Management for Real-Time Multimedia Networks (Option A & B)"
    )
    parser.add_argument("command",
        choices=[
            "simulate", "dynamic", "changing_load",
            "dataset", "train", "evaluate", "evaluate_b", "predict", "all"
        ],
        help="Action to perform"
    )
    parser.add_argument("--scheduler", default="fifo", choices=["fifo", "priority", "dynamic"],
        help="Scheduler type (default: fifo)")
    parser.add_argument("--load", default="medium",
        choices=["low", "medium", "high", "changing", "sustained"],
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
        "simulate":      cmd_simulate,
        "dynamic":        cmd_dynamic,
        "changing_load":  cmd_changing_load,
        "dataset":        cmd_dataset,
        "train":          cmd_train,
        "evaluate":       cmd_evaluate,
        "evaluate_b":     cmd_evaluate_b,
        "predict":        cmd_predict,
        "all":            cmd_all,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
