<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide covers the fastest way to run **PyResOps** for both normal human/developer usage and MCP tool usage.

## Prerequisites

- `Python >= 3.11` (from `pyproject.toml`)
- Recommended local version: `Python 3.14` (from `.python-version`)
- `uv` package manager/runner (used by project commands)
- `git` (to clone the repository)

## Installation steps

1. Clone the repository:

```bash
git clone https://github.com/chooron/res-ops-mcp.git
```

2. Enter the project directory:

```bash
cd res-ops-mcp
```

3. Install dependencies:

```bash
uv sync
```

Alternative (editable install with pip):

```bash
pip install -e .
```

## First run

### Normal human usage (local script)

Run a built-in end-to-end example:

```bash
uv run python examples/case1_flood_dispatch.py
```

This prints simulation, constraint-check, and evaluation output in the terminal.

### MCP usage (tool server)

Start the FastMCP server:

```bash
uv run python -m pyresops.server
```

This starts the `res-ops-mcp` server and registers snapshot/program/simulation/evaluation/rolling-ops tools for MCP clients.

## Common setup issues

1. **`uv: command not found`**
   - Cause: `uv` is not installed or not on PATH.
   - Fix: install `uv`, then re-run `uv sync`.

2. **Startup fails with reservoir YAML error**
   - Symptom: startup raises `Failed to load reservoir configuration: ...`.
   - Cause: `PYRESOPS_RESERVOIR_CONFIG` points to a missing or malformed YAML file.
   - Fix: unset the variable to use fallback config, or point it to a valid YAML file.

3. **Python version incompatibility during install**
   - Cause: running with Python older than `3.11`.
   - Fix: switch to a supported Python version (`>=3.11`; project pin is `3.14`).

## Next steps

- See [DEVELOPMENT.md](DEVELOPMENT.md) for local development workflow and coding standards.
- See [TESTING.md](TESTING.md) for test commands and CI test behavior.
- See [CONFIGURATION.md](CONFIGURATION.md) for reservoir YAML/bootstrap configuration details.
- See [ARCHITECTURE.md](ARCHITECTURE.md) for system structure and data flow.
