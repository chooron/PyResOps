"""Dataset-freeze reporting for paper validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from experiments.paper_validation.utils import load_manifest_rows, write_markdown


def build_dataset_quality_summary(manifest_path: str | Path) -> dict[str, Any]:
    rows = load_manifest_rows(manifest_path)
    if not rows:
        return {
            "total_events": 0,
            "strict_clean_count": 0,
            "repaired_executable_count": 0,
            "diagnostic_only_count": 0,
            "total_outflow_filled_count": 0,
            "total_level_interpolated_count": 0,
            "total_inflow_dropped_rows": 0,
            "invalid_time_axis_events": 0,
        }
    return {
        "total_events": len(rows),
        "strict_clean_count": sum(1 for row in rows if row["event_class"] == "strict_clean"),
        "repaired_executable_count": sum(
            1 for row in rows if row["event_class"] == "repaired_executable"
        ),
        "diagnostic_only_count": sum(1 for row in rows if row["event_class"] == "diagnostic_only"),
        "total_outflow_filled_count": sum(int(row.get("outflow_filled_by_inflow_count") or 0) for row in rows),
        "total_level_interpolated_count": sum(int(row.get("level_interpolated_count") or 0) for row in rows),
        "total_inflow_dropped_rows": sum(int(row.get("rows_dropped_due_to_missing_inflow") or 0) for row in rows),
        "invalid_time_axis_events": sum(1 for row in rows if str(row.get("valid_time_axis")).lower() not in {"true", "1"}),
    }


def write_dataset_freeze_report(
    *,
    manifest_path: str | Path,
    output_path: str | Path,
) -> Path:
    rows = load_manifest_rows(manifest_path)
    strict_clean = [row["event_id"] for row in rows if row["event_class"] == "strict_clean"]
    repaired = [row["event_id"] for row in rows if row["event_class"] == "repaired_executable"]
    summary = build_dataset_quality_summary(manifest_path)
    lines = [
        "# Dataset Freeze Report",
        "",
        f"- Total events: {summary['total_events']}",
        f"- Strict clean: {summary['strict_clean_count']}",
        f"- Repaired executable: {summary['repaired_executable_count']}",
        f"- Diagnostic only: {summary['diagnostic_only_count']}",
        "",
        "## Repair Policy",
        "",
        "- Missing outflow is repaired by inflow fallback.",
        "- Missing inflow rows are dropped.",
        "- Missing level values are repaired by time-axis linear interpolation.",
        "- Events stay `strict_clean` only when no repair was applied.",
        "- Events with successful repair and valid time axis become `repaired_executable`.",
        "",
        "## Strict Clean Events",
        "",
        ", ".join(strict_clean) if strict_clean else "None.",
        "",
        "## Repaired Executable Events",
        "",
        ", ".join(repaired) if repaired else "None.",
        "",
    ]
    return write_markdown(output_path, "\n".join(lines))


def write_dataset_quality_table(
    *,
    manifest_path: str | Path,
    output_path: str | Path,
) -> Path:
    summary = build_dataset_quality_summary(manifest_path)
    resolved = Path(output_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([summary]).to_csv(resolved, index=False, encoding="utf-8-sig")
    return resolved
