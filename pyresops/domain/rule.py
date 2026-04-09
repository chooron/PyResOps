"""Rule domain objects for policy-driven dispatch."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RuleActionType = Literal[
    "set_target_outflow",
    "clamp_outflow",
    "switch_mode",
    "emit_event",
]


class RuleAction(BaseModel):
    """Rule action payload."""

    action_type: RuleActionType
    parameters: dict[str, Any] = Field(default_factory=dict)


class DispatchRule(BaseModel):
    """Dispatch rule definition."""

    id: str
    name: str
    condition: dict[str, Any] = Field(default_factory=dict)
    actions: list[RuleAction] = Field(default_factory=list)
    priority: int = Field(default=100)
    enabled: bool = Field(default=True)
    stop_on_match: bool = Field(default=False)
    impl_class: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleSet(BaseModel):
    """Rule collection."""

    rules: list[DispatchRule] = Field(default_factory=list)

    def enabled_rules(self) -> list[DispatchRule]:
        """Return enabled rules sorted by priority then id."""
        return sorted(
            (rule for rule in self.rules if rule.enabled),
            key=lambda item: (-item.priority, item.id),
        )
