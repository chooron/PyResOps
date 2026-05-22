"""CLI runner for Stage 2 dynamic command-intervention workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.stage1.dynamic_command_intervention import (
    SELECTED_EVENTS,
    COMMAND_TYPES,
    CHECKPOINT_LABELS,
)
from experiments.stage2.dynamic_command_intervention_workflow import (
    DynamicCommandInterventionWorkflow,
    DynamicCommandInterventionComparator,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Stage 2 dynamic command-intervention workflow."
    )
    parser.add_argument("--events", nargs="+", default=SELECTED_EVENTS)
    parser.add_argument("--command-types", nargs="+", default=COMMAND_TYPES)
    parser.add_argument("--checkpoints", nargs="+", default=CHECKPOINT_LABELS)
    parser.add_argument("--data-root", default="data")
    parser.add_argument(
        "--output",
        default="experiments/results/stage2_dynamic_command_intervention",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run comparison against Stage 1 oracle (requires --stage1-dir)",
    )
    parser.add_argument(
        "--stage1-dir",
        default="experiments/results/stage1_dynamic_command_intervention",
        help="Stage 1 oracle directory (used with --compare)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.compare:
        # Compare mode: load existing Stage 2 results against Stage 1 oracle
        s2_path = out_dir / "results.csv"
        s1_path = Path(args.stage1_dir) / "results.csv"

        if not s2_path.exists():
            print(f"ERROR: Stage 2 results not found at {s2_path}. Run without --compare first.")
            return
        if not s1_path.exists():
            print(f"ERROR: Stage 1 oracle not found at {s1_path}.")
            return

        s2_df = pd.read_csv(s2_path)
        s2_records = s2_df.to_dict(orient="records")

        comparator = DynamicCommandInterventionComparator(oracle_dir=args.stage1_dir)
        cmp_df = comparator.compare(s2_records)

        cmp_dir = out_dir / "comparison"
        cmp_dir.mkdir(parents=True, exist_ok=True)
        cmp_df.to_csv(cmp_dir / "stage2_vs_stage1_dynamic_command_comparison.csv", index=False)

        total = len(cmp_df)
        passed = int(cmp_df["passes_oracle"].sum()) if "passes_oracle" in cmp_df.columns else 0
        failed = total - passed
        oracle_pass = failed == 0

        summary = {
            "total_rows": total,
            "oracle_pass_count": passed,
            "oracle_fail_count": failed,
            "oracle_pass": oracle_pass,
        }
        (out_dir / "summary").mkdir(parents=True, exist_ok=True)
        (out_dir / "summary" / "dynamic_command_stage2_metrics.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

        print(f"Oracle comparison: {passed}/{total} passed, oracle_pass={oracle_pass}")
        print(f"Comparison written to {cmp_dir}")
        return

    # Run mode: execute Stage 2 workflow
    workflow = DynamicCommandInterventionWorkflow(data_root=args.data_root)
    results = workflow.run_all(
        events=args.events,
        command_types=args.command_types,
        checkpoint_labels=args.checkpoints,
    )

    df = pd.DataFrame(results)
    # Strip tool_trace from CSV
    df_csv = df.drop(columns=["tool_trace"], errors="ignore")
    df_csv.to_csv(out_dir / "results.csv", index=False)

    total = len(df)
    handling_ok = int(df["command_handling_success"].sum()) if "command_handling_success" in df.columns else 0
    execution_ok = int(df["feasible_execution_success"].sum()) if "feasible_execution_success" in df.columns else 0

    if args.verbose:
        print(f"Stage 2 dynamic command-intervention: {total} records")
        print(f"  command_handling_success: {handling_ok}/{total}")
        print(f"  feasible_execution_success: {execution_ok}/{total}")
        print(f"Results written to {out_dir}")


if __name__ == "__main__":
    main()
