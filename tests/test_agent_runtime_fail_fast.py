from __future__ import annotations

import textwrap
import types

import pytest

from experiments.scenario_config import get_scenario
from pyresops.agents import ReservoirAgentRuntime
from pyresops.agents.config_loader import AgentModelConfigLoader
from pyresops.agents.runner import ReservoirAgentRunner


def _write_temp_config(tmp_path, api_key_env: str) -> str:
    cfg_path = tmp_path / "config.yml"
    cfg_path.write_text(
        textwrap.dedent(
            f"""
            default_profile: test
            models:
              test:
                provider: openai_like
                model_id: fake-model
                base_url: https://example.com/v1
                api_key_env: '{api_key_env}'
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return str(cfg_path)


def test_config_loader_accepts_literal_key_in_api_key_env(tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="sk-literal-test-key")
    cfg = AgentModelConfigLoader.load(profile="test", config_path=cfg_path)
    assert cfg["api_key"] == "sk-literal-test-key"


def test_config_loader_raises_when_missing_api_key(tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="MISSING_ENV_KEY")
    with pytest.raises(ValueError, match="MISSING_ENV_KEY"):
        AgentModelConfigLoader.load(profile="test", config_path=cfg_path)


def test_run_scenario_fails_if_no_tool_calls(monkeypatch, tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="sk-literal-test-key")
    runtime = ReservoirAgentRuntime(model_profile="test", config_path=cfg_path)
    scenario = get_scenario("S01")

    class FakeResponse:
        content = '{"outflow": 300.0, "reasoning": "ok", "constraint_check": "ok"}'
        tools = []

    class FakeAgent:
        def __init__(self):
            self.calls = 0

        def run(self, _):
            self.calls += 1
            return FakeResponse()

    monkeypatch.setattr(runtime, "_get_spec", lambda _: object())
    monkeypatch.setattr(
        runtime, "_build_agent", lambda _spec, _scenario: FakeAgent(), raising=False
    )
    if hasattr(runtime, "_runner"):

        class FakeRunner:
            @staticmethod
            def run(**kwargs):
                return {
                    "scenario_id": kwargs["scenario"]["id"],
                    "outflow": float(kwargs["scenario"]["inflow"]),
                    "tool_call_count": 0,
                    "tool_call_chain": [],
                    "tool_calls_detail": [],
                    "llm_execution_trace": {"attempts": runtime.max_attempts, "tool_events": []},
                    "accepted_attempt_index": None,
                    "acceptance_failure_reason": "missing_simulation",
                    "success": False,
                }

        monkeypatch.setattr(runtime, "_runner", FakeRunner())

    result = runtime.run_scenario(scenario)
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "missing_simulation"


def test_run_scenario_fails_if_output_is_not_json(monkeypatch, tmp_path) -> None:
    cfg_path = _write_temp_config(tmp_path, api_key_env="sk-literal-test-key")
    runtime = ReservoirAgentRuntime(model_profile="test", config_path=cfg_path)
    scenario = get_scenario("S01")

    class FakeRunner:
        @staticmethod
        def run(**kwargs):
            return {
                "scenario_id": kwargs["scenario"]["id"],
                "outflow": float(kwargs["scenario"]["inflow"]),
                "tool_call_count": 0,
                "tool_call_chain": [],
                "tool_calls_detail": [],
                "llm_execution_trace": {"attempts": runtime.max_attempts, "tool_events": []},
                "accepted_attempt_index": None,
                "acceptance_failure_reason": "non_json_final_output",
                "success": False,
            }

    monkeypatch.setattr(runtime, "_runner", FakeRunner())

    result = runtime.run_scenario(scenario)
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "non_json_final_output"


class _FakeAgent:
    def __init__(self, responses):
        self._responses = responses
        self._idx = 0

    def run(self, _prompt):
        response = self._responses[self._idx]
        self._idx = min(self._idx + 1, len(self._responses) - 1)
        return response


def _install_fake_agno_agent(monkeypatch, responses) -> None:
    agent_module = types.SimpleNamespace(Agent=lambda **_kwargs: _FakeAgent(responses))
    monkeypatch.setitem(__import__("sys").modules, "agno.agent", agent_module)


def _runner_args() -> dict:
    return {
        "scenario": {
            "id": "S01",
            "name": "demo",
            "description": "demo",
            "inflow": 1000.0,
            "initial_inflow": 900.0,
            "current_level": 157.0,
            "target_level": 156.5,
            "season": "flood",
            "flood_risk": "high",
        },
        "spec": object(),
        "model_cfg": {"provider": "openai_like", "model_id": "fake", "api_key": "k"},
        "system_prompt": "prompt",
        "tools": [],
        "max_attempts": 2,
        "model_id": "fake",
        "temperature": 0.0,
        "seed": 1,
    }


def _result_payload(declared_outflow: float) -> str:
    return '{"declared_outflow": ' + str(float(declared_outflow)) + "}"


def test_acceptance_rejects_cross_attempt_mismatch(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response_1 = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {"name": "simulate_dispatch_program", "result": _result_payload(350.0)},
        ],
    )
    response_2 = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {"name": "evaluate_dispatch_result", "result": _result_payload(350.0)},
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response_1, response_2])

    result = ReservoirAgentRunner().run(**_runner_args())
    assert result["success"] is False
    assert result["accepted_attempt_index"] is None
    assert result["acceptance_failure_reason"] == "cross_attempt_mismatch"


def test_acceptance_accepts_same_attempt_pair(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {"name": "simulate_dispatch_program", "result": _result_payload(350.0)},
            {"name": "evaluate_dispatch_result", "result": _result_payload(350.0)},
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_runner_args())
    assert result["success"] is True
    assert result["accepted_attempt_index"] == 1
