<!-- generated-by: gsd-doc-writer -->
# Development

This guide covers local development for **PyResOps** in two modes:

- **Normal human usage** (Python scripts/services)
- **MCP usage** (running the FastMCP server and calling tools)

## Local setup

1. Fork the repository in GitHub (if you plan to contribute upstream).
2. Clone and enter the project:

```bash
git clone https://github.com/chooron/res-ops-mcp.git
cd res-ops-mcp
```

3. Install dependencies:

```bash
uv sync
```

4. (Optional, for full dev tooling) Install the dev dependency group:

```bash
uv sync --group dev
```

5. Configure reservoir bootstrap input (optional). If unset, startup falls back to `configs/default_reservoir.yaml`, then built-in demo values:

```bash
$env:PYRESOPS_RESERVOIR_CONFIG = "E:\path\to\reservoir.yaml"
```

6. Run in your preferred mode:

- **Human usage (examples/scripts):**

```bash
uv run python examples/case1_flood_dispatch.py
```

- **MCP usage (server):**

```bash
uv run python -m pyresops.server
```

## Build commands

This repository does not use JavaScript package scripts. Use the Python/uv commands below.

| Command | Description |
| --- | --- |
| `uv sync` | Install project dependencies from `pyproject.toml`/`uv.lock`. |
| `uv sync --group dev` | Install optional development dependencies (`pytest`, `pytest-asyncio`, `ruff`). |
| `uv run python -m pyresops.server` | Start the FastMCP server (`pyresops/server.py`) for MCP tool calls. |
| `uv run python main.py` | Start the MCP server via the root entry script (`main.py`). |
| `uv run pytest` | Run the full test suite (test paths configured as `tests` in `pyproject.toml`). |
| `uv run pytest tests/ -v` | Run tests with verbose output. |
| `uv run ruff check .` | Run lint checks using Ruff settings in `pyproject.toml`. |

## Code style

- **Ruff** is the linting/style tool, configured in `pyproject.toml` under `[tool.ruff]`.
  - Configured values include `line-length = 100` and `target-version = "py311"`.
  - Run with: `uv run ruff check .`
- **Pytest** configuration is in `pyproject.toml` under `[tool.pytest.ini_options]`.
  - Includes `asyncio_mode = "auto"` and `testpaths = ["tests"]`.
- No ESLint/Prettier/Biome configuration files are present in this repository.

## Branch conventions

- Default branch is `master`.
- No branch naming convention is documented in repository docs/templates.

## PR process

No formal contributing guide or pull request template is currently present, so follow this lightweight process:

1. Create a focused feature/fix branch from `master`.
2. Keep changes scoped and include tests for behavior changes.
3. Run validation before opening a PR:
   - `uv run pytest`
   - `uv run ruff check .`
4. In the PR description, include:
   - problem statement and motivation,
   - summary of changes,
   - verification steps and results,
   - whether changes affect human usage, MCP usage, or both.
5. If your change affects runtime behavior, update related docs (for example `README.md`, `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`).
