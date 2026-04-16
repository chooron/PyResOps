from __future__ import annotations

import sys
import types

import pytest

import experiments.paper_experiment_runner as paper_runner


def test_summarize_all_results_excludes_legacy_automated_buckets() -> None:
    static_results = [
        {
            "llm_scores": {"overall": 0.82},
            "human_scores": {"overall": 0.73},
            "llm_constraint_violations": 0,
            "process_complete": True,
        }
    ]
    dynamic_results = [
        {
            "scenario_id": "S03",
            "overall_pass_rate": 0.75,
            "hard_task_partial_credits": {"T1": 0.6},
        }
    ]
    deviation_results = [
        {
            "scenario_id": "S02",
            "controller_type": "llm_tool",
            "overall_score": 0.9,
            "total_constraint_violations": 0,
            "effective_correction_rate": 1.0,
        }
    ]

    report = paper_runner.summarize_all_results(
        static_results=static_results,
        dynamic_results=dynamic_results,
        deviation_results=deviation_results,
    )

    assert "automated_summary" not in report
    assert "automated_results" not in report
    assert report["deviation_summary"]["total"] == 1
    assert report["deviation_summary"]["by_controller"]["llm_tool"]["count"] == 1


def test_run_all_fails_fast_on_error_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paper_runner, "_save_report", lambda report: None)

    static_module = types.SimpleNamespace(
        run_static_experiments=lambda model_profile=None: [{"error": "static failed"}]
    )
    dynamic_module = types.SimpleNamespace(
        run_dynamic_experiments=lambda model_profile=None: []
    )
    deviation_module = types.SimpleNamespace(
        run_all_deviation_experiments=lambda model_profile=None: []
    )

    monkeypatch.setitem(sys.modules, "experiments.static_experiment", static_module)
    monkeypatch.setitem(sys.modules, "experiments.dynamic_experiment", dynamic_module)
    monkeypatch.setitem(sys.modules, "experiments.automated_experiment", deviation_module)

    with pytest.raises(RuntimeError, match="static_experiments"):
        paper_runner.run_all(model_profile="dummy")


def test_run_all_uses_deviation_tier_and_returns_abc_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_reports: list[dict] = []
    monkeypatch.setattr(paper_runner, "_save_report", lambda report: captured_reports.append(report))

    static_module = types.SimpleNamespace(
        run_static_experiments=lambda model_profile=None: [
            {
                "llm_scores": {"overall": 0.8},
                "human_scores": {"overall": 0.7},
                "llm_constraint_violations": 0,
                "process_complete": True,
            }
        ]
    )
    dynamic_module = types.SimpleNamespace(
        run_dynamic_experiments=lambda model_profile=None: [
            {
                "scenario_id": "S03",
                "overall_pass_rate": 0.6,
                "hard_task_partial_credits": {"T1": 0.4},
            }
        ]
    )
    deviation_module = types.SimpleNamespace(
        run_all_deviation_experiments=lambda model_profile=None: [
            {
                "scenario_id": "S02",
                "controller_type": "static",
                "overall_score": 0.7,
                "total_constraint_violations": 1,
                "effective_correction_rate": 0.0,
            }
        ]
    )

    monkeypatch.setitem(sys.modules, "experiments.static_experiment", static_module)
    monkeypatch.setitem(sys.modules, "experiments.dynamic_experiment", dynamic_module)
    monkeypatch.setitem(sys.modules, "experiments.automated_experiment", deviation_module)

    report = paper_runner.run_all(model_profile="dummy")

    assert "static_summary" in report
    assert "dynamic_summary" in report
    assert "deviation_summary" in report
    assert "automated_summary" not in report
    assert "automated_results" not in report
    assert report["deviation_summary"]["total"] == 1
    assert len(captured_reports) == 1
