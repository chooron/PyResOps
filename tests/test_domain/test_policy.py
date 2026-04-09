"""Tests for policy domain objects."""

from pyresops.domain import (
    Constraint,
    ConstraintSet,
    DispatchRule,
    PolicyBundle,
    RuleAction,
    RuleSet,
)


def test_policy_bundle_roundtrip() -> None:
    policy = PolicyBundle(
        constraints=ConstraintSet(
            constraints=[
                Constraint(
                    id="c1",
                    name="Max flow",
                    constraint_type="flow_max",
                    parameters={"max_flow": 9000.0},
                    scope="step",
                    severity="major",
                    enforcement="hard",
                )
            ]
        ),
        rules=RuleSet(
            rules=[
                DispatchRule(
                    id="r1",
                    name="Clamp",
                    condition={"op": "all", "items": []},
                    actions=[RuleAction(action_type="clamp_outflow", parameters={"max": 8500.0})],
                )
            ]
        ),
        objectives={"target": "safe"},
        directives={"mode": "normal"},
    )

    dumped = policy.model_dump(mode="json")
    restored = PolicyBundle(**dumped)

    assert restored.constraints.constraints[0].constraint_type == "flow_max"
    assert restored.rules.rules[0].actions[0].action_type == "clamp_outflow"


def test_constraint_set_scope_filter() -> None:
    constraint_set = ConstraintSet(
        constraints=[
            Constraint(id="s", name="step", constraint_type="flow_max", scope="step"),
            Constraint(id="g", name="global", constraint_type="flow_min", scope="global"),
            Constraint(id="b", name="both", constraint_type="level_max", scope="both"),
            Constraint(id="d", name="disabled", constraint_type="level_min", enabled=False),
        ]
    )

    step_ids = {item.id for item in constraint_set.get_by_scope("step")}
    global_ids = {item.id for item in constraint_set.get_by_scope("global")}

    assert step_ids == {"s", "b"}
    assert global_ids == {"g", "b"}
