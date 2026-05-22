"""Tests for Stage 2 instruction-conditioned static extension comparator."""

from __future__ import annotations

import pytest

from experiments.stage2.instruction_static_workflow import InstructionStaticComparator


def _make_row(
    event_id: str,
    family: str,
    interval_h: int,
    accepted: bool = True,
    max_level: float = 158.0,
    terminal_deviation: float = 0.3,
    peak_reduction_rate: float = 0.25,
    command_compliance: bool = True,
    interval_compliance: bool = True,
) -> dict:
    return {
        "event_id": event_id,
        "specified_release_family": family,
        "operation_interval_h": interval_h,
        "accepted": accepted,
        "max_level": max_level,
        "terminal_deviation": terminal_deviation,
        "peak_reduction_rate": peak_reduction_rate,
        "command_compliance": command_compliance,
        "interval_compliance": interval_compliance,
    }


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def test_comparator_aligns_by_three_keys():
    s1_rows = [_make_row("2024061623", "constant_release", 6)]
    s2_rows = [_make_row("2024061623", "constant_release", 6)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["matched_rows"] == 1
    assert result["missing_in_s2"] == 0
    assert result["extra_in_s2"] == 0


def test_comparator_different_interval_not_matched():
    s1_rows = [_make_row("2024061623", "constant_release", 6)]
    s2_rows = [_make_row("2024061623", "constant_release", 12)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["matched_rows"] == 0
    assert result["missing_in_s2"] == 1
    assert result["extra_in_s2"] == 1


def test_comparator_different_family_not_matched():
    s1_rows = [_make_row("2024061623", "constant_release", 6)]
    s2_rows = [_make_row("2024061623", "joint_driven_release", 6)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["matched_rows"] == 0


# ---------------------------------------------------------------------------
# Missing row detection
# ---------------------------------------------------------------------------

def test_missing_row_detection():
    s1_rows = [
        _make_row("2024061623", "constant_release", 6),
        _make_row("2024061623", "joint_driven_release", 6),
    ]
    s2_rows = [_make_row("2024061623", "constant_release", 6)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["missing_in_s2"] == 1
    assert result["passes_oracle"] is False


# ---------------------------------------------------------------------------
# Tolerance failures
# ---------------------------------------------------------------------------

def test_max_level_tolerance_failure():
    s1_rows = [_make_row("2024061623", "constant_release", 6, max_level=158.0)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, max_level=158.8)]  # diff=0.8 > 0.5
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["max_level_failures"] == 1
    assert result["passes_oracle"] is False


def test_max_level_within_tolerance():
    s1_rows = [_make_row("2024061623", "constant_release", 6, max_level=158.0)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, max_level=158.3)]  # diff=0.3 < 0.5
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["max_level_failures"] == 0


def test_terminal_deviation_tolerance_failure():
    s1_rows = [_make_row("2024061623", "constant_release", 6, terminal_deviation=0.3)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, terminal_deviation=0.9)]  # diff=0.6 > 0.5
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["terminal_deviation_failures"] == 1


def test_peak_reduction_tolerance_failure():
    s1_rows = [_make_row("2024061623", "constant_release", 6, peak_reduction_rate=0.25)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, peak_reduction_rate=0.32)]  # diff=0.07 > 0.05
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["peak_reduction_failures"] == 1


# ---------------------------------------------------------------------------
# Compliance mismatch detection
# ---------------------------------------------------------------------------

def test_command_compliance_mismatch():
    s1_rows = [_make_row("2024061623", "constant_release", 6, command_compliance=True)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, command_compliance=False)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["command_compliance_mismatches"] == 1
    assert result["passes_oracle"] is False


def test_interval_compliance_mismatch():
    s1_rows = [_make_row("2024061623", "constant_release", 6, interval_compliance=True)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, interval_compliance=False)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["interval_compliance_mismatches"] == 1
    assert result["passes_oracle"] is False


# ---------------------------------------------------------------------------
# passes_oracle
# ---------------------------------------------------------------------------

def test_passes_oracle_all_match():
    row = _make_row("2024061623", "constant_release", 6)
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows([row])
    comp._s1 = __import__("pandas").DataFrame([row])
    result = comp.compare()
    assert result["passes_oracle"] is True


def test_passes_oracle_false_on_accepted_mismatch():
    s1_rows = [_make_row("2024061623", "constant_release", 6, accepted=True)]
    s2_rows = [_make_row("2024061623", "constant_release", 6, accepted=False)]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(s2_rows)
    comp._s1 = __import__("pandas").DataFrame(s1_rows)
    result = comp.compare()
    assert result["passes_oracle"] is False


# ---------------------------------------------------------------------------
# Multiple rows
# ---------------------------------------------------------------------------

def test_multiple_rows_all_pass():
    families = ["constant_release", "joint_driven_release"]
    intervals = [6, 12]
    rows = [_make_row("2024061623", f, i) for f in families for i in intervals]
    comp = InstructionStaticComparator()
    comp.load_stage2_from_rows(rows)
    comp._s1 = __import__("pandas").DataFrame(rows)
    result = comp.compare()
    assert result["matched_rows"] == 4
    assert result["passes_oracle"] is True
