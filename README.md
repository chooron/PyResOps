# pyresops

`pyresops` is a modular reservoir operation and dispatch package for single-reservoir scheduling scenarios.
It provides:

- simulation and evaluation of dispatch programs
- rule/constraint/metric extension points
- execution plugins for inflow generation, step-side process models, and post-simulation impact models
- a FastMCP server surface for tool-driven orchestration

The package is now in a good state for local installation and internal use as a reusable Python package.
It is strongest as an engineering framework and scenario execution kernel. It is not yet a production-grade forecasting system by itself.

## What Is Included

- `pyresops.core`
  - simulation engine
  - hydraulics checks
  - decision orchestration
- `pyresops.services`
  - program creation
  - simulation
  - evaluation
  - rolling operations workflow
- `pyresops.rules`
  - built-in and custom rule evaluators
- `pyresops.constraints`
  - built-in and custom constraints
- `pyresops.metrics`
  - built-in and custom evaluation metrics
- `pyresops.plugins`
  - execution plugin framework
  - built-in plugins:
    - `simple_rainfall_runoff`
    - `gate_release_calculator`
    - `muskingum_routing`
- `pyresops.server`
  - packaged FastMCP server

## Installation

### Editable install for local development

```bash
pip install -e .
```

Or with `uv`:

```bash
uv pip install -e .
```

### Build a local wheel

```bash
uv build
```

This produces artifacts under `dist/`.

### Install from the built wheel

```bash
pip install dist/pyresops-0.1.0-py3-none-any.whl
```

## Local CLI Usage

After installation, the package provides a console command:

```bash
pyresops-server
```

This launches the bundled FastMCP server.

You can still run it as a module:

```bash
python -m pyresops.server
```

## Python Usage

### Minimal simulation example

```python
from datetime import datetime

from pyresops.domain import TimeHorizon
from pyresops.services import ProgramService, SimulationService, SnapshotService
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import (
    ReservoirSpec,
    ReservoirState,
    LevelStorageCurve,
    DischargeCapacity,
)

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

program = program_service.create_program(
    name="demo_program",
    time_horizon=TimeHorizon(
        start=datetime(2024, 7, 1, 0, 0, 0),
        end=datetime(2024, 7, 1, 3, 0, 0),
        time_step=3600,
    ),
    module_configs=[
        {"module_type": "constant_release", "parameters": {"target_release": 800.0}},
    ],
)

initial_state = ReservoirState(
    timestamp=datetime(2024, 7, 1, 0, 0, 0),
    level=165.0,
    storage=30.0,
    inflow=800.0,
    outflow=800.0,
)

forecast = ForecastBundle(
    forecast_time=datetime(2024, 7, 1, 0, 0, 0),
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

## Execution Plugins

The formal execution plugin surface is under `pyresops.plugins`.

Main classes:

- `ExecutionPluginBase`
- `InputPluginBase`
- `StepPluginBase`
- `PostPluginBase`
- `ReportPluginBase`
- `ExecutionPluginRegistry`
- `PluginManager`
- `PluginStage`

Official bundle keys are:

- `input`
- `step`
- `post`
- `report`

### Example plugin skeleton

```python
from pyresops.plugins import (
    InputPluginBase,
    InputPluginContext,
    PluginExecutionResult,
    PluginStage,
)


class MyInputPlugin(InputPluginBase):
    plugin_name = "my_input"
    stage = PluginStage.INFLOW_GENERATION
    summary = "My inflow generator"

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        return dict(config)

    def validate_inputs(self, context: InputPluginContext) -> None:
        return None

    def execute(self, context: InputPluginContext, config) -> PluginExecutionResult:
        return PluginExecutionResult(payload={"generated_series": {...}})
```

## Provider Layer

`pyresops` also includes a provider-based materialization layer under `pyresops.providers`.

This layer is for loading and building typed inputs at runtime instead of manually constructing
every domain object in code.

Built-in targets include:

- `reservoir_bootstrap`
- `forecast_bundle`
- `dispatch_program`
- `scenario_input_bundle`

Built-in providers include:

- `reservoir_bootstrap_yaml`
- `forecast_yaml`
- `forecast_csv`
- `dispatch_program_yaml`
- `scenario_input_bundle_yaml`

Main classes:

- `DataRequest`
- `ProviderRegistry`
- `ProviderManager`
- `ScenarioInputBundle`

### Minimal provider example

```python
from pyresops.providers import (
    DataRequest,
    ProviderManager,
    ProviderRegistry,
    register_builtin_providers,
)

registry = ProviderRegistry()
register_builtin_providers(registry)
manager = ProviderManager(registry)

bootstrap = manager.ensure(
    DataRequest(
        target_type="reservoir_bootstrap",
        source_hint="yaml",
        locator="configs/default_reservoir.yaml",
    )
)
```

### Scenario bundle manifest example

```yaml
reservoir:
  source: yaml
  path: reservoir.yaml
snapshot: bootstrap_default
forecast:
  source: yaml
  path: forecast.yaml
program:
  source: yaml
  path: program.yaml
plugin_bundle:
  input:
    name: simple_rainfall_runoff
    config:
      runoff_coefficient: 0.6
      lag_steps: 1
```

Load it in one call:

```python
bundle = manager.ensure(
    DataRequest(
        target_type="scenario_input_bundle",
        source_hint="yaml",
        locator="scenario.yaml",
    )
)
```

## MCP Surface

The packaged FastMCP server exposes tools including:

- snapshot and program tools
- simulation and evaluation tools
- rolling operations tools
- plugin discovery tools:
  - `list_plugins`
  - `describe_plugin`
  - `resolve_plugins_for_task`
  - `preview_plugin`

## Configuration and Materialization

Reservoir bootstrap YAML is supported through:

- `pyresops.providers.load_reservoir_bootstrap_from_yaml`

The server loads configuration in this order:

1. `PYRESOPS_RESERVOIR_CONFIG`
2. `configs/default_reservoir.yaml`
3. bundled demo fallback

Example:

```bash
set PYRESOPS_RESERVOIR_CONFIG=E:\path\to\reservoir.yaml
pyresops-server
```

Execution plugin bundle config is now exposed from `pyresops.plugins`:

- `PluginSelectionConfig`
- `PluginBundleConfig`
- `ExecutionConfig`

## Testing

Run the main regression suite with:

```bash
uv run pytest tests -q
```

Lint:

```bash
uv run ruff check pyresops tests
```

## Current Maturity

`pyresops` is sufficiently complete for:

- local package installation
- internal scenario execution
- plugin/rule-based dispatch experiments
- MCP-driven tool workflows

It is not yet sufficient to claim:

- production-grade forecast quality
- site-calibrated hydrologic realism by default
- comprehensive operational coverage for every reservoir context

Those depend on project-side configuration, data quality, and custom plugins.

## License

MIT
