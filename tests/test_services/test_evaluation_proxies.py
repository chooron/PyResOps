"""Tests for power/ecology proxy scoring and weighted overall score."""

from datetime import datetime, timedelta

from res_ops.domain.constraint import Constraint, ConstraintSet
from res_ops.domain.result import SimulationResult, StateSnapshot
from res_ops.services import EvaluationService


def _build_result(levels: list[float], outflows: list[float]) -> SimulationResult:
    start = datetime(2024, 7, 1, 0, 0, 0)
    snapshots = []
    for idx, (level, outflow) in enumerate(zip(levels, outflows)):
        snapshots.append(
            StateSnapshot(
                timestamp=start + timedelta(hours=idx),
                level=level,
                storage=25.0,
                inflow=8000.0,
                outflow=outflow,
            )
        )
    return SimulationResult(
        program_id="proxy_test",
        start_time=start,
        end_time=start + timedelta(hours=len(snapshots) - 1),
        snapshots=snapshots,
        max_level=max(levels),
        min_level=min(levels),
        avg_outflow=sum(outflows) / len(outflows),
    )


def test_power_proxy_monotonicity(sample_reservoir_spec) -> None:
    service = EvaluationService(sample_reservoir_spec)

    low_power = _build_result([160.0, 160.0, 160.0], [2000.0, 2000.0, 2000.0])
    high_power = _build_result([170.0, 170.0, 170.0], [6000.0, 6000.0, 6000.0])

    eval_low = service.evaluate(low_power, proxy_options={"tailwater_level": 150.0})
    eval_high = service.evaluate(high_power, proxy_options={"tailwater_level": 150.0})

    assert 0.0 <= eval_low.power_generation_score <= 100.0
    assert 0.0 <= eval_high.power_generation_score <= 100.0
    assert eval_high.power_generation_score > eval_low.power_generation_score


def test_ecology_proxy_penalizes_min_flow_and_ramp(sample_reservoir_spec) -> None:
    service = EvaluationService(sample_reservoir_spec)

    smooth = _build_result([165.0, 165.0, 165.0, 165.0], [3000.0, 3200.0, 3100.0, 3000.0])
    violating = _build_result([165.0, 165.0, 165.0, 165.0], [500.0, 7000.0, 500.0, 7000.0])

    eval_smooth = service.evaluate(
        smooth,
        proxy_options={"env_min_flow": 2500.0, "max_ramp_rate": 2000.0},
    )
    eval_violating = service.evaluate(
        violating,
        proxy_options={"env_min_flow": 2500.0, "max_ramp_rate": 2000.0},
    )

    assert 0.0 <= eval_smooth.ecological_score <= 100.0
    assert 0.0 <= eval_violating.ecological_score <= 100.0
    assert eval_smooth.ecological_score > eval_violating.ecological_score


def test_overall_score_weighted_sum_with_penalty(sample_reservoir_spec) -> None:
    service = EvaluationService(sample_reservoir_spec)
    result = _build_result([165.0, 168.0, 170.0], [3000.0, 3000.0, 3000.0])

    weights = {"flood": 0.45, "supply": 0.25, "power": 0.20, "ecology": 0.10}
    eval_without_violations = service.evaluate(
        result,
        weights=weights,
        proxy_options={"env_min_flow": 2000.0},
    )

    expected_raw = (
        weights["flood"] * eval_without_violations.flood_control_score
        + weights["supply"] * eval_without_violations.water_supply_score
        + weights["power"] * eval_without_violations.power_generation_score
        + weights["ecology"] * eval_without_violations.ecological_score
    ) / sum(weights.values())
    assert eval_without_violations.overall_score == expected_raw

    constraints = ConstraintSet(
        constraints=[
            Constraint(
                id="lmax",
                name="max level",
                constraint_type="level_max",
                parameters={"max_level": 160.0},
            )
        ]
    )
    eval_with_violations = service.evaluate(
        result,
        constraint_set=constraints,
        weights=weights,
        proxy_options={"env_min_flow": 2000.0},
    )

    assert eval_with_violations.overall_score == expected_raw * 0.5
