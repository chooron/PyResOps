"""CLI runner for Stage 1 dynamic command-intervention extension."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.stage1.dynamic_command_intervention import (
    SELECTED_EVENTS,
    COMMAND_TYPES,
    CHECKPOINT_LABELS,
    DynamicCommandInterventionRunner,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Stage 1 dynamic command-intervention extension."
    )
    parser.add_argument(
        "--events", nargs="+", default=SELECTED_EVENTS,
        help="Event IDs to run (default: all 5 selected events)",
    )
    parser.add_argument(
        "--command-types", nargs="+", default=COMMAND_TYPES,
        help="Command types to run",
    )
    parser.add_argument(
        "--checkpoints", nargs="+", default=CHECKPOINT_LABELS,
        help="Checkpoint labels to run (T1, T2_peak)",
    )
    parser.add_argument(
        "--data-root", default="data",
        help="Path to data root directory",
    )
    parser.add_argument(
        "--output", default="experiments/results/stage1_dynamic_command_intervention",
        help="Output directory for results",
    )
    args = parser.parse_args()

    runner = DynamicCommandInterventionRunner(data_root=args.data_root)
    results = runner.run_all(
        events=args.events,
        command_types=args.command_types,
        checkpoint_labels=args.checkpoints,
    )

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)
    df.to_csv(out_dir / "results.csv", index=False)
    try:
        df.to_parquet(out_dir / "results.parquet", index=False)
    except ImportError:
        pass

    total = len(df)
    handling_ok = df["command_handling_success"].sum()
    execution_ok = df["feasible_execution_success"].sum()
    print(f"Stage 1 dynamic command-intervention: {total} records")
    print(f"  command_handling_success: {handling_ok}/{total}")
    print(f"  feasible_execution_success: {execution_ok}/{total}")
    print(f"Results written to {out_dir}")


if __name__ == "__main__":
    main()
