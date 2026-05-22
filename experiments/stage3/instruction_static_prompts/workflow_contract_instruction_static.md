# Instruction-Conditioned Static Workflow Contract

## Hard Rules

- Hard safety constraints have absolute priority over operator commands.
- Do not accept an unsafe plan to satisfy a command. If infeasible, return `reject_infeasible`.
- Do not invent data. Every value in the final payload must come from a PyResOps MCP tool result.
- The `evaluation_reference` field must cite the exact reference ID returned by `evaluate_release_plan`.
- If a tool call fails, report `failure_reason`; do not pretend the workflow succeeded.
- Return strict JSON only in the final answer. No natural language outside the JSON object.
- Call each required tool exactly once.

## Operator Command Compliance

- `specified_release_family` is a hard command. Pass it as `requested_module_type` to
  `optimize_release_plan`. Do not switch families silently.
- `operation_interval_h` is a hard command. The final release series must be block-constant
  at this interval (all values within each block equal).
- Report `command_compliance = (actual_release_family == specified_release_family)`.
- Report `interval_compliance = (release series is block-constant at operation_interval_h)`.

## Acceptance Gate

```
accepted =
  tool_order_valid
  AND eval_ref_valid
  AND schema_valid
  AND NOT hard_violation
  AND NOT downstream_violation
  AND command_compliance
  AND interval_compliance
```

## Required Payload Fields

- `decision_type`, `selected_plan_id`, `safety_status`, `hard_constraint_violation`
- `instruction_status`, `evaluation_reference`, `explanation`
- `specified_release_family`, `actual_release_family`, `command_compliance`
- `operation_interval_h`, `interval_compliance`
- `eval_ref_id`
