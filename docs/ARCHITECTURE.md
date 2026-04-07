<!-- generated-by: gsd-doc-writer -->
# Architecture

## System overview

PyResOps is a layered Python reservoir-operations engine that turns reservoir state snapshots, forecast inflow series, and dispatch programs into simulation and evaluation outputs, with two entry styles: direct in-process service usage (Python API) and tool-based usage through a FastMCP server (`pyresops/server.py`) for agent or external system integration.

## Component diagram

```text
Human / Python caller                    MCP client / agent
         |                                       |
         v                                       v
  pyresops.services.* <----------------> pyresops.tools.*
         |                                       |
         +------------------+--------------------+
                            v
                    pyresops.core.*
            (SimulationEngine, DecisionOrchestrator,
             ConstraintValidator, HydraulicsCalculator)
                            |
          +-----------------+------------------+
          v                                    v
  pyresops.modules.*                    pyresops.domain.*
          |                                    |
          +-----------------+------------------+
                            v
         pyresops.rules.* / constraints.* / metrics.*
                            |
                            v
                   pyresops.storage.Repository
                       (SQLite persistence)
```

## Data flow

### A) Normal human/developer usage (Python API)

1. Create core services (`SnapshotService`, `ProgramService`, `SimulationService`, `EvaluationService`, optional `RollingOpsService`).
2. Seed or update current reservoir snapshot via `SnapshotService`.
3. Create a `DispatchProgram` via `ProgramService` (module sequence + optional switch conditions).
4. Run simulation with `SimulationService.run_simulation(...)`, which delegates to `SimulationEngine`.
5. During each time step, the engine resolves active module, computes baseline outflow, optionally applies policy-driven rule/constraint orchestration, applies hydraulics bounds, then advances state by water balance.
6. Evaluate results with `EvaluationService.evaluate(...)` (built-in flood/supply/power/ecology metrics + optional extensions).
7. Persist artifacts (program, simulation, evaluation, traces, finalized records) via `storage.Repository` when needed.

### B) MCP usage (tool-based orchestration)

1. Start `python -m pyresops.server`, which builds `FastMCP("res-ops-mcp")`, initializes services, and registers tools.
2. MCP tools in `pyresops/tools/*.py` translate tool payloads into domain objects (e.g., `ForecastBundle`, `PolicyBundle`).
3. Tool handlers call the same service layer used by direct Python callers (no separate execution engine).
4. Results are returned as JSON-like dictionaries, including summaries such as levels, scores, and decision-trace counts.
5. Rolling workflow tools (`optimize_flexible_release_plan`, `reassess_plan`, `replace_working_plan`, `finalize_plan`, `get_working_state`) coordinate candidate-plan lifecycle and repository persistence.

## Key abstractions

- `SimulationEngine` (`pyresops/core/engine.py`): time-step simulation loop, module switching, hydraulics checks, and state progression.
- `DecisionOrchestrator` (`pyresops/core/orchestrator.py`): rule hit evaluation, action resolution, step/global constraint enforcement, decision tracing.
- `ConstraintValidator` (`pyresops/core/validator.py`): validates simulation outputs against registered constraints.
- `ProgramService` (`pyresops/services/program.py`): creates/validates dispatch programs and manages module registry.
- `SimulationService` (`pyresops/services/simulation.py`): service wrapper around engine execution, including policy/orchestrator path.
- `EvaluationService` (`pyresops/services/evaluation.py`): computes built-in and custom metrics and aggregate scores.
- `RollingOpsService` (`pyresops/services/rolling_ops.py`): rolling-operations workflow (candidate generation, reassessment, replacement, finalization).
- `Repository` (`pyresops/storage/repository.py`): SQLite persistence for programs, results, events, finalized plans, decision traces.
- `PolicyBundle` / `ExecutionContext` (`pyresops/domain/policy.py`): policy payload and runtime context consumed by rules/constraints.
- `DispatchRule` / `RuleAction` / `RuleSet` (`pyresops/domain/rule.py`): rule model and action semantics.
- `ConstraintEvaluator` + built-ins (`pyresops/constraints/base.py`, `pyresops/constraints/builtin/*.py`): pluggable constraint SPI.
- `RuleEvaluator` + expression evaluator (`pyresops/rules/base.py`, `pyresops/rules/expression.py`): pluggable rule SPI.
- `MetricEvaluator` + built-ins (`pyresops/metrics/base.py`, `pyresops/metrics/builtin.py`): pluggable metric SPI.

## Directory structure rationale

The repository is organized as a layered architecture: stable domain models at the center, reusable core logic around them, service orchestration above core, and delivery interfaces (MCP tools/server) plus persistence/adapters at the boundary.

```text
pyresops/
├── config/        # Reservoir YAML bootstrap loading and normalization
├── constraints/   # Constraint SPI, registry/factory, built-in constraints
├── core/          # Simulation/evaluation primitives (engine, orchestrator, validator, hydraulics)
├── domain/        # Pydantic domain models (reservoir, program, forecast, policy, result, rule)
├── metrics/       # Metric SPI, registry, built-in scoring metrics
├── modules/       # Executable operation modules (constant, inflow, storage, flexible, etc.)
├── plugins/       # Generic plugin base and registry
├── rules/         # Rule SPI, expression evaluator, actions, loader/registry/factory
├── services/      # Use-case orchestration layer consumed by API/tools
├── storage/       # SQLite repository and persistence contracts
├── tools/         # FastMCP tool handlers mapping requests to services
└── server.py      # FastMCP application bootstrap and tool registration entrypoint

tests/
├── test_config/        # YAML/config bootstrap behavior
├── test_constraints/   # Constraint registration and validation behavior
├── test_core/          # Core engine/orchestrator/validator behavior
├── test_domain/        # Domain-model edge cases
├── test_integration/   # End-to-end workflows including MCP tools
├── test_modules/       # Operation module behavior and validation
├── test_plugins/       # Plugin registry behavior
├── test_rules/         # Rule engine and expression matching behavior
├── test_services/      # Service-layer workflows and policy integration
└── test_storage/       # Repository persistence behavior
```

## Usage orientation by interface

- Prefer **service-layer usage** (`pyresops.services`) for local scripts, notebooks, and embedded application logic.
- Prefer **MCP tool usage** (`pyresops.server` + `pyresops.tools`) when integrating with LLM agents or external orchestrators that speak the MCP tool protocol.
- Both paths converge on the same domain/core/services pipeline, so simulation and evaluation semantics remain consistent across interfaces.
