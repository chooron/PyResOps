<!-- generated-by: gsd-doc-writer -->

# Configuration

This document covers runtime configuration for **PyResOps** for both direct human operation (local runs/scripts) and MCP-based operation (LLM/client calls through FastMCP tools).

## Environment variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `PYRESOPS_RESERVOIR_CONFIG` | Optional | Unset (auto fallback behavior applies) | Path to a YAML file loaded at server startup (`pyresops.server:load_reservoir_spec_from_env_or_demo`). If set, it is used as the primary reservoir bootstrap source. |

## Config file format

PyResOps uses a YAML bootstrap file for reservoir specification and optional initial snapshot data.

- Default file location: `configs/default_reservoir.yaml`
- Loader: `pyresops.config.load_reservoir_bootstrap_from_yaml`
- Accepted top-level styles:
  - Structured payload under `reservoir` with grouped keys
  - Flat payload directly compatible with `ReservoirSpec`

Minimal working example:

```yaml
reservoir:
  id: demo_reservoir
  name: Demo Reservoir

  characteristic_levels:
    dead_level: 150.0
    normal_level: 175.0
    flood_limit_level: 145.0
    design_flood_level: 180.0
    check_flood_level: 185.0

  capacities:
    total_capacity: 39.3
    flood_capacity: 22.15

  curves:
    level_storage:
      levels: [135.0, 145.0, 155.0, 165.0, 175.0, 185.0]
      storages: [0.0, 10.0, 20.0, 30.0, 39.3, 51.6]
    discharge_capacity:
      levels: [135.0, 145.0, 155.0, 165.0, 175.0, 185.0]
      max_discharges: [0.0, 5000.0, 10000.0, 15000.0, 20000.0, 30000.0]

snapshot:
  level: 165.0
  inflow: 8000.0
```

## Required vs optional settings

### Required

- No environment variable is strictly required for startup.

### Optional (with behavior implications)

- `PYRESOPS_RESERVOIR_CONFIG` is optional. If provided, it must point to a valid YAML file. Startup fails if:
  - the file does not exist (`Reservoir YAML not found`), or
  - the YAML is malformed / missing required reservoir fields (`Invalid reservoir spec payload` or related `ReservoirYamlError`).

For MCP usage, these startup failures prevent the FastMCP server from initializing its tools.

## Defaults

When `PYRESOPS_RESERVOIR_CONFIG` is not set, startup behavior is:

1. Try `configs/default_reservoir.yaml` if it exists.
2. If not present, fall back to built-in demo `ReservoirSpec` values in `pyresops/server.py:create_demo_reservoir_spec`.

YAML snapshot defaults (`pyresops/config/reservoir_yaml.py`):

- `snapshot.inflow`: defaults to `0.0` if omitted.
- `snapshot.level`: defaults to `spec.normal_level` when omitted.
- `snapshot.outflow`: defaults to `inflow` when omitted.
- `snapshot.timestamp`: defaults to current time when omitted.
- `snapshot.metadata`: defaults to `{}` and is extended with `reservoir_id` and `source: yaml_bootstrap`.

## Per-environment overrides

No `.env.development`, `.env.production`, or `.env.test` files are defined in this repository.

Use environment-specific values by setting `PYRESOPS_RESERVOIR_CONFIG` differently per environment:

- **Development (human usage):** point to a local YAML scenario file for iterative testing.
- **Development/Integration (MCP usage):** point the MCP server process to a deterministic YAML for stable tool responses.
- **Production:** provide the production YAML path through your process manager/container environment.

Example (PowerShell):

```bash
$env:PYRESOPS_RESERVOIR_CONFIG = "E:\path\to\reservoir.yaml"
uv run python -m pyresops.server
```

<!-- VERIFY: Production YAML storage location and secret management approach are deployment-specific and not defined in this repository. -->
