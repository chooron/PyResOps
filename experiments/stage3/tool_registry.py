"""Stage 3 tool registry: canonical tool chains and required tools per workflow."""

from __future__ import annotations

from experiments.paper_validation.mcp_skill_runner import CORE_MCP_SKILL_TOOLS, MCP_SKILL_AGENT_TOOLS

STATIC_TOOL_CHAIN = [
    "prepare_event",
    "optimize_release_plan",
    "simulate_release_plan",
    "evaluate_release_plan",
]

DYNAMIC_REPLAN_CHAIN = [
    "prepare_event",
    "optimize_release_plan",
    "simulate_release_plan",
    "evaluate_release_plan",
]

DYNAMIC_RETAIN_CHAIN = [
    "simulate_release_plan",
    "evaluate_release_plan",
]

ROLLING_REPLAN_CHAIN = [
    "prepare_event",
    "optimize_release_plan",
    "simulate_release_plan",
    "evaluate_release_plan",
]

ROLLING_RETAIN_CHAIN: list[str] = []

REQUIRED_TOOLS: list[str] = list(CORE_MCP_SKILL_TOOLS)
AGENT_TOOLS: list[str] = list(MCP_SKILL_AGENT_TOOLS)

WORKFLOW_CHAINS: dict[str, list[str]] = {
    "static": STATIC_TOOL_CHAIN,
    "dynamic_replan": DYNAMIC_REPLAN_CHAIN,
    "dynamic_retain": DYNAMIC_RETAIN_CHAIN,
    "rolling_replan": ROLLING_REPLAN_CHAIN,
    "rolling_retain": ROLLING_RETAIN_CHAIN,
}
