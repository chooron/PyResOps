"""Expression-based rule evaluator."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..domain.policy import ExecutionContext
from ..domain.rule import DispatchRule
from .base import RuleEvaluator


def _resolve_path(context: ExecutionContext, path: str) -> Any:
    """Resolve dotted path like `state.level` from execution context."""
    tokens = path.split(".")
    if not tokens:
        return None

    root = tokens[0]
    if root == "state":
        value: Any = context.state
    elif root == "forecast":
        value = context.forecast
    elif root == "history":
        value = context.history
    elif root == "directives":
        value = context.directives
    elif root == "step":
        value = {"index": context.step_index}
    elif root == "inflow":
        value = context.inflow
    elif root == "proposed_outflow":
        value = context.proposed_outflow
    else:
        return None

    for token in tokens[1:]:
        if isinstance(value, dict):
            value = value.get(token)
        else:
            value = getattr(value, token, None)
        if value is None:
            return None
    return value


def _evaluate_predicate(node: dict[str, Any], context: ExecutionContext) -> bool:
    """Evaluate one boolean predicate node."""
    op = str(node.get("op", "eq"))

    if op == "all":
        return all(_evaluate_predicate(item, context) for item in node.get("items", []))
    if op == "any":
        return any(_evaluate_predicate(item, context) for item in node.get("items", []))
    if op == "not":
        return not _evaluate_predicate(node.get("item", {}), context)

    left = _resolve_path(context, str(node.get("left", "")))
    right = node.get("right")

    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "gt":
        return left is not None and left > right
    if op == "gte":
        return left is not None and left >= right
    if op == "lt":
        return left is not None and left < right
    if op == "lte":
        return left is not None and left <= right
    if op == "in":
        return left in right if isinstance(right, Sequence) else False

    return False


class ExpressionRuleEvaluator(RuleEvaluator):
    """Rule evaluator using simple dict-AST expressions."""

    def __init__(self, rule: DispatchRule):
        super().__init__(rule)

    def match(self, context: ExecutionContext) -> bool:
        condition = self.rule.condition
        if not condition:
            return False
        return _evaluate_predicate(condition, context)
