"""Formal preprocessing for real flood-event CSV files."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ("time", "prcp", "level", "inflow", "outflow")
DEFAULT_EXPECTED_TIME_STEP_HOURS = 3
PREPROCESSING_VERSION = "real_event_preprocess_v1"


@dataclass(frozen=True)
class EventPreprocessResult:
    event_id: str
    raw_path: str
    processed_path: str
    raw_row_count: int
    processed_row_count: int
    inflow_missing_count_raw: int
    outflow_missing_count_raw: int
    rows_dropped_due_to_missing_inflow: int
    outflow_filled_by_inflow_count: int
    level_interpolated_count: int
    outflow_fallback_applied: bool
    inflow_drop_applied: bool
    level_interpolation_applied: bool
    valid_time_axis: bool
    non_increasing_time_count: int
    irregular_time_step_count: int
    expected_time_step_hours: int
    strict_clean_eligible: bool
    repaired_executable_eligible: bool
    diagnostic_only: bool
    event_class: str
    notes: str

    def to_manifest_row(self) -> dict[str, Any]:
        return asdict(self)


def preprocess_flood_event_directory(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    manifest_path: str | Path,
    expected_time_step_hours: int = DEFAULT_EXPECTED_TIME_STEP_HOURS,
    preprocessing_version: str = PREPROCESSING_VERSION,
) -> list[dict[str, Any]]:
    """Preprocess all flood-event CSV files and write a manifest."""

    raw_root = Path(input_dir)
    if not raw_root.exists():
        raise FileNotFoundError(f"Missing input directory: {raw_root}")
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    rows = [
        preprocess_flood_event_file(
            raw_path=path,
            output_dir=output_root,
            expected_time_step_hours=expected_time_step_hours,
            preprocessing_version=preprocessing_version,
        ).to_manifest_row()
        for path in sorted(raw_root.glob("*.csv"))
    ]
    resolved_manifest = Path(manifest_path)
    resolved_manifest.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(resolved_manifest, index=False, encoding="utf-8-sig")
    return rows


def preprocess_flood_event_file(
    *,
    raw_path: str | Path,
    output_dir: str | Path,
    expected_time_step_hours: int = DEFAULT_EXPECTED_TIME_STEP_HOURS,
    preprocessing_version: str = PREPROCESSING_VERSION,
) -> EventPreprocessResult:
    """Preprocess one raw flood-event CSV into the processed directory."""

    source = Path(raw_path)
    frame = _read_csv(source)
    _validate_columns(source, frame)

    raw_row_count = int(len(frame))
    inflow_missing_count_raw = int(frame["inflow"].isna().sum())
    outflow_missing_count_raw = int(frame["outflow"].isna().sum())

    processed = frame.copy()
    processed["outflow_filled_by_inflow"] = False
    processed["level_filled_by_interpolation"] = False
    processed["source_event_id"] = source.stem
    processed["preprocessing_version"] = preprocessing_version

    inflow_missing_mask = processed["inflow"].isna()
    rows_dropped_due_to_missing_inflow = int(inflow_missing_mask.sum())
    if rows_dropped_due_to_missing_inflow:
        processed = processed.loc[~inflow_missing_mask].copy()

    outflow_fill_mask = processed["outflow"].isna() & processed["inflow"].notna()
    outflow_filled_by_inflow_count = int(outflow_fill_mask.sum())
    if outflow_filled_by_inflow_count:
        processed.loc[outflow_fill_mask, "outflow"] = processed.loc[outflow_fill_mask, "inflow"]
        processed.loc[outflow_fill_mask, "outflow_filled_by_inflow"] = True

    level_interpolated_count = _fill_missing_level_by_time(processed)

    time_check = inspect_time_axis(
        processed,
        expected_time_step_hours=expected_time_step_hours,
    )
    critical_missing_columns = [
        column
        for column in ("time", "level", "inflow", "outflow")
        if processed[column].isna().any()
    ]
    processed_row_count = int(len(processed))
    insufficient_workflow_horizon = processed_row_count < 2
    valid_time_axis = bool(time_check["valid_time_axis"])
    has_repair = bool(
        rows_dropped_due_to_missing_inflow
        or outflow_filled_by_inflow_count
        or level_interpolated_count
    )
    strict_clean_eligible = (
        inflow_missing_count_raw == 0
        and outflow_missing_count_raw == 0
        and not has_repair
        and valid_time_axis
        and not critical_missing_columns
        and not insufficient_workflow_horizon
    )
    repaired_executable_eligible = (
        has_repair
        and valid_time_axis
        and not critical_missing_columns
        and not insufficient_workflow_horizon
    )
    diagnostic_only = not strict_clean_eligible and not repaired_executable_eligible
    event_class = (
        "strict_clean"
        if strict_clean_eligible
        else "repaired_executable"
        if repaired_executable_eligible
        else "diagnostic_only"
    )
    notes = _build_notes(
        critical_missing_columns=critical_missing_columns,
        insufficient_workflow_horizon=insufficient_workflow_horizon,
        valid_time_axis=valid_time_axis,
        non_increasing_time_count=int(time_check["non_increasing_time_count"]),
        irregular_time_step_count=int(time_check["irregular_time_step_count"]),
        level_interpolated_count=level_interpolated_count,
    )

    processed_path = Path(output_dir) / source.name
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_path, index=False, encoding="utf-8-sig")

    return EventPreprocessResult(
        event_id=source.stem,
        raw_path=source.as_posix(),
        processed_path=processed_path.as_posix(),
        raw_row_count=raw_row_count,
        processed_row_count=processed_row_count,
        inflow_missing_count_raw=inflow_missing_count_raw,
        outflow_missing_count_raw=outflow_missing_count_raw,
        rows_dropped_due_to_missing_inflow=rows_dropped_due_to_missing_inflow,
        outflow_filled_by_inflow_count=outflow_filled_by_inflow_count,
        level_interpolated_count=level_interpolated_count,
        outflow_fallback_applied=outflow_filled_by_inflow_count > 0,
        inflow_drop_applied=rows_dropped_due_to_missing_inflow > 0,
        level_interpolation_applied=level_interpolated_count > 0,
        valid_time_axis=valid_time_axis,
        non_increasing_time_count=int(time_check["non_increasing_time_count"]),
        irregular_time_step_count=int(time_check["irregular_time_step_count"]),
        expected_time_step_hours=int(expected_time_step_hours),
        strict_clean_eligible=strict_clean_eligible,
        repaired_executable_eligible=repaired_executable_eligible,
        diagnostic_only=diagnostic_only,
        event_class=event_class,
        notes=notes,
    )


def inspect_time_axis(
    frame: pd.DataFrame,
    *,
    expected_time_step_hours: int = DEFAULT_EXPECTED_TIME_STEP_HOURS,
) -> dict[str, Any]:
    """Check whether the time column is strictly increasing and on the expected step."""

    if frame.empty:
        return {
            "valid_time_axis": False,
            "non_increasing_time_count": 0,
            "irregular_time_step_count": 0,
            "expected_time_step_hours": int(expected_time_step_hours),
        }

    timestamps = pd.to_datetime(frame["time"], errors="coerce")
    if timestamps.isna().any():
        return {
            "valid_time_axis": False,
            "non_increasing_time_count": 0,
            "irregular_time_step_count": max(len(frame) - 1, 0),
            "expected_time_step_hours": int(expected_time_step_hours),
        }

    deltas = timestamps.diff().dt.total_seconds().div(3600.0).iloc[1:]
    non_increasing_time_count = int((deltas <= 0).sum())
    irregular_time_step_count = int(
        ((deltas > 0) & (deltas.sub(float(expected_time_step_hours)).abs() > 1e-6)).sum()
    )
    return {
        "valid_time_axis": non_increasing_time_count == 0 and irregular_time_step_count == 0,
        "non_increasing_time_count": non_increasing_time_count,
        "irregular_time_step_count": irregular_time_step_count,
        "expected_time_step_hours": int(expected_time_step_hours),
    }


def summarize_manifest(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return aggregate counts for CLI output."""

    return {
        "total_events": len(rows),
        "strict_clean_count": sum(1 for row in rows if row["event_class"] == "strict_clean"),
        "repaired_executable_count": sum(
            1 for row in rows if row["event_class"] == "repaired_executable"
        ),
        "diagnostic_only_count": sum(1 for row in rows if row["event_class"] == "diagnostic_only"),
        "total_outflow_filled_count": sum(
            int(row["outflow_filled_by_inflow_count"]) for row in rows
        ),
        "total_level_interpolated_count": sum(int(row["level_interpolated_count"]) for row in rows),
        "total_inflow_dropped_rows": sum(
            int(row["rows_dropped_due_to_missing_inflow"]) for row in rows
        ),
        "invalid_time_axis_events": sum(1 for row in rows if not row["valid_time_axis"]),
    }


def _read_csv(path: Path) -> pd.DataFrame:
    read_kwargs = {
        "na_values": ["", " ", "  ", "\u3000", "\u3000\u3000"],
        "keep_default_na": True,
    }
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **read_kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="gb18030", **read_kwargs)


def _validate_columns(path: Path, frame: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"{path}: missing required columns {missing}")


def _build_notes(
    *,
    critical_missing_columns: list[str],
    insufficient_workflow_horizon: bool,
    valid_time_axis: bool,
    non_increasing_time_count: int,
    irregular_time_step_count: int,
    level_interpolated_count: int = 0,
) -> str:
    notes: list[str] = []
    if level_interpolated_count:
        notes.append(f"level_interpolated_count={level_interpolated_count}")
    if critical_missing_columns:
        notes.append(f"critical_missing_after_preprocessing={','.join(critical_missing_columns)}")
    if insufficient_workflow_horizon:
        notes.append("insufficient_workflow_horizon")
    if not valid_time_axis:
        if non_increasing_time_count:
            notes.append(f"non_increasing_time_count={non_increasing_time_count}")
        if irregular_time_step_count:
            notes.append(f"irregular_time_step_count={irregular_time_step_count}")
    return "; ".join(notes)


def _fill_missing_level_by_time(frame: pd.DataFrame) -> int:
    if "level" not in frame.columns or frame.empty:
        return 0
    missing_mask = frame["level"].isna()
    if not bool(missing_mask.any()):
        return 0

    timestamps = pd.to_datetime(frame["time"], errors="coerce")
    if timestamps.isna().any():
        return 0

    values = frame["level"].astype(float).to_numpy()
    valid_mask = ~np.isnan(values)
    if valid_mask.sum() == 0:
        return 0

    x = timestamps.astype("int64").to_numpy(dtype=np.float64)
    x_valid = x[valid_mask]
    y_valid = values[valid_mask]
    filled = values.copy()

    if valid_mask.sum() == 1:
        filled[~valid_mask] = y_valid[0]
    else:
        filled[~valid_mask] = np.interp(x[~valid_mask], x_valid, y_valid)

        leading_mask = (~valid_mask) & (x < x_valid[0])
        if leading_mask.any():
            slope = (y_valid[1] - y_valid[0]) / (x_valid[1] - x_valid[0])
            filled[leading_mask] = y_valid[0] + (x[leading_mask] - x_valid[0]) * slope

        trailing_mask = (~valid_mask) & (x > x_valid[-1])
        if trailing_mask.any():
            slope = (y_valid[-1] - y_valid[-2]) / (x_valid[-1] - x_valid[-2])
            filled[trailing_mask] = y_valid[-1] + (x[trailing_mask] - x_valid[-1]) * slope

    frame.loc[missing_mask, "level"] = filled[missing_mask]
    frame.loc[missing_mask, "level_filled_by_interpolation"] = True
    return int(missing_mask.sum())
