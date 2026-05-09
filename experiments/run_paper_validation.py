"""Run phase-based paper validation for PyResOps."""

from __future__ import annotations

import argparse
import json
import sys

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
    args = parser.parse_args()

    result = run_paper_validation_phase(
        phase=args.phase,
        model_profile=args.model_profile,
        llm_config=args.llm_config,
        limit_events=args.limit_events,
        include_rolling_stress=args.include_rolling_stress,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
