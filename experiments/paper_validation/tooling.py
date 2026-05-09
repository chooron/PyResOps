"""Paper-validation tool surfaces for local Agno tools and MCP wrappers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from experiments.paper_validation.execution import (
    evaluate_release_plan_payload,
    optimize_release_plan_payload,
    parse_module_parameters,
    prepare_event_payload,
    simulate_release_plan_payload,
)
from pyresops.modules import ALLOWED_BASE_RELEASE_MODULE_TYPES


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


class PaperLocalToolBundleFactory:
    """Create paper-validation local tools with auditable names."""

    def __init__(self, spec, scenario_resolver=None):
        self.spec = spec
        self._scenario_resolver = scenario_resolver

    def resolve_scenario(self, scenario_id: str, runtime_scenario: dict[str, Any] | None = None) -> dict[str, Any]:
        if runtime_scenario and runtime_scenario.get("id") == scenario_id:
            return runtime_scenario
        if self._scenario_resolver is None:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")
        scenario = self._scenario_resolver(scenario_id)
        if scenario is None:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")
        return scenario

    def make_tools(self, runtime_scenario: dict[str, Any] | None = None):
        try:
            from agno.tools import tool as agno_tool
        except ImportError as exc:
            raise RuntimeError("Agno is required to create paper-validation tools.") from exc

        spec = self.spec

        def get_scenario(scenario_id: str) -> dict[str, Any]:
            return self.resolve_scenario(scenario_id, runtime_scenario)

        @agno_tool
        def prepare_event(scenario_id: str) -> str:
            payload = prepare_event_payload(get_scenario(scenario_id), spec)
            return _json(payload)

        @agno_tool
        def optimize_release_plan(scenario_id: str, requested_module_type: str = "") -> str:
            payload = optimize_release_plan_payload(
                get_scenario(scenario_id),
                spec,
                requested_module_type=requested_module_type.strip() or None,
                use_prediction=get_scenario(scenario_id).get("workflow_type") == "rolling",
            )
            return _json(payload)

        @agno_tool
        def simulate_release_plan(
            scenario_id: str,
            target_outflow: float,
            module_type: str = "constant_release",
            module_parameters_json: str = "",
        ) -> str:
            if module_type not in ALLOWED_BASE_RELEASE_MODULE_TYPES:
                raise ValueError(f"Unsupported module_type: {module_type}")
            scenario = get_scenario(scenario_id)
            module_parameters = parse_module_parameters(
                module_type,
                float(target_outflow),
                module_parameters_json or None,
            )
            payload = simulate_release_plan_payload(
                scenario,
                spec,
                target_outflow=float(target_outflow),
                module_type=module_type,
                module_parameters=module_parameters,
            )
            return _json(payload["summary"])

        @agno_tool
        def evaluate_release_plan(
            scenario_id: str,
            target_outflow: float,
            module_type: str = "constant_release",
            module_parameters_json: str = "",
        ) -> str:
            if module_type not in ALLOWED_BASE_RELEASE_MODULE_TYPES:
                raise ValueError(f"Unsupported module_type: {module_type}")
            scenario = get_scenario(scenario_id)
            module_parameters = parse_module_parameters(
                module_type,
                float(target_outflow),
                module_parameters_json or None,
            )
            sim_payload = simulate_release_plan_payload(
                scenario,
                spec,
                target_outflow=float(target_outflow),
                module_type=module_type,
                module_parameters=module_parameters,
            )
            eval_payload = evaluate_release_plan_payload(
                scenario,
                spec,
                target_outflow=float(target_outflow),
                module_type=module_type,
                module_parameters=module_parameters,
                simulation_result=sim_payload["simulation_result"],
            )
            return _json(eval_payload["summary"])

        return [
            prepare_event,
            optimize_release_plan,
            simulate_release_plan,
            evaluate_release_plan,
        ]


def setup_paper_validation_mcp_tools(mcp_server: Any, runtime) -> None:
    """Register paper-validation workflow wrapper tools on the MCP server."""

    spec = runtime.reservoir_spec

    @mcp_server.tool()
    def prepare_event(scenario: dict[str, Any]) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        return prepare_event_payload(scenario, spec)

    @mcp_server.tool()
    def optimize_release_plan(
        scenario: dict[str, Any],
        requested_module_type: str = "",
    ) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        return optimize_release_plan_payload(
            scenario,
            spec,
            requested_module_type=requested_module_type.strip() or None,
            use_prediction=scenario.get("workflow_type") == "rolling",
        )

    @mcp_server.tool()
    def simulate_release_plan(
        scenario: dict[str, Any],
        target_outflow: float,
        module_type: str = "constant_release",
        module_parameters_json: str = "",
    ) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        module_parameters = parse_module_parameters(
            module_type,
            float(target_outflow),
            module_parameters_json or None,
        )
        payload = simulate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(target_outflow),
            module_type=module_type,
            module_parameters=module_parameters,
        )
        return payload["summary"]

    @mcp_server.tool()
    def evaluate_release_plan(
        scenario: dict[str, Any],
        target_outflow: float,
        module_type: str = "constant_release",
        module_parameters_json: str = "",
    ) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        module_parameters = parse_module_parameters(
            module_type,
            float(target_outflow),
            module_parameters_json or None,
        )
        sim_payload = simulate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(target_outflow),
            module_type=module_type,
            module_parameters=module_parameters,
        )
        eval_payload = evaluate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(target_outflow),
            module_type=module_type,
            module_parameters=module_parameters,
            simulation_result=sim_payload["simulation_result"],
        )
        return eval_payload["summary"]

    @mcp_server.tool()
    def validate_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
        from experiments.paper_validation.schema import validate_structured_payload

        decision, failure = validate_structured_payload(payload)
        return {
            "valid": failure is None,
            "failure_reason": failure,
            "payload": decision.model_dump(mode="json") if decision is not None else None,
        }

    @mcp_server.tool()
    def check_hard_constraints(evaluation_payload: dict[str, Any]) -> dict[str, Any]:
        count = int(evaluation_payload.get("hard_constraint_violations_count") or 0)
        return {
            "hard_constraint_violation": count > 0,
            "hard_constraint_violations_count": count,
            "hard_constraint_violations": evaluation_payload.get("hard_constraint_violations", []),
            "safety_status": "unsafe" if count > 0 else "safe",
        }

    @mcp_server.tool()
    def run_static_workflow(scenario: dict[str, Any]) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        prep = prepare_event_payload(scenario, spec)
        opt = optimize_release_plan_payload(scenario, spec, use_prediction=False)
        sim = simulate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(opt["avg_release_m3s"]),
            module_type=str(opt["selected_module_type"]),
            module_parameters=dict(opt["selected_module_parameters"]),
        )
        evaluation = evaluate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(opt["avg_release_m3s"]),
            module_type=str(opt["selected_module_type"]),
            module_parameters=dict(opt["selected_module_parameters"]),
            simulation_result=sim["simulation_result"],
        )
        return {
            "prepare_event": prep,
            "optimize_release_plan": opt,
            "simulate_release_plan": sim["summary"],
            "evaluate_release_plan": evaluation["summary"],
        }

    @mcp_server.tool()
    def run_dynamic_stage(scenario: dict[str, Any]) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        return run_static_workflow(scenario)

    @mcp_server.tool()
    def run_rolling_stage(scenario: dict[str, Any]) -> dict[str, Any]:
        scenario = _normalize_mcp_scenario(scenario)
        prep = prepare_event_payload(scenario, spec)
        opt = optimize_release_plan_payload(scenario, spec, use_prediction=True)
        sim = simulate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(opt["avg_release_m3s"]),
            module_type=str(opt["selected_module_type"]),
            module_parameters=dict(opt["selected_module_parameters"]),
        )
        evaluation = evaluate_release_plan_payload(
            scenario,
            spec,
            target_outflow=float(opt["avg_release_m3s"]),
            module_type=str(opt["selected_module_type"]),
            module_parameters=dict(opt["selected_module_parameters"]),
            simulation_result=sim["simulation_result"],
        )
        return {
            "prepare_event": prep,
            "optimize_release_plan": opt,
            "simulate_release_plan": sim["summary"],
            "evaluate_release_plan": evaluation["summary"],
        }


def _normalize_mcp_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Restore Python types lost across JSON MCP transport."""

    normalized = dict(scenario)
    start_time = normalized.get("start_time")
    if isinstance(start_time, str):
        normalized["start_time"] = datetime.fromisoformat(start_time)
    return normalized
