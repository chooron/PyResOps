from __future__ import annotations

from pyresops.agents import ReservoirAgentRuntime, ScenarioPayload, ScenarioRunResult


def test_runtime_facade_composes_components() -> None:
    class FakeLoader:
        @staticmethod
        def load(profile=None, config_path=None):
            return {"model_id": "m", "temperature": 0.0, "provider": "openai_like", "api_key": "k"}

    class FakePrompt:
        @staticmethod
        def system_prompt():
            return "prompt"

    class FakeFactory:
        @staticmethod
        def make_tools(spec, runtime_scenario=None):
            return ["t"]

    class FakeRunner:
        @staticmethod
        def run(**kwargs):
            assert kwargs["tools"] == ["t"]
            assert kwargs["system_prompt"] == "prompt"
            return {
                "scenario_id": kwargs["scenario"]["id"],
                "method": "agno_mcp_agent",
                "model": kwargs["model_id"],
                "outflow": 300.0,
                "reasoning": "ok",
                "constraint_check": "ok",
                "parse_warning": None,
                "parsed_from": "json",
                "llm_temperature": 0.0,
                "llm_seed": None,
                "final_decision_text": "{}",
                "tool_call_count": 1,
                "tool_call_chain": ["get_reservoir_status"],
                "tool_calls_detail": [{"call_order": 1, "tool_name": "get_reservoir_status"}],
                "llm_execution_trace": {"attempts": kwargs["max_attempts"], "tool_events": []},
                "accepted_attempt_index": 1,
                "acceptance_failure_reason": None,
                "accepted_evidence_pair": None,
                "total_time_seconds": 0.1,
                "success": True,
            }

    runtime = ReservoirAgentRuntime(
        model_profile="test",
        config_path="ignored.yml",
        config_loader=FakeLoader(),
        prompt_pack=FakePrompt(),
        tool_bundle_factory=FakeFactory(),
        runner=FakeRunner(),
    )

    payload = {
        "id": "S01",
        "name": "n",
        "description": "d",
        "current_level": 150.0,
        "initial_storage": 20.0,
        "initial_inflow": 100.0,
        "inflow": 100.0,
        "target_level": 149.0,
        "season": "dry",
        "flood_risk": "none",
        "duration_hours": 24,
        "time_step_hours": 1,
    }
    result = runtime.run_scenario(payload)
    assert result["scenario_id"] == "S01"
    assert result["success"] is True


def test_payload_and_result_typed_contracts_expose_expected_fields() -> None:
    payload_required = set(ScenarioPayload.__required_keys__)  # type: ignore[attr-defined]
    result_required = set(ScenarioRunResult.__required_keys__)  # type: ignore[attr-defined]

    assert {"id", "inflow", "duration_hours", "time_step_hours"}.issubset(payload_required)
    assert {
        "scenario_id",
        "outflow",
        "success",
        "tool_call_count",
        "llm_execution_trace",
        "accepted_attempt_index",
    }.issubset(result_required)
