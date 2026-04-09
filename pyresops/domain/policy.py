"""Policy bundle domain objects."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .constraint import ConstraintSet
from .rule import RuleSet


class PolicyBundle(BaseModel):
    """Unified policy payload consumed by orchestrator."""

    constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    rules: RuleSet = Field(default_factory=RuleSet)
    objectives: dict[str, Any] = Field(default_factory=dict)
    directives: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    """Runtime context for rule/constraint evaluation."""

    step_index: int
    state: dict[str, Any]
    inflow: float
    proposed_outflow: float
    forecast: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)
    directives: dict[str, Any] = Field(default_factory=dict)
