# Dynamic Command-Intervention Workflow Contract

## Hard Rules

- Hard safety constraints have absolute priority over operator commands.
- Do not accept an unsafe plan to satisfy a command. If infeasible, return `reject_infeasible`.
- Do not invent data. Every value in the final payload must come from a PyResOps MCP tool result.
- The `evaluation_reference` field must cite the exact reference ID returned by `evaluate_release_plan`.
- If a tool call fails, report `failure_reason`; do not pretend the workflow succeeded.
- Return strict JSON only in the final answer. No natural language outside the JSON object.
- Call each required tool exactly once.

## Command Handling

- The `operator_instruction` field contains the command type and parameters.
- Apply the command constraints when calling `optimize_release_plan`.
- Correct infeasibility rejection counts as `command_handling_success=true`.
- Do NOT ignore the command or proceed without applying it.

## Acceptance Gate

```
accepted =
  tool_order_valid
  AND eval_ref_valid
  AND schema_valid
  AND NOT hard_violation
  AND NOT downstream_violation
  AND command_handling_success
```

## Required Payload Fields

- `decision_type`, `selected_plan_id`, `safety_status`, `hard_constraint_violation`
- `instruction_status`, `evaluation_reference`, `explanation`
- `command_type`, `command_text`, `command_parameters`
- `command_feasibility`, `command_outcome`
- `command_handling_success`, `feasible_execution_success`
- `infeasibility_reason`, `checkpoint_id`, `eval_ref_id`
