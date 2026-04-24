"""Simulation execution tools."""

from typing import Any

from ..domain.constraint import Constraint, ConstraintSet
from ..plugins import PluginBundleConfig
from ..services import ProgramService, SimulationService, SnapshotService
from .common import build_forecast_bundle_from_payload


def setup_simulation_tools(
    mcp_server: Any,
    simulation_service: SimulationService,
    program_service: ProgramService,
    snapshot_service: SnapshotService,
) -> None:
    """Setup simulation-related MCP tools."""

    @mcp_server.tool()
    def simulate_program(
        program_id: str,
        reservoir_id: str,
        forecast_data: dict[str, Any],
        policy_bundle: dict[str, Any] | None = None,
        plugin_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Simulate one dispatch program.

        Args:
            program_id: Dispatch program ID.
            reservoir_id: Reservoir ID.
            forecast_data: Forecast payload with `series` or shorthand inflow/rainfall arrays.

        Returns:
            Simulation result summary.
        """
        from ..domain.policy import PolicyBundle
        from ..domain.rule import DispatchRule, RuleAction, RuleSet

        program = program_service.get_program(program_id)
        if not program:
            return {"error": f"Program not found: {program_id}"}

        initial_state = snapshot_service.get_snapshot(reservoir_id)
        if not initial_state:
            return {"error": f"Snapshot not found for reservoir: {reservoir_id}"}

        forecast = build_forecast_bundle_from_payload(forecast_data)

        policy_obj = None
        if policy_bundle:
            constraints = [Constraint(**item) for item in policy_bundle.get("constraints", [])]
            rules: list[DispatchRule] = []
            for item in policy_bundle.get("rules", []):
                actions = [RuleAction(**action) for action in item.get("actions", [])]
                payload = dict(item)
                payload["actions"] = actions
                rules.append(DispatchRule(**payload))
            policy_obj = PolicyBundle(
                constraints=ConstraintSet(constraints=constraints),
                rules=RuleSet(rules=rules),
                objectives=policy_bundle.get("objectives", {}),
                directives=policy_bundle.get("directives", {}),
                metadata=policy_bundle.get("metadata", {}),
            )

        result = simulation_service.run_simulation(
            program,
            initial_state,
            forecast,
            policy_bundle=policy_obj,
            plugin_bundle=PluginBundleConfig(**plugin_bundle) if plugin_bundle else None,
        )

        payload = {
            "program_id": result.program_id,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat(),
            "max_level": result.max_level,
            "min_level": result.min_level,
            "avg_outflow": result.avg_outflow,
            "snapshot_count": len(result.snapshots),
            "decision_trace_steps": len(result.metadata.get("decision_trace", [])),
        }
        if result.metadata.get("plugin_results"):
            payload["plugin_results"] = result.metadata["plugin_results"]
        if result.metadata.get("plugin_warnings"):
            payload["plugin_warnings"] = result.metadata["plugin_warnings"]
        return payload
