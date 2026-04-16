from __future__ import annotations

import types

from pyresops.agents.runner import ReservoirAgentRunner


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


def _build_args():
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


def _build_static_s01_profile_args():
    args = _build_args()
    args["scenario"] = {
        **args["scenario"],
        "initial_inflow": 400.0,
        "inflow": 400.0,
        "current_level": 157.5,
        "target_level": 156.5,
        "agent_workflow_profile": "static_s01_mcp_chain_v1",
    }
    return args


def test_runner_fails_fast_when_missing_tool_calls(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 300.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[],
    )
    _install_fake_agno_agent(monkeypatch, [response, response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "missing_simulation"


def test_runner_fails_fast_on_non_json_output(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(content="recommend outflow 420 m3/s", tools=[{"name": "t"}])
    _install_fake_agno_agent(monkeypatch, [response, response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "non_json_final_output"


def test_runner_succeeds_with_valid_output(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {"name": "simulate_dispatch_program", "result": _tool_result_payload(350.0)},
            {"name": "evaluate_dispatch_result", "result": _tool_result_payload(350.0)},
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["outflow"] == 350.0
    assert result["parsed_from"] == "json"
    assert result["success"] is True


def _tool_result_payload(declared_outflow: float) -> str:
    return (
        '{"declared_outflow": '
        + str(float(declared_outflow))
        + ', "overall_score": 0.9, "final_level_m": 156.2}'
    )


def test_acceptance_rejects_missing_simulation(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "evaluate_dispatch_result",
                "result": _tool_result_payload(350.0),
            }
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "missing_simulation"


def test_acceptance_rejects_missing_evaluation(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "simulate_dispatch_program",
                "result": _tool_result_payload(350.0),
            }
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "missing_evaluation"


def test_acceptance_rejects_wrong_event_order(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "evaluate_dispatch_result",
                "result": _tool_result_payload(350.0),
            },
            {
                "name": "simulate_dispatch_program",
                "result": _tool_result_payload(350.0),
            },
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "evaluation_precedes_simulation"


def test_acceptance_rejects_outflow_mismatch(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "simulate_dispatch_program",
                "result": _tool_result_payload(360.0),
            },
            {
                "name": "evaluate_dispatch_result",
                "result": _tool_result_payload(360.0),
            },
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "outflow_mismatch"


def test_acceptance_rejects_tool_error_event(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 350.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "simulate_dispatch_program",
                "result": {"error": "unsupported_module_type"},
            },
            {
                "name": "evaluate_dispatch_result",
                "result": _tool_result_payload(350.0),
            },
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_args())
    assert result["success"] is False
    assert str(result["acceptance_failure_reason"]).startswith("tool_error")


def test_static_s01_profile_accepts_valid_fixed_chain(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 700.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "get_reservoir_status",
                "result": {
                    "scenario_id": "S01",
                    "current_level_m": 157.5,
                    "current_inflow_m3s": 400.0,
                    "forecast_inflow_m3s": 400.0,
                    "flood_limit_level_m": 156.5,
                },
            },
            {
                "name": "query_dispatch_rules",
                "result": {
                    "target_level_m": 156.5,
                    "downstream_safe_flow_m3s": 14000.0,
                    "eco_min_flow_m3s": 50.0,
                    "window_hours": 48.0,
                },
            },
            {
                "name": "optimize_release_plan",
                "result": {
                    "avg_release_m3s": 700.0,
                    "min_release_m3s": 700.0,
                    "max_release_m3s": 700.0,
                    "release_values_m3s": [700.0] * 16,
                },
            },
            {
                "name": "simulate_dispatch_program",
                "result": {
                    "declared_outflow": 700.0,
                    "final_level_m": 156.4,
                },
            },
            {
                "name": "evaluate_dispatch_result",
                "result": {
                    "declared_outflow": 700.0,
                    "overall_score": 0.9,
                    "constraint_violations_count": 0,
                },
            },
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_static_s01_profile_args())
    assert result["success"] is True
    assert result["accepted_attempt_index"] == 1
    assert result["tool_call_chain"] == [
        "get_reservoir_status",
        "query_dispatch_rules",
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]


def test_static_s01_profile_rejects_unexpected_chain(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 700.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {"name": "get_reservoir_status", "result": {"current_level_m": 157.5, "forecast_inflow_m3s": 400.0, "flood_limit_level_m": 156.5}},
            {"name": "query_dispatch_rules", "result": {"target_level_m": 156.5, "downstream_safe_flow_m3s": 14000.0, "eco_min_flow_m3s": 50.0, "window_hours": 48.0}},
            {"name": "check_safety_constraints", "result": {"safe": True}},
            {"name": "optimize_release_plan", "result": {"avg_release_m3s": 700.0, "min_release_m3s": 700.0, "max_release_m3s": 700.0, "release_values_m3s": [700.0] * 16}},
            {"name": "simulate_dispatch_program", "result": {"declared_outflow": 700.0, "final_level_m": 156.4}},
            {"name": "evaluate_dispatch_result", "result": {"declared_outflow": 700.0, "overall_score": 0.9, "constraint_violations_count": 0}},
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_static_s01_profile_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "unexpected_tool_chain"


def test_static_s01_profile_rejects_untrustworthy_optimization(monkeypatch) -> None:
    monkeypatch.setattr("pyresops.agents.runner.build_agno_model", lambda *args, **kwargs: object())
    response = types.SimpleNamespace(
        content='{"outflow": 340.0, "reasoning": "ok", "constraint_check": "ok"}',
        tools=[
            {
                "name": "get_reservoir_status",
                "result": {
                    "scenario_id": "S01",
                    "current_level_m": 157.5,
                    "current_inflow_m3s": 400.0,
                    "forecast_inflow_m3s": 400.0,
                    "flood_limit_level_m": 156.5,
                },
            },
            {
                "name": "query_dispatch_rules",
                "result": {
                    "target_level_m": 156.5,
                    "downstream_safe_flow_m3s": 14000.0,
                    "eco_min_flow_m3s": 50.0,
                    "window_hours": 48.0,
                },
            },
            {
                "name": "optimize_release_plan",
                "result": {
                    "avg_release_m3s": 340.0,
                    "min_release_m3s": 340.0,
                    "max_release_m3s": 340.0,
                    "release_values_m3s": [340.0] * 16,
                },
            },
            {
                "name": "simulate_dispatch_program",
                "result": {
                    "declared_outflow": 340.0,
                    "final_level_m": 157.4,
                },
            },
            {
                "name": "evaluate_dispatch_result",
                "result": {
                    "declared_outflow": 340.0,
                    "overall_score": 0.8,
                    "constraint_violations_count": 0,
                },
            },
        ],
    )
    _install_fake_agno_agent(monkeypatch, [response])

    result = ReservoirAgentRunner().run(**_build_static_s01_profile_args())
    assert result["success"] is False
    assert result["acceptance_failure_reason"] == "optimize_result_untrustworthy"
