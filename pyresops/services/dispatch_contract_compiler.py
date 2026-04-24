from __future__ import annotations

import re
from typing import Any

from pyresops.domain.dispatch import (
    CompiledDispatchContract,
    CompilerMessage,
    FallbackTerm,
    HardConstraint,
    ObjectiveTerm,
    ReportingRequirement,
    TaskConstraint,
)


class DispatchContractCompiler:
    """Compile scenario facts, rule payloads, and optional user hints into a solve contract."""

    REQUIRED_RULE_FACT_KEYS = (
        "flood_limit_level_m",
        "eco_min_flow_m3s",
        "downstream_safe_flow_m3s",
        "deadline_hours",
    )
    S01_CANONICAL_RULE_KEYS = (
        "effective_horizon_hours",
        "advance_hours",
        "deadline_source",
    )
    KEY_PARAMS_ALIASES = (
        "关键参数",
        "鍏抽敭鍙傛暟",
        "閸忔娊鏁崣鍌涙殶",
    )
    CORE_REQUIREMENTS_ALIASES = (
        "核心要求",
        "鏍稿績瑕佹眰",
        "閺嶇绺剧憰浣圭湴",
    )

    @staticmethod
    def _first_dict(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _first_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def normalize_rule_payload(self, rule_payload: dict[str, Any]) -> tuple[dict[str, Any], list[CompilerMessage]]:
        messages: list[CompilerMessage] = []
        normalized: dict[str, Any] = {}
        canonical_contract = rule_payload.get("s01_rule_contract")
        canonical_contract = canonical_contract if isinstance(canonical_contract, dict) else {}

        key_params = self._first_dict(rule_payload, self.KEY_PARAMS_ALIASES)
        for key in ("flood_limit_level_m", "downstream_safe_flow_m3s", "eco_min_flow_m3s"):
            if key in key_params:
                normalized[key] = float(key_params[key])

        for key in ("flood_limit_level_m", "downstream_safe_flow_m3s", "eco_min_flow_m3s"):
            if key in rule_payload and key not in normalized:
                normalized[key] = float(rule_payload[key])

        for key in self.S01_CANONICAL_RULE_KEYS:
            if key in rule_payload:
                normalized[key] = rule_payload[key]
            elif key in canonical_contract:
                normalized[key] = canonical_contract[key]

        deadline = rule_payload.get("deadline_hours")
        if deadline is None:
            deadline = rule_payload.get("effective_horizon_hours")
        if deadline is None:
            deadline = canonical_contract.get("effective_horizon_hours")
        if deadline is not None:
            normalized["deadline_hours"] = float(deadline)

        core_requirements = self._first_list(rule_payload, self.CORE_REQUIREMENTS_ALIASES)
        if "deadline_hours" not in normalized:
            deadline = self._extract_deadline_hours(core_requirements)
            if deadline is not None:
                normalized["deadline_hours"] = deadline

        missing = [key for key in self.REQUIRED_RULE_FACT_KEYS if key not in normalized]
        for key in missing:
            messages.append(
                CompilerMessage(
                    code="missing_rule_numeric_constraint",
                    message=f"Missing normalized rule fact: {key}",
                    severity="error",
                )
            )

        return normalized, messages

    def compile_contract(
        self,
        *,
        scenario: dict[str, Any],
        status_payload: dict[str, Any],
        rule_payload: dict[str, Any],
        spec,
        user_instruction: dict[str, Any] | None = None,
    ) -> CompiledDispatchContract:
        user_instruction = user_instruction or {}
        normalized_rule_facts, messages = self.normalize_rule_payload(rule_payload)
        if (
            str(scenario.get("id", "")).strip() == "S01"
            and "deadline_hours" not in normalized_rule_facts
            and scenario.get("duration_hours") is not None
        ):
            normalized_rule_facts["deadline_hours"] = float(scenario["duration_hours"])
        hard_constraints: list[HardConstraint] = []
        task_constraints: list[TaskConstraint] = []
        objective_terms: list[ObjectiveTerm] = []
        fallback_terms: list[FallbackTerm] = []
        reporting_requirements: list[ReportingRequirement] = [
            ReportingRequirement(id="task_completion", type="report_task_completion"),
            ReportingRequirement(id="unmet_constraints", type="report_unmet_constraints"),
            ReportingRequirement(id="solve_stage", type="report_solve_stage"),
            ReportingRequirement(id="compile_warnings", type="report_compile_warnings"),
        ]

        current_level = float(status_payload["current_level_m"])
        hard_constraints.extend(
            [
                HardConstraint(
                    id="dead_level",
                    type="level_min",
                    parameters={"level_m": float(status_payload["dead_level_m"])},
                    source="scenario",
                ),
                HardConstraint(
                    id="normal_level",
                    type="level_max",
                    parameters={"level_m": float(status_payload["normal_level_m"])},
                    source="scenario",
                ),
                HardConstraint(
                    id="discharge_capacity",
                    type="discharge_capacity",
                    parameters={
                        "max_discharge_m3s": float(
                            spec.discharge_capacity.get_max_discharge(current_level)
                        )
                    },
                    source="scenario",
                ),
            ]
        )
        if "eco_min_flow_m3s" in normalized_rule_facts:
            hard_constraints.append(
                HardConstraint(
                    id="eco_min_flow",
                    type="ecological_min_flow",
                    parameters={"flow_m3s": float(normalized_rule_facts["eco_min_flow_m3s"])},
                    source="rules",
                )
            )
        if "downstream_safe_flow_m3s" in normalized_rule_facts:
            hard_constraints.append(
                HardConstraint(
                    id="downstream_safe_flow",
                    type="flow_max",
                    parameters={
                        "flow_m3s": float(normalized_rule_facts["downstream_safe_flow_m3s"])
                    },
                    source="rules",
                )
            )

        if user_instruction.get("override_hard_constraints") or user_instruction.get(
            "hard_constraints"
        ):
            messages.append(
                CompilerMessage(
                    code="conflicting_user_constraint_with_hard_rule",
                    message="User instruction attempted to override hard safety constraints.",
                    severity="error",
                )
            )

        if {"target_level", "deadline_hours"} <= normalized_rule_facts.keys() or (
            "target_level" in scenario and "deadline_hours" in normalized_rule_facts
        ):
            task_constraints.append(
                TaskConstraint(
                    id="deadline_target_level",
                    type="deadline_level_target",
                    parameters={
                        "target_level_m": float(scenario["target_level"]),
                        "deadline_hours": float(normalized_rule_facts["deadline_hours"]),
                        "tolerance_m": 0.0,
                    },
                    source="rules",
                )
            )

        for item in user_instruction.get("quantitative_constraints", []):
            if not isinstance(item, dict):
                continue
            task_constraints.append(
                TaskConstraint(
                    id=str(item.get("id", "user_quantitative_constraint")),
                    type="quantitative_requirement",
                    parameters={
                        "metric": str(item.get("metric", "")),
                        "operator": str(item.get("operator", "<=")),
                        "value": float(item.get("value", 0.0)),
                        "unit": str(item.get("unit", "")),
                    },
                    source="user_instruction",
                )
            )

        objective_type = self._resolve_objective_type(scenario, user_instruction, messages)
        if objective_type is not None:
            objective_terms.append(
                ObjectiveTerm(
                    id="primary_objective",
                    type=objective_type,
                    weight=1.0,
                    source=(
                        "user_instruction" if user_instruction.get("objective_family") else "default_compiler_policy"
                    ),
                )
            )

        fallback_terms.append(
            FallbackTerm(
                id="fallback_terminal_level_deviation",
                type="min_terminal_level_deviation",
                weight=1.0,
                source="compiler_policy",
            )
        )

        status = "ok"
        if any(item.severity == "error" for item in messages):
            status = "error"
        elif messages:
            status = "warning"

        return CompiledDispatchContract(
            scenario_id=str(scenario["id"]),
            hard_constraints=hard_constraints,
            task_constraints=task_constraints,
            objective_terms=objective_terms,
            fallback_terms=fallback_terms,
            reporting_requirements=reporting_requirements,
            status=status,
            messages=messages,
            normalized_rule_facts=normalized_rule_facts,
        )

    def _resolve_objective_type(
        self,
        scenario: dict[str, Any],
        user_instruction: dict[str, Any],
        messages: list[CompilerMessage],
    ) -> str | None:
        requested = user_instruction.get("objective_family")
        if requested:
            if requested in {"flood_control", "power_generation"}:
                return "min_avg_release" if requested == "flood_control" else "max_generation"
            messages.append(
                CompilerMessage(
                    code="unsupported_objective_family",
                    message=f"Unsupported objective family: {requested}",
                    severity="warning",
                )
            )

        text = str(user_instruction.get("text", "")).strip()
        if text and not requested:
            messages.append(
                CompilerMessage(
                    code="unmapped_instruction_phrase",
                    message="User instruction text did not map to an explicit objective family.",
                    severity="warning",
                )
            )

        key_dimension = str(scenario.get("key_dimension", ""))
        if key_dimension == "power_generation_score" or scenario.get("season") == "dry":
            return "max_generation"
        return "min_avg_release"

    @staticmethod
    def _extract_deadline_hours(requirements: list[Any]) -> float | None:
        for item in requirements:
            if not isinstance(item, str):
                continue
            lowered = item.lower()
            if any(token in lowered for token in ("hour", "hours", "h", "小时")):
                match = re.search(r"(\d+(?:\.\d+)?)", item)
                if match:
                    return float(match.group(1))
        return None
