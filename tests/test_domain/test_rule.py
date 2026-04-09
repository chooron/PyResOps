"""Tests for rule domain helpers."""

from pyresops.domain import DispatchRule, RuleAction, RuleSet


def test_ruleset_enabled_order() -> None:
    rules = RuleSet(
        rules=[
            DispatchRule(id="r1", name="A", priority=10),
            DispatchRule(id="r2", name="B", priority=100),
            DispatchRule(id="r3", name="C", priority=100, enabled=False),
            DispatchRule(id="r0", name="D", priority=100),
        ]
    )

    enabled = rules.enabled_rules()
    ids = [item.id for item in enabled]
    assert ids == ["r0", "r2", "r1"]


def test_rule_action_defaults() -> None:
    action = RuleAction(action_type="set_target_outflow")
    assert action.parameters == {}
