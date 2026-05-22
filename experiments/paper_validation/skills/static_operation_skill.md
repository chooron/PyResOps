# Static Reservoir Operation Skill

Static workflow required chain:

prepare_event
-> optimize_release_plan
-> simulate_release_plan
-> evaluate_release_plan
-> final_answer

Rules:

- Call `optimize_release_plan` exactly once.
- For command challenge cases, translate the command into the single `optimize_release_plan` call; do not call `optimize_release_plan` twice to compare alternatives.
- For conservative-release, peak-reduction, ambiguous, or multi-objective commands, use the single `evaluate_release_plan` result to explain the trade-off.
- Call `simulate_release_plan` exactly once.
- Call `evaluate_release_plan` exactly once.
- Do not call optimize again after evaluation.
- Do not skip evaluation.
- The final answer must include `selected_plan_id`, `safety_status`, `hard_constraint_violation`, and `evaluation_reference`.
- The final answer `evaluation_reference` must refer to the returned `evaluate_release_plan` result.
