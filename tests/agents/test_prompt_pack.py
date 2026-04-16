from __future__ import annotations

from pyresops.agents import ReservoirPromptPack


def test_prompt_pack_exposes_system_prompt() -> None:
    prompt = ReservoirPromptPack.system_prompt()
    assert "professional reservoir dispatch assistant" in prompt
    assert "strict JSON only" in prompt


def test_prompt_pack_contains_required_workflow_steps() -> None:
    prompt = ReservoirPromptPack.system_prompt()
    assert "get_reservoir_status" in prompt
    assert "simulate_dispatch_program" in prompt
    assert "evaluate_dispatch_result" in prompt
    assert "check_safety_constraints" in prompt
