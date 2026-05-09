"""Rolling flood-operations MCP tools."""

from __future__ import annotations

from typing import Any

from ..domain.constraint import Constraint, ConstraintSet
from ..domain.forecast import ForecastBundle
from ..domain.policy import PolicyBundle
from ..plugins import PluginBundleConfig
from ..domain.rule import DispatchRule, RuleAction, RuleSet
from ..services.rolling_ops import RollingOpsService
from .common import build_forecast_bundle_from_payload


def setup_rolling_ops_tools(
    mcp_server: Any,
    rolling_ops_service: RollingOpsService,
    *,
    optimize_tool_name: str = "optimize_release_plan",
) -> None:
    """Setup rolling workflow MCP tools."""

    def _build_forecast_bundle(forecast_data: dict[str, Any]) -> ForecastBundle:
        return build_forecast_bundle_from_payload(forecast_data)

    def _build_policy_bundle(policy_data: dict[str, Any] | None) -> PolicyBundle | None:
        if not policy_data:
            return None

        constraints = [Constraint(**item) for item in policy_data.get("constraints", [])]

        rules: list[DispatchRule] = []
        for item in policy_data.get("rules", []):
            actions = [RuleAction(**action) for action in item.get("actions", [])]
            rule_payload = dict(item)
            rule_payload["actions"] = actions
            rules.append(DispatchRule(**rule_payload))

        return PolicyBundle(
            constraints=ConstraintSet(constraints=constraints),
            rules=RuleSet(rules=rules),
            objectives=policy_data.get("objectives", {}),
            directives=policy_data.get("directives", {}),
            metadata=policy_data.get("metadata", {}),
        )

    def optimize_release_plan(
        reservoir_id: str,
        context_id: str,
        forecast_data: dict[str, Any],
        constraints: dict[str, Any] | None = None,
        objectives: dict[str, Any] | None = None,
        task_constraints: dict[str, Any] | None = None,
        directives: dict[str, Any] | None = None,
        requested_module_type: str | None = None,
        allowed_module_types: list[str] | None = None,
        rules: list[dict[str, Any]] | None = None,
        policy_bundle: dict[str, Any] | None = None,
        plugin_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate candidate release plan and supporting evidence."""
        try:
            forecast = _build_forecast_bundle(forecast_data)
            return rolling_ops_service.optimize_release_plan(
                reservoir_id=reservoir_id,
                context_id=context_id,
                forecast=forecast,
                constraints=constraints,
                objectives=objectives,
                task_constraints=task_constraints,
                directives=directives,
                requested_module_type=requested_module_type,
                allowed_module_types=allowed_module_types,
                rules=rules,
                policy_bundle=_build_policy_bundle(policy_bundle),
                plugin_bundle=PluginBundleConfig(**plugin_bundle) if plugin_bundle else None,
            )
        except Exception as exc:
            return {"error": str(exc)}

    optimize_release_plan.__name__ = optimize_tool_name
    mcp_server.tool()(optimize_release_plan)

    @mcp_server.tool()
    def reassess_plan(
        reservoir_id: str,
        context_id: str,
        updated_external_conditions: dict[str, Any],
        rules: list[dict[str, Any]] | None = None,
        policy_bundle: dict[str, Any] | None = None,
        plugin_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reassess working plan under updated external conditions (read-only)."""
        try:
            forecast = _build_forecast_bundle(updated_external_conditions["forecast_data"])
            constraints = updated_external_conditions.get("constraints", {})
            directives = updated_external_conditions.get("directives", {})
            return rolling_ops_service.reassess_plan(
                reservoir_id=reservoir_id,
                context_id=context_id,
                forecast=forecast,
                constraints=constraints,
                directives=directives,
                rules=rules,
                policy_bundle=_build_policy_bundle(policy_bundle),
                plugin_bundle=PluginBundleConfig(**plugin_bundle) if plugin_bundle else None,
            )
        except Exception as exc:
            return {"error": str(exc)}

    @mcp_server.tool()
    def replace_working_plan(
        reservoir_id: str,
        context_id: str,
        candidate_plan_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Explicitly replace working plan with a generated candidate plan."""
        try:
            return rolling_ops_service.replace_working_plan(
                reservoir_id=reservoir_id,
                context_id=context_id,
                candidate_plan_id=candidate_plan_id,
                reason=reason,
            )
        except Exception as exc:
            return {"error": str(exc)}

    @mcp_server.tool()
    def finalize_plan(reservoir_id: str, context_id: str) -> dict[str, Any]:
        """Finalize current working plan and persist append-only records."""
        try:
            return rolling_ops_service.finalize_plan(
                reservoir_id=reservoir_id,
                context_id=context_id,
            )
        except Exception as exc:
            return {"error": str(exc)}

    @mcp_server.tool()
    def get_working_state(reservoir_id: str, context_id: str) -> dict[str, Any]:
        """Get current working state (plan + latest sim/eval)."""
        try:
            return rolling_ops_service.get_working_state(
                reservoir_id=reservoir_id,
                context_id=context_id,
            )
        except Exception as exc:
            return {"error": str(exc)}
