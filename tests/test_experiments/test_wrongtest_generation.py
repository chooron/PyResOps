"""Tests for forecast-error wrongtest generation (Stage 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from experiments.create_forecast_error_wrongtest import (
    MANIFEST_FIELDS,
    OBSERVED_INFLOW_COLUMN,
    OBSERVED_LEVEL_COLUMN,
    OBSERVED_OUTFLOW_COLUMN,
    PREDICT_COLUMN,
    SELECTED_EVENTS,
    run,
)

WRONGTEST_DIR = Path("data/wrongtest")
MANIFEST_PATH = WRONGTEST_DIR / "wrongtest_manifest.csv"
GATE_PATH = WRONGTEST_DIR / "stage1_gate_result.json"


def _load_manifest() -> pd.DataFrame:
    assert MANIFEST_PATH.exists(), "wrongtest_manifest.csv not found — run Stage 1 first"
    return pd.read_csv(MANIFEST_PATH, encoding="utf-8-sig")


def test_wrongtest_generation_creates_five_files(tmp_path: Path) -> None:
    result = run(
        source_dir=Path("data/withpred"),
        output_dir=tmp_path,
        max_events=5,
        mild=True,
    )
    csv_files = list(tmp_path.glob("*_wrongtest_*.csv"))
    assert len(csv_files) == 5, f"Expected 5 wrongtest CSVs, got {len(csv_files)}"
    assert result["stage1_pass"] is True


def test_wrongtest_does_not_modify_observed_columns(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    manifest = pd.read_csv(tmp_path / "wrongtest_manifest.csv", encoding="utf-8-sig")
    for _, row in manifest.iterrows():
        src = pd.read_csv(row["source_file"], encoding="utf-8-sig")
        src.columns = [c.strip().lstrip("﻿") for c in src.columns]
        out = pd.read_csv(row["wrongtest_file"], encoding="utf-8-sig")
        out.columns = [c.strip().lstrip("﻿") for c in out.columns]
        for col in [OBSERVED_INFLOW_COLUMN, OBSERVED_OUTFLOW_COLUMN, OBSERVED_LEVEL_COLUMN]:
            if col in src.columns:
                pd.testing.assert_series_equal(
                    src[col].reset_index(drop=True),
                    out[col].reset_index(drop=True),
                    check_names=False,
                    obj=f"{row['original_event_id']} column '{col}'",
                )


def test_wrongtest_forecast_column_perturbed(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    manifest = pd.read_csv(tmp_path / "wrongtest_manifest.csv", encoding="utf-8-sig")
    for _, row in manifest.iterrows():
        src = pd.read_csv(row["source_file"], encoding="utf-8-sig")
        src.columns = [c.strip().lstrip("﻿") for c in src.columns]
        out = pd.read_csv(row["wrongtest_file"], encoding="utf-8-sig")
        out.columns = [c.strip().lstrip("﻿") for c in out.columns]
        diff = (src[PREDICT_COLUMN] - out[PREDICT_COLUMN]).abs()
        assert diff.sum() > 0, (
            f"{row['original_event_id']}: predict column was not perturbed"
        )


def test_wrongtest_time_axis_valid(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    for csv_path in sorted(tmp_path.glob("*_wrongtest_*.csv")):
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        df.columns = [c.strip().lstrip("﻿") for c in df.columns]
        times = pd.to_datetime(df["time"])
        diffs = times.diff().dropna()
        assert (diffs > pd.Timedelta(0)).all(), (
            f"{csv_path.name}: time axis is not strictly increasing"
        )
        # time step should be consistent (3h for all withpred events)
        unique_steps = diffs.dt.total_seconds().unique()
        assert len(unique_steps) == 1, (
            f"{csv_path.name}: irregular time steps: {unique_steps}"
        )


def test_wrongtest_manifest_fields(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    manifest = pd.read_csv(tmp_path / "wrongtest_manifest.csv", encoding="utf-8-sig")
    assert len(manifest) == 5
    for field in MANIFEST_FIELDS:
        assert field in manifest.columns, f"Missing manifest field: {field}"
    assert manifest["perturbation_type"].notna().all()
    assert manifest["selection_reason"].notna().all()
    assert manifest["mean_abs_forecast_difference"].gt(0).all()
    assert manifest["mean_relative_forecast_difference"].gt(0).all()
    # 5 distinct events
    assert manifest["original_event_id"].nunique() == 5
    # 5 distinct perturbation types
    assert manifest["perturbation_type"].nunique() == 5


def test_wrongtest_no_negative_forecast(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    for csv_path in sorted(tmp_path.glob("*_wrongtest_*.csv")):
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        df.columns = [c.strip().lstrip("﻿") for c in df.columns]
        assert (df[PREDICT_COLUMN] >= 0).all(), (
            f"{csv_path.name}: negative forecast values found"
        )


def test_stage1_gate_result_written(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    gate_path = tmp_path / "stage1_gate_result.json"
    assert gate_path.exists()
    gates = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gates["stage1_pass"] is True
    assert gates["wrongtest_file_count"] == 5
    assert gates["observed_columns_unchanged"] is True
    assert gates["forecast_missing_count"] == 0


def test_stage2_requires_stage1_pass(tmp_path: Path) -> None:
    """Stage 2 must not run if stage1_gate_result.json is absent or failed."""
    wrongtest_dir = tmp_path / "wrongtest_missing"
    wrongtest_dir.mkdir()
    gate_path = wrongtest_dir / "stage1_gate_result.json"
    # no gate file → should raise
    from experiments.paper_validation.wrongtest_runner import check_stage1_gate
    with pytest.raises(RuntimeError, match="Stage 1"):
        check_stage1_gate(wrongtest_dir)

    # gate file with stage1_pass=False → should raise
    gate_path.write_text(json.dumps({"stage1_pass": False}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Stage 1"):
        check_stage1_gate(wrongtest_dir)

    # gate file with stage1_pass=True → should not raise
    gate_path.write_text(json.dumps({"stage1_pass": True}), encoding="utf-8")
    check_stage1_gate(wrongtest_dir)  # no exception


def test_stage3_requires_stage2_pass(tmp_path: Path) -> None:
    """Stage 3 must not run if stage2_gate_result.json is absent or failed."""
    wrongtest_dir = tmp_path / "wrongtest_s2"
    wrongtest_dir.mkdir()
    gate_path = wrongtest_dir / "stage2_gate_result.json"

    from experiments.paper_validation.wrongtest_runner import check_stage2_gate
    with pytest.raises(RuntimeError, match="Stage 2"):
        check_stage2_gate(wrongtest_dir)

    gate_path.write_text(json.dumps({"stage2_pass": False}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Stage 2"):
        check_stage2_gate(wrongtest_dir)

    gate_path.write_text(json.dumps({"stage2_pass": True}), encoding="utf-8")
    check_stage2_gate(wrongtest_dir)  # no exception


def test_wrongtest_report_generation(tmp_path: Path) -> None:
    run(source_dir=Path("data/withpred"), output_dir=tmp_path, max_events=5, mild=True)
    report = tmp_path / "wrongtest_generation_report.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Stage 1" in text
    assert "perturbation" in text.lower()
    assert "observed inflow" in text.lower() or "predict" in text.lower()
