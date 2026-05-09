"""Structured payload schemas for paper validation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class ReservoirDecisionPayload(BaseModel):
    event_id: str
    workflow: Literal["static", "dynamic", "rolling"]
    stage_id: str | None = None
    method_level: str
    transport: Literal["mcp_tools"] | None = None
    skill_name: str | None = None
    decision_type: Literal[
        "accept",
        "retain_carry_over",
        "replan",
        "reject_infeasible",
    ]
    selected_plan_id: str | None = None
    target_release_summary: dict[str, Any] = Field(default_factory=dict)
    safety_status: Literal["safe", "unsafe", "unknown"]
    hard_constraint_violation: bool
    instruction_status: Literal[
        "satisfied",
        "partially_satisfied",
        "in_progress",
        "infeasible",
        "not_applicable",
    ]
    tool_chain_summary: list[str] = Field(default_factory=list)
    mcp_tool_chain_summary: list[str] = Field(default_factory=list)
    evaluation_reference: str | None = None
    failure_reason: str | None = None
    explanation: str


def validate_structured_payload(payload: dict[str, Any] | None) -> tuple[ReservoirDecisionPayload | None, str | None]:
    if not isinstance(payload, dict):
        return None, "invalid_final_payload"
    try:
        return ReservoirDecisionPayload.model_validate(payload), None
    except ValidationError:
        return None, "invalid_final_payload"
