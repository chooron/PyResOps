"""Integration tests for MCP tools."""

from datetime import datetime

from res_ops.services import (
    ProgramService,
    SnapshotService,
    SimulationService,
    EvaluationService,
    ExplanationService,
)
from res_ops.domain.program import TimeHorizon


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
