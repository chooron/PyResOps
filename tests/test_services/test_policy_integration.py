"""Service-level integration tests for policy bundle execution."""

from datetime import datetime

from pyresops.domain import (
    Constraint,
    ConstraintSet,
    DispatchRule,
    PolicyBundle,
    RuleAction,
    RuleSet,
    TimeHorizon,
)
from pyresops.services import ProgramService, SimulationService


def test_simulation_service_with_policy_bundle(
    sample_reservoir_spec,
    sample_initial_state,
    sample_forecast,
) -> None:
    program_service = ProgramService()
    simulation_service = SimulationService(
        sample_reservoir_spec, program_service.get_module_registry()
    )

    program = program_service.create_program(
        name="policy_test",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_configs=[{"module_type": "constant_release", "parameters": {"target_flow": 7000.0}}],
    )

    policy = PolicyBundle(
        constraints=ConstraintSet(
            constraints=[
                Constraint(
                    id="fmax",
                    name="Flow max",
                    constraint_type="flow_max",
                    parameters={"max_flow": 6500.0},
                    scope="step",
                )
            ]
        ),
        rules=RuleSet(
            rules=[
                DispatchRule(
                    id="set_outflow",
                    name="set",
                    condition={"op": "all", "items": []},
                    actions=[
                        RuleAction(action_type="set_target_outflow", parameters={"value": 7000.0})
                    ],
                )
            ]
        ),
    )

    result = simulation_service.run_simulation(
        program,
        sample_initial_state,
        sample_forecast,
        policy_bundle=policy,
    )

    assert result.metadata.get("decision_trace")
    assert all(snapshot.outflow <= 6500.0 for snapshot in result.snapshots)
