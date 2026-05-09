"""Public facade for Agno reservoir agent execution."""

from __future__ import annotations

from typing import Any

from pyresops.agents.config_loader import AgentModelConfigLoader
from pyresops.agents.prompts import ReservoirPromptPack
from pyresops.agents.runner import ReservoirAgentRunner
from pyresops.agents.specs import load_default_experiment_spec
from pyresops.agents.tool_bundle import ReservoirToolBundleFactory


class ReservoirAgentRuntime:
    """Compose config, prompt pack, tools, and Agno runner."""

    def __init__(
        self,
        model_profile: str | None = None,
        config_path: str | None = None,
        max_attempts: int = 1,
        scenario_resolver=None,
        *,
        config_loader: AgentModelConfigLoader | None = None,
        prompt_pack: ReservoirPromptPack | None = None,
        tool_bundle_factory: ReservoirToolBundleFactory | None = None,
        runner: ReservoirAgentRunner | None = None,
    ):
        self._config_loader = config_loader or AgentModelConfigLoader()
        self._prompt_pack = prompt_pack or ReservoirPromptPack()
        self._tool_bundle_factory = tool_bundle_factory or ReservoirToolBundleFactory(
            scenario_resolver=scenario_resolver
        )
        self._runner = runner or ReservoirAgentRunner()
        self._model_cfg = self._config_loader.load(profile=model_profile, config_path=config_path)
        self.model_id = str(self._model_cfg.get("model_id", "unknown"))
        self.model_profile = model_profile or str(self._model_cfg.get("profile", ""))
        self.max_attempts = max(1, int(max_attempts))

    def _resolve_temperature(self, scenario: dict[str, Any]) -> float:
        if scenario.get("temperature_override") is not None:
            return float(scenario["temperature_override"])
        return float(self._model_cfg.get("temperature", 0.0))

    def _resolve_seed(self, scenario: dict[str, Any]) -> int | None:
        if scenario.get("llm_seed") is not None:
            return int(scenario["llm_seed"])
        reproducibility = scenario.get("reproducibility")
        if isinstance(reproducibility, dict) and reproducibility.get("llm_seed") is not None:
            return int(reproducibility["llm_seed"])
        if self._model_cfg.get("seed") is not None:
            return int(self._model_cfg["seed"])
        return None

    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        spec = load_default_experiment_spec()
        tools = self._tool_bundle_factory.make_tools(spec, runtime_scenario=payload)
        return self._runner.run(
            scenario=payload,
            spec=spec,
            model_cfg=self._model_cfg,
            system_prompt=self._prompt_pack.system_prompt(payload),
            tools=tools,
            max_attempts=self.max_attempts,
            model_id=self.model_id,
            temperature=self._resolve_temperature(payload),
            seed=self._resolve_seed(payload),
        )
