"""Simulation service for running dispatch programs."""

from ..core.engine import SimulationEngine
from ..domain.forecast import ForecastBundle
from ..domain.program import DispatchProgram
from ..domain.reservoir import ReservoirSpec, ReservoirState
from ..domain.result import SimulationResult


class SimulationService:
    """仿真服务 (Simulation Service)."""

    def __init__(self, spec: ReservoirSpec, module_registry: dict[str, type]):
        """初始化仿真服务."""
        self.spec = spec
        self.module_registry = module_registry
        self.engine = SimulationEngine(spec)
        self._results: dict[str, SimulationResult] = {}

    def run_simulation(
        self,
        program: DispatchProgram,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
    ) -> SimulationResult:
        """
        运行仿真.

        Args:
            program: 调度方案
            initial_state: 初始状态
            forecast: 预报数据

        Returns:
            仿真结果
        """
        # 实例化操作模块
        modules = {}
        for module_instance in program.module_sequence:
            module_type = module_instance.module_type
            if module_type in self.module_registry:
                module_class = self.module_registry[module_type]
                modules[module_type] = module_class(module_instance.parameters)

        # 执行仿真
        result = self.engine.simulate(program, initial_state, forecast, modules)

        # 保存结果
        self._results[result.program_id] = result

        return result

    def get_result(self, program_id: str) -> SimulationResult | None:
        """获取仿真结果."""
        return self._results.get(program_id)
