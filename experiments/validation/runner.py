"""Execution orchestration for minimal real-data validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.data_adapters import RealEventDataAdapter
from experiments.validation.deterministic import DeterministicToolRunner
from experiments.validation.results import JsonlResultLogger, classify_failure_taxonomy
from experiments.validation.scenarios import ScenarioCase
from experiments.workflows import DynamicRealDataWorkflow, RollingRealDataWorkflow, StaticRealDataWorkflow
from experiments.workflows.rolling import RollingThresholds
from pyresops.agents import ReservoirAgentRuntime


@dataclass(frozen=True)
class RunPaths:
    output_dir: Path
    jsonl_path: Path
    csv_path: Path
    markdown_path: Path
    manifest_path: Path


def build_run_paths(output_dir: str | Path, run_id: str) -> RunPaths:
    root = Path(output_dir)
    return RunPaths(
        output_dir=root,
        jsonl_path=root / f"{run_id}.jsonl",
        csv_path=root / f"{run_id}_summary.csv",
        markdown_path=root / f"{run_id}_summary.md",
        manifest_path=root / "event_manifest.csv",
    )


def run_case(
    *,
    scenario_set: str,
    case: ScenarioCase,
    cfg: dict[str, Any],
    adapter: RealEventDataAdapter,
    logger: JsonlResultLogger,
    run_id: str,
    llm_config: str,
    model_profile: str | None,
    max_attempts: int,
) -> list[dict[str, Any]]:
    """Run one scenario case and append stage records."""

    try:
        runner = _build_method_runner(
            case.method_id,
            llm_config=llm_config,
            model_profile=model_profile,
            max_attempts=max_attempts,
        )
    except Exception as exc:
        workflow = _build_workflow(case, cfg, adapter, runner=None)
        try:
            prepared = workflow.prepare(case.rolling_event_path or case.event)
        except Exception as prepare_exc:
            record = _log_case_failure(
                logger=logger,
                run_id=run_id,
                scenario_set=scenario_set,
                case=case,
                model_profile=model_profile or case.method_id,
                failure_reason=f"{type(prepare_exc).__name__}: {prepare_exc}",
                quality=_inspect_case_quality(adapter, case),
            )
            return [record]
        records = []
        for stage in prepared.stages:
            records.append(
                logger.log_stage_result(
                    run_id=run_id,
                    scenario_set=scenario_set,
                    scenario_group=case.scenario_group,
                    event_id=prepared.event_id,
                    workflow_type=case.workflow_type,
                    method_id=case.method_id,
                    model_profile=model_profile or case.method_id,
                    stage=stage,
                    stage_result=None,
                    process_success=False,
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            )
        return records
    workflow = _build_workflow(case, cfg, adapter, runner)
    try:
        result = workflow.run(case.rolling_event_path or case.event)
    except Exception as exc:
        try:
            prepared = workflow.prepare(case.rolling_event_path or case.event)
        except Exception as prepare_exc:
            record = _log_case_failure(
                logger=logger,
                run_id=run_id,
                scenario_set=scenario_set,
                case=case,
                model_profile=_model_profile(case.method_id, runner),
                failure_reason=f"{type(prepare_exc).__name__}: {prepare_exc}",
                quality=_inspect_case_quality(adapter, case),
            )
            return [record]
        records = []
        for stage in prepared.stages:
            records.append(
                logger.log_stage_result(
                    run_id=run_id,
                    scenario_set=scenario_set,
                    scenario_group=case.scenario_group,
                    event_id=prepared.event_id,
                    workflow_type=case.workflow_type,
                    method_id=case.method_id,
                    model_profile=_model_profile(case.method_id, runner),
                    stage=stage,
                    stage_result=None,
                    process_success=False,
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            )
        return records

    stage_results = _stage_results(result.result, len(result.stages))
    if not result.stages:
        record = _log_case_failure(
            logger=logger,
            run_id=run_id,
            scenario_set=scenario_set,
            case=case,
            model_profile=_model_profile(case.method_id, runner),
            failure_reason=result.failure_reason or "no_workflow_stages",
            quality=_inspect_case_quality(adapter, case),
        )
        return [record]
    records = []
    for index, stage in enumerate(result.stages):
        stage_result = stage_results[index] if index < len(stage_results) else {}
        process_success = bool(stage_result.get("process_success", result.success))
        stage_failure_reason = None
        if not process_success:
            stage_failure_reason = (
                stage_result.get("acceptance_failure_reason")
                or result.failure_reason
            )
        records.append(
            logger.log_stage_result(
                run_id=run_id,
                scenario_set=scenario_set,
                scenario_group=case.scenario_group,
                event_id=result.event_id,
                workflow_type=case.workflow_type,
                method_id=case.method_id,
                model_profile=_model_profile(case.method_id, runner),
                stage=stage,
                stage_result=stage_result,
                process_success=process_success,
                failure_reason=stage_failure_reason,
            )
        )
    return records


def _build_method_runner(
    method_id: str,
    *,
    llm_config: str,
    model_profile: str | None,
    max_attempts: int,
):
    if method_id == "tools_only":
        return DeterministicToolRunner()
    if method_id in {
        "full_agent",
        "l0_text_only",
        "l1_manual_only",
        "l2_agno_functions",
        "l3_mcp",
        "l4_mcp_validator",
        "no_tools",
        "manual_only",
        "no_mcp",
        "no_validator",
        "no_structured_output",
        "no_dynamic_contract",
    }:
        return ReservoirAgentRuntime(
            model_profile=model_profile,
            config_path=llm_config,
            max_attempts=max_attempts,
        )
    raise ValueError(f"Unsupported method_id: {method_id}")


def _build_workflow(
    case: ScenarioCase,
    cfg: dict[str, Any],
    adapter: RealEventDataAdapter,
    runner,
):
    if case.workflow_type == "static":
        return StaticRealDataWorkflow(adapter, runner)
    if case.workflow_type == "dynamic":
        reservoir = cfg.get("reservoir") or {}
        return DynamicRealDataWorkflow(
            adapter,
            runner,
            instructions=case.instructions,
            stage_offsets=case.stage_offsets,
            target_adjustments_m=case.target_adjustments_m,
            target_level_tolerance=float(reservoir.get("target_level_tolerance", 0.1)),
        )
    if case.workflow_type == "rolling":
        rolling = cfg.get("rolling") or {}
        thresholds = RollingThresholds(
            relative_error_trigger=float(rolling.get("relative_error_trigger", 0.2)),
            absolute_error_trigger_m3s=float(rolling.get("absolute_error_trigger_m3s", 150.0)),
            high_level_margin_m=float(rolling.get("high_level_margin_m", 0.5)),
            min_remaining_horizon_hours=int(rolling.get("min_remaining_horizon_hours", 9)),
            check_interval_hours=int(rolling.get("check_interval_hours", 3)),
            scheduled_check_replan=bool(rolling.get("scheduled_check_replan", False)),
        )
        manual_offsets = {
            int(offset): str(text)
            for offset, text in (rolling.get("manual_instruction_offsets") or {}).items()
        }
        return RollingRealDataWorkflow(
            adapter,
            runner,
            thresholds=thresholds,
            manual_instruction_offsets=manual_offsets,
        )
    raise ValueError(f"Unsupported workflow_type: {case.workflow_type}")


def _stage_results(result: dict[str, Any] | None, stage_count: int) -> list[dict[str, Any]]:
    if not result:
        return [{} for _ in range(stage_count)]
    if isinstance(result.get("stage_results"), list):
        return [item if isinstance(item, dict) else {} for item in result["stage_results"]]
    return [result]


def _model_profile(method_id: str, runner) -> str:
    if method_id == "tools_only":
        return getattr(runner, "model_profile", "deterministic_tools_only")
    return str(getattr(runner, "model_profile", "") or getattr(runner, "model_id", "full_agent"))


def _log_case_failure(
    *,
    logger: JsonlResultLogger,
    run_id: str,
    scenario_set: str,
    case: ScenarioCase,
    model_profile: str,
    failure_reason: str,
    quality: dict[str, Any] | None = None,
    failure_taxonomy: str | None = None,
) -> dict[str, Any]:
    quality = quality or {}
    record = {
        "run_id": run_id,
        "scenario_set": scenario_set,
        "scenario_group": case.scenario_group,
        "event_id": case.event,
        "workflow_type": case.workflow_type,
        "stage_id": "prepare_failed",
        "stage_offset_hours": None,
        "method_id": case.method_id,
        "model_profile": model_profile,
        "process_success": False,
        "safety_status": {"status": "unknown"},
        "instruction_status": {"status": "unknown"},
        "tool_call_chain": [],
        "tool_call_chain_expected": None,
        "metrics": {},
        "failure_reason": failure_reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "replan_reason": "prepare_failed",
        "operator_instruction": "",
        "payload_summary": {
            "scenario_id": f"{case.workflow_type}_{case.event}",
            "source_path": case.rolling_event_path or case.event,
        },
        "tool_trace": [],
        "final_payload": None,
        "raw_result": {},
        "data_quality_status": quality.get("data_quality_status", "diagnostic_only"),
        "data_quality_reason": quality.get("data_quality_reason", case.data_quality_reason or ""),
        "event_class": quality.get("event_class", "diagnostic_only"),
        "strict_clean_eligible": bool(quality.get("strict_clean_eligible", False)),
        "repaired_executable_eligible": bool(quality.get("repaired_executable_eligible", False)),
        "diagnostic_only": bool(quality.get("diagnostic_only", True)),
        "outflow_fallback_applied": bool(quality.get("outflow_fallback_applied", False)),
        "excluded_from_clean_success_denominator": bool(
            quality.get("excluded_from_clean_success_denominator", True)
        ),
        "excluded_from_repaired_success_denominator": bool(
            quality.get("excluded_from_repaired_success_denominator", True)
        ),
        "failure_taxonomy": failure_taxonomy or classify_failure_taxonomy(failure_reason),
    }
    logger.append(record)
    return record


def _inspect_case_quality(
    adapter: RealEventDataAdapter,
    case: ScenarioCase,
) -> dict[str, Any]:
    target = case.rolling_event_path or case.event
    predicted = False
    if case.workflow_type == "rolling":
        if target and str(target).startswith("stress://"):
            return {
                "data_quality_status": "diagnostic_only",
                "event_class": "diagnostic_only",
                "strict_clean_eligible": False,
                "repaired_executable_eligible": False,
                "diagnostic_only": True,
                "excluded_from_clean_success_denominator": True,
                "excluded_from_repaired_success_denominator": True,
                "data_quality_reason": "rolling_stress_prepare_failed",
            }
        predicted = True
    summary = adapter.inspect_quality(target, predicted=predicted)
    return {
        "data_quality_status": summary.data_quality_status,
        "data_quality_reason": summary.reason,
        "event_class": summary.event_class,
        "strict_clean_eligible": summary.strict_clean_eligible,
        "repaired_executable_eligible": summary.repaired_executable_eligible,
        "diagnostic_only": summary.diagnostic_only,
        "outflow_fallback_applied": summary.outflow_fallback_applied,
        "excluded_from_clean_success_denominator": not summary.strict_clean_eligible,
        "excluded_from_repaired_success_denominator": not summary.repaired_executable_eligible,
    }
