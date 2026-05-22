"""Method-level runners for paper validation."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from experiments.paper_validation.execution import (
    evaluate_release_plan_payload,
    optimize_release_plan_payload,
    prepare_event_payload,
    simulate_release_plan_payload,
)
from experiments.paper_validation.schema import ReservoirDecisionPayload, validate_structured_payload
from experiments.paper_validation.tooling import PaperLocalToolBundleFactory
from pyresops.agents.config_loader import AgentModelConfigLoader
from pyresops.agents.model_builder import build_agno_model
from pyresops.agents.runner import ReservoirAgentRunner
from pyresops.agents.specs import load_default_experiment_spec
from pyresops.agents.runtime import ReservoirAgentRuntime


@dataclass(frozen=True)
class MethodRegistration:
    method_id: str
    method_level: str
    runner_kind: str


METHOD_REGISTRY = {
    "pyresops_direct": MethodRegistration("pyresops_direct", "L0", "pyresops_direct"),
    "tools_only": MethodRegistration("tools_only", "L1", "tools_only"),
    "mimo_without_tools": MethodRegistration("mimo_without_tools", "L2", "mimo_without_tools"),
    "mimo_with_pyresops_tools": MethodRegistration(
        "mimo_with_pyresops_tools",
        "L3",
        "mimo_with_pyresops_tools",
    ),
    "mimo_mcp_no_skill": MethodRegistration(
        "mimo_mcp_no_skill",
        "B3",
        "true_mcp_no_skill",
    ),
    "mimo_mcp_validator": MethodRegistration(
        "mimo_mcp_validator",
        "L4",
        "true_mcp_skill",
    ),
    "mimo_mcp_skill": MethodRegistration(
        "mimo_mcp_skill",
        "B4",
        "true_mcp_skill",
    ),
}


def registered_method_levels() -> dict[str, str]:
    return {method_id: registration.method_level for method_id, registration in METHOD_REGISTRY.items()}


class DirectLibraryRunner:
    model_id = "pyresops-direct"
    model_profile = "pyresops_direct"

    def __init__(self):
        self.spec = load_default_experiment_spec()

    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        started_at = ReservoirAgentRunner._utc_now()
        wall_start = time.time()
        prep = prepare_event_payload(payload, self.spec)
        opt = optimize_release_plan_payload(
            payload,
            self.spec,
            use_prediction=payload.get("workflow_type") == "rolling",
        )
        sim = simulate_release_plan_payload(
            payload,
            self.spec,
            target_outflow=float(opt["avg_release_m3s"]),
            module_type=str(opt["selected_module_type"]),
            module_parameters=dict(opt["selected_module_parameters"]),
        )
        evaluation = evaluate_release_plan_payload(
            payload,
            self.spec,
            target_outflow=float(opt["avg_release_m3s"]),
            module_type=str(opt["selected_module_type"]),
            module_parameters=dict(opt["selected_module_parameters"]),
            simulation_result=sim["simulation_result"],
        )
        finished_at = ReservoirAgentRunner._utc_now()
        final_payload = _synthesized_decision_payload(
            payload=payload,
            method_level="L0",
            decision_type="accept",
            tool_chain_summary=["direct_api"],
            evaluation_reference=f"direct::{payload['id']}",
            target_release_m3s=float(opt["avg_release_m3s"]),
            safety_status="unsafe"
            if int(evaluation["summary"]["hard_constraint_violations_count"]) > 0
            else "safe",
            hard_constraint_violation=bool(evaluation["summary"]["hard_constraint_violations_count"]),
            instruction_status=_instruction_status_label(evaluation["summary"]),
            explanation="Direct PyResOps API execution baseline.",
            selected_plan_id=str(opt["program_id"]),
        )
        result = {
            "scenario_id": payload["id"],
            "method": "pyresops_direct",
            "model": self.model_id,
            "success": True,
            "outflow": round(float(opt["avg_release_m3s"]), 3),
            "reasoning": "Direct PyResOps API execution baseline.",
            "constraint_check": "Evaluated by PyResOps EvaluationService.",
            "process_success": True,
            "protocol_warning": None,
            "safety_status": ReservoirAgentRunner._derive_safety_status(evaluation["summary"]),
            "instruction_status": ReservoirAgentRunner._derive_instruction_status(
                scenario=payload,
                evaluation_payload=evaluation["summary"],
            ),
            "parse_warning": None,
            "parsed_from": "dict",
            "final_decision_text": json.dumps(final_payload, ensure_ascii=False),
            "tool_call_count": 0,
            "tool_call_chain": ["direct_api"],
            "tool_calls_detail": [],
            "llm_execution_trace": {
                "started_at": started_at,
                "finished_at": finished_at,
                "tool_events": [],
                "attempts": 1,
            },
            "accepted_attempt_index": 1,
            "acceptance_failure_reason": None,
            "accepted_evidence_pair": {"final_payload": final_payload},
            "total_time_seconds": round(time.time() - wall_start, 3),
            "llm_temperature": 0.0,
            "llm_seed": None,
            "llm_usage": None,
            "llm_usage_log_path": None,
            "evaluation_metrics": evaluation["summary"],
            "direct_artifacts": {
                "prepare_event": prep,
                "optimize_release_plan": opt,
                "simulate_release_plan": sim["summary"],
                "evaluate_release_plan": evaluation["summary"],
            },
        }
        return result


class PaperAgentRunnerBase:
    def __init__(self, *, model_profile: str | None, config_path: str | None):
        self._loader = AgentModelConfigLoader()
        self._model_cfg = self._loader.load(profile=model_profile, config_path=config_path)
        self.model_profile = model_profile or str(self._model_cfg.get("profile", ""))
        self.model_id = str(self._model_cfg.get("model_id", "unknown"))
        self._validator = ReservoirAgentRunner()
        self.spec = load_default_experiment_spec()

    def _run_agent(self, *, payload: dict[str, Any], tools: list[Any], system_prompt: str) -> dict[str, Any]:
        try:
            from agno.agent import Agent
        except ImportError as exc:
            raise RuntimeError("Agno is required for paper-validation MiMo runs.") from exc

        model = build_agno_model(self._model_cfg, temperature=0.0, seed=None)
        agent = Agent(model=model, tools=tools, instructions=system_prompt, markdown=False)
        prompt = _paper_user_message(payload)
        started_at = ReservoirAgentRunner._utc_now()
        wall_start = time.time()
        response = agent.run(prompt)
        finished_at = ReservoirAgentRunner._utc_now()
        final_text = str(getattr(response, "content", "") or "")
        payload_json = ReservoirAgentRunner._extract_json_payload(final_text)
        tool_events = ReservoirAgentRunner._tool_events(response)
        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed": round(time.time() - wall_start, 3),
            "prompt": prompt,
            "final_text": final_text,
            "payload_json": payload_json,
            "tool_events": tool_events,
            "tool_chain": [event["tool_name"] for event in tool_events],
        }


class TextOnlyRunner(PaperAgentRunnerBase):
    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        run = self._run_agent(payload=payload, tools=[], system_prompt=_paper_system_prompt(payload, "L2"))
        decision, failure_reason = validate_structured_payload(run["payload_json"])
        diagnostics = _ablation_payload_diagnostics(
            raw_payload=run["payload_json"],
            decision=decision,
            schema_failure=failure_reason,
            method_level="L2",
        )
        if failure_reason is None and decision is not None:
            result = _decision_result_from_schema(
                payload=payload,
                decision=decision,
                run=run,
                method="mimo_without_tools",
                model_id=self.model_id,
                method_level="L2",
                spec=self.spec,
            )
            result.update(diagnostics)
            return result
        result = _invalid_payload_result(
            payload=payload,
            run=run,
            method="mimo_without_tools",
            model_id=self.model_id,
            failure_reason=failure_reason or "invalid_final_payload",
        )
        result.update(diagnostics)
        return result


class LocalToolsRunner(PaperAgentRunnerBase):
    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        tools = PaperLocalToolBundleFactory(self.spec).make_tools(runtime_scenario=payload)
        run = self._run_agent(payload=payload, tools=tools, system_prompt=_paper_system_prompt(payload, "L3"))
        decision, failure_reason = validate_structured_payload(run["payload_json"])
        protocol_failure = _paper_protocol_failure(payload, run["tool_chain"], decision)
        if failure_reason is None and protocol_failure is None and decision is not None:
            return _decision_result_from_schema(
                payload=payload,
                decision=decision,
                run=run,
                method="mimo_with_pyresops_tools",
                model_id=self.model_id,
                method_level="L3",
                spec=self.spec,
            )
        return _invalid_payload_result(
            payload=payload,
            run=run,
            method="mimo_with_pyresops_tools",
            model_id=self.model_id,
            failure_reason=protocol_failure or failure_reason or "invalid_final_payload",
        )


class MCPValidatorRunner(PaperAgentRunnerBase):
    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._run_async(payload))

    async def _run_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from agno.agent import Agent
            from agno.tools.mcp import MCPTools
        except ImportError as exc:
            raise RuntimeError("Agno MCPTools is required for L4 paper validation.") from exc

        async with MCPTools(
            command="uv run python -m pyresops.server",
            include_tools=[
                "run_static_workflow",
                "run_dynamic_stage",
                "run_rolling_stage",
            ],
            timeout_seconds=20,
        ) as mcp_tools:
            model = build_agno_model(self._model_cfg, temperature=0.0, seed=None)
            agent = Agent(
                model=model,
                tools=[mcp_tools],
                instructions=_paper_system_prompt(payload, "L4", mcp_wrapper_only=True),
                markdown=False,
            )
            prompt = _paper_user_message(payload)
            started_at = ReservoirAgentRunner._utc_now()
            wall_start = time.time()
            response = await agent.arun(prompt) if hasattr(agent, "arun") else agent.run(prompt)
            finished_at = ReservoirAgentRunner._utc_now()
            final_text = str(getattr(response, "content", "") or "")
            payload_json = ReservoirAgentRunner._extract_json_payload(final_text)
            tool_events = ReservoirAgentRunner._tool_events(response)
            tool_chain = [event["tool_name"] for event in tool_events]
            decision, failure_reason = validate_structured_payload(payload_json)
            protocol_failure = _paper_protocol_failure(payload, tool_chain, decision, mcp_wrapper_only=True)
            run = {
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed": round(time.time() - wall_start, 3),
                "prompt": prompt,
                "final_text": final_text,
                "payload_json": payload_json,
                "tool_events": tool_events,
                "tool_chain": tool_chain,
            }
            if failure_reason is None and protocol_failure is None and decision is not None:
                return _decision_result_from_schema(
                    payload=payload,
                    decision=decision,
                    run=run,
                    method="mimo_mcp_validator",
                    model_id=self.model_id,
                    method_level="L4",
                    spec=self.spec,
                )
            return _invalid_payload_result(
                payload=payload,
                run=run,
                method="mimo_mcp_validator",
                model_id=self.model_id,
                failure_reason=protocol_failure or failure_reason or "invalid_final_payload",
            )


class StableValidatedAgentRunner:
    """Use the existing validated Agno local-tool runtime and synthesize paper payloads."""

    def __init__(self, *, model_profile: str | None, config_path: str | None, method_id: str, method_level: str):
        self._runtime = ReservoirAgentRuntime(
            model_profile=model_profile,
            config_path=config_path,
            max_attempts=1,
        )
        self.model_profile = self._runtime.model_profile
        self.model_id = self._runtime.model_id
        self.method_id = method_id
        self.method_level = method_level

    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._runtime.run_scenario(payload)
        process_success = bool(result.get("process_success", result.get("success", False)))
        paper_payload = _synthesized_decision_payload(
            payload=payload,
            method_level=self.method_level,
            decision_type=_decision_type_from_runtime(payload, result),
            tool_chain_summary=list(result.get("tool_call_chain", [])),
            evaluation_reference=f"runtime::{payload['id']}",
            target_release_m3s=float(result.get("outflow") or 0.0),
            safety_status="unsafe" if ((result.get("safety_status") or {}).get("status") == "hard_constraint_violation") else "safe",
            hard_constraint_violation=bool(((result.get("safety_status") or {}).get("hard_constraint_violations_count") or 0) > 0),
            instruction_status=_paper_instruction_status_from_runtime(result),
            explanation=str(result.get("reasoning") or "Validated Agno tool execution."),
            selected_plan_id=None,
        )
        result["paper_method_level"] = self.method_level
        result["structured_output_valid"] = True
        result["protocol_adherent"] = bool(process_success and not result.get("protocol_warning"))
        result["command_following_success"] = process_success
        result["infeasible_command_detected"] = paper_payload["decision_type"] == "reject_infeasible"
        result["paper_decision_payload"] = paper_payload
        result["accepted_evidence_pair"] = {"final_payload": paper_payload} if process_success else result.get("accepted_evidence_pair")
        return result


def create_method_runner(
    method_id: str,
    *,
    model_profile: str | None = None,
    llm_config: str | None = None,
):
    registration = METHOD_REGISTRY.get(method_id)
    if registration is None:
        raise ValueError(f"Unsupported paper-validation method_id: {method_id}")
    if registration.runner_kind == "pyresops_direct":
        return DirectLibraryRunner()
    if registration.runner_kind == "tools_only":
        from experiments.validation.deterministic import DeterministicToolRunner

        return DeterministicToolRunner()
    if registration.runner_kind == "mimo_without_tools":
        return TextOnlyRunner(model_profile=model_profile, config_path=llm_config)
    if registration.runner_kind == "mimo_with_pyresops_tools":
        return StableValidatedAgentRunner(
            model_profile=model_profile,
            config_path=llm_config,
            method_id=method_id,
            method_level=registration.method_level,
        )
    if registration.runner_kind in {"true_mcp_skill", "true_mcp_no_skill"}:
        from experiments.paper_validation.config import load_paper_validation_config
        from experiments.paper_validation.mcp_skill_runner import TrueMcpSkillRunner

        return TrueMcpSkillRunner(
            model_profile=model_profile,
            config_path=llm_config,
            paper_config=load_paper_validation_config(),
            method_id=method_id,
            method_level=registration.method_level,
            skill_enabled=registration.runner_kind == "true_mcp_skill",
        )
    raise ValueError(f"Unhandled runner kind: {registration.runner_kind}")


def _paper_system_prompt(payload: dict[str, Any], method_level: str, *, mcp_wrapper_only: bool = False) -> str:
    workflow = str(payload.get("workflow_type", "static"))
    if mcp_wrapper_only:
        wrapper_name = {
            "static": "run_static_workflow",
            "dynamic": "run_dynamic_stage",
            "rolling": "run_rolling_stage",
        }[workflow]
        protocol = f"Use exactly one MCP workflow wrapper tool: {wrapper_name}. Do not call any other tool."
    elif workflow == "static":
        protocol = (
            "Use the protocol prepare_event -> optimize_release_plan -> simulate_release_plan -> "
            "evaluate_release_plan -> final_answer. Call optimize_release_plan exactly once. "
            "Do not optimize after evaluation."
        )
    elif workflow == "dynamic":
        protocol = (
            "If carry_over_plan is present, first evaluate it with "
            "simulate_release_plan -> evaluate_release_plan. Only then either retain it or "
            "replan with optimize_release_plan -> simulate_release_plan -> evaluate_release_plan."
        )
    else:
        protocol = (
            "Use prepare_event before planning. Replan only when justified by forecast-error or safety context."
        )
    tool_rule = (
        "No tool use is allowed." if method_level == "L2" else "Use tools only; no free-form reasoning without tool grounding."
    )
    return (
        "You are a reservoir-dispatch validation assistant.\n"
        f"Method level: {method_level}\n"
        f"{tool_rule}\n"
        f"{protocol}\n"
        "Return strict JSON only and conform exactly to this schema:\n"
        "{"
        "\"event_id\":\"str\","
        "\"workflow\":\"static|dynamic|rolling\","
        "\"stage_id\":\"str|null\","
        "\"method_level\":\"str\","
        "\"decision_type\":\"accept|retain_carry_over|replan|reject_infeasible\","
        "\"selected_plan_id\":\"str|null\","
        "\"target_release_summary\":{\"target_release_m3s\":123.4},"
        "\"safety_status\":\"safe|unsafe|unknown\","
        "\"hard_constraint_violation\":false,"
        "\"instruction_status\":\"satisfied|partially_satisfied|in_progress|infeasible|not_applicable\","
        "\"tool_chain_summary\":[\"prepare_event\"],"
        "\"evaluation_reference\":\"str|null\","
        "\"failure_reason\":null,"
        "\"explanation\":\"str\""
        "}"
    )


def _paper_user_message(payload: dict[str, Any]) -> str:
    command = payload.get("command_challenge") or {}
    return (
        f"event_id={payload['data_source']['event_id']}\n"
        f"workflow={payload['workflow_type']}\n"
        f"stage_id={payload.get('id')}\n"
        f"current_level={payload['current_level']}\n"
        f"target_level={payload['target_level']}\n"
        f"initial_inflow={payload['initial_inflow']}\n"
        f"time_step_hours={payload['time_step_hours']}\n"
        f"series_length={len(payload['benchmark_inflow_series_m3s'])}\n"
        f"command_id={command.get('command_id', '')}\n"
        f"command_type={command.get('command_type', '')}\n"
        f"evaluation_focus={command.get('evaluation_focus', '')}\n"
        f"operator_instruction={payload.get('operator_instruction','')}\n"
    )


def _decision_result_from_schema(
    *,
    payload: dict[str, Any],
    decision: ReservoirDecisionPayload,
    run: dict[str, Any],
    method: str,
    model_id: str,
    method_level: str,
    spec,
) -> dict[str, Any]:
    target_release = float(decision.target_release_summary.get("target_release_m3s", 0.0))
    if decision.decision_type == "reject_infeasible":
        safety_status = {"priority": 1, "status": "safe", "hard_constraints_satisfied": True, "hard_constraint_violations_count": 0, "hard_constraint_violations": []}
        instruction_status = {"priority": 2, "status": "infeasible", "completed": False, "process_failure": False}
        metrics = {"overall_score": 0.0, "hard_constraint_violations_count": 0, "instruction_violations_count": 0}
        outflow = None
    else:
        sim = simulate_release_plan_payload(
            payload,
            spec,
            target_outflow=target_release,
            module_type=str(decision.target_release_summary.get("module_type", "constant_release")),
            module_parameters=dict(decision.target_release_summary.get("module_parameters") or {"target_release": target_release}),
        )
        evaluation = evaluate_release_plan_payload(
            payload,
            spec,
            target_outflow=target_release,
            module_type=str(decision.target_release_summary.get("module_type", "constant_release")),
            module_parameters=dict(decision.target_release_summary.get("module_parameters") or {"target_release": target_release}),
            simulation_result=sim["simulation_result"],
        )
        safety_status = ReservoirAgentRunner._derive_safety_status(evaluation["summary"])
        instruction_status = ReservoirAgentRunner._derive_instruction_status(
            scenario=payload,
            evaluation_payload=evaluation["summary"],
        )
        metrics = evaluation["summary"]
        outflow = target_release

    return {
        "scenario_id": payload["id"],
        "method": method,
        "model": model_id,
        "success": True,
        "outflow": outflow,
        "reasoning": decision.explanation,
        "constraint_check": decision.evaluation_reference or "",
        "process_success": True,
        "protocol_warning": None,
        "safety_status": safety_status,
        "instruction_status": instruction_status,
        "parse_warning": None,
        "parsed_from": "json",
        "final_decision_text": run["final_text"],
        "tool_call_count": len(run["tool_chain"]),
        "tool_call_chain": run["tool_chain"],
        "tool_calls_detail": [
            {"call_order": event["call_order"], "tool_name": event["tool_name"]}
            for event in run["tool_events"]
        ],
        "llm_execution_trace": {
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "user_message": run["prompt"],
            "tool_events": run["tool_events"],
            "attempts": 1,
        },
        "accepted_attempt_index": 1,
        "acceptance_failure_reason": None,
        "accepted_evidence_pair": {"final_payload": decision.model_dump(mode="json")},
        "total_time_seconds": run["elapsed"],
        "llm_temperature": 0.0,
        "llm_seed": None,
        "llm_usage": None,
        "llm_usage_log_path": None,
        "evaluation_metrics": metrics,
        "paper_method_level": method_level,
        "structured_output_valid": True,
        "protocol_adherent": True,
        "command_following_success": decision.instruction_status in {"satisfied", "partially_satisfied", "in_progress", "infeasible"},
        "infeasible_command_detected": decision.decision_type == "reject_infeasible",
        "paper_decision_payload": decision.model_dump(mode="json"),
    }


def _invalid_payload_result(
    *,
    payload: dict[str, Any],
    run: dict[str, Any],
    method: str,
    model_id: str,
    failure_reason: str,
) -> dict[str, Any]:
    return {
        "scenario_id": payload["id"],
        "method": method,
        "model": model_id,
        "success": False,
        "outflow": None,
        "reasoning": "",
        "constraint_check": "",
        "process_success": False,
        "protocol_warning": None,
        "safety_status": {"priority": 1, "status": "unknown", "hard_constraints_satisfied": None, "hard_constraint_violations_count": 0, "hard_constraint_violations": []},
        "instruction_status": {"priority": 2, "status": "unknown", "completed": None, "process_failure": False},
        "parse_warning": failure_reason,
        "parsed_from": "none",
        "final_decision_text": run["final_text"],
        "tool_call_count": len(run["tool_chain"]),
        "tool_call_chain": run["tool_chain"],
        "tool_calls_detail": [
            {"call_order": event["call_order"], "tool_name": event["tool_name"]}
            for event in run["tool_events"]
        ],
        "llm_execution_trace": {
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "user_message": run["prompt"],
            "tool_events": run["tool_events"],
            "attempts": 1,
        },
        "accepted_attempt_index": None,
        "acceptance_failure_reason": failure_reason,
        "accepted_evidence_pair": None,
        "total_time_seconds": run["elapsed"],
        "llm_temperature": 0.0,
        "llm_seed": None,
        "llm_usage": None,
        "llm_usage_log_path": None,
        "evaluation_metrics": {},
        "paper_method_level": METHOD_REGISTRY[method].method_level if method in METHOD_REGISTRY else "unknown",
        "structured_output_valid": False,
        "protocol_adherent": False,
        "command_following_success": False,
        "infeasible_command_detected": False,
        "paper_decision_payload": None,
    }


def _ablation_payload_diagnostics(
    *,
    raw_payload: dict[str, Any] | None,
    decision: ReservoirDecisionPayload | None,
    schema_failure: str | None,
    method_level: str,
) -> dict[str, Any]:
    required = {
        "event_id",
        "workflow",
        "method_level",
        "decision_type",
        "target_release_summary",
        "safety_status",
        "hard_constraint_violation",
        "instruction_status",
        "explanation",
    }
    missing = sorted(required - set(raw_payload or {})) if isinstance(raw_payload, dict) else sorted(required)
    target_summary = raw_payload.get("target_release_summary") if isinstance(raw_payload, dict) else None
    target_release = target_summary.get("target_release_m3s") if isinstance(target_summary, dict) else None
    executable = decision is not None and schema_failure is None and target_release is not None
    evaluation_reference = decision.evaluation_reference if decision is not None else None
    hallucinated_reference = bool(method_level == "L2" and evaluation_reference)
    return {
        "executable_plan": bool(executable),
        "missing_required_field_count": len(missing),
        "missing_required_fields": missing,
        "missing_required_field": bool(missing),
        "hallucinated_value": hallucinated_reference,
        "hallucinated_value_count": 1 if hallucinated_reference else 0,
        "evaluation_reference_valid": not hallucinated_reference and bool(evaluation_reference),
    }


def _paper_protocol_failure(
    payload: dict[str, Any],
    tool_chain: list[str],
    decision: ReservoirDecisionPayload | None,
    *,
    mcp_wrapper_only: bool = False,
) -> str | None:
    workflow = str(payload.get("workflow_type", "static"))
    if mcp_wrapper_only:
        expected = {
            "static": ["run_static_workflow"],
            "dynamic": ["run_dynamic_stage"],
            "rolling": ["run_rolling_stage"],
        }[workflow]
        if tool_chain != expected:
            return "unexpected_tool_chain"
        return "invalid_final_payload" if decision is None else None
    if workflow == "static":
        counts = {name: tool_chain.count(name) for name in ["prepare_event", "optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]}
        if counts["optimize_release_plan"] > 1:
            return "repeated_static_optimization"
        if counts["simulate_release_plan"] > 1:
            return "repeated_static_simulation"
        if counts["evaluate_release_plan"] > 1:
            return "repeated_static_evaluation"
        if any(counts[name] == 0 for name in counts):
            return "missing_required_tool"
        if tool_chain[:4] != ["prepare_event", "optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]:
            return "wrong_tool_order"
        if decision is None:
            return "invalid_final_payload"
    if workflow == "dynamic":
        has_carry_over = bool(payload.get("carry_over_plan"))
        if has_carry_over:
            prefix = ["prepare_event", "simulate_release_plan", "evaluate_release_plan"]
            if tool_chain[:3] != prefix:
                return "missing_carry_over_evaluation"
            if "optimize_release_plan" in tool_chain:
                if tool_chain[-3:] != ["optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]:
                    return "missing_dynamic_replan_evaluation"
                if tool_chain.count("optimize_release_plan") > 1:
                    return "repeated_dynamic_optimization"
                if tool_chain.count("simulate_release_plan") > 2:
                    return "repeated_dynamic_simulation"
        else:
            if tool_chain[:4] != ["prepare_event", "optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]:
                return "unexpected_dynamic_tool_chain"
    return None


def _instruction_status_label(metrics: dict[str, Any]) -> str:
    count = int(metrics.get("instruction_violations_count") or 0)
    return "satisfied" if count == 0 else "in_progress"


def _paper_instruction_status_from_runtime(result: dict[str, Any]) -> str:
    status = str((result.get("instruction_status") or {}).get("status") or "unknown")
    mapping = {
        "completed": "satisfied",
        "in_progress": "in_progress",
        "unknown": "not_applicable",
    }
    return mapping.get(status, "partially_satisfied")


def _decision_type_from_runtime(payload: dict[str, Any], result: dict[str, Any]) -> str:
    chain = list(result.get("tool_call_chain", []))
    if payload.get("carry_over_plan"):
        return "replan" if "optimize_release_plan" in chain else "retain_carry_over"
    return "accept"


def _synthesized_decision_payload(
    *,
    payload: dict[str, Any],
    method_level: str,
    decision_type: str,
    tool_chain_summary: list[str],
    evaluation_reference: str,
    target_release_m3s: float,
    safety_status: str,
    hard_constraint_violation: bool,
    instruction_status: str,
    explanation: str,
    selected_plan_id: str | None = None,
) -> dict[str, Any]:
    return ReservoirDecisionPayload(
        event_id=str(payload["data_source"]["event_id"]),
        workflow=str(payload["workflow_type"]),
        stage_id=str(payload["id"]),
        method_level=method_level,
        decision_type=decision_type,
        selected_plan_id=selected_plan_id,
        target_release_summary={
            "target_release_m3s": round(float(target_release_m3s), 3),
            "module_type": "constant_release",
            "module_parameters": {"target_release": round(float(target_release_m3s), 3)},
        },
        safety_status=safety_status,
        hard_constraint_violation=hard_constraint_violation,
        instruction_status=instruction_status,
        tool_chain_summary=tool_chain_summary,
        evaluation_reference=evaluation_reference,
        failure_reason=None,
        explanation=explanation,
    ).model_dump(mode="json")
