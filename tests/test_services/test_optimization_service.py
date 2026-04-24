"""Tests for family-oriented release optimization."""

from datetime import datetime, timedelta

from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.policy import PolicyBundle
from pyresops.domain.rule import DispatchRule, RuleAction, RuleSet
from pyresops.services import OptimizationService, ProgramService


def _build_forecast(start: datetime, values: list[float]) -> ForecastBundle:
    timestamps = [start + timedelta(hours=i) for i in range(len(values))]
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


def test_unspecified_family_stops_at_first_feasible(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    forecast = _build_forecast(sample_initial_state.timestamp, [4000.0] * 6)

    result = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 165.0, "target_tolerance": 0.2},
    )

    assert result.selected_candidate.module_type == "constant_release"
    attempted_types = [item["module_type"] for item in result.family_attempts]
    assert attempted_types == ["constant_release"]


def test_explicit_family_evaluates_only_that_family(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    forecast = _build_forecast(sample_initial_state.timestamp, [5000.0, 7000.0, 9000.0, 6000.0])

    result = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 10000.0},
        requested_module_type="inflow_linear_release",
    )

    assert result.selected_candidate.module_type == "inflow_linear_release"
    attempted_types = [item["module_type"] for item in result.family_attempts]
    assert attempted_types == ["inflow_linear_release"]


def test_search_skips_invalid_family_and_continues_to_next_one(
    sample_reservoir_spec,
    sample_initial_state,
    monkeypatch,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    piecewise_cls = service.program_service.get_module_registry()["inflow_piecewise_constant_release"]

    def _raise_invalid(*, context):
        raise ValueError("intentional family failure")

    monkeypatch.setattr(piecewise_cls, "get_optimization_spec", classmethod(lambda cls, *, context: _raise_invalid(context=context)))
    forecast = _build_forecast(
        sample_initial_state.timestamp,
        [1000.0, 1500.0, 2500.0, 4000.0, 6000.0, 8500.0, 11000.0, 13500.0, 15500.0, 17000.0, 17500.0, 17200.0]
        + [500.0] * 8,
    )

    result = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 11085.0, "max_level": 169.15},
        task_constraints={"target_level": 165.87, "target_tolerance": 0.5},
        allowed_module_types=[
            "inflow_piecewise_constant_release",
            "inflow_linear_release",
            "joint_driven_release",
        ],
    )

    assert result.selected_candidate.module_type == "inflow_linear_release"
    assert result.family_attempts[0]["module_type"] == "inflow_piecewise_constant_release"
    assert result.family_attempts[0]["candidate_count"] == 0
    assert "intentional family failure" in result.family_attempts[0]["error"]
    assert result.family_attempts[1]["module_type"] == "inflow_linear_release"


def test_policy_bundle_rules_participate_in_family_search(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    forecast = _build_forecast(sample_initial_state.timestamp, [4000.0] * 12)

    unconstrained = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 164.0, "target_tolerance": 0.2},
        requested_module_type="constant_release",
    )

    policy_bundle = PolicyBundle(
        constraints=ConstraintSet(
            constraints=[
                Constraint(
                    id="flow_max",
                    name="Flow max",
                    constraint_type="flow_max",
                    parameters={"max_flow": 5000.0},
                    scope="both",
                )
            ]
        ),
        rules=RuleSet(
            rules=[
                DispatchRule(
                    id="tight_manual_cap",
                    name="Tight manual cap",
                    condition={"op": "all", "items": []},
                    actions=[
                        RuleAction(
                            action_type="clamp_outflow",
                            parameters={"max": 500.0},
                        )
                    ],
                    priority=1200,
                )
            ]
        ),
        metadata={"source_constraints": {"ecological_min_flow": 50.0, "max_release": 5000.0}},
    )
    constrained = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 164.0, "target_tolerance": 0.2},
        requested_module_type="constant_release",
        policy_bundle=policy_bundle,
    )

    assert unconstrained.selected_candidate.simulation_result.avg_outflow > 500.0
    assert constrained.selected_candidate.simulation_result.avg_outflow <= 500.0
    assert constrained.fallback_applied is True
