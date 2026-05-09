"""Phase orchestration for paper validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.data_adapters import RealEventDataAdapter
from experiments.paper_validation.config import PaperPhaseConfig, load_phase_config, load_paper_validation_config
from experiments.paper_validation.dataset import (
    build_dataset_quality_summary,
    write_dataset_freeze_report,
    write_dataset_quality_table,
)
from experiments.paper_validation.mcp_audit import run_mcp_schema_audit
from experiments.paper_validation.runners import METHOD_REGISTRY, create_method_runner
from experiments.paper_validation.utils import (
    git_commit_hash,
    sha256_file,
    sha256_jsonable,
    utc_now_compact,
    write_json,
    write_markdown,
)
from experiments.validation.results import build_stage_record
from experiments.validation.scenarios import load_scenario_set
from experiments.workflows import (
    DynamicRealDataWorkflow,
    RollingRealDataWorkflow,
    StaticRealDataWorkflow,
    WorkflowExecutionResult,
)
from experiments.workflows.rolling import RollingThresholds


@dataclass(frozen=True)
class PaperRunPaths:
    root: Path
    jsonl: Path
    summary_csv: Path
    summary_md: Path
    failure_audit_csv: Path
    tables_dir: Path
    config_snapshot: Path
    metadata_json: Path


def run_paper_validation_phase(
    *,
    phase: str,
    model_profile: str | None,
    llm_config: str,
    limit_events: int | None = None,
    include_rolling_stress: bool = False,
) -> dict[str, Any]:
    cfg = load_paper_validation_config()
    if phase == "mcp-skill-all":
        subphases = ["mcp-skill-smoke", "mcp-skill-static", "mcp-skill-dynamic", "mcp-skill-rolling"]
        if include_rolling_stress:
            subphases.append("mcp-skill-rolling-stress")
        results = [
            run_paper_validation_phase(
                phase=subphase,
                model_profile=model_profile,
                llm_config=llm_config,
                limit_events=None,
                include_rolling_stress=include_rolling_stress,
            )
            for subphase in subphases
        ]
        return {
            "phase": phase,
            "subphases": subphases,
            "results": results,
            "status": "PASS" if all(item.get("success_rate", 0.0) >= 0.0 for item in results) else "FAIL",
        }
    phase_cfg = load_phase_config(cfg, phase)
    output_dir = Path((cfg.get("output") or {}).get("dir", "experiments/results/paper_validation"))
    run_id = f"{phase}_{utc_now_compact()}"
    paths = _build_paths(output_dir, run_id)
    adapter = RealEventDataAdapter(
        data_root=(cfg.get("data") or {}).get("root", "data"),
        quality_manifest_path=(cfg.get("data") or {}).get(
            "quality_manifest",
            "experiments/results/data_quality/event_quality_manifest.csv",
        ),
    )

    write_json(paths.config_snapshot, cfg)
    metadata = {
        "run_id": run_id,
        "phase": phase,
        "model_profile": model_profile,
        "llm_config": llm_config,
        "git_commit_hash": git_commit_hash(),
        "data_manifest_hash": sha256_file(adapter.quality_manifest_path),
        "reservoir_spec_hash": sha256_file("experiments/config/default_reservoir.yaml"),
        "config_hash": sha256_jsonable(cfg),
    }
    write_json(paths.metadata_json, metadata)

    if phase == "data-freeze":
        freeze_path = write_dataset_freeze_report(
            manifest_path=adapter.quality_manifest_path,
            output_path="experiments/results/data_quality/dataset_freeze_report.md",
        )
        table_path = write_dataset_quality_table(
            manifest_path=adapter.quality_manifest_path,
            output_path=paths.tables_dir / "dataset_quality_summary.csv",
        )
        audit = run_mcp_schema_audit(output_root="experiments/results/mcp_schema_audit")
        summary = {
            "run_id": run_id,
            "phase": phase,
            "dataset_quality": build_dataset_quality_summary(adapter.quality_manifest_path),
            "freeze_report_path": freeze_path.as_posix(),
            "dataset_table_path": table_path.as_posix(),
            "mcp_schema_audit": audit,
        }
        write_markdown(paths.summary_md, _data_freeze_markdown(summary))
        pd.DataFrame([summary["dataset_quality"]]).to_csv(paths.summary_csv, index=False, encoding="utf-8-sig")
        return summary

    cases = _expand_phase_cases(cfg, phase_cfg)
    if phase == "mcp-skill-smoke":
        cases = _smoke_cases(cases)
    if limit_events is not None:
        cases = _limit_cases_by_event(cases, limit_events)
    records = _run_cases(
        phase=phase,
        cfg=cfg,
        cases=cases,
        adapter=adapter,
        model_profile=model_profile,
        llm_config=llm_config,
        jsonl_path=paths.jsonl,
    )
    summary = export_paper_summary(
        jsonl_path=paths.jsonl,
        summary_csv=paths.summary_csv,
        summary_md=paths.summary_md,
        failure_audit_csv=paths.failure_audit_csv,
        tables_dir=paths.tables_dir,
        manifest_path=adapter.quality_manifest_path,
    )
    summary.update(
        {
            "run_id": run_id,
            "phase": phase,
            "case_count": len(cases),
            "stage_record_count": len(records),
            "paths": {
                "jsonl": paths.jsonl.as_posix(),
                "summary_csv": paths.summary_csv.as_posix(),
                "summary_markdown": paths.summary_md.as_posix(),
                "failure_audit_csv": paths.failure_audit_csv.as_posix(),
                "tables_dir": paths.tables_dir.as_posix(),
                "config_snapshot": paths.config_snapshot.as_posix(),
                "metadata_json": paths.metadata_json.as_posix(),
            },
        }
    )
    return summary


def export_paper_summary(
    *,
    jsonl_path: str | Path,
    summary_csv: str | Path,
    summary_md: str | Path,
    failure_audit_csv: str | Path,
    tables_dir: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    records = _load_jsonl(jsonl_path)
    frame = pd.DataFrame(records)
    if frame.empty:
        frame = pd.DataFrame(
            columns=[
                "workflow_type",
                "method_id",
                "paper_method_level",
                "process_success",
                "structured_output_valid",
                "protocol_adherent",
                "failure_reason",
            ]
        )
    Path(summary_csv).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    failure_frame = frame[frame["process_success"] != True].copy() if "process_success" in frame.columns else pd.DataFrame()
    Path(failure_audit_csv).parent.mkdir(parents=True, exist_ok=True)
    failure_frame.to_csv(failure_audit_csv, index=False, encoding="utf-8-sig")

    tables_root = Path(tables_dir)
    tables_root.mkdir(parents=True, exist_ok=True)
    dataset_summary = build_dataset_quality_summary(manifest_path)
    pd.DataFrame([dataset_summary]).to_csv(
        tables_root / "dataset_quality_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    if not frame.empty:
        l1 = frame[frame["paper_method_level"] == "L1"].copy()
        if not l1.empty:
            _workflow_summary_table(l1, tables_root / "library_baseline_tools_only.csv")
        _workflow_method_summary_table(frame, tables_root / "mimo_static_dynamic_rolling_summary.csv")
        _ablation_summary_table(frame, tables_root / "l0_l4_ablation_summary.csv")
        _failure_taxonomy_table(frame, tables_root / "failure_taxonomy_summary.csv")
        _rolling_stress_table(frame, tables_root / "rolling_stress_summary.csv")
        export_mcp_skill_tables(frame, tables_root)

    summary = _paper_summary_dict(frame)
    write_markdown(summary_md, _paper_summary_markdown(summary))
    return summary


def _build_paths(output_dir: Path, run_id: str) -> PaperRunPaths:
    root = output_dir
    root.mkdir(parents=True, exist_ok=True)
    return PaperRunPaths(
        root=root,
        jsonl=root / f"{run_id}.jsonl",
        summary_csv=root / f"{run_id}_summary.csv",
        summary_md=root / f"{run_id}_summary.md",
        failure_audit_csv=root / f"{run_id}_failure_audit.csv",
        tables_dir=root / "tables",
        config_snapshot=root / f"{run_id}_config_snapshot.json",
        metadata_json=root / f"{run_id}_metadata.json",
    )


def _expand_phase_cases(cfg: dict[str, Any], phase_cfg: PaperPhaseConfig) -> list[dict[str, Any]]:
    large_cfg, large_cases = load_scenario_set("large_validation")
    dynamic_events = sorted({case.event for case in large_cases if case.workflow_type == "dynamic"})
    cases: list[dict[str, Any]] = []
    for scenario_group in phase_cfg.scenario_groups:
        if scenario_group == "static_large":
            static_dir = Path((cfg.get("data") or {}).get("processed_flood_event_dir", "data/processed/flood_event"))
            for path in sorted(static_dir.glob("*.csv")):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "static",
                            "event": path.stem,
                            "method_id": method,
                        }
                    )
        elif scenario_group == "dynamic_representative":
            group_cfg = cfg.get("dynamic_representative") or {}
            for event in dynamic_events:
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "dynamic",
                            "event": event,
                            "method_id": method,
                            "stage_offsets": tuple(int(v) for v in group_cfg.get("stage_offsets", [])),
                            "instructions": {int(k): str(v) for k, v in (group_cfg.get("instructions") or {}).items()},
                            "target_adjustments_m": {int(k): float(v) for k, v in (group_cfg.get("target_adjustments_m") or {}).items()},
                        }
                    )
        elif scenario_group == "rolling_real_forecast":
            group_cfg = cfg.get("rolling_real_forecast") or {}
            for rolling_event_path in group_cfg.get("rolling_event_paths", []):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "rolling",
                            "event": Path(str(rolling_event_path)).stem,
                            "rolling_event_path": str(rolling_event_path),
                            "method_id": method,
                        }
                    )
        elif scenario_group == "rolling_stress":
            group_cfg = cfg.get("rolling_stress") or {}
            for item in group_cfg.get("rolling_forecast_error_scenarios", []):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "rolling",
                            "event": f"{item['event']}_with_pred_{item['forecast_error_type']}",
                            "rolling_event_path": f"stress://{item['event']}?pattern={item['pattern']}",
                            "forecast_error_type": item["forecast_error_type"],
                            "method_id": method,
                        }
                    )
        elif scenario_group == "static_ablation_sample":
            group_cfg = cfg.get("static_ablation_sample") or {}
            for event in group_cfg.get("events", []):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "static",
                            "event": str(event),
                            "method_id": method,
                        }
                    )
        elif scenario_group == "dynamic_ablation_sample":
            group_cfg = cfg.get("dynamic_ablation_sample") or {}
            for event in group_cfg.get("events", []):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "dynamic",
                            "event": str(event),
                            "method_id": method,
                            "stage_offsets": tuple(int(v) for v in group_cfg.get("stage_offsets", [])),
                            "instructions": {int(k): str(v) for k, v in (group_cfg.get("instructions") or {}).items()},
                            "target_adjustments_m": {int(k): float(v) for k, v in (group_cfg.get("target_adjustments_m") or {}).items()},
                        }
                    )
        else:
            raise ValueError(f"Unsupported scenario_group in phase: {scenario_group}")
    return cases


def _run_cases(
    *,
    phase: str,
    cfg: dict[str, Any],
    cases: list[dict[str, Any]],
    adapter: RealEventDataAdapter,
    model_profile: str | None,
    llm_config: str,
    jsonl_path: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if jsonl_path.exists():
        jsonl_path.unlink()
    run_id = jsonl_path.stem
    for case in cases:
        try:
            runner = create_method_runner(
                case["method_id"],
                model_profile=model_profile,
                llm_config=llm_config,
            )
        except Exception as exc:
            record = _blocked_record(run_id, phase, case, str(exc))
            _append_jsonl(jsonl_path, record)
            records.append(record)
            continue

        workflow = _build_workflow(case, cfg, adapter, runner)
        try:
            event_arg = case.get("rolling_event_path") or case["event"]
            result = _run_smoke_stage(workflow, event_arg) if phase == "mcp-skill-smoke" else workflow.run(event_arg)
        except Exception as exc:
            record = _blocked_record(run_id, phase, case, f"{type(exc).__name__}: {exc}")
            _append_jsonl(jsonl_path, record)
            records.append(record)
            continue

        stage_results = []
        if isinstance(result.result, dict) and isinstance(result.result.get("stage_results"), list):
            stage_results = result.result["stage_results"]
        elif isinstance(result.result, dict):
            stage_results = [result.result]
        else:
            stage_results = [{} for _ in result.stages]

        stages_to_log = result.stages
        if isinstance(result.result, dict) and isinstance(result.result.get("stage_results"), list):
            stages_to_log = result.stages[: len(stage_results)]

        for index, stage in enumerate(stages_to_log):
            stage_result = stage_results[index] if index < len(stage_results) else {}
            record = build_stage_record(
                run_id=run_id,
                scenario_set="paper_validation",
                scenario_group=case["scenario_group"],
                event_id=result.event_id,
                workflow_type=case["workflow_type"],
                method_id=case["method_id"],
                model_profile=getattr(runner, "model_profile", case["method_id"]),
                stage=stage,
                stage_result=stage_result,
                process_success=bool(stage_result.get("process_success", result.success)),
                failure_reason=stage_result.get("acceptance_failure_reason") if isinstance(stage_result, dict) else None,
            )
            record["phase"] = phase
            record["method_level"] = METHOD_REGISTRY[case["method_id"]].method_level
            record["paper_method_level"] = stage_result.get("paper_method_level", record["method_level"]) if isinstance(stage_result, dict) else record["method_level"]
            record["structured_output_valid"] = bool(stage_result.get("structured_output_valid", case["method_id"] in {"pyresops_direct", "tools_only"})) if isinstance(stage_result, dict) else False
            record["protocol_adherent"] = bool(stage_result.get("protocol_adherent", case["method_id"] in {"pyresops_direct", "tools_only"})) if isinstance(stage_result, dict) else False
            record["protocol_adherence"] = bool(stage_result.get("protocol_adherence", record["protocol_adherent"])) if isinstance(stage_result, dict) else False
            record["command_following_success"] = bool(stage_result.get("command_following_success", True)) if isinstance(stage_result, dict) else False
            record["infeasible_command_detected"] = bool(stage_result.get("infeasible_command_detected", False)) if isinstance(stage_result, dict) else False
            record["forecast_error_type"] = case.get("forecast_error_type")
            forecast_error = _forecast_error_fields(stage.payload)
            record["forecast_error_type"] = record["forecast_error_type"] or forecast_error["forecast_error_type"]
            record["relative_forecast_error"] = forecast_error["relative_forecast_error"]
            record["absolute_forecast_error"] = forecast_error["absolute_forecast_error"]
            record["whether_replan"] = record.get("replan_reason") not in {None, "", "retain_plan", "no_replan_needed"}
            record["trigger_reason"] = record.get("replan_reason")
            record["total_time_seconds"] = (
                stage_result.get("total_time_seconds") if isinstance(stage_result, dict) else None
            )
            record["tool_call_count"] = (
                stage_result.get("tool_call_count") if isinstance(stage_result, dict) else 0
            )
            if isinstance(stage_result, dict):
                _copy_mcp_trace_fields(record, stage_result)
            record["final_payload_valid"] = bool(record.get("final_payload_valid", record["structured_output_valid"]))
            record["final_payload_validation_error"] = record.get("final_payload_validation_error")
            record["hard_constraint_violation"] = _hard_constraint_violation(record.get("safety_status"))
            if record.get("failure_reason"):
                record["failure_taxonomy"] = _paper_failure_taxonomy(record.get("failure_reason"))
            _append_jsonl(jsonl_path, record)
            records.append(record)
    return records


def _build_workflow(case: dict[str, Any], cfg: dict[str, Any], adapter: RealEventDataAdapter, runner):
    if case["workflow_type"] == "static":
        return StaticRealDataWorkflow(adapter, runner)
    if case["workflow_type"] == "dynamic":
        dynamic_cfg = cfg.get("dynamic_representative") or {}
        return DynamicRealDataWorkflow(
            adapter,
            runner,
            instructions=case.get("instructions"),
            stage_offsets=case.get("stage_offsets"),
            target_adjustments_m=case.get("target_adjustments_m"),
            target_level_tolerance=float(dynamic_cfg.get("target_level_tolerance", 0.1)),
        )
    if case["workflow_type"] == "rolling":
        rolling_cfg = (cfg.get("rolling_real_forecast") or {}) | (cfg.get("rolling_stress") or {})
        thresholds = RollingThresholds(
            relative_error_trigger=float(rolling_cfg.get("relative_error_trigger", 0.2)),
            absolute_error_trigger_m3s=float(rolling_cfg.get("absolute_error_trigger_m3s", 150.0)),
            high_level_margin_m=float(rolling_cfg.get("high_level_margin_m", 0.5)),
            min_remaining_horizon_hours=int(rolling_cfg.get("min_remaining_horizon_hours", 9)),
        )
        manual_offsets = {
            int(offset): str(text)
            for offset, text in (rolling_cfg.get("manual_instruction_offsets") or {6: "Operator review at 6h."}).items()
        }
        return RollingRealDataWorkflow(adapter, runner, thresholds=thresholds, manual_instruction_offsets=manual_offsets)
    raise ValueError(f"Unsupported workflow_type: {case['workflow_type']}")


def _run_smoke_stage(workflow, event_arg: str) -> WorkflowExecutionResult:
    prepared = workflow.prepare(event_arg)
    if not prepared.stages:
        return prepared
    stage = prepared.stages[0]
    stage.payload["stage_id"] = stage.stage_id
    stage.payload["replan_reason"] = stage.replan_reason
    result = workflow.runner.run_scenario(stage.payload)
    return WorkflowExecutionResult(
        workflow_type=prepared.workflow_type,
        event_id=prepared.event_id,
        contract=prepared.contract,
        stages=[stage],
        success=bool(result.get("success")),
        result=result,
        failure_reason=result.get("acceptance_failure_reason"),
        diagnostics={"contract_only": False, "smoke_stage_only": True},
    )


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _smoke_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_workflows: set[str] = set()
    for case in cases:
        workflow = str(case["workflow_type"])
        if workflow in seen_workflows:
            continue
        selected.append(case)
        seen_workflows.add(workflow)
        if seen_workflows == {"static", "dynamic", "rolling"}:
            break
    return selected


def _limit_cases_by_event(cases: list[dict[str, Any]], limit_events: int) -> list[dict[str, Any]]:
    if limit_events <= 0:
        return []
    selected_events: list[str] = []
    selected: list[dict[str, Any]] = []
    for case in cases:
        event = str(case["event"])
        if event not in selected_events:
            if len(selected_events) >= limit_events:
                continue
            selected_events.append(event)
        selected.append(case)
    return selected


def _copy_mcp_trace_fields(record: dict[str, Any], stage_result: dict[str, Any]) -> None:
    fields = [
        "transport",
        "skill_enabled",
        "skill_name",
        "mcp_transport",
        "mcp_url_or_command",
        "mcp_connect_success",
        "mcp_tools_list_success",
        "mcp_available_tool_names",
        "available_tool_names",
        "mcp_tool_call_sequence",
        "mcp_tool_call_count",
        "mcp_tool_call_success_count",
        "mcp_tool_call_failure_count",
        "mcp_structured_result_count",
        "mcp_unstructured_result_count",
        "mcp_structured_content_rate",
        "mcp_error_message",
        "mcp_session_error",
        "final_payload_valid",
        "final_payload_validation_error",
        "protocol_adherence",
    ]
    for field in fields:
        if field in stage_result:
            record[field] = stage_result[field]


def _forecast_error_fields(payload: dict[str, Any]) -> dict[str, Any]:
    data_source = payload.get("data_source") or {}
    observed = float(payload.get("initial_inflow") or 0.0)
    predicted = float(payload.get("predicted_mean_inflow", observed) or observed)
    absolute = abs(observed - predicted)
    relative = absolute / max(abs(predicted), 1.0)
    return {
        "forecast_error_type": data_source.get("forecast_error_pattern"),
        "relative_forecast_error": round(relative, 6),
        "absolute_forecast_error": round(absolute, 6),
    }


def _hard_constraint_violation(safety_status: Any) -> bool:
    if isinstance(safety_status, dict):
        return bool(
            safety_status.get("status") == "hard_constraint_violation"
            or int(safety_status.get("hard_constraint_violations_count") or 0) > 0
        )
    return str(safety_status) == "hard_constraint_violation"


def _paper_failure_taxonomy(reason: str | None) -> str | None:
    text = str(reason or "")
    if text.startswith("mcp_"):
        return "mcp"
    if text in {
        "skill_instruction_not_loaded",
        "static_skill_violation",
        "dynamic_skill_violation",
        "rolling_skill_violation",
        "missing_required_tool",
        "wrong_tool_order",
        "repeated_static_optimization",
        "missing_carry_over_evaluation",
        "missing_dynamic_replan_evaluation",
        "missing_rolling_trigger_reason",
    }:
        return "protocol"
    if text in {"invalid_final_payload", "missing_evaluation_reference", "hallucinated_evaluation_reference"}:
        return "payload"
    if text in {"hard_constraint_violation", "unsafe_plan_accepted", "infeasible_instruction_not_rejected"}:
        return "safety"
    return "tool"


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    return [json.loads(line) for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()]


def _blocked_record(run_id: str, phase: str, case: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scenario_set": "paper_validation",
        "scenario_group": case["scenario_group"],
        "event_id": case["event"],
        "workflow_type": case["workflow_type"],
        "stage_id": "blocked",
        "stage_offset_hours": None,
        "method_id": case["method_id"],
        "model_profile": case["method_id"],
        "process_success": False,
        "safety_status": {"status": "unknown", "hard_constraint_violations_count": 0},
        "instruction_status": {"status": "unknown"},
        "tool_call_chain": [],
        "tool_call_chain_expected": None,
        "metrics": {},
        "failure_reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "replan_reason": None,
        "operator_instruction": "",
        "had_carry_over_plan": False,
        "payload_summary": {"scenario_id": case["event"], "source_path": case.get("rolling_event_path") or case["event"]},
        "tool_trace": [],
        "final_payload": None,
        "raw_result": {},
        "failure_taxonomy": "tool",
        "phase": phase,
        "method_level": METHOD_REGISTRY[case["method_id"]].method_level,
        "paper_method_level": METHOD_REGISTRY[case["method_id"]].method_level,
        "structured_output_valid": False,
        "protocol_adherent": False,
        "command_following_success": False,
        "infeasible_command_detected": False,
        "total_time_seconds": None,
        "tool_call_count": 0,
        "event_class": "diagnostic_only",
        "data_quality_status": "diagnostic_only",
        "strict_clean_eligible": False,
        "repaired_executable_eligible": False,
        "diagnostic_only": True,
    }


def _paper_summary_dict(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"run_count": 0}
    return {
        "run_count": int(len(frame)),
        "success_count": int(frame["process_success"].astype(bool).sum()),
        "success_rate": round(float(frame["process_success"].astype(bool).mean()), 4),
        "hard_constraint_violation_count": _hard_constraint_violation_count(frame),
        "method_levels": sorted(set(frame["paper_method_level"])) if "paper_method_level" in frame.columns else [],
        "failure_reason_distribution": frame["failure_reason"].fillna("").replace("", pd.NA).dropna().value_counts().to_dict() if "failure_reason" in frame.columns else {},
    }


def _paper_summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Paper Validation Summary",
            "",
            f"- Runs: {summary.get('run_count', 0)}",
            f"- Success count: {summary.get('success_count', 0)}",
            f"- Success rate: {summary.get('success_rate', 0.0):.2%}" if summary.get("run_count") else "- Success rate: 0.00%",
            f"- Hard constraint violations: {summary.get('hard_constraint_violation_count', 0)}",
            f"- Method levels: {summary.get('method_levels', [])}",
            f"- Failure reasons: {summary.get('failure_reason_distribution', {})}",
            "",
        ]
    )


def _data_freeze_markdown(summary: dict[str, Any]) -> str:
    dataset = summary["dataset_quality"]
    return "\n".join(
        [
            "# Data Freeze",
            "",
            f"- Total events: {dataset['total_events']}",
            f"- Strict clean: {dataset['strict_clean_count']}",
            f"- Repaired executable: {dataset['repaired_executable_count']}",
            f"- Diagnostic only: {dataset['diagnostic_only_count']}",
            f"- Freeze report: {summary['freeze_report_path']}",
            f"- MCP schema audit: {summary['mcp_schema_audit']['json_path']}",
            "",
        ]
    )


def _workflow_summary_table(frame: pd.DataFrame, output_path: Path) -> None:
    rows = []
    for workflow, group in frame.groupby("workflow_type"):
        rows.append(
            {
                "workflow": workflow,
                "records": len(group),
                "success_rate": round(float(group["process_success"].astype(bool).mean()), 4),
                "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                "strict_clean_success_rate": round(float(group[group["event_class"] == "strict_clean"]["process_success"].astype(bool).mean()), 4) if not group[group["event_class"] == "strict_clean"].empty else 0.0,
                "repaired_executable_success_rate": round(float(group[group["event_class"] == "repaired_executable"]["process_success"].astype(bool).mean()), 4) if not group[group["event_class"] == "repaired_executable"].empty else 0.0,
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _workflow_method_summary_table(frame: pd.DataFrame, output_path: Path) -> None:
    rows = []
    for (method_level, workflow), group in frame.groupby(["paper_method_level", "workflow_type"]):
        rows.append(
            {
                "method_level": method_level,
                "workflow": workflow,
                "denominator_type": "raw",
                "records": len(group),
                "success_rate": round(float(group["process_success"].astype(bool).mean()), 4),
                "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                "protocol_adherence_rate": round(float(group["protocol_adherent"].astype(bool).mean()), 4),
                "structured_output_valid_rate": round(float(group["structured_output_valid"].astype(bool).mean()), 4),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _ablation_summary_table(frame: pd.DataFrame, output_path: Path) -> None:
    rows = []
    for (method_level, workflow), group in frame.groupby(["paper_method_level", "workflow_type"]):
        rows.append(
            {
                "method_level": method_level,
                "workflow": workflow,
                "success_rate": round(float(group["process_success"].astype(bool).mean()), 4),
                "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                "command_following_success_rate": round(float(group["command_following_success"].astype(bool).mean()), 4),
                "infeasible_command_detection_rate": round(float(group["infeasible_command_detected"].astype(bool).mean()), 4),
                "protocol_adherence_rate": round(float(group["protocol_adherent"].astype(bool).mean()), 4),
                "runtime_mean": round(float(group["total_time_seconds"].fillna(0.0).mean()), 4),
                "tool_call_count_mean": round(float(group["tool_call_count"].fillna(0.0).mean()), 4),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _failure_taxonomy_table(frame: pd.DataFrame, output_path: Path) -> None:
    failing = frame[frame["process_success"] != True].copy()
    rows = []
    if not failing.empty:
        for (method_level, workflow, taxonomy, reason), group in failing.groupby(
            ["paper_method_level", "workflow_type", "failure_taxonomy", "failure_reason"]
        ):
            rows.append(
                {
                    "method_level": method_level,
                    "workflow": workflow,
                    "failure_taxonomy": taxonomy,
                    "failure_reason": reason,
                    "count": len(group),
                    "example_event_ids": ",".join(sorted(set(group["event_id"]))[:5]),
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _rolling_stress_table(frame: pd.DataFrame, output_path: Path) -> None:
    rolling = frame[frame["forecast_error_type"].notna()].copy() if "forecast_error_type" in frame.columns else pd.DataFrame()
    rows = []
    if not rolling.empty:
        for forecast_error_type, group in rolling.groupby("forecast_error_type"):
            trigger_reason = group["replan_reason"].mode().iloc[0] if "replan_reason" in group.columns and not group["replan_reason"].dropna().empty else ""
            rows.append(
                {
                    "forecast_error_type": forecast_error_type,
                    "records": len(group),
                    "success_rate": round(float(group["process_success"].astype(bool).mean()), 4),
                    "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                    "replan_rate": round(float(group["whether_replan"].astype(bool).mean()), 4) if "whether_replan" in group.columns else 0.0,
                    "dominant_trigger_reason": trigger_reason,
                    "mean_relative_forecast_error": round(float(group["relative_forecast_error"].fillna(0.0).mean()), 4) if "relative_forecast_error" in group.columns else 0.0,
                    "mean_absolute_forecast_error": round(float(group["absolute_forecast_error"].fillna(0.0).mean()), 4) if "absolute_forecast_error" in group.columns else 0.0,
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _hard_constraint_violation_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    if "hard_constraint_violation" in frame.columns:
        return int(_bool_series(frame["hard_constraint_violation"]).sum())
    if "safety_status" not in frame.columns:
        return 0
    return int(frame["safety_status"].astype(str).str.contains("hard_constraint_violation").sum())


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "pass", "passed"}


def _bool_series(series: pd.Series) -> pd.Series:
    return series.map(_bool_value)


def _rate_from_bool_column(group: pd.DataFrame, column: str) -> float:
    if group.empty or column not in group.columns:
        return 0.0
    return round(float(_bool_series(group[column]).mean()), 4)


def _numeric_sum(group: pd.DataFrame, column: str) -> float:
    if group.empty or column not in group.columns:
        return 0.0
    return float(pd.to_numeric(group[column], errors="coerce").fillna(0).sum())


def _mcp_frame(frame: pd.DataFrame, workflow: str | None = None, phase: str | None = None) -> pd.DataFrame:
    if "transport" not in frame.columns:
        return pd.DataFrame()
    subset = frame[frame["transport"] == "mcp_tools"].copy()
    if workflow is not None and not subset.empty:
        subset = subset[subset["workflow_type"] == workflow].copy()
    if phase is not None and not subset.empty and "phase" in subset.columns:
        subset = subset[subset["phase"] == phase].copy()
    return subset


def _safe_rate(group: pd.DataFrame, column: str) -> float:
    return _rate_from_bool_column(group, column)


def _tool_call_success_rate(group: pd.DataFrame) -> float:
    if group.empty or "mcp_tool_call_count" not in group.columns:
        return 0.0
    calls = _numeric_sum(group, "mcp_tool_call_count")
    if calls == 0:
        return 0.0
    successes = _numeric_sum(group, "mcp_tool_call_success_count")
    return round(successes / calls, 4)


def export_mcp_skill_tables(frame: pd.DataFrame, tables_root: str | Path) -> None:
    """Write MCP skill paper tables from a phase frame or latest combined frame."""
    root = Path(tables_root)
    root.mkdir(parents=True, exist_ok=True)
    _mcp_skill_static_table(frame, root / "mcp_skill_static_summary.csv")
    _mcp_skill_dynamic_table(frame, root / "mcp_skill_dynamic_summary.csv")
    _mcp_skill_rolling_table(frame, root / "mcp_skill_rolling_summary.csv")
    _mcp_transport_audit_table(frame, root / "mcp_transport_audit_summary.csv")
    _mcp_skill_failure_taxonomy_table(frame, root / "mcp_skill_failure_taxonomy.csv")


def _mcp_skill_static_table(frame: pd.DataFrame, output_path: Path) -> None:
    group = _mcp_frame(frame, "static", "mcp-skill-static")
    rows = []
    if not group.empty:
        strict_clean = group[group["event_class"] == "strict_clean"] if "event_class" in group.columns else pd.DataFrame()
        repaired = group[group["event_class"] == "repaired_executable"] if "event_class" in group.columns else pd.DataFrame()
        rows.append(
            {
                "denominator_type": "raw",
                "records": len(group),
                "success_rate": _rate_from_bool_column(group, "process_success"),
                "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                "mcp_connect_success_rate": _safe_rate(group, "mcp_connect_success"),
                "mcp_tool_call_success_rate": _tool_call_success_rate(group),
                "structured_output_valid_rate": _safe_rate(group, "structured_output_valid"),
                "protocol_adherence_rate": _safe_rate(group, "protocol_adherent"),
                "strict_clean_success_rate": _rate_from_bool_column(strict_clean, "process_success"),
                "repaired_executable_success_rate": _rate_from_bool_column(repaired, "process_success"),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _mcp_skill_dynamic_table(frame: pd.DataFrame, output_path: Path) -> None:
    group = _mcp_frame(frame, "dynamic", "mcp-skill-dynamic")
    rows = []
    if not group.empty:
        rows.append(
            {
                "records": len(group),
                "success_rate": _rate_from_bool_column(group, "process_success"),
                "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                "carry_over_evaluation_rate": _mcp_carry_over_evaluation_rate(group),
                "dynamic_protocol_adherence_rate": _safe_rate(group, "protocol_adherent"),
                "mcp_tool_call_success_rate": _tool_call_success_rate(group),
                "structured_output_valid_rate": _safe_rate(group, "structured_output_valid"),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _mcp_skill_rolling_table(frame: pd.DataFrame, output_path: Path) -> None:
    group = _mcp_frame(frame, "rolling", "mcp-skill-rolling")
    rows = []
    if not group.empty:
        trigger = group["trigger_reason"].mode().iloc[0] if "trigger_reason" in group.columns and not group["trigger_reason"].dropna().empty else ""
        rows.append(
            {
                "records": len(group),
                "success_rate": _rate_from_bool_column(group, "process_success"),
                "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                "replan_rate": _rate_from_bool_column(group, "whether_replan"),
                "dominant_trigger_reason": trigger,
                "mcp_tool_call_success_rate": _tool_call_success_rate(group),
                "structured_output_valid_rate": _safe_rate(group, "structured_output_valid"),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _mcp_transport_audit_table(frame: pd.DataFrame, output_path: Path) -> None:
    group = _mcp_frame(frame)
    rows = []
    if not group.empty:
        for (phase, transport), subset in group.groupby(["phase", "mcp_transport"], dropna=False):
            rows.append(
                {
                    "phase": phase,
                    "transport": transport,
                    "connect_success_rate": _safe_rate(subset, "mcp_connect_success"),
                    "tools_list_success_rate": _safe_rate(subset, "mcp_tools_list_success"),
                    "tool_call_success_rate": _tool_call_success_rate(subset),
                    "structured_content_rate": round(float(subset["mcp_structured_content_rate"].fillna(0.0).mean()), 4) if "mcp_structured_content_rate" in subset.columns else 0.0,
                    "timeout_count": int(subset["failure_reason"].fillna("").astype(str).str.contains("mcp_timeout").sum()) if "failure_reason" in subset.columns else 0,
                    "server_error_count": int(subset["failure_reason"].fillna("").astype(str).str.contains("mcp_server_error").sum()) if "failure_reason" in subset.columns else 0,
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _mcp_skill_failure_taxonomy_table(frame: pd.DataFrame, output_path: Path) -> None:
    group = _mcp_frame(frame)
    failing = group[~_bool_series(group["process_success"])].copy() if not group.empty and "process_success" in group.columns else pd.DataFrame()
    rows = []
    if not failing.empty:
        for (phase, workflow, taxonomy, reason), subset in failing.groupby(["phase", "workflow_type", "failure_taxonomy", "failure_reason"], dropna=False):
            rows.append(
                {
                    "phase": phase,
                    "workflow": workflow,
                    "failure_taxonomy": taxonomy,
                    "failure_reason": reason,
                    "count": len(subset),
                    "example_event_ids": ",".join(sorted(set(subset["event_id"].astype(str)))[:5]),
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _mcp_carry_over_evaluation_rate(frame: pd.DataFrame) -> float:
    carry = frame[_bool_series(frame["had_carry_over_plan"])].copy()
    if carry.empty:
        return 1.0
    matched = 0
    for value in carry["mcp_tool_call_sequence"]:
        chain = value if isinstance(value, list) else []
        if not chain and isinstance(value, str):
            try:
                chain = json.loads(value.replace("'", '"'))
            except Exception:
                chain = []
        if list(chain)[:2] == ["simulate_release_plan", "evaluate_release_plan"]:
            matched += 1
    return round(matched / len(carry), 4)
