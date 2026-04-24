from __future__ import annotations

from datetime import datetime
from typing import Any


DEFAULT_SCENARIO_START_TIME = datetime(2025, 6, 1, 0, 0, 0)
S01_SCENARIO_ID = "S01"
S01_DEADLINE_SOURCES = {
    "explicit_task",
    "explicit_trigger",
    "inherited_remaining",
    "process_length_fallback",
}


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_positive(value: Any) -> float | None:
    parsed = _coerce_float(value)
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


def resolve_scenario_start_time(scenario: dict) -> datetime:
    for key in (
        "scenario_start_time",
        "start_time",
        "start_timestamp",
        "forecast_start_time",
    ):
        parsed = _parse_datetime(scenario.get(key))
        if parsed is not None:
            return parsed
    return DEFAULT_SCENARIO_START_TIME


def resolve_process_length_hours(scenario: dict) -> float:
    contract = scenario.get("time_contract")
    if isinstance(contract, dict):
        explicit = _coerce_positive(contract.get("process_length_hours"))
        if explicit is not None:
            return explicit

    sequence = scenario.get("benchmark_inflow_series_m3s")
    step_hours = _coerce_positive(scenario.get("time_step_hours"))
    if isinstance(sequence, list) and sequence and step_hours is not None:
        return float(len(sequence)) * step_hours

    duration_hours = _coerce_positive(scenario.get("duration_hours"))
    if duration_hours is not None:
        return duration_hours
    return 0.0


def resolve_s01_rule_contract(
    scenario: dict,
    *,
    current_plan: dict | None = None,
    advance_hours: float | None = None,
) -> dict[str, Any] | None:
    if str(scenario.get("id")) != S01_SCENARIO_ID:
        return None

    contract = scenario.get("time_contract")
    contract = dict(contract) if isinstance(contract, dict) else {}
    legacy_context = scenario.get("deadline_context")
    legacy_context = dict(legacy_context) if isinstance(legacy_context, dict) else {}
    process_length_hours = resolve_process_length_hours(scenario)
    scheduled_hours_before_update = _coerce_float(
        scenario.get("scheduled_hours_before_update")
    )
    if scheduled_hours_before_update is None:
        scheduled_hours_before_update = _coerce_float(
            contract.get("scheduled_hours_before_update")
        )
    if scheduled_hours_before_update is None:
        scheduled_hours_before_update = _coerce_float(
            legacy_context.get("elapsed_hours_since_plan_start")
        )
    if scheduled_hours_before_update is None:
        scheduled_hours_before_update = 0.0

    explicit_deadline_hours = _coerce_positive(contract.get("explicit_deadline_hours"))
    if explicit_deadline_hours is None:
        explicit_deadline_hours = _coerce_positive(scenario.get("deadline_hours"))

    trigger_override_hours = _coerce_positive(contract.get("trigger_override_hours"))
    if trigger_override_hours is None:
        trigger_override_hours = _coerce_positive(legacy_context.get("trigger_override_deadline_hours"))

    inherited_remaining_hours = None
    if isinstance(current_plan, dict):
        inherited_remaining_hours = _coerce_positive(current_plan.get("remaining_horizon_hours"))
    if inherited_remaining_hours is None:
        remaining_before_update = _coerce_positive(legacy_context.get("remaining_hours_before_update"))
        elapsed_since_last_update = _coerce_float(legacy_context.get("elapsed_hours_since_last_update"))
        if remaining_before_update is not None:
            if elapsed_since_last_update is not None:
                inherited_remaining_hours = max(0.0, remaining_before_update - max(elapsed_since_last_update, 0.0))
            else:
                inherited_remaining_hours = remaining_before_update

    if trigger_override_hours is not None:
        effective_horizon_hours = trigger_override_hours
        deadline_source = "explicit_trigger"
    elif explicit_deadline_hours is not None:
        effective_horizon_hours = explicit_deadline_hours
        deadline_source = "explicit_task"
    elif inherited_remaining_hours is not None:
        effective_horizon_hours = inherited_remaining_hours
        deadline_source = "inherited_remaining"
    else:
        if scheduled_hours_before_update > 0.0:
            return None
        # Initial instruction fallback: no explicit deadline => full initial process length.
        effective_horizon_hours = process_length_hours
        deadline_source = "process_length_fallback"

    resolved_advance_hours = _coerce_float(advance_hours)
    if resolved_advance_hours is None:
        resolved_advance_hours = _coerce_float(contract.get("advance_hours"))
    if resolved_advance_hours is None:
        resolved_advance_hours = _coerce_float(legacy_context.get("elapsed_hours_since_last_update"))
    if resolved_advance_hours is None:
        resolved_advance_hours = float(effective_horizon_hours)

    return {
        "process_length_hours": float(process_length_hours),
        "scheduled_hours_before_update": float(max(scheduled_hours_before_update, 0.0)),
        "explicit_deadline_hours": explicit_deadline_hours,
        "trigger_override_hours": trigger_override_hours,
        "remaining_horizon_hours": inherited_remaining_hours,
        "effective_horizon_hours": float(effective_horizon_hours),
        "effective_deadline_hours": float(effective_horizon_hours),
        "advance_hours": float(resolved_advance_hours),
        "deadline_source": deadline_source,
    }


def validate_s01_rule_contract(payload: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "missing_rule_contract"

    contract_payload = payload.get("s01_rule_contract")
    contract_payload = contract_payload if isinstance(contract_payload, dict) else payload

    required_fields = (
        "effective_horizon_hours",
        "advance_hours",
        "deadline_source",
    )
    missing = [field for field in required_fields if field not in contract_payload]
    if missing:
        return False, "missing_s01_deadline_fields"

    process_length = _coerce_positive(contract_payload.get("process_length_hours"))
    effective_horizon = _coerce_positive(contract_payload.get("effective_horizon_hours"))
    effective_deadline = _coerce_positive(contract_payload.get("effective_deadline_hours"))
    advance = _coerce_float(contract_payload.get("advance_hours"))
    if process_length is None:
        return False, "invalid_process_length_hours"
    if effective_horizon is None:
        return False, "invalid_effective_horizon_hours"
    if effective_deadline is None:
        return False, "invalid_effective_deadline_hours"
    if advance is None or advance < 0.0:
        return False, "invalid_advance_hours"

    source = contract_payload.get("deadline_source")
    if source not in S01_DEADLINE_SOURCES:
        return False, "invalid_deadline_source"

    if abs(effective_deadline - effective_horizon) > 1e-6:
        return False, "deadline_horizon_mismatch"

    if source == "process_length_fallback":
        if abs(effective_horizon - process_length) > 1e-6:
            return False, "fallback_not_process_length"
    elif source == "explicit_task":
        explicit = _coerce_positive(contract_payload.get("explicit_deadline_hours"))
        if explicit is None:
            return False, "missing_explicit_deadline_hours"
        if abs(effective_horizon - explicit) > 1e-6:
            return False, "explicit_deadline_mismatch"
    elif source == "explicit_trigger":
        override = _coerce_positive(contract_payload.get("trigger_override_hours"))
        if override is None:
            return False, "missing_trigger_override_hours"
        if abs(effective_horizon - override) > 1e-6:
            return False, "trigger_override_mismatch"
    elif source == "inherited_remaining":
        remaining = _coerce_positive(contract_payload.get("remaining_horizon_hours"))
        if remaining is None:
            return False, "missing_remaining_horizon_hours"
        if abs(effective_horizon - remaining) > 1e-6:
            return False, "remaining_horizon_mismatch"

    legacy_deadline = _coerce_float(contract_payload.get("deadline_hours"))
    if legacy_deadline is not None and abs(legacy_deadline - effective_horizon) > 1e-6:
        return False, "legacy_deadline_mismatch"
    legacy_window = _coerce_float(contract_payload.get("window_hours"))
    if legacy_window is not None and abs(legacy_window - effective_horizon) > 1e-6:
        return False, "legacy_window_mismatch"

    return True, None


def validate_s01_runtime_candidate(
    *,
    scenario: dict[str, Any],
    status_payload: dict[str, Any] | None,
    rules_payload: dict[str, Any] | None,
    optimization_payload: dict[str, Any] | None,
    simulation_payload: dict[str, Any] | None,
    evaluation_payload: dict[str, Any] | None,
    require_optimization: bool,
    declared_outflow_tolerance: float = 1e-6,
) -> tuple[bool, str | None]:
    if str(scenario.get("id")) != S01_SCENARIO_ID:
        return True, None

    if not isinstance(status_payload, dict):
        return False, "malformed_status_result"
    if not isinstance(rules_payload, dict):
        return False, "malformed_rules_result"
    if not isinstance(simulation_payload, dict):
        return False, "malformed_simulation_result"
    if not isinstance(evaluation_payload, dict):
        return False, "malformed_evaluation_result"

    valid_rules, rule_failure = validate_s01_rule_contract(rules_payload)
    if not valid_rules:
        if rule_failure in {
            "missing_rule_contract",
            "missing_s01_deadline_fields",
            "missing_explicit_deadline_hours",
            "missing_trigger_override_hours",
            "missing_remaining_horizon_hours",
        }:
            return False, "missing_rule_deadline_contract"
        if rule_failure in {
            "legacy_deadline_mismatch",
            "legacy_window_mismatch",
            "deadline_horizon_mismatch",
        }:
            return False, "rule_deadline_alias_conflict"
        return False, rule_failure or "invalid_s01_rule_contract"

    current_level = _coerce_float(status_payload.get("current_level_m"))
    forecast_inflow = _coerce_float(status_payload.get("forecast_inflow_m3s"))
    flood_limit = _coerce_float(status_payload.get("flood_limit_level_m"))
    if current_level is None or forecast_inflow is None or flood_limit is None:
        return False, "malformed_status_result"

    simulated_outflow = _coerce_float(simulation_payload.get("declared_outflow"))
    final_level = _coerce_float(simulation_payload.get("final_level_m"))
    eval_declared = _coerce_float(evaluation_payload.get("declared_outflow"))
    violation_count = _coerce_float(evaluation_payload.get("constraint_violations_count"))
    if (
        simulated_outflow is None
        or final_level is None
        or eval_declared is None
        or violation_count is None
    ):
        return False, "malformed_evaluation_result"

    if abs(simulated_outflow - eval_declared) > declared_outflow_tolerance:
        return False, "outflow_mismatch"

    selected_outflow = simulated_outflow
    if require_optimization:
        if not isinstance(optimization_payload, dict):
            return False, "optimize_result_untrustworthy"
        release_values = optimization_payload.get("release_values_m3s")
        avg_release = _coerce_float(optimization_payload.get("avg_release_m3s"))
        min_release = _coerce_float(optimization_payload.get("min_release_m3s"))
        max_release = _coerce_float(optimization_payload.get("max_release_m3s"))
        if (
            not isinstance(release_values, list)
            or not release_values
            or avg_release is None
            or min_release is None
            or max_release is None
        ):
            return False, "optimize_result_untrustworthy"
        release_numbers = [_coerce_float(value) for value in release_values]
        if any(value is None for value in release_numbers):
            return False, "optimize_result_untrustworthy"
        is_constant = (
            abs(min_release - max_release) <= declared_outflow_tolerance
            and all(
                abs(float(value) - avg_release) <= declared_outflow_tolerance
                for value in release_numbers
            )
        )
        if not is_constant:
            return False, "unsupported_optimized_schedule"
        if current_level > flood_limit and avg_release <= forecast_inflow + declared_outflow_tolerance:
            return False, "optimize_result_untrustworthy"
        if abs(simulated_outflow - avg_release) > declared_outflow_tolerance:
            return False, "simulation_outflow_mismatch"
        selected_outflow = avg_release

    if abs(eval_declared - selected_outflow) > declared_outflow_tolerance:
        return False, "outflow_mismatch"

    target_level = _coerce_float(scenario.get("target_level"))
    if target_level is None:
        target_level = flood_limit
    if current_level > target_level and final_level >= current_level - declared_outflow_tolerance:
        return False, "simulation_direction_invalid"
    if final_level > target_level + declared_outflow_tolerance:
        return False, "target_unmet"
    if violation_count > 0:
        return False, "evaluated_candidate_invalid"
    return True, None
