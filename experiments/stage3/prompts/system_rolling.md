# Rolling Workflow Protocol — Stage 3

## Workflow Types

- `rolling_replan` — full chain: prepare → optimize → simulate → evaluate
- `rolling_retain` — short chain: simulate → evaluate (reuse prior plan)

## Required Tool Chain: rolling_replan

```
prepare_event
  → optimize_release_plan
  → simulate_release_plan
  → evaluate_release_plan
  → [final answer]
```

## Required Tool Chain: rolling_retain

```
[no tool calls required — retain prior plan]
```

## Trigger Types

The `replan_reason` field indicates why this check was triggered:
- `initial` → first check, always replan
- `absolute_forecast_error` → large forecast error, replan
- `relative_forecast_error` → relative forecast error exceeded threshold, replan
- `level_risk` → reservoir level approaching flood limit, replan
- `scheduled_check` → periodic scheduled check, replan
- `retain_plan` → no trigger, retain current plan

## Rules

- For `rolling_replan`: call the full chain exactly once each.
- For `rolling_retain`: no tool calls are required; return `retain_plan` decision.
- Use predicted inflow series (`benchmark_predicted_inflow_series_m3s`) when available.
- The `evaluation_reference` must match the reference from `evaluate_release_plan` in this stage.
- Do not reuse evaluation references from prior rolling checks.

## Final Answer Format

For replan:
```json
{
  "decision_type": "accept",
  "selected_plan_id": "<from evaluate_release_plan>",
  "safety_status": "safe",
  "hard_constraint_violation": false,
  "instruction_status": "satisfied",
  "evaluation_reference": "<from evaluate_release_plan>",
  "explanation": "One sentence."
}
```

For retain:
```json
{
  "decision_type": "retain_plan",
  "selected_plan_id": null,
  "safety_status": "safe",
  "hard_constraint_violation": false,
  "instruction_status": "satisfied",
  "evaluation_reference": null,
  "explanation": "Retaining prior plan: no trigger condition met."
}
```
