"""Registry for rule evaluators."""

from __future__ import annotations

from collections.abc import Callable

from ..domain.rule import DispatchRule
from .base import RuleEvaluator

RuleEvaluatorFactory = Callable[[DispatchRule], RuleEvaluator]


class RuleRegistry:
    """Runtime registry for named rule evaluator factories."""

    def __init__(self) -> None:
        self._factories: dict[str, RuleEvaluatorFactory] = {}

    def register(self, rule_type: str, factory: RuleEvaluatorFactory) -> None:
        """Register or replace evaluator factory by type."""
        self._factories[rule_type] = factory

    def create(self, rule: DispatchRule) -> RuleEvaluator | None:
        """Create evaluator instance based on rule metadata type."""
        rule_type = str(rule.metadata.get("rule_type", "expression"))
        factory = self._factories.get(rule_type)
        if not factory:
            return None
        return factory(rule)

    def list_types(self) -> list[str]:
        """Return sorted registered types."""
        return sorted(self._factories.keys())
