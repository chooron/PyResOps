"""Stage 3 LLM + MCP tool-use evaluation CLI entry point.

Usage:
    python -m experiments.run_stage3_llm_mcp --workflow all
    python -m experiments.run_stage3_llm_mcp --workflow static --limit 2
    python -m experiments.run_stage3_llm_mcp --workflow dynamic --events 2010062002
    python -m experiments.run_stage3_llm_mcp --workflow static --model-profile deepseek_v4_pro
    python -m experiments.run_stage3_llm_mcp --compare --stage2-dir experiments/results/stage2
    python -m experiments.run_stage3_llm_mcp --dry-run-tools
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from experiments.stage3.comparator import Stage3Comparator
from experiments.stage3.llm_runner import Stage3LlmRunner
from experiments.stage3.mcp_tools import list_dynamic_events, list_rolling_events, list_static_events
from experiments.stage3.reporting import (
    generate_stage3_comparison,
    generate_stage3_outputs,
    generate_stage3_summary,
)


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_static_events(runner: Stage3LlmRunner) -> list[str]:
    return list_static_events(runner.adapter)


def _resolve_dynamic_events(config: dict) -> list[str]:
    return list_dynamic_events(config)


def _resolve_rolling_events(config: dict) -> list[str]:
    return list_rolling_events(config)


def _dry_run_tools(config: dict, verbose: bool) -> None:
    """Validate MCP connection and tool availability without LLM calls."""
    import asyncio

    mcp_cfg_raw = config.get("mcp", {})
    model_profile = config.get("model_profile", "mimo_v25")
    llm_config_path = config.get("llm_config_path")

    print(f"[dry-run] model_profile={model_profile}")
    print(f"[dry-run] MCP transport={mcp_cfg_raw.get('transport')} command={mcp_cfg_raw.get('command')}")

    try:
        from agno.tools.mcp import MCPTools
        from experiments.paper_validation.mcp_skill_runner import MCP_SKILL_AGENT_TOOLS, _mcp_tools_kwargs, McpSkillConnectionConfig

        mcp_cfg = McpSkillConnectionConfig(
            transport=mcp_cfg_raw.get("transport", "stdio"),
            url=mcp_cfg_raw.get("url"),
            command=mcp_cfg_raw.get("command"),
            connect_timeout_seconds=int(mcp_cfg_raw.get("connect_timeout_seconds", 30)),
            call_timeout_seconds=int(mcp_cfg_raw.get("call_timeout_seconds", 120)),
            agent_timeout_seconds=int(mcp_cfg_raw.get("agent_timeout_seconds", 180)),
            refresh_connection=bool(mcp_cfg_raw.get("refresh_connection", True)),
            reservoir_config_path=None,
        )

        async def _check() -> None:
            mcp_tools = MCPTools(
                **_mcp_tools_kwargs(mcp_cfg),
                include_tools=MCP_SKILL_AGENT_TOOLS,
                timeout_seconds=mcp_cfg.call_timeout_seconds,
                refresh_connection=mcp_cfg.refresh_connection,
            )
            await asyncio.wait_for(mcp_tools.connect(), timeout=mcp_cfg.connect_timeout_seconds)
            available = sorted(getattr(mcp_tools, "functions", {}).keys())
            print(f"[dry-run] MCP connected. Available tools: {available}")
            missing = [t for t in MCP_SKILL_AGENT_TOOLS if t not in available]
            if missing:
                print(f"[dry-run] MISSING tools: {missing}", file=sys.stderr)
                sys.exit(1)
            else:
                print("[dry-run] All required tools present. MCP plumbing OK.")
            try:
                await mcp_tools.aclose()
            except Exception:
                pass

        asyncio.run(_check())
    except ImportError as exc:
        print(f"[dry-run] Agno not available: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[dry-run] MCP connection failed: {exc}", file=sys.stderr)
        sys.exit(1)


def run_static(
    runner: Stage3LlmRunner,
    events: list[str],
    verbose: bool,
) -> list[dict]:
    results = []
    for event_id in events:
        if verbose:
            print(f"  [static] {event_id} ...", end=" ", flush=True)
        try:
            row = runner.run_static(event_id)
            results.append(row)
            if verbose:
                status = "ACCEPTED" if row.get("accepted") else f"REJECTED({row.get('failure_reason')})"
                print(status)
        except Exception as exc:
            if verbose:
                print(f"ERROR: {exc}")
            results.append({"event_id": event_id, "accepted": False, "failure_reason": str(exc)})
    return results


def run_dynamic(
    runner: Stage3LlmRunner,
    events: list[str],
    verbose: bool,
) -> list[dict]:
    results = []
    for event_id in events:
        if verbose:
            print(f"  [dynamic] {event_id} ...", flush=True)
        try:
            rows = runner.run_dynamic(event_id)
            results.extend(rows)
            if verbose:
                for row in rows:
                    status = "ACCEPTED" if row.get("accepted") else f"REJECTED({row.get('failure_reason')})"
                    print(f"    {row.get('workflow_stage')}: {status}")
        except Exception as exc:
            if verbose:
                print(f"  ERROR: {exc}")
            results.append({"event_id": event_id, "accepted": False, "failure_reason": str(exc)})
    return results


def run_rolling(
    runner: Stage3LlmRunner,
    events: list[str],
    verbose: bool,
    llm_call_policy: str = "trigger_only",
    log_retain_steps: bool = True,
) -> list[dict]:
    results = []
    for event_id in events:
        if verbose:
            print(f"  [rolling] {event_id} ...", flush=True)
        try:
            rows = runner.run_rolling(
                event_id,
                llm_call_policy=llm_call_policy,
                log_retain_steps=log_retain_steps,
            )
            results.extend(rows)
            if verbose:
                llm_rows = [r for r in rows if r.get("llm_called", True)]
                retain_rows = [r for r in rows if not r.get("llm_called", True)]
                accepted_llm = sum(1 for r in llm_rows if r.get("accepted"))
                print(f"    {len(rows)} checks: {len(llm_rows)} LLM ({accepted_llm} accepted), {len(retain_rows)} retain")
        except Exception as exc:
            if verbose:
                print(f"  ERROR: {exc}")
            results.append({"event_id": event_id, "accepted": False, "failure_reason": str(exc)})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3 LLM + MCP tool-use evaluation")
    parser.add_argument(
        "--workflow",
        choices=["static", "dynamic", "rolling", "all"],
        help="Workflow type to run",
    )
    parser.add_argument("--events", nargs="+", help="Specific event IDs to run")
    parser.add_argument("--limit", type=int, help="Limit number of events per workflow")
    parser.add_argument("--model-profile", help="LLM model profile (overrides config)")
    parser.add_argument("--config", default="experiments/config/stage3_llm_mcp.yml", help="Config file path")
    parser.add_argument("--output", help="Output directory (overrides config)")
    parser.add_argument("--compare", action="store_true", help="Run Stage 2 oracle comparison")
    parser.add_argument("--stage2-dir", help="Stage 2 oracle directory")
    parser.add_argument("--dry-run-tools", action="store_true", help="Validate MCP plumbing without LLM calls")
    parser.add_argument("--rolling-policy", choices=["trigger_only", "dense"], default=None, help="Rolling LLM call policy")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    config = _load_config(args.config)
    model_profile = args.model_profile or config.get("model_profile", "mimo_v25")
    llm_config_path = config.get("llm_config_path")
    output_dir = Path(args.output or config.get("output", {}).get("base_dir", "experiments/results/stage3"))
    data_root = config.get("data", {}).get("root", "data")
    traces_dir = str(output_dir)
    rolling_cfg = config.get("rolling", {})
    rolling_policy = args.rolling_policy or rolling_cfg.get("llm_call_policy", "trigger_only")
    log_retain_steps = rolling_cfg.get("log_retain_steps", True)

    if args.dry_run_tools:
        _dry_run_tools(config, verbose=args.verbose)
        return

    static_metrics: list[dict] = []
    dynamic_metrics: list[dict] = []
    rolling_metrics: list[dict] = []

    if args.workflow:
        runner = Stage3LlmRunner(
            model_profile=model_profile,
            config_path=llm_config_path,
            paper_config={"mcp": config.get("mcp", {})},
            data_root=data_root,
            traces_dir=traces_dir,
        )

        try:
            if args.workflow in ("static", "all"):
                events = args.events or _resolve_static_events(runner)
                if args.limit:
                    events = events[: args.limit]
                print(f"Running static workflow on {len(events)} events...")
                static_metrics = run_static(runner, events, args.verbose)
                print(f"  Done: {len(static_metrics)} rows, {sum(1 for r in static_metrics if r.get('accepted'))} accepted")

            if args.workflow in ("dynamic", "all"):
                events = args.events or _resolve_dynamic_events(config)
                if args.limit:
                    events = events[: args.limit]
                print(f"Running dynamic workflow on {len(events)} events...")
                dynamic_metrics = run_dynamic(runner, events, args.verbose)
                print(f"  Done: {len(dynamic_metrics)} rows, {sum(1 for r in dynamic_metrics if r.get('accepted'))} accepted")

            if args.workflow in ("rolling", "all"):
                events = args.events or _resolve_rolling_events(config)
                if args.limit:
                    events = events[: args.limit]
                print(f"Running rolling workflow on {len(events)} events...")
                rolling_metrics = run_rolling(runner, events, args.verbose, rolling_policy, log_retain_steps)
                llm_rows = sum(1 for r in rolling_metrics if r.get("llm_called", True))
                accepted = sum(1 for r in rolling_metrics if r.get("accepted"))
                print(f"  Done: {len(rolling_metrics)} rows ({llm_rows} LLM-called), {accepted} accepted")
        finally:
            runner.close()

        generate_stage3_outputs(static_metrics, dynamic_metrics, rolling_metrics, output_dir)
        print(f"Results saved to {output_dir}")

    comparison: dict | None = None
    if args.compare or (args.workflow and (static_metrics or dynamic_metrics or rolling_metrics)):
        stage2_dir = args.stage2_dir or config.get("stage2_oracle_dir", "experiments/results/stage2")
        comp = Stage3Comparator()
        comp.load_stage2(stage2_dir)
        if static_metrics or dynamic_metrics or rolling_metrics:
            comp.load_stage3_from_metrics(static_metrics, dynamic_metrics, rolling_metrics)
        else:
            comp.load_stage3(output_dir)
        comparison = comp.compare()
        generate_stage3_comparison(comparison, output_dir)
        passes = comparison.get("passes_oracle", False)
        print(f"Oracle comparison: {'PASS' if passes else 'FAIL'} | matched={comparison.get('matched_rows')} missing={comparison.get('missing_in_s3')} accepted={comparison.get('s3_accepted')}/{comparison.get('s3_total')}")

    generate_stage3_summary(
        static_metrics,
        dynamic_metrics,
        rolling_metrics,
        comparison,
        output_dir,
        model_profile=model_profile,
    )
    print(f"Summary written to {output_dir / 'STAGE3_SUMMARY.md'}")


if __name__ == "__main__":
    main()
