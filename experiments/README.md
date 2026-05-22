# PyResOps Experiments

Reservoir operation agent evaluation suite for Tankeng (滩坑) Reservoir, Zhejiang.
Three-stage validation framework: deterministic baseline → workflow replication → LLM+MCP agent evaluation.

---

## Repository Layout

```
experiments/
├── config/                  # YAML configs for all stages and LLM profiles
├── stage1/                  # Deterministic baseline runners and metrics
├── stage2/                  # Workflow abstraction layer runners
├── stage3/                  # LLM+MCP agent runners, prompts, validators
├── workflows/               # Static / Dynamic / Rolling workflow classes
├── validation/              # Shared runner, manifest, results, reporting
├── paper_validation/        # Orchestrator, MCP skill runner, wrongtest runner
├── data_adapters/           # Real event CSV loader and preprocessor
├── figures/                 # Chapter 5 figure generation scripts
├── report/                  # Internal design and status documents
├── legacy/                  # Archived agno-workflow prototype (2026-05-07)
├── results/                 # All experiment outputs (see below)
├── .tmp/                    # Temporary / development scripts (not part of main pipeline)
│
├── run_paper_validation.py          # Main entry point for all paper validation phases
├── run_realdata_workflows.py        # Real-data rolling workflow runner
├── run_stage1_baseline.py           # Stage 1 deterministic baseline
├── run_stage1_instruction_static.py # Stage 1 static instruction experiment
├── run_stage1_dynamic_command_intervention.py
├── run_stage2_workflow.py
├── run_stage2_instruction_static.py
├── run_stage2_dynamic_command_intervention.py
├── run_stage3_llm_mcp.py
├── run_stage3_instruction_static.py
├── run_stage3_instruction_static_multimodel.py
├── run_stage3_dynamic_command_intervention.py
├── run_cross_model_phase_g.py       # Cross-model Phase G runner
├── create_forecast_error_wrongtest.py  # Wrongtest perturbation generator
├── build_wrongtest_report.py        # Wrongtest comparison table and report builder
├── build_chapter5_results.py        # Chapter 5 paper figure/table builder
├── check_paper_validation_gates.py  # Gate checker for all phases
├── smoke_test_model_calls.py        # Quick model connectivity smoke test
└── preprocess_real_events.py        # Preprocess raw event CSVs
```

---

## Dataset

**Reservoir:** 滩坑 (Tankeng), Zhejiang Province
**Reference:** 2025年度水库控制运用计划
**Flood limit level:** 156.5 m (汛期), 162.0 m (非汛期)
**Downstream constraint:** outflow ≤ 3500 m³/s

| Category | Count | Notes |
|----------|-------|-------|
| Total historical flood events | 44 | |
| Excluded (pre-impoundment) | 3 | 2007–2008, reservoir not at operating level |
| **Retained events** | **41** | All in `data/flood_event/` |
| Events with forecast (`withpred`) | 10 | In `data/withpred/`, used for rolling workflow |

**Event classification (41 events):**

| Group | Criteria | Count |
|-------|----------|-------|
| S1 Routine | peak_inflow < 1500 m³/s AND peak_level < 153 m | 8 |
| S2 Moderate | 1500 ≤ peak_inflow < 2500 OR 153 ≤ peak_level < 156.5 m | 16 |
| S3 High-risk | peak_inflow ≥ 2500 OR peak_level ≥ 156.5 m | 12 |
| S4 Extreme | peak_level ≥ 160 m OR volume ≥ 5×10⁸ m³ OR peak_inflow ≥ 4000 m³/s | 5 |

---

## Stage 1 — Deterministic Baseline

**Purpose:** Pure-code reference with no LLM or agent layer. Calls `OptimizationService`,
`SimulationService`, and `EvaluationService` directly. Establishes the oracle for Stage 2
and Stage 3 comparisons.

**Runner:** `run_stage1_baseline.py`

**Coverage:**

| Workflow | Events | Rows | Result |
|----------|--------|------|--------|
| Static | 41 | 41 | 41/41 accepted, 0 hard violations |
| Dynamic | 10 | 48 | 48/48 accepted, 0 hard violations |
| Rolling | 10 | 373 | 373/373 accepted, 0 hard violations |
| **Total** | | **462** | **462/462 accepted** |

**Sub-experiments:**

- **Instruction-Static** (41 events × 6 families × 2 intervals = 492 records): Tests six
  operator-specified release families (constant, linear_ramp, step_down, joint_driven,
  peak_shaving, ecological_base) at 6 h and 12 h intervals. All 492 records accepted.
- **Dynamic Command Intervention** (10 events × 4 command types × 2 checkpoints = 40 oracle
  rows): Tests release_cap_adjustment, target_level_override, emergency_release, and
  scheduled_check commands at T2/T4 checkpoints. All 40 rows accepted, zero hard violations.

**Results:** `experiments/results/stage1/`

---

## Stage 2 — Workflow Replication

**Purpose:** Validates that the workflow abstraction layer
(`prepare → optimize → simulate → evaluate → validate`) reproduces Stage 1 results exactly.
No LLM, no MCP.

**Runner:** `run_stage2_workflow.py`

**Coverage:** Same 462 rows as Stage 1.

**Oracle comparison result:**

| Metric | Value |
|--------|-------|
| Matched rows | 462 / 462 |
| `accepted` mismatches | 0 |
| `max_level` tolerance failures (±0.5 m) | 0 |
| `terminal_deviation` tolerance failures (±0.5 m) | 0 |
| `peak_reduction_rate` tolerance failures (±0.05) | 0 |
| **Oracle contract** | **PASS** |

**Sub-experiments:**

- **Instruction-Static workflow replication:** 492 records, all matched Stage 1 oracle.
- **Dynamic Command Intervention workflow replication:** 48 records, all matched Stage 1 oracle.

**Results:** `experiments/results/stage2/`

---

## Stage 3 — LLM + MCP Agent Evaluation

**Purpose:** Evaluates whether an LLM can correctly execute reservoir operation workflows
through MCP tools, produce valid decision payloads, and pass fail-closed validation against
the Stage 2 oracle.

**MCP tool chain:**
`get_reservoir_status → query_dispatch_rules → optimize_release_plan → simulate_dispatch_program → evaluate_dispatch_result`

**Fail-closed gate:** tool_order AND eval_ref AND schema AND NOT hard_violation AND NOT downstream_violation

**Primary model:** `mimo_v25` (MiMo-v2.5)

**Full evaluation coverage (462 rows):**

| Workflow | Stage 2 Rows | Stage 3 Rows | Accepted |
|----------|-------------|-------------|---------|
| Static | 41 | 41 | 41 (100%) |
| Dynamic | 48 | 48 | 43 (89.6%) |
| Rolling | 373 | 373 | 367 (98.4%) |
| **Total** | **462** | **462** | **451 (97.6%)** |

Hard violations: 0. Downstream violations: 0.

**Rolling workflow detail:**

| Category | Count |
|----------|-------|
| Total rolling checks | 373 |
| LLM-called checks (replan) | 142 |
| Deterministic retain rows | 231 |
| Accepted LLM decisions | 136 / 142 (95.8%) |
| Accepted retain rows | 231 / 231 (100%) |

**Sub-experiments:**

- **Instruction-Static LLM evaluation (41 events):** Tests whether LLM correctly follows
  family and interval instructions via MCP. All 41 accepted.
- **Dynamic Command Intervention LLM evaluation (40 rows):** Tests command handling success,
  feasible execution, and acceptance. All 40 accepted, zero hard violations.
- **Cross-model evaluation (Phase G):** mimo_v25, claude_haiku_4_5, minimax_m2_5_free,
  deepseek_v4_flash, gemini_3_1_flash_lite, qwen3_6_flash tested on representative subsets.

**Results:** `experiments/results/stage3/`, `experiments/results/paper_validation/cross_model_runs/`

---

## Ablation Study

**Purpose:** Isolates the contribution of each system component by comparing three executor
variants on the same oracle subset.

| Variant | Description |
|---------|-------------|
| B2 `mimo_without_tools` | LLM generates plans without MCP tool access |
| B3 `mimo_mcp_no_skill` | LLM uses MCP tools but without skill contract |
| B4 `mimo_mcp_skill` | Full system: LLM + MCP tools + skill contract (primary) |

**Full run results (112 records):**

| Variant | Success Rate | Hard Violations | eval_ref_valid_rate | protocol_adherence |
|---------|-------------|----------------|--------------------|--------------------|
| B2 no-tools | — | 0 | 0.0 | — |
| B3 MCP no-skill | ~95% | 0 | partial | partial |
| B4 MCP+Skill | 95.5% (107/112) | 0 | 1.0 | 1.0 |

B2 produced executable numeric plans but `evaluation_reference_valid_rate = 0.0` — no
tool-grounded evidence. B3 had protocol failures in static and rolling workflows. B4 achieved
full compliance across all metrics.

**L0–L4 ablation** (`l0-l4` runs): Tests five executor levels from pure library (L0) to full
MCP+Skill (L4).

**Results:** `experiments/results/paper_validation/tables/ablation_b2_b3_b4_summary.csv`

---

## Forecast-Error Wrongtest (Supplementary)

**Purpose:** Verifies that the rolling MCPTools-based operation remains safe and auditable
under degraded forecast inputs. Real automatic forecasts in the 10-event rolling experiment
were relatively accurate; this test applies mild perturbations to 5 representative events.

**Not a synthetic flood:** only the `predict` (forecast inflow) column is perturbed.
Observed inflow, outflow, and water level are unchanged. State propagation and evaluation
use observed inflow. Recommended as supplementary material, not a primary result.

**Stage 1 — Perturbation generation** (`create_forecast_error_wrongtest.py`):

| Event | Perturbation | Mean Rel Diff | Peak Shift |
|-------|-------------|--------------|-----------|
| 2012062402 | lag_6h | 0.262 | +6 h |
| 2022062023 | over_peak_mild | 0.018 | 0 h |
| 2013100711 | under_peak_mild | 0.026 | 0 h |
| 2024061623 | lead_6h | 0.252 | −6 h |
| 2024072617 | mixed_mild | 0.179 | +3 h |

**Stage 2 — Deterministic (pyresops_direct):** 51 stages, success_rate=1.0, hard_violations=0.
All 4 trigger types observed: relative_forecast_error, absolute_forecast_error, state_risk,
scheduled_12h_check.

**Stage 3 — LLM+MCP+Skill results (51 stages each model):**

| Model | Success Rate | Hard Violations | MCP Rate | Protocol Rate |
|-------|-------------|----------------|---------|--------------|
| mimo_v25 | 1.0 | 0 | 1.0 | 1.0 |
| claude_haiku_4_5 | 1.0 | 0 | 1.0 | 1.0 |

**Scripts:**

```bash
# Generate perturbed CSVs
uv run python experiments/create_forecast_error_wrongtest.py

# Run Stage 2 (deterministic)
uv run python experiments/run_paper_validation.py \
  --phase forecast-error-wrongtest-stage2 \
  --wrongtest-dir data/wrongtest \
  --output-dir experiments/results/paper_validation

# Run Stage 3 (LLM+MCP)
uv run python experiments/run_paper_validation.py \
  --phase forecast-error-wrongtest-stage3 \
  --model-profile mimo_v25 \
  --wrongtest-dir data/wrongtest \
  --output-dir experiments/results/paper_validation

# Generate comparison report
uv run python experiments/build_wrongtest_report.py --model-label mimo_v25
```

**Results:** `experiments/results/paper_validation/forecast_error_wrongtest/`

---

## Running the Full Pipeline

```bash
# Stage 1 deterministic baseline
uv run python experiments/run_stage1_baseline.py --workflow all

# Stage 2 workflow replication
uv run python experiments/run_stage2_workflow.py

# Stage 3 LLM+MCP (primary model)
uv run python experiments/run_paper_validation.py \
  --phase mcp-skill-full --model-profile mimo_v25

# Ablation
uv run python experiments/run_paper_validation.py \
  --phase component-ablation --model-profile mimo_v25

# Cross-model Phase G
uv run python experiments/run_cross_model_phase_g.py

# Gate checks
uv run python experiments/check_paper_validation_gates.py \
  --latest --include-component-ablation

# Chapter 5 figures and tables
uv run python docs/paper/figures/generate_chapter5_results.py
```

---

## Results Directory Structure

```
experiments/results/
├── stage1/                          # Stage 1 deterministic baseline outputs
│   ├── static/
│   ├── dynamic/
│   ├── rolling/
│   └── STAGE1_SUMMARY.md
├── stage2/                          # Stage 2 workflow replication outputs
│   ├── comparison/
│   └── STAGE2_SUMMARY.md
├── stage3/                          # Stage 3 LLM+MCP outputs
│   ├── static/
│   ├── dynamic/
│   ├── rolling/
│   └── STAGE3_SUMMARY.md
├── paper_validation/                # All paper validation phase outputs
│   ├── tables/                      # Summary tables (ablation, cross-model, etc.)
│   ├── cross_model_runs/            # Phase G cross-model full and smoke runs
│   ├── compact_context_validation/  # Compact context cross-model runs
│   ├── forecast_error_wrongtest/    # Wrongtest pipeline outputs
│   │   ├── stage2_workflow/
│   │   ├── stage3_mimo_mcp/         # mimo_v25 results
│   │   └── stage3_claude_haiku_4_5/
│   └── ...                          # Phase-specific JSONL + summary files
└── paper_ready/                     # Publication-ready tables and figures
```

---

## Tests

```bash
uv run pytest tests/test_experiments/ -v
```

| File | Coverage |
|------|---------|
| `test_stage1_instruction_static.py` | Stage 1 static instruction runner |
| `test_stage1_dynamic_command_intervention.py` | Stage 1 dynamic command runner |
| `test_stage2_workflow.py` | Stage 2 workflow replication |
| `test_stage2_instruction_static.py` | Stage 2 static instruction |
| `test_stage2_dynamic_command_intervention.py` | Stage 2 dynamic command |
| `test_stage3_mcp_tools.py` | MCP tool registration and calls |
| `test_stage3_validator.py` | Fail-closed validator |
| `test_paper_validation.py` | Paper validation orchestrator |
| `test_realdata_workflows.py` | Real-data rolling workflow |
| `test_wrongtest_generation.py` | Wrongtest perturbation generation and gates |

---

## .tmp Directory

`experiments/.tmp/` contains development and exploratory scripts not part of the main pipeline:

- `run_minimal_validation.py` — early-stage minimal validation runner (superseded by `run_paper_validation.py`)

These files are excluded from CI and paper results.
