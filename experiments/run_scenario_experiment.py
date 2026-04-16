from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "experiments"))

from experiments.dynamic_experiment import (  # noqa: E402
    run_multi_round_dynamic_experiment,
    run_static_baseline,
)
from pyresops.agents import ReservoirAgentRuntime  # noqa: E402


SCENARIO_IDS = ["S01", "S02", "S03", "S04", "S05"]


def run_one_scenario(
    scenario_id: str,
    mode: str,
    model_profile: str | None,
    max_rounds: int | None,
) -> dict:
    result: dict = {
        "scenario_id": scenario_id,
        "mode": mode,
        "model_profile": model_profile or "default",
        "run_time": datetime.now().isoformat(),
    }

    runtime = ReservoirAgentRuntime(model_profile=model_profile)

    if mode in ("static", "both"):
        result["static"] = run_static_baseline(
            scenario_id=scenario_id,
            experiment=runtime,
            save_result=True,
        )

    if mode in ("dynamic", "both"):
        result["dynamic"] = run_multi_round_dynamic_experiment(
            scenario_id=scenario_id,
            max_rounds=max_rounds,
            experiment=runtime,
            save_result=True,
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run static and dynamic experiments per scenario.")
    parser.add_argument(
        "--scenario",
        type=str,
        default="ALL",
        help="Scenario ID: S01-S05 or ALL",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="both",
        choices=["static", "dynamic", "both"],
        help="Which experiment mode to run",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model profile from experiments/config/llm_config.yml",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=0,
        help="Max dynamic stages; use 0 for all stages",
    )
    args = parser.parse_args()

    max_rounds = None if args.rounds <= 0 else args.rounds
    scenario_ids = SCENARIO_IDS if args.scenario.upper() == "ALL" else [args.scenario.upper()]

    invalid = [sid for sid in scenario_ids if sid not in SCENARIO_IDS]
    if invalid:
        raise ValueError(f"Invalid scenario(s): {invalid}; allowed: {SCENARIO_IDS}")

    all_results = []
    for sid in scenario_ids:
        print(f"\nRunning {sid} | mode={args.mode} | model={args.model or 'default'}")
        all_results.append(
            run_one_scenario(
                scenario_id=sid,
                mode=args.mode,
                model_profile=args.model,
                max_rounds=max_rounds,
            )
        )

    out_dir = REPO_ROOT / "experiments" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    scenario_tag = args.scenario.upper()
    out_file = out_dir / f"scenario_runs_{scenario_tag}_{args.mode}_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\nSaved run summary: {out_file}")


if __name__ == "__main__":
    main()
