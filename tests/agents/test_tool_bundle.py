from __future__ import annotations

import json
import types

from pyresops.agents import ReservoirToolBundleFactory


def test_tool_bundle_factory_returns_expected_tools(monkeypatch) -> None:
    agno_tools = types.SimpleNamespace(tool=lambda fn: fn)
    monkeypatch.setitem(__import__("sys").modules, "agno.tools", agno_tools)

    scenario = {
        "id": "S01",
        "current_level": 157.5,
        "initial_storage": 33.1,
        "initial_inflow": 1000.0,
        "inflow": 1200.0,
        "flood_limit_level": 156.5,
        "season": "flood",
        "flood_risk": "high",
        "time_step_hours": 6,
        "duration_hours": 24,
        "name": "demo",
    }

    class _Spec:
        dead_level = 120.0
        normal_level = 160.0
        design_flood_level = 165.87
        total_capacity = 41.9
        flood_capacity = 3.5

        class _DC:
            @staticmethod
            def get_max_discharge(_level):
                return 5000.0

        discharge_capacity = _DC()

    factory = ReservoirToolBundleFactory(
        scenario_resolver=lambda sid: scenario if sid == "S01" else None
    )
    tools = factory.make_tools(_Spec(), runtime_scenario=None)

    names = {tool.__name__ for tool in tools}
    assert {
        "get_reservoir_status",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
        "check_safety_constraints",
        "optimize_release_plan",
        "query_dispatch_rules",
    }.issubset(names)


def test_tool_bundle_factory_supports_runtime_injection() -> None:
    factory = ReservoirToolBundleFactory(scenario_resolver=lambda _sid: None)
    runtime = {"id": "S99", "name": "runtime-only"}
    resolved = factory.resolve_scenario_config("S99", runtime_scenario=runtime)
    assert resolved is runtime


def test_simulate_dispatch_program_rejects_unsupported_module_type(monkeypatch) -> None:
    agno_tools = types.SimpleNamespace(tool=lambda fn: fn)
    monkeypatch.setitem(__import__("sys").modules, "agno.tools", agno_tools)

    scenario = {
        "id": "S01",
        "current_level": 157.5,
        "initial_storage": 33.1,
        "initial_inflow": 1000.0,
        "inflow": 1200.0,
        "flood_limit_level": 156.5,
        "season": "flood",
        "flood_risk": "high",
        "time_step_hours": 6,
        "duration_hours": 24,
        "name": "demo",
    }

    class _Spec:
        dead_level = 120.0
        normal_level = 160.0
        design_flood_level = 165.87
        total_capacity = 41.9
        flood_capacity = 3.5

        class _DC:
            @staticmethod
            def get_max_discharge(_level):
                return 5000.0

        discharge_capacity = _DC()

    factory = ReservoirToolBundleFactory(
        scenario_resolver=lambda sid: scenario if sid == "S01" else None
    )
    tools = {tool.__name__: tool for tool in factory.make_tools(_Spec(), runtime_scenario=None)}
    payload = json.loads(
        tools["simulate_dispatch_program"](
            scenario_id="S01",
            target_outflow=800.0,
            module_type="unsupported_mode",
        )
    )

    assert payload["error"] == "unsupported_module_type"
    assert payload["module_type"] == "unsupported_mode"
    assert payload["supported_module_types"] == ["constant_release", "flexible_release"]
