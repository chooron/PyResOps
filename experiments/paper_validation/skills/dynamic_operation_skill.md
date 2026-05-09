# Dynamic Reservoir Operation Skill

Dynamic workflow required protocol:

First evaluate carry-over plan when `carry_over_plan` is present:

simulate_release_plan
-> evaluate_release_plan

Then:

- If carry-over satisfies safety and instruction, return `retain_carry_over`.
- Otherwise call:

optimize_release_plan
-> simulate_release_plan
-> evaluate_release_plan
-> final_answer

Rules:

- Carry-over evaluation is mandatory when `carry_over_plan` exists.
- Replan evaluation is mandatory if replan occurs.
- Do not optimize before evaluating carry-over.
- Do not return final_answer immediately after optimize.
- Instruction can be infeasible; safe rejection is allowed.
- The final answer `evaluation_reference` must refer to `evaluate_release_plan` or the carry-over evaluation result.
