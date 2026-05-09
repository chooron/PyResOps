# Static Reservoir Operation Skill

Static workflow required chain:

prepare_event
-> optimize_release_plan
-> simulate_release_plan
-> evaluate_release_plan
-> final_answer

Rules:

- Call `optimize_release_plan` exactly once.
- Call `simulate_release_plan` exactly once.
- Call `evaluate_release_plan` exactly once.
- Do not call optimize again after evaluation.
- Do not skip evaluation.
- The final answer must include `selected_plan_id`, `safety_status`, `hard_constraint_violation`, and `evaluation_reference`.
- The final answer `evaluation_reference` must refer to the returned `evaluate_release_plan` result.
