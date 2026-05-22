## 5. Results

This section reports the validation results of PyResOps on Tankeng Reservoir flood-event records. The experiments are organized around three operational decision layers: static release-level planning, dynamic command intervention, and rolling forecast-triggered operation, plus an ablation setting for tools and workflow skills. Stage 1 establishes deterministic direct-service references, Stage 2 verifies workflow-level replication, and Stage 3 evaluates LLM+MCP execution under fail-closed validation. The results focus on feasibility, auditability, tool-use reliability, and hydrological safety checks rather than comparison with historical operation.

### 5.1 Scenario construction and deterministic oracle

The source archive contains 44 flood events. Three events were excluded before validation because their water-level states represent pre-impoundment or initial-filling conditions rather than normal reservoir operation. The retained set contains 41 events, grouped only for stratified reporting into S1 routine, S2 moderate, S3 high-risk, and S4 extreme cases. The verified stratified coverage is 8 S1 events, 16 S2 events, 12 S3 events, and 5 S4 events. These groups are used to check scenario coverage and risk diversity, not to support frequency analysis.

The main deterministic oracle contains 462 records: 41 static records, 48 dynamic retain/replan records, and 373 rolling checks. Stage 2 reproduced Stage 1 on 462/462 records, with no missing rows, no extra rows, and no metric tolerance failures. Oracle metric comparison: PASS. The workflow-level oracle is therefore used as the reference for Stage 3 fail-closed validation. Table 5.0 records the workflow pseudo-code used to structure the results, and Table 5.1 summarizes the scenario design.

The fail-closed acceptance rule used for Stage 3 is:

```text
A = tool_order_valid AND eval_ref_valid AND schema_valid
    AND NOT hard_violation AND NOT downstream_violation
```

For instruction-conditioned static planning, the accepted record must also satisfy command and operation-interval compliance:

```text
A_static = A AND command_compliance AND interval_compliance
```

For dynamic command intervention, command handling success counts either a feasible command executed through a valid plan or an infeasible/unsafe command rejected in structured form:

```text
command_handling_success =
    feasible command executed with a valid plan
    OR infeasible/unsafe command returned as structured rejection
```

For rolling operation, the LLM-call reduction is reported as:

```text
LLM-call reduction = deterministic_retain_rows / total_rolling_checks
```

**Table 5.0. Formula-based tool-execution pseudo-code for the three operational workflows.**

| Workflow | Indexed execution set | Tool execution pseudo-code | Decision formula | Fail-closed acceptance / recorded output |
| --- | --- | --- | --- | --- |
| Static instruction-conditioned release-level planning | For event \(e \in E_{41}\), release family \(f \in F_6\), operation interval \(\Delta \in \{6h,12h\}\). | 1. \(s_0 \leftarrow\) `get_reservoir_status(e, t_0)`.<br>2. \(\mathcal{R}, \mathcal{C} \leftarrow\) `query_dispatch_rules(e, s_0)`.<br>3. Build command constraints \(u=(f,\Delta)\) and target set \(\Theta_e\).<br>4. \(p_{e,f,\Delta} \leftarrow\) `optimize_release_plan(s_0, \hat{q}_{0:T}, \mathcal{C}, u, \Theta_e)`.<br>5. \(\tau_{e,f,\Delta} \leftarrow\) `simulate_dispatch_program(p_{e,f,\Delta}, q_{0:T}, s_0)`.<br>6. \(m_{e,f,\Delta} \leftarrow\) `evaluate_dispatch_result(\tau_{e,f,\Delta}, \mathcal{C})`.<br>7. Validate tool order, evidence reference, schema, command compliance, and interval compliance. | \(p_{e,f,\Delta} = \arg\min_{p \in \mathcal{P}(f,\Delta)} J(p; s_0, \hat{q}_{0:T}, \mathcal{C}, \Theta_e)\).<br>\(\tau_{e,f,\Delta}=\mathrm{Sim}(p_{e,f,\Delta}, q_{0:T}, s_0)\).<br>\(C_{cmd}=\mathbb{1}[p \in \mathcal{P}(f)]\).<br>\(C_{int}=\mathbb{1}[\mathrm{step}(p)=\Delta]\). | \(A = O_{tool}\land O_{ref}\land O_{schema}\land \neg V_{hard}\land \neg V_{downstream}\).<br>\(A_{static}=A\land C_{cmd}\land C_{int}\).<br>Record: plan id, release family, interval, trajectory, metrics, \(A_{static}\). |
| Dynamic command-intervention operation | For selected event \(e\), checkpoint \(c \in C_e\), command \(d \in D_4\). | 1. \(s_c \leftarrow\) `get_reservoir_status(e, t_c)`.<br>2. \(\mathcal{R}_c,\mathcal{C}_c \leftarrow\) `query_dispatch_rules(e, s_c)`.<br>3. Parse command \(d\) into modified constraint/target set \(\mathcal{C}'_c,\Theta'_c\).<br>4. Feasibility pre-check: \(G(d,s_c,\mathcal{C}'_c,\Theta'_c)\).<br>5a. If feasible: \(p_{e,c,d} \leftarrow\) `optimize_release_plan(s_c, \hat{q}_{c:T}, \mathcal{C}'_c, d, \Theta'_c)`.<br>5b. If infeasible/unsafe: return structured rejection \(r_{e,c,d}\).<br>6a. If planned: \(\tau_{e,c,d}\leftarrow\) `simulate_dispatch_program(p_{e,c,d}, q_{c:T}, s_c)` and \(m_{e,c,d}\leftarrow\) `evaluate_dispatch_result(\tau_{e,c,d}, \mathcal{C}'_c)`.<br>7. Validate payload, tool sequence, evidence reference, safety, and command outcome. | \(G=1\) means command constraints admit a safe candidate.<br>If \(G=1\): \(p_{e,c,d}=\arg\min_{p\in\mathcal{P}(d)}J(p;s_c,\hat{q}_{c:T},\mathcal{C}'_c,\Theta'_c)\).<br>If \(G=0\): \(r_{e,c,d}=\mathrm{Reject}(d,\mathrm{reason},\mathcal{C}'_c)\).<br>\(\mathrm{FES}=\mathbb{1}[G=1\land A\land \mathrm{executed}(p)]\). | \(\mathrm{CHS}=\mathbb{1}[(G=1\land A\land \mathrm{executed}(p))\lor(G=0\land O_{schema}\land O_{ref}\land \mathrm{structured}(r))]\).<br>\(A_{dynamic}=\mathrm{CHS}\) with hard/downstream gates checked when a plan is executed.<br>Record: command id, checkpoint, executed plan or rejection, CHS, FES, failure reason. |
| Rolling forecast-triggered operation | For forecast-enabled event \(e \in E_{10}^{pred}\), rolling check \(k=0,\ldots,K_e\) at 3 h interval. | 1. Initialize with fixed forecast \(\hat{q}^{(0)}_{0:T}\).<br>2. At each check \(t_k\), update observed state \(s_k\leftarrow\) `get_reservoir_status(e, t_k)` using observed inflow and level.<br>3. Compute trigger vector \(z_k=(z^{abs}_k,z^{rel}_k,z^{risk}_k,z^{sch}_k)\).<br>4. If \(T_k=\mathbb{1}[\max(z_k)=1]=1\): query rules, optimize, simulate, evaluate, and validate a new rolling plan through the MCP tool chain.<br>5. If \(T_k=0\): retain previous plan \(p_{k}=p_{k-1}\) and write deterministic audit row.<br>6. Store trigger reason, action, metrics, evidence reference, and acceptance flag. | \(T_k=z^{abs}_k\lor z^{rel}_k\lor z^{risk}_k\lor z^{sch}_k\).<br>If \(T_k=1\): \(p_k=\arg\min_{p\in\mathcal{P}}J(p;s_k,\hat{q}^{(0)}_{k:T},\mathcal{C}_k)\), \(\tau_k=\mathrm{Sim}(p_k,q_{k:T},s_k)\).<br>If \(T_k=0\): \(p_k=p_{k-1}\).<br>\(\rho_{call}=N_{retain}/N_{checks}\). | If \(T_k=1\): \(A_k=A\).<br>If \(T_k=0\): \(A_k=A_{retain}=1\) when deterministic retain audit row is complete.<br>Rolling acceptance: \(A_{rolling}=\prod_k A_k\) at event level or \(\sum_k A_k/N_{checks}\) at check level.<br>Record: trigger/retain action, plan id, release step, level trace, accepted flag. |

**Table 5.1. Scenario design and deterministic oracle coverage.**

| Scenario | Operational role | Deterministic coverage | Stage 3 evaluation | Key success criteria |
| --- | --- | --- | --- | --- |
| Static release planning | Full-horizon release-level planning and operator-specified release form/interval | 41 main records + 492 instruction-conditioned records | 96 representative instruction records per executor | feasibility; command compliance; interval compliance; zero hard/downstream violations |
| Dynamic command intervention | Checkpoint-based retain/replan decisions plus D1-D4 operator command validation | 48 main retain/replan oracle records used in the 462-row Stage 3 summary + 40 command-intervention subset records for D1-D4 instruction validation | 48 main dynamic records per executor in the 462-row summary; 40 command records per executor in the command subset | retain/replan validity; command handling success; feasible execution success; structured rejection if infeasible |
| Rolling forecast-triggered operation | Fixed initial forecast with 3 h observed-state updates and trigger-only LLM calls | 373 rolling checks + 51 supplementary forecast-error wrongtest stages | 373 checks per executor; 142 LLM-called nodes; supplementary 51-stage perturbed-forecast check | trigger validity; fail-closed acceptance; LLM-call reduction; forecast-error auditability |
| Tools/skills ablation | Mechanism validation for tools and workflow-skill contracts | ablation variants | text-only; tools-only; tools plus skills/full MCP | auditable acceptance; tool-order validity; eval-ref validity; schema validity |

The generated scenario-oracle table gives the same accounting from a coverage perspective. S1 contributes 36 oracle rows, S2 contributes 85, S3 contributes 256, and S4 contributes 85. By workflow, the deterministic oracle remains 41 static rows, 48 dynamic rows, and 373 rolling rows, totaling 462 rows.

### 5.2 Static instruction-conditioned release planning

The static scenario evaluates full-horizon release-level planning when the operator specifies both the release family and operation interval. The default static oracle accepted 41/41 retained events with zero hard-safety violations and zero downstream-routing violations. The instruction-conditioned deterministic extension contains 492 rows, corresponding to 41 events, six release families, and two operation intervals. Stage 1 accepted 492/492 rows, with 492/492 command compliance and 492/492 interval compliance. Stage 2 reproduced all 492 rows with no accepted-status, command-compliance, interval-compliance, or metric-tolerance mismatch.

The flood-group static summary confirms that the deterministic baseline is feasible across the retained risk groups. S1 accepted 8/8 records, S2 accepted 16/16, S3 accepted 12/12, and S4 accepted 5/5. Across all 41 events, the mean maximum water level is 154.6 m, the maximum simulated level reaches 160.0 m, the mean terminal deviation is 4.9 m, and the mean inflow-peak attenuation rate is 0.980. The grouped mean maximum levels are 149.4 m for S1, 154.4 m for S2, 158.0 m for S3, and 155.6 m for S4. The grouped mean inflow-peak attenuation rates are 1.000, 1.000, 0.952, and 0.955, respectively.

Stage 3 was run on a representative 96-row subset per executor. MiMo v2.5 accepted 93/96 rows, Claude Haiku 4.5 accepted 94/96 rows, and MiniMax M2.5 accepted 87/96 rows. Interval compliance was 100.0% for all three executors. The residual losses were rejected by the fail-closed gate and were mainly associated with protocol, schema, or command-compliance checks, not hydrological hard-safety failures. Table 5.2 reports the static results.

**Figure 5.1 reading: static instruction dispatch.** The generated dispatch figure `fig5_1_static_instruction_dispatch.png` visualizes three representative static events: 2024061623, 2010062002, and 2012062402. Each row pairs an inflow-and-release panel with a reservoir-level panel. The release panels show the observed inflow in black and six command-specified release families at a 6 h operation interval: constant, inflow-PWC, inflow-linear, storage-PWC, storage-NL, and joint-driven. The level panels show how these different release shapes translate into reservoir storage response against the flood-limit line. For the high-water 2024061623 event, several release families approach the 160.0 m flood-limit line, while the inflow-PWC family produces visibly lower intermediate levels because it releases more aggressively near the inflow peaks. For 2010062002, the release-active case shows larger separation between the inflow-driven families and the flatter storage/constant families; the resulting levels rise toward, but remain bounded by, the flood-limit line. For 2012062402, the inflow peaks are smaller in magnitude and the release families are closer together, so the level trajectories almost overlap and gradually approach the terminal target. The figure supports command-following and feasibility checks for release-level planning; it is not a ranking of release families.

**Table 5.2. Static instruction-conditioned release-planning results.**

| Executor / source | Records | Accepted | Command compliance | Interval compliance | Tool-order valid | Eval-ref valid | Schema valid | Hard viol. | Downstream viol. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 default static oracle | 41 | 41/41 (100.0%) | not applicable | not applicable | not applicable | not applicable | not applicable | 0 | 0 |
| Stage 1/2 instruction deterministic oracle | 492 | 492/492 (100.0%) | 492/492 (100.0%) | 492/492 (100.0%) | not applicable | not applicable | not applicable | 0 | 0 |
| MiMo v2.5 | 96 | 93/96 (96.9%) | 96.9% | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 0 |
| MiniMax M2.5 | 96 | 87/96 (90.6%) | 90.6% | 100.0% | 92.7% | 92.7% | 92.7% | 0 | 0 |
| Claude Haiku 4.5 | 96 | 94/96 (97.9%) | 97.9% | 100.0% | 97.9% | 97.9% | 97.9% | 0 | 0 |

### 5.3 Dynamic command-intervention operation

Two dynamic datasets are reported because they answer different validation questions. The 48 dynamic retain/replan records are the main dynamic oracle used in the 462-record Stage 3 summary, together with 41 static records and 373 rolling checks. They evaluate whether the workflow makes checkpoint-level retain or replan decisions over 10 events. The 40 command-intervention records are a focused subset for operator-instruction validation, testing whether D1-D4 command types are parsed, checked, executed, or rejected correctly. The two counts are therefore complementary rather than additive inside the 462-row main oracle.

The dynamic command-intervention scenario evaluates mid-event operator commands at two checkpoints across five selected events. The verified deterministic command matrix contains 40 rows: 5 events, 4 command types, and 2 checkpoints. The five events are 2010062002, 2021052114, 2009080920, 2012062402, and 2024061623, each contributing eight command records. The command set covers stricter release caps, lower terminal targets, compressed target deadlines, and conservative risk buffers. Stage 1 achieved 40/40 command handling success and 40/40 feasible execution success. Stage 2 matched the Stage 1 command oracle on 40/40 rows, with oracle_pass=True. The metric separates command-handling success from feasible-execution success, so that a structured rejection would be counted as successful handling when a command is infeasible.

Stage 3 shows executor sensitivity in command-intervention protocol adherence. Claude Haiku 4.5 accepted 40/40 command rows. MiniMax M2.5 accepted 39/40 rows, with one wrong-tool-order rejection. MiMo v2.5 accepted 38/40 rows, with two wrong-tool-order rejections. In all three runs, hard-safety and downstream-routing violation counts were zero. Table 5.3 reports the dynamic command results.

The broader deterministic dynamic retain/replan oracle contains 48 records across 10 events, with 26 replan decisions and 22 retain decisions. The event-level dynamic summary is concentrated in high-risk and extreme events: S3 contributes 30 dynamic rows and S4 contributes 15 rows, while S1 and S2 contribute 1 and 2 rows. This supports the command-intervention result by showing that dynamic operation is represented as checkpoint-based workflow decisions rather than as a single full-event plan.

**Figure 5.2 reading: dynamic command dispatch.** The generated dispatch figure `fig5_2_dynamic_command_dispatch.png` shows chained mid-event commands for 2010062002, 2024061517, and 2024061623. Each row again pairs flow and level panels. Vertical markers identify command checkpoints C1, C2, and C3, while colored command segments show the executed release and level trajectories after each intervention. In 2010062002, the C1 release-cap adjustment keeps the release near a low controlled value during the first segment, the C2 lower-target command raises the release slightly as the event develops, and the C3 safety-buffer command continues the controlled release while the level rises toward but remains below 160.0 m. In 2024061517, the first safety-buffer command is applied during a rising high-water state; later release-cap and terminal-target commands generate visibly different projected levels, showing how target and safety preferences alter the remaining operation horizon. In 2024061623, the release-cap command begins during a high inflow episode, the safety-buffer segment is applied soon after, and the lower-target segment maintains higher planned releases over the remainder of the event. The figure records command execution and validation context; it should be read as an intervention trace rather than as a comparison with historical operation.

**Table 5.3. Dynamic command-intervention results.**

| Executor / source | Records | Accepted | CHS | FES | Tool-order valid | Eval-ref valid | Schema valid | Hard viol. | Downstream viol. | Failure reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 command deterministic oracle | 40 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | not applicable | not applicable | not applicable | 0 | 0 | none |
| Stage 2 command workflow oracle | 40 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | not applicable | not applicable | not applicable | 0 | 0 | oracle_pass=True |
| MiMo v2.5 | 40 | 38/40 (95.0%) | 38/40 (95.0%) | 38/40 (95.0%) | 38/40 (95.0%) | 38/40 (95.0%) | 38/40 (95.0%) | 0 | 0 | wrong_tool_order x2 |
| Claude Haiku 4.5 | 40 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 0 | 0 | none |
| MiniMax M2.5 | 40 | 39/40 (97.5%) | 39/40 (97.5%) | 39/40 (97.5%) | 39/40 (97.5%) | 39/40 (97.5%) | 39/40 (97.5%) | 0 | 0 | wrong_tool_order x1 |

### 5.4 Rolling forecast-triggered operation

The rolling scenario uses one fixed forecast issued at event start. Observed inflow and reservoir state are updated every 3 h, but the forecast itself is not updated. At each check, a deterministic trigger checker decides whether the LLM+MCP workflow is called or whether the existing plan is retained as a deterministic audit row.

The rolling oracle contains 373 checks across 10 forecast-enabled events. The trigger-only policy calls the LLM at 142 checks and records 231 deterministic retain rows. The LLM-call reduction is therefore 231/373, or 61.9%. Full event and check coverage was retained while reducing LLM calls. The deterministic retain branch was accepted in all 231 records for each executor.

Stage 3 rolling acceptance was 367/373 for MiniMax M2.5, 368/373 for MiMo v2.5, and 370/373 for Claude Haiku 4.5. The rejected rows are fail-closed auditability failures rather than hydrological hard-safety failures. Table 5.4 reports rolling results.

**Figure 5.3 reading: rolling dispatch process.** The generated dispatch figure `fig5_3_rolling_dispatch_process.png` shows five representative rolling events: 2012062402, 2021052114, 2022062023, 2013100711, and 2024061623. In each row, the left panel compares observed inflow, the fixed initial forecast, and the rolling release trajectory, while the right panel shows the reservoir level, flood-limit line, replan markers, and retain markers. The 2012062402 row shows a long multi-trigger case: repeated replan markers appear around the main inflow pulses and the rolling release increases before later tapering as inflow recedes. The 2021052114 and 2022062023 rows show high-volume cases where the fixed forecast closely follows observed inflow around major peaks, and the release trajectory changes stepwise only at trigger points. The 2013100711 row shows an extreme inflow case with high observed inflow at the beginning of the event and a rolling release path that remains high while the level declines below the flood limit. The 2024061623 row shows a short high-water event in which replan markers cluster early, after which the level remains below the 160.0 m limit. Across rows, retain markers document that non-trigger checks remain auditable deterministic records rather than omitted decisions.

The rolling section also includes a supplementary forecast-error wrongtest because the real automatic forecasts in the 10-event rolling experiment were relatively accurate. The wrongtest perturbs only the `predict` forecast inflow column; observed inflow, observed outflow, water level, state propagation, and evaluation remain tied to the observed event record. It is therefore a perturbed-forecast audit on real observed events, not a synthetic flood experiment. Five representative events were used: 2012062402 with a 6 h lag, 2022062023 with a mild over-peak perturbation, 2013100711 with a mild under-peak perturbation, 2024061623 with a 6 h lead, and 2024072617 with a mixed mild perturbation.

The forecast-error Stage 2 deterministic workflow contains 51 stages and accepted 51/51, with zero hard-constraint violations. The stage counts are 21 for 2012062402, 11 for 2022062023, 7 for 2013100711, 5 for 2024061623, and 7 for 2024072617. All four trigger types are observed in this supplementary run: scheduled_12h_check appears 28 times, relative_forecast_error appears 12 times, absolute_forecast_error appears 8 times, and state_risk appears 3 times. Stage 3 MiMo v2.5 accepted 51/51 with 1.0 MCP tool-call success, 1.0 structured-output validity, 1.0 evaluation-reference validity, and 1.0 protocol adherence. Stage 3 Claude Haiku 4.5 also accepted 51/51 with the same gate rates and zero hard-constraint violations. The available MiniMax M2.5 wrongtest event summary records 0/51 accepted because the final payload/tool-protocol gates were invalid; it also records zero hard-constraint violations. This MiniMax wrongtest run is therefore an auditability/protocol failure record, not a hydrological safety failure.

**Figure 5.4 reading: forecast-error wrongtest.** The generated dispatch figure `fig5_4_wrongtest_forecast_error.png` compares observed inflow, the original forecast, the perturbed forecast, the rolling release, and reservoir level for the five perturbed events. The lag +6 h case for 2012062402 shifts forecast peaks later than the observed peaks, producing many replan markers across 21 stages; the reservoir level rises gradually and stays below the displayed flood-limit line. The over-peak case for 2022062023 amplifies forecast peaks while preserving peak timing, and the rolling release remains a stepwise conservative response with 11 stages. The under-peak case for 2013100711 suppresses the forecast peak, but the observed-state updates still drive replanning and the level remains below its limit. The lead -6 h case for 2024061623 advances the forecast timing, producing five replan stages in a short high-water event. The mixed mild case for 2024072617 combines timing and magnitude differences over seven stages, with lower absolute inflow and level ranges than the other examples. The figure supports the interpretation that forecast-error triggers and observed-state updates can preserve auditability under mild degraded forecasts; it is not a complete forecast-uncertainty analysis.

**Table 5.4. Rolling forecast-triggered operation results.**

| Executor | Records | LLM-called | Retain rows | Accepted | Accepted LLM decisions | Accepted retain rows | Hard viol. | Downstream viol. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MiniMax M2.5 | 373 | 142 | 231 | 367/373 (98.4%) | 136/142 (95.8%) | 231/231 (100.0%) | 0 | 0 |
| MiMo v2.5 | 373 | 142 | 231 | 368/373 (98.7%) | 137/142 (96.5%) | 231/231 (100.0%) | 0 | 0 |
| Claude Haiku 4.5 | 373 | 142 | 231 | 370/373 (99.2%) | 139/142 (97.9%) | 231/231 (100.0%) | 0 | 0 |

**Table 5.4a. Supplementary forecast-error wrongtest results.**

| Source / executor | Events | Stages | Accepted / success | Hard viol. | Tool/protocol evidence |
| --- | --- | --- | --- | --- | --- |
| Stage 2 deterministic workflow | 5 | 51 | 51/51 (100.0%) | 0 | direct workflow reference |
| MiMo v2.5 | 5 | 51 | 51/51 (100.0%) | 0 | MCP, schema, eval-ref, protocol all 1.0 |
| Claude Haiku 4.5 | 5 | 51 | 51/51 (100.0%) | 0 | MCP, schema, eval-ref, protocol all 1.0 |
| MiniMax M2.5 available run | 5 | 51 | 0/51 (0.0%) | 0 | final payload/protocol invalid in event summary |

### 5.5 Ablation of tools and workflow skills

The ablation results test whether auditable execution depends on tool access and workflow-skill contracts. The text-only setting can produce formatted numeric plans, but it has no tool-grounded evaluation reference and therefore has 0/40 auditable accepted records. The tools-only setting improves grounding but remains vulnerable to protocol and evidence-binding failures, reaching 27/32 auditable accepted records in the frozen ablation table. The tools plus skills/full MCP setting reaches 40/40 auditable accepted records, with 40/40 tool-order validity, 40/40 evaluation-reference validity, and 40/40 schema validity.

These results show that tools and workflow skills improve auditable execution. They do not imply that the optimization kernel itself changes across ablation variants. Table 5.5 reports the ablation results.

The cross-executor Stage 3 summary provides a compact consistency check for the main 462-row evaluation. MiniMax M2.5 accepted 451/462 rows, MiMo v2.5 accepted 457/462 rows, and Claude Haiku 4.5 accepted 452/462 rows. Oracle metric comparison is PASS for all three executors, with zero hard-safety violations and zero downstream-routing violations. By workflow, all three executors accepted 41/41 static records. The dynamic main-workflow acceptance counts are 43/48 for MiniMax M2.5, 48/48 for MiMo v2.5, and 41/48 for Claude Haiku 4.5. The rolling counts are 367/373, 368/373, and 370/373, respectively. The failure taxonomy records only auditability and protocol failures: MiniMax M2.5 has 4 wrong-tool-order, 3 missing-required-tool, and 4 missing-evaluation-reference rejections; MiMo v2.5 has 5 missing-evaluation-reference rejections; Claude Haiku 4.5 has 7 wrong-tool-order and 3 missing-required-tool rejections.

**Table 5.5. Ablation of tools and workflow skills.**

| Variant | Method id | Records | Accepted | Tool-order valid | Eval-ref valid | Schema valid | Hard viol. | Downstream viol. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Text-only | mimo_without_tools | 40 | 0/40 (0.0%) | not applicable (no tools) | 0/40 (0.0%) | 40/40 (100.0%) | 0 | not evaluated |
| Tools-only | mimo_mcp_no_skill | 32 | 27/32 (84.4%) | 27/32 (84.4%) | 27/32 (84.4%) | 27/32 (84.4%) | 0 | not evaluated |
| Tools + skills / full MCP | mimo_mcp_skill | 40 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 0 | not evaluated |

### 5.6 Data sources for this result draft

The values above were checked against the current generated Chapter 5 assets and experiment reports:

| Result element | Primary source |
| --- | --- |
| Scenario/oracle coverage | `docs/paper/figures/chapter5/generated/tables/table5_1_scenario_oracle_coverage.csv` |
| Static group summary | `docs/paper/figures/chapter5/generated/tables/table5_2_static_by_flood_group.csv` |
| Dynamic retain/replan summary | `docs/paper/figures/chapter5/generated/tables/table5_3_dynamic_results.csv` |
| Rolling trigger-only summary | `docs/paper/figures/chapter5/generated/tables/table5_4_rolling_trigger_only.csv` |
| Main executor summary | `docs/paper/figures/chapter5/generated/tables/table5_5_executor_stage3_summary.csv` |
| Workflow-by-executor summary | `docs/paper/figures/chapter5/generated/tables/table5_6_workflow_by_executor.csv` |
| Failure taxonomy | `docs/paper/figures/chapter5/generated/tables/table5_7_failure_taxonomy.csv` |
| Forecast-error wrongtest | `experiments/results/paper_validation/forecast_error_wrongtest/forecast_error_wrongtest_report.md` and event/trigger summaries under the same folder |
| Dispatch figures | `docs/paper/figures/chapter5/generated/dispatch/*.png` |
