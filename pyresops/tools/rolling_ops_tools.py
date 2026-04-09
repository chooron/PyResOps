"""Rolling flood-operations MCP tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..domain.constraint import Constraint, ConstraintSet
from ..domain.forecast import ForecastBundle, ForecastSeries
from ..domain.policy import PolicyBundle
from ..domain.rule import DispatchRule, RuleAction, RuleSet
from ..services.rolling_ops import RollingOpsService


def setup_rolling_ops_tools(mcp_server: Any, rolling_ops_service: RollingOpsService) -> None:
    """Setup rolling workflow MCP tools."""

    def _build_forecast_bundle(forecast_data: dict[str, Any]) -> ForecastBundle:
        timestamps = [datetime.fromisoformat(ts) for ts in forecast_data["timestamps"]]
        inflow_values = [float(v) for v in forecast_data["inflow_values"]]
        if len(timestamps) != len(inflow_values):
            raise ValueError("forecast_data timestamps and inflow_values length mismatch")

        return ForecastBundle(
            forecast_time=datetime.now(),
            series=[
                ForecastSeries(
                    variable="inflow",
                    timestamps=timestamps,
                    values=inflow_values,
                    unit="m3/s",
                )
            ],
        )

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

    @mcp_server.tool()
    def optimize_flexible_release_plan(
        reservoir_id: str,
        context_id: str,
        horizon_hours: int,
        control_interval_seconds: int,
        forecast_data: dict[str, Any],
        constraints: dict[str, Any] | None = None,
        objectives: dict[str, Any] | None = None,
        directives: dict[str, Any] | None = None,
        rules: list[dict[str, Any]] | None = None,
        policy_bundle: dict[str, Any] | None = None,
        optimizer_backend: str | None = None,
    ) -> dict[str, Any]:
        """Generate candidate flexible-release plan and supporting evidence."""
        try:
            forecast = _build_forecast_bundle(forecast_data)
            result = rolling_ops_service.optimize_flexible_release_plan(
                reservoir_id=reservoir_id,
                context_id=context_id,
                horizon_hours=horizon_hours,
                control_interval_seconds=control_interval_seconds,
                forecast=forecast,
                constraints=constraints,
                objectives=objectives,
                directives=directives,
                rules=rules,
                policy_bundle=_build_policy_bundle(policy_bundle),
                optimizer_backend=optimizer_backend,
            )
            return result
        except Exception as exc:
            return {"error": str(exc)}

    @mcp_server.tool()
    def reassess_plan(
        reservoir_id: str,
        context_id: str,
        updated_external_conditions: dict[str, Any],
        rules: list[dict[str, Any]] | None = None,
        policy_bundle: dict[str, Any] | None = None,
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
        """Explicitly replace working plan with candidate plan."""
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
