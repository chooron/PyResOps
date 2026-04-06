"""Tests for step-by-step evaluation scoring."""

from datetime import datetime

from pyresops.services import EvaluationService
from pyresops.domain.result import SimulationResult, StateSnapshot


def _make_sim_result(max_level, min_level):
    """Helper."""
    snapshots = [
        StateSnapshot(
            timestamp=datetime(2024, 7, 1, i, 0, 0),
            level=level,
            storage=25.0,
            inflow=8000.0,
            outflow=8000.0,
        )
        for i, level in enumerate([165.0, 168.0, max_level, 166.0, min_level])
    ]
    return SimulationResult(
        program_id="eval_test",
        start_time=datetime(2024, 7, 1, 0, 0, 0),
        end_time=datetime(2024, 7, 1, 4, 0, 0),
        snapshots=snapshots,
        max_level=max_level,
        min_level=min_level,
        avg_outflow=8000.0,
    )


def test_step_scores_included(sample_reservoir_spec):
    """评估时可选择包含逐步评分."""
    service = EvaluationService(sample_reservoir_spec)
    result = _make_sim_result(170.0, 160.0)

    eval_result = service.evaluate(result, include_step_scores=True)
    assert len(eval_result.step_scores) == 5

    for ss in eval_result.step_scores:
        assert 0 <= ss.risk_score <= 100
        assert 0 <= ss.constraint_score <= 100
        assert 0 <= ss.benefit_score <= 100


def test_step_scores_excluded_by_default(sample_reservoir_spec):
    """默认不包含逐步评分."""
    service = EvaluationService(sample_reservoir_spec)
    result = _make_sim_result(170.0, 160.0)

    eval_result = service.evaluate(result)
    assert len(eval_result.step_scores) == 0


def test_step_scores_with_constraints(sample_reservoir_spec):
    """带约束的逐步评分."""
    from pyresops.domain.constraint import Constraint, ConstraintSet

    service = EvaluationService(sample_reservoir_spec)
    result = _make_sim_result(170.0, 160.0)

    cs = ConstraintSet(
        constraints=[
            Constraint(
                id="lmax", name="", constraint_type="level_max", parameters={"max_level": 169.0}
            ),
        ]
    )

    eval_result = service.evaluate(result, constraint_set=cs, include_step_scores=True)
    # 最高水位170 > 169, 所以某些步应该有违反
    assert len(eval_result.constraint_violations) > 0
    # 步评分中有约束分
    assert any(ss.constraint_score < 100 for ss in eval_result.step_scores)


def test_step_scores_to_dataframe(sample_reservoir_spec):
    """逐步评分可转 DataFrame."""
    import pandas as pd

    service = EvaluationService(sample_reservoir_spec)
    result = _make_sim_result(170.0, 160.0)

    eval_result = service.evaluate(result, include_step_scores=True)
    df = eval_result.to_dataframe()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5
    assert "risk_score" in df.columns
    assert "constraint_score" in df.columns
    assert "benefit_score" in df.columns
