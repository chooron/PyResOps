"""Rule evaluator protocol and base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.policy import ExecutionContext
from ..domain.rule import DispatchRule, RuleAction


class RuleEvaluator(ABC):
    """Pluggable evaluator for one dispatch rule.

    Minimal custom evaluator template:

    ```python
    from pyresops.rules.base import RuleEvaluator


    class MyRule(RuleEvaluator):
        def match(self, context):
            return context.inflow > 10000
    ```
    """

    def __init__(self, rule: DispatchRule):
        self.rule = rule

    @abstractmethod
    def match(self, context: ExecutionContext) -> bool:
        """Return whether rule matches current context."""

    def produce_actions(self, context: ExecutionContext) -> list[RuleAction]:
        """Produce actions for matched rule."""
        return list(self.rule.actions)
