# Stage 3 Workflow Contract

## Hard Rules (apply to all workflows)

- Hard safety constraints have absolute priority over operator commands.
- Do not accept an unsafe plan to satisfy a command. If infeasible, return `reject_infeasible`.
- Do not invent data. Every value in the final payload must come from a PyResOps MCP tool result.
- Do not hand-write simulated or evaluated results. Use tool outputs only.
- The `evaluation_reference` field must cite the exact reference ID returned by `evaluate_release_plan`.
- If a tool call fails, report `failure_reason`; do not pretend the workflow succeeded.
- Return strict JSON only in the final answer. No natural language outside the JSON object.
- Call each required tool exactly once unless the workflow explicitly allows retain.

## Required Payload Fields

Every final answer must include:
- `decision_type` — one of: `accept`, `reject_infeasible`, `retain_plan`
- `selected_plan_id` — the plan ID from `evaluate_release_plan`
- `safety_status` — `safe` or `hard_constraint_violation`
- `hard_constraint_violation` — boolean
- `instruction_status` — one of: `satisfied`, `partially_satisfied`, `infeasible`, `in_progress`
- `evaluation_reference` — the reference ID from `evaluate_release_plan`
- `explanation` — brief reasoning (one sentence)

## Evidence Binding

The `evaluation_reference` must be a reference ID that was actually returned by
`evaluate_release_plan` in this session. Do not reuse references from prior stages.
Do not fabricate reference IDs.

## Fail-Closed Validation

Your output will be validated against these gates:
1. Tool order matches the required chain for this workflow type
2. `evaluation_reference` is present and matches an available reference
3. Payload schema is valid (all required fields present and correctly typed)
4. `hard_constraint_violation` is false (or correctly set to true with `reject_infeasible`)
5. No downstream routing violation
