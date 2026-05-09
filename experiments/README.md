# Real-Data Agno Workflow Experiments

Phase 1 is a workflow-contract gate, not a batch-result gate. The only target is to make three real-data Agno workflows explicit, executable, and fail-first:

- static dispatch: known complete observed flood process, one tool-verified plan.
- dynamic dispatch: observed state advances by the real CSV, with 3h/6h/9h operator updates.
- rolling dispatch: `predict` plans, observed `inflow` advances state, and forecast error or instructions trigger re-planning.

Data is restricted to `data/flood_event/*.csv` and `data/2024072617_with_pred.csv`. Synthetic flood generation, mocked flood processes, and fake runners are not part of this phase.

## Contracts

The formal workflow code lives in:

- `experiments/data_adapters/real_events.py`
- `experiments/workflows/static.py`
- `experiments/workflows/dynamic.py`
- `experiments/workflows/rolling.py`

The Agno runtime boundary is a package API under `pyresops.agents`.

Static S01 keeps the strict chain:

```text
get_reservoir_status -> query_dispatch_rules -> optimize_release_plan -> simulate_dispatch_program -> evaluate_dispatch_result
```

No model-side guessed release is accepted as a fallback.

## Run

Describe and validate contracts without invoking Agno:

```bash
uv run python experiments/run_realdata_workflows.py --contract-only --workflow all
```

Run with a real model configuration:

```bash
uv run python experiments/run_realdata_workflows.py --workflow static --model-profile deepseek
```

If Agno is missing or the selected profile cannot resolve an API key, the run fails immediately with a diagnostic.

## Archive

The previous experiment draft was archived under:

```text
experiments/legacy/20260507_agnoworkflow_archive/
```
