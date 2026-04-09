"""Tests for rule registry and factory."""

from pyresops.domain import DispatchRule
from pyresops.rules import RuleFactory, RuleRegistry
from pyresops.rules.base import RuleEvaluator


class _DummyRuleEvaluator(RuleEvaluator):
    def match(self, context):
        return True


def test_rule_registry_factory() -> None:
    registry = RuleRegistry()
    registry.register("dummy", _DummyRuleEvaluator)
    factory = RuleFactory(registry)

    rule = DispatchRule(id="r1", name="rule", metadata={"rule_type": "dummy"})
    evaluator = factory.create(rule)

    assert isinstance(evaluator, _DummyRuleEvaluator)
    assert "dummy" in registry.list_types()
