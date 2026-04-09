"""Factory utilities for rule evaluators."""

from __future__ import annotations

from ..domain.rule import DispatchRule
from .base import RuleEvaluator
from .loader import load_rule_evaluator_class
from .registry import RuleRegistry


class RuleFactory:
    """Build evaluator instances from rules and registry."""

    def __init__(self, registry: RuleRegistry):
        self.registry = registry

    def create(self, rule: DispatchRule) -> RuleEvaluator | None:
        """Create evaluator; prefer explicit impl_class when provided."""
        if rule.impl_class:
            evaluator_class = load_rule_evaluator_class(rule.impl_class)
            return evaluator_class(rule)
        return self.registry.create(rule)
