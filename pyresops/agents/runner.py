from __future__ import annotations

import json
import re
import time
from typing import Any

from pyresops.agents.model_builder import build_agno_model


class ReservoirAgentRunner:
    """Run agno agent with fail-fast semantics and normalized result extraction."""

    DECLARED_OUTFLOW_TOLERANCE = 1e-6
    STATIC_S01_CHAIN_PROFILE = "static_s01_mcp_chain_v1"
    _STATIC_S01_CHAIN = [
        "get_reservoir_status",
        "query_dispatch_rules",
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]

    _SIMULATION_TOOLS = {"simulate_dispatch_program"}
    _EVALUATION_TOOLS = {"evaluate_dispatch_result"}

    @staticmethod
    def extract_json_payload(text: str) -> dict | None:
        stripped = text.strip()
        candidates = [stripped]
        if "```json" in stripped:
            candidates.extend(re.findall(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL))
        candidates.extend(re.findall(r"(\{.*\})", stripped, re.DOTALL))

        for candidate in candidates:
            if not candidate:
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @classmethod
    def extract_outflow(cls, final_text: str, fallback_outflow: float) -> dict:
        payload = cls.extract_json_payload(final_text)
        if payload is not None:
            outflow = payload.get("outflow")
            try:
                parsed_outflow = float(outflow)
            except (TypeError, ValueError):
                parsed_outflow = fallback_outflow
            return {
                "outflow": parsed_outflow,
                "reasoning": str(payload.get("reasoning", "")),
                "constraint_check": str(payload.get("constraint_check", "")),
                "parse_warning": None,
                "parsed_from": "json",
            }

        for pattern in [
            r"出库流量[：:]\s*(\d+\.?\d*)\s*m³/s",
            r"建议.*?(\d+\.?\d*)\s*m³/s",
            r"泄放\s*(\d+\.?\d*)\s*m³/s",
            r"目标出库.*?(\d+\.?\d*)",
            r"(?:release|outflow).*?(\d+\.?\d*)\s*m3/s",
            r"(?:recommended|recommend).*?(\d+\.?\d*)\s*m3/s",
            r"(?:target\s+)?outflow[\s:=]+(\d+\.?\d*)",
        ]:
            match = re.search(pattern, final_text)
            if match:
                return {
                    "outflow": float(match.group(1)),
                    "reasoning": "",
                    "constraint_check": "",
                    "parse_warning": "Agent output was not valid JSON; fell back to regex parsing.",
                    "parsed_from": "regex",
                }

        return {
            "outflow": fallback_outflow,
            "reasoning": "",
            "constraint_check": "",
            "parse_warning": "Agent output did not contain parseable JSON or regex outflow.",
            "parsed_from": "default",
        }

    @staticmethod
    def _is_tool_error_event(event: dict) -> str | None:
        for key in ("result", "output", "tool_result", "observation", "content"):
            payload = event.get(key)
            if isinstance(payload, dict):
                error_value = payload.get("error")
                if isinstance(error_value, str) and error_value.strip():
                    return f"tool_error:{error_value}"
                status_value = payload.get("status")
                if isinstance(status_value, str) and status_value.strip().lower() in {
                    "error",
                    "failed",
                    "failure",
                }:
                    return f"tool_error_status:{status_value.lower()}"
                success_value = payload.get("success")
                if isinstance(success_value, bool) and not success_value:
                    return "tool_error:success_false"
        return None

    @classmethod
    def _extract_declared_outflow(cls, event: dict) -> tuple[float | None, str | None]:
        tool_args = event.get("tool_args")
        if isinstance(tool_args, dict) and "declared_outflow" in tool_args:
            try:
                return float(tool_args["declared_outflow"]), None
            except (TypeError, ValueError):
                return None, "declared_outflow_not_numeric"

        args = event.get("args")
        if isinstance(args, dict) and "declared_outflow" in args:
            try:
                return float(args["declared_outflow"]), None
            except (TypeError, ValueError):
                return None, "declared_outflow_not_numeric"

        result_payload: Any = event.get("result")
        if result_payload is None:
            return None, "missing_declared_outflow"

        parsed_result: dict | None = None
        if isinstance(result_payload, dict):
            parsed_result = result_payload
        elif isinstance(result_payload, str):
            try:
                decoded = json.loads(result_payload)
            except json.JSONDecodeError:
                return None, "parse_failed_result_json"
            if isinstance(decoded, dict):
                parsed_result = decoded
            else:
                return None, "parse_failed_result_json"
        else:
            return None, "missing_declared_outflow"

        if "declared_outflow" not in parsed_result:
            return None, "missing_declared_outflow"

        try:
            return float(parsed_result["declared_outflow"]), None
        except (TypeError, ValueError):
            return None, "declared_outflow_not_numeric"

    @classmethod
    def _normalize_event(cls, event: dict) -> dict:
        tool_name = str(event.get("tool_name", "unknown"))
        if tool_name in cls._SIMULATION_TOOLS:
            event_kind = "simulation"
        elif tool_name in cls._EVALUATION_TOOLS:
            event_kind = "evaluation"
        else:
            event_kind = "other"

        attempt_index = int(event.get("attempt_index", 0) or 0)
        call_order = int(event.get("call_order", 0) or 0)
        declared_outflow, parse_reason = cls._extract_declared_outflow(event)
        tool_error_reason = cls._is_tool_error_event(event)

        failure_reason = None
        if tool_error_reason is not None:
            failure_reason = tool_error_reason
        elif event_kind in {"simulation", "evaluation"} and parse_reason is not None:
            failure_reason = parse_reason

        event_ok = failure_reason is None
        return {
            "attempt_index": attempt_index,
            "call_order": call_order,
            "tool_name": tool_name,
            "event_kind": event_kind,
            "declared_outflow": declared_outflow,
            "event_ok": event_ok,
            "failure_reason": failure_reason,
            "raw_event": event,
        }

    @staticmethod
    def _extract_result_payload(raw_event: dict) -> dict | str | None:
        result_payload: Any = raw_event.get("result")
        if isinstance(result_payload, dict):
            return result_payload
        if isinstance(result_payload, str):
            try:
                decoded = json.loads(result_payload)
                if isinstance(decoded, dict):
                    return decoded
            except json.JSONDecodeError:
                return result_payload
            return result_payload
        return None

    @classmethod
    def _public_event_record(cls, event: dict) -> dict:
        return {
            "attempt_index": event["attempt_index"],
            "call_order": event["call_order"],
            "tool_name": event["tool_name"],
            "event_kind": event["event_kind"],
            "declared_outflow": event["declared_outflow"],
            "event_ok": event["event_ok"],
            "failure_reason": event["failure_reason"],
            "result_payload": cls._extract_result_payload(event["raw_event"]),
        }

    @classmethod
    def _resolve_workflow_profile(cls, scenario: dict) -> str | None:
        profile = scenario.get("agent_workflow_profile")
        if not isinstance(profile, str):
            return None
        cleaned = profile.strip()
        return cleaned or None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_dict_payload(cls, raw_event: dict) -> dict | None:
        payload = cls._extract_result_payload(raw_event)
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _collect_numbers(cls, payload: Any) -> list[float]:
        if isinstance(payload, (int, float)):
            return [float(payload)]
        if isinstance(payload, str):
            matches = re.findall(r"\d+(?:\.\d+)?", payload)
            return [float(match) for match in matches]
        if isinstance(payload, dict):
            numbers: list[float] = []
            for value in payload.values():
                numbers.extend(cls._collect_numbers(value))
            return numbers
        if isinstance(payload, list):
            numbers: list[float] = []
            for value in payload:
                numbers.extend(cls._collect_numbers(value))
            return numbers
        return []

    @classmethod
    def _has_required_rule_numbers(cls, payload: dict) -> bool:
        numbers = cls._collect_numbers(payload)
        required = [156.5, 14000.0, 50.0, 48.0]
        return all(any(abs(number - required_value) <= 1e-6 for number in numbers) for required_value in required)

    @classmethod
    def _validate_static_s01_chain(
        cls,
        *,
        attempt: int,
        tool_events: list[dict],
        scenario: dict,
    ) -> tuple[dict | None, int | None, str | None]:
        tool_names = [str(event.get("tool_name", "unknown")) for event in tool_events]
        if tool_names != cls._STATIC_S01_CHAIN:
            return None, None, "unexpected_tool_chain"

        status_payload = cls._extract_dict_payload(tool_events[0])
        if status_payload is None:
            return None, None, "malformed_status_result"
        current_level = cls._coerce_float(status_payload.get("current_level_m"))
        forecast_inflow = cls._coerce_float(status_payload.get("forecast_inflow_m3s"))
        flood_limit = cls._coerce_float(status_payload.get("flood_limit_level_m"))
        if current_level is None or forecast_inflow is None or flood_limit is None:
            return None, None, "malformed_status_result"

        rules_payload = cls._extract_dict_payload(tool_events[1])
        if rules_payload is None or not cls._has_required_rule_numbers(rules_payload):
            return None, None, "missing_rule_numeric_constraints"

        optimize_payload = cls._extract_dict_payload(tool_events[2])
        if optimize_payload is None:
            return None, None, "optimize_result_untrustworthy"
        release_values = optimize_payload.get("release_values_m3s")
        avg_release = cls._coerce_float(optimize_payload.get("avg_release_m3s"))
        min_release = cls._coerce_float(optimize_payload.get("min_release_m3s"))
        max_release = cls._coerce_float(optimize_payload.get("max_release_m3s"))
        if (
            not isinstance(release_values, list)
            or not release_values
            or avg_release is None
            or min_release is None
            or max_release is None
        ):
            return None, None, "optimize_result_untrustworthy"
        release_numbers = [cls._coerce_float(value) for value in release_values]
        if any(value is None for value in release_numbers):
            return None, None, "optimize_result_untrustworthy"
        constant_schedule = (
            abs(min_release - max_release) <= cls.DECLARED_OUTFLOW_TOLERANCE
            and all(
                abs(float(value) - avg_release) <= cls.DECLARED_OUTFLOW_TOLERANCE
                for value in release_numbers
            )
        )
        if not constant_schedule:
            return None, None, "unsupported_optimized_schedule"
        if current_level > flood_limit and avg_release <= forecast_inflow + cls.DECLARED_OUTFLOW_TOLERANCE:
            return None, None, "optimize_result_untrustworthy"

        simulation_payload = cls._extract_dict_payload(tool_events[3])
        if simulation_payload is None:
            return None, None, "malformed_simulation_result"
        simulated_outflow = cls._coerce_float(simulation_payload.get("declared_outflow"))
        final_level = cls._coerce_float(simulation_payload.get("final_level_m"))
        if simulated_outflow is None or final_level is None:
            return None, None, "malformed_simulation_result"
        if abs(simulated_outflow - avg_release) > cls.DECLARED_OUTFLOW_TOLERANCE:
            return None, None, "simulation_outflow_mismatch"

        target_level = cls._coerce_float(scenario.get("target_level"))
        if target_level is None:
            target_level = flood_limit
        if current_level > target_level and final_level >= current_level - cls.DECLARED_OUTFLOW_TOLERANCE:
            return None, None, "simulation_direction_invalid"

        evaluation_payload = cls._extract_dict_payload(tool_events[4])
        if evaluation_payload is None:
            return None, None, "malformed_evaluation_result"
        overall_score = cls._coerce_float(evaluation_payload.get("overall_score"))
        violation_count = cls._coerce_float(evaluation_payload.get("constraint_violations_count"))
        if overall_score is None or violation_count is None:
            return None, None, "malformed_evaluation_result"
        if final_level > target_level + cls.DECLARED_OUTFLOW_TOLERANCE:
            return None, None, "target_unmet"

        accepted_evidence_pair = {
            "attempt_index": attempt,
            "status": cls._public_event_record(cls._normalize_event(tool_events[0])),
            "rules": cls._public_event_record(cls._normalize_event(tool_events[1])),
            "optimization": cls._public_event_record(cls._normalize_event(tool_events[2])),
            "simulation": cls._public_event_record(cls._normalize_event(tool_events[3])),
            "evaluation": cls._public_event_record(cls._normalize_event(tool_events[4])),
        }
        return accepted_evidence_pair, attempt, None

    @classmethod
    def _select_evidence_pair(
        cls,
        selected_outflow: float,
        normalized_events: list[dict],
    ) -> tuple[dict | None, int | None, str | None]:
        candidate_events = [
            e for e in normalized_events if e["event_kind"] in {"simulation", "evaluation"}
        ]
        ok_sims = [e for e in candidate_events if e["event_kind"] == "simulation" and e["event_ok"]]
        ok_evals = [
            e for e in candidate_events if e["event_kind"] == "evaluation" and e["event_ok"]
        ]
        failed_sims = [
            e for e in candidate_events if e["event_kind"] == "simulation" and not e["event_ok"]
        ]
        failed_evals = [
            e for e in candidate_events if e["event_kind"] == "evaluation" and not e["event_ok"]
        ]

        matched_sims = [
            e
            for e in ok_sims
            if abs(float(e["declared_outflow"]) - selected_outflow)
            <= cls.DECLARED_OUTFLOW_TOLERANCE
        ]
        matched_evals = [
            e
            for e in ok_evals
            if abs(float(e["declared_outflow"]) - selected_outflow)
            <= cls.DECLARED_OUTFLOW_TOLERANCE
        ]

        if not matched_sims:
            for event in failed_sims:
                reason = str(event.get("failure_reason") or "")
                if reason.startswith("tool_error"):
                    return None, None, reason
            for event in failed_sims:
                reason = str(event.get("failure_reason") or "")
                if reason:
                    return None, None, reason
            if ok_sims:
                return None, None, "outflow_mismatch"
            return None, None, "missing_simulation"
        if not matched_evals:
            for event in failed_evals:
                reason = str(event.get("failure_reason") or "")
                if reason.startswith("tool_error"):
                    return None, None, reason
            for event in failed_evals:
                reason = str(event.get("failure_reason") or "")
                if reason:
                    return None, None, reason
            if ok_evals:
                return None, None, "outflow_mismatch"
            return None, None, "missing_evaluation"

        candidate_pairs: list[dict] = []
        for sim in matched_sims:
            for ev in matched_evals:
                if sim["attempt_index"] != ev["attempt_index"]:
                    continue
                if ev["call_order"] <= sim["call_order"]:
                    continue
                candidate_pairs.append(
                    {
                        "simulation": sim,
                        "evaluation": ev,
                        "attempt_index": sim["attempt_index"],
                        "delta": ev["call_order"] - sim["call_order"],
                    }
                )

        if candidate_pairs:
            winner = min(
                candidate_pairs,
                key=lambda pair: (
                    pair["delta"],
                    -pair["simulation"]["call_order"],
                ),
            )
            public_winner = {
                "attempt_index": int(winner["attempt_index"]),
                "simulation": cls._public_event_record(winner["simulation"]),
                "evaluation": cls._public_event_record(winner["evaluation"]),
            }
            return public_winner, int(winner["attempt_index"]), None

        same_attempt_exists = any(
            sim["attempt_index"] == ev["attempt_index"]
            for sim in matched_sims
            for ev in matched_evals
        )
        if same_attempt_exists:
            return None, None, "evaluation_precedes_simulation"

        cross_attempt_exists = any(
            sim["attempt_index"] != ev["attempt_index"]
            for sim in matched_sims
            for ev in matched_evals
        )
        if cross_attempt_exists:
            return None, None, "cross_attempt_mismatch"

        return None, None, "missing_evidence_link"

    def run(
        self,
        *,
        scenario: dict,
        spec,
        model_cfg: dict,
        system_prompt: str,
        tools: list,
        max_attempts: int,
        model_id: str,
        temperature: float,
        seed: int | None,
    ) -> dict:
        from agno.agent import Agent

        start_time = time.time()
        model = build_agno_model(model_cfg, temperature=temperature, seed=seed)
        agent = Agent(
            model=model,
            tools=tools,
            description=system_prompt,
            markdown=False,
        )

        current_inflow = scenario.get("initial_inflow", scenario["inflow"])
        user_message = (
            f"Please perform a complete analysis for the following reservoir dispatch scenario and provide a final decision:\n\n"
            f"Scenario ID: {scenario['id']}\n"
            f"Scenario Name: {scenario['name']}\n"
            f"Scenario Description: {scenario['description']}\n\n"
            f"Current State:\n"
            f"- Current Inflow: {current_inflow} m3/s\n"
            f"- Forecast Inflow: {scenario['inflow']} m3/s\n"
            f"- Current Water Level: {scenario['current_level']} m\n"
            f"- Target Water Level: {scenario['target_level']} m\n"
            f"- Season: {scenario['season']}\n"
            f"- Flood Risk: {scenario['flood_risk']}\n\n"
            f"Use available tools for end-to-end analysis (status -> rules -> simulation -> evaluation), then provide the final dispatch plan in English."
        )

        final_text = ""
        tool_calls_detail: list[dict] = []
        tool_call_events: list[dict] = []
        normalized_events: list[dict] = []
        parsed = {
            "outflow": float(scenario["inflow"]),
            "reasoning": "",
            "constraint_check": "",
            "parse_warning": "",
            "parsed_from": "default",
        }
        accepted_attempt_index: int | None = None
        acceptance_failure_reason: str | None = "missing_simulation"
        accepted_evidence_pair: dict | None = None
        workflow_profile = self._resolve_workflow_profile(scenario)
        attempt_limit = 1 if workflow_profile == self.STATIC_S01_CHAIN_PROFILE else max_attempts

        for attempt in range(1, attempt_limit + 1):
            attempt_tool_calls_detail: list[dict] = []
            attempt_events: list[dict] = []
            attempt_prompt = user_message
            if attempt > 1:
                attempt_prompt += (
                    "\n\nRetry requirements: return strict JSON only; "
                    "outflow must be a positive numeric value and satisfy ecological minimum flow."
                )

            run_response = agent.run(attempt_prompt)
            final_text = (
                str(run_response.content)
                if hasattr(run_response, "content") and run_response.content
                else ""
            )

            if hasattr(run_response, "tools") and run_response.tools:
                for i, tc in enumerate(run_response.tools, 1):
                    if isinstance(tc, dict):
                        tool_name = tc.get("tool_name") or tc.get("name", "unknown")
                        event = {
                            "attempt_index": attempt,
                            "call_order": i,
                            "tool_name": tool_name,
                        }
                        for key in (
                            "args",
                            "tool_args",
                            "arguments",
                            "input",
                            "tool_input",
                            "result",
                            "output",
                            "tool_result",
                            "observation",
                            "content",
                        ):
                            value = tc.get(key)
                            if value not in (None, "", {}, []):
                                event[key] = value
                    else:
                        tool_name = getattr(tc, "tool_name", None) or getattr(tc, "name", "unknown")
                        event = {
                            "attempt_index": attempt,
                            "call_order": i,
                            "tool_name": tool_name,
                        }
                        for key in (
                            "args",
                            "tool_args",
                            "arguments",
                            "input",
                            "tool_input",
                            "result",
                            "output",
                            "tool_result",
                            "observation",
                            "content",
                        ):
                            value = getattr(tc, key, None)
                            if value not in (None, "", {}, []):
                                event[key] = value
                    attempt_tool_calls_detail.append({"call_order": i, "tool_name": tool_name})
                    tool_call_events.append(event)
                    attempt_events.append(event)
                    normalized_events.append(self._normalize_event(event))

            tool_calls_detail = attempt_tool_calls_detail

            if workflow_profile == self.STATIC_S01_CHAIN_PROFILE:
                accepted_evidence_pair, accepted_attempt_index, validation_failure = (
                    self._validate_static_s01_chain(
                        attempt=attempt,
                        tool_events=attempt_events,
                        scenario=scenario,
                    )
                )
                if accepted_evidence_pair is None:
                    acceptance_failure_reason = validation_failure or "unexpected_tool_chain"
                    break

                parsed = self.extract_outflow(final_text, fallback_outflow=float(scenario["inflow"]))
                selected_outflow = float(parsed["outflow"])
                if parsed["parsed_from"] != "json":
                    acceptance_failure_reason = "non_json_final_output"
                    accepted_evidence_pair = None
                    accepted_attempt_index = None
                    break
                if selected_outflow <= 0.0:
                    acceptance_failure_reason = "non_positive_outflow"
                    accepted_evidence_pair = None
                    accepted_attempt_index = None
                    break

                optimization_payload = accepted_evidence_pair.get("optimization", {}).get("result_payload", {})
                if isinstance(optimization_payload, dict):
                    optimized_outflow = self._coerce_float(optimization_payload.get("avg_release_m3s"))
                else:
                    optimized_outflow = None
                if optimized_outflow is None or abs(selected_outflow - optimized_outflow) > self.DECLARED_OUTFLOW_TOLERANCE:
                    acceptance_failure_reason = "outflow_mismatch"
                    accepted_evidence_pair = None
                    accepted_attempt_index = None
                    break

                acceptance_failure_reason = None
                break

            parsed = self.extract_outflow(final_text, fallback_outflow=float(scenario["inflow"]))
            selected_outflow = float(parsed["outflow"])

            if parsed["parsed_from"] != "json":
                acceptance_failure_reason = "non_json_final_output"
                continue
            if selected_outflow <= 0.0:
                acceptance_failure_reason = "non_positive_outflow"
                continue

            accepted_evidence_pair, accepted_attempt_index, linkage_failure = (
                self._select_evidence_pair(
                    selected_outflow=selected_outflow,
                    normalized_events=normalized_events,
                )
            )
            if accepted_evidence_pair is not None:
                acceptance_failure_reason = None
                break
            acceptance_failure_reason = linkage_failure or "missing_evidence_link"

        tool_call_count = len(tool_calls_detail)

        total_time = time.time() - start_time
        return {
            "scenario_id": scenario["id"],
            "method": "agno_mcp_agent",
            "model": model_id,
            "outflow": parsed["outflow"],
            "reasoning": parsed["reasoning"],
            "constraint_check": parsed["constraint_check"],
            "parse_warning": parsed["parse_warning"],
            "parsed_from": parsed["parsed_from"],
            "llm_temperature": temperature,
            "llm_seed": seed,
            "final_decision_text": final_text,
            "tool_call_count": tool_call_count,
            "tool_call_chain": [tc.get("tool_name", "unknown") for tc in tool_calls_detail],
            "tool_calls_detail": tool_calls_detail,
            "llm_execution_trace": {
                "user_message": user_message,
                "tool_events": tool_call_events,
                "attempts": max_attempts,
            },
            "accepted_attempt_index": accepted_attempt_index,
            "acceptance_failure_reason": acceptance_failure_reason,
            "accepted_evidence_pair": accepted_evidence_pair,
            "total_time_seconds": round(total_time, 3),
            "success": accepted_evidence_pair is not None,
        }
