"""Run phase-based paper validation for PyResOps."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from experiments.paper_validation.orchestrator import run_paper_validation_phase


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--model-profile", default=None)
    parser.add_argument("--llm-config", default="experiments/config/llm_config.yml")
    parser.add_argument("--limit-events", type=int, default=None)
    parser.add_argument("--include-rolling-stress", action="store_true")
    parser.add_argument("--source", default=None)
    parser.add_argument("--source-run-id", default=None)
    parser.add_argument("--source-dir", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--wrongtest-dir", default=None)
    args = parser.parse_args()

    result = run_paper_validation_phase(
        phase=args.phase,
        model_profile=args.model_profile,
        llm_config=args.llm_config,
        limit_events=args.limit_events,
        include_rolling_stress=args.include_rolling_stress,
        source=args.source,
        source_run_id=args.source_run_id,
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        max_workers=args.max_workers,
        wrongtest_dir=args.wrongtest_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
