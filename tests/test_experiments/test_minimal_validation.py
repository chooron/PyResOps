from __future__ import annotations

from experiments.data_adapters import RealEventDataAdapter
from experiments.validation import DeterministicToolRunner, JsonlResultLogger, build_event_manifest
from experiments.validation.reporting import export_summary_report
from experiments.validation.results import build_stage_record
from experiments.validation.runner import run_case
from experiments.validation.scenarios import ScenarioCase
from experiments.validation.scenarios import (
    data_quality_blockers,
    load_scenario_set,
    resolve_rolling_event_paths,
)
from experiments.workflows import DynamicRealDataWorkflow, StaticRealDataWorkflow
from experiments.workflows.contracts import WorkflowContract, WorkflowExecutionResult


def test_manifest_marks_minimal_static_dynamic_and_forecast() -> None:
    adapter = RealEventDataAdapter()

    rows = build_event_manifest(
        adapter,
        selected_static=["2024072617", "2010062002"],
        selected_dynamic=["2024072617"],
    )

    by_id = {row["event_id"]: row for row in rows}
    assert len(rows) == 41
    assert by_id["2010062002"]["max_level"] == 160.16
    assert by_id["2010062002"]["selected_for_minimal_static"] is True
    assert by_id["2024072617"]["selected_for_dynamic"] is True
    assert by_id["2024072617"]["has_forecast"] is True


def test_manifest_marks_data_quality_blockers() -> None:
    adapter = RealEventDataAdapter()

    rows = build_event_manifest(
        adapter,
        selected_static=["2009080920"],
        data_quality_blockers={"2009080920": "missing outflow"},
    )

    by_id = {row["event_id"]: row for row in rows}
    assert by_id["2009080920"]["data_quality_status"] == "repaired_executable"
    assert by_id["2009080920"]["event_class"] == "repaired_executable"
    assert by_id["2009080920"]["excluded_from_clean_static_success_denominator"] is True
    assert by_id["2009080920"]["excluded_from_repaired_static_success_denominator"] is False
    assert by_id["2009080920"]["outflow_fallback_applied"] is True


def test_minimal_validation_scenario_set_expands_requested_cases() -> None:
    cfg, cases = load_scenario_set(
        "minimal_validation",
        workflow="dynamic",
        method="tools_only",
    )

    s2_cases = [
        case for case in cases if case.scenario_group == "s2" and case.event == "2024061623"
    ]
    assert cfg["name"] == "minimal_validation"
    assert s2_cases
    assert s2_cases[0].stage_offsets == (0, 3, 6, 9)
    assert {case.method_id for case in cases} == {"tools_only"}


def test_rolling_auto_scan_deduplicates_configured_forecast_path() -> None:
    cfg, cases = load_scenario_set(
        "minimal_validation",
        workflow="rolling",
        method="all",
    )

    assert resolve_rolling_event_paths(cfg) == ["data/withpred/2024072617.csv"]
    s3_cases = [case for case in cases if case.scenario_group == "s3"]
    assert len(s3_cases) == 2


def test_large_validation_set_covers_static_dynamic_and_rolling_stress_cases() -> None:
    cfg, static_cases = load_scenario_set(
        "large_validation",
        workflow="static",
        method="tools_only",
    )
    _, dynamic_cases = load_scenario_set(
        "large_validation",
        workflow="dynamic",
        method="tools_only",
    )
    _, rolling_cases = load_scenario_set(
        "large_validation",
        workflow="rolling",
        method="tools_only",
    )

    s1_static = [case for case in static_cases if case.scenario_group == "s1"]
    s2_dynamic = [case for case in dynamic_cases if case.scenario_group == "s2"]
    stress_cases = [
        case for case in rolling_cases if str(case.rolling_event_path).startswith("stress://")
    ]

    assert len(s1_static) == 41
    assert len(s2_dynamic) == 11
    assert {case.rolling_event_path for case in stress_cases} == {
        "stress://2024072617?pattern=perfect",
        "stress://2024072617?pattern=under-peak",
        "stress://2024072617?pattern=over-peak",
        "stress://2024072617?pattern=lag",
        "stress://2024072617?pattern=lead",
        "stress://2024072617?pattern=mixed",
    }
    assert data_quality_blockers(cfg)["2009080920"].startswith("missing observed")
    assert next(case for case in s1_static if case.event == "2009080920").data_quality_blocker


def test_manifest_marks_stress_or_safety_events() -> None:
    adapter = RealEventDataAdapter()

    rows = build_event_manifest(
        adapter,
        stress_or_safety_events=["2024072617"],
    )

    by_id = {row["event_id"]: row for row in rows}
    assert by_id["2024072617"]["selected_for_stress_or_safety"] is True
    assert by_id["2024072617"]["selection_class"] == "stress_or_safety"


def test_dynamic_workflow_accepts_configured_zero_hour_stage() -> None:
    adapter = RealEventDataAdapter()

    prepared = DynamicRealDataWorkflow(
        adapter,
        stage_offsets=[0, 3, 6, 9],
        instructions={0: "Initial dispatch."},
    ).prepare("2024072617")

    assert [stage.offset_hours for stage in prepared.stages] == [0, 3, 6, 9]
    assert prepared.stages[0].payload["stage_offset_hours"] == 0
    assert prepared.stages[0].payload["initial_inflow"] == 32.6


def test_tools_only_runner_generates_auditable_static_result() -> None:
    adapter = RealEventDataAdapter()
    stage = StaticRealDataWorkflow(adapter).prepare("2024072617").stages[0]

    result = DeterministicToolRunner().run_scenario(stage.payload)

    assert result["process_success"] is True
    assert result["tool_call_chain"] == [
        "get_reservoir_status",
        "query_dispatch_rules",
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    assert result["accepted_evidence_pair"]["final_payload"]["module_type"]
    assert result["evaluation_metrics"]["final_level_m"] > 0


def test_result_logger_and_report_export_stage_records(tmp_path) -> None:
    adapter = RealEventDataAdapter()
    stage = StaticRealDataWorkflow(adapter).prepare("2024072617").stages[0]
    stage_result = {
        "process_success": True,
        "safety_status": {"status": "safe", "hard_constraint_violations_count": 0},
        "instruction_status": {"status": "completed"},
        "tool_call_chain": ["get_reservoir_status"],
        "evaluation_metrics": {"overall_score": 90.0, "final_level_m": 156.0},
        "accepted_evidence_pair": {"final_payload": {"outflow": 100.0}},
    }

    record = build_stage_record(
        run_id="test_run",
        scenario_set="minimal_validation",
        scenario_group="s0",
        event_id="2024072617",
        workflow_type="static",
        method_id="tools_only",
        model_profile="deterministic_tools_only",
        stage=stage,
        stage_result=stage_result,
        process_success=True,
    )
    logger = JsonlResultLogger(tmp_path / "runs.jsonl")
    logger.append(record)
    logger.append(
        {
            **record,
            "event_id": "2009080920",
            "process_success": False,
            "failure_reason": "data_quality_blocker: missing outflow",
            "data_quality_status": "repaired_executable",
            "event_class": "repaired_executable",
            "strict_clean_eligible": False,
            "repaired_executable_eligible": True,
            "diagnostic_only": False,
            "excluded_from_clean_success_denominator": True,
            "excluded_from_repaired_success_denominator": False,
            "outflow_fallback_applied": True,
        }
    )
    logger.append(
        {
            **record,
            "event_id": "2013060217",
            "process_success": False,
            "failure_reason": "ValueError: Real event has missing inflow value inside workflow horizon",
            "data_quality_status": "diagnostic_only",
            "event_class": "diagnostic_only",
            "strict_clean_eligible": False,
            "repaired_executable_eligible": False,
            "diagnostic_only": True,
            "excluded_from_clean_success_denominator": True,
            "excluded_from_repaired_success_denominator": True,
        }
    )
    report = export_summary_report(
        tmp_path / "runs.jsonl",
        markdown_path=tmp_path / "summary.md",
        csv_path=tmp_path / "summary.csv",
    )

    assert report["summary"]["run_count"] == 3
    assert report["summary"]["success_count"] == 1
    assert report["summary"]["clean_denominator_count"] == 1
    assert report["summary"]["clean_success_rate"] == 1.0
    assert report["summary"]["repaired_denominator_count"] == 1
    assert report["summary"]["repaired_success_rate"] == 0.0
    assert report["summary"]["raw_all_events"] == 3
    assert report["summary"]["strict_clean_set"] == 1
    assert report["summary"]["repaired_executable_set"] == 1
    assert report["summary"]["diagnostic_only_count"] == 1
    assert report["summary"]["failure_taxonomy_distribution"] == {"data": 2}
    assert (tmp_path / "summary.md").read_text(encoding="utf-8").startswith(
        "# Minimal Real-Data Validation Summary"
    )


def test_run_case_uses_repaired_manifest_quality_after_level_interpolation(tmp_path) -> None:
    adapter = RealEventDataAdapter()
    logger = JsonlResultLogger(tmp_path / "runs.jsonl")

    records = run_case(
        scenario_set="large_validation",
        case=ScenarioCase(
            scenario_group="s1",
            workflow_type="static",
            event="2024052720",
            method_id="tools_only",
        ),
        cfg={},
        adapter=adapter,
        logger=logger,
        run_id="test_run",
        llm_config="experiments/config/llm_config.yml",
        model_profile=None,
        max_attempts=1,
    )

    assert records[0]["data_quality_status"] == "repaired_executable"
    assert records[0]["event_class"] == "repaired_executable"
    assert records[0]["strict_clean_eligible"] is False
    assert records[0]["repaired_executable_eligible"] is True
    assert records[0]["excluded_from_repaired_success_denominator"] is False


def test_run_case_only_marks_failed_stage_with_failure_reason(tmp_path, monkeypatch) -> None:
    adapter = RealEventDataAdapter()
    prepared = DynamicRealDataWorkflow(
        adapter,
        stage_offsets=[0, 3],
        instructions={0: "Initial dispatch.", 3: "Re-evaluate."},
    ).prepare("2024072617")

    class DummyWorkflow:
        def prepare(self, event):
            return prepared

        def run(self, event):
            return WorkflowExecutionResult(
                workflow_type="dynamic",
                event_id="2024072617",
                contract=WorkflowContract(
                    workflow_type="dynamic",
                    description="dummy",
                    fixed_inputs=[],
                    tool_chain=[],
                    state_update_rules=[],
                    output_schema={},
                    failure_conditions=[],
                ),
                stages=prepared.stages,
                success=False,
                result={
                    "stage_results": [
                        {"process_success": True},
                        {
                            "process_success": False,
                            "acceptance_failure_reason": "stage_failed",
                        },
                    ]
                },
                failure_reason="stage_failed",
                diagnostics={},
            )

    monkeypatch.setattr(
        "experiments.validation.runner._build_method_runner",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "experiments.validation.runner._build_workflow",
        lambda *args, **kwargs: DummyWorkflow(),
    )

    logger = JsonlResultLogger(tmp_path / "runs.jsonl")
    records = run_case(
        scenario_set="minimal_validation",
        case=ScenarioCase(
            scenario_group="s2",
            workflow_type="dynamic",
            event="2024072617",
            method_id="full_agent",
        ),
        cfg={},
        adapter=adapter,
        logger=logger,
        run_id="test_run",
        llm_config="experiments/config/llm_config.yml",
        model_profile="deepseek",
        max_attempts=1,
    )

    assert records[0]["process_success"] is True
    assert records[0]["failure_reason"] is None
    assert records[1]["process_success"] is False
    assert records[1]["failure_reason"] == "stage_failed"
