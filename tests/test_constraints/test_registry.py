"""Tests for constraint registry and factory."""

from pyresops.constraints import ConstraintFactory, ConstraintRegistry
from pyresops.constraints.base import ConstraintEvaluator
from pyresops.domain import Constraint


class _DummyConstraint(ConstraintEvaluator):
    constraint_type = "dummy"


def test_constraint_registry_and_factory() -> None:
    registry = ConstraintRegistry()
    registry.register("dummy", _DummyConstraint)

    factory = ConstraintFactory(registry)
    evaluator = factory.create(
        Constraint(id="d1", name="dummy", constraint_type="dummy", parameters={})
    )

    assert isinstance(evaluator, _DummyConstraint)
    assert registry.has("dummy")
    assert "dummy" in registry.list_types()
