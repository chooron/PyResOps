"""Tests for built-in constraint evaluators."""

from datetime import datetime

from pyresops.constraints import ConstraintFactory, ConstraintRegistry, register_builtin_constraints
from pyresops.domain import Constraint, SimulationResult, StateSnapshot


def _make_result(outflows: list[float]) -> SimulationResult:
    snaps = [
        StateSnapshot(
            timestamp=datetime(2024, 7, 1, i, 0, 0),
            level=165.0,
            storage=30.0,
            inflow=8000.0,
            outflow=value,
        )
        for i, value in enumerate(outflows)
    ]
    return SimulationResult(
        program_id="p",
        start_time=datetime(2024, 7, 1, 0, 0, 0),
        end_time=datetime(2024, 7, 1, len(outflows) - 1, 0, 0),
        snapshots=snaps,
        max_level=max(snapshot.level for snapshot in snaps),
        min_level=min(snapshot.level for snapshot in snaps),
        avg_outflow=sum(outflows) / len(outflows),
    )


def test_builtin_flow_max_constraint() -> None:
    registry = ConstraintRegistry()
    register_builtin_constraints(registry)
    factory = ConstraintFactory(registry)

    constraint = Constraint(
        id="fmax",
        name="Flow max",
        constraint_type="flow_max",
        parameters={"max_flow": 9000.0},
        scope="both",
    )
    evaluator = factory.create(constraint)
    assert evaluator is not None

    result = _make_result([8000.0, 9500.0, 8500.0])
    violations = evaluator.validate_global(result=result)
    assert len(violations) == 1
    assert violations[0].violation_type == "flow_exceeded"


def test_builtin_ramp_rate_constraint_step() -> None:
    registry = ConstraintRegistry()
    register_builtin_constraints(registry)
    factory = ConstraintFactory(registry)
    constraint = Constraint(
        id="ramp",
        name="Ramp",
        constraint_type="ramp_rate_max",
        parameters={"max_ramp": 500.0},
        scope="step",
    )
    evaluator = factory.create(constraint)
    assert evaluator is not None

    violations = evaluator.validate_step(
        step_index=1,
        level=165.0,
        inflow=8000.0,
        outflow=9000.0,
        context={"previous_outflow": 8000.0},
    )
    assert len(violations) == 1
    suggestion = evaluator.suggest_adjustment(
        step_index=1,
        level=165.0,
        inflow=8000.0,
        outflow=9000.0,
        context={"previous_outflow": 8000.0},
    )
    assert suggestion is not None
    assert suggestion["action"] == "clamp_outflow"
