"""Extended validator: step constraints, empty snapshots, unknown types."""

from datetime import datetime

from pyresops.core import ConstraintValidator
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.result import SimulationResult, StateSnapshot


def _result(snapshots=None, max_level=165, min_level=160, avg_outflow=8000):
    return SimulationResult(
        program_id="vtest",
        start_time=datetime(2024, 7, 1),
        end_time=datetime(2024, 7, 1, 2, 0, 0),
        snapshots=snapshots or [],
        max_level=max_level,
        min_level=min_level,
        avg_outflow=avg_outflow,
    )


class TestValidatorStepConstraints:
    """单步约束校核"""

    def test_step_level_min_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="level_min", parameters={"min_level": 160.0}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        viols = v.validate_step(0, level=155.0, inflow=8000.0, outflow=8000.0)
        assert len(viols) == 1
        assert viols[0]["violation_type"] == "level_below"
        assert viols[0]["step_index"] == 0

    def test_step_level_min_ok(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="level_min", parameters={"min_level": 160.0}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        assert len(v.validate_step(0, level=165.0, inflow=8000, outflow=8000)) == 0

    def test_step_flow_max_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_max", parameters={"max_flow": 9000.0}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        viols = v.validate_step(0, level=165, inflow=8000, outflow=10000)
        assert len(viols) == 1
        assert viols[0]["violation_type"] == "flow_exceeded"

    def test_step_flow_max_ok(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_max", parameters={"max_flow": 9000.0}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        assert len(v.validate_step(0, level=165, inflow=8000, outflow=8000)) == 0

    def test_step_flow_min_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_min", parameters={"min_flow": 5000.0}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        viols = v.validate_step(0, level=165, inflow=8000, outflow=3000)
        assert len(viols) == 1
        assert viols[0]["violation_type"] == "flow_below"

    def test_step_flow_min_ok(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_min", parameters={"min_flow": 5000.0}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        assert len(v.validate_step(0, level=165, inflow=8000, outflow=6000)) == 0


class TestValidatorEmptySnapshots:
    """空快照全局约束"""

    def test_flow_max_empty_no_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_max", parameters={"max_flow": 100}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        result = _result(snapshots=[])
        assert len(v.validate_simulation(result)) == 0

    def test_flow_min_empty_no_violation(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_min", parameters={"min_flow": 99999}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        result = _result(snapshots=[])
        assert len(v.validate_simulation(result)) == 0


class TestValidatorUnknownType:
    """未知约束类型"""

    def test_unknown_constraint_type_global(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(id="c", name="", constraint_type="totally_unknown", parameters={}),
            ]
        )
        v = ConstraintValidator(cs)
        result = _result(
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1), level=165, storage=30, inflow=8000, outflow=8000
                )
            ],
            max_level=165,
            min_level=165,
        )
        assert len(v.validate_simulation(result)) == 0

    def test_unknown_constraint_type_step(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(id="c", name="", constraint_type="totally_unknown", parameters={}),
            ]
        )
        v = ConstraintValidator(cs)
        assert len(v.validate_step(0, 165, 8000, 8000)) == 0


class TestValidatorGlobalFlowWithSnapshots:
    """有快照时的全局流量约束"""

    def test_flow_max_global_violation(self):
        snaps = [
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, h), level=165, storage=30, inflow=8000, outflow=o
            )
            for h, o in enumerate([5000, 9500, 6000])
        ]
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_max", parameters={"max_flow": 9000}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        viols = v.validate_simulation(_result(snapshots=snaps))
        assert len(viols) == 1
        assert viols[0]["value"] == 9500

    def test_flow_min_global_violation(self):
        snaps = [
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, h), level=165, storage=30, inflow=8000, outflow=o
            )
            for h, o in enumerate([8000, 2000, 7000])
        ]
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="flow_min", parameters={"min_flow": 3000}
                ),
            ]
        )
        v = ConstraintValidator(cs)
        viols = v.validate_simulation(_result(snapshots=snaps))
        assert len(viols) == 1
        assert viols[0]["value"] == 2000
