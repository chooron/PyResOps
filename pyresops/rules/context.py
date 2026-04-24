"""Context-aware rule evaluator with enum-based operators."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from ..domain.policy import ExecutionContext
from ..domain.rule import DispatchRule
from .base import RuleEvaluator


class ContextRuleOp(StrEnum):
    ALWAYS = "always"
    ALL = "all"
    ANY = "any"
    NOT = "not"
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"


def resolve_context_path(context: ExecutionContext, path: str) -> Any:
    tokens = str(path).split(".")
    if not tokens or tokens == [""]:
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


def evaluate_context_condition(node: dict[str, Any], context: ExecutionContext) -> bool:
    op = ContextRuleOp(str(node.get("op", ContextRuleOp.EQ)))
    if op is ContextRuleOp.ALWAYS:
        return True
    if op is ContextRuleOp.ALL:
        return all(evaluate_context_condition(item, context) for item in node.get("items", []))
    if op is ContextRuleOp.ANY:
        return any(evaluate_context_condition(item, context) for item in node.get("items", []))
    if op is ContextRuleOp.NOT:
        return not evaluate_context_condition(node.get("item", {}), context)

    left = resolve_context_path(context, str(node.get("left", "")))
    if "right_from" in node:
        right = resolve_context_path(context, str(node["right_from"]))
    else:
        right = node.get("right_value", node.get("right"))

    if op is ContextRuleOp.EQ:
        return left == right
    if op is ContextRuleOp.NE:
        return left != right
    if op is ContextRuleOp.GT:
        return left is not None and right is not None and left > right
    if op is ContextRuleOp.GTE:
        return left is not None and right is not None and left >= right
    if op is ContextRuleOp.LT:
        return left is not None and right is not None and left < right
    if op is ContextRuleOp.LTE:
        return left is not None and right is not None and left <= right
    if op is ContextRuleOp.IN:
        return left in right if isinstance(right, Sequence) and not isinstance(right, (str, bytes)) else False
    return False


class ContextExpressionRuleEvaluator(RuleEvaluator):
    """Evaluate dict-AST predicates against ExecutionContext."""

    def __init__(self, rule: DispatchRule):
        super().__init__(rule)

    def match(self, context: ExecutionContext) -> bool:
        if not self.rule.condition:
            return False
        return evaluate_context_condition(self.rule.condition, context)
