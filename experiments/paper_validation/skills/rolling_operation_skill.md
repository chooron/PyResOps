# Rolling Reservoir Operation Skill

Rolling workflow protocol:

- Read trigger reason.
- Check forecast error and current safety status.
- Decide `whether_replan`.
- If no replan, explain retain reason.
- If replan:

optimize_release_plan
-> simulate_release_plan
-> evaluate_release_plan
-> final_answer

Required trigger fields:

- `trigger_time`
- `forecast_error_type`
- `trigger_reason`
- `relative_forecast_error`
- `absolute_forecast_error`
- `whether_replan`

Rules:

- Every rolling final answer must include the trigger fields in the explanation or payload-adjacent trace.
- The final answer `evaluation_reference` must refer to a PyResOps MCP evaluation result when a replan is selected.
