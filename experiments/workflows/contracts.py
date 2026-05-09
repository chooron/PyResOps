"""Shared workflow contract objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STATIC_S01_CHAIN = [
    "get_reservoir_status",
    "query_dispatch_rules",
    "optimize_release_plan",
    "simulate_dispatch_program",
    "evaluate_dispatch_result",
]


@dataclass(frozen=True)
class WorkflowContract:
    workflow_type: str
    description: str
    fixed_inputs: list[str]
    tool_chain: list[str]
    state_update_rules: list[str]
    output_schema: dict[str, Any]
    failure_conditions: list[str]


@dataclass(frozen=True)
class WorkflowStage:
    stage_id: str
    offset_hours: int
    payload: dict[str, Any]
    operator_instruction: str = ""
    replan_required: bool = True
    replan_reason: str = "initial_plan"


@dataclass(frozen=True)
class WorkflowExecutionResult:
    workflow_type: str
    event_id: str
    contract: WorkflowContract
    stages: list[WorkflowStage]
    success: bool
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "event_id": self.event_id,
            "success": self.success,
            "failure_reason": self.failure_reason,
            "contract": {
                "workflow_type": self.contract.workflow_type,
                "description": self.contract.description,
                "fixed_inputs": self.contract.fixed_inputs,
                "tool_chain": self.contract.tool_chain,
                "state_update_rules": self.contract.state_update_rules,
                "output_schema": self.contract.output_schema,
                "failure_conditions": self.contract.failure_conditions,
            },
            "stages": [
                {
                    "stage_id": stage.stage_id,
                    "offset_hours": stage.offset_hours,
                    "scenario_id": stage.payload["id"],
                    "operator_instruction": stage.operator_instruction,
                    "replan_required": stage.replan_required,
                    "replan_reason": stage.replan_reason,
                    "payload_summary": {
                        "source_path": stage.payload["data_source"]["path"],
                        "start_time": stage.payload["start_time"].isoformat(),
                        "time_step_hours": stage.payload["time_step_hours"],
                        "duration_hours": stage.payload["duration_hours"],
                        "series_length": len(stage.payload["benchmark_inflow_series_m3s"]),
                        "uses_synthetic_data": stage.payload["data_source"]["uses_synthetic_data"],
                    },
                }
                for stage in self.stages
            ],
            "result": self.result,
            "diagnostics": self.diagnostics,
        }


COMMON_OUTPUT_SCHEMA = {
    "success": "bool",
    "process_success": "bool",
    "tool_call_chain": "list[str]",
    "protocol_warning": "str | null",
    "state_trace": "list[dict]",
    "dispatch_plan": "dict",
    "evaluation_metrics": "dict",
    "safety_status": "dict(priority=1, status, hard_constraint_violations_count)",
    "instruction_status": "dict(priority=2, status=completed|in_progress|unknown)",
    "failure_reason": "str | null",
}


COMMON_FAILURE_CONDITIONS = [
    "missing_required_csv_column",
    "non_uniform_or_invalid_time_step",
    "missing_required_value_inside_workflow_horizon",
    "agno_not_installed",
    "model_api_key_missing",
    "unexpected_tool_chain",
    "untrustworthy_tool_result",
    "non_json_or_schema_invalid_agent_output",
    "workflow_process_blocked",
]
