"""Decision trace domain objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .rule import RuleAction


class ViolationRecord(BaseModel):
    """Normalized violation output."""

    constraint_id: str
    constraint_name: str
    violation_type: str
    severity: str = "major"
    enforcement: str = "hard"
    scope: str = "global"
    step_index: int | None = None
    value: float | None = None
    limit: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return backward-compatible dictionary payload."""
        payload: dict[str, Any] = {
            "constraint_id": self.constraint_id,
            "constraint_name": self.constraint_name,
            "violation_type": self.violation_type,
        }
        if self.step_index is not None:
            payload["step_index"] = self.step_index
        if self.value is not None:
            payload["value"] = self.value
        if self.limit is not None:
            payload["limit"] = self.limit
        payload.update(self.details)
        payload["severity"] = self.severity
        payload["enforcement"] = self.enforcement
        payload["scope"] = self.scope
        return payload


class DecisionTraceStep(BaseModel):
    """Trace item for one simulation step."""

    step_index: int
    timestamp: datetime
    active_module: str | None = None
    rule_hits: list[str] = Field(default_factory=list)
    actions: list[RuleAction] = Field(default_factory=list)
    proposed_outflow: float = 0.0
    resolved_outflow: float = 0.0
    adjustments: list[dict[str, Any]] = Field(default_factory=list)
    violations: list[ViolationRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionOutcome(BaseModel):
    """Final resolved decision."""

    outflow: float
    rule_hits: list[str] = Field(default_factory=list)
    actions: list[RuleAction] = Field(default_factory=list)
    adjustments: list[dict[str, Any]] = Field(default_factory=list)
    violations: list[ViolationRecord] = Field(default_factory=list)
    fallback_used: bool = False
