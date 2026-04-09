"""Factory utilities for constraint evaluators."""

from __future__ import annotations

from ..domain.constraint import Constraint
from .base import ConstraintEvaluator
from .loader import load_evaluator_class
from .registry import ConstraintRegistry


class ConstraintFactory:
    """Build evaluator instances from constraints and registry."""

    def __init__(self, registry: ConstraintRegistry):
        self.registry = registry

    def create(self, constraint: Constraint) -> ConstraintEvaluator | None:
        """Create evaluator; prefer explicit impl_class when provided."""
        if constraint.impl_class:
            evaluator_class = load_evaluator_class(constraint.impl_class)
            return evaluator_class(constraint)
        return self.registry.create(constraint)
