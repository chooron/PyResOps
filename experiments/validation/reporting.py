"""Summary report export for validation JSONL logs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.validation.results import classify_failure_taxonomy


def export_summary_report(
    jsonl_path: str | Path,
    *,
    markdown_path: str | Path,
    csv_path: str | Path,
) -> dict[str, Any]:
    """Export flat CSV and Markdown summary from stage-level JSONL."""

    records = _load_jsonl(jsonl_path)
    rows = [_flat_row(record) for record in records]
    frame = pd.DataFrame(rows)
    csv_resolved = Path(csv_path)
    csv_resolved.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_resolved, index=False, encoding="utf-8-sig")

    summary = _summary(records)
    md_resolved = Path(markdown_path)
    md_resolved.parent.mkdir(parents=True, exist_ok=True)
    md_resolved.write_text(_markdown(summary, frame), encoding="utf-8")
    return {
        "jsonl_path": Path(jsonl_path).as_posix(),
        "csv_path": csv_resolved.as_posix(),
        "markdown_path": md_resolved.as_posix(),
        "summary": summary,
    }


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    records: list[dict[str, Any]] = []
    with resolved.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _flat_row(record: dict[str, Any]) -> dict[str, Any]:
    safety = record.get("safety_status") or {}
    instruction = record.get("instruction_status") or {}
    metrics = record.get("metrics") or {}
    payload_summary = record.get("payload_summary") or {}
    return {
        "run_id": record.get("run_id"),
        "scenario_set": record.get("scenario_set"),
        "scenario_group": record.get("scenario_group"),
        "workflow_type": record.get("workflow_type"),
        "event_id": record.get("event_id"),
        "stage_id": record.get("stage_id"),
        "stage_offset_hours": record.get("stage_offset_hours"),
        "method_id": record.get("method_id"),
        "model_profile": record.get("model_profile"),
        "process_success": record.get("process_success"),
        "had_carry_over_plan": bool(record.get("had_carry_over_plan", False)),
        "safety_status": safety.get("status"),
        "hard_constraint_violations_count": safety.get("hard_constraint_violations_count"),
        "instruction_status": instruction.get("status"),
        "replan_reason": record.get("replan_reason"),
        "failure_reason": record.get("failure_reason"),
        "failure_taxonomy": record.get("failure_taxonomy")
        or classify_failure_taxonomy(
            record.get("failure_reason"),
            result=record.get("raw_result") if isinstance(record.get("raw_result"), dict) else record,
        ),
        "data_quality_status": record.get("data_quality_status", "strict_clean"),
        "event_class": _event_class(record),
        "strict_clean_eligible": bool(record.get("strict_clean_eligible", True)),
        "repaired_executable_eligible": bool(record.get("repaired_executable_eligible", True)),
        "diagnostic_only": bool(record.get("diagnostic_only", False)),
        "outflow_fallback_applied": bool(record.get("outflow_fallback_applied", False)),
        "excluded_from_clean_success_denominator": bool(
            record.get("excluded_from_clean_success_denominator")
        ),
        "excluded_from_repaired_success_denominator": bool(
            record.get("excluded_from_repaired_success_denominator")
        ),
        "source_path": payload_summary.get("source_path"),
        "raw_path": payload_summary.get("raw_path"),
        "processed_path": payload_summary.get("processed_path"),
        "uses_processed_data": bool(payload_summary.get("uses_processed_data", False)),
        "overall_score": metrics.get("overall_score"),
        "flood_control_score": metrics.get("flood_control_score"),
        "final_level_m": metrics.get("final_level_m"),
        "target_level_m": metrics.get("target_level_m"),
        "tool_call_chain": " -> ".join(record.get("tool_call_chain") or []),
    }


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    successes = sum(1 for record in records if record.get("process_success") is True)
    clean_records = [
        record
        for record in records
        if not bool(record.get("excluded_from_clean_success_denominator"))
    ]
    clean_successes = sum(1 for record in clean_records if record.get("process_success") is True)
    repaired_records = [
        record
        for record in records
        if not bool(record.get("excluded_from_repaired_success_denominator"))
    ]
    repaired_successes = sum(
        1 for record in repaired_records if record.get("process_success") is True
    )

    event_rollups = _event_rollups(records)
    raw_all_events = len(event_rollups)
    strict_clean_events = [
        event_id
        for event_id, rollup in event_rollups.items()
        if rollup["event_class"] == "strict_clean"
    ]
    repaired_executable_events = [
        event_id
        for event_id, rollup in event_rollups.items()
        if rollup["event_class"] == "repaired_executable"
    ]
    diagnostic_only_events = [
        event_id
        for event_id, rollup in event_rollups.items()
        if rollup["event_class"] == "diagnostic_only"
    ]
    strict_clean_event_successes = sum(
        1 for event_id in strict_clean_events if event_rollups[event_id]["event_success"]
    )
    repaired_executable_event_successes = sum(
        1
        for event_id in repaired_executable_events
        if event_rollups[event_id]["event_success"]
    )

    safety_counter = Counter(
        (record.get("safety_status") or {}).get("status", "unknown") for record in records
    )
    data_quality_counter = Counter(_event_class(record) for record in records)
    instruction_counter = Counter(
        (record.get("instruction_status") or {}).get("status", "unknown")
        for record in records
        if record.get("workflow_type") == "dynamic"
    )
    protocol_warning_counter = Counter(
        str((record.get("raw_result") or {}).get("protocol_warning"))
        for record in records
        if isinstance(record.get("raw_result"), dict)
        and (record.get("raw_result") or {}).get("protocol_warning")
    )
    replan_counter = Counter(
        record.get("replan_reason", "unknown")
        for record in records
        if record.get("workflow_type") == "rolling"
    )
    failures = Counter(
        str(record.get("failure_reason") or "none")
        for record in records
        if record.get("failure_reason")
        or (record.get("safety_status") or {}).get("status") not in (None, "safe")
        or record.get("process_success") is not True
    )
    failure_taxonomy = Counter()
    for record in records:
        taxonomy = record.get("failure_taxonomy") or classify_failure_taxonomy(
            record.get("failure_reason"),
            result=record.get("raw_result") if isinstance(record.get("raw_result"), dict) else record,
        )
        if taxonomy:
            failure_taxonomy[str(taxonomy)] += 1

    dynamic_records = [record for record in records if record.get("workflow_type") == "dynamic"]
    carry_over_records = [record for record in dynamic_records if record.get("had_carry_over_plan")]
    carry_over_evaluated = sum(
        1
        for record in carry_over_records
        if (record.get("tool_call_chain") or [])[:4]
        == [
            "get_reservoir_status",
            "query_dispatch_rules",
            "simulate_dispatch_program",
            "evaluate_dispatch_result",
        ]
    )
    dynamic_protocol_adherent = sum(
        1
        for record in dynamic_records
        if (
            (record.get("failure_taxonomy") or classify_failure_taxonomy(
                record.get("failure_reason"),
                result=record.get("raw_result") if isinstance(record.get("raw_result"), dict) else record,
            ))
            != "protocol"
        )
        and not ((record.get("raw_result") or {}).get("protocol_warning"))
    )

    return {
        "run_count": total,
        "success_count": successes,
        "success_rate": 0.0 if total == 0 else round(successes / total, 4),
        "raw_denominator_count": total,
        "clean_denominator_count": len(clean_records),
        "clean_success_count": clean_successes,
        "clean_success_rate": (
            0.0 if not clean_records else round(clean_successes / len(clean_records), 4)
        ),
        "repaired_denominator_count": len(repaired_records),
        "repaired_success_count": repaired_successes,
        "repaired_success_rate": (
            0.0 if not repaired_records else round(repaired_successes / len(repaired_records), 4)
        ),
        "raw_all_events": raw_all_events,
        "strict_clean_set": len(strict_clean_events),
        "repaired_executable_set": len(repaired_executable_events),
        "diagnostic_only_count": len(diagnostic_only_events),
        "strict_clean_event_success_count": strict_clean_event_successes,
        "strict_clean_event_success_rate": (
            0.0
            if not strict_clean_events
            else round(strict_clean_event_successes / len(strict_clean_events), 4)
        ),
        "repaired_executable_event_success_count": repaired_executable_event_successes,
        "repaired_executable_event_success_rate": (
            0.0
            if not repaired_executable_events
            else round(
                repaired_executable_event_successes / len(repaired_executable_events),
                4,
            )
        ),
        "diagnostic_only_events": diagnostic_only_events,
        "data_quality_blocker_count": len(diagnostic_only_events),
        "strict_clean_exclusion_count": total - len(clean_records),
        "repaired_exclusion_count": total - len(repaired_records),
        "hard_constraint_violation_count": sum(
            int((record.get("safety_status") or {}).get("hard_constraint_violations_count") or 0)
            for record in records
        ),
        "safety_status_distribution": dict(safety_counter),
        "data_quality_status_distribution": dict(data_quality_counter),
        "dynamic_instruction_status_distribution": dict(instruction_counter),
        "protocol_warning_distribution": dict(protocol_warning_counter),
        "carry_over_stage_count": len(carry_over_records),
        "carry_over_evaluation_rate": (
            0.0
            if not carry_over_records
            else round(carry_over_evaluated / len(carry_over_records), 4)
        ),
        "dynamic_protocol_adherence_rate": (
            0.0 if not dynamic_records else round(dynamic_protocol_adherent / len(dynamic_records), 4)
        ),
        "rolling_replan_reason_distribution": dict(replan_counter),
        "failure_reason_distribution": dict(failures),
        "failure_taxonomy_distribution": dict(failure_taxonomy),
    }


def _event_rollups(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        event_id = str(record.get("event_id") or "").strip()
        if not event_id:
            continue
        grouped.setdefault(event_id, []).append(record)

    rollups: dict[str, dict[str, Any]] = {}
    for event_id, group in grouped.items():
        exemplar = group[0]
        rollups[event_id] = {
            "event_class": _event_class(exemplar),
            "event_success": all(item.get("process_success") is True for item in group),
        }
    return rollups


def _event_class(record: dict[str, Any]) -> str:
    explicit = str(record.get("event_class") or "").strip()
    if explicit:
        return explicit
    if bool(record.get("diagnostic_only", False)):
        return "diagnostic_only"
    if bool(record.get("strict_clean_eligible", False)):
        return "strict_clean"
    if bool(record.get("repaired_executable_eligible", False)):
        return "repaired_executable"
    return "diagnostic_only"


def _markdown(summary: dict[str, Any], frame: pd.DataFrame) -> str:
    lines = [
        "# Minimal Real-Data Validation Summary",
        "",
        f"- Runs: {summary['run_count']}",
        f"- Raw success rate: {summary['success_rate']:.2%} "
        f"({summary['success_count']}/{summary['raw_denominator_count']})",
        f"- Strict clean success rate: {summary['clean_success_rate']:.2%} "
        f"({summary['clean_success_count']}/{summary['clean_denominator_count']})",
        f"- Repaired executable success rate: {summary['repaired_success_rate']:.2%} "
        f"({summary['repaired_success_count']}/{summary['repaired_denominator_count']})",
        f"- Raw all events: {summary['raw_all_events']}",
        f"- Strict clean set: {summary['strict_clean_set']} "
        f"(event success {summary['strict_clean_event_success_rate']:.2%})",
        f"- Repaired executable set: {summary['repaired_executable_set']} "
        f"(event success {summary['repaired_executable_event_success_rate']:.2%})",
        f"- Diagnostic only count: {summary['diagnostic_only_count']}",
        f"- Diagnostic only events: {summary['diagnostic_only_events']}",
        f"- Hard constraint violations: {summary['hard_constraint_violation_count']}",
        f"- Data quality statuses: {summary['data_quality_status_distribution']}",
        f"- Dynamic instruction statuses: {summary['dynamic_instruction_status_distribution']}",
        f"- Protocol warnings: {summary['protocol_warning_distribution']}",
        f"- Carry-over evaluation rate: {summary['carry_over_evaluation_rate']:.2%}",
        f"- Dynamic protocol adherence rate: {summary['dynamic_protocol_adherence_rate']:.2%}",
        f"- Rolling replan reasons: {summary['rolling_replan_reason_distribution']}",
        f"- Failure reasons: {summary['failure_reason_distribution']}",
        f"- Failure taxonomy: {summary['failure_taxonomy_distribution']}",
        "",
        "## Representative Results",
        "",
    ]
    if frame.empty:
        lines.append("No records.")
    else:
        columns = [
            "scenario_group",
            "workflow_type",
            "event_id",
            "stage_id",
            "method_id",
            "event_class",
            "process_success",
            "safety_status",
            "instruction_status",
            "failure_reason",
        ]
        lines.extend(_markdown_table(frame[columns].fillna("")))
    lines.append("")
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in frame.to_dict(orient="records"):
        lines.append("| " + " | ".join(str(row[column]) for column in headers) + " |")
    return lines
