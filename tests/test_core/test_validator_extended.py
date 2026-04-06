"""Tests for extended constraint validation."""

from datetime import datetime

from pyresops.core import ConstraintValidator
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.result import SimulationResult, StateSnapshot


def _make_result(max_level, min_level, outflows):
    """Helper to create SimulationResult."""
    snapshots = [
        StateSnapshot(
            timestamp=datetime(2024, 7, 1, i, 0, 0),
            level=165.0,
            storage=30.0,
            inflow=8000.0,
            outflow=o,
        )
        for i, o in enumerate(outflows)
    ]
    return SimulationResult(
        program_id="test",
        start_time=datetime(2024, 7, 1, 0, 0, 0),
        end_time=datetime(2024, 7, 1, len(outflows) - 1, 0, 0),
        snapshots=snapshots,
        max_level=max_level,
        min_level=min_level,
        avg_outflow=sum(outflows) / len(outflows) if outflows else 0.0,
    )


class TestFlowConstraints:
    """流量约束测试."""

    def test_flow_max_violation(self):
        constraint = Constraint(
            id="flow_max_1",
            name="最大流量限制",
            constraint_type="flow_max",
            parameters={"max_flow": 9000.0},
        )
        cs = ConstraintSet(constraints=[constraint])
        validator = ConstraintValidator(cs)
        result = _make_result(165.0, 160.0, [8000, 9500, 8500])

        violations = validator.validate_simulation(result)
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "flow_exceeded"
        assert violations[0]["value"] == 9500.0

    def test_flow_min_violation(self):
        constraint = Constraint(
            id="flow_min_1",
            name="最小流量限制",
            constraint_type="flow_min",
            parameters={"min_flow": 5000.0},
        )
        cs = ConstraintSet(constraints=[constraint])
        validator = ConstraintValidator(cs)
        result = _make_result(165.0, 160.0, [8000, 4000, 6000])

        violations = validator.validate_simulation(result)
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "flow_below"

    def test_no_flow_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="fmax", name="", constraint_type="flow_max", parameters={"max_flow": 10000.0}
                ),
                Constraint(
                    id="fmin", name="", constraint_type="flow_min", parameters={"min_flow": 3000.0}
                ),
            ]
        )
        validator = ConstraintValidator(cs)
        result = _make_result(165.0, 160.0, [8000, 7500, 6000])
        assert len(validator.validate_simulation(result)) == 0


class TestWaterSupplyConstraint:
    """供水约束测试."""

    def test_water_supply_violation(self):
        constraint = Constraint(
            id="ws_1",
            name="供水需求",
            constraint_type="water_supply",
            parameters={"demand": 7000.0},
        )
        cs = ConstraintSet(constraints=[constraint])
        validator = ConstraintValidator(cs)
        result = _make_result(165.0, 160.0, [5000, 6000, 5500])

        violations = validator.validate_simulation(result)
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "water_supply_insufficient"


class TestLevelRangeConstraint:
    """水位范围约束测试."""

    def test_level_range_violation(self):
        constraint = Constraint(
            id="lr_1",
            name="水位范围",
            constraint_type="level_range",
            parameters={"min_level": 160.0, "max_level": 172.0},
        )
        cs = ConstraintSet(constraints=[constraint])
        validator = ConstraintValidator(cs)
        result = _make_result(175.0, 158.0, [8000])

        violations = validator.validate_simulation(result)
        assert len(violations) == 1
        assert violations[0]["violation_type"] == "level_range_violated"


class TestStepValidation:
    """逐步约束校核测试."""

    def test_step_level_max(self):
        constraint = Constraint(
            id="slm",
            name="单步最高水位",
            constraint_type="level_max",
            parameters={"max_level": 170.0},
        )
        cs = ConstraintSet(constraints=[constraint])
        validator = ConstraintValidator(cs)

        violations = validator.validate_step(0, level=175.0, inflow=8000.0, outflow=7000.0)
        assert len(violations) == 1
        assert violations[0]["step_index"] == 0

    def test_step_no_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="smax", name="", constraint_type="level_max", parameters={"max_level": 180.0}
                ),
            ]
        )
        validator = ConstraintValidator(cs)
        violations = validator.validate_step(0, level=165.0, inflow=8000.0, outflow=8000.0)
        assert len(violations) == 0
