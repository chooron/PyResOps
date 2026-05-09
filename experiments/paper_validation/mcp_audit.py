"""MCP schema audit for paper validation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pyresops.server import create_server


CORE_MCP_TOOLS = [
    "prepare_event",
    "optimize_release_plan",
    "simulate_release_plan",
    "evaluate_release_plan",
    "run_static_workflow",
    "run_dynamic_stage",
    "run_rolling_stage",
    "validate_decision_payload",
    "check_hard_constraints",
]


def run_mcp_schema_audit(*, output_root: str | Path = "experiments/results/mcp_schema_audit") -> dict[str, Any]:
    tools = asyncio.run(_list_tools())
    tool_rows = []
    for tool in tools:
        row = {
            "name": getattr(tool, "name", None),
            "description_present": bool(getattr(tool, "description", None)),
            "input_schema_present": bool(getattr(tool, "parameters", None)),
            "output_schema_present": bool(getattr(tool, "output_schema", None)),
            "required_fields_present": bool((getattr(tool, "parameters", {}) or {}).get("required", [])),
            "structured_result_expected": True,
        }
        tool_rows.append(row)
    summary = {
        "tool_count": len(tools),
        "tools": tool_rows,
        "core_tools_present": {
            name: any(row["name"] == name for row in tool_rows) for name in CORE_MCP_TOOLS
        },
    }
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "mcp_schema_audit.json"
    md_path = root / "mcp_schema_audit.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_audit_markdown(summary), encoding="utf-8")
    return {
        "json_path": json_path.as_posix(),
        "markdown_path": md_path.as_posix(),
        "summary": summary,
    }


async def _list_tools():
    server = create_server()
    return await server.list_tools()


def _audit_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# MCP Schema Audit",
        "",
        f"- Tool count: {summary['tool_count']}",
        f"- Core tools present: {summary['core_tools_present']}",
        "",
        "## Tools",
        "",
    ]
    for row in summary["tools"]:
        lines.append(
            f"- {row['name']}: description={row['description_present']}, "
            f"inputSchema={row['input_schema_present']}, "
            f"outputSchema={row['output_schema_present']}, "
            f"requiredFields={row['required_fields_present']}"
        )
    lines.append("")
    return "\n".join(lines)
