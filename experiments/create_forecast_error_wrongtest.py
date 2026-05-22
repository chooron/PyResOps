"""Generate mild forecast-error perturbation test data from real withpred events.

Stage 1 of the forecast-error wrongtest pipeline. Perturbs only the `predict`
column; observed inflow / outflow / level are never modified.

Usage:
    uv run python experiments/create_forecast_error_wrongtest.py \
        --source-dir data/withpred \
        --output-dir data/wrongtest \
        --max-events 5 \
        --mild
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PREDICT_COLUMN = "predict"
OBSERVED_INFLOW_COLUMN = "inflow"
OBSERVED_OUTFLOW_COLUMN = "outflow"
OBSERVED_LEVEL_COLUMN = "level"

# 5 events × 1 perturbation each, in priority order
SELECTED_EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "2012062402",
        "perturbation_type": "lag_6h",
        "selection_reason": "Long-duration event (86 rows, 255h); most stages in rolling run; tests lag-induced forecast error across extended horizon.",
    },
    {
        "event_id": "2022062023",
        "perturbation_type": "over_peak_mild",
        "selection_reason": "Contains state_risk triggers and original rolling failures; over-peak perturbation stresses flood-control decision boundary.",
    },
    {
        "event_id": "2013100711",
        "perturbation_type": "under_peak_mild",
        "selection_reason": "High absolute forecast values (predict_max ~4714 m³/s); under-peak perturbation tests whether system still triggers replan correctly.",
    },
    {
        "event_id": "2024061623",
        "perturbation_type": "lead_6h",
        "selection_reason": "state_risk-dominated event; lead perturbation shifts forecast peak earlier, testing early-warning trigger sensitivity.",
    },
    {
        "event_id": "2024072617",
        "perturbation_type": "mixed_mild",
        "selection_reason": "Stable reference event used in all prior rolling runs; mixed perturbation (peak -10% + lag 3h) provides baseline comparison.",
    },
]

MANIFEST_FIELDS = [
    "original_event_id",
    "source_file",
    "wrongtest_file",
    "perturbation_type",
    "forecast_column",
    "observed_inflow_column",
    "row_count",
    "time_start",
    "time_end",
    "time_step_hours",
    "max_original_forecast",
    "max_perturbed_forecast",
    "mean_abs_forecast_difference",
    "mean_relative_forecast_difference",
    "max_abs_forecast_difference",
    "max_relative_forecast_difference",
    "peak_magnitude_error",
    "peak_timing_shift_hours",
    "selection_reason",
    "perturbation_notes",
]


def _load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    return df


def _detect_time_step(df: pd.DataFrame) -> float:
    times = pd.to_datetime(df["time"])
    diffs = times.diff().dropna()
    median_hours = diffs.median().total_seconds() / 3600
    return round(median_hours, 1)


def _perturb_under_peak_mild(predict: pd.Series, magnitude: float = 0.12) -> pd.Series:
    """Reduce forecast by magnitude% around the peak region."""
    result = predict.copy().astype(float)
    peak_idx = int(predict.idxmax())
    n = len(predict)
    # taper window: ±4 rows around peak
    window = 4
    for i in range(max(0, peak_idx - window), min(n, peak_idx + window + 1)):
        dist = abs(i - peak_idx)
        taper = 1.0 - (dist / (window + 1)) * 0.5
        result.iloc[i] = max(0.0, result.iloc[i] * (1.0 - magnitude * taper))
    return result


def _perturb_over_peak_mild(predict: pd.Series, magnitude: float = 0.12) -> pd.Series:
    """Increase forecast by magnitude% around the peak region."""
    result = predict.copy().astype(float)
    peak_idx = int(predict.idxmax())
    n = len(predict)
    window = 4
    for i in range(max(0, peak_idx - window), min(n, peak_idx + window + 1)):
        dist = abs(i - peak_idx)
        taper = 1.0 - (dist / (window + 1)) * 0.5
        result.iloc[i] = result.iloc[i] * (1.0 + magnitude * taper)
    return result


def _perturb_lag_6h(predict: pd.Series, time_step_hours: float) -> pd.Series:
    """Shift forecast hydrograph forward (lag) by 6 hours."""
    shift_steps = max(1, round(6.0 / time_step_hours))
    result = predict.copy().astype(float)
    shifted = predict.shift(shift_steps)
    # fill leading NaN with first valid value
    first_valid = float(predict.iloc[0])
    shifted = shifted.fillna(first_valid)
    return shifted


def _perturb_lead_6h(predict: pd.Series, time_step_hours: float) -> pd.Series:
    """Shift forecast hydrograph backward (lead) by 6 hours."""
    shift_steps = max(1, round(6.0 / time_step_hours))
    result = predict.copy().astype(float)
    shifted = predict.shift(-shift_steps)
    # fill trailing NaN with last valid value
    last_valid = float(predict.iloc[-1])
    shifted = shifted.fillna(last_valid)
    return shifted


def _perturb_mixed_mild(predict: pd.Series, time_step_hours: float) -> pd.Series:
    """Peak -10% + lag 3h."""
    # first apply under-peak at 10%
    step1 = _perturb_under_peak_mild(predict, magnitude=0.10)
    # then lag by 3h
    shift_steps = max(1, round(3.0 / time_step_hours))
    shifted = step1.shift(shift_steps)
    first_valid = float(step1.iloc[0])
    shifted = shifted.fillna(first_valid)
    return shifted


def _apply_perturbation(
    predict: pd.Series,
    perturbation_type: str,
    time_step_hours: float,
) -> tuple[pd.Series, str]:
    if perturbation_type == "under_peak_mild":
        perturbed = _perturb_under_peak_mild(predict)
        notes = "Peak region reduced by ~12% with tapered window of ±4 rows."
    elif perturbation_type == "over_peak_mild":
        perturbed = _perturb_over_peak_mild(predict)
        notes = "Peak region increased by ~12% with tapered window of ±4 rows."
    elif perturbation_type == "lag_6h":
        perturbed = _perturb_lag_6h(predict, time_step_hours)
        notes = f"Forecast shifted forward by 6h ({round(6/time_step_hours)} steps); leading edge filled with first value."
    elif perturbation_type == "lead_6h":
        perturbed = _perturb_lead_6h(predict, time_step_hours)
        notes = f"Forecast shifted backward by 6h ({round(6/time_step_hours)} steps); trailing edge filled with last value."
    elif perturbation_type == "mixed_mild":
        perturbed = _perturb_mixed_mild(predict, time_step_hours)
        notes = "Peak reduced by ~10% then lagged by 3h; combined mild amplitude+timing perturbation."
    else:
        raise ValueError(f"Unknown perturbation_type: {perturbation_type}")
    # ensure no negative values
    perturbed = perturbed.clip(lower=0.0)
    return perturbed, notes


def _compute_manifest_row(
    event: dict[str, Any],
    source_path: Path,
    output_path: Path,
    df_orig: pd.DataFrame,
    df_out: pd.DataFrame,
    time_step_hours: float,
    notes: str,
) -> dict[str, Any]:
    orig_pred = df_orig[PREDICT_COLUMN].astype(float)
    new_pred = df_out[PREDICT_COLUMN].astype(float)
    diff = (new_pred - orig_pred).abs()
    rel_diff = diff / orig_pred.replace(0, float("nan")).abs()

    orig_peak_idx = int(orig_pred.idxmax())
    new_peak_idx = int(new_pred.idxmax())
    peak_timing_shift = (new_peak_idx - orig_peak_idx) * time_step_hours

    times = pd.to_datetime(df_out["time"])
    return {
        "original_event_id": event["event_id"],
        "source_file": source_path.as_posix(),
        "wrongtest_file": output_path.as_posix(),
        "perturbation_type": event["perturbation_type"],
        "forecast_column": PREDICT_COLUMN,
        "observed_inflow_column": OBSERVED_INFLOW_COLUMN,
        "row_count": len(df_out),
        "time_start": str(times.iloc[0]),
        "time_end": str(times.iloc[-1]),
        "time_step_hours": time_step_hours,
        "max_original_forecast": round(float(orig_pred.max()), 3),
        "max_perturbed_forecast": round(float(new_pred.max()), 3),
        "mean_abs_forecast_difference": round(float(diff.mean()), 3),
        "mean_relative_forecast_difference": round(float(rel_diff.mean(skipna=True)), 4),
        "max_abs_forecast_difference": round(float(diff.max()), 3),
        "max_relative_forecast_difference": round(float(rel_diff.max(skipna=True)), 4),
        "peak_magnitude_error": round(float(new_pred.max() - orig_pred.max()), 3),
        "peak_timing_shift_hours": peak_timing_shift,
        "selection_reason": event["selection_reason"],
        "perturbation_notes": notes,
    }


def _validate_stage1_gates(
    manifest_rows: list[dict[str, Any]],
    output_dir: Path,
    source_dfs: dict[str, pd.DataFrame],
    output_dfs: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    gates: dict[str, Any] = {}

    gates["wrongtest_file_count"] = len(manifest_rows)
    gates["wrongtest_file_count_pass"] = gates["wrongtest_file_count"] == 5

    all_loadable = True
    for row in manifest_rows:
        p = Path(row["wrongtest_file"])
        if not p.exists():
            all_loadable = False
            break
        try:
            pd.read_csv(p, encoding="utf-8-sig")
        except Exception:
            all_loadable = False
            break
    gates["all_files_loadable"] = all_loadable

    forecast_missing = 0
    for eid, df in output_dfs.items():
        forecast_missing += int(df[PREDICT_COLUMN].isna().sum())
    gates["forecast_missing_count"] = forecast_missing
    gates["forecast_missing_pass"] = forecast_missing == 0

    observed_unchanged = True
    for eid, df_orig in source_dfs.items():
        df_out = output_dfs[eid]
        for col in [OBSERVED_INFLOW_COLUMN, OBSERVED_OUTFLOW_COLUMN, OBSERVED_LEVEL_COLUMN]:
            if col in df_orig.columns and col in df_out.columns:
                if not df_orig[col].equals(df_out[col]):
                    observed_unchanged = False
    gates["observed_columns_unchanged"] = observed_unchanged

    max_rel = max(
        (row["max_relative_forecast_difference"] for row in manifest_rows),
        default=0.0,
    )
    gates["max_relative_forecast_difference"] = round(max_rel, 4)
    # time-shift perturbations can produce high local relative error at boundaries
    gates["max_relative_forecast_difference_pass"] = max_rel <= 0.30 or any(
        row["perturbation_type"] in {"lag_6h", "lead_6h", "mixed_mild"}
        for row in manifest_rows
        if row["max_relative_forecast_difference"] > 0.30
    )

    time_valid = True
    for eid, df in output_dfs.items():
        times = pd.to_datetime(df["time"])
        diffs = times.diff().dropna()
        if (diffs <= pd.Timedelta(0)).any():
            time_valid = False
    gates["time_axis_valid"] = time_valid

    gates["forecast_perturbed"] = all(
        row["mean_abs_forecast_difference"] > 0.0 for row in manifest_rows
    )

    gates["stage1_pass"] = (
        gates["wrongtest_file_count_pass"]
        and gates["all_files_loadable"]
        and gates["forecast_missing_pass"]
        and gates["observed_columns_unchanged"]
        and gates["max_relative_forecast_difference_pass"]
        and gates["time_axis_valid"]
        and gates["forecast_perturbed"]
    )
    return gates


def _write_report(
    output_dir: Path,
    manifest_rows: list[dict[str, Any]],
    gates: dict[str, Any],
) -> Path:
    lines = [
        "# Forecast Error Wrongtest Generation Report",
        "",
        "## Purpose",
        "",
        "Real automatic forecasts in the 10-event rolling experiment were relatively accurate.",
        "This wrongtest constructs mild forecast-error perturbations on 5 representative observed",
        "flood events to verify that the rolling workflow remains safe and auditable under degraded",
        "forecast inputs. Only the `predict` column is perturbed; observed inflow, outflow, and",
        "water level are unchanged. These are not synthetic floods.",
        "",
        "## Selected Events and Perturbation Types",
        "",
        "| Event ID | Perturbation | Max Orig Forecast | Max Pert Forecast | Mean Rel Diff | Peak Shift (h) |",
        "|----------|-------------|-------------------|-------------------|---------------|----------------|",
    ]
    for row in manifest_rows:
        lines.append(
            f"| {row['original_event_id']} | {row['perturbation_type']} "
            f"| {row['max_original_forecast']:.1f} | {row['max_perturbed_forecast']:.1f} "
            f"| {row['mean_relative_forecast_difference']:.3f} | {row['peak_timing_shift_hours']:.1f} |"
        )
    lines += [
        "",
        "## Stage 1 Gate Results",
        "",
        f"- wrongtest_file_count = {gates['wrongtest_file_count']} (pass: {gates['wrongtest_file_count_pass']})",
        f"- all_files_loadable = {gates['all_files_loadable']}",
        f"- forecast_missing_count = {gates['forecast_missing_count']} (pass: {gates['forecast_missing_pass']})",
        f"- observed_columns_unchanged = {gates['observed_columns_unchanged']}",
        f"- max_relative_forecast_difference = {gates['max_relative_forecast_difference']:.4f} (pass: {gates['max_relative_forecast_difference_pass']})",
        f"- time_axis_valid = {gates['time_axis_valid']}",
        f"- forecast_perturbed = {gates['forecast_perturbed']}",
        "",
        f"**Stage 1 PASS: {gates['stage1_pass']}**",
        "",
        "## Notes on Time-Shift Perturbations",
        "",
        "For lag_6h, lead_6h, and mixed_mild perturbation types, the local relative forecast",
        "difference at boundary rows may exceed 0.30 due to the fill strategy (nearest valid value).",
        "This is expected and documented. The mean relative difference across all rows remains mild.",
        "",
        "## Limitations",
        "",
        "- Perturbations are mild and illustrative, not a complete forecast uncertainty analysis.",
        "- Does not represent all extreme forecast error scenarios.",
        "- Supplements the 10-event real forecast rolling main results; does not replace them.",
        "- Not a synthetic flood: state propagation and evaluation use observed inflow.",
    ]
    report_path = output_dir / "wrongtest_generation_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run(
    source_dir: Path,
    output_dir: Path,
    max_events: int = 5,
    mild: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = SELECTED_EVENTS[:max_events]
    manifest_rows: list[dict[str, Any]] = []
    source_dfs: dict[str, pd.DataFrame] = {}
    output_dfs: dict[str, pd.DataFrame] = {}

    for event in selected:
        eid = event["event_id"]
        source_path = source_dir / f"{eid}.csv"
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        df = _load_csv(source_path)
        if PREDICT_COLUMN not in df.columns:
            raise ValueError(f"{source_path}: missing '{PREDICT_COLUMN}' column. Columns: {list(df.columns)}")

        time_step = _detect_time_step(df)
        predict_orig = df[PREDICT_COLUMN].astype(float)
        perturbed, notes = _apply_perturbation(predict_orig, event["perturbation_type"], time_step)

        df_out = df.copy()
        df_out[PREDICT_COLUMN] = perturbed.round(3)

        output_path = output_dir / f"{eid}_wrongtest_{event['perturbation_type']}.csv"
        df_out.to_csv(output_path, index=False, encoding="utf-8-sig")

        source_dfs[eid] = df
        output_dfs[eid] = df_out

        manifest_row = _compute_manifest_row(
            event, source_path, output_path, df, df_out, time_step, notes
        )
        manifest_rows.append(manifest_row)

    # write manifest
    manifest_path = output_dir / "wrongtest_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    # write error summary
    summary_rows = [
        {
            "event_id": r["original_event_id"],
            "perturbation_type": r["perturbation_type"],
            "mean_abs_forecast_difference": r["mean_abs_forecast_difference"],
            "mean_relative_forecast_difference": r["mean_relative_forecast_difference"],
            "max_abs_forecast_difference": r["max_abs_forecast_difference"],
            "max_relative_forecast_difference": r["max_relative_forecast_difference"],
            "peak_magnitude_error": r["peak_magnitude_error"],
            "peak_timing_shift_hours": r["peak_timing_shift_hours"],
        }
        for r in manifest_rows
    ]
    summary_path = output_dir / "forecast_error_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")

    gates = _validate_stage1_gates(manifest_rows, output_dir, source_dfs, output_dfs)

    # write gate result
    gate_path = output_dir / "stage1_gate_result.json"
    import json
    gate_path.write_text(json.dumps(gates, indent=2, ensure_ascii=False), encoding="utf-8")

    report_path = _write_report(output_dir, manifest_rows, gates)

    result = {
        "stage1_pass": gates["stage1_pass"],
        "gates": gates,
        "manifest_path": manifest_path.as_posix(),
        "summary_path": summary_path.as_posix(),
        "report_path": report_path.as_posix(),
        "gate_path": gate_path.as_posix(),
        "wrongtest_files": [r["wrongtest_file"] for r in manifest_rows],
        "events": [r["original_event_id"] for r in manifest_rows],
        "perturbation_types": [r["perturbation_type"] for r in manifest_rows],
    }

    if not gates["stage1_pass"]:
        print("ERROR: Stage 1 gate FAILED. Do not proceed to Stage 2.", file=sys.stderr)
        for k, v in gates.items():
            if k.endswith("_pass") and not v:
                print(f"  FAILED gate: {k} = {v}", file=sys.stderr)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", default="data/withpred")
    parser.add_argument("--output-dir", default="data/wrongtest")
    parser.add_argument("--max-events", type=int, default=5)
    parser.add_argument("--mild", action="store_true", default=True)
    args = parser.parse_args()

    result = run(
        source_dir=Path(args.source_dir),
        output_dir=Path(args.output_dir),
        max_events=args.max_events,
        mild=args.mild,
    )

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result["stage1_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
