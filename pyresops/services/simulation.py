"""Simulation service for running dispatch programs."""

from __future__ import annotations

from ..core.engine import SimulationEngine
from ..core.orchestrator import DecisionOrchestrator
from ..domain.forecast import ForecastBundle
from ..domain.policy import PolicyBundle
from ..domain.program import DispatchProgram
from ..domain.reservoir import ReservoirSpec, ReservoirState
from ..domain.result import SimulationResult
from ..modules import assert_supported_base_release_module_type
from ..plugins import PluginBundleConfig, PluginManager, PostPluginContext


class SimulationService:
    """Run dispatch programs against reservoir simulation."""

    def __init__(
        self,
        spec: ReservoirSpec,
        module_registry: dict[str, type],
        plugin_manager: PluginManager | None = None,
        default_plugin_bundle: PluginBundleConfig | None = None,
    ):
        self.spec = spec
        self.module_registry = module_registry
        self.engine = SimulationEngine(spec)
        self._results: dict[str, SimulationResult] = {}
        self.plugin_manager = plugin_manager
        self.default_plugin_bundle = default_plugin_bundle

    def run_simulation(
        self,
        program: DispatchProgram,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        policy_bundle: PolicyBundle | None = None,
        orchestrator: DecisionOrchestrator | None = None,
        plugin_bundle: PluginBundleConfig | None = None,
    ) -> SimulationResult:
        self._validate_program(program)

        active_plugin_bundle = plugin_bundle or self.default_plugin_bundle
        resolved_forecast = forecast
        plugin_results: dict[str, object] = {}
        if self.plugin_manager and active_plugin_bundle:
            (
                resolved_forecast,
                prepared_results,
                active_plugin_bundle,
            ) = self.plugin_manager.prepare_forecast(
                forecast=forecast,
                initial_state=initial_state,
                plugin_bundle=active_plugin_bundle,
            )
            plugin_results.update(prepared_results)

        if policy_bundle is not None and orchestrator is None:
            orchestrator = DecisionOrchestrator()

        modules: dict[str, object] = {}
        for module_instance in program.module_sequence:
            module_type = module_instance.module_type
            assert_supported_base_release_module_type(module_type)
            module_class = self.module_registry[module_type]
            modules[module_type] = module_class(module_instance.parameters)

        result = self.engine.simulate(
            program,
            initial_state,
            resolved_forecast,
            modules,
            policy_bundle=policy_bundle,
            orchestrator=orchestrator,
            plugin_manager=self.plugin_manager,
            plugin_bundle=active_plugin_bundle,
        )
        if (
            self.plugin_manager
            and active_plugin_bundle
            and active_plugin_bundle.post is not None
        ):
            post_result = self.plugin_manager.execute_post(
                selection=active_plugin_bundle.post,
                context=PostPluginContext(simulation_result=result),
            )
            if post_result is not None:
                plugin_results["post"] = self.plugin_manager.pack_selection_result(
                    selection=active_plugin_bundle.post,
                    result=post_result,
                )
        existing_plugin_results = result.metadata.get("plugin_results", {})
        if existing_plugin_results:
            plugin_results = {**existing_plugin_results, **plugin_results}
        if plugin_results:
            result.metadata["plugin_results"] = plugin_results
            warnings: list[str] = []
            for value in plugin_results.values():
                if isinstance(value, dict):
                    warnings.extend(value.get("warnings", []))
            if warnings:
                result.metadata["plugin_warnings"] = warnings
        self._results[result.program_id] = result
        return result

    def _validate_program(self, program: DispatchProgram) -> None:
        for module in program.module_sequence:
            assert_supported_base_release_module_type(module.module_type)
        for condition in program.switch_conditions:
            assert_supported_base_release_module_type(condition.from_module)
            assert_supported_base_release_module_type(condition.to_module)

    def get_result(self, program_id: str) -> SimulationResult | None:
        return self._results.get(program_id)
