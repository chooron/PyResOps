"""Gate checks and runners for forecast-error wrongtest Stage 2 and Stage 3.

Stage 2: deterministic workflow-level validation (pyresops_direct).
Stage 3: MiMo + MCPTools + Skill validation (mimo_mcp_skill).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def check_stage1_gate(wrongtest_dir: Path | str) -> None:
    """Raise RuntimeError if Stage 1 gate has not passed."""
    d = Path(wrongtest_dir)
    gate_path = d / "stage1_gate_result.json"
    if not gate_path.exists():
        raise RuntimeError(
            f"Stage 1 gate result not found at {gate_path}. "
            "Run Stage 1 (create_forecast_error_wrongtest.py) first."
        )
    gates = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gates.get("stage1_pass"):
        raise RuntimeError(
            f"Stage 1 gate FAILED (stage1_pass=False in {gate_path}). "
            "Fix Stage 1 before running Stage 2."
        )


def check_stage2_gate(wrongtest_dir: Path | str) -> None:
    """Raise RuntimeError if Stage 2 gate has not passed."""
    d = Path(wrongtest_dir)
    gate_path = d / "stage2_gate_result.json"
    if not gate_path.exists():
        raise RuntimeError(
            f"Stage 2 gate result not found at {gate_path}. "
            "Run Stage 2 (forecast-error-wrongtest-stage2) first."
        )
    gates = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gates.get("stage2_pass"):
        raise RuntimeError(
            f"Stage 2 gate FAILED (stage2_pass=False in {gate_path}). "
            "Fix Stage 2 before running Stage 3."
        )


def load_wrongtest_cases(wrongtest_dir: Path) -> list[dict[str, Any]]:
    """Load the 5 wrongtest CSV paths from the manifest."""
    manifest_path = wrongtest_dir / "wrongtest_manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"wrongtest_manifest.csv not found in {wrongtest_dir}")
    df = pd.read_csv(manifest_path, encoding="utf-8-sig")
    cases = []
    for _, row in df.iterrows():
        cases.append(
            {
                "event_id": str(row["original_event_id"]),
                "wrongtest_file": str(row["wrongtest_file"]),
                "perturbation_type": str(row["perturbation_type"]),
                "forecast_column": str(row["forecast_column"]),
                "selection_reason": str(row["selection_reason"]),
            }
        )
    return cases


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def run_wrongtest_stage2(
    wrongtest_dir: Path,
    output_dir: Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Run Stage 2: deterministic rolling workflow on all 5 wrongtest events."""
    check_stage1_gate(wrongtest_dir)

    from experiments.data_adapters import RealEventDataAdapter
    from experiments.paper_validation.runners import create_method_runner
    from experiments.paper_validation.orchestrator import _build_paths
    from experiments.workflows.rolling import RollingThresholds, RollingRealDataWorkflow
    from experiments.validation.results import build_stage_record

    cases = load_wrongtest_cases(wrongtest_dir)
    timestamp = _utc_now()
    run_id = f"stage2_wrongtest_{timestamp}"

    stage2_output = output_dir / "stage2_workflow"
    stage2_output.mkdir(parents=True, exist_ok=True)
    jsonl_path = stage2_output / f"{run_id}.jsonl"

    rolling_cfg = cfg.get("rolling_real_forecast") or {}
    thresholds = RollingThresholds(
        relative_error_trigger=float(rolling_cfg.get("relative_error_trigger", 0.30)),
        absolute_error_trigger_m3s=float(rolling_cfg.get("absolute_error_trigger_m3s", 300.0)),
        high_level_margin_m=float(rolling_cfg.get("high_level_margin_m", 0.5)),
        min_remaining_horizon_hours=int(rolling_cfg.get("min_remaining_horizon_hours", 12)),
        check_interval_hours=int(rolling_cfg.get("check_interval_hours", 12)),
        scheduled_check_replan=True,
    )

    runner = create_method_runner("pyresops_direct", model_profile=None, llm_config="experiments/config/llm_config.yml")
    adapter = RealEventDataAdapter(data_root=cfg.get("data", {}).get("root", "data"))
    workflow = RollingRealDataWorkflow(
        adapter,
        runner,
        thresholds=thresholds,
        manual_instruction_offsets={},
        continue_on_stage_failure=True,
    )

    all_records: list[dict[str, Any]] = []
    event_summaries: list[dict[str, Any]] = []

    for case in cases:
        wf_path = Path(case["wrongtest_file"])
        if not wf_path.exists():
            # try relative
            wf_path = wrongtest_dir / wf_path.name
        result = workflow.run(wf_path)

        stage_results = []
        if isinstance(result.result, dict) and isinstance(result.result.get("stage_results"), list):
            stage_results = result.result["stage_results"]

        event_hard_violations = 0
        event_success = 0
        event_stages = len(result.stages)
        trigger_reasons: list[str] = []
        peak_releases: list[float] = []
        max_levels: list[float] = []
        replan_count = 0

        for idx, stage in enumerate(result.stages):
            sr = stage_results[idx] if idx < len(stage_results) else {}
            record = build_stage_record(
                run_id=run_id,
                scenario_set="forecast_error_wrongtest",
                scenario_group="wrongtest_forecast_error",
                event_id=result.event_id,
                workflow_type="rolling",
                method_id="pyresops_direct",
                model_profile="pyresops_direct",
                stage=stage,
                stage_result=sr,
                process_success=bool(sr.get("process_success", True)),
                failure_reason=sr.get("acceptance_failure_reason"),
            )
            record["perturbation_type"] = case["perturbation_type"]
            record["stage2_run"] = True
            hard_viol = bool(sr.get("hard_constraint_violation", False))
            record["hard_constraint_violation"] = hard_viol
            if hard_viol:
                event_hard_violations += 1
            if sr.get("process_success", True):
                event_success += 1
            trigger_reasons.append(stage.replan_reason or "")
            if isinstance(sr.get("outflow"), (int, float)):
                peak_releases.append(float(sr["outflow"]))
            eval_m = sr.get("evaluation_metrics") or {}
            if isinstance(eval_m.get("max_level"), (int, float)):
                max_levels.append(float(eval_m["max_level"]))
            replan_count += 1
            all_records.append(record)
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        event_summaries.append(
            {
                "event_id": result.event_id,
                "perturbation_type": case["perturbation_type"],
                "stage_count": event_stages,
                "success_count": event_success,
                "success_rate": round(event_success / max(event_stages, 1), 4),
                "hard_constraint_violation_count": event_hard_violations,
                "trigger_reasons": "|".join(trigger_reasons),
                "peak_release": round(max(peak_releases), 2) if peak_releases else None,
                "max_water_level": round(max(max_levels), 3) if max_levels else None,
                "replan_count": replan_count,
            }
        )

    # write outputs
    frame = pd.DataFrame(all_records)
    summary_csv = stage2_output / f"{run_id}_summary.csv"
    frame.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    event_summary_csv = stage2_output / "stage2_wrongtest_event_summary.csv"
    pd.DataFrame(event_summaries).to_csv(event_summary_csv, index=False, encoding="utf-8-sig")

    failure_frame = frame[frame.get("process_success", pd.Series([True] * len(frame))) != True].copy() if not frame.empty else pd.DataFrame()
    failure_audit_csv = stage2_output / f"{run_id}_failure_audit.csv"
    failure_frame.to_csv(failure_audit_csv, index=False, encoding="utf-8-sig")

    # trigger summary
    trigger_counts: dict[str, int] = {}
    for r in all_records:
        t = r.get("replan_reason") or "unknown"
        trigger_counts[t] = trigger_counts.get(t, 0) + 1
    trigger_summary_csv = stage2_output / "stage2_wrongtest_trigger_summary.csv"
    pd.DataFrame([{"trigger_reason": k, "count": v} for k, v in trigger_counts.items()]).to_csv(
        trigger_summary_csv, index=False, encoding="utf-8-sig"
    )

    total_stages = sum(e["stage_count"] for e in event_summaries)
    total_success = sum(e["success_count"] for e in event_summaries)
    total_hard = sum(e["hard_constraint_violation_count"] for e in event_summaries)
    success_rate = round(total_success / max(total_stages, 1), 4)

    # gate evaluation
    gates: dict[str, Any] = {
        "event_count": len(event_summaries),
        "event_count_pass": len(event_summaries) == 5,
        "stage_count": total_stages,
        "stage_count_pass": total_stages > 0,
        "hard_constraint_violation_count": total_hard,
        "hard_constraint_violation_pass": total_hard == 0,
        "workflow_execution_success_rate": success_rate,
        "workflow_execution_success_rate_pass": success_rate >= 0.95,
        "trigger_reason_coverage_rate": len(trigger_counts) / max(len(trigger_counts), 1),
        "failure_audit_exists": failure_audit_csv.exists(),
    }
    gates["stage2_pass"] = (
        gates["event_count_pass"]
        and gates["stage_count_pass"]
        and gates["hard_constraint_violation_pass"]
        and gates["workflow_execution_success_rate_pass"]
    )

    gate_path = wrongtest_dir / "stage2_gate_result.json"
    gate_path.write_text(json.dumps(gates, indent=2, ensure_ascii=False), encoding="utf-8")

    # summary markdown
    md_lines = [
        f"# Stage 2 Wrongtest Workflow Summary",
        f"",
        f"Run ID: `{run_id}`",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| event_count | {gates['event_count']} |",
        f"| stage_count | {gates['stage_count']} |",
        f"| success_rate | {gates['workflow_execution_success_rate']:.4f} |",
        f"| hard_constraint_violation_count | {gates['hard_constraint_violation_count']} |",
        f"| **Stage 2 PASS** | **{gates['stage2_pass']}** |",
    ]
    summary_md = stage2_output / f"{run_id}_summary.md"
    summary_md.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "stage2_pass": gates["stage2_pass"],
        "gates": gates,
        "run_id": run_id,
        "event_summaries": event_summaries,
        "paths": {
            "jsonl": jsonl_path.as_posix(),
            "summary_csv": summary_csv.as_posix(),
            "summary_md": summary_md.as_posix(),
            "failure_audit_csv": failure_audit_csv.as_posix(),
            "event_summary_csv": event_summary_csv.as_posix(),
            "trigger_summary_csv": trigger_summary_csv.as_posix(),
            "gate_path": gate_path.as_posix(),
        },
    }


def run_wrongtest_stage3(
    wrongtest_dir: Path,
    output_dir: Path,
    cfg: dict[str, Any],
    model_profile: str = "mimo_v25",
    llm_config: str = "experiments/config/llm_config.yml",
) -> dict[str, Any]:
    """Run Stage 3: MiMo + MCPTools + Skill on all 5 wrongtest events."""
    check_stage1_gate(wrongtest_dir)
    check_stage2_gate(wrongtest_dir)

    from experiments.data_adapters import RealEventDataAdapter
    from experiments.paper_validation.runners import create_method_runner
    from experiments.workflows.rolling import RollingThresholds, RollingRealDataWorkflow
    from experiments.validation.results import build_stage_record

    cases = load_wrongtest_cases(wrongtest_dir)
    timestamp = _utc_now()
    model_label = model_profile.replace("/", "_").replace(":", "_")
    run_id = f"stage3_wrongtest_{model_label}_{timestamp}"

    stage3_output = output_dir / f"stage3_{model_label}"
    stage3_output.mkdir(parents=True, exist_ok=True)
    jsonl_path = stage3_output / f"{run_id}.jsonl"

    rolling_cfg = cfg.get("rolling_real_forecast") or {}
    thresholds = RollingThresholds(
        relative_error_trigger=float(rolling_cfg.get("relative_error_trigger", 0.30)),
        absolute_error_trigger_m3s=float(rolling_cfg.get("absolute_error_trigger_m3s", 300.0)),
        high_level_margin_m=float(rolling_cfg.get("high_level_margin_m", 0.5)),
        min_remaining_horizon_hours=int(rolling_cfg.get("min_remaining_horizon_hours", 12)),
        check_interval_hours=int(rolling_cfg.get("check_interval_hours", 12)),
        scheduled_check_replan=True,
    )

    runner = create_method_runner("mimo_mcp_skill", model_profile=model_profile, llm_config=llm_config)
    adapter = RealEventDataAdapter(data_root=cfg.get("data", {}).get("root", "data"))
    workflow = RollingRealDataWorkflow(
        adapter,
        runner,
        thresholds=thresholds,
        manual_instruction_offsets={},
        continue_on_stage_failure=True,
    )

    all_records: list[dict[str, Any]] = []
    event_summaries: list[dict[str, Any]] = []

    for case in cases:
        wf_path = Path(case["wrongtest_file"])
        if not wf_path.exists():
            wf_path = wrongtest_dir / wf_path.name
        result = workflow.run(wf_path)

        stage_results = []
        if isinstance(result.result, dict) and isinstance(result.result.get("stage_results"), list):
            stage_results = result.result["stage_results"]

        event_hard_violations = 0
        event_success = 0
        event_stages = len(result.stages)
        trigger_reasons: list[str] = []
        replan_count = 0
        evidence_binding_failures = 0
        invalid_final_payloads = 0
        mcp_tool_call_successes = 0
        mcp_tool_call_total = 0
        structured_valid = 0
        eval_ref_valid = 0
        protocol_adherent = 0
        runtimes: list[float] = []

        for idx, stage in enumerate(result.stages):
            sr = stage_results[idx] if idx < len(stage_results) else {}
            record = build_stage_record(
                run_id=run_id,
                scenario_set="forecast_error_wrongtest",
                scenario_group="wrongtest_forecast_error",
                event_id=result.event_id,
                workflow_type="rolling",
                method_id="mimo_mcp_skill",
                model_profile=model_profile,
                stage=stage,
                stage_result=sr,
                process_success=bool(sr.get("process_success", result.success)),
                failure_reason=sr.get("acceptance_failure_reason"),
            )
            record["perturbation_type"] = case["perturbation_type"]
            record["stage3_run"] = True
            hard_viol = bool(sr.get("hard_constraint_violation", False))
            record["hard_constraint_violation"] = hard_viol
            if hard_viol:
                event_hard_violations += 1
            if sr.get("process_success", False):
                event_success += 1
            trigger_reasons.append(stage.replan_reason or "")
            replan_count += 1

            # MCP metrics
            tool_calls = sr.get("tool_calls_detail") or []
            for tc in tool_calls:
                mcp_tool_call_total += 1
                if tc.get("success", True):
                    mcp_tool_call_successes += 1

            if sr.get("structured_output_valid", False):
                structured_valid += 1
            if sr.get("evaluation_reference_valid", sr.get("protocol_adherent", False)):
                eval_ref_valid += 1
            if sr.get("protocol_adherent", False):
                protocol_adherent += 1
            if sr.get("acceptance_failure_reason") == "missing_evaluation_reference":
                evidence_binding_failures += 1
            if not sr.get("final_payload_valid", True):
                invalid_final_payloads += 1
            if isinstance(sr.get("total_time_seconds"), (int, float)):
                runtimes.append(float(sr["total_time_seconds"]))

            all_records.append(record)
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

        event_summaries.append(
            {
                "event_id": result.event_id,
                "perturbation_type": case["perturbation_type"],
                "stage_count": event_stages,
                "success_count": event_success,
                "success_rate": round(event_success / max(event_stages, 1), 4),
                "hard_constraint_violation_count": event_hard_violations,
                "trigger_reasons": "|".join(trigger_reasons),
                "replan_count": replan_count,
                "evidence_binding_failure_count": evidence_binding_failures,
                "invalid_final_payload_count": invalid_final_payloads,
                "mcp_tool_call_success_rate": round(mcp_tool_call_successes / max(mcp_tool_call_total, 1), 4),
                "structured_output_valid_rate": round(structured_valid / max(event_stages, 1), 4),
                "evaluation_reference_valid_rate": round(eval_ref_valid / max(event_stages, 1), 4),
                "protocol_adherence_rate": round(protocol_adherent / max(event_stages, 1), 4),
                "average_runtime_seconds": round(sum(runtimes) / len(runtimes), 2) if runtimes else None,
            }
        )

    frame = pd.DataFrame(all_records)
    summary_csv = stage3_output / f"{run_id}_summary.csv"
    frame.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    event_summary_csv = stage3_output / f"stage3_wrongtest_{model_label}_event_summary.csv"
    pd.DataFrame(event_summaries).to_csv(event_summary_csv, index=False, encoding="utf-8-sig")

    failure_frame = frame[frame.get("process_success", pd.Series([True] * len(frame))) != True].copy() if not frame.empty else pd.DataFrame()
    failure_audit_csv = stage3_output / f"{run_id}_failure_audit.csv"
    failure_frame.to_csv(failure_audit_csv, index=False, encoding="utf-8-sig")

    trigger_counts: dict[str, int] = {}
    for r in all_records:
        t = r.get("replan_reason") or "unknown"
        trigger_counts[t] = trigger_counts.get(t, 0) + 1
    trigger_summary_csv = stage3_output / f"stage3_wrongtest_{model_label}_trigger_summary.csv"
    pd.DataFrame([{"trigger_reason": k, "count": v} for k, v in trigger_counts.items()]).to_csv(
        trigger_summary_csv, index=False, encoding="utf-8-sig"
    )

    # token usage
    token_rows = []
    for r in all_records:
        usage = r.get("llm_usage") or {}
        if usage:
            token_rows.append({"event_id": r.get("event_id"), "stage_id": r.get("stage_id"), **usage})
    token_csv = stage3_output / f"stage3_wrongtest_{model_label}_token_usage.csv"
    pd.DataFrame(token_rows).to_csv(token_csv, index=False, encoding="utf-8-sig")

    total_stages = sum(e["stage_count"] for e in event_summaries)
    total_success = sum(e["success_count"] for e in event_summaries)
    total_hard = sum(e["hard_constraint_violation_count"] for e in event_summaries)
    success_rate = round(total_success / max(total_stages, 1), 4)
    mcp_rate = round(
        sum(e["mcp_tool_call_success_rate"] * e["stage_count"] for e in event_summaries)
        / max(total_stages, 1),
        4,
    )
    struct_rate = round(sum(e["structured_output_valid_rate"] * e["stage_count"] for e in event_summaries) / max(total_stages, 1), 4)
    eval_rate = round(sum(e["evaluation_reference_valid_rate"] * e["stage_count"] for e in event_summaries) / max(total_stages, 1), 4)
    proto_rate = round(sum(e["protocol_adherence_rate"] * e["stage_count"] for e in event_summaries) / max(total_stages, 1), 4)

    gates: dict[str, Any] = {
        "event_count": len(event_summaries),
        "event_count_pass": len(event_summaries) == 5,
        "stage_count": total_stages,
        "stage_count_pass": total_stages > 0,
        "success_rate": success_rate,
        "success_rate_pass": success_rate >= 0.90,
        "hard_constraint_violation_count": total_hard,
        "hard_constraint_violation_pass": total_hard == 0,
        "mcp_tool_call_success_rate": mcp_rate,
        "mcp_tool_call_success_rate_pass": mcp_rate >= 0.95,
        "structured_output_valid_rate": struct_rate,
        "structured_output_valid_rate_pass": struct_rate >= 0.90,
        "evaluation_reference_valid_rate": eval_rate,
        "evaluation_reference_valid_rate_pass": eval_rate >= 0.90,
        "protocol_adherence_rate": proto_rate,
        "protocol_adherence_rate_pass": proto_rate >= 0.90,
    }
    gates["stage3_pass"] = (
        gates["event_count_pass"]
        and gates["stage_count_pass"]
        and gates["success_rate_pass"]
        and gates["hard_constraint_violation_pass"]
    )

    gate_path = wrongtest_dir / f"stage3_gate_result_{model_label}.json"
    gate_path.write_text(json.dumps(gates, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# Stage 3 Wrongtest MiMo+MCP Summary",
        f"",
        f"Run ID: `{run_id}`  Model: `{model_profile}`",
        f"",
        f"| Metric | Value | Pass |",
        f"|--------|-------|------|",
        f"| event_count | {gates['event_count']} | {gates['event_count_pass']} |",
        f"| stage_count | {gates['stage_count']} | {gates['stage_count_pass']} |",
        f"| success_rate | {gates['success_rate']:.4f} | {gates['success_rate_pass']} |",
        f"| hard_constraint_violation_count | {gates['hard_constraint_violation_count']} | {gates['hard_constraint_violation_pass']} |",
        f"| mcp_tool_call_success_rate | {gates['mcp_tool_call_success_rate']:.4f} | {gates['mcp_tool_call_success_rate_pass']} |",
        f"| structured_output_valid_rate | {gates['structured_output_valid_rate']:.4f} | {gates['structured_output_valid_rate_pass']} |",
        f"| evaluation_reference_valid_rate | {gates['evaluation_reference_valid_rate']:.4f} | {gates['evaluation_reference_valid_rate_pass']} |",
        f"| protocol_adherence_rate | {gates['protocol_adherence_rate']:.4f} | {gates['protocol_adherence_rate_pass']} |",
        f"| **Stage 3 PASS** | **{gates['stage3_pass']}** | |",
    ]
    summary_md = stage3_output / f"{run_id}_summary.md"
    summary_md.write_text("\n".join(md_lines), encoding="utf-8")

    return {
        "stage3_pass": gates["stage3_pass"],
        "gates": gates,
        "run_id": run_id,
        "event_summaries": event_summaries,
        "paths": {
            "jsonl": jsonl_path.as_posix(),
            "summary_csv": summary_csv.as_posix(),
            "summary_md": summary_md.as_posix(),
            "failure_audit_csv": failure_audit_csv.as_posix(),
            "event_summary_csv": event_summary_csv.as_posix(),
            "trigger_summary_csv": trigger_summary_csv.as_posix(),
            "token_usage_csv": token_csv.as_posix(),
            "gate_path": gate_path.as_posix(),
        },
    }
