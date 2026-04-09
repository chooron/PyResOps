"""Resolve rule actions into an executable outflow decision."""

from __future__ import annotations

from ..domain.rule import RuleAction


class ActionResolver:
    """Resolve normalized rule actions into outflow values."""

    def resolve_outflow(
        self, *, baseline_outflow: float, actions: list[RuleAction]
    ) -> tuple[float, list[dict]]:
        """Apply actions in order and return (resolved_outflow, adjustments)."""
        resolved = float(baseline_outflow)
        adjustments: list[dict] = []

        for action in actions:
            if action.action_type == "set_target_outflow":
                value = float(action.parameters.get("value", resolved))
                if value != resolved:
                    adjustments.append(
                        {
                            "source": "rule_action",
                            "type": "set_target_outflow",
                            "before": resolved,
                            "after": value,
                        }
                    )
                resolved = value
            elif action.action_type == "clamp_outflow":
                min_value = action.parameters.get("min")
                max_value = action.parameters.get("max")
                before = resolved
                if min_value is not None:
                    resolved = max(resolved, float(min_value))
                if max_value is not None:
                    resolved = min(resolved, float(max_value))
                if resolved != before:
                    adjustments.append(
                        {
                            "source": "rule_action",
                            "type": "clamp_outflow",
                            "before": before,
                            "after": resolved,
                            "min": min_value,
                            "max": max_value,
                        }
                    )
            elif action.action_type == "switch_mode":
                adjustments.append(
                    {
                        "source": "rule_action",
                        "type": "switch_mode",
                        "mode": action.parameters.get("mode"),
                    }
                )
            elif action.action_type == "emit_event":
                adjustments.append(
                    {
                        "source": "rule_action",
                        "type": "emit_event",
                        "event": action.parameters,
                    }
                )

        return resolved, adjustments
