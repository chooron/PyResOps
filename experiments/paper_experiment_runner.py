"""Unified paper experiment entrypoint (A/B/C)."""

from __future__ import annotations

import json


def run_all(model_profile: str | None = None) -> dict:
    """Unified experiment entrypoint for paper experiments: A(static), B(dynamic), C(deviation)."""
    from experiments.automated_experiment import run_all_deviation_experiments
    from experiments.dynamic_experiment import run_dynamic_experiments
    from experiments.static_experiment import run_static_experiments

    def _to_record(item: object) -> dict:
        if isinstance(item, dict):
            return item
        if hasattr(item, "to_dict"):
            return item.to_dict()
        raise TypeError(f"Unsupported deviation result type: {type(item)!r}")

    def _ensure_no_error_results(stage: str, results: list[dict]) -> None:
        errors = [result for result in results if "error" in result]
        if errors:
            raise RuntimeError(f"{stage} returned {len(errors)} error result(s); failing fast.")

    print("=" * 60)
    print("PyResOps Paper Experiments - Unified Entry")
    print("=" * 60)

    print("\n[1/3] Running static experiment tier (A)...")
    static_results = run_static_experiments(model_profile=model_profile)
    _ensure_no_error_results("static_experiments", static_results)

    print("\n[2/3] Running dynamic experiment tier (B)...")
    dynamic_results = run_dynamic_experiments(model_profile=model_profile)
    _ensure_no_error_results("dynamic_experiments", dynamic_results)

    print("\n[3/3] Running deviation rolling-control tier (C)...")
    deviation_raw = run_all_deviation_experiments(model_profile=model_profile)
    deviation_results = [_to_record(item) for item in deviation_raw]
    _ensure_no_error_results("deviation_experiments", deviation_results)

    report = summarize_all_results(
        static_results=static_results,
        dynamic_results=dynamic_results,
        deviation_results=deviation_results,
    )
    _save_report(report)
    return report


def summarize_all_results(
    static_results: list[dict],
    dynamic_results: list[dict],
    deviation_results: list[dict] | None = None,
) -> dict:
    """Aggregate static, dynamic, and deviation experiment outputs into report payload."""

    def avg(lst):
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    valid_static = [r for r in static_results if "error" not in r]
    static_summary = {
        "total": len(valid_static),
        "llm_avg_overall": avg([r["llm_scores"]["overall"] for r in valid_static]),
        "human_avg_overall": avg([r["human_scores"]["overall"] for r in valid_static]),
        "total_llm_violations": sum(r["llm_constraint_violations"] for r in valid_static),
        "process_complete_rate": avg([1.0 if r["process_complete"] else 0.0 for r in valid_static]),
    }

    valid_dynamic = [r for r in dynamic_results if "error" not in r]
    dynamic_summary = {
        "total": len(valid_dynamic),
        "overall_pass_rate": avg([r.get("overall_pass_rate", 0.0) for r in valid_dynamic]),
        "per_scenario_pass_rates": {
            r["scenario_id"]: r.get("overall_pass_rate", 0.0) for r in valid_dynamic
        },
        "hard_task_partial_credits": {
            r["scenario_id"]: r.get("hard_task_partial_credits", {})
            for r in valid_dynamic
            if r.get("hard_task_partial_credits")
        },
    }

    deviation_summary = summarize_deviation_results(deviation_results or [])

    return {
        "experiment_time": __import__("datetime").datetime.now().isoformat(),
        "static_summary": static_summary,
        "dynamic_summary": dynamic_summary,
        "deviation_summary": deviation_summary,
        "static_results": static_results,
        "dynamic_results": dynamic_results,
        "deviation_results": deviation_results or [],
    }


def summarize_deviation_results(deviation_results: list[dict]) -> dict:
    if not deviation_results:
        return {
            "total": 0,
            "by_controller": {},
        }

    grouped: dict[str, list[dict]] = {}
    for item in deviation_results:
        controller = str(item.get("controller_type", "unknown"))
        grouped.setdefault(controller, []).append(item)

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    summary = {}
    for controller, items in grouped.items():
        summary[controller] = {
            "count": len(items),
            "mean_overall_score": avg([float(i.get("overall_score", 0.0)) for i in items]),
            "worst_overall_score": round(min(float(i.get("overall_score", 0.0)) for i in items), 4),
            "mean_total_constraint_violations": avg(
                [float(i.get("total_constraint_violations", 0.0)) for i in items]
            ),
            "mean_effective_correction_rate": avg(
                [float(i.get("effective_correction_rate", 0.0)) for i in items]
            ),
        }

    return {
        "total": len(deviation_results),
        "by_controller": summary,
    }


def _save_report(report: dict) -> None:
    """Save combined report to experiments/results/."""
    from pathlib import Path

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"full_report_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n综合报告已保存: {out_path}")


if __name__ == "__main__":
    run_all()
