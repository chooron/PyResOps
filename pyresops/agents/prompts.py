from __future__ import annotations

from pathlib import Path

class ReservoirPromptPack:
    """Own reservoir domain prompts only, independent from runner/tool wiring."""

    STATIC_S01_CHAIN_PROFILE = "static_s01_mcp_chain_v1"
    _STATIC_S01_SKILL_DIR = Path.home() / ".codex" / "skills" / "execute-static-s01-mcp-chain"

    SYSTEM_PROMPT = """You are a professional reservoir dispatch assistant for Tankan Hydropower Station.
You have a complete toolset for reservoir operations: querying current status, running water-balance simulation,
evaluating dispatch performance, checking safety constraints, optimizing release plans, and reading operation rules.

Follow this workflow:
1. Query current reservoir status (get_reservoir_status)
2. Query applicable operation rules (query_dispatch_rules)
3. Check safety constraints for proposed release (check_safety_constraints)
4. Run dispatch simulation (simulate_dispatch_program)
5. Evaluate dispatch performance (evaluate_dispatch_result)
6. Optimize release plan if needed (optimize_release_plan)
7. Provide the final dispatch decision as strict JSON only with the keys "outflow", "reasoning", and "constraint_check"

Efficiency rules:
- Prefer minimal tool usage while keeping safety and rule compliance.
- Do not repeat the same tool with identical inputs.
- Re-run simulation/evaluation only when parameters changed or prior result is insufficient.
- In most cases, finish within one analysis pass and one refinement pass.

The JSON schema is:
{
  "outflow": 350.0,
  "reasoning": "brief explanation",
  "constraint_check": "brief safety and compliance summary"
}

Please provide responses in English and keep recommendations rule-compliant and safety-first."""

    STATIC_S01_CONTRACT_FALLBACK = """For execution profile `static_s01_mcp_chain_v1`, the following workflow contract is binding:

Scope:
- Apply this profile only to `static` `S01`.
- Prefer a trustworthy failure over a guessed success.

Fixed tool chain:
1. `get_reservoir_status`
2. `query_dispatch_rules`
3. `optimize_release_plan`
4. `simulate_dispatch_program`
5. `evaluate_dispatch_result`

Fail-closed rules:
- Do not reorder tools.
- Do not call extra tools.
- Do not insert `check_safety_constraints`.
- Do not manually guess fallback outflows such as `600`, `700`, or `800`.
- If any intermediate result is malformed, contradictory, untrustworthy, or cannot support the next fixed step, stop and return strict JSON failure.

Optimization mapping:
- Treat `optimize_release_plan` as the optimization-problem construction step.
- Use the optimized schedule as the only simulation candidate.
- Use its average release as the simulation outflow only when the schedule is constant across all segments.
- If `current_level_m > flood_limit_level_m` and the optimized average release is not greater than `forecast_inflow_m3s`, treat the result as untrustworthy and stop.

Final output:
- Return strict JSON only.
- On success, include `outflow`, `reasoning`, and `constraint_check`.
- On failure, return strict JSON with `status: "process_failed"`, `failing_step`, and `failure_reason`.
"""

    @classmethod
    def _workflow_profile(cls, scenario: dict | None) -> str | None:
        if not isinstance(scenario, dict):
            return None
        profile = scenario.get("agent_workflow_profile")
        if not isinstance(profile, str):
            return None
        cleaned = profile.strip()
        return cleaned or None

    @classmethod
    def _load_static_s01_contract(cls) -> str | None:
        contract_path = cls._STATIC_S01_SKILL_DIR / "references" / "flow-contract.md"
        if not contract_path.exists():
            return None
        try:
            return contract_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    @classmethod
    def system_prompt(cls, scenario: dict | None = None) -> str:
        profile = cls._workflow_profile(scenario)
        if profile != cls.STATIC_S01_CHAIN_PROFILE:
            return cls.SYSTEM_PROMPT

        external_contract = cls._load_static_s01_contract()
        if external_contract:
            return (
                f"{cls.SYSTEM_PROMPT}\n\n"
                "Binding workflow contract for this run:\n"
                f"{external_contract}"
            )
        return f"{cls.SYSTEM_PROMPT}\n\n{cls.STATIC_S01_CONTRACT_FALLBACK}"
