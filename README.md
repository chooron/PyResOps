# PyResOps

**English** | [中文](README-zh.md)

PyResOps is a Python framework for single-reservoir operation scheduling. It supports
dispatch-program modelling, simulation, optimization, evaluation, plugin execution, and
tool-driven LLM/MCP validation workflows.

The central design rule is simple: an LLM must not invent reservoir decisions as free text.
Operational decisions have to become executable dispatch programs, pass structured schema
validation, run through simulation and evaluation, and leave traceable evidence. If a required
tool is missing, the tool order is wrong, the output cannot be trusted, or a hard constraint is
violated, the workflow fails closed instead of treating natural-language text as a valid result.

## What This Repository Contains

- `pyresops`: the reusable reservoir-operation core, including domain models, simulation,
  optimization, evaluation, rules, constraints, plugins, persistence, FastMCP tools, and Agno
  agent integration.
- `experiments`: research and paper-validation workflows built on real flood-event CSV data,
  including static, dynamic, and rolling operation scenarios.
- `tests`: unit and integration tests for the core, services, plugins, modules, constraints,
  providers, and experiment workflows.
- `docs`: architecture notes, examples, and paper-oriented documentation.

The repository is intended for engineering research and experiment reproducibility. It is not a
drop-in production hydrological forecasting system and does not replace site-specific reservoir
calibration, operating authority, or formal safety review.

## Main Capabilities

- Single-reservoir simulation based on water balance and discharge-capacity curves.
- Executable dispatch programs instead of plain-text release suggestions.
- Six supported release-module families aligned with the paper taxonomy.
- Rule, constraint, metric, provider, and execution-plugin extension points.
- Rolling operation state management with candidate, working, and finalized plans.
- FastMCP server exposing reservoir, program, simulation, evaluation, optimization, plugin, and
  rolling-operation tools.
- Agno runtime for constrained tool-use agents with JSON payload validation and tool-trace checks.
- Real-data validation workflows for static, dynamic, and rolling operation experiments.
- Paper-validation pipelines for ablation, command-challenge, MCP-skill, gate-checking, and table
  export experiments.

## Design Principles

### Tool-first decisions

Every operational decision should be executable, simulatable, and evaluable. A valid decision is a
`DispatchProgram` plus supporting metadata and evidence, not only a textual recommendation.

### Explicit boundaries

Core engineering logic lives in `pyresops`. Research protocols, scenario expansion, paper phases,
and result export live in `experiments`. This keeps the core reusable while allowing the research
layer to evolve.

### Structured data contracts

Reservoir states, forecasts, dispatch programs, policy bundles, evaluation results, compiled
dispatch contracts, workflow stages, and MCP payloads are represented with typed models or explicit
schemas. Invalid or unparsable model output is treated as failure.

### Hard constraints before instructions

Safety constraints are evaluated separately from operator-instruction progress. A target may remain
`in_progress`, but hard safety violations, invalid tool chains, or untrusted tool results cause
failure.

### Real data with visible quality labels

Experiment workflows use real flood-event CSV files. Data quality is labelled explicitly, for
example `strict_clean`, `repaired_executable`, or `diagnostic_only`, rather than hidden behind
preprocessing.

## Repository Layout

```text
pyresops/
  domain/        Reservoir, forecast, program, module, policy, result, rule, constraint,
                 objective, and dispatch-contract domain objects.
  core/          Simulation engine, hydraulics, orchestration, validation, action resolution,
                 scenario time contracts, and family optimization.
  modules/       Supported release-module families.
  services/      Snapshot, program, simulation, optimization, evaluation, explanation,
                 dispatch-contract compiler, and rolling-operation services.
  constraints/   Constraint SPI, registry, loader, factory, and built-in constraints.
  rules/         Rule SPI, expression evaluation, registry, and action normalization.
  metrics/       Metric SPI and built-in evaluation metrics.
  plugins/       Execution-plugin framework and built-in input, step, and post plugins.
  providers/     YAML/CSV materialization for reservoirs, forecasts, programs, and scenarios.
  tools/         FastMCP tool registration modules.
  agents/        Agno model config, prompts, runtime, runner, and tool bundles.
  storage/       SQLite repository for programs, results, snapshots, events, finalized plans,
                 and decision traces.
  server.py      FastMCP server assembly.
  cli.py         `pyresops-server` command entry point.

experiments/
  config/              Reservoir, model, scenario, and validation YAML files.
  data_adapters/       Real flood-event loading and preprocessing.
  workflows/           Static, dynamic, and rolling workflow contracts.
  validation/          Scenario expansion, execution, JSONL records, CSV/Markdown summaries.
  paper_validation/    Paper-phase runners, MCP-skill runners, gates, command challenges,
                       data freeze, failure taxonomy, and table export.
  stage1/ stage2/ stage3/
                       Staged experiment implementations.
  run_*.py             Experiment entry-point scripts.
```

## Installation

PyResOps requires Python 3.11 or newer.

Install locally in editable mode:

```bash
pip install -e .
```

Or with `uv`:

```bash
uv pip install -e .
```

Install development dependencies:

```bash
uv sync --group dev
```

Build a wheel:

```bash
uv build
```

## Start the MCP Server

After installation:

```bash
pyresops-server
```

Or:

```bash
python -m pyresops.server
```

Use a specific reservoir configuration:

```powershell
$env:PYRESOPS_RESERVOIR_CONFIG="E:\PyCode\PyResOps\experiments\config\default_reservoir.yaml"
pyresops-server
```

## Minimal Python Example

```python
from datetime import datetime

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import TimeHorizon
from pyresops.domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
    ReservoirState,
)
from pyresops.services import ProgramService, SimulationService

spec = ReservoirSpec(
    id="demo",
    name="Demo Reservoir",
    dead_level=150.0,
    normal_level=175.0,
    flood_limit_level=145.0,
    design_flood_level=180.0,
    check_flood_level=185.0,
    total_capacity=39.3,
    flood_capacity=22.15,
    level_storage_curve=LevelStorageCurve(
        levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
        storages=[0.0, 10.0, 20.0, 30.0, 39.3, 51.6],
    ),
    discharge_capacity=DischargeCapacity(
        levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
        max_discharges=[0.0, 5000.0, 10000.0, 15000.0, 20000.0, 30000.0],
    ),
)

program_service = ProgramService()
simulation_service = SimulationService(spec, program_service.get_module_registry())

start = datetime(2024, 7, 1, 0, 0, 0)
program = program_service.create_program(
    name="demo_program",
    time_horizon=TimeHorizon(start=start, end=start.replace(hour=3), time_step=3600),
    module_configs=[
        {"module_type": "constant_release", "parameters": {"target_release": 800.0}},
    ],
)

initial_state = ReservoirState(
    timestamp=start,
    level=165.0,
    storage=30.0,
    inflow=800.0,
    outflow=800.0,
)

forecast = ForecastBundle(
    forecast_time=start,
    series=[
        ForecastSeries(
            variable="inflow",
            timestamps=[
                datetime(2024, 7, 1, 0, 0, 0),
                datetime(2024, 7, 1, 1, 0, 0),
                datetime(2024, 7, 1, 2, 0, 0),
                datetime(2024, 7, 1, 3, 0, 0),
            ],
            values=[800.0, 900.0, 850.0, 780.0],
            unit="m3/s",
        )
    ],
)

result = simulation_service.run_simulation(program, initial_state, forecast)
print(result.max_level, result.avg_outflow)
```

## Experiment Commands

Run real-data workflow contract checks without calling an Agno model:

```bash
uv run python experiments/run_realdata_workflows.py --contract-only --workflow all
```

Run a real-data workflow with a model profile:

```bash
uv run python experiments/run_realdata_workflows.py --workflow static --model-profile deepseek
```

Run paper-validation phases:

```bash
uv run python experiments/run_paper_validation.py --phase data-freeze
uv run python experiments/run_paper_validation.py --phase mcp-skill-smoke --model-profile deepseek_v4_pro --limit-events 1
uv run python experiments/run_paper_validation.py --phase component-ablation --model-profile deepseek_v4_pro
uv run python experiments/run_paper_validation.py --phase command-challenge --model-profile deepseek_v4_pro
```

Check paper-validation gates:

```bash
uv run python experiments/check_paper_validation_gates.py --latest
```

Model calls require provider configuration and API keys through local config or environment
variables, for example `DEEPSEEK_API_KEY`. Do not commit local provider secrets.

## Data Policy

The repository keeps only a small representative sample dataset under version control. Bulk real
event data, derived data, logs, JSONL traces, generated figures, and local provider credentials are
ignored by `.gitignore`.

## Tests and Lint

Run the full test suite:

```bash
uv run pytest tests -q
```

Run focused tests:

```bash
uv run pytest tests/test_experiments/test_paper_validation.py -q
uv run pytest tests/test_services -q
uv run pytest tests/test_modules -q
```

Run lint:

```bash
uv run ruff check pyresops experiments tests
```

## Current Maturity and Boundaries

PyResOps is suitable for:

- local package development;
- deterministic single-reservoir dispatch simulation;
- rule, constraint, metric, and plugin experiments;
- parameter optimization over supported release-module families;
- static, dynamic, and rolling real-data workflow validation;
- MCP-driven agent tool-flow validation;
- paper ablation, command-challenge, and gate-checking experiments.

PyResOps should not be presented as:

- a production hydrological forecasting system;
- a fully calibrated hydrodynamic model for arbitrary reservoirs;
- a replacement for reservoir-operation authority;
- proof that an LLM decision is safe without tool-based validation.

## License

MIT
