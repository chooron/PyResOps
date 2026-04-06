"""Tests for constraint validator."""

from datetime import datetime

from pyresops.core import ConstraintValidator
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.result import SimulationResult, StateSnapshot


def test_constraint_validator_level_max():
    """测试最高水位约束."""
    constraint = Constraint(
        id="level_max_test",
        name="最高水位限制",
        constraint_type="level_max",
        parameters={"max_level": 170.0},
    )

    constraint_set = ConstraintSet(constraints=[constraint])
    validator = ConstraintValidator(constraint_set)

    # 创建仿真结果 (违反约束)
    result = SimulationResult(
        program_id="test",
        start_time=datetime(2024, 7, 1, 0, 0, 0),
        end_time=datetime(2024, 7, 1, 1, 0, 0),
        snapshots=[
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, 0, 0, 0),
                level=175.0,
                storage=30.0,
                inflow=8000.0,
                outflow=8000.0,
            )
        ],
        max_level=175.0,
        min_level=165.0,
        avg_outflow=8000.0,
    )

    violations = validator.validate_simulation(result)

    assert len(violations) == 1
    assert violations[0]["constraint_id"] == "level_max_test"
    assert violations[0]["violation_type"] == "level_exceeded"


def test_constraint_validator_level_min():
    """测试最低水位约束."""
    constraint = Constraint(
        id="level_min_test",
        name="最低水位限制",
        constraint_type="level_min",
        parameters={"min_level": 160.0},
    )

    constraint_set = ConstraintSet(constraints=[constraint])
    validator = ConstraintValidator(constraint_set)

    # 创建仿真结果 (违反约束)
    result = SimulationResult(
        program_id="test",
        start_time=datetime(2024, 7, 1, 0, 0, 0),
        end_time=datetime(2024, 7, 1, 1, 0, 0),
        snapshots=[],
        max_level=165.0,
        min_level=155.0,
        avg_outflow=8000.0,
    )

    violations = validator.validate_simulation(result)

    assert len(violations) == 1
    assert violations[0]["constraint_id"] == "level_min_test"
