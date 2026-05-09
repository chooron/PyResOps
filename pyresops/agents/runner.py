"""Agno runner with fail-first result validation."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from pyresops.agents.model_builder import build_agno_model


class ReservoirAgentRunner:
    """Execute an Agno agent and normalize the result for workflows."""

    STATIC_S01_CHAIN_PROFILE = "static_s01_mcp_chain_v1"
    STATIC_RESERVOIR_PROFILE = "static_realdata_dispatch_v1"
    DYNAMIC_RESERVOIR_PROFILE = "dynamic_realdata_dispatch_v1"
    ROLLING_RESERVOIR_PROFILE = "rolling_realdata_dispatch_v1"
    STATIC_S01_CHAIN = [
        "get_reservoir_status",
        "query_dispatch_rules",
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    DYNAMIC_RETAIN_CHAIN = [
        "get_reservoir_status",
        "query_dispatch_rules",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    DYNAMIC_REPLAN_CHAIN = [
        "get_reservoir_status",
        "query_dispatch_rules",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    DYNAMIC_CORE_PREFIX = ["get_reservoir_status", "query_dispatch_rules"]
    DYNAMIC_CARRY_OVER_EVALUATION_PREFIX = [
        "get_reservoir_status",
        "query_dispatch_rules",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    DYNAMIC_REPLAN_SUFFIX = [
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        candidates = [stripped]
        candidates.extend(re.findall(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL))
        candidates.extend(re.findall(r"(\{.*\})", stripped, re.DOTALL))
        if "{" in stripped and "}" in stripped:
            candidates.append(stripped[stripped.find("{") : stripped.rfind("}") + 1])
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @classmethod
    def _coerce_payload(cls, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return cls._extract_json_payload(value)
        return None

    @staticmethod
    def _tool_name(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return str(tool_call.get("tool_name") or tool_call.get("name") or "unknown")
        return str(getattr(tool_call, "tool_name", None) or getattr(tool_call, "name", "unknown"))

    @classmethod
    def _tool_events(cls, run_response: Any) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for index, tool_call in enumerate(getattr(run_response, "tools", []) or [], 1):
            event = {"call_order": index, "tool_name": cls._tool_name(tool_call)}
            for key in ("args", "tool_args", "arguments", "input", "result", "output", "content"):
                value = (
                    tool_call.get(key)
                    if isinstance(tool_call, dict)
                    else getattr(tool_call, key, None)
                )
                if value not in (None, "", {}, []):
                    event[key] = value
            events.append(event)
        return events

    @classmethod
    def _last_tool_payload(
        cls,
        tool_events: list[dict[str, Any]],
        tool_name: str,
    ) -> dict[str, Any] | None:
        for event in reversed(tool_events):
            if event.get("tool_name") != tool_name:
                continue
            for key in ("result", "output", "content"):
                payload = cls._coerce_payload(event.get(key))
                if payload is not None:
                    return payload
        return None

    @classmethod
    def _validate_static_s01(cls, tool_chain: list[str], payload: dict[str, Any] | None) -> str | None:
        counts = {tool_name: tool_chain.count(tool_name) for tool_name in cls.STATIC_S01_CHAIN}
        if counts["optimize_release_plan"] > 1:
            return "repeated_static_optimization"
        if counts["simulate_dispatch_program"] > 1:
            return "repeated_static_simulation"
        if counts["evaluate_dispatch_result"] > 1:
            return "repeated_static_evaluation"
        if any(counts[tool_name] == 0 for tool_name in cls.STATIC_S01_CHAIN):
            return "missing_required_tool"
        if tool_chain != cls.STATIC_S01_CHAIN:
            return "wrong_tool_order"
        if payload is None:
            return "non_json_final_output"
        if payload.get("status") == "process_failed":
            return str(payload.get("failure_reason") or "process_failed")
        if payload.get("outflow") is None:
            return "missing_outflow"
        try:
            if float(payload["outflow"]) < 0:
                return "negative_outflow"
        except (TypeError, ValueError):
            return "outflow_not_numeric"
        return None

    @classmethod
    def _validate_profile_chain(
        cls,
        *,
        scenario: dict[str, Any],
        tool_chain: list[str],
        payload: dict[str, Any] | None,
    ) -> str | None:
        profile = scenario.get("agent_workflow_profile")
        if profile in {cls.STATIC_S01_CHAIN_PROFILE, cls.STATIC_RESERVOIR_PROFILE, cls.ROLLING_RESERVOIR_PROFILE}:
            failure = cls._validate_static_s01(tool_chain, payload)
            if failure is not None:
                return failure
        elif profile == cls.DYNAMIC_RESERVOIR_PROFILE:
            failure = cls._validate_dynamic_process(scenario=scenario, tool_chain=tool_chain)
            if failure is not None:
                return failure

        if payload is None:
            return "non_json_final_output"
        if payload.get("status") == "process_failed":
            return str(payload.get("failure_reason") or "process_failed")
        if payload.get("outflow") is None:
            return "missing_outflow"
        try:
            if float(payload["outflow"]) < 0:
                return "negative_outflow"
        except (TypeError, ValueError):
            return "outflow_not_numeric"
        return None

    @classmethod
    def _validate_dynamic_process(
        cls,
        *,
        scenario: dict[str, Any],
        tool_chain: list[str],
    ) -> str | None:
        if tool_chain[:2] != cls.DYNAMIC_CORE_PREFIX:
            return "missing_dynamic_status_or_rules"
        if "simulate_dispatch_program" not in tool_chain or "evaluate_dispatch_result" not in tool_chain:
            return "missing_dynamic_simulation_or_evaluation"
        has_carry_over = bool(scenario.get("carry_over_plan"))
        if not has_carry_over and "optimize_release_plan" not in tool_chain:
            return "missing_dynamic_initial_optimization"
        if has_carry_over:
            if tool_chain[:4] != cls.DYNAMIC_CARRY_OVER_EVALUATION_PREFIX:
                return "missing_carry_over_evaluation"
            post_evaluation = tool_chain[4:]
            if not post_evaluation:
                return None
            if post_evaluation[0] != "optimize_release_plan":
                return "unexpected_dynamic_post_carry_over_step"
            last_optimize = len(tool_chain) - 1 - list(reversed(tool_chain)).index(
                "optimize_release_plan"
            )
            if tool_chain[last_optimize : last_optimize + 3] != cls.DYNAMIC_REPLAN_SUFFIX:
                return "missing_dynamic_replan_evaluation"
        return None

    @classmethod
    def _dynamic_protocol_warning(
        cls,
        *,
        scenario: dict[str, Any],
        tool_chain: list[str],
    ) -> str | None:
        if scenario.get("agent_workflow_profile") != cls.DYNAMIC_RESERVOIR_PROFILE:
            return None
        if scenario.get("carry_over_plan"):
            if tool_chain[:4] == cls.DYNAMIC_CARRY_OVER_EVALUATION_PREFIX and (
                tool_chain.count("optimize_release_plan") > 1
            ):
                return "repeated_dynamic_optimization"
            if tuple(tool_chain) not in {
                tuple(cls.DYNAMIC_RETAIN_CHAIN),
                tuple(cls.DYNAMIC_REPLAN_CHAIN),
            }:
                return "unexpected_dynamic_tool_chain"
        elif tool_chain != cls.STATIC_S01_CHAIN:
            return "unexpected_dynamic_initial_tool_chain"
        return None

    @staticmethod
    def _derive_safety_status(evaluation_payload: dict[str, Any] | None) -> dict[str, Any]:
        if evaluation_payload is None:
            return {
                "priority": 1,
                "status": "unknown",
                "hard_constraints_satisfied": None,
                "diagnostic": "missing_evaluate_dispatch_result_payload",
            }
        count = evaluation_payload.get("hard_constraint_violations_count")
        if count is None:
            violations = [
                item
                for item in evaluation_payload.get("constraint_violations", [])
                if isinstance(item, dict) and item.get("constraint_id") != "target_level"
            ]
            count = len(violations)
        count = int(count)
        return {
            "priority": 1,
            "status": "safe" if count == 0 else "hard_constraint_violation",
            "hard_constraints_satisfied": count == 0,
            "hard_constraint_violations_count": count,
            "hard_constraint_violations": evaluation_payload.get(
                "hard_constraint_violations",
                evaluation_payload.get("constraint_violations", []),
            ),
        }

    @staticmethod
    def _derive_instruction_status(
        *,
        scenario: dict[str, Any],
        evaluation_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if evaluation_payload is None:
            return {
                "priority": 2,
                "status": "unknown",
                "completed": None,
                "process_failure": False,
                "diagnostic": "missing_evaluate_dispatch_result_payload",
            }
        final_level = evaluation_payload.get("final_level_m")
        target_level = evaluation_payload.get("target_level_m", scenario.get("target_level"))
        if final_level is None or target_level is None:
            return {
                "priority": 2,
                "status": "unknown",
                "completed": None,
                "process_failure": False,
                "diagnostic": "missing_final_or_target_level",
            }
        final_level = float(final_level)
        target_level = float(target_level)
        tolerance = float(scenario.get("target_level_tolerance", 0.5))
        current_level = float(scenario.get("current_level", final_level))
        completed = final_level <= target_level + tolerance
        start_gap = abs(current_level - target_level)
        final_gap = abs(final_level - target_level)
        return {
            "priority": 2,
            "status": "completed" if completed else "in_progress",
            "completed": completed,
            "process_failure": False,
            "final_level_m": round(final_level, 3),
            "target_level_m": round(target_level, 3),
            "target_level_tolerance_m": tolerance,
            "remaining_gap_m": round(max(0.0, final_level - target_level), 3),
            "progressing_toward_target": final_gap <= start_gap,
            "instruction_violations_count": int(
                evaluation_payload.get("instruction_violations_count", 0)
            ),
            "instruction_violations": evaluation_payload.get("instruction_violations", []),
            "diagnostic": (
                "instruction target satisfied"
                if completed
                else "instruction target not yet satisfied; this is not a workflow failure"
            ),
        }

    def run(
        self,
        *,
        scenario: dict[str, Any],
        spec,
        model_cfg: dict[str, Any],
        system_prompt: str,
        tools: list[Any],
        max_attempts: int,
        model_id: str,
        temperature: float,
        seed: int | None,
    ) -> dict[str, Any]:
        try:
            from agno.agent import Agent
        except ImportError as exc:
            raise RuntimeError(
                "Agno is required for real workflow execution but is not installed."
            ) from exc

        model = build_agno_model(model_cfg, temperature=temperature, seed=seed)
        agent = Agent(model=model, tools=tools, instructions=system_prompt, markdown=False)
        prompt = self._build_user_message(scenario)

        started_at = self._utc_now()
        wall_start = time.time()
        run_response = agent.run(prompt)
        elapsed = round(time.time() - wall_start, 3)
        finished_at = self._utc_now()

        final_text = str(getattr(run_response, "content", "") or "")
        payload = self._extract_json_payload(final_text)
        tool_events = self._tool_events(run_response)
        tool_chain = [event["tool_name"] for event in tool_events]
        evaluation_payload = self._last_tool_payload(tool_events, "evaluate_dispatch_result")
        failure_reason = self._validate_profile_chain(
            scenario=scenario,
            tool_chain=tool_chain,
            payload=payload,
        )
        protocol_warning = self._dynamic_protocol_warning(scenario=scenario, tool_chain=tool_chain)
        safety_status = self._derive_safety_status(evaluation_payload)
        instruction_status = self._derive_instruction_status(
            scenario=scenario,
            evaluation_payload=evaluation_payload,
        )

        outflow = None
        if isinstance(payload, dict) and payload.get("outflow") is not None:
            outflow = float(payload["outflow"])
        success = failure_reason is None
        return {
            "scenario_id": scenario["id"],
            "method": "agno_realdata_agent",
            "model": model_id,
            "success": success,
            "outflow": outflow,
            "reasoning": "" if payload is None else str(payload.get("reasoning", "")),
            "constraint_check": "" if payload is None else str(payload.get("constraint_check", "")),
            "process_success": success,
            "protocol_warning": protocol_warning,
            "safety_status": safety_status,
            "instruction_status": instruction_status,
            "parse_warning": None if payload is not None else "final output was not JSON",
            "parsed_from": "json" if payload is not None else "none",
            "final_decision_text": final_text,
            "tool_call_count": len(tool_chain),
            "tool_call_chain": tool_chain,
            "tool_calls_detail": [{"call_order": e["call_order"], "tool_name": e["tool_name"]} for e in tool_events],
            "llm_execution_trace": {
                "started_at": started_at,
                "finished_at": finished_at,
                "user_message": prompt,
                "tool_events": tool_events,
                "attempts": max(1, int(max_attempts)),
            },
            "accepted_attempt_index": 1 if success else None,
            "acceptance_failure_reason": failure_reason,
            "accepted_evidence_pair": {"final_payload": payload} if success else None,
            "total_time_seconds": elapsed,
            "llm_temperature": temperature,
            "llm_seed": seed,
            "llm_usage": getattr(run_response, "metrics", None),
            "llm_usage_log_path": None,
        }

    @staticmethod
    def _build_user_message(scenario: dict[str, Any]) -> str:
        profile = scenario.get("agent_workflow_profile")
        completion_rule = (
            "Follow the dynamic stage contract. Do not return process_failed just because "
            "the operator target is unfinished; safety constraints come first and unfinished "
            "instruction targets are evaluation status, not workflow failure. If carry_over_plan "
            "is present, first simulate_dispatch_program and evaluate_dispatch_result for that "
            "plan before any optimize_release_plan call. Return strict JSON only."
            if profile == ReservoirAgentRunner.DYNAMIC_RESERVOIR_PROFILE
            else "Use exactly the required tool chain, call each required tool exactly once, and return strict JSON only."
        )
        return (
            "Run the reservoir dispatch workflow for this real-data scenario.\n"
            f"scenario_id: {scenario['id']}\n"
            f"workflow_type: {scenario.get('workflow_type')}\n"
            f"description: {scenario.get('description')}\n"
            f"current_level_m: {scenario['current_level']}\n"
            f"initial_inflow_m3s: {scenario['initial_inflow']}\n"
            f"observed_mean_inflow_m3s: {scenario.get('observed_mean_inflow', scenario['inflow'])}\n"
            f"planning_mean_inflow_m3s: {scenario.get('predicted_mean_inflow', scenario['inflow'])}\n"
            f"target_level_m: {scenario['target_level']}\n"
            f"operator_instruction: {scenario.get('operator_instruction', '')}\n"
            f"required_tool_chain: {ReservoirAgentRunner._required_chain_hint(scenario)}\n"
            f"{completion_rule}"
        )

    @classmethod
    def _required_chain_hint(cls, scenario: dict[str, Any]) -> str:
        profile = scenario.get("agent_workflow_profile")
        if profile == cls.DYNAMIC_RESERVOIR_PROFILE and scenario.get("carry_over_plan"):
            return (
                "either get_reservoir_status -> query_dispatch_rules -> simulate_dispatch_program "
                "-> evaluate_dispatch_result, or get_reservoir_status -> query_dispatch_rules "
                "-> simulate_dispatch_program -> evaluate_dispatch_result -> optimize_release_plan "
                "-> simulate_dispatch_program -> evaluate_dispatch_result"
            )
        return " -> ".join(cls.STATIC_S01_CHAIN)
