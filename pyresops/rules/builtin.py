"""Built-in rule evaluators and registry helper."""

from __future__ import annotations

from .context import ContextExpressionRuleEvaluator
from .expression import ExpressionRuleEvaluator
from .registry import RuleRegistry


def register_builtin_rules(registry: RuleRegistry) -> None:
    """Register built-in rule evaluators."""
    registry.register("expression", ExpressionRuleEvaluator)
    registry.register("context_expression", ContextExpressionRuleEvaluator)
