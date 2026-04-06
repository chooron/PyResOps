"""Tests for simulation service."""

from datetime import datetime

from res_ops.services import SimulationService, ProgramService
from res_ops.domain.program import TimeHorizon


def test_simulation_service(sample_reservoir_spec, sample_initial_state, sample_forecast):
    """测试仿真服务."""
    program_service = ProgramService()
    simulation_service = SimulationService(
        sample_reservoir_spec, program_service.get_module_registry()
    )

    # 创建方案
    program = program_service.create_program(
        name="测试方案",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_configs=[{"module_type": "constant_release", "parameters": {"target_flow": 7000.0}}],
    )

    # 运行仿真
    result = simulation_service.run_simulation(program, sample_initial_state, sample_forecast)

    assert result.program_id == program.id
    assert len(result.snapshots) > 0

    # 获取结果
    retrieved = simulation_service.get_result(program.id)
    assert retrieved is not None
    assert retrieved.program_id == result.program_id
