"""Tests for Stage 2 dynamic command-intervention workflow and comparator."""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from experiments.stage2.dynamic_command_intervention_workflow import (
    DynamicCommandInterventionComparator,
    _ALIGN_KEYS,
    _TOL_MAX_LEVEL,
    _TOL_TERMINAL_DEV,
    _TOL_PEAK_ATTENUATION,
)


# ---------------------------------------------------------------------------
# Comparator alignment
# ---------------------------------------------------------------------------

def _make_s2_row(
    event_id="2024061623",
    checkpoint_id="T1",
    command_type="D1_release_cap_adjustment",
    command_handling_success=True,
    feasible_execution_success=True,
    max_level=159.0,
    terminal_deviation=0.3,
    inflow_peak_attenuation_rate=0.25,
):
    return {
        "event_id": event_id,
        "checkpoint_id": checkpoint_id,
        "command_type": command_type,
        "command_handling_success": command_handling_success,
        "feasible_execution_success": feasible_execution_success,
        "max_level": max_level,
        "terminal_deviation": terminal_deviation,
        "inflow_peak_attenuation_rate": inflow_peak_attenuation_rate,
    }


def _make_oracle_df(rows):
    return pd.DataFrame(rows)


def test_comparator_passes_oracle_when_matching(tmp_path):
    oracle_row = _make_s2_row()
    oracle_df = _make_oracle_df([oracle_row])
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [_make_s2_row()]
    result = comparator.compare(s2_rows)

    assert len(result) == 1
    assert result.iloc[0]["passes_oracle"] == True


def test_comparator_fails_when_handling_mismatch(tmp_path):
    oracle_row = _make_s2_row(command_handling_success=True)
    oracle_df = _make_oracle_df([oracle_row])
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [_make_s2_row(command_handling_success=False)]
    result = comparator.compare(s2_rows)

    assert result.iloc[0]["passes_oracle"] == False
    assert result.iloc[0]["handling_match"] == False


def test_comparator_fails_when_execution_mismatch(tmp_path):
    oracle_row = _make_s2_row(feasible_execution_success=True)
    oracle_df = _make_oracle_df([oracle_row])
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [_make_s2_row(feasible_execution_success=False)]
    result = comparator.compare(s2_rows)

    assert result.iloc[0]["passes_oracle"] == False
    assert result.iloc[0]["execution_match"] == False


def test_comparator_fails_when_max_level_outside_tolerance(tmp_path):
    oracle_row = _make_s2_row(max_level=159.0)
    oracle_df = _make_oracle_df([oracle_row])
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [_make_s2_row(max_level=159.0 + _TOL_MAX_LEVEL + 0.1)]
    result = comparator.compare(s2_rows)

    assert result.iloc[0]["passes_oracle"] == False
    assert result.iloc[0]["max_level_within_tol"] == False


def test_comparator_passes_when_max_level_within_tolerance(tmp_path):
    oracle_row = _make_s2_row(max_level=159.0)
    oracle_df = _make_oracle_df([oracle_row])
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [_make_s2_row(max_level=159.0 + _TOL_MAX_LEVEL - 0.01)]
    result = comparator.compare(s2_rows)

    assert result.iloc[0]["max_level_within_tol"] == True


def test_comparator_skips_metric_check_when_infeasible(tmp_path):
    oracle_row = _make_s2_row(
        feasible_execution_success=False,
        max_level=float("nan"),
        terminal_deviation=float("nan"),
        inflow_peak_attenuation_rate=float("nan"),
    )
    oracle_df = _make_oracle_df([oracle_row])
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [_make_s2_row(
        feasible_execution_success=False,
        max_level=float("nan"),
        terminal_deviation=float("nan"),
        inflow_peak_attenuation_rate=float("nan"),
    )]
    result = comparator.compare(s2_rows)

    assert result.iloc[0]["execution_match"] == True
    assert result.iloc[0]["max_level_within_tol"] == True


def test_comparator_align_keys():
    assert _ALIGN_KEYS == ["event_id", "checkpoint_id", "command_type"]


def test_comparator_tolerances():
    assert _TOL_MAX_LEVEL == 0.5
    assert _TOL_TERMINAL_DEV == 0.5
    assert _TOL_PEAK_ATTENUATION == 0.05


def test_comparator_no_oracle_raises(tmp_path):
    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        comparator.load_oracle()


def test_comparator_multiple_rows(tmp_path):
    oracle_rows = [
        _make_s2_row(event_id="2024061623", checkpoint_id="T1",
                     command_type="D1_release_cap_adjustment"),
        _make_s2_row(event_id="2024061623", checkpoint_id="T2_peak",
                     command_type="D2_terminal_target_lowering"),
    ]
    oracle_df = _make_oracle_df(oracle_rows)
    oracle_df.to_csv(tmp_path / "results.csv", index=False)

    comparator = DynamicCommandInterventionComparator(oracle_dir=tmp_path)
    s2_rows = [
        _make_s2_row(event_id="2024061623", checkpoint_id="T1",
                     command_type="D1_release_cap_adjustment"),
        _make_s2_row(event_id="2024061623", checkpoint_id="T2_peak",
                     command_type="D2_terminal_target_lowering"),
    ]
    result = comparator.compare(s2_rows)

    assert len(result) == 2
    assert result["passes_oracle"].all()
