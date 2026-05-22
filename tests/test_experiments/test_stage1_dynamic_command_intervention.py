"""Tests for Stage 1 dynamic command-intervention extension."""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock

import pytest

from experiments.stage1.dynamic_command_intervention import (
    CHECKPOINT_LABELS,
    COMMAND_TYPES,
    EXTENSION_TYPE,
    SELECTED_EVENTS,
    D1_RELEASE_CAP_M3S,
    D1_RELEASE_CAP_MODERATE_M3S,
    D2_TARGET_DELTA_M,
    D3_NEW_DEADLINE_H,
    D4_FLOOD_LIMIT_BUFFER_M,
    CheckpointState,
    CommandSpec,
    make_config_hash,
    _failure_row,
    build_command,
    check_d1_feasibility,
    check_d2_feasibility,
    check_d3_feasibility,
    check_d4_feasibility,
)


def test_extension_type():
    assert EXTENSION_TYPE == "dynamic_command_intervention"


def test_selected_events_count():
    assert len(SELECTED_EVENTS) == 5


def test_command_types_count():
    assert len(COMMAND_TYPES) == 4


def test_checkpoint_labels():
    assert CHECKPOINT_LABELS == ["T1", "T2_peak"]


def test_command_types_names():
    assert "D1_release_cap_adjustment" in COMMAND_TYPES
    assert "D2_terminal_target_lowering" in COMMAND_TYPES
    assert "D3_target_deadline_compression" in COMMAND_TYPES
    assert "D4_conservative_risk_buffer" in COMMAND_TYPES


def test_config_hash_length():
    h = make_config_hash("2024061623", "T1", "D1_release_cap_adjustment", {"level_max": 160.0})
    assert len(h) == 12


def test_config_hash_deterministic():
    h1 = make_config_hash("2024061623", "T1", "D1_release_cap_adjustment", {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "T1", "D1_release_cap_adjustment", {"level_max": 160.0})
    assert h1 == h2


def test_config_hash_sensitive_to_command_type():
    h1 = make_config_hash("2024061623", "T1", "D1_release_cap_adjustment", {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "T1", "D2_terminal_target_lowering", {"level_max": 160.0})
    assert h1 != h2


def test_config_hash_sensitive_to_checkpoint():
    h1 = make_config_hash("2024061623", "T1", "D1_release_cap_adjustment", {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "T2_peak", "D1_release_cap_adjustment", {"level_max": 160.0})
    assert h1 != h2


def test_failure_row_required_keys():
    row = _failure_row(
        event_id="2024061623",
        checkpoint_id="T1",
        checkpoint_hour=12.0,
        command_type="D1_release_cap_adjustment",
        command_text="test",
        command_parameters={"release_cap_m3s": 1500.0},
        config_hash="abc123",
        failure_reason="test_failure",
        season="test",
        flood_limit=160.0,
        command_handling_success=True,
        feasible_execution_success=False,
        infeasibility_reason="test_infeasible",
    )
    required_keys = [
        "result_id", "config_hash", "event_id", "extension_type",
        "checkpoint_id", "checkpoint_hour", "command_type",
        "command_handling_success", "feasible_execution_success",
        "infeasibility_reason", "failure_reason", "accepted",
        "season", "flood_limit_applied",
    ]
    for key in required_keys:
        assert key in row, f"Missing key: {key}"


def test_failure_row_infeasible_rejection_is_handling_success():
    row = _failure_row(
        event_id="2024061623",
        checkpoint_id="T1",
        checkpoint_hour=12.0,
        command_type="D1_release_cap_adjustment",
        command_text="test",
        command_parameters={},
        config_hash="abc123",
        failure_reason="command_infeasible_correctly_rejected",
        season="test",
        flood_limit=160.0,
        command_handling_success=True,
        feasible_execution_success=False,
        infeasibility_reason="some reason",
    )
    assert row["command_handling_success"] is True
    assert row["feasible_execution_success"] is False
    assert row["accepted"] is True


def test_failure_row_nan_metrics():
    row = _failure_row(
        event_id="2024061623",
        checkpoint_id="T1",
        checkpoint_hour=float("nan"),
        command_type="D1_release_cap_adjustment",
        command_text="",
        command_parameters={},
        config_hash="abc123",
        failure_reason="load_failed",
        season="",
        flood_limit=float("nan"),
        command_handling_success=False,
        feasible_execution_success=False,
        infeasibility_reason="",
    )
    assert math.isnan(row["max_level"])
    assert math.isnan(row["terminal_level"])


def _make_cp_state(peak_inflow: float = 2000.0, flood_limit: float = 160.0) -> CheckpointState:
    sliced_event = MagicMock()
    sliced_event.time_step_hours = 3.0
    return CheckpointState(
        event_id="2024061623",
        checkpoint_id="T1",
        checkpoint_hour=12.0,
        checkpoint_idx=4,
        sliced_event=sliced_event,
        initial_level=158.0,
        flood_limit=flood_limit,
        season="test",
        peak_inflow=peak_inflow,
        constraints={"level_max": flood_limit, "downstream_flow_limit": 14000.0},
        task_constraints={"target_level": flood_limit, "target_tolerance": 0.5},
    )


def test_build_command_d1_high_inflow():
    cp = _make_cp_state(peak_inflow=3500.0)
    cmd = build_command("D1_release_cap_adjustment", cp)
    assert cmd.command_parameters["release_cap_m3s"] == D1_RELEASE_CAP_M3S


def test_build_command_d1_moderate_inflow():
    cp = _make_cp_state(peak_inflow=2000.0)
    cmd = build_command("D1_release_cap_adjustment", cp)
    assert cmd.command_parameters["release_cap_m3s"] == D1_RELEASE_CAP_MODERATE_M3S


def test_build_command_d2_target():
    cp = _make_cp_state(flood_limit=160.0)
    cmd = build_command("D2_terminal_target_lowering", cp)
    assert abs(cmd.command_parameters["new_target_level_m"] - (160.0 + D2_TARGET_DELTA_M)) < 1e-9


def test_build_command_d3_horizon():
    cp = _make_cp_state()
    cmd = build_command("D3_target_deadline_compression", cp)
    assert cmd.command_parameters["new_deadline_h"] == D3_NEW_DEADLINE_H


def test_build_command_d4_buffer():
    cp = _make_cp_state(flood_limit=160.0)
    cmd = build_command("D4_conservative_risk_buffer", cp)
    assert abs(cmd.command_parameters["buffered_level_max_m"] - (160.0 - D4_FLOOD_LIMIT_BUFFER_M)) < 1e-9


def test_build_command_unknown_raises():
    cp = _make_cp_state()
    with pytest.raises(ValueError):
        build_command("D99_unknown", cp)


def test_d1_feasibility_normal():
    cp = _make_cp_state()
    ok, reason = check_d1_feasibility(cp, 1500.0)
    assert ok is True
    assert reason == ""


def test_d1_feasibility_zero_cap():
    cp = _make_cp_state()
    ok, reason = check_d1_feasibility(cp, 0.0)
    assert ok is False


def test_d1_feasibility_tiny_cap():
    cp = _make_cp_state()
    ok, reason = check_d1_feasibility(cp, 50.0)
    assert ok is False


def test_d2_feasibility_normal():
    cp = _make_cp_state(flood_limit=160.0)
    ok, reason = check_d2_feasibility(cp, 159.5)
    assert ok is True


def test_d2_feasibility_below_dead_storage():
    cp = _make_cp_state(flood_limit=160.0)
    ok, reason = check_d2_feasibility(cp, 120.0)
    assert ok is False


def test_d2_feasibility_above_flood_limit():
    cp = _make_cp_state(flood_limit=160.0)
    ok, reason = check_d2_feasibility(cp, 161.0)
    assert ok is False


def test_d3_feasibility_normal():
    cp = _make_cp_state()
    ok, reason = check_d3_feasibility(cp, 9.0, 160.0)
    assert ok is True


def test_d3_feasibility_zero_steps():
    cp = _make_cp_state()
    ok, reason = check_d3_feasibility(cp, 0.5, 160.0)
    assert ok is False


def test_d4_feasibility_normal():
    cp = _make_cp_state(flood_limit=160.0)
    ok, reason = check_d4_feasibility(cp, 159.7)
    assert ok is True


def test_d4_feasibility_below_initial_level():
    sliced_event = MagicMock()
    sliced_event.time_step_hours = 3.0
    cp_high = CheckpointState(
        event_id="2024061623",
        checkpoint_id="T1",
        checkpoint_hour=12.0,
        checkpoint_idx=4,
        sliced_event=sliced_event,
        initial_level=160.5,
        flood_limit=160.0,
        season="test",
        peak_inflow=2000.0,
        constraints={"level_max": 160.0, "downstream_flow_limit": 14000.0},
        task_constraints={"target_level": 160.0, "target_tolerance": 0.5},
    )
    ok, reason = check_d4_feasibility(cp_high, 159.7)
    assert ok is False
