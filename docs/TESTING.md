<!-- generated-by: gsd-doc-writer -->
# Testing

This project uses a Python/pytest test stack and supports two testing paths:

- **Normal human usage** (run tests locally from terminal)
- **MCP usage validation** (integration tests for MCP-facing workflows and tool orchestration)

## Test framework and setup

- **Primary framework:** `pytest` (locked to `9.0.2` in `uv.lock`)
- **Async support:** `pytest-asyncio` (locked to `1.3.0` in `uv.lock`)
- **Configuration source:** `pyproject.toml` (`[tool.pytest.ini_options]`)
  - `asyncio_mode = "auto"`
  - `testpaths = ["tests"]`

Setup before running tests:

```bash
uv sync
```

Then run tests via `uv run` (recommended by repository docs):

```bash
uv run pytest tests/ -v
```

## Running tests

### Full suite (human/local)

```bash
uv run pytest tests/ -v
```

Runs all tests under `tests/` (core engine, services, domain models, storage, constraints, rules, modules, and integration).

### Subset by area

```bash
uv run pytest tests/test_core -v
uv run pytest tests/test_services -v
uv run pytest tests/test_storage -v
```

### Single file

```bash
uv run pytest tests/test_core/test_engine.py -v
```

### MCP-oriented tests

Use integration tests to validate MCP-facing workflows and tool-chain behavior:

```bash
uv run pytest tests/test_integration/test_mcp_tools.py -v
```

This verifies service-level end-to-end behavior used by MCP tool paths (program creation, simulation, evaluation, explanation).

### Watch mode

No dedicated watch-mode script or watcher configuration is defined in this repository.

## Writing new tests

### File naming and placement

- Place tests under `tests/`.
- Current convention is `test_*.py` files, grouped by domain area (for example `tests/test_core/`, `tests/test_services/`, `tests/test_integration/`).
- Use descriptive test function names beginning with `test_`.

### Shared test helpers/fixtures

- Shared fixtures are defined in `tests/conftest.py` (for example `sample_reservoir_spec`, `sample_initial_state`, `sample_forecast`).
- Reuse these fixtures for consistent scenario setup across unit and integration tests.

### MCP test guidance

For MCP-related contributions, add or update tests in `tests/test_integration/` (especially alongside `test_mcp_tools.py`) to cover:

- tool-call workflow correctness,
- result shape consistency,
- end-to-end behavior through services that back MCP tools.

## Coverage requirements

No coverage threshold is configured in repository test config.

| Type | Threshold |
| --- | --- |
| lines | Not configured |
| branches | Not configured |
| functions | Not configured |
| statements | Not configured |

## CI integration

No GitHub Actions workflow file was detected under `.github/workflows/` for automated test execution.

- **Workflow:** Not configured
- **Trigger:** Not configured
- **Test command:** Not configured

If CI is added later, mirror local commands (for example `uv sync` + `uv run pytest tests/ -v`) to keep local and CI behavior aligned.
