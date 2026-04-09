"""Registry for constraint evaluators."""

from __future__ import annotations

from collections.abc import Callable

from ..domain.constraint import Constraint
from .base import ConstraintEvaluator

ConstraintEvaluatorFactory = Callable[[Constraint], ConstraintEvaluator]


class ConstraintRegistry:
    """Runtime registry for constraint evaluator factories."""

    def __init__(self) -> None:
        self._factories: dict[str, ConstraintEvaluatorFactory] = {}

    def register(self, constraint_type: str, factory: ConstraintEvaluatorFactory) -> None:
        """Register or replace evaluator factory by type."""
        self._factories[constraint_type] = factory

    def has(self, constraint_type: str) -> bool:
        """Check whether a type is registered."""
        return constraint_type in self._factories

    def create(self, constraint: Constraint) -> ConstraintEvaluator | None:
        """Create evaluator instance for constraint, if registered."""
        factory = self._factories.get(constraint.constraint_type)
        if not factory:
            return None
        return factory(constraint)

    def list_types(self) -> list[str]:
        """Return sorted registered types."""
        return sorted(self._factories.keys())
