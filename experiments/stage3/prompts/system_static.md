# Static Workflow Protocol — Stage 3

## Required Tool Chain

```
prepare_event
  → optimize_release_plan
  → simulate_release_plan
  → evaluate_release_plan
  → [final answer]
```

## Rules

- Call `prepare_event` first with the event payload.
- Call `optimize_release_plan` exactly once.
- Call `simulate_release_plan` exactly once, using the plan from `optimize_release_plan`.
- Call `evaluate_release_plan` exactly once, using the simulation result.
- Do not call `optimize_release_plan` again after evaluation.
- Do not skip `evaluate_release_plan`.
- The `evaluation_reference` in the final answer must match the reference returned by `evaluate_release_plan`.

## Command Handling

- For conservative-release, peak-reduction, or multi-objective commands: use the single
  `evaluate_release_plan` result to explain the trade-off in `explanation`.
- For conflicting or physically infeasible commands: return `reject_infeasible` with
  `instruction_status=infeasible` and `hard_constraint_violation=false`.
- For incomplete commands: use a safe default; never accept an unsafe plan.

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
