"""Simulation service for running dispatch programs."""

from ..core.engine import SimulationEngine
from ..core.orchestrator import DecisionOrchestrator
from ..domain.forecast import ForecastBundle
from ..domain.policy import PolicyBundle
from ..domain.program import DispatchProgram
from ..domain.release import SegmentedReleaseSchedule
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
        policy_bundle: PolicyBundle | None = None,
        orchestrator: DecisionOrchestrator | None = None,
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
        self._validate_program(program)

        if policy_bundle is not None and orchestrator is None:
            orchestrator = DecisionOrchestrator()

        # 实例化操作模块
        modules: dict[str, object] = {}
        for module_instance in program.module_sequence:
            module_type = module_instance.module_type
            if module_type not in self.module_registry:
                continue

            module_class = self.module_registry[module_type]

            if module_type == "flexible_release":
                schedule = SegmentedReleaseSchedule.from_module_parameters(
                    parameters=module_instance.parameters,
                    start=program.time_horizon.start,
                    end=program.time_horizon.end,
                )
                module_instance.parameters = schedule.to_module_parameters()
                module = module_class(module_instance.parameters)
                if hasattr(module, "bind_schedule"):
                    module.bind_schedule(schedule)
            else:
                module = module_class(module_instance.parameters)

            modules[module_type] = module

        # 执行仿真
        result = self.engine.simulate(
            program,
            initial_state,
            forecast,
            modules,
            policy_bundle=policy_bundle,
            orchestrator=orchestrator,
        )

        # 保存结果
        self._results[result.program_id] = result

        return result

    def _validate_program(self, program: DispatchProgram) -> None:
        """Validate V1 executable-program constraints."""
        flexible_count = sum(
            1 for m in program.module_sequence if m.module_type == "flexible_release"
        )
        if flexible_count > 1:
            raise ValueError("V1 supports at most one flexible_release module per program")

        if flexible_count > 0 and program.switch_conditions:
            raise ValueError("V1 does not allow mixing flexible_release with switch_conditions")

    def get_result(self, program_id: str) -> SimulationResult | None:
        """获取仿真结果."""
        return self._results.get(program_id)
