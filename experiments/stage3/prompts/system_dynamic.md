# Dynamic Workflow Protocol — Stage 3

## Workflow Types

- `dynamic_replan` — full chain: prepare → optimize → simulate → evaluate
- `dynamic_retain` — short chain: simulate → evaluate (reuse prior plan)

## Required Tool Chain: dynamic_replan

```
prepare_event
  → optimize_release_plan
  → simulate_release_plan
  → evaluate_release_plan
  → [final answer]
```

## Required Tool Chain: dynamic_retain

```
simulate_release_plan
  → evaluate_release_plan
  → [final answer]
```

## Retain vs Replan Decision

The `replan_reason` field in the scenario payload tells you which path to take:
- `initial` or `infeasible_or_deviation` → use `dynamic_replan` chain
- `plan_still_feasible` or `prior_violation` → use `dynamic_retain` chain

## Rules

- At T0 (initial checkpoint), always replan.
- For retain stages, do not call `prepare_event` or `optimize_release_plan`.
- For replan stages, call the full chain exactly once each.
- The `evaluation_reference` must match the reference from `evaluate_release_plan` in this stage.
- Do not reuse evaluation references from prior checkpoints.

## Final Answer Format

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
