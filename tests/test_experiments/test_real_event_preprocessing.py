from __future__ import annotations

from pathlib import Path

import pandas as pd

from experiments.data_adapters import RealEventDataAdapter
from experiments.data_adapters.preprocessing import (
    preprocess_flood_event_directory,
    preprocess_flood_event_file,
)
from experiments.validation import JsonlResultLogger
from experiments.validation.reporting import export_summary_report
from experiments.validation.runner import run_case
from experiments.validation.scenarios import ScenarioCase
from experiments.workflows import StaticRealDataWorkflow


def test_outflow_missing_filled_by_inflow(tmp_path) -> None:
    raw_path = _write_event_csv(
        tmp_path / "raw" / "event_a.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": None},
            {"time": "2024-01-01 03:00", "prcp": 1.0, "level": 150.1, "inflow": 120.0, "outflow": 110.0},
            {"time": "2024-01-01 06:00", "prcp": 0.5, "level": 150.2, "inflow": 140.0, "outflow": 130.0},
        ],
    )

    result = preprocess_flood_event_file(raw_path=raw_path, output_dir=tmp_path / "processed")
    processed = pd.read_csv(tmp_path / "processed" / "event_a.csv", encoding="utf-8-sig")

    assert processed.loc[0, "outflow"] == 100.0
    assert bool(processed.loc[0, "outflow_filled_by_inflow"]) is True
    assert result.strict_clean_eligible is False
    assert result.repaired_executable_eligible is True
    assert result.outflow_filled_by_inflow_count == 1


def test_inflow_missing_row_dropped(tmp_path) -> None:
    raw_path = _write_event_csv(
        tmp_path / "raw" / "event_b.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": 90.0},
            {"time": "2024-01-01 03:00", "prcp": 1.0, "level": 150.1, "inflow": 120.0, "outflow": 95.0},
            {"time": "2024-01-01 06:00", "prcp": 0.5, "level": 150.2, "inflow": 140.0, "outflow": 130.0},
            {"time": "2024-01-01 09:00", "prcp": 0.2, "level": 150.3, "inflow": None, "outflow": 140.0},
        ],
    )

    result = preprocess_flood_event_file(raw_path=raw_path, output_dir=tmp_path / "processed")
    processed = pd.read_csv(tmp_path / "processed" / "event_b.csv", encoding="utf-8-sig")

    assert len(processed) == 3
    assert result.rows_dropped_due_to_missing_inflow == 1
    assert result.inflow_drop_applied is True
    assert result.repaired_executable_eligible is True


def test_inflow_drop_invalidates_time_axis(tmp_path) -> None:
    raw_path = _write_event_csv(
        tmp_path / "raw" / "event_c.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": 90.0},
            {"time": "2024-01-01 03:00", "prcp": 1.0, "level": 150.1, "inflow": None, "outflow": 95.0},
            {"time": "2024-01-01 06:00", "prcp": 0.5, "level": 150.2, "inflow": 140.0, "outflow": 130.0},
        ],
    )

    result = preprocess_flood_event_file(raw_path=raw_path, output_dir=tmp_path / "processed")

    assert result.valid_time_axis is False
    assert result.event_class == "diagnostic_only"
    assert result.diagnostic_only is True


def test_strict_clean_event_unchanged(tmp_path) -> None:
    raw_path = _write_event_csv(
        tmp_path / "raw" / "event_d.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": 90.0},
            {"time": "2024-01-01 03:00", "prcp": 1.0, "level": 150.1, "inflow": 120.0, "outflow": 110.0},
            {"time": "2024-01-01 06:00", "prcp": 0.5, "level": 150.2, "inflow": 140.0, "outflow": 130.0},
        ],
    )

    result = preprocess_flood_event_file(raw_path=raw_path, output_dir=tmp_path / "processed")
    processed = pd.read_csv(tmp_path / "processed" / "event_d.csv", encoding="utf-8-sig")

    assert result.raw_row_count == result.processed_row_count == 3
    assert result.strict_clean_eligible is True
    assert list(processed.columns) == [
        "time",
        "prcp",
        "level",
        "inflow",
        "outflow",
        "outflow_filled_by_inflow",
        "level_filled_by_interpolation",
        "source_event_id",
        "preprocessing_version",
    ]


def test_level_missing_filled_by_linear_interpolation(tmp_path) -> None:
    raw_path = _write_event_csv(
        tmp_path / "raw" / "event_e.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": 90.0},
            {"time": "2024-01-01 03:00", "prcp": 1.0, "level": None, "inflow": 120.0, "outflow": 110.0},
            {"time": "2024-01-01 06:00", "prcp": 0.5, "level": 150.2, "inflow": 140.0, "outflow": 130.0},
        ],
    )

    result = preprocess_flood_event_file(raw_path=raw_path, output_dir=tmp_path / "processed")
    processed = pd.read_csv(tmp_path / "processed" / "event_e.csv", encoding="utf-8-sig")

    assert processed.loc[1, "level"] == 150.1
    assert bool(processed.loc[1, "level_filled_by_interpolation"]) is True
    assert result.level_interpolated_count == 1
    assert result.strict_clean_eligible is False
    assert result.repaired_executable_eligible is True


def test_validation_uses_processed_file(tmp_path) -> None:
    data_root = tmp_path / "data"
    flood_event_dir = data_root / "flood_event"
    manifest_path = tmp_path / "event_quality_manifest.csv"

    _write_event_csv(
        flood_event_dir / "strict_event.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 10.0, "outflow": 9.0},
            {"time": "2024-01-01 03:00", "prcp": 0.0, "level": 150.1, "inflow": 11.0, "outflow": 10.0},
            {"time": "2024-01-01 06:00", "prcp": 0.0, "level": 150.2, "inflow": 12.0, "outflow": 11.0},
        ],
    )
    _write_event_csv(
        flood_event_dir / "repaired_event.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": None},
            {"time": "2024-01-01 03:00", "prcp": 0.0, "level": 150.1, "inflow": 110.0, "outflow": 100.0},
            {"time": "2024-01-01 06:00", "prcp": 0.0, "level": 150.2, "inflow": 120.0, "outflow": 110.0},
        ],
    )
    _write_event_csv(
        flood_event_dir / "diagnostic_event.csv",
        [
            {"time": "2024-01-01 00:00", "prcp": 0.0, "level": 150.0, "inflow": 100.0, "outflow": 90.0},
            {"time": "2024-01-01 03:00", "prcp": 0.0, "level": 150.1, "inflow": None, "outflow": 95.0},
            {"time": "2024-01-01 06:00", "prcp": 0.0, "level": 150.2, "inflow": 120.0, "outflow": 110.0},
        ],
    )
    rows = preprocess_flood_event_directory(
        input_dir=flood_event_dir,
        output_dir=data_root / "processed" / "flood_event",
        manifest_path=manifest_path,
    )

    processed_strict = pd.read_csv(
        data_root / "processed" / "flood_event" / "strict_event.csv",
        encoding="utf-8-sig",
    )
    processed_strict.loc[:, "inflow"] = [310.0, 320.0, 330.0]
    processed_strict.to_csv(
        data_root / "processed" / "flood_event" / "strict_event.csv",
        index=False,
        encoding="utf-8-sig",
    )

    adapter = RealEventDataAdapter(data_root=data_root, quality_manifest_path=manifest_path)
    loaded = adapter.load_event("strict_event")
    prepared = StaticRealDataWorkflow(adapter).prepare("strict_event")

    assert loaded.source_path == data_root / "processed" / "flood_event" / "strict_event.csv"
    assert prepared.stages[0].payload["benchmark_inflow_series_m3s"][0] == 310.0
    assert prepared.stages[0].payload["data_source"]["uses_processed_data"] is True

    logger = JsonlResultLogger(tmp_path / "runs.jsonl")
    strict_records = run_case(
        scenario_set="large_validation",
        case=ScenarioCase(
            scenario_group="s1",
            workflow_type="static",
            event="strict_event",
            method_id="tools_only",
        ),
        cfg={},
        adapter=adapter,
        logger=logger,
        run_id="test_run",
        llm_config="experiments/config/llm_config.yml",
        model_profile=None,
        max_attempts=1,
    )
    repaired_records = run_case(
        scenario_set="large_validation",
        case=ScenarioCase(
            scenario_group="s1",
            workflow_type="static",
            event="repaired_event",
            method_id="tools_only",
        ),
        cfg={},
        adapter=adapter,
        logger=logger,
        run_id="test_run",
        llm_config="experiments/config/llm_config.yml",
        model_profile=None,
        max_attempts=1,
    )
    diagnostic_records = run_case(
        scenario_set="large_validation",
        case=ScenarioCase(
            scenario_group="s1",
            workflow_type="static",
            event="diagnostic_event",
            method_id="tools_only",
        ),
        cfg={},
        adapter=adapter,
        logger=logger,
        run_id="test_run",
        llm_config="experiments/config/llm_config.yml",
        model_profile=None,
        max_attempts=1,
    )
    report = export_summary_report(
        tmp_path / "runs.jsonl",
        markdown_path=tmp_path / "summary.md",
        csv_path=tmp_path / "summary.csv",
    )

    assert len(rows) == 3
    assert strict_records[0]["payload_summary"]["source_path"].endswith(
        "data/processed/flood_event/strict_event.csv"
    )
    assert strict_records[0]["payload_summary"]["uses_processed_data"] is True
    assert repaired_records[0]["event_class"] == "repaired_executable"
    assert diagnostic_records[0]["event_class"] == "diagnostic_only"
    assert report["summary"]["raw_all_events"] == 3
    assert report["summary"]["strict_clean_set"] == 1
    assert report["summary"]["repaired_executable_set"] == 1
    assert report["summary"]["diagnostic_only_count"] == 1


def _write_event_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path
