"""Run minimal real-data validation scenario sets."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from experiments.data_adapters import RealEventDataAdapter
from experiments.validation.manifest import build_event_manifest, write_manifest_csv
from experiments.validation.reporting import export_summary_report
from experiments.validation.results import JsonlResultLogger
from experiments.validation.runner import build_run_paths, run_case
from experiments.validation.scenarios import (
    data_quality_blockers,
    load_scenario_set,
    selected_dynamic_events,
    selected_static_events,
    selected_stress_or_safety_events,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-set", default="minimal_validation")
    parser.add_argument("--workflow", choices=["static", "dynamic", "rolling", "all"], default="all")
    parser.add_argument("--method", default="tools_only")
    parser.add_argument("--llm-config", default="experiments/config/llm_config.yml")
    parser.add_argument("--model-profile", default=None)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    run_id = f"{args.scenario_set}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    cfg, cases = load_scenario_set(
        args.scenario_set,
        workflow=args.workflow,
        method=args.method,
    )
    output_dir = args.output_dir or ((cfg.get("output") or {}).get("dir") or "experiments/results/minimal_validation")
    paths = build_run_paths(output_dir, run_id)
    adapter = _build_adapter(cfg)

    manifest = build_event_manifest(
        adapter,
        selected_static=selected_static_events(cfg),
        selected_dynamic=selected_dynamic_events(cfg),
        data_quality_blockers=data_quality_blockers(cfg, "static"),
        stress_or_safety_events=selected_stress_or_safety_events(cfg),
    )
    write_manifest_csv(manifest, paths.manifest_path)

    logger = JsonlResultLogger(paths.jsonl_path)
    records: list[dict[str, Any]] = []
    for case in cases:
        records.extend(
            run_case(
                scenario_set=args.scenario_set,
                case=case,
                cfg=cfg,
                adapter=adapter,
                logger=logger,
                run_id=run_id,
                llm_config=args.llm_config,
                model_profile=args.model_profile,
                max_attempts=args.max_attempts,
            )
        )

    report = export_summary_report(
        paths.jsonl_path,
        markdown_path=paths.markdown_path,
        csv_path=paths.csv_path,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "scenario_set": args.scenario_set,
                "case_count": len(cases),
                "stage_record_count": len(records),
                "paths": {
                    "jsonl": paths.jsonl_path.as_posix(),
                    "summary_csv": paths.csv_path.as_posix(),
                    "summary_markdown": paths.markdown_path.as_posix(),
                    "manifest_csv": paths.manifest_path.as_posix(),
                },
                "summary": report["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _build_adapter(cfg: dict[str, Any]) -> RealEventDataAdapter:
    data = cfg.get("data") or {}
    return RealEventDataAdapter(
        data_root=data.get("root", "data"),
    )


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
