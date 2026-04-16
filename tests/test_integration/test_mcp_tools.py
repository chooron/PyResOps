"""Integration tests for MCP tools."""

from datetime import datetime
import json
import types

from pyresops.services import (
    ProgramService,
    SnapshotService,
    SimulationService,
    EvaluationService,
    ExplanationService,
)
from pyresops.domain.program import TimeHorizon
from pyresops.agents import ReservoirToolBundleFactory


def test_end_to_end_workflow(sample_reservoir_spec, sample_forecast):
    """测试端到端工作流."""
    # 初始化服务
    snapshot_service = SnapshotService()
    program_service = ProgramService()
    simulation_service = SimulationService(
        sample_reservoir_spec, program_service.get_module_registry()
    )
    evaluation_service = EvaluationService(sample_reservoir_spec)
    explanation_service = ExplanationService()

    # 1. 创建快照
    initial_state = snapshot_service.create_initial_snapshot(
        reservoir_id="test_res", spec=sample_reservoir_spec, level=165.0, inflow=8000.0
    )

    # 2. 创建方案
    program = program_service.create_program(
        name="端到端测试方案",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_configs=[
            {"module_type": "inflow_driven", "parameters": {"coefficient": 1.0}},
        ],
    )

    # 3. 运行仿真
    result = simulation_service.run_simulation(program, initial_state, sample_forecast)
    assert result.program_id == program.id

    # 4. 评估方案
    evaluation = evaluation_service.evaluate(result)
    assert evaluation.overall_score >= 0

    # 5. 生成解释
    explanation = explanation_service.explain_program(program, result, evaluation)
    assert explanation["program_id"] == program.id
    assert "summary" in explanation


def test_module_listing(sample_reservoir_spec):
    """测试模块列举."""
    program_service = ProgramService()

    modules = program_service.list_available_modules()

    assert len(modules) >= 3
    module_types = [m["module_type"] for m in modules]
    assert "constant_release" in module_types
    assert "inflow_driven" in module_types
    assert "storage_driven" in module_types
    assert "flexible_release" in module_types


def test_tool_bundle_rejects_unsupported_module_type(monkeypatch):
    agno_tools = types.SimpleNamespace(tool=lambda fn: fn)
    monkeypatch.setitem(__import__("sys").modules, "agno.tools", agno_tools)

    scenario = {
        "id": "S01",
        "name": "demo",
        "description": "demo",
        "flood_limit_level": 156.5,
        "current_level": 157.5,
        "initial_storage": 33.1,
        "initial_inflow": 1000.0,
        "inflow": 1200.0,
        "target_level": 156.5,
        "season": "flood",
        "flood_risk": "high",
        "duration_hours": 24,
        "time_step_hours": 6,
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
                return 6000.0

        discharge_capacity = _DC()

    factory = ReservoirToolBundleFactory(
        scenario_resolver=lambda sid: scenario if sid == "S01" else None
    )
    tools = {tool.__name__: tool for tool in factory.make_tools(_Spec(), runtime_scenario=scenario)}

    payload = json.loads(
        tools["simulate_dispatch_program"](
            scenario_id="S01",
            target_outflow=1000.0,
            module_type="legacy_mode",
        )
    )

    assert payload["error"] == "unsupported_module_type"
    assert payload["module_type"] == "legacy_mode"
