"""Stage 1 baseline CLI entry point.

Usage:
    python -m experiments.run_stage1_baseline --workflow static
    python -m experiments.run_stage1_baseline --workflow dynamic
    python -m experiments.run_stage1_baseline --workflow rolling
    python -m experiments.run_stage1_baseline --workflow all
    python -m experiments.run_stage1_baseline --workflow static --events 2010062002 2022062023
    python -m experiments.run_stage1_baseline --workflow static --output experiments/results/my_run/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from experiments.stage1.classify import classify_all_events
from experiments.stage1.reporting import generate_summary_tables
from experiments.stage1.runner import Stage1Runner


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_static_events(runner: Stage1Runner) -> list[str]:
    files = runner.adapter.list_raw_flood_event_files()
    return [p.stem for p in files]


def _resolve_dynamic_events(config: dict) -> list[str]:
    return [str(e) for e in config.get("dynamic_events", [])]


def _resolve_rolling_events(config: dict) -> list[str]:
    return [str(e) for e in config.get("rolling_events", [])]


def run_static(
    runner: Stage1Runner,
    events: list[str],
    output_dir: Path,
    verbose: bool,
) -> list[dict]:
    results = []
    for event_id in events:
        if verbose:
            print(f"  [static] {event_id} ...", end=" ", flush=True)
        try:
            row = runner.run_static(event_id)
            results.append(row)
            if verbose:
                status = "OK" if row.get("accepted") else "VIOLATION"
                print(f"{status} | max_level={row.get('max_level')} | group={row.get('scenario_group')}")
        except Exception as exc:
            if verbose:
                print(f"ERROR: {exc}")
            results.append({"event_id": event_id, "error": str(exc), "accepted": False})
    return results


def run_dynamic(
    runner: Stage1Runner,
    events: list[str],
    output_dir: Path,
    verbose: bool,
) -> list[dict]:
    results = []
    for event_id in events:
        if verbose:
            print(f"  [dynamic] {event_id} ...", flush=True)
        try:
            rows = runner.run_dynamic(event_id)
            results.extend(rows)
            if verbose:
                for row in rows:
                    print(f"    {row.get('workflow_stage')} action={row.get('action')} accepted={row.get('accepted')}")
        except Exception as exc:
            if verbose:
                print(f"    ERROR: {exc}")
            results.append({"event_id": event_id, "error": str(exc), "accepted": False})
    return results


def run_rolling(
    runner: Stage1Runner,
    events: list[str],
    output_dir: Path,
    verbose: bool,
) -> list[dict]:
    results = []
    for event_id in events:
        if verbose:
            print(f"  [rolling] {event_id} ...", flush=True)
        try:
            rows = runner.run_rolling(event_id)
            results.extend(rows)
            if verbose:
                triggers = [r.get("trigger_type") for r in rows if r.get("action") == "replan"]
                print(f"    {len(rows)} checks, {len(triggers)} replans: {triggers}")
        except Exception as exc:
            if verbose:
                print(f"    ERROR: {exc}")
            results.append({"event_id": event_id, "error": str(exc), "accepted": False})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1 deterministic baseline experiment")
    parser.add_argument(
        "--workflow",
        choices=["static", "dynamic", "rolling", "all"],
        default="static",
        help="Which workflow(s) to run",
    )
    parser.add_argument(
        "--events",
        nargs="*",
        default=None,
        help="Optional list of event IDs to filter (default: all for the workflow)",
    )
    parser.add_argument(
        "--output",
        default="experiments/results/stage1_baseline",
        help="Output directory",
    )
    parser.add_argument(
        "--config",
        default="experiments/config/stage1_baseline.yml",
        help="Config YAML path",
    )
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    args = parser.parse_args(argv)

    config = _load_config(args.config)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    rolling_thresholds = config.get("rolling_thresholds", {})
    runner = Stage1Runner(
        data_root=config.get("data", {}).get("root", "data"),
        rolling_thresholds=rolling_thresholds,
    )

    static_results: list[dict] = []
    dynamic_results: list[dict] = []
    rolling_results: list[dict] = []

    run_all = args.workflow == "all"

    if run_all or args.workflow == "static":
        events = args.events or _resolve_static_events(runner)
        if args.verbose:
            print(f"Running static workflow on {len(events)} events...")
        static_results = run_static(runner, events, output_dir, args.verbose)

    if run_all or args.workflow == "dynamic":
        events = args.events or _resolve_dynamic_events(config)
        if args.verbose:
            print(f"Running dynamic workflow on {len(events)} events...")
        dynamic_results = run_dynamic(runner, events, output_dir, args.verbose)

    if run_all or args.workflow == "rolling":
        events = args.events or _resolve_rolling_events(config)
        if args.verbose:
            print(f"Running rolling workflow on {len(events)} events...")
        rolling_results = run_rolling(runner, events, output_dir, args.verbose)

    generate_summary_tables(static_results, dynamic_results, rolling_results, output_dir)

    if args.verbose:
        total = len(static_results) + len(dynamic_results) + len(rolling_results)
        print(f"\nDone. {total} result rows written to {output_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
