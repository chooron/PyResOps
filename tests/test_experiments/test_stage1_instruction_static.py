"""Tests for Stage 1 instruction-conditioned static extension."""

from __future__ import annotations

import yaml
import pytest

from experiments.stage1.instruction_static import (
    RELEASE_FAMILIES,
    VALID_OPERATION_INTERVALS_H,
    check_interval_compliance,
    make_config_hash,
    quantize_to_interval,
    validate_operation_interval,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_loads():
    with open("experiments/config/stage1_instruction_static.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config["extension_type"] == "instruction_conditioned_static"
    assert "release_families" in config
    assert "operation_intervals_h" in config


def test_config_contains_all_six_families():
    with open("experiments/config/stage1_instruction_static.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    families = config["release_families"]
    for expected in RELEASE_FAMILIES:
        assert expected in families, f"Missing family: {expected}"


def test_config_operation_intervals():
    with open("experiments/config/stage1_instruction_static.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    intervals = config["operation_intervals_h"]
    assert 6 in intervals
    assert 12 in intervals


# ---------------------------------------------------------------------------
# Event list
# ---------------------------------------------------------------------------

def test_event_list_loads_41_events():
    events = []
    with open("experiments/config/stage1_event_list_41.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            event_id = line.split("|")[0].strip()
            if event_id:
                events.append(event_id)
    assert len(events) == 41


def test_event_list_excludes_pre_impoundment():
    excluded = {"2007081917", "2007100817", "2008073005"}
    events = set()
    with open("experiments/config/stage1_event_list_41.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            event_id = line.split("|")[0].strip()
            if event_id:
                events.add(event_id)
    assert events.isdisjoint(excluded)


# ---------------------------------------------------------------------------
# Release family list
# ---------------------------------------------------------------------------

def test_release_families_contains_all_six():
    expected = {
        "constant_release",
        "inflow_piecewise_constant_release",
        "inflow_linear_release",
        "storage_piecewise_constant_release",
        "storage_nonlinear_release",
        "joint_driven_release",
    }
    assert expected == set(RELEASE_FAMILIES)


# ---------------------------------------------------------------------------
# Operation interval validation
# ---------------------------------------------------------------------------

def test_validate_operation_interval_accepts_valid():
    for v in (3, 6, 12):
        validate_operation_interval(v)  # should not raise


def test_validate_operation_interval_rejects_invalid():
    with pytest.raises(ValueError):
        validate_operation_interval(5)
    with pytest.raises(ValueError):
        validate_operation_interval(0)
    with pytest.raises(ValueError):
        validate_operation_interval(24)


# ---------------------------------------------------------------------------
# Quantize to interval
# ---------------------------------------------------------------------------

def test_quantize_to_interval_k2():
    series = [100.0, 200.0, 300.0, 400.0]
    result = quantize_to_interval(series, k=2)
    assert len(result) == 4
    assert result[0] == pytest.approx(150.0)
    assert result[1] == pytest.approx(150.0)
    assert result[2] == pytest.approx(350.0)
    assert result[3] == pytest.approx(350.0)


def test_quantize_to_interval_k1_passthrough():
    series = [10.0, 20.0, 30.0]
    assert quantize_to_interval(series, k=1) == series


def test_quantize_to_interval_last_block_shorter():
    series = [100.0, 200.0, 300.0]  # 3 elements, k=2 → blocks [0:2] and [2:3]
    result = quantize_to_interval(series, k=2)
    assert len(result) == 3
    assert result[0] == pytest.approx(150.0)
    assert result[1] == pytest.approx(150.0)
    assert result[2] == pytest.approx(300.0)  # last block has only one element


# ---------------------------------------------------------------------------
# Interval compliance checker
# ---------------------------------------------------------------------------

def test_check_interval_compliance_passes_valid():
    # k=2: blocks [150, 150] and [350, 350]
    series = [150.0, 150.0, 350.0, 350.0]
    assert check_interval_compliance(series, k=2) is True


def test_check_interval_compliance_fails_mid_block_change():
    # Second element in first block differs
    series = [150.0, 151.0, 350.0, 350.0]
    assert check_interval_compliance(series, k=2) is False


def test_check_interval_compliance_k1_always_true():
    series = [1.0, 2.0, 3.0, 4.0]
    assert check_interval_compliance(series, k=1) is True


def test_check_interval_compliance_last_block_shorter():
    # k=2, 3 elements: blocks [0:2] and [2:3]
    series = [100.0, 100.0, 999.0]
    assert check_interval_compliance(series, k=2) is True


def test_check_interval_compliance_quantized_output():
    series = [100.0, 200.0, 300.0, 400.0]
    quantized = quantize_to_interval(series, k=2)
    assert check_interval_compliance(quantized, k=2) is True


# ---------------------------------------------------------------------------
# Config hash
# ---------------------------------------------------------------------------

def test_make_config_hash_deterministic():
    h1 = make_config_hash("2024061623", "constant_release", 6, {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "constant_release", 6, {"level_max": 160.0})
    assert h1 == h2


def test_make_config_hash_differs_by_family():
    h1 = make_config_hash("2024061623", "constant_release", 6, {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "joint_driven_release", 6, {"level_max": 160.0})
    assert h1 != h2


def test_make_config_hash_differs_by_interval():
    h1 = make_config_hash("2024061623", "constant_release", 6, {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "constant_release", 12, {"level_max": 160.0})
    assert h1 != h2


def test_make_config_hash_differs_by_constraints():
    h1 = make_config_hash("2024061623", "constant_release", 6, {"level_max": 160.0})
    h2 = make_config_hash("2024061623", "constant_release", 6, {"level_max": 156.5})
    assert h1 != h2


def test_make_config_hash_length():
    h = make_config_hash("2024061623", "constant_release", 6, {})
    assert len(h) == 12


# ---------------------------------------------------------------------------
# Result schema (smoke — requires data)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "result_id", "config_hash", "event_id", "scenario_type", "workflow_type",
    "extension_type", "specified_release_family", "actual_release_family",
    "command_compliance", "operation_interval_h", "interval_compliance",
    "accepted", "hard_violation", "max_level", "terminal_level",
    "terminal_deviation", "peak_inflow", "peak_release",
    "inflow_peak_attenuation_rate", "routing_max_flow_hecheng",
    "downstream_violation", "downstream_margin", "optimization_score",
    "season", "flood_limit_applied",
}


@pytest.mark.skipif(
    not __import__("pathlib").Path("data/flood_event/2024061623.csv").exists(),
    reason="flood event data not available",
)
def test_result_row_contains_required_fields():
    from experiments.stage1.instruction_static import InstructionStaticRunner
    runner = InstructionStaticRunner(data_root="data")
    row = runner.run_instruction_static("2024061623", "constant_release", 6)
    for field in REQUIRED_FIELDS:
        assert field in row, f"Missing field: {field}"


@pytest.mark.skipif(
    not __import__("pathlib").Path("data/flood_event/2024061623.csv").exists(),
    reason="flood event data not available",
)
def test_result_extension_type():
    from experiments.stage1.instruction_static import InstructionStaticRunner
    runner = InstructionStaticRunner(data_root="data")
    row = runner.run_instruction_static("2024061623", "constant_release", 6)
    assert row["extension_type"] == "instruction_conditioned_static"
    assert row["workflow_type"] == "stage1_direct_service"
    assert row["specified_release_family"] == "constant_release"
    assert row["operation_interval_h"] == 6
