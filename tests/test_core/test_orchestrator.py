"""Tests for policy decision orchestrator."""

from datetime import datetime

from pyresops.core.orchestrator import DecisionOrchestrator
from pyresops.domain import (
    Constraint,
    ConstraintSet,
    DispatchRule,
    PolicyBundle,
    RuleAction,
    RuleSet,
)


def test_orchestrator_rule_and_constraint_adjustment() -> None:
    orchestrator = DecisionOrchestrator()
    policy = PolicyBundle(
        constraints=ConstraintSet(
            constraints=[
                Constraint(
                    id="fmax",
                    name="Flow max",
                    constraint_type="flow_max",
                    parameters={"max_flow": 9000.0},
                    scope="step",
                )
            ]
        ),
        rules=RuleSet(
            rules=[
                DispatchRule(
                    id="r1",
                    name="Set high",
                    condition={"op": "all", "items": []},
                    actions=[
                        RuleAction(action_type="set_target_outflow", parameters={"value": 9500.0})
                    ],
                )
            ]
        ),
    )

    outcome = orchestrator.decide(
        timestamp=datetime(2024, 7, 1, 0, 0, 0),
        step_index=0,
        state_payload={"level": 165.0, "storage": 30.0},
        inflow=8000.0,
        baseline_outflow=8000.0,
        active_module="constant_release",
        policy_bundle=policy,
    )

    assert outcome.outflow == 9000.0
    assert len(outcome.rule_hits) == 1
    assert any(item["source"] == "rule_action" for item in outcome.adjustments)
