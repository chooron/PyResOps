# Stage 3: LLM + MCP Tool-Use Evaluation

Stage 3 evaluates whether an LLM can correctly execute reservoir operation workflows
through MCP tools, produce valid decision payloads, and pass fail-closed validation.

## What Stage 3 Tests

Stage 3 does **not** test optimizer quality — Stage 1 and Stage 2 already prove the
optimization kernel. Stage 3 tests LLM tool-use reliability:

- Correct tool ordering (prepare → optimize → simulate → evaluate)
- Evidence binding (evaluation_reference cites a real tool result)
- Schema compliance (ReservoirDecisionPayload fields present and typed correctly)
- Safety adherence (hard_constraint_violation correctly reported)
- Downstream routing (no Hecheng limit violation)

## Fail-Closed Gate

```
accepted = tool_order_valid
         AND eval_ref_valid
         AND schema_valid
         AND NOT hard_violation
         AND NOT downstream_violation
```

All five gates must pass. Any single failure rejects the result.

## Workflow Types

| Workflow | Tool Chain | Trigger |
|----------|-----------|---------|
| `static` | prepare → optimize → simulate → evaluate | once per event |
| `dynamic_replan` | prepare → optimize → simulate → evaluate | T0 or deviation |
| `dynamic_retain` | simulate → evaluate | plan still feasible |
| `rolling_replan` | prepare → optimize → simulate → evaluate | forecast error / level risk |
| `rolling_retain` | (none) | no trigger |

## Running Stage 3

```bash
# Validate MCP plumbing without LLM calls
python -m experiments.run_stage3_llm_mcp --dry-run-tools

# Run static workflow (all 41 events)
python -m experiments.run_stage3_llm_mcp --workflow static

# Run with event limit
python -m experiments.run_stage3_llm_mcp --workflow static --limit 2

# Run specific events
python -m experiments.run_stage3_llm_mcp --workflow dynamic --events 2010062002

# Run all workflows
python -m experiments.run_stage3_llm_mcp --workflow all

# Use a different model profile
python -m experiments.run_stage3_llm_mcp --workflow static --model-profile deepseek_v4_pro

# Compare against Stage 2 oracle
python -m experiments.run_stage3_llm_mcp --compare --stage2-dir experiments/results/stage2
```

## Output Structure

```
experiments/results/stage3/
  static/
    results.csv
    traces/static_traces.jsonl
  dynamic/
    results.csv
    validation_log.csv
    traces/dynamic_replan_traces.jsonl
    traces/dynamic_retain_traces.jsonl
  rolling/
    results.csv
    validation_log.csv
    traces/rolling_replan_traces.jsonl
    traces/rolling_retain_traces.jsonl
  comparison/
    stage3_vs_stage2_comparison.json
    workflow_summary.csv
    failure_taxonomy.csv
  summary/
    stage3_metrics.json
  STAGE3_SUMMARY.md
```

## Result Schema

Each row includes all Stage 2 metric fields plus:

| Field | Description |
|-------|-------------|
| `accepted` | Fail-closed composite gate |
| `tool_order_valid` | Tool chain matches required sequence |
| `eval_ref_valid` | evaluation_reference cites a real tool result |
| `schema_valid` | ReservoirDecisionPayload schema passes |
| `hard_violation` | hard_constraint_violation flag |
| `downstream_violation` | Hecheng routing limit exceeded |
| `failure_reason` | First failing gate name |
| `model_profile` | LLM model profile used |
| `session_id` | Unique session identifier |
| `wrong_tool_order` | Tool chain order error |
| `missing_required_tool` | Required tool not called |
| `stale_eval_ref` | eval_ref not in available references |
| `missing_eval_ref` | No eval_ref provided |
| `llm_output_parse_error` | JSON parse failure |
| `tool_call_error` | MCP tool call failure |

## Configuration

See `experiments/config/stage3_llm_mcp.yml` for model profile, MCP connection
settings, event lists, and oracle tolerances.

## Tests

```bash
pytest tests/test_experiments/test_stage3_mcp_tools.py
pytest tests/test_experiments/test_stage3_validator.py
```
