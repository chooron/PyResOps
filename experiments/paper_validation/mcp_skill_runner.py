"""True Agno MCPTools runner for reservoir operation skill validation."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.paper_validation.schema import ReservoirDecisionPayload, validate_structured_payload
from pyresops.agents.config_loader import AgentModelConfigLoader
from pyresops.agents.model_builder import build_agno_model
from pyresops.agents.runner import ReservoirAgentRunner


CORE_MCP_SKILL_TOOLS = [
    "prepare_event",
    "optimize_release_plan",
    "simulate_release_plan",
    "evaluate_release_plan",
    "run_static_workflow",
    "run_dynamic_stage",
    "run_rolling_stage",
    "validate_decision_payload",
    "check_hard_constraints",
]

MCP_SKILL_AGENT_TOOLS = [
    "prepare_event",
    "optimize_release_plan",
    "simulate_release_plan",
    "evaluate_release_plan",
    "validate_decision_payload",
    "check_hard_constraints",
]

MCP_TRACE_DEFAULTS: dict[str, Any] = {
    "transport": "mcp_tools",
    "skill_enabled": True,
    "skill_name": None,
    "mcp_transport": None,
    "mcp_url_or_command": None,
    "mcp_connect_success": False,
    "mcp_tools_list_success": False,
    "mcp_available_tool_names": [],
    "available_tool_names": [],
    "mcp_tool_call_sequence": [],
    "mcp_tool_call_count": 0,
    "mcp_tool_call_success_count": 0,
    "mcp_tool_call_failure_count": 0,
    "mcp_structured_result_count": 0,
    "mcp_unstructured_result_count": 0,
    "mcp_structured_content_rate": 0.0,
    "mcp_error_message": None,
    "mcp_session_error": None,
    "final_payload_valid": False,
    "final_payload_validation_error": None,
    "protocol_adherence": False,
}


@dataclass(frozen=True)
class McpSkillConnectionConfig:
    transport: str
    url: str | None
    command: str | None
    connect_timeout_seconds: int
    call_timeout_seconds: int
    refresh_connection: bool
    reservoir_config_path: str | None

    @property
    def endpoint_label(self) -> str | None:
        return self.url if self.transport in {"streamable-http", "sse"} else self.command


class TrueMcpSkillRunner:
    """Execute paper-validation stages through Agno MCPTools only."""

    model_profile: str
    model_id: str
    method_id = "mimo_mcp_validator"
    method_level = "L4"

    def __init__(
        self,
        *,
        model_profile: str | None,
        config_path: str | None,
        paper_config: dict[str, Any] | None = None,
        method_id: str = "mimo_mcp_validator",
        method_level: str = "L4",
    ):
        self._model_cfg = AgentModelConfigLoader().load(profile=model_profile, config_path=config_path)
        self.model_profile = model_profile or str(self._model_cfg.get("profile", ""))
        self.model_id = str(self._model_cfg.get("model_id", "unknown"))
        self.method_id = method_id
        self.method_level = method_level
        self._paper_config = paper_config or {}
        self._mcp_cfg = _load_mcp_config(self._paper_config)
        self._validate_model_config()

    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._run_async(payload))

    async def _run_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        started_at = ReservoirAgentRunner._utc_now()
        wall_start = time.time()
        trace = dict(MCP_TRACE_DEFAULTS)
        workflow = str(payload.get("workflow_type", "static"))
        skill_name = f"{workflow}_operation_skill"
        trace.update(
            {
                "skill_name": skill_name,
                "mcp_transport": self._mcp_cfg.transport,
                "mcp_url_or_command": self._mcp_cfg.endpoint_label,
            }
        )
        mcp_tools = None
        model = None
        try:
            from agno.agent import Agent
            from agno.tools.mcp import MCPTools
        except ImportError as exc:
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason="mcp_server_error",
                error_message=f"Agno MCPTools is required: {exc}",
                tool_events=[],
                final_text="",
            )

        try:
            mcp_tools = MCPTools(
                **_mcp_tools_kwargs(self._mcp_cfg),
                include_tools=MCP_SKILL_AGENT_TOOLS,
                timeout_seconds=self._mcp_cfg.call_timeout_seconds,
                refresh_connection=self._mcp_cfg.refresh_connection,
            )
            await asyncio.wait_for(mcp_tools.connect(), timeout=self._mcp_cfg.connect_timeout_seconds)
            if getattr(mcp_tools, "session", None) is None or not getattr(mcp_tools, "initialized", False):
                raise RuntimeError("MCPTools did not initialize a session")
            trace["mcp_connect_success"] = True
            available = sorted(getattr(mcp_tools, "functions", {}).keys())
            trace["mcp_available_tool_names"] = available
            trace["available_tool_names"] = available
            trace["mcp_tools_list_success"] = bool(available)
        except TimeoutError:
            await _close_mcp_tools(mcp_tools)
            await _drain_async_cleanup()
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason="mcp_timeout",
                error_message="Timed out connecting to MCP server",
                tool_events=[],
                final_text="",
            )
        except Exception as exc:
            await _close_mcp_tools(mcp_tools)
            await _drain_async_cleanup()
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason="mcp_connect_failed",
                error_message=f"{type(exc).__name__}: {exc}",
                tool_events=[],
                final_text="",
            )

        prompt = _mcp_skill_user_message(payload, self.method_level, skill_name)
        instructions = _load_skill_instructions(workflow, self.method_level)
        if not instructions:
            await _close_mcp_tools(mcp_tools)
            await _drain_async_cleanup()
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason="skill_instruction_not_loaded",
                error_message="Missing MCP reservoir operation skill instructions",
                tool_events=[],
                final_text="",
            )

        try:
            model = build_agno_model(self._model_cfg, temperature=0.0, seed=None)
            agent = Agent(
                model=model,
                tools=[mcp_tools],
                instructions=instructions,
                markdown=False,
            )
            response = await agent.arun(prompt) if hasattr(agent, "arun") else agent.run(prompt)
            final_text = str(getattr(response, "content", "") or "")
            payload_json = ReservoirAgentRunner._extract_json_payload(final_text)
            tool_events = ReservoirAgentRunner._tool_events(response)
        except TimeoutError:
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason="mcp_timeout",
                error_message="Timed out during MCP agent call",
                tool_events=[],
                final_text="",
            )
        except Exception as exc:
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason="mcp_tool_call_failed",
                error_message=f"{type(exc).__name__}: {exc}",
                tool_events=[],
                final_text="",
            )
        finally:
            await _close_agno_model(model)
            await _close_mcp_tools(mcp_tools)
            await _drain_async_cleanup()

        finished_at = ReservoirAgentRunner._utc_now()
        tool_chain = [str(event.get("tool_name")) for event in tool_events]
        trace.update(_mcp_trace_from_tool_events(trace, tool_events))
        payload_json = _normalize_final_payload(
            payload_json,
            workflow=workflow,
            method_level=self.method_level,
            skill_name=skill_name,
            tool_chain=tool_chain,
        )
        decision, payload_failure = validate_structured_payload(payload_json)
        payload_failure = _mcp_payload_failure(decision, payload_failure, tool_chain)
        protocol_failure = validate_skill_protocol(
            workflow=workflow,
            tool_chain=tool_chain,
            final_payload=decision.model_dump(mode="json") if decision else None,
            stage_payload=payload,
        )
        failure_reason = protocol_failure or payload_failure
        trace["final_payload_valid"] = payload_failure is None and decision is not None
        trace["final_payload_validation_error"] = payload_failure
        trace["protocol_adherence"] = protocol_failure is None
        if failure_reason is not None:
            return self._failure_result(
                payload=payload,
                started_at=started_at,
                elapsed=time.time() - wall_start,
                trace=trace,
                failure_reason=failure_reason,
                error_message=failure_reason,
                tool_events=tool_events,
                final_text=final_text,
            )
        assert decision is not None
        hard_violation = bool(decision.hard_constraint_violation)
        if hard_violation:
            failure_reason = "hard_constraint_violation"
        result = {
            "scenario_id": payload["id"],
            "method": self.method_id,
            "model": self.model_id,
            "success": not hard_violation,
            "outflow": _target_release(decision),
            "reasoning": decision.explanation,
            "constraint_check": decision.evaluation_reference or "",
            "process_success": not hard_violation,
            "protocol_warning": None,
            "safety_status": {
                "priority": 1,
                "status": "hard_constraint_violation" if hard_violation else decision.safety_status,
                "hard_constraints_satisfied": not hard_violation,
                "hard_constraint_violations_count": 1 if hard_violation else 0,
                "hard_constraint_violations": [],
            },
            "instruction_status": {
                "priority": 2,
                "status": _instruction_status_to_runtime(decision.instruction_status),
                "completed": decision.instruction_status == "satisfied",
                "process_failure": False,
            },
            "parse_warning": None,
            "parsed_from": "json",
            "final_decision_text": final_text,
            "tool_call_count": len(tool_chain),
            "tool_call_chain": tool_chain,
            "tool_calls_detail": [
                {"call_order": event.get("call_order"), "tool_name": event.get("tool_name")}
                for event in tool_events
            ],
            "llm_execution_trace": {
                "started_at": started_at,
                "finished_at": finished_at,
                "user_message": prompt,
                "tool_events": tool_events,
                "attempts": 1,
            },
            "accepted_attempt_index": 1 if not hard_violation else None,
            "acceptance_failure_reason": failure_reason,
            "accepted_evidence_pair": {"final_payload": decision.model_dump(mode="json")},
            "total_time_seconds": round(time.time() - wall_start, 3),
            "llm_temperature": 0.0,
            "llm_seed": None,
            "llm_usage": str(getattr(response, "metrics", None)),
            "llm_usage_log_path": None,
            "evaluation_metrics": _last_evaluation_payload(tool_events),
            "paper_method_level": self.method_level,
            "structured_output_valid": True,
            "protocol_adherent": True,
            "command_following_success": decision.instruction_status
            in {"satisfied", "partially_satisfied", "in_progress", "infeasible"},
            "infeasible_command_detected": decision.decision_type == "reject_infeasible",
            "paper_decision_payload": decision.model_dump(mode="json"),
            **trace,
        }
        return result

    def _failure_result(
        self,
        *,
        payload: dict[str, Any],
        started_at: str,
        elapsed: float,
        trace: dict[str, Any],
        failure_reason: str,
        error_message: str,
        tool_events: list[dict[str, Any]],
        final_text: str,
    ) -> dict[str, Any]:
        trace = dict(trace)
        trace["mcp_error_message"] = error_message
        trace["mcp_session_error"] = error_message
        trace.update(_mcp_trace_from_tool_events(trace, tool_events))
        return {
            "scenario_id": payload.get("id"),
            "method": self.method_id,
            "model": self.model_id,
            "success": False,
            "outflow": None,
            "reasoning": "",
            "constraint_check": "",
            "process_success": False,
            "protocol_warning": failure_reason,
            "safety_status": {
                "priority": 1,
                "status": "unknown",
                "hard_constraints_satisfied": None,
                "hard_constraint_violations_count": 0,
                "hard_constraint_violations": [],
            },
            "instruction_status": {"priority": 2, "status": "unknown", "completed": None, "process_failure": True},
            "parse_warning": failure_reason,
            "parsed_from": "none",
            "final_decision_text": final_text,
            "tool_call_count": len(tool_events),
            "tool_call_chain": [str(event.get("tool_name")) for event in tool_events],
            "tool_calls_detail": [
                {"call_order": event.get("call_order"), "tool_name": event.get("tool_name")}
                for event in tool_events
            ],
            "llm_execution_trace": {
                "started_at": started_at,
                "finished_at": ReservoirAgentRunner._utc_now(),
                "tool_events": tool_events,
                "attempts": 1,
            },
            "accepted_attempt_index": None,
            "acceptance_failure_reason": failure_reason,
            "accepted_evidence_pair": None,
            "total_time_seconds": round(elapsed, 3),
            "llm_temperature": 0.0,
            "llm_seed": None,
            "llm_usage": None,
            "llm_usage_log_path": None,
            "evaluation_metrics": {},
            "paper_method_level": self.method_level,
            "structured_output_valid": False,
            "protocol_adherent": False,
            "command_following_success": False,
            "infeasible_command_detected": False,
            "paper_decision_payload": None,
            **trace,
        }

    def _validate_model_config(self) -> None:
        api_key = self._model_cfg.get("api_key") or os.getenv("MIMO_API_KEY")
        if not api_key:
            raise ValueError("MIMO_API_KEY is required for mcp-skill runner")
        if os.getenv("MIMO_BASE_URL"):
            self._model_cfg["base_url"] = os.getenv("MIMO_BASE_URL")


def _load_mcp_config(cfg: dict[str, Any]) -> McpSkillConnectionConfig:
    mcp = dict((cfg.get("mcp") or {}) if isinstance(cfg, dict) else {})
    transport = str(mcp.get("transport") or "stdio")
    url = mcp.get("url")
    command = mcp.get("command") or "uv run python -m pyresops.server"
    if transport in {"streamable-http", "sse"} and not url:
        raise ValueError("mcp.url is required for HTTP MCP transport")
    if transport in {"stdio", "command"} and not command:
        raise ValueError("mcp.command is required for stdio MCP transport")
    if transport == "command":
        transport = "stdio"
    return McpSkillConnectionConfig(
        transport=transport,
        url=str(url) if url else None,
        command=str(command) if command else None,
        connect_timeout_seconds=int(mcp.get("connect_timeout_seconds") or 30),
        call_timeout_seconds=int(mcp.get("call_timeout_seconds") or 120),
        refresh_connection=bool(mcp.get("refresh_connection", False)),
        reservoir_config_path=str(mcp.get("reservoir_config_path") or "experiments/config/default_reservoir.yaml"),
    )


def _mcp_tools_kwargs(cfg: McpSkillConnectionConfig) -> dict[str, Any]:
    env = {}
    if cfg.reservoir_config_path:
        env["PYRESOPS_RESERVOIR_CONFIG"] = cfg.reservoir_config_path
    if cfg.transport in {"streamable-http", "sse"}:
        return {"transport": cfg.transport, "url": cfg.url, "env": env or None}
    return {"transport": "stdio", "command": cfg.command, "env": env or None}


async def _close_mcp_tools(mcp_tools: Any | None) -> None:
    if mcp_tools is None:
        return
    close = getattr(mcp_tools, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:
        # Cleanup errors are surfaced through the stage trace when they affect execution.
        pass


async def _close_agno_model(model: Any | None) -> None:
    if model is None:
        return
    for attr in ("async_client", "client"):
        client = getattr(model, attr, None)
        await _close_client(client)


async def _close_client(client: Any | None) -> None:
    if client is None:
        return
    is_closed = getattr(client, "is_closed", None)
    try:
        if callable(is_closed) and is_closed():
            return
        if isinstance(is_closed, bool) and is_closed:
            return
    except Exception:
        pass
    close = getattr(client, "close", None) or getattr(client, "aclose", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:
        pass


async def _drain_async_cleanup(timeout_seconds: float = 2.0) -> None:
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
    if pending:
        done, _ = await asyncio.wait(pending, timeout=timeout_seconds)
        for task in done:
            if task.cancelled():
                continue
            try:
                task.exception()
            except Exception:
                pass
    await asyncio.sleep(0)


def _load_skill_instructions(workflow: str, method_level: str) -> str:
    root = Path(__file__).resolve().parent / "skills"
    common = root / "common_safety_skill.md"
    workflow_file = root / f"{workflow}_operation_skill.md"
    if not common.exists() or not workflow_file.exists():
        return ""
    schema = (
        "Return strict JSON only with fields: event_id, workflow, stage_id, method_level, "
        "transport, skill_name, decision_type, selected_plan_id, target_release_summary, "
        "safety_status, hard_constraint_violation, instruction_status, tool_chain_summary, "
        "mcp_tool_chain_summary, evaluation_reference, failure_reason, explanation. "
        "Set transport to mcp_tools and method_level to "
        f"{method_level}."
    )
    return "\n\n".join(
        [
            common.read_text(encoding="utf-8"),
            workflow_file.read_text(encoding="utf-8"),
            schema,
        ]
    )


def _mcp_skill_user_message(payload: dict[str, Any], method_level: str, skill_name: str) -> str:
    scenario_json = json.dumps(payload, ensure_ascii=False, default=str)
    rolling_fields = _rolling_trigger_fields(payload)
    carry_over = payload.get("carry_over_plan")
    dynamic_carry_rule = ""
    if payload.get("workflow_type") == "dynamic" and carry_over:
        dynamic_carry_rule = (
            "MANDATORY DYNAMIC CARRY-OVER FIRST TWO CALLS: "
            "1) simulate_release_plan using carry_over_plan values; "
            "2) evaluate_release_plan for that same carry_over_plan. "
            "Do not call optimize_release_plan until both carry-over calls are complete.\n"
            f"carry_over_plan: {json.dumps(carry_over, ensure_ascii=False, default=str)}\n"
        )
    return (
        "Run the reservoir operation stage using PyResOps MCP tools only.\n"
        f"event_id: {payload['data_source']['event_id']}\n"
        f"scenario_id: {payload['id']}\n"
        f"workflow: {payload.get('workflow_type')}\n"
        f"stage_id: {payload.get('id')}\n"
        f"method_level: {method_level}\n"
        f"skill_name: {skill_name}\n"
        f"rolling_trigger_context: {json.dumps(rolling_fields, ensure_ascii=False)}\n"
        f"{dynamic_carry_rule}"
        "Use the JSON object below as the exact `scenario` argument for MCP tools.\n"
        f"SCENARIO_JSON:\n{scenario_json}\n"
    )


def _rolling_trigger_fields(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data_source") or {}
    observed = float(payload.get("initial_inflow") or 0.0)
    predicted = float(payload.get("predicted_mean_inflow", observed) or observed)
    absolute = abs(observed - predicted)
    relative = absolute / max(abs(predicted), 1.0)
    return {
        "trigger_time": payload.get("stage_offset_hours"),
        "forecast_error_type": data.get("forecast_error_pattern"),
        "trigger_reason": payload.get("replan_reason"),
        "relative_forecast_error": round(relative, 6),
        "absolute_forecast_error": round(absolute, 6),
        "whether_replan": True,
    }


def validate_skill_protocol(
    *,
    workflow: str,
    tool_chain: list[str],
    final_payload: dict[str, Any] | None,
    stage_payload: dict[str, Any] | None = None,
) -> str | None:
    if workflow == "static":
        counts = {name: tool_chain.count(name) for name in ["prepare_event", "optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]}
        if counts["optimize_release_plan"] > 1:
            return "repeated_static_optimization"
        if counts["optimize_release_plan"] == 0:
            return "missing_required_tool"
        if counts["simulate_release_plan"] == 0 or counts["evaluate_release_plan"] == 0:
            return "missing_required_tool"
        if tool_chain[:4] != ["prepare_event", "optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]:
            return "wrong_tool_order"
        return None
    if workflow == "dynamic":
        has_carry = bool((stage_payload or {}).get("carry_over_plan"))
        if has_carry:
            if tool_chain[:2] != ["simulate_release_plan", "evaluate_release_plan"]:
                return "missing_carry_over_evaluation"
            if "optimize_release_plan" in tool_chain:
                opt_index = tool_chain.index("optimize_release_plan")
                if opt_index < 2:
                    return "missing_carry_over_evaluation"
                if tool_chain[opt_index : opt_index + 3] != ["optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]:
                    return "missing_dynamic_replan_evaluation"
        else:
            expected = ["prepare_event", "optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]
            compact_expected = ["optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"]
            if tool_chain[:4] != expected and tool_chain[:3] != compact_expected:
                return "wrong_tool_order"
        return None
    if workflow == "rolling":
        trigger_reason = (stage_payload or {}).get("replan_reason")
        if not trigger_reason and not _payload_mentions_trigger(final_payload):
            return "missing_rolling_trigger_reason"
        if "optimize_release_plan" in tool_chain and "evaluate_release_plan" not in tool_chain:
            return "missing_required_tool"
        return None
    return "missing_required_tool"


def _mcp_payload_failure(
    decision: ReservoirDecisionPayload | None,
    schema_failure: str | None,
    tool_chain: list[str],
) -> str | None:
    if schema_failure is not None or decision is None:
        return "invalid_final_payload"
    if decision.transport != "mcp_tools":
        return "invalid_final_payload"
    if not decision.evaluation_reference:
        return "missing_evaluation_reference"
    if not any(name in decision.evaluation_reference for name in ["evaluate_release_plan", "evaluate_carry_over_plan", "evaluation"]):
        return "hallucinated_evaluation_reference"
    return None


def _mcp_trace_from_tool_events(trace: dict[str, Any], tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    sequence = [str(event.get("tool_name")) for event in tool_events]
    failure_count = sum(1 for event in tool_events if _event_failed(event))
    structured_count = sum(1 for event in tool_events if _event_has_structured_payload(event))
    total = len(tool_events)
    return {
        "mcp_tool_call_sequence": sequence,
        "mcp_tool_call_count": total,
        "mcp_tool_call_success_count": total - failure_count,
        "mcp_tool_call_failure_count": failure_count,
        "mcp_structured_result_count": structured_count,
        "mcp_unstructured_result_count": max(0, total - structured_count),
        "mcp_structured_content_rate": round(structured_count / total, 4) if total else 0.0,
    }


def _event_failed(event: dict[str, Any]) -> bool:
    for key in ("error", "exception", "traceback"):
        if key in event and event[key]:
            return True
    for key in ("result", "output", "content"):
        value = event.get(key)
        payload = value if isinstance(value, dict) else ReservoirAgentRunner._extract_json_payload(value) if isinstance(value, str) else None
        if isinstance(payload, dict):
            if payload.get("isError") or payload.get("error") or payload.get("exception"):
                return True
    return False


def _event_has_structured_payload(event: dict[str, Any]) -> bool:
    for key in ("result", "output", "content"):
        value = event.get(key)
        if isinstance(value, dict):
            return True
        if isinstance(value, str) and ReservoirAgentRunner._extract_json_payload(value) is not None:
            return True
    return False


def _payload_mentions_trigger(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return "trigger_reason" in text


def _target_release(decision: ReservoirDecisionPayload) -> float | None:
    value = decision.target_release_summary.get("target_release_m3s")
    return None if value is None else float(value)


def _instruction_status_to_runtime(status: str) -> str:
    if status == "satisfied":
        return "completed"
    if status == "infeasible":
        return "infeasible"
    if status in {"partially_satisfied", "in_progress"}:
        return "in_progress"
    return "unknown"


def _last_evaluation_payload(tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(tool_events):
        if event.get("tool_name") != "evaluate_release_plan":
            continue
        for key in ("result", "output", "content"):
            value = event.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                parsed = ReservoirAgentRunner._extract_json_payload(value)
                if parsed:
                    return parsed
    return {}


def _normalize_final_payload(
    payload: dict[str, Any] | None,
    *,
    workflow: str,
    method_level: str,
    skill_name: str,
    tool_chain: list[str],
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    normalized["workflow"] = workflow
    normalized["method_level"] = str(normalized.get("method_level") or method_level)
    normalized["transport"] = "mcp_tools"
    normalized["skill_name"] = str(normalized.get("skill_name") or skill_name)
    target_summary = normalized.get("target_release_summary")
    if isinstance(target_summary, str):
        import re

        match = re.search(r"[-+]?\d+(?:\.\d+)?", target_summary)
        normalized["target_release_summary"] = {
            "target_release_m3s": float(match.group(0)) if match else 0.0,
            "module_type": "constant_release",
        }
    elif not isinstance(target_summary, dict):
        normalized["target_release_summary"] = {}
    decision_type = str(normalized.get("decision_type") or "")
    if decision_type not in {"accept", "retain_carry_over", "replan", "reject_infeasible"}:
        normalized["decision_type"] = "replan" if workflow in {"dynamic", "rolling"} else "accept"
    safety = str(normalized.get("safety_status") or "").strip().lower()
    if safety in {"pass", "ok", "safe", "no_violations"}:
        normalized["safety_status"] = "safe"
    elif safety in {"fail", "unsafe", "hard_constraint_violation"}:
        normalized["safety_status"] = "unsafe"
    elif safety not in {"safe", "unsafe", "unknown"}:
        normalized["safety_status"] = "unknown"
    hard = normalized.get("hard_constraint_violation")
    if isinstance(hard, dict):
        normalized["hard_constraint_violation"] = int(hard.get("count") or hard.get("hard_constraint_violations_count") or 0) > 0
    elif isinstance(hard, list):
        normalized["hard_constraint_violation"] = len(hard) > 0
    elif isinstance(hard, str):
        normalized["hard_constraint_violation"] = hard.strip().lower() not in {"", "none", "false", "no", "0"}
    elif hard is None:
        normalized["hard_constraint_violation"] = False
    instruction = normalized.get("instruction_status")
    if isinstance(instruction, dict):
        if int(instruction.get("instruction_violations_count") or 0) == 0 or instruction.get("target_level_met") is True:
            normalized["instruction_status"] = "satisfied"
        else:
            normalized["instruction_status"] = "in_progress"
    elif instruction in {"no_violations", "completed", "safe"}:
        normalized["instruction_status"] = "satisfied"
    elif instruction not in {"satisfied", "partially_satisfied", "in_progress", "infeasible", "not_applicable"}:
        normalized["instruction_status"] = "not_applicable"
    for field in ("tool_chain_summary", "mcp_tool_chain_summary"):
        value = normalized.get(field)
        if isinstance(value, dict):
            normalized[field] = list(value.keys())
        elif isinstance(value, str):
            normalized[field] = [item.strip().split("(", 1)[0] for item in value.split("->") if item.strip()]
        elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
            normalized[field] = [
                str(item.get("tool") or item.get("tool_name") or item.get("name") or item)
                for item in value
                if isinstance(item, dict)
            ]
        elif not isinstance(value, list):
            normalized[field] = list(tool_chain)
    if not normalized.get("mcp_tool_chain_summary"):
        normalized["mcp_tool_chain_summary"] = list(tool_chain)
    evaluation_reference = normalized.get("evaluation_reference")
    if isinstance(evaluation_reference, dict):
        scenario_id = evaluation_reference.get("scenario_id") or normalized.get("stage_id") or normalized.get("event_id")
        normalized["evaluation_reference"] = f"evaluate_release_plan::{scenario_id}"
    elif not evaluation_reference and "evaluate_release_plan" in tool_chain:
        normalized["evaluation_reference"] = f"evaluate_release_plan::{normalized.get('stage_id') or normalized.get('event_id')}"
    if not isinstance(normalized.get("explanation"), str):
        normalized["explanation"] = json.dumps(normalized.get("explanation"), ensure_ascii=False, default=str)
    return normalized
