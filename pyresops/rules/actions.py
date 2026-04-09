"""Rule action helpers."""

from __future__ import annotations

from ..domain.rule import RuleAction


def normalize_action(action: RuleAction) -> RuleAction:
    """Return normalized action payload with typed defaults."""
    if action.action_type == "set_target_outflow":
        if "value" in action.parameters:
            action.parameters["value"] = float(action.parameters["value"])
    elif action.action_type == "clamp_outflow":
        if "min" in action.parameters:
            action.parameters["min"] = float(action.parameters["min"])
        if "max" in action.parameters:
            action.parameters["max"] = float(action.parameters["max"])
    return action
