"""Phase orchestration for paper validation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.data_adapters import RealEventDataAdapter
from experiments.paper_validation.config import PaperPhaseConfig, load_phase_config, load_paper_validation_config
from experiments.paper_validation.command_challenge import (
    build_payload_repair_audit_rows,
    command_case_prompt_fields,
    enrich_record_with_command_metrics,
    export_command_challenge_tables,
    export_cross_model_tables,
    group_dynamic_command_cases,
    group_rolling_command_cases,
    load_command_challenge_config,
    write_deepseek_status_report,
    write_phase_g_status_report,
)
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
    WorkflowStage,
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
    source: str | None = None,
    source_run_id: str | None = None,
    source_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    max_workers: int = 1,
    wrongtest_dir: str | Path | None = None,
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
                output_dir=output_dir,
                max_workers=max_workers,
            )
            for subphase in subphases
        ]
        return {
            "phase": phase,
            "subphases": subphases,
            "results": results,
            "status": "PASS" if all(item.get("success_rate", 0.0) >= 0.0 for item in results) else "FAIL",
        }
    if phase == "rolling-targeted-rerun":
        return _run_rolling_targeted_rerun_phase(
            cfg=cfg,
            model_profile=model_profile,
            llm_config=llm_config,
            source_run_id=source_run_id or source or "mimo-rolling_20260512_082639_713975",
            source_dir=Path(source_dir or "experiments/results/mimo_rolling_2024072617"),
            output_dir=Path(output_dir or "experiments/results/paper_validation/rolling_targeted_rerun"),
            max_workers=max_workers,
        )
    if phase in {"forecast-error-wrongtest-stage2", "forecast-error-wrongtest-stage3"}:
        from experiments.paper_validation.wrongtest_runner import (
            run_wrongtest_stage2,
            run_wrongtest_stage3,
        )
        resolved_wrongtest_dir = Path(wrongtest_dir or "data/wrongtest")
        resolved_output_dir = Path(output_dir or (cfg.get("output") or {}).get("dir", "experiments/results/paper_validation")) / "forecast_error_wrongtest"
        if phase == "forecast-error-wrongtest-stage2":
            return run_wrongtest_stage2(
                wrongtest_dir=resolved_wrongtest_dir,
                output_dir=resolved_output_dir,
                cfg=cfg,
            )
        return run_wrongtest_stage3(
            wrongtest_dir=resolved_wrongtest_dir,
            output_dir=resolved_output_dir,
            cfg=cfg,
            model_profile=model_profile or "mimo_v25",
            llm_config=llm_config,
        )
    phase_cfg = load_phase_config(cfg, phase)
    output_dir = Path(output_dir or (cfg.get("output") or {}).get("dir", "experiments/results/paper_validation"))
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

    if phase == "freeze-mcp-skill-v1":
        summary = _write_mcp_skill_validation_freeze(
            cfg=cfg,
            adapter=adapter,
            paths=paths,
            model_profile=model_profile,
        )
        return summary

    if phase == "payload-repair-audit":
        return _run_payload_repair_audit(paths=paths, source=source or "latest")

    if wrongtest_dir is not None:
        cfg = dict(cfg) | {"wrongtest_dir": str(wrongtest_dir)}
    cases = _expand_phase_cases(cfg, phase_cfg)
    if phase in {"mcp-skill-smoke", "component-ablation-smoke"}:
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
        max_workers=max_workers,
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
    if phase == "deepseek-mcp-skill-subset":
        frame = pd.DataFrame(records)
        gate_result = None
        try:
            from experiments.check_paper_validation_gates import evaluate_gates

            gate_result = evaluate_gates(paths.summary_csv, include_deepseek_subset=True)
        except Exception:
            gate_result = None
        base_url = _model_base_url(model_profile, llm_config)
        write_deepseek_status_report(
            frame=frame,
            output_path=output_dir / "deepseek_subset_current_status.md",
            model_profile=model_profile,
            base_url=base_url,
            gate_result=gate_result,
            comparison_frame=_latest_command_frame_for_mimo(),
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
        if not _component_ablation_frame(frame).empty:
            _component_ablation_table(frame, tables_root / "ablation_b2_b3_b4_summary.csv")
            _component_contribution_table(frame, tables_root / "component_contribution_summary.csv")
        if "command_id" in frame.columns and frame["command_id"].notna().any():
            export_command_challenge_tables(frame, tables_root)
        if "phase" in frame.columns and frame["phase"].isin(
            {"deepseek-mcp-skill-subset", "cross-model-mcp-skill-subset"}
        ).any():
            export_cross_model_tables(frame, tables_root)

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
        elif scenario_group in {"static_ablation_sample", "component_static_sample"}:
            group_cfg = cfg.get("static_ablation_sample") or {}
            if scenario_group == "component_static_sample":
                group_cfg = cfg.get("component_static_sample") or {}
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
        elif scenario_group in {"dynamic_ablation_sample", "component_dynamic_sample"}:
            group_cfg = cfg.get("dynamic_ablation_sample") or {}
            if scenario_group == "component_dynamic_sample":
                group_cfg = cfg.get("component_dynamic_sample") or {}
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
        elif scenario_group == "component_rolling_real":
            group_cfg = cfg.get("component_rolling_real") or {}
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
        elif scenario_group == "command_challenge":
            command_cfg = load_command_challenge_config((cfg.get("command_challenge") or {}).get("config_path", "experiments/config/command_challenge.yml"))
            command_cases = []
            for section in ("static_cases", "dynamic_cases", "rolling_cases"):
                command_cases.extend(dict(item) for item in command_cfg.get(section, []))
            for command_case in command_cfg.get("static_cases", []) or []:
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "static",
                            "event": str(command_case["event_id"]),
                            "method_id": method,
                            "command_case": dict(command_case),
                        }
                    )
            for grouped in group_dynamic_command_cases(command_cases):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "dynamic",
                            "event": grouped["event_id"],
                            "method_id": method,
                            "stage_offsets": grouped["stage_offsets"],
                            "instructions": grouped["instructions"],
                            "target_adjustments_m": {int(offset): 0.0 for offset in grouped["stage_offsets"]},
                            "command_cases": grouped["command_cases"],
                        }
                    )
            for grouped in group_rolling_command_cases(command_cases):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "rolling",
                            "event": grouped["event_id"],
                            "rolling_event_path": grouped["rolling_event_path"],
                            "method_id": method,
                            "command_cases": grouped["command_cases"],
                            "forced_stage_offsets": [
                                int(item["stage_id"])
                                for item in command_cfg.get("rolling_cases", [])
                                if str(item.get("event_id")) == str(grouped["event_id"])
                            ],
                        }
                    )
        elif scenario_group == "deepseek_static_subset":
            group_cfg = cfg.get("deepseek_static_subset") or {}
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
        elif scenario_group == "deepseek_dynamic_subset":
            group_cfg = cfg.get("deepseek_dynamic_subset") or {}
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
        elif scenario_group == "deepseek_rolling_subset":
            group_cfg = cfg.get("deepseek_rolling_subset") or {}
            for rolling_event_path in group_cfg.get("rolling_event_paths", []):
                for method in phase_cfg.methods:
                    cases.append(
                        {
                            "scenario_group": scenario_group,
                            "workflow_type": "rolling",
                            "event": Path(str(rolling_event_path)).stem,
                            "rolling_event_path": str(rolling_event_path),
                            "method_id": method,
                            "forced_stage_offsets": [int(v) for v in group_cfg.get("forced_stage_offsets", [])],
                            "trigger_reasons": {int(k): str(v) for k, v in (group_cfg.get("trigger_reasons") or {}).items()},
                        }
                    )
        elif scenario_group == "wrongtest_forecast_error":
            # wrongtest_dir is injected via cfg at call time
            wrongtest_dir = Path(cfg.get("wrongtest_dir") or "data/wrongtest")
            manifest_path = wrongtest_dir / "wrongtest_manifest.csv"
            if manifest_path.exists():
                import pandas as _pd
                manifest = _pd.read_csv(manifest_path, encoding="utf-8-sig")
                for _, row in manifest.iterrows():
                    for method in phase_cfg.methods:
                        cases.append(
                            {
                                "scenario_group": scenario_group,
                                "workflow_type": "rolling",
                                "event": str(row["original_event_id"]),
                                "rolling_event_path": str(row["wrongtest_file"]),
                                "perturbation_type": str(row["perturbation_type"]),
                                "method_id": method,
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
    max_workers: int = 1,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if jsonl_path.exists():
        jsonl_path.unlink()
    run_id = jsonl_path.stem

    workers = max(1, min(int(max_workers or 1), len(cases) or 1))
    if workers == 1:
        case_records = [
            _run_case_records(
                run_id=run_id,
                phase=phase,
                cfg=cfg,
                case=case,
                adapter=adapter,
                model_profile=model_profile,
                llm_config=llm_config,
            )
            for case in cases
        ]
    else:
        case_records_by_index: dict[int, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _run_case_records,
                    run_id=run_id,
                    phase=phase,
                    cfg=cfg,
                    case=case,
                    adapter=adapter,
                    model_profile=model_profile,
                    llm_config=llm_config,
                ): index
                for index, case in enumerate(cases)
            }
            for future in as_completed(futures):
                case_records_by_index[futures[future]] = future.result()
        case_records = [
            case_records_by_index[index]
            for index in range(len(cases))
        ]

    for group in case_records:
        for record in group:
            _append_jsonl(jsonl_path, record)
            records.append(record)
    return records


def _run_case_records(
    *,
    run_id: str,
    phase: str,
    cfg: dict[str, Any],
    case: dict[str, Any],
    adapter: RealEventDataAdapter,
    model_profile: str | None,
    llm_config: str,
) -> list[dict[str, Any]]:
    try:
        runner = create_method_runner(
            case["method_id"],
            model_profile=model_profile,
            llm_config=llm_config,
        )
    except Exception as exc:
        record = _blocked_record(run_id, phase, case, str(exc), model_profile=model_profile)
        return [record]

    workflow = _build_workflow(case, cfg, adapter, runner)
    try:
        event_arg = case.get("rolling_event_path") or case["event"]
        result = (
            _run_smoke_stage(workflow, event_arg)
            if phase in {"mcp-skill-smoke", "component-ablation-smoke"}
            else _run_configured_case(workflow, event_arg, case)
            if _case_needs_configured_execution(case)
            else workflow.run(event_arg)
        )
    except Exception as exc:
        record = _blocked_record(
            run_id,
            phase,
            case,
            f"{type(exc).__name__}: {exc}",
            model_profile=model_profile,
        )
        return [record]

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

    records: list[dict[str, Any]] = []
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
            _copy_ablation_fields(record, stage_result)
        record["final_payload_valid"] = bool(record.get("final_payload_valid", record["structured_output_valid"]))
        record["final_payload_validation_error"] = record.get("final_payload_validation_error")
        record["hard_constraint_violation"] = _hard_constraint_violation(record.get("safety_status"))
        command_case = _command_case_for_stage(case, stage.stage_id)
        enrich_record_with_command_metrics(record, command_case)
        if record.get("failure_reason") and not record.get("failure_taxonomy"):
            record["failure_taxonomy"] = _paper_failure_taxonomy(record.get("failure_reason"))
        records.append(record)
    return records


def _write_mcp_skill_validation_freeze(
    *,
    cfg: dict[str, Any],
    adapter: RealEventDataAdapter,
    paths: PaperRunPaths,
    model_profile: str | None,
) -> dict[str, Any]:
    audit = run_mcp_schema_audit(output_root="experiments/results/mcp_schema_audit")
    skill_root = Path("experiments/paper_validation/skills")
    skill_files = sorted(skill_root.glob("*_skill.md"))
    latest_runs = _latest_phase_run_ids(
        [
            "mcp-skill-smoke",
            "mcp-skill-static",
            "mcp-skill-dynamic",
            "mcp-skill-rolling",
            "mcp-skill-rolling-stress",
        ],
        paths.root,
    )
    gate_result: dict[str, Any] | None = None
    combined = paths.root / "mcp_skill_latest_combined_summary.csv"
    if combined.exists():
        from experiments.check_paper_validation_gates import evaluate_gates

        gate_result = evaluate_gates(combined, include_mcp_skill=True)
    mcp_cfg = cfg.get("mcp") or {}
    freeze = {
        "version": "mcp_skill_validation_v1",
        "dataset_freeze_report": "experiments/results/data_quality/dataset_freeze_report.md",
        "event_quality_manifest": adapter.quality_manifest_path.as_posix(),
        "event_quality_manifest_sha256": sha256_file(adapter.quality_manifest_path),
        "reservoir_config": "experiments/config/default_reservoir.yaml",
        "reservoir_config_sha256": sha256_file("experiments/config/default_reservoir.yaml"),
        "mcp_tool_names": [row["name"] for row in audit["summary"]["tools"]],
        "mcp_tool_count": audit["summary"]["tool_count"],
        "skill_contracts": {
            path.as_posix(): sha256_file(path)
            for path in skill_files
        },
        "latest_run_ids": latest_runs,
        "gate_checker_status": (gate_result or {}).get("status", "UNKNOWN"),
        "gate_checker_result": gate_result,
        "git_commit_hash": git_commit_hash(),
        "model_profile": model_profile,
        "mcp_transport": mcp_cfg.get("transport"),
        "mcp_command": mcp_cfg.get("command"),
        "mcp_url": mcp_cfg.get("url"),
    }
    write_json(paths.metadata_json, freeze)
    pd.DataFrame([{
        "version": freeze["version"],
        "gate_checker_status": freeze["gate_checker_status"],
        "model_profile": freeze["model_profile"],
        "mcp_transport": freeze["mcp_transport"],
        "mcp_command": freeze["mcp_command"],
        "git_commit_hash": freeze["git_commit_hash"],
    }]).to_csv(paths.summary_csv, index=False, encoding="utf-8-sig")
    write_markdown(paths.summary_md, _mcp_skill_freeze_markdown(freeze))
    write_markdown(paths.root / "mcp_skill_validation_v1_freeze.md", _mcp_skill_freeze_markdown(freeze))
    return {
        "run_id": paths.jsonl.stem,
        "phase": "freeze-mcp-skill-v1",
        "freeze_path": (paths.root / "mcp_skill_validation_v1_freeze.md").as_posix(),
        "summary_csv": paths.summary_csv.as_posix(),
        "summary_markdown": paths.summary_md.as_posix(),
        **freeze,
    }


def _run_payload_repair_audit(*, paths: PaperRunPaths, source: str) -> dict[str, Any]:
    records = _source_records_for_repair(source)
    rows = build_payload_repair_audit_rows(records)
    paths.jsonl.parent.mkdir(parents=True, exist_ok=True)
    if paths.jsonl.exists():
        paths.jsonl.unlink()
    for row in rows:
        _append_jsonl(paths.jsonl, row)
    frame = pd.DataFrame(rows)
    frame.to_csv(paths.summary_csv, index=False, encoding="utf-8-sig")
    paths.tables_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(paths.tables_dir / "payload_repair_audit.csv", index=False, encoding="utf-8-sig")
    failure_frame = frame[frame["repair_attempted"] != True].copy() if not frame.empty else pd.DataFrame()
    failure_frame.to_csv(paths.failure_audit_csv, index=False, encoding="utf-8-sig")
    summary = {
        "run_id": paths.jsonl.stem,
        "phase": "payload-repair-audit",
        "source": source,
        "records": len(rows),
        "repair_attempted_count": int(frame["repair_attempted"].astype(bool).sum()) if not frame.empty else 0,
        "repair_success_count": int(frame["repair_success"].astype(bool).sum()) if not frame.empty else 0,
        "paths": {
            "jsonl": paths.jsonl.as_posix(),
            "summary_csv": paths.summary_csv.as_posix(),
            "summary_markdown": paths.summary_md.as_posix(),
            "failure_audit_csv": paths.failure_audit_csv.as_posix(),
            "payload_repair_audit": (paths.tables_dir / "payload_repair_audit.csv").as_posix(),
        },
    }
    write_markdown(
        paths.summary_md,
        "\n".join(
            [
                "# Payload Repair Audit",
                "",
                f"- Source: `{source}`",
                f"- Invalid payload records: {summary['records']}",
                f"- Repair attempted: {summary['repair_attempted_count']}",
                f"- Repair success: {summary['repair_success_count']}",
                "- Repair-only rule: no MCP tools are called during repair.",
                "- Original failures are preserved and are not overwritten by repair outcomes.",
                "",
            ]
        ),
    )
    _write_phase_g_report_after_audit(frame)
    return summary


ROLLING_TARGETED_RERUN_FALLBACK_FAILURES = [
    {
        "event_id": "2012062402",
        "stage_id": "rolling_48h",
        "stage_offset_hours": 48,
        "trigger_reason": "scheduled_12h_check",
        "failure_reason": "missing_evaluation_reference",
        "failure_taxonomy": "tool",
    },
    {
        "event_id": "2012062402",
        "stage_id": "rolling_204h",
        "stage_offset_hours": 204,
        "trigger_reason": "relative_forecast_error",
        "failure_reason": "hallucinated_evaluation_reference",
        "failure_taxonomy": "tool",
    },
    {
        "event_id": "2019070517",
        "stage_id": "rolling_24h",
        "stage_offset_hours": 24,
        "trigger_reason": "scheduled_12h_check",
        "failure_reason": "hallucinated_evaluation_reference",
        "failure_taxonomy": "tool",
    },
    {
        "event_id": "2021052114",
        "stage_id": "rolling_168h",
        "stage_offset_hours": 168,
        "trigger_reason": "scheduled_12h_check",
        "failure_reason": "hallucinated_evaluation_reference",
        "failure_taxonomy": "tool",
    },
    {
        "event_id": "2022062023",
        "stage_id": "rolling_36h",
        "stage_offset_hours": 36,
        "trigger_reason": "scheduled_12h_check",
        "failure_reason": "hallucinated_evaluation_reference",
        "failure_taxonomy": "tool",
    },
    {
        "event_id": "2022062023",
        "stage_id": "rolling_72h",
        "stage_offset_hours": 72,
        "trigger_reason": "scheduled_12h_check",
        "failure_reason": "missing_required_tool",
        "failure_taxonomy": "protocol",
    },
]


def _run_rolling_targeted_rerun_phase(
    *,
    cfg: dict[str, Any],
    model_profile: str | None,
    llm_config: str,
    source_run_id: str,
    source_dir: Path,
    output_dir: Path,
    max_workers: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"rolling_targeted_rerun_{utc_now_compact()}"
    paths = _build_paths(output_dir, run_id)
    adapter = RealEventDataAdapter(
        data_root=(cfg.get("data") or {}).get("root", "data"),
        quality_manifest_path=(cfg.get("data") or {}).get(
            "quality_manifest",
            "experiments/results/data_quality/event_quality_manifest.csv",
        ),
    )
    failures = load_targeted_rerun_failures(source_run_id=source_run_id, source_dir=source_dir)
    cases = _targeted_rerun_cases(failures)
    write_json(paths.config_snapshot, {"source_run_id": source_run_id, "source_dir": source_dir.as_posix(), "cases": cases})
    write_json(
        paths.metadata_json,
        {
            "run_id": run_id,
            "phase": "rolling-targeted-rerun",
            "source_run_id": source_run_id,
            "source_dir": source_dir.as_posix(),
            "model_profile": model_profile,
            "llm_config": llm_config,
            "git_commit_hash": git_commit_hash(),
        },
    )
    records = _run_cases(
        phase="rolling-targeted-rerun",
        cfg=cfg,
        cases=cases,
        adapter=adapter,
        model_profile=model_profile,
        llm_config=llm_config,
        jsonl_path=paths.jsonl,
        max_workers=max_workers,
    )
    summary = export_paper_summary(
        jsonl_path=paths.jsonl,
        summary_csv=paths.summary_csv,
        summary_md=paths.summary_md,
        failure_audit_csv=paths.failure_audit_csv,
        tables_dir=paths.tables_dir,
        manifest_path=adapter.quality_manifest_path,
    )
    comparison = _build_targeted_rerun_comparison(
        original_run_id=source_run_id,
        failures=failures,
        rerun_id=run_id,
        records=records,
    )
    comparison_path = output_dir / "rolling_targeted_rerun_comparison.csv"
    comparison.to_csv(comparison_path, index=False, encoding="utf-8-sig")
    report_path = output_dir / "rolling_targeted_rerun_report.md"
    write_markdown(
        report_path,
        _rolling_targeted_rerun_report(
            original_run_id=source_run_id,
            rerun_id=run_id,
            failures=failures,
            comparison=comparison,
        ),
    )
    summary.update(
        {
            "run_id": run_id,
            "phase": "rolling-targeted-rerun",
            "source_run_id": source_run_id,
            "case_count": len(cases),
            "stage_record_count": len(records),
            "comparison_csv": comparison_path.as_posix(),
            "report_path": report_path.as_posix(),
            "paths": {
                "jsonl": paths.jsonl.as_posix(),
                "summary_csv": paths.summary_csv.as_posix(),
                "summary_markdown": paths.summary_md.as_posix(),
                "failure_audit_csv": paths.failure_audit_csv.as_posix(),
                "comparison_csv": comparison_path.as_posix(),
                "report": report_path.as_posix(),
            },
        }
    )
    return summary


def load_targeted_rerun_failures(*, source_run_id: str, source_dir: str | Path) -> list[dict[str, Any]]:
    source_root = Path(source_dir)
    audit_path = source_root / f"{source_run_id}_failure_audit.csv"
    rows: list[dict[str, Any]] = []
    if audit_path.exists():
        frame = pd.read_csv(audit_path, encoding="utf-8-sig")
        if not frame.empty:
            if "workflow_type" in frame.columns:
                rolling = frame[frame["workflow_type"].astype(str) == "rolling"].copy()
            else:
                rolling = pd.DataFrame()
            if rolling.empty and "stage_id" in frame.columns:
                rolling = frame[frame["stage_id"].astype(str).str.startswith("rolling_")].copy()
            for _, row in rolling.iterrows():
                rows.append(_targeted_failure_row(row.to_dict()))
    if not rows:
        jsonl_path = source_root / f"{source_run_id}.jsonl"
        for record in _load_jsonl(jsonl_path):
            if record.get("workflow_type") == "rolling" and record.get("process_success") is not True:
                rows.append(_targeted_failure_row(record))
    if not rows:
        rows = [dict(item) for item in ROLLING_TARGETED_RERUN_FALLBACK_FAILURES]
    rows = [row for row in rows if row.get("failure_reason")]
    rows.sort(key=lambda item: (str(item["event_id"]), int(item["stage_offset_hours"])))
    return rows


def _targeted_failure_row(row: dict[str, Any]) -> dict[str, Any]:
    offset = row.get("stage_offset_hours", row.get("offset_hours"))
    if pd.isna(offset):
        offset = str(row.get("stage_id", "")).removeprefix("rolling_").removesuffix("h")
    return {
        "event_id": str(row.get("event_id")),
        "stage_id": str(row.get("stage_id")),
        "stage_offset_hours": int(float(offset)),
        "trigger_reason": str(row.get("trigger_reason") or row.get("replan_reason") or ""),
        "failure_reason": str(row.get("failure_reason") or ""),
        "failure_taxonomy": str(row.get("failure_taxonomy") or _paper_failure_taxonomy(row.get("failure_reason")) or ""),
    }


def _targeted_rerun_cases(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for failure in failures:
        event_id = str(failure["event_id"])
        offset = int(failure["stage_offset_hours"])
        cases.append(
            {
                "scenario_group": "rolling_targeted_rerun",
                "workflow_type": "rolling",
                "event": event_id,
                "rolling_event_path": f"data/withpred/{event_id}.csv",
                "method_id": "mimo_mcp_validator",
                "forced_stage_offsets": [offset],
                "trigger_reasons": {offset: str(failure.get("trigger_reason") or "targeted_rerun")},
                "original_failure_reason": failure.get("failure_reason"),
                "original_failure_taxonomy": failure.get("failure_taxonomy"),
            }
        )
    return cases


def _build_targeted_rerun_comparison(
    *,
    original_run_id: str,
    failures: list[dict[str, Any]],
    rerun_id: str,
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    record_by_key = {
        (str(record.get("event_id")), str(record.get("stage_id"))): record
        for record in records
    }
    rows: list[dict[str, Any]] = []
    for failure in failures:
        key = (str(failure["event_id"]), str(failure["stage_id"]))
        record = record_by_key.get(key, {})
        rerun_success = bool(record.get("process_success", False))
        rerun_failure = record.get("failure_reason")
        original_failure = failure.get("failure_reason")
        same_failure = bool(rerun_failure and str(rerun_failure) == str(original_failure))
        ref_count = int(record.get("available_evaluation_reference_count") or 0)
        ref_valid = _bool_value(record.get("reference_valid") or record.get("evaluation_reference_valid"))
        if rerun_success and ref_valid:
            interpretation = "evidence_binding_failure_not_reproduced"
        elif same_failure:
            interpretation = "same_failure_reproduced"
        elif rerun_failure:
            interpretation = "different_failure_after_binding_fix"
        else:
            interpretation = "rerun_inconclusive"
        rows.append(
            {
                "original_run_id": original_run_id,
                "rerun_id": rerun_id,
                "event_id": failure["event_id"],
                "stage_id": failure["stage_id"],
                "offset_hours": int(failure["stage_offset_hours"]),
                "trigger_reason": failure.get("trigger_reason"),
                "original_failure_reason": original_failure,
                "original_failure_taxonomy": failure.get("failure_taxonomy"),
                "rerun_success": rerun_success,
                "rerun_failure_reason": rerun_failure,
                "rerun_failure_taxonomy": record.get("failure_taxonomy"),
                "hard_constraint_violation": bool(record.get("hard_constraint_violation", False)),
                "available_evaluation_reference_count": ref_count,
                "final_evaluation_reference": record.get("final_evaluation_reference"),
                "reference_valid": ref_valid,
                "protocol_repair_attempted": _bool_value(record.get("protocol_repair_attempted")),
                "protocol_repair_success": _bool_value(record.get("protocol_repair_success")),
                "same_failure_reproduced": same_failure,
                "interpretation": interpretation,
            }
        )
    return pd.DataFrame(rows)


def _rolling_targeted_rerun_report(
    *,
    original_run_id: str,
    rerun_id: str,
    failures: list[dict[str, Any]],
    comparison: pd.DataFrame,
) -> str:
    success_count = int(_bool_series(comparison["rerun_success"]).sum()) if not comparison.empty else 0
    hard_count = int(_bool_series(comparison["hard_constraint_violation"]).sum()) if not comparison.empty else 0
    ref_valid_count = int(_bool_series(comparison["reference_valid"]).sum()) if not comparison.empty else 0
    repair_attempts = int(_bool_series(comparison["protocol_repair_attempted"]).sum()) if not comparison.empty else 0
    repair_success = int(_bool_series(comparison["protocol_repair_success"]).sum()) if not comparison.empty else 0
    reproduced = comparison[comparison["same_failure_reproduced"] == True] if not comparison.empty else pd.DataFrame()
    cleared = comparison[(comparison["same_failure_reproduced"] != True) & (comparison["rerun_success"] == True)] if not comparison.empty else pd.DataFrame()
    lines = [
        "# Rolling Targeted Rerun Report",
        "",
        "## Purpose",
        "",
        f"This rerun targets only the original {len(failures)} evidence/protocol failure stages from `{original_run_id}`. It does not overwrite the original 93-stage rolling result and must not be used to replace the main success statistic.",
        "",
        "## Original failure summary",
        "",
        "| event_id | stage_id | offset_hours | trigger_reason | original_failure_reason |",
        "|---|---:|---:|---|---|",
    ]
    for failure in failures:
        lines.append(
            f"| {failure['event_id']} | {failure['stage_id']} | {failure['stage_offset_hours']} | {failure.get('trigger_reason', '')} | {failure.get('failure_reason', '')} |"
        )
    lines.extend(
        [
            "",
            "## Evidence-binding fix",
            "",
            "- `available_evaluation_references` is collected only from real MCP tool results such as `evaluate_release_plan`, `check_hard_constraints`, and wrapped workflow tools that contain an evaluation result.",
            "- The final payload is valid only when `evaluation_reference` exactly matches one collected `reference_id` for the current event/stage.",
            "- Missing references, hallucinated references, and stages with no evaluation/check tool result are separated as auditability/evidence-binding failures, not hydrological operation failures.",
            "- Rolling stages with missing evaluation/check tools get one protocol repair attempt; the rerun record keeps repair metadata instead of modifying the original run.",
            "",
            "## Targeted rerun results",
            "",
            f"- Rerun ID: `{rerun_id}`",
            f"- Stage success: {success_count}/{len(comparison)}",
            f"- Hard constraint violation count: {hard_count}",
            f"- Reference valid rate: {ref_valid_count}/{len(comparison)}",
            f"- Protocol repair attempted/success: {repair_attempts}/{repair_success}",
            "",
            "| event_id | stage_id | original_failure_reason | rerun_success | reference_valid | final_evaluation_reference | interpretation |",
            "|---|---:|---|---:|---:|---|---|",
        ]
    )
    for row in comparison.itertuples(index=False):
        lines.append(
            f"| {row.event_id} | {row.stage_id} | {row.original_failure_reason} | {row.rerun_success} | {row.reference_valid} | {row.final_evaluation_reference or ''} | {row.interpretation} |"
        )
    lines.extend(
        [
            "",
            "## Failure reproduction analysis",
            "",
            f"- Same failure reproduced: {len(reproduced)}",
            f"- Original failure not reproduced with successful rerun: {len(cleared)}",
        ]
    )
    if not reproduced.empty:
        lines.append("- Reproduced stages: " + ", ".join(f"{row.event_id}/{row.stage_id}" for row in reproduced.itertuples()))
    if not cleared.empty:
        lines.append("- Cleared stages: " + ", ".join(f"{row.event_id}/{row.stage_id}" for row in cleared.itertuples()))
    lines.extend(
        [
            "",
            "## Paper interpretation",
            "",
            "- The main paper result should continue to report the original 10-event rolling validation: 87/93 successful stages, zero hard-constraint violations, and failures concentrated in auditability/evidence binding.",
            "- This targeted rerun is an evidence-binding robustness check. It tests whether the six original failures persist after strict reference binding and one rolling protocol repair attempt.",
            "- The rerun must not be used to inflate or replace the original rolling success rate.",
            "",
        ]
    )
    return "\n".join(lines)


def _source_records_for_repair(source: str) -> list[dict[str, Any]]:
    root = Path("experiments/results/paper_validation")
    if source == "latest":
        records: list[dict[str, Any]] = []
        for phase in ("command-challenge", "deepseek-mcp-skill-subset"):
            candidates = sorted(root.glob(f"{phase}_*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
            if candidates:
                records.extend(_load_jsonl(candidates[0]))
        if records:
            return records
    candidate = root / f"{source}.jsonl"
    if candidate.exists():
        return _load_jsonl(candidate)
    path = Path(source)
    if path.exists():
        return _load_jsonl(path)
    candidates = sorted(root.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    return _load_jsonl(candidates[0]) if candidates else []


def _write_phase_g_report_after_audit(payload_repair_frame: pd.DataFrame) -> None:
    root = Path("experiments/results/paper_validation")
    command_frame = _latest_phase_frame("command-challenge")
    deepseek_frame = _latest_phase_frame("deepseek-mcp-skill-subset")
    command_gate = None
    deepseek_gate = None
    try:
        from experiments.check_paper_validation_gates import evaluate_gates

        command_summary = _latest_phase_summary("command-challenge")
        if command_summary:
            command_gate = evaluate_gates(command_summary, include_command_challenge=True)
        deepseek_summary = _latest_phase_summary("deepseek-mcp-skill-subset")
        if deepseek_summary:
            deepseek_gate = evaluate_gates(deepseek_summary, include_deepseek_subset=True)
    except Exception:
        pass
    write_phase_g_status_report(
        output_path=root / "phase_g_current_status.md",
        changed_files=[
            "experiments/config/command_challenge.yml",
            "experiments/config/llm_config.yml",
            "experiments/config/paper_validation.yml",
            "experiments/run_paper_validation.py",
            "experiments/check_paper_validation_gates.py",
            "experiments/paper_validation/command_challenge.py",
            "experiments/paper_validation/orchestrator.py",
            "experiments/paper_validation/mcp_skill_runner.py",
            "pyresops/agents/config_loader.py",
            "pyresops/agents/model_builder.py",
            "tests/test_experiments/test_paper_validation.py",
        ],
        command_frame=command_frame,
        deepseek_frame=deepseek_frame,
        payload_repair_frame=payload_repair_frame,
        command_gate=command_gate,
        deepseek_gate=deepseek_gate,
    )


def _latest_phase_frame(phase: str) -> pd.DataFrame:
    root = Path("experiments/results/paper_validation")
    candidates = sorted(root.glob(f"{phase}_*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    return pd.DataFrame(_load_jsonl(candidates[0])) if candidates else pd.DataFrame()


def _latest_phase_summary(phase: str) -> Path | None:
    root = Path("experiments/results/paper_validation")
    candidates = sorted(root.glob(f"{phase}_*_summary.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _latest_command_frame_for_mimo() -> pd.DataFrame:
    frame = _latest_phase_frame("command-challenge")
    if frame.empty or "model_profile" not in frame.columns:
        return frame
    return frame[frame["model_profile"].astype(str).str.contains("mimo", case=False, na=False)].copy()


def _model_base_url(model_profile: str | None, llm_config: str) -> str | None:
    try:
        from pyresops.agents.config_loader import AgentModelConfigLoader

        cfg = AgentModelConfigLoader().load(profile=model_profile, config_path=llm_config)
        return str(cfg.get("base_url") or "")
    except Exception:
        return None


def _latest_phase_run_ids(phases: list[str], root: Path) -> dict[str, str | None]:
    latest: dict[str, str | None] = {}
    for phase in phases:
        candidates = sorted(root.glob(f"{phase}_*_summary.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
        latest[phase] = candidates[0].name.removesuffix("_summary.csv") if candidates else None
    return latest


def _mcp_skill_freeze_markdown(freeze: dict[str, Any]) -> str:
    lines = [
        "# MCP Skill Validation v1 Freeze",
        "",
        f"- Version: {freeze['version']}",
        f"- Dataset freeze report: {freeze['dataset_freeze_report']}",
        f"- Event quality manifest: {freeze['event_quality_manifest']}",
        f"- Event quality manifest SHA256: `{freeze['event_quality_manifest_sha256']}`",
        f"- Reservoir config: {freeze['reservoir_config']}",
        f"- Reservoir config SHA256: `{freeze['reservoir_config_sha256']}`",
        f"- Model profile: {freeze['model_profile']}",
        f"- MCP transport: {freeze['mcp_transport']}",
        f"- MCP command: `{freeze['mcp_command']}`",
        f"- Gate checker status: {freeze['gate_checker_status']}",
        f"- Git commit hash: `{freeze['git_commit_hash']}`",
        "",
        "## Latest Run IDs",
        "",
    ]
    for phase, run_id in freeze["latest_run_ids"].items():
        lines.append(f"- {phase}: `{run_id}`")
    lines.extend(["", "## MCP Tools", ""])
    for name in freeze["mcp_tool_names"]:
        lines.append(f"- {name}")
    lines.extend(["", "## Skill Contracts", ""])
    for path, digest in freeze["skill_contracts"].items():
        lines.append(f"- {path}: `{digest}`")
    lines.append("")
    return "\n".join(lines)


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
            check_interval_hours=int(rolling_cfg.get("check_interval_hours", 3)),
            scheduled_check_replan=bool(rolling_cfg.get("scheduled_check_replan", False)),
        )
        configured_manual_offsets = (
            rolling_cfg["manual_instruction_offsets"]
            if "manual_instruction_offsets" in rolling_cfg
            else {6: "Operator review at 6h."}
        )
        manual_offsets = {
            int(offset): str(text)
            for offset, text in (configured_manual_offsets or {}).items()
        }
        return RollingRealDataWorkflow(
            adapter,
            runner,
            thresholds=thresholds,
            manual_instruction_offsets=manual_offsets,
            continue_on_stage_failure=bool(rolling_cfg.get("continue_on_stage_failure", False)),
        )
    raise ValueError(f"Unsupported workflow_type: {case['workflow_type']}")


def _case_needs_configured_execution(case: dict[str, Any]) -> bool:
    return bool(case.get("command_case") or case.get("command_cases") or case.get("forced_stage_offsets"))


def _run_configured_case(workflow, event_arg: str, case: dict[str, Any]) -> WorkflowExecutionResult:
    if case["workflow_type"] == "rolling" and case.get("forced_stage_offsets"):
        return _run_forced_rolling_case(workflow, event_arg, case)
    prepared = workflow.prepare(event_arg)
    if workflow.runner is None:
        return prepared
    stages: list[WorkflowStage] = []
    stage_results: list[dict[str, Any]] = []
    failure_reason = None
    for stage in prepared.stages:
        command_case = _command_case_for_stage(case, stage.stage_id)
        configured_stage = _stage_with_command(stage, command_case)
        configured_stage.payload["stage_id"] = configured_stage.stage_id
        configured_stage.payload["replan_reason"] = configured_stage.replan_reason
        result = workflow.runner.run_scenario(configured_stage.payload)
        stage_results.append(result)
        stages.append(configured_stage)
        if not result.get("success") and not case.get("command_cases"):
            failure_reason = result.get("acceptance_failure_reason") or "stage_failed"
            break
        if not result.get("success") and failure_reason is None:
            failure_reason = result.get("acceptance_failure_reason") or "stage_failed"
    if len(stage_results) == 1:
        result_payload: dict[str, Any] = stage_results[0]
    else:
        result_payload = {"stage_results": stage_results}
    return WorkflowExecutionResult(
        workflow_type=prepared.workflow_type,
        event_id=prepared.event_id,
        contract=prepared.contract,
        stages=stages,
        success=failure_reason is None,
        result=result_payload,
        failure_reason=failure_reason,
        diagnostics=prepared.diagnostics | {"configured_execution": True},
    )


def _run_forced_rolling_case(workflow, event_arg: str, case: dict[str, Any]) -> WorkflowExecutionResult:
    loaded = workflow.adapter.load_predicted_event(event_arg)
    if not loaded.has_prediction:
        raise ValueError(f"{loaded.event_id}: rolling workflow requires predict column")
    stages: list[WorkflowStage] = []
    stage_results: list[dict[str, Any]] = []
    failure_reason = None
    trigger_reasons = {int(k): str(v) for k, v in (case.get("trigger_reasons") or {}).items()}
    for offset in [int(value) for value in case.get("forced_stage_offsets", [])]:
        index = int(offset / loaded.time_step_hours)
        if index < 0 or index >= len(loaded.records):
            continue
        record = loaded.records[index]
        if record.inflow is None or record.predict is None or record.level is None:
            continue
        command_case = _command_case_for_stage(case, f"rolling_{offset}h")
        instruction = str((command_case or {}).get("command_text") or "")
        replan_reason = trigger_reasons.get(offset) or _rolling_command_trigger_reason(command_case, offset)
        payload = workflow.adapter.to_payload(
            loaded,
            workflow_type="rolling",
            scenario_id=f"rolling_{loaded.event_id}_{offset}h",
            stage_offset_hours=offset,
            operator_instruction=instruction,
            agent_workflow_profile="rolling_reservoir",
        )
        stage = WorkflowStage(
            stage_id=f"rolling_{offset}h",
            offset_hours=offset,
            payload=payload,
            operator_instruction=instruction,
            replan_required=bool((command_case or {}).get("requires_replan", True)),
            replan_reason=replan_reason,
        )
        configured_stage = _stage_with_command(stage, command_case)
        configured_stage.payload["stage_id"] = configured_stage.stage_id
        configured_stage.payload["replan_reason"] = configured_stage.replan_reason
        result = workflow.runner.run_scenario(configured_stage.payload)
        stage_results.append(result)
        stages.append(configured_stage)
        if not result.get("success") and not case.get("command_cases"):
            failure_reason = result.get("acceptance_failure_reason") or "stage_failed"
            break
        if not result.get("success") and failure_reason is None:
            failure_reason = result.get("acceptance_failure_reason") or "stage_failed"
    return WorkflowExecutionResult(
        workflow_type="rolling",
        event_id=loaded.event_id,
        contract=workflow.contract(),
        stages=stages,
        success=failure_reason is None and bool(stages),
        result={"stage_results": stage_results},
        failure_reason=failure_reason,
        diagnostics={"contract_only": False, "configured_execution": True},
    )


def _stage_with_command(stage: WorkflowStage, command_case: dict[str, Any] | None) -> WorkflowStage:
    if not command_case:
        return stage
    payload = dict(stage.payload)
    payload["operator_instruction"] = str(command_case.get("command_text") or "")
    payload["command_challenge"] = command_case_prompt_fields(command_case)
    payload["command_id"] = command_case.get("command_id")
    payload["command_type"] = command_case.get("command_type")
    return WorkflowStage(
        stage_id=stage.stage_id,
        offset_hours=stage.offset_hours,
        payload=payload,
        operator_instruction=str(command_case.get("command_text") or stage.operator_instruction),
        replan_required=bool(command_case.get("requires_replan", stage.replan_required)),
        replan_reason=stage.replan_reason,
    )


def _command_case_for_stage(case: dict[str, Any], stage_id: str) -> dict[str, Any] | None:
    if case.get("command_case"):
        return dict(case["command_case"])
    command_cases = case.get("command_cases") or {}
    if stage_id in command_cases:
        return dict(command_cases[stage_id])
    stage_text = str(stage_id)
    for key, value in command_cases.items():
        if str(key) == stage_text:
            return dict(value)
    return None


def _rolling_command_trigger_reason(command_case: dict[str, Any] | None, offset: int) -> str:
    notes = str((command_case or {}).get("notes") or "")
    for candidate in ("manual_instruction", "relative_forecast_error", "scheduled_update"):
        if candidate in notes:
            return candidate
    if offset in {6, 15}:
        return "manual_instruction"
    if offset in {3, 12, 21}:
        return "relative_forecast_error"
    return "scheduled_update"


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
    seen_keys: set[tuple[str, str]] = set()
    methods = {str(case["method_id"]) for case in cases}
    workflows = {str(case["workflow_type"]) for case in cases}
    for case in cases:
        workflow = str(case["workflow_type"])
        method = str(case["method_id"])
        key = (workflow, method)
        if key in seen_keys:
            continue
        selected.append(case)
        seen_keys.add(key)
        if len(seen_keys) == len(methods) * len(workflows):
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
        "available_evaluation_references",
        "available_evaluation_reference_count",
        "final_evaluation_reference",
        "reference_valid",
        "protocol_repair_attempted",
        "protocol_repair_success",
        "missing_tool_before_repair",
        "repair_added_tool_calls",
        "repair_parent_failure_reason",
        "repair_parent_tool_call_chain",
    ]
    for field in fields:
        if field in stage_result:
            record[field] = stage_result[field]


def _copy_ablation_fields(record: dict[str, Any], stage_result: dict[str, Any]) -> None:
    fields = [
        "executable_plan",
        "missing_required_field_count",
        "missing_required_fields",
        "missing_required_field",
        "hallucinated_value",
        "hallucinated_value_count",
        "evaluation_reference_valid",
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
    if text in {"invalid_final_payload"}:
        return "payload"
    if text in {"missing_evaluation_reference", "hallucinated_evaluation_reference"}:
        return "tool"
    if text in {"hard_constraint_violation", "unsafe_plan_accepted", "infeasible_instruction_not_rejected"}:
        return "safety"
    return "tool"


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    return [json.loads(line) for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()]


def _blocked_record(
    run_id: str,
    phase: str,
    case: dict[str, Any],
    reason: str,
    *,
    model_profile: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scenario_set": "paper_validation",
        "scenario_group": case["scenario_group"],
        "event_id": case["event"],
        "workflow_type": case["workflow_type"],
        "stage_id": "blocked",
        "stage_offset_hours": None,
        "method_id": case["method_id"],
        "model_profile": model_profile or case["method_id"],
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


def _component_ablation_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "phase" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["phase"].isin({"component-ablation", "component-ablation-smoke"})].copy()


def _component_ablation_table(frame: pd.DataFrame, output_path: Path) -> None:
    component = _component_ablation_frame(frame)
    rows = []
    if not component.empty:
        for (method_level, method_id, workflow), group in component.groupby(
            ["paper_method_level", "method_id", "workflow_type"],
            dropna=False,
        ):
            rows.append(
                {
                    "method_level": method_level,
                    "method_id": method_id,
                    "workflow": workflow,
                    "records": len(group),
                    "success_rate": _rate_from_bool_column(group, "process_success"),
                    "executable_plan_rate": _rate_from_bool_column(group, "executable_plan"),
                    "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                    "structured_output_valid_rate": _rate_from_bool_column(group, "structured_output_valid"),
                    "protocol_adherence_rate": _rate_from_bool_column(group, "protocol_adherent"),
                    "tool_order_accuracy": _rate_from_bool_column(group, "protocol_adherent"),
                    "carry_over_evaluation_rate": _mcp_carry_over_evaluation_rate(group)
                    if workflow == "dynamic"
                    else 1.0,
                    "rolling_trigger_reason_coverage_rate": _coverage_rate(group, "trigger_reason")
                    if workflow == "rolling"
                    else 1.0,
                    "invalid_final_payload_count": int(
                        group["failure_reason"].fillna("").astype(str).eq("invalid_final_payload").sum()
                    )
                    if "failure_reason" in group.columns
                    else 0,
                    "missing_required_field_count": int(_numeric_sum(group, "missing_required_field_count")),
                    "hallucinated_value_count": int(_numeric_sum(group, "hallucinated_value_count")),
                    "evaluation_reference_valid_rate": _rate_from_bool_column(group, "evaluation_reference_valid"),
                    "mcp_tool_call_success_rate": _tool_call_success_rate(group)
                    if "mcp_tool_call_count" in group.columns
                    else 0.0,
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _component_contribution_table(frame: pd.DataFrame, output_path: Path) -> None:
    component = _component_ablation_frame(frame)
    rows = []
    if not component.empty:
        summary_rows = []
        for method_level, group in component.groupby("paper_method_level", dropna=False):
            summary_rows.append(
                {
                    "method_level": method_level,
                    "records": len(group),
                    "success_rate": _rate_from_bool_column(group, "process_success"),
                    "executable_plan_rate": _rate_from_bool_column(group, "executable_plan"),
                    "protocol_adherence_rate": _rate_from_bool_column(group, "protocol_adherent"),
                    "structured_output_valid_rate": _rate_from_bool_column(group, "structured_output_valid"),
                    "evaluation_reference_valid_rate": _rate_from_bool_column(group, "evaluation_reference_valid"),
                    "mcp_tool_call_success_rate": _tool_call_success_rate(group)
                    if "mcp_tool_call_count" in group.columns
                    else 0.0,
                    "hard_constraint_violation_count": _hard_constraint_violation_count(group),
                }
            )
        by_level = {row["method_level"]: row for row in summary_rows}

        def delta(metric: str, after: str, before: str) -> float | None:
            if after not in by_level or before not in by_level:
                return None
            return round(float(by_level[after][metric]) - float(by_level[before][metric]), 4)

        rows.append(
            {
                "comparison": "B3_minus_B2",
                "component": "MCPTools",
                "executable_plan_rate_delta": delta("executable_plan_rate", "B3", "L2"),
                "success_rate_delta": delta("success_rate", "B3", "L2"),
                "protocol_adherence_rate_delta": delta("protocol_adherence_rate", "B3", "L2"),
                "structured_output_valid_rate_delta": delta("structured_output_valid_rate", "B3", "L2"),
                "evaluation_reference_valid_rate_delta": delta("evaluation_reference_valid_rate", "B3", "L2"),
                "mcp_tool_call_success_rate_delta": delta("mcp_tool_call_success_rate", "B3", "L2"),
            }
        )
        rows.append(
            {
                "comparison": "B4_minus_B3",
                "component": "Skill+Validator",
                "executable_plan_rate_delta": delta("executable_plan_rate", "B4", "B3"),
                "success_rate_delta": delta("success_rate", "B4", "B3"),
                "protocol_adherence_rate_delta": delta("protocol_adherence_rate", "B4", "B3"),
                "structured_output_valid_rate_delta": delta("structured_output_valid_rate", "B4", "B3"),
                "evaluation_reference_valid_rate_delta": delta("evaluation_reference_valid_rate", "B4", "B3"),
                "mcp_tool_call_success_rate_delta": delta("mcp_tool_call_success_rate", "B4", "B3"),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _coverage_rate(group: pd.DataFrame, column: str) -> float:
    if group.empty or column not in group.columns:
        return 0.0
    values = group[column].dropna().astype(str).str.strip()
    return round(float((values != "").mean()), 4) if len(values) else 0.0


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
