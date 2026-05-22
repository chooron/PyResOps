"""Stage 3 session trace logger: JSONL persistence for per-call LLM+MCP traces."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.paper_validation.mcp_skill_runner import MCP_TRACE_DEFAULTS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    return uuid.uuid4().hex[:16]


class SessionTraceLogger:
    """Append JSONL trace records to per-workflow trace files."""

    def __init__(self, traces_dir: str | Path, session_id: str | None = None) -> None:
        self.traces_dir = Path(traces_dir)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or _new_session_id()
        self._handles: dict[str, Any] = {}

    # ------------------------------------------------------------------
    def log(
        self,
        *,
        event_id: str,
        workflow_type: str,
        workflow_stage: str,
        model_profile: str,
        raw_result: dict[str, Any],
        validation_result: Any,  # ValidationResult from fail_closed_validator
        stage_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build and persist one trace record; return the record dict."""
        trace = self._build_record(
            event_id=event_id,
            workflow_type=workflow_type,
            workflow_stage=workflow_stage,
            model_profile=model_profile,
            raw_result=raw_result,
            validation_result=validation_result,
            stage_payload=stage_payload,
        )
        self._append(workflow_type, trace)
        return trace

    def close(self) -> None:
        for fh in self._handles.values():
            try:
                fh.close()
            except Exception:
                pass
        self._handles.clear()

    # ------------------------------------------------------------------
    def _build_record(
        self,
        *,
        event_id: str,
        workflow_type: str,
        workflow_stage: str,
        model_profile: str,
        raw_result: dict[str, Any],
        validation_result: Any,
        stage_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        llm_trace: dict[str, Any] = raw_result.get("llm_execution_trace") or {}
        tool_events: list[dict[str, Any]] = llm_trace.get("tool_events") or []

        tool_inputs_summary = [
            {"tool": e.get("tool_name"), "input_keys": list((e.get("input") or {}).keys())}
            for e in tool_events
        ]
        tool_outputs_summary = [
            {
                "tool": e.get("tool_name"),
                "success": e.get("success", True),
                "output_keys": list((e.get("output") or {}).keys()) if isinstance(e.get("output"), dict) else [],
            }
            for e in tool_events
        ]

        record: dict[str, Any] = {
            "session_id": self.session_id,
            "recorded_at": _utc_now(),
            "event_id": event_id,
            "workflow_type": workflow_type,
            "workflow_stage": workflow_stage,
            "model_profile": model_profile,
            # tool chain
            "tool_call_sequence": raw_result.get("mcp_tool_call_sequence") or [],
            "tool_call_count": raw_result.get("mcp_tool_call_count", 0),
            "tool_inputs_summary": tool_inputs_summary,
            "tool_outputs_summary": tool_outputs_summary,
            # evidence
            "eval_ref_id": raw_result.get("final_evaluation_reference"),
            "available_eval_refs": raw_result.get("available_evaluation_references") or [],
            # payload
            "final_payload": raw_result.get("accepted_evidence_pair"),
            # validation
            "accepted": validation_result.accepted,
            "tool_order_valid": validation_result.tool_order_valid,
            "eval_ref_valid": validation_result.eval_ref_valid,
            "schema_valid": validation_result.schema_valid,
            "hard_violation": validation_result.hard_violation,
            "downstream_violation": validation_result.downstream_violation,
            "failure_reason": validation_result.failure_reason,
            # MCP connection
            "mcp_connect_success": raw_result.get("mcp_connect_success", False),
            "mcp_error_message": raw_result.get("mcp_error_message"),
            # scenario context (lightweight)
            "stage_payload_id": (stage_payload or {}).get("id"),
            "stage_payload_event_id": (stage_payload or {}).get("event_id"),
        }

        # Merge MCP_TRACE_DEFAULTS fields present in raw_result
        for key in MCP_TRACE_DEFAULTS:
            if key not in record and key in raw_result:
                record[key] = raw_result[key]

        return record

    def _append(self, workflow_type: str, record: dict[str, Any]) -> None:
        key = workflow_type
        if key not in self._handles:
            path = self.traces_dir / f"{workflow_type}_traces.jsonl"
            self._handles[key] = path.open("a", encoding="utf-8")
        fh = self._handles[key]
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        fh.flush()
