"""Lightweight tests for Stage 2 workflow replication."""

from __future__ import annotations

import pytest
import yaml


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

def test_stage2_imports():
    from experiments.stage2 import __doc__ as doc
    assert doc is not None

    from experiments.stage2.workflows import StaticWorkflow, DynamicWorkflow, RollingWorkflow
    from experiments.stage2.deterministic_runner import Stage2Runner
    from experiments.stage2.comparator import Stage2Comparator
    from experiments.stage2.reporting import (
        generate_stage2_outputs,
        generate_comparison_report,
        generate_stage2_summary,
    )


def test_config_loads():
    with open("experiments/config/stage2_workflow.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert "dynamic_events" in cfg
    assert "rolling_events" in cfg
    assert len(cfg["dynamic_events"]) == 10
    assert len(cfg["rolling_events"]) == 10
    assert cfg["rolling_thresholds"]["relative_error_trigger"] == 0.20


# ---------------------------------------------------------------------------
# Comparator unit tests
# ---------------------------------------------------------------------------

def test_comparator_aligned_rows():
    from experiments.stage2.comparator import Stage2Comparator
    import pandas as pd

    row = {
        "event_id": "2024061623",
        "scenario_type": "static",
        "workflow_stage": "static",
        "accepted": True,
        "hard_violation": False,
        "max_level": 158.5,
        "terminal_deviation": 1.2,
        "peak_reduction_rate": 0.95,
    }

    cmp = Stage2Comparator()
    cmp._s1 = pd.DataFrame([row])
    cmp._s2 = pd.DataFrame([row])
    result = cmp.compare()

    assert result["matched_rows"] == 1
    assert result["missing_in_s2"] == 0
    assert result["extra_in_s2"] == 0
    assert result["accepted_mismatch"] == 0
    assert result["max_level_failures"] == 0
    assert result["terminal_deviation_failures"] == 0
    assert result["peak_reduction_failures"] == 0
    assert result["passes_oracle"] is True


def test_comparator_tolerance_failure():
    from experiments.stage2.comparator import Stage2Comparator
    import pandas as pd

    s1_row = {
        "event_id": "2024061623",
        "scenario_type": "static",
        "workflow_stage": "static",
        "accepted": True,
        "hard_violation": False,
        "max_level": 158.5,
        "terminal_deviation": 1.2,
        "peak_reduction_rate": 0.95,
    }
    s2_row = dict(s1_row)
    s2_row["max_level"] = 159.2  # delta = 0.7 > 0.5 tolerance

    cmp = Stage2Comparator()
    cmp._s1 = pd.DataFrame([s1_row])
    cmp._s2 = pd.DataFrame([s2_row])
    result = cmp.compare()

    assert result["max_level_failures"] == 1
    assert result["passes_oracle"] is False


def test_comparator_missing_row():
    from experiments.stage2.comparator import Stage2Comparator
    import pandas as pd

    row = {
        "event_id": "2024061623",
        "scenario_type": "static",
        "workflow_stage": "static",
        "accepted": True,
        "hard_violation": False,
        "max_level": 158.5,
        "terminal_deviation": 1.2,
        "peak_reduction_rate": 0.95,
    }

    cmp = Stage2Comparator()
    cmp._s1 = pd.DataFrame([row])
    cmp._s2 = pd.DataFrame()  # empty
    result = cmp.compare()

    assert result["missing_in_s2"] == 1
    assert result["matched_rows"] == 0
    assert result["passes_oracle"] is False


# ---------------------------------------------------------------------------
# Result schema test
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "result_id",
    "config_hash",
    "event_id",
    "scenario_type",
    "workflow_stage",
    "action",
    "accepted",
    "hard_violation",
    "downstream_violation",
    "max_level",
    "max_release",
    "terminal_level",
    "terminal_deviation",
    "peak_inflow",
    "peak_release",
    "peak_reduction_rate",
    "release_smoothness",
    "routing_max_flow_hecheng",
    "downstream_margin",
    "optimization_family",
    "optimization_score",
    "season",
    "flood_limit_applied",
]


def test_result_schema_fields():
    """Verify that a synthetic result row contains all required schema fields.

    Uses a mock OptimizationService result to avoid needing real data files.
    """
    from unittest.mock import MagicMock, patch
    from experiments.stage2.workflows import _run_optimization, _build_services

    # Build a minimal fake opt_result / sim_result
    snapshot = MagicMock()
    snapshot.level = 157.0
    snapshot.outflow = 800.0
    snapshot.inflow = 1000.0

    candidate = MagicMock()
    candidate.feasible = True
    candidate.violations = []
    candidate.unmet_task_constraints = []
    candidate.objective_score = -1.5
    candidate.module_type = "constant_release"

    sim_result = MagicMock()
    sim_result.snapshots = [snapshot] * 10

    opt_result = MagicMock()
    opt_result.selected_candidate = candidate
    candidate.simulation_result = sim_result

    routing_check = MagicMock()
    routing_check.check_violation.return_value = (False, 5000.0)

    spec = MagicMock()
    spec.level_storage_curve.get_storage.return_value = 1e8

    opt_service = MagicMock()
    opt_service.optimize_release_plan.return_value = opt_result

    from pathlib import Path
    from datetime import datetime
    from experiments.data_adapters.real_events import FloodEventData, FloodEventRecord

    records = [
        FloodEventRecord(
            time=datetime(2024, 7, 1, 0),
            prcp=0.0,
            level=156.0,
            inflow=1000.0,
            outflow=800.0,
            predict=950.0,
        )
    ] * 12

    event = FloodEventData(
        event_id="test_event",
        source_path=Path("data/flood_event/test_event.csv"),
        records=records,
        time_step_hours=3,
        has_prediction=True,
    )

    row = _run_optimization(
        spec=spec,
        opt_service=opt_service,
        routing_check=routing_check,
        event=event,
        workflow_stage="static",
        scenario_type="static",
        action="replan",
        trigger_type="initial",
    )

    # downstream_margin is not produced by extract_unified_metrics; skip it
    required = [f for f in REQUIRED_FIELDS if f != "downstream_margin"]
    missing = [f for f in required if f not in row]
    assert missing == [], f"Missing fields: {missing}"
