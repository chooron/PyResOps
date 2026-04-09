"""Tests for expression-based rule evaluator."""

from pyresops.domain import DispatchRule, ExecutionContext, RuleAction
from pyresops.rules.expression import ExpressionRuleEvaluator


def test_expression_rule_match_and_action() -> None:
    rule = DispatchRule(
        id="r1",
        name="High level clamp",
        condition={"op": "gt", "left": "state.level", "right": 170.0},
        actions=[RuleAction(action_type="clamp_outflow", parameters={"max": 9000.0})],
    )
    evaluator = ExpressionRuleEvaluator(rule)

    ctx = ExecutionContext(
        step_index=0,
        state={"level": 171.0},
        inflow=8000.0,
        proposed_outflow=9500.0,
    )
    assert evaluator.match(ctx)
    actions = evaluator.produce_actions(ctx)
    assert actions[0].action_type == "clamp_outflow"


def test_expression_logical_nodes() -> None:
    rule = DispatchRule(
        id="r2",
        name="Composite",
        condition={
            "op": "all",
            "items": [
                {"op": "gte", "left": "state.level", "right": 160.0},
                {
                    "op": "any",
                    "items": [
                        {"op": "lt", "left": "inflow", "right": 5000.0},
                        {"op": "gt", "left": "inflow", "right": 7000.0},
                    ],
                },
            ],
        },
    )
    evaluator = ExpressionRuleEvaluator(rule)
    ctx = ExecutionContext(
        step_index=1,
        state={"level": 165.0},
        inflow=8001.0,
        proposed_outflow=8000.0,
    )
    assert evaluator.match(ctx)
