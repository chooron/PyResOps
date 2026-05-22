"""Run or describe real-data Agno workflow contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from experiments.data_adapters import RealEventDataAdapter
from experiments.workflows import (
    DynamicRealDataWorkflow,
    RollingRealDataWorkflow,
    StaticRealDataWorkflow,
)
from experiments.workflows.rolling import RollingThresholds
from pyresops.agents import ReservoirAgentRuntime


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_config(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Missing real-data workflow config: {resolved}")
    with resolved.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a mapping: {resolved}")
    return payload


def build_adapter(cfg: dict[str, Any]) -> RealEventDataAdapter:
    return RealEventDataAdapter(
        data_root="data",
    )


def build_runtime(args) -> ReservoirAgentRuntime | None:
    if args.contract_only:
        return None
    return ReservoirAgentRuntime(
        model_profile=args.model_profile,
        config_path=args.llm_config,
        max_attempts=args.max_attempts,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="experiments/config/real_events.yml")
    parser.add_argument("--llm-config", default="experiments/config/llm_config.yml")
    parser.add_argument("--workflow", choices=["static", "dynamic", "rolling", "all"], default="all")
    parser.add_argument("--model-profile", default=None)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Validate and print workflow contracts without invoking Agno or a model.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    adapter = build_adapter(cfg)
    runtime = build_runtime(args)
    outputs: dict[str, Any] = {}

    if args.workflow in {"static", "all"}:
        static_cfg = cfg.get("static") or {}
        event_id = static_cfg.get("event_id", cfg.get("data", {}).get("default_event", "2024072617"))
        outputs["static"] = StaticRealDataWorkflow(adapter, runtime).run(str(event_id)).to_dict()

    if args.workflow in {"dynamic", "all"}:
        dynamic_cfg = cfg.get("dynamic") or {}
        instructions = {
            int(offset): str(text)
            for offset, text in (dynamic_cfg.get("instruction_offsets") or {}).items()
        }
        target_adjustments = {
            int(offset): float(value)
            for offset, value in (dynamic_cfg.get("target_adjustments_m") or {}).items()
        }
        outputs["dynamic"] = DynamicRealDataWorkflow(
            adapter,
            runtime,
            instructions=instructions or None,
            target_adjustments_m=target_adjustments or None,
            target_level_tolerance=float(dynamic_cfg.get("target_level_tolerance", 0.1)),
        ).run(str(dynamic_cfg.get("event_id", "2024072617"))).to_dict()

    if args.workflow in {"rolling", "all"}:
        rolling_cfg = cfg.get("rolling") or {}
        thresholds = RollingThresholds(
            relative_error_trigger=float(rolling_cfg.get("relative_error_trigger", 0.2)),
            absolute_error_trigger_m3s=float(rolling_cfg.get("absolute_error_trigger_m3s", 150.0)),
            high_level_margin_m=float(rolling_cfg.get("high_level_margin_m", 0.5)),
            min_remaining_horizon_hours=int(rolling_cfg.get("min_remaining_horizon_hours", 9)),
            check_interval_hours=int(rolling_cfg.get("check_interval_hours", 3)),
            scheduled_check_replan=bool(rolling_cfg.get("scheduled_check_replan", False)),
        )
        manual_offsets = {
            int(offset): str(text)
            for offset, text in (rolling_cfg.get("manual_instruction_offsets") or {}).items()
        }
        outputs["rolling"] = RollingRealDataWorkflow(
            adapter,
            runtime,
            thresholds=thresholds,
            manual_instruction_offsets=manual_offsets,
        ).run(rolling_cfg.get("event_path")).to_dict()

    print(json.dumps(outputs, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, RuntimeError, ImportError) as exc:
        diagnostic = {
            "success": False,
            "failure_reason": str(exc),
            "failure_type": type(exc).__name__,
        }
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        sys.exit(1)
