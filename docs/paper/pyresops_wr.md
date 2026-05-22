# Workflow-Constrained Generative AI for Auditable Reservoir Flood-Operation Decision Support

## Abstract

Safe reservoir flood operation is an important component of sustainable water management, climate resilience, and downstream risk reduction. Generative AI can provide a flexible interface for operational decision support, but unconstrained large language model (LLM) outputs are not sufficient for safety-relevant water operations. This paper proposes a workflow-constrained generative AI methodology for auditable single-reservoir flood-operation decision support. The methodology embeds LLM agents as instruction interpreters and workflow coordinators, while deterministic tools perform hydrological computation, release simulation, constraint checking, and evaluation. A decision record is accepted only when the required workflow is completed, the final payload is bound to the current tool-returned evaluation result, schema validation succeeds, and hard constraints are satisfied. The methodology is instantiated as PyResOps and evaluated on retained flood events from Tankeng Reservoir, covering static planning, dynamic retain/replan operation, command intervention, rolling forecast-triggered operation, forecast-error audit, cross-executor testing, and tools/skills ablation. In the 462-record main workflow set, three LLM executors achieved acceptance rates of 98.9%, 97.6%, and 97.8%, with no hard-constraint or downstream-release violations. Ablation results show that tool access alone is insufficient; auditable generative AI for reservoir operation requires explicit workflow protocols and fail-closed validation.

**Keywords:** reservoir flood operation; generative AI; large language model agent; sustainable water management; auditable decision support; workflow governance; fail-closed validation; water safety

---

# 1. Introduction

Sustainable water management is increasingly shaped by the need for timely, adaptive, and accountable decisions under hydrological uncertainty. Under climate change, more frequent and intense extreme rainfall events are increasing the pressure on flood-control infrastructure, downstream water security, and climate-resilient water services. Modern water systems are no longer managed only through static infrastructure design or routine operation; they require continuous interpretation of monitoring data, forecasts, operational constraints, risk signals, and human instructions. Artificial intelligence (AI) has therefore become an important direction for improving prediction, monitoring, automation, and decision support in water engineering. Machine learning and deep learning have been used for flood prediction, water-quality assessment, leakage detection, remote sensing analysis, and smart operation of water infrastructure. Together, these developments form an important basis for intelligent and sustainable water systems, in which computational models support data interpretation, operational planning, and real-time response.

Reservoir flood operation is a representative safety-relevant water-management task in this transition. During a flood event, operators must interpret reservoir level, storage, inflow, release capacity, downstream constraints, forecast uncertainty, and operational targets, and then issue release decisions that can be executed over the remaining horizon. Such decisions influence flood-risk reduction, downstream safety, infrastructure reliability, hydropower and water-supply continuity, and the resilience of water services during extreme events. A reservoir-operation recommendation is therefore not useful merely because it is plausible or clearly written. It must correspond to a release trajectory that can be computed, simulated, checked against hard operational constraints, evaluated against operational objectives, and reconstructed after the event.

Reservoir operation has long been studied as a constrained water-resources decision problem. Rule curves, operating rules, simulation models, optimization algorithms, and rolling-horizon control remain central because they preserve explicit links among reservoir states, release decisions, physical constraints, and evaluation metrics (Yeh, 1985; Labadie, 2004). More recent scenario-based and model-predictive-control formulations further address the sequential and forecast-dependent nature of flood operation, allowing release plans to be revised as inflow forecasts, reservoir states, or operational preferences change (Cestari et al., 2023; Koo et al., 2024). These methods provide the computational foundation for reservoir flood management. However, practical operation is not only a release-optimization problem. Operators may revise instructions during an ongoing event, such as lowering the terminal water-level target, tightening a release cap, shortening the deadline for reaching a target level, imposing a conservative safety buffer, or deciding whether a forecast deviation requires replanning. Deterministic reservoir-operation models can evaluate such requests once they are properly encoded, but they do not naturally provide a flexible interface for translating changing natural-language operational intent into structured, executable, and auditable workflow tasks.

Generative AI, especially large language model (LLM) agents, offers a possible interface layer for this problem. Unlike conventional numerical models designed for specific prediction or optimization tasks, LLM agents can interpret natural-language instructions, organize multi-step procedures, select external tools, and generate structured summaries. Recent studies have started to examine LLMs and LLM-based agent systems in water engineering, including water-science question answering, hydrological knowledge tasks, code assistance, conversational support, model interaction, data integration, monitoring, reservoir management, flood response, and collaborative decision-making. These studies identify an important opportunity: LLM-powered systems may help connect human instructions, technical knowledge, external data sources, numerical models, and operational reporting. However, much of the current literature remains conceptual, benchmark-oriented, or system-oriented. Fewer studies have operationally tested how LLM agents should be constrained, verified, and rejected in real reservoir-operation workflows. A key practical question therefore remains insufficiently addressed: how can generative AI be embedded into a safety-relevant water-management workflow while preserving traceability, physical constraint safety, and operational accountability?

Direct use of LLM-generated recommendations is risky in reservoir flood operation. An LLM agent may skip a required simulation, call tools in an invalid order, reuse stale values from an earlier stage, report a result that was not produced by the current tool session, or generate a final answer that appears structured but is not linked to any reproducible evaluation. These errors are not simply language-quality problems. In safety-relevant reservoir operation, they determine whether a decision record can be trusted, audited, and reviewed after the event. A safe-looking textual answer without a valid execution trace is not an acceptable operational record. Tool access alone also does not solve the problem. A standardized tool interface can expose reservoir-operation functions through structured inputs and outputs, but it does not by itself define which tool sequence is valid, which workflow branch should be followed, which calls are prohibited, or which tool-returned evidence must appear in the final decision. In this setting, workflow governance is part of the engineering knowledge base.

This paper addresses this practical adoption barrier by proposing a workflow-constrained generative AI methodology for auditable single-reservoir flood-operation decision support. The central idea is to place the LLM agent at the operational interface rather than at the computational authority layer. The agent interprets operator instructions, selects the relevant workflow, coordinates permitted tools, and generates a structured decision payload. Hydrological computation, release simulation, constraint checking, and performance evaluation are delegated to deterministic reservoir-operation tools. The final decision is accepted only when it is tied to a valid tool execution trace, bound to the current tool-returned evaluation result, and checked by an external fail-closed validator. This design converts the LLM output from a free-form recommendation into an auditable decision record.

The methodology has four core principles. First, numerical quantities that determine physical feasibility are computed by deterministic tools rather than generated by the language model. Second, the LLM agent operates under explicit workflow protocols that define required tool sequences, branch logic, prohibited calls, and final payload requirements. Third, each final decision record binds to the current-stage evaluation result returned by the tools, so that the reported decision can be traced to reproducible computation. Fourth, validation is fail-closed: if a required tool call, evaluation reference, schema field, or hard-constraint check is missing or invalid, the record is rejected rather than treated as a usable recommendation. These principles are intended to make the boundary of acceptable agent behavior explicit, rather than relying on the apparent fluency or confidence of the generated answer.

In this study, the methodology is instantiated as PyResOps for single-reservoir flood operation. PyResOps connects a deterministic reservoir-operation kernel with a tool-mediated LLM-agent execution layer, workflow skills, and an external validator. The deterministic kernel computes release plans, state trajectories, evaluation metrics, and constraint checks. The tool interface exposes these computations through structured inputs and outputs. Workflow skills specify how static planning, dynamic retain/replan operation, mid-event command intervention, and rolling forecast-triggered operation should be executed. The validator then checks workflow/tool order, evidence binding, payload schema, hard operational constraints, and downstream release constraints before accepting a decision record.

The case study uses retained flood-event records from Tankeng Reservoir. The evaluation is organized as a staged validation design. Stage 1 directly calls the deterministic reservoir-operation kernel to establish executable references. Stage 2 exposes the same computations through tool-mediated fixed workflows to verify that tool schemas and workflow wrappers reproduce the deterministic references. Stage 3 introduces LLM executors and evaluates whether they can complete auditable decision records under workflow constraints. The experiments cover static planning, dynamic retain/replan operation, command intervention, rolling forecast-triggered operation, forecast-error audit, cross-executor testing, and tools/skills ablation. This design evaluates not only whether release plans are hydrologically feasible, but also whether generative-AI-assisted execution remains traceable, evidence-bound, and acceptable under a conservative validation rule.

The contribution of this paper is threefold. First, it proposes a workflow-constrained generative AI methodology for embedding LLM agents into safety-relevant reservoir flood-operation decision support. The methodology converts natural-language operational intent into structured workflow execution while limiting the LLM role to instruction interpretation, workflow coordination, and structured reporting. Second, it develops an evidence-bound and fail-closed validation mechanism for generative-AI-assisted operation records. A decision is accepted only when the required workflow is completed, the final payload is bound to the current tool-returned evaluation result, the schema is valid, and hard operational constraints are satisfied. Third, it validates the methodology through a real-event Tankeng Reservoir case study covering static, dynamic, command-intervention, rolling, forecast-error, and ablation experiments. In the 462-record main workflow set, three LLM executors achieved acceptance rates of 98.9%, 97.6%, and 97.8%, with no hard-constraint or downstream-release violations. The ablation further shows that text-only generation produced no auditable accepted records, tools-only execution remained vulnerable to protocol and evidence-binding failures, and deterministic tools combined with workflow protocols and external validation supported reliable generative-AI-assisted execution under the evaluated single-reservoir setting.

---

# 2. Methodology: workflow-constrained generative AI for reservoir flood-operation decision support

## 2.1 Methodological overview: embedding LLM agents into reservoir-operation workflows

The proposed methodology embeds LLM agents into reservoir flood-operation decision support as workflow coordinators rather than reservoir-operation decision makers. The operational chain is organized as instruction interpretation, task formalization, deterministic tool execution, evidence binding, external validation, and audit-record generation. This chain defines how a natural-language instruction can enter a safety-relevant water-management workflow without allowing the language model to become the source of numerical authority.

The methodology has four functional layers. The first layer is a deterministic reservoir-operation kernel that computes release plans, state trajectories, evaluation metrics, and constraint checks. The second layer exposes these computations as structured tools with explicit input and output schemas. The third layer is the LLM-agent execution layer, which interprets the task context and coordinates tool calls under workflow skills. The fourth layer is the fail-closed validation layer, which checks whether the agent has followed the permitted workflow and whether the resulting decision can be accepted as an auditable record.

**Figure 1. Workflow-constrained methodology for LLM-assisted auditable single-reservoir flood operation.**  
The LLM agent interprets operator instructions and coordinates deterministic reservoir-operation tools under workflow skills. Accepted decisions must pass evidence-bound fail-closed validation, including tool-order, evaluation-reference, schema, hard-constraint, and downstream-release checks.

The separation between deterministic water-operation computation and agent coordination is central to the methodology. All quantities that determine physical feasibility are computed by tools. The LLM is not asked to estimate water levels, storage changes, release capacities, objective components, or constraint violations from text. Its role is limited to interpreting instructions, selecting the appropriate workflow, coordinating permitted tools, and producing a structured final payload. The final payload is accepted only if it can be linked to the current tool-returned evidence and passes external validation.

This design treats the final response as a decision record rather than ordinary text. A valid record contains the task context, tool trace, evaluation reference, payload fields, validation outcome, and failure category if rejected. This record-level representation makes it possible to evaluate not only whether the underlying release plan is feasible, but also whether the agent produced it through an auditable business process.

## 2.2 Reservoir-operation task formalization and deterministic grounding

The computational core is a deterministic single-reservoir operation kernel. The kernel translates a release program into a reservoir state trajectory through the discrete water-balance equation:

\[
S_{t+1}=S_t+(I_t-Q_t)\Delta t,
\]

where \(S_t\) is storage, \(I_t\) is inflow, \(Q_t\) is release, and \(\Delta t\) is the time-step length. Water level is recovered from storage using a stage-storage relationship:

\[
Z_{t+1}=f_Z(S_{t+1}).
\]

Release feasibility is checked against the physical release-capacity curve:

\[
Q_t \leq Q_{\max}(Z_t).
\]

The evaluated scenarios impose a scenario-specific upper operating level and a downstream release constraint. In this study, the scenario-imposed upper operating level is 160.0 m, and the uniform downstream release constraint is 3000 m³/s. The historical flood-season limit level of 156.5 m and the design flood level of 165.87 m are treated as reservoir-background information rather than as the direct hard threshold used in the evaluated scenarios. This distinction is described in Section 3.1 and Appendix A.

A release program \(\pi=\{Q_t\}_{t=0}^{T-1}\) is treated as hard-feasible only if all time steps satisfy the upper-level constraint, downstream release constraint, and physical release-capacity constraint:

\[
H(\pi)=
\prod_{t=0}^{T-1}
\mathbf{1}
\left[
Z_t \leq Z_{\mathrm{upper}},
Q_t \leq Q_{\mathrm{down}},
Q_t \leq Q_{\max}(Z_t)
\right].
\]

The methodology formalizes reservoir-operation tasks into workflow types that can be coordinated by the LLM agent. Static planning asks the agent to execute a full-horizon release plan under a specified release family and operation interval. Dynamic operation asks the agent to follow either a replan branch or a retain branch at a checkpoint. Command intervention asks the agent to translate a mid-event operator instruction into updated constraints and a remaining-horizon execution. Rolling forecast-triggered operation asks the workflow to decide whether an updated observed state or forecast deviation requires replanning, while retaining the current plan as an auditable row when no trigger fires.

The kernel supports six release families, including constant, inflow-conditioned, storage-conditioned, and joint inflow-storage release formulations. These release families are used to create instruction-conditioned planning tasks. When a release family is specified, the correct behavior is not for the agent to choose a preferred family, but to use the requested family, complete the required workflow, and report the tool-grounded evaluation result. Full release-family definitions are provided in Appendix C.

## 2.3 Workflow-constrained agent execution

The methodology constrains LLM-agent execution through explicit workflow skills. A workflow skill is a protocol document that specifies required tool chains, branch conditions, prohibited calls, evaluation-reference rules, and final JSON payload format. In this setting, a skill is not an optional prompt hint. It functions as an execution contract between the agent and the validation layer.

In the PyResOps implementation, the deterministic kernel is exposed through MCPTools as a structured tool interface. The tool set includes event preparation, release-plan optimization, release simulation, release evaluation, constraint checking, workflow execution, and payload validation. Each tool has a structured input schema, output schema, and result identifier. The result identifier is used to bind the final decision payload to the tool-returned evaluation result.

The static workflow skill specifies a linear chain:

```text
prepare_event
  -> optimize_release_plan
  -> simulate_release_plan
  -> evaluate_release_plan
  -> final answer
```

The dynamic workflow skill specifies two branches. The `dynamic_replan` branch uses the full chain, while the `dynamic_retain` branch reuses the prior plan and requires only simulation and evaluation. For retain stages, the executor must not call `prepare_event` or `optimize_release_plan`. The rolling skill specifies trigger conditions and determines whether the workflow should replan or record a deterministic retain row.

The Agno workflow is used in two different ways. In Stage 2, Agno calls MCPTools through fixed workflows without an LLM executor. This verifies whether the tool-mediated workflow reproduces the direct-code reference. In Stage 3, Agno coordinates the LLM executor, MCPTools, and workflow skills. The LLM can call tools, but the accepted decision is determined by the external validator rather than by the model's final wording.

This structure makes tool order and branch discipline part of the evaluated behavior. A final answer may look correct but still be rejected if the agent used the wrong branch, omitted a required tool, called a prohibited tool, or failed to cite the current evaluation result. Conversely, a rejected record may correspond to a numerically feasible release plan, but it cannot be treated as an auditable operation record if the required workflow was not completed.

## 2.4 Evidence-bound decision records and fail-closed validation

A submitted decision record \(r\) is accepted only if all audit and safety conditions are satisfied:

\[
A(r)=\mathbf{1}
[
O_{\mathrm{tool}}(r)
\land O_{\mathrm{ref}}(r)
\land O_{\mathrm{schema}}(r)
\land \neg V_{\mathrm{hard}}(r)
\land \neg V_{\mathrm{down}}(r)
].
\]

Here, \(O_{\mathrm{tool}}\) denotes valid tool-order execution, \(O_{\mathrm{ref}}\) denotes valid evaluation-reference binding, \(O_{\mathrm{schema}}\) denotes final payload schema validity, \(V_{\mathrm{hard}}\) denotes hard-constraint violation, and \(V_{\mathrm{down}}\) denotes downstream-release violation. The rule is fail-closed because partial compliance is rejected. A record is not accepted merely because the text is plausible or because some tools were called. It must satisfy all conditions.

The final payload schema contains the decision type, selected plan identifier, safety status, hard-constraint flag, instruction-status flag, evaluation reference, and a concise explanation. The explanation is not used as the primary evidence. The accepted evidence is the tool trace and the referenced evaluation result. A final payload that cites an evaluation result from a previous stage is rejected even if the reported numbers are close to a feasible plan.

This criterion converts LLM-agent evaluation into decision-record validation. The validator checks whether the workflow was completed, whether the final record is bound to the current tool-returned evidence, whether required fields are present and valid, and whether hard operational constraints are satisfied. Rejected records are logged with failure categories, expected tool chains, observed tool chains, and reference-binding status. These logs support the failure taxonomy reported in Section 4.4 and Appendix J.

## 2.5 PyResOps implementation

PyResOps implements the proposed methodology for the Tankeng Reservoir single-reservoir flood-operation case study. It consists of a deterministic reservoir-operation kernel, a tool interface implemented with MCPTools, an Agno-based LLM-agent execution layer, workflow skill protocols, and a fail-closed validation layer. The deterministic kernel is organized into modules for event loading, reservoir state update, release-family construction, optimization, simulation, evaluation, and validation. The tool-interface layer wraps these functions as structured tools and returns machine-readable outputs with stable result identifiers.

PyResOps is implemented in Python 3.11. The inspected codebase contains 177 Python source modules and approximately 28,600 nonblank lines of project code, counted over the reusable package, experiment runners, and the root server entry point while excluding generated outputs, experiment result logs, tests, and documentation artifacts. The MCP server was deployed as a local subprocess FastMCP server. In the Stage 3 runtime template, Agno MCPTools connected through stdio command transport to `python -m pyresops.server`.

LLM executor calls used the profile-specific Agno model adapter defined in `experiments/config/llm_config.yml`; the main Stage 3 template selects the OpenAI-compatible MiniMax-M2.5 profile through `MINMAX_BASE_URL`, with default endpoint `https://api.penguinsaichat.dpdns.org/v1`. Calls used temperature 0, maximum output tokens 8192, and a single-attempt fail-closed policy: no automatic model-output retry was used, and timeout, schema, tool-order, or evidence-binding failures were recorded as rejected executions. The MCP connection, tool-call, and agent-call timeouts in the main template were 30 s, 120 s, and 180 s, respectively. All Stage 3 records were logged with tool-call traces, final payloads, evaluation references, and validation results. The full tool inventory and runtime configuration template are provided in Appendix D.

---

# 3. Case Study Setup

## 3.1 Study site and operational constraints

The case study uses processed flood-event records from Tankeng Reservoir in Zhejiang Province, China. Tankeng Reservoir is a large multipurpose reservoir with flood-control, hydropower, water-supply, and ecological-flow functions. Flood-control operation is the relevant setting in this paper. Figure 2 provides a study-area and operational-context overview.

**Figure 2. Tankeng Reservoir study area and operational context.**  
`[TO FILL: study-area overview figure. Suggested panels: map/location of Tankeng Reservoir; simplified reservoir-inflow-outflow schematic; key background water levels; data streams used by PyResOps; distinction between reservoir background parameters and experimental constraints.]`

The reservoir has several water-level references. The historical flood-season limit level of 156.5 m and the design flood level of 165.87 m are reported as study-site background. They are not used as the direct hard upper-level threshold in the evaluated scenarios. The experiments impose a scenario-specific upper operating level of 160.0 m. Similarly, site-level design discharge capacity is treated as reservoir background, while the experiments use a uniform downstream release constraint of 3000 m³/s to stress the decision workflow under a conservative release limit.

This separation prevents confusion between engineering background information and experimental validation constraints. The proposed implementation is evaluated as an auditable decision-support layer under the specified scenario constraints. It is not presented as an official operating rule or as a replacement for reservoir-authority review.

## 3.2 Flood-event dataset and scenario groups

The source archive contains 44 flood events. Three events were excluded before validation because their water-level states correspond to pre-impoundment or initial-filling conditions rather than normal reservoir operation. The retained dataset contains 41 flood events. The retained events are grouped into four scenario groups for stratified reporting: 8 S1 routine cases, 16 S2 moderate cases, 12 S3 high-risk cases, and 5 S4 extreme or high-volume cases.

The scenario groups are used to check operational diversity and to support stratified sampling. They are not used for frequency analysis. Full event lists, group labels, event durations, peak inflows, and data-quality notes are provided in Appendix E.

## 3.3 Three-stage validation design

The evaluation uses three validation stages to support the proposed generative AI methodology. Stage 1 directly calls the deterministic reservoir-operation kernel through code. No MCPTools, Agno workflow, or LLM executor is involved. This stage validates scenario executability, constraint evaluation, and deterministic reference generation.

Stage 2 exposes the same deterministic functions as MCPTools and calls them through fixed Agno workflows. No LLM executor is involved. This stage verifies that MCPTools, workflow ordering, input/output schemas, and evaluation-reference generation reproduce the Stage 1 reference.

Stage 3 introduces the LLM executor. The agent operates through Agno, uses MCPTools, and follows workflow skills. Stage 3 evaluates whether LLM agents can complete auditable execution under explicit workflow, branch-routing, reference-binding, and schema constraints. The Stage 3 executors are reported in the fixed order MiMo v2.5, MiniMax M2.5, and Claude Haiku 4.5. The ordering is fixed for reporting consistency and is not intended as a model ranking.

**Figure 3. Static, dynamic, and rolling workflows for LLM-assisted reservoir operation.**  
The static workflow executes a full-horizon planning pipeline, the dynamic workflow selects between replan and retain branches at checkpoints, and the rolling workflow triggers LLM-called replanning only when state-risk, forecast-error, or scheduled-check conditions are met. Each workflow produces an auditable decision record with a selected plan, safety status, and evaluation reference.

## 3.4 Evaluation blocks

The main workflow validation set contains 462 records:

\[
462 = 41 \text{ static} + 48 \text{ dynamic retain/replan} + 373 \text{ rolling checks}.
\]

This set is evaluated through Stage 1, Stage 2, and Stage 3. The 41 static records contain one default full-horizon planning task for each retained event. The 48 dynamic retain/replan records test whether the executor follows the correct branch at checkpoints. The 373 rolling checks test fixed-forecast rolling operation with observed-state updates and trigger-based replanning.

A larger static instruction-conditioned matrix contains 492 records:

\[
41 \text{ events} \times 6 \text{ release families} \times 2 \text{ operation intervals} = 492.
\]

The 492-record matrix is fully evaluated in Stage 1 and Stage 2. In Stage 3, each executor is evaluated on a 96-row stratified subset sampled across flood group, release family, and operation interval.

A separate 40-record command-intervention subset evaluates mid-event operator instructions. It contains 5 events, 2 checkpoints, and 4 command types: release-cap adjustment, terminal-target lowering, target-deadline compression, and conservative risk buffer. These 40 records are not included in the 462-record main workflow set. In this batch, all commands are feasible executions; structured rejection remains part of the workflow design but is not triggered.

The rolling workflow uses 10 forecast-enabled events and 373 checks. At each 3 h check, the workflow either triggers an LLM-called replan or retains the current plan and records a deterministic audit row. A forecast-error audit further perturbs only the forecast inflow column for five cases and produces 51 stages. Observed inflow, observed level, state propagation, and validation remain tied to real event records.

The tools/skills ablation evaluates three variants: text-only, tools-only, and tools + workflow skills / full MCP. Their record counts are 40, 32, and 40, respectively. The ablation tests whether auditable acceptance depends on tool access and workflow skills.

These blocks are intentionally not merged into a single undifferentiated pool. The 462-record set is the main workflow validation set; the 492-record static matrix expands the static instruction space; the 40-record command subset isolates mid-event command handling; the 51-stage forecast-error audit stresses rolling trigger behavior under degraded forecasts; and the ablation isolates mechanism contribution. This separation prevents a large record count from hiding differences in task purpose.

**Table 1. Experimental design and validation blocks.**

| Evaluation block                      | Record count                               | Stage coverage                                     | Role                                                |
| ------------------------------------- | ------------------------------------------:| -------------------------------------------------- | --------------------------------------------------- |
| Main workflow validation set          | 462 = 41 static + 48 dynamic + 373 rolling | Stage 1-3                                          | Main auditable workflow validation                  |
| Static instruction-conditioned matrix | 492                                        | Stage 1-2 full; Stage 3 96-row subset per executor | Command and interval compliance                     |
| Command-intervention subset           | 40                                         | Stage 1-3                                          | Mid-event command parsing and constrained execution |
| Forecast-error audit                  | 51                                         | Stage 2-3                                          | Degraded-forecast rolling audit                     |
| Tools/skills ablation                 | 40 / 32 / 40                               | Stage 3                                            | Mechanism test for tools and workflow skills        |

## 3.5 Evaluation metrics

The primary metric is fail-closed acceptance rate. A record is accepted only if the required tool order, evaluation-reference binding, schema validity, hard-constraint check, and downstream-release check are all valid. Secondary metrics include command compliance, interval compliance, tool-order validity, evaluation-reference validity, schema validity, hard-constraint violation count, downstream-release violation count, and LLM-call reduction in rolling operation.

The evaluation intentionally reports auditability failures as failures even when the associated numerical operation may be hydrologically safe. This conservative rule reflects the purpose of PyResOps: an accepted LLM-agent decision must be computationally grounded, auditable, and constraint-checked.

---

# 4. Results

## 4.1 Static instruction-conditioned release planning

The static scenario evaluates whether the implementation can generate feasible full-horizon release plans while following operator-specified release forms and implementation intervals. The default static workflow accepted all 41 retained events in Stage 1 and Stage 2, with zero hard-constraint violations and zero downstream-release violations.

The larger instruction-conditioned matrix contains 492 records, corresponding to 41 events, six release families, and two operation intervals. Stage 1 accepted 492/492 records. Stage 2 reproduced all 492 records with no accepted-status mismatch, command-compliance mismatch, interval-compliance mismatch, or metric-tolerance failure. This confirms that the deterministic kernel and Agno-MCP workflow implementation produce consistent instruction-conditioned references.

Across the 41 default static records, the mean maximum water level was 154.6 m, and the maximum simulated level reached the scenario-imposed upper operating level of 160.0 m. No record exceeded 160.0 m; four records reached exactly 160.0 m. The mean terminal deviation was 4.9 m. The internal inflow-peak attenuation metric averaged 0.980. This metric is interpreted as a release-shaping indicator within the evaluated plans, not as a comparison with historical operation.

Stage 3 was evaluated on a 96-row stratified static instruction subset for each executor. MiMo v2.5 accepted 93/96 records, MiniMax M2.5 accepted 87/96 records, and Claude Haiku 4.5 accepted 94/96 records. Interval compliance was 100% for all three executors. The rejected records were associated with auditability gates, including command-compliance or protocol-related checks, rather than hydrological hard-safety failures. This pattern is important for interpreting the static results. The deterministic instruction matrix establishes that the requested release-family and interval combinations are executable, whereas the Stage 3 subset evaluates whether the LLM executor follows the specified computational pathway. The static experiment therefore tests instruction adherence and evidence binding more than hydrological optimization quality.

The stratified 96-row subset is smaller than the 492-row deterministic matrix, but it preserves coverage across flood group, release family, and interval. This design avoids treating a single easy static command as representative of the full instruction space. The lower MiniMax acceptance rate in this subset is therefore interpreted as executor-specific protocol sensitivity under varied instructions, not as failure of the release families themselves.

Figure 4 visualizes representative static instruction-conditioned plans. The examples show that different release families produce distinct release-level trajectories while maintaining the requested operation interval and respecting the scenario-imposed upper operating level. The figure is used to illustrate instruction-conditioned feasibility and command following, not to rank release families.

**Figure 4. Static instruction-conditioned release planning under representative flood events.**  
`[TO FILL: final static figure. Each row should pair inflow-release trajectories with reservoir-level trajectories for representative events. Include release-family labels, 6 h or 12 h interval markers, scenario-imposed upper operating level, and accepted-status annotation.]`

## 4.2 Dynamic retain/replan and command-intervention operation

The dynamic results contain two related record pools and are reported together because both evaluate mid-event execution. The first pool is the 48-record dynamic retain/replan workflow included in the 462-record main validation set. The second pool is the 40-record command-intervention subset, which is not included in the 462-record set. No aggregate acceptance rate is computed across the two pools because they answer different questions: branch-correct workflow execution versus command-conditioned constraint updating. The distinction between the two pools is maintained in Table 2.

The 48-record dynamic retain/replan workflow evaluates whether the executor follows the correct branch at each checkpoint. Stage 1 and Stage 2 reproduced all dynamic references. In Stage 3, MiMo v2.5 accepted 48/48 records, MiniMax M2.5 accepted 43/48 records, and Claude Haiku 4.5 accepted 41/48 records. All accepted records satisfied hard-constraint and downstream-release checks. Rejected records were caused by protocol-level failures, such as wrong tool order or missing required tool calls, rather than infeasible reservoir operation.

The 40-record command-intervention subset evaluates mid-event operator instructions. The command matrix covers release-cap adjustment, terminal-target lowering, target-deadline compression, and conservative risk buffer. The deterministic workflow accepted all 40 command records, confirming that all commands in this batch are feasible executions. In Stage 3, MiMo v2.5 accepted 38/40 command records, MiniMax M2.5 accepted 39/40, and Claude Haiku 4.5 accepted 40/40. No hard-constraint or downstream-release violations were detected.

The representative event 2024061623 illustrates how command interventions modify remaining-horizon operation. A release-cap command at the inflow-peak checkpoint remains feasible under the constrained release plan. A conservative risk-buffer command at the same checkpoint imposes a stricter upper-level target and produces a different release trajectory. These examples show that the workflow-constrained implementation can translate distinct operator intentions into different constrained release plans while keeping the final decision auditable.

The dynamic retain/replan pool and the command-intervention pool should be read as complementary tests. The retain/replan pool tests branch discipline: whether the agent follows the scenario-provided route and avoids prohibited calls in retain stages. The command-intervention pool tests instruction translation: whether the agent can convert a mid-event operational command into updated constraints and a new auditable execution record. Combining them in one results section reflects their shared mid-event character, but the record counts remain separate throughout the reporting.

The higher rejection frequency in the 48-record dynamic retain/replan pool for MiniMax and Claude also indicates that conditional workflows are more difficult than linear static workflows. In a linear workflow, the agent can follow a fixed chain. In the dynamic workflow, the agent must choose between two valid chains and avoid tools that are valid in one branch but invalid in the other. This is precisely the kind of workflow-control risk that the skill and validator are designed to expose.

Figure 5 shows representative dynamic retain/replan and command-intervention operation. Vertical markers indicate decision checkpoints. Release and water-level trajectories after command injection show how the workflow updates the remaining operation under different instructions.

**Figure 5. Dynamic retain/replan and command-intervention operation under representative flood events.**  
`[TO FILL: final dynamic figure. Suggested panels: retain/replan checkpoints, command checkpoints, release paths, reservoir-level paths, upper operating level, and accepted/rejected audit labels. Clearly label that the 48 retain/replan records and 40 command records are separate pools.]`

**Table 2. Static and dynamic Stage 3 results.**

| Evaluation block          | Records per executor | MiMo v2.5 | MiniMax M2.5 | Claude Haiku 4.5 | Hard viol. | Downstream viol. |
| ------------------------- | --------------------:| ---------:| ------------:| ----------------:| ----------:| ----------------:|
| Main static workflow      | 41                   | 41/41     | 41/41        | 41/41            | 0          | 0                |
| Static instruction subset | 96                   | 93/96     | 87/96        | 94/96            | 0          | 0                |
| Dynamic retain/replan     | 48                   | 48/48     | 43/48        | 41/48            | 0          | 0                |
| Command intervention      | 40                   | 38/40     | 39/40        | 40/40            | 0          | 0                |

The distinction between accepted execution and feasible command handling is worth noting. The command-intervention records were designed so that the deterministic tools could find feasible plans for all commands. Therefore, a rejected Stage 3 command record does not indicate that the command was impossible. It indicates that the agent failed to complete the required auditable procedure. This distinction preserves the interpretation of the command experiment as an agent-workflow test rather than a feasibility benchmark.

## 4.3 Rolling forecast-triggered operation and forecast-error audit

The rolling workflow evaluates fixed-forecast operation under 3 h observed-state updates. The rolling oracle contains 373 checks across 10 forecast-enabled events. Among these checks, 142 triggered LLM-called replanning and 231 retained the current plan as deterministic audit rows. The trigger-only design therefore reduced LLM calls by:

\[
R_{\mathrm{call}} = \frac{231}{373} = 61.9\%.
\]

This reduction does not remove audit coverage. All non-trigger checks are still recorded as deterministic retain rows.

In Stage 3, MiMo v2.5 accepted 368/373 rolling records, MiniMax M2.5 accepted 367/373, and Claude Haiku 4.5 accepted 370/373. All three executors accepted 231/231 retain rows. Rejected records were concentrated in LLM-called decisions and were associated with evidence binding or protocol failures. No hard-constraint or downstream-release violations occurred.

Figure 6 shows representative rolling forecast-triggered operation. Each row compares observed inflow, fixed forecast, rolling release, reservoir level, replan markers, and retain markers. The examples show that the workflow can combine full audit coverage with selective LLM-agent replanning. Events with repeated forecast-error or state-risk triggers show denser replan markers, while stable periods are handled through deterministic retain rows.

The forecast-error audit further evaluates degraded-forecast behavior. Five perturbed forecast cases produce 51 audit stages. The perturbations include lagged, lead, over-peak, under-peak, and mixed mild forecast-error patterns. Observed inflow, observed level, state propagation, and validation remain tied to the real event records. Stage 2 accepted 51/51 audit stages. In Stage 3, MiMo v2.5, MiniMax M2.5, and Claude Haiku 4.5 each accepted 51/51 stages, with zero hard-constraint violations. The trigger distribution includes scheduled checks, relative forecast-error triggers, absolute forecast-error triggers, and state-risk triggers, confirming that all trigger categories are exercised in the audit.

The rolling results show two forms of auditability. First, every check receives a record, regardless of whether the LLM is called. This prevents the absence of a replan from becoming an unlogged decision. Second, LLM-called stages are subjected to the same reference-binding and schema checks as static and dynamic records. The retain rows are therefore not missing data; they are deterministic audit rows that document why the existing plan was carried forward.

The 61.9% call reduction is not presented as a universal efficiency gain. It depends on the trigger thresholds, forecast quality, event duration, and state trajectory. Its role in this paper is to show that a rolling LLM-agent workflow can be designed without requiring the LLM to participate in every time step. This is relevant for cost control, context-length management, and operational robustness, especially when long events contain many low-risk periods.

The forecast-error audit complements the real-forecast rolling experiment. The original rolling forecasts are relatively accurate in several events, so the perturbed audit creates a more explicit test of trigger behavior. Because only the forecast column is perturbed, the audit remains anchored to real observed inflow and water-level records. This avoids turning the experiment into a fully synthetic flood simulation while still exposing the workflow to degraded forecast timing and magnitude.

**Figure 6. Rolling forecast-triggered operation and forecast-error audit.**  
`[TO FILL: final rolling figure. Suggested layout: left panels for real-forecast rolling cases with observed inflow, fixed forecast, release, level, replan markers, and retain markers; right or lower panels for forecast-error audit cases: lag, lead, over-peak, under-peak, and mixed mild perturbation.]`

**Table 3. Rolling operation and forecast-error audit results.**

| Evaluation block                     | Records | MiMo v2.5 | MiniMax M2.5 | Claude Haiku 4.5 | Key audit result                                       | Hard viol. | Downstream viol. |
| ------------------------------------ | -------:| ---------:| ------------:| ----------------:| ------------------------------------------------------ | ----------:| ----------------:|
| Rolling forecast-triggered operation | 373     | 368/373   | 367/373      | 370/373          | 231/231 retain rows accepted; 61.9% LLM-call reduction | 0          | 0                |
| Forecast-error audit                 | 51      | 51/51     | 51/51        | 51/51            | All trigger categories observed                        | 0          | 0                |

The rolling and forecast-error results together support a conservative interpretation. The proposed methodology does not claim to improve forecast accuracy, nor does it replace hydrological forecasting. The framework uses forecast deviations as triggers for tool-grounded replanning. When a forecast remains close to observations, the workflow can retain the current plan and record the retain decision. When the forecast departs from observations or the state approaches the upper operating level, the workflow triggers replanning and requires a new evaluation reference. This design turns forecast uncertainty into a workflow-control signal rather than asking the LLM to infer hydrological risk from text.

## 4.4 Tools + workflow skills / full MCP ablation and executor failure taxonomy

The ablation experiment tests whether auditable generative-AI-assisted execution depends on tool access alone or on the combination of tools, workflow skills, and validation. The text-only setting produced formatted numeric plans and schema-like outputs, but no record could be accepted because no tool-returned evaluation reference existed. It therefore achieved 0/40 auditable accepted records.

The tools-only setting improved computational grounding but remained vulnerable to protocol and evidence-binding failures. It accepted 27/32 records. The rejected records involved wrong tool order, missing or invalid evaluation references, or schema-related failures. This result indicates that tool access alone is not sufficient for reliable reservoir-operation execution.

The tools + workflow skills / full MCP setting accepted 40/40 records. Tool-order validity, evaluation-reference validity, schema validity, and hard-safety checks all reached 100% in this ablation setting. The result supports the role of workflow skills as execution contracts that constrain the LLM agent to a verifiable tool chain.

Across the 462-record main workflow validation set, MiMo v2.5 accepted 457/462 records, MiniMax M2.5 accepted 451/462, and Claude Haiku 4.5 accepted 452/462. The rejected records were concentrated in protocol-level failure modes: wrong tool order, missing required tools, and missing evaluation references. No accepted or rejected record produced a hard-constraint or downstream-release violation.

The failure taxonomy supports the interpretation that residual Stage 3 failures are mostly interface-level and protocol-level problems. Wrong-tool-order failures indicate that the executor departed from the skill-defined process. Missing-required-tool failures indicate incomplete execution. Missing-evaluation-reference failures indicate that the final answer could not be bound to a valid current-stage result. These failures are operationally meaningful because they would prevent an engineer from reconstructing the basis of the decision after the event.

The ablation also clarifies why schema validity alone is insufficient. The text-only setting can produce structured-looking outputs, but without tool evidence those outputs are not auditable. The tools-only setting can produce real computations, but without a workflow contract it can still produce incomplete or incorrectly referenced records. The full configuration combines computation and protocol, which is why it is the appropriate PyResOps setting.

Figure 7 summarizes the ablation and failure taxonomy. The figure is intended to provide the main evidence chain for the paper's methodological contribution: text-only output is not auditable, tools alone reduce but do not eliminate protocol failures, and tools + workflow skills / full MCP provide the most reliable execution contract under the tested settings.

**Figure 7. Tools/skills ablation and executor failure taxonomy.**  
`[TO FILL: final summary figure. Suggested panels: ablation acceptance bars for text-only, tools-only, tools+skills; cross-executor acceptance for the 462-record set; stacked failure taxonomy by executor: wrong tool order, missing required tool, missing evaluation reference; note zero hard/downstream violations.]`

**Table 4. Tools/skills ablation and main workflow failure taxonomy.**

| Block                    | Metric                       | MiMo v2.5 / variant | MiniMax M2.5 / variant | Claude Haiku 4.5 / variant |
| ------------------------ | ---------------------------- | -------------------:| ----------------------:| --------------------------:|
| Main 462-record workflow | Accepted                     | 457/462             | 451/462                | 452/462                    |
| Main 462-record workflow | Wrong tool order             | 0                   | 4                      | 7                          |
| Main 462-record workflow | Missing required tool        | 0                   | 3                      | 3                          |
| Main 462-record workflow | Missing evaluation reference | 5                   | 4                      | 0                          |
| Ablation                 | Text-only                    | 0/40                | -                      | -                          |
| Ablation                 | Tools-only                   | 27/32               | -                      | -                          |
| Ablation                 | Tools + skills / full MCP    | 40/40               | -                      | -                          |

Overall, the results indicate that the main value of the methodology lies in making the boundary of acceptable agent behavior explicit. Static, dynamic, command, and rolling tasks all reached zero hard-constraint and downstream-release violations, but acceptance still varied across executors and workflows. This shows that safety-relevant evaluation cannot stop at hydrological feasibility. The workflow must also verify that the agent produced the decision through the required evidence path. The tools/skills ablation provides the clearest mechanism-level support for this conclusion: without tools there is no computational evidence, and without skills there is no reliable procedure for using that evidence.

---

# 5. Discussion

## 5.1 Generative AI as a governed operational interface for reservoir flood management

The results support a bounded and governed role for generative AI in reservoir flood-operation decision support. In the 462-record main workflow set, the three LLM executors accepted 457/462, 451/462, and 452/462 records, respectively, with no hard-constraint or downstream-release violations. This result provides evidence that LLM agents can participate in reservoir-operation workflows when their role is restricted to instruction interpretation, workflow coordination, and structured reporting, while hydrological computation and safety checks remain delegated to deterministic tools and external validators. The main implication is that generative AI can serve as an operational interface between human instructions and verified computational workflows, rather than as a substitute for reservoir-operation models or human decision authority.

This role boundary is important for sustainable reservoir management because flood-operation decisions must be made under time pressure, forecast uncertainty, and downstream safety constraints. The accepted records indicate that natural-language operational intent can be translated into executable and auditable workflow records without allowing the LLM to become the source of numerical authority. Conversely, rejected records show that a plan cannot be treated as operationally acceptable if its evidence trail is incomplete, even when the underlying numerical operation may be feasible. This distinction is relevant to climate-resilient water management, where decision-support systems need to remain adaptive while preserving traceability and accountability during extreme events.

The three-stage validation design further clarifies how such systems should be developed. Stage 1 established that the deterministic reservoir-operation tasks were executable by direct code; Stage 2 verified that tool-mediated workflows reproduced the deterministic references; and Stage 3 tested whether LLM executors could coordinate the verified workflows without violating protocol or evidence-binding requirements. This separation reduces the risk of conflating deterministic-kernel errors, tool-interface errors, and agent-execution errors. It also provides a practical development route for safety-relevant water-management AI systems: deterministic computation should be validated first, tool-mediated execution second, and LLM-agent coordination only after these layers are stable.

## 5.2 Workflow governance and fail-closed validation for water-safety decision support

The ablation experiment provides the clearest mechanism-level evidence for the proposed methodology. Text-only generation produced formatted numeric plans and schema-like outputs, but no record could be accepted because no tool-returned evaluation reference existed. This shows that structured-looking text is not sufficient for auditable reservoir operation. Without computational evidence, the final answer cannot become an operation record.

Tools-only execution improved computational grounding but remained vulnerable to protocol and evidence-binding failures. The agent had access to the necessary computations, but tool availability did not ensure that the tools were called in the correct order, that required steps were completed, or that the final payload cited the current evaluation result. This result is important for generative AI adoption in water operations because it separates tool access from workflow reliability. A tool-enabled LLM is not automatically an auditable decision-support system.

The tools combined with workflow skills and external validation accepted all records in the ablation subset. This does not imply that the implementation is universally reliable, but it supports the mechanism evaluated in this study: deterministic tools, workflow protocols, evidence binding, and fail-closed validation jointly reduce the space of acceptable agent behavior. Under this design, the system does not need to trust the LLM's wording. It accepts only records that can be traced to a valid tool execution and constraint check.

This finding distinguishes the present study from much of the existing AI and LLM literature in water management. Traditional rule curves, optimization models, and MPC formulations provide hydrologically meaningful release computations, but they usually do not address how free-text operator instructions should be converted into auditable LLM-agent workflows. Recent LLM and LLM-agent studies in water engineering have highlighted opportunities for data integration, knowledge support, model interaction, and decision assistance, but fewer studies have operationally tested how agent outputs should be constrained, verified, and rejected in a real reservoir-operation workflow. The present results indicate that workflow governance is not an implementation detail; it is a core requirement for safe generative-AI adoption in water-safety decision support.

## 5.3 Water-operation implications across static, dynamic, command, and rolling workflows

The static results indicate that the deterministic operation layer can produce instruction-conditioned release plans that remain within the evaluated safety constraints. In the 492-record deterministic static matrix, all records were accepted in Stage 1 and Stage 2, confirming that the release-family and operation-interval combinations were executable under the configured scenario constraints. The Stage 3 stratified subset then showed that LLM executors could reproduce most of these instruction-conditioned workflows, although acceptance varied across executors. At the operation-metric level, the accepted static records maintained water levels within the scenario-imposed upper operating level, with the maximum simulated level reaching the 160.0 m threshold and no hard-constraint or downstream-release violation. These results indicate that the workflow can translate operational instructions into feasible release trajectories while preserving the audit trail required for post-event inspection.

The dynamic and command-intervention results show that mid-event adaptation is more demanding than linear full-horizon planning. Rejections in the dynamic retain/replan workflow were concentrated in protocol-level failures such as wrong tool order and missing required tool calls, rather than in hydrological constraint violations. This suggests that the main difficulty for LLM agents is not recognizing that reservoir-operation tools are needed, but maintaining the correct branch discipline when different operational states require different tool chains. The command-intervention subset further shows that mid-event operator instructions, including release-cap adjustment, terminal-target lowering, deadline compression, and conservative risk buffering, can be converted into updated constraints and remaining-horizon execution records. Because all commands in this subset were feasible under deterministic execution, the rejected Stage 3 records are best interpreted as auditability failures rather than reservoir-feasibility failures.

The rolling workflow provides the strongest connection to real-time and adaptive water management. Among 373 rolling checks, 231 were retained as deterministic audit rows and 142 triggered LLM-called replanning, corresponding to a 61.9% reduction in LLM calls while preserving complete audit coverage. This reduction should not be interpreted as a universal computational-efficiency gain because it depends on trigger thresholds, forecast quality, and event characteristics. Its water-management significance is that selective generative-AI participation can coexist with continuous operational traceability. Stable periods can be documented through deterministic retain rows, while state-risk, forecast-error, or scheduled-check triggers can activate replanning with a new evaluation reference.

The forecast-error audit further supports this interpretation. Forecast deviations were treated as workflow triggers rather than as risks to be inferred directly by the LLM from text. This design is important because hydrological risk assessment should remain tied to observed states, forecast-error thresholds, and deterministic simulation rather than to model-generated reasoning alone. The 51-stage forecast-error audit was accepted by all three executors, with zero hard-constraint violations, indicating that the workflow can remain auditable under controlled forecast degradation. Taken together, the static, dynamic, command, and rolling results suggest that the practical value of the methodology lies in combining adaptive interaction with traceable and constraint-safe execution, rather than in replacing established reservoir-operation models.

## 5.4 Scope, development implications, and future intelligent water systems

Several boundaries define the scope of the present validation. The experiments were conducted on a single reservoir, Tankeng Reservoir, using 41 retained flood events and the operating constraints configured for this case study. The results support the feasibility of workflow-constrained generative-AI-assisted execution under the evaluated single-reservoir setting, but they do not establish general operational performance across reservoirs with different storage-elevation curves, outlet-capacity functions, downstream protection standards, dispatch rules, or flood-season control policies. The scenario-imposed upper operating level of 160.0 m and the uniform downstream release constraint of 3000 m³/s are case-specific validation settings.

The present study also does not claim superiority over historical operation, rule-curve operation, or MPC-based release optimization. Its contribution lies in the operational interface and verification layer: how generative AI can translate natural-language operational intent into traceable, evidence-bound, and rejectable decision records. A future hydrological-performance benchmark should compare the resulting release trajectories with historical operation, rule-curve policies, and optimization or MPC baselines using metrics such as peak release reduction, maximum water level, terminal water-level deviation, spillway use, and downstream risk exposure. Such comparisons would complement the present workflow-audit evaluation and help quantify how the proposed decision-support pathway affects water-management outcomes.

The evaluated command-intervention subset contains feasible operator commands. The workflow definition includes structured rejection for infeasible or unsafe commands, but the current command matrix mainly tests command parsing, constraint updating, constrained execution, and evidence binding. A dedicated infeasible-command and unsafe-command benchmark is needed to evaluate whether the same fail-closed mechanism can reliably reject instructions that violate physical, downstream, or policy constraints. Similarly, the forecast-error audit uses controlled perturbations of the forecast inflow column while keeping observed inflow, observed water level, state propagation, and validation tied to real event records. More severe forecast bias, missing forecast updates, multi-source forecast disagreement, and communication delays remain outside the present validation.

The staged validation design has a practical implication for developing generative-AI-assisted water-operation tools. Before introducing an LLM executor, the deterministic operation kernel should be validated by direct code execution, and the tool-mediated workflow should then be checked against deterministic references. Only after these layers are stable should LLM-agent execution be evaluated. This staged design reduces the risk of attributing kernel or tool-interface errors to the LLM executor and provides a reproducible route for developing safety-relevant agentic decision-support systems.

Future extensions should move in two directions. The first is multi-reservoir or reservoir-group operation, where upstream and downstream reservoirs interact through travel time, storage allocation, routing effects, flood-control priorities, and competing operational objectives. Such systems would require workflow protocols for inter-reservoir communication, joint constraint checking, conflict resolution, authority assignment, and basin-level audit records. The second direction is multi-agent reservoir-operation systems, where reservoir-level agents, basin-level supervisory agents, forecasting or routing tool agents, and human operators interact under shared workflow protocols and fail-closed validation. These extensions would test whether the present single-reservoir methodology can be expanded into coordinated basin-scale intelligent water systems without weakening traceability and human oversight.

In the context of sustainable water management, these extensions are not only technical. Climate change is increasing the need for coordinated flood-risk management, resilient infrastructure operation, and accountable allocation of water-related risks across upstream and downstream regions. Workflow-constrained generative AI may support this transition only when its flexibility is combined with basin-scale constraint validation, transparent responsibility assignment, and human authority over final operational decisions.

# 6. Conclusions

This paper proposed a workflow-constrained generative AI methodology for auditable single-reservoir flood-operation decision support and instantiated it as PyResOps. The methodology embeds LLM agents into the reservoir-operation business process as instruction interpreters and workflow coordinators, while deterministic tools perform hydrological computation, release simulation, constraint checking, and evaluation. A decision record is accepted only when the required workflow is completed, the final payload is bound to the current tool-returned evaluation result, schema validation succeeds, and hard operational constraints are satisfied.

The case study on Tankeng Reservoir evaluated the methodology on 41 retained flood events. The 462-record main workflow set was executed through direct-code validation, tool-mediated workflow validation, and LLM-agent execution. MiMo v2.5, MiniMax M2.5, and Claude Haiku 4.5 accepted 457/462, 451/462, and 452/462 records, respectively, with zero hard-constraint and downstream-release violations. The 492-record static instruction matrix confirmed deterministic command and interval feasibility, and the 96-row Stage 3 subset tested executor compliance under stratified instruction conditions. The rolling workflow contained 373 checks and reduced LLM calls by 61.9% while preserving deterministic audit rows. The 51-stage forecast-error audit was accepted by all three executors.

The results show that different workflow types expose different agent risks. Static planning mainly tests instruction and interval compliance. Dynamic operation tests branch discipline and prohibited-call handling. Command intervention tests whether mid-event operator instructions can be converted into updated constraints and auditable execution. Rolling operation tests whether triggered replanning and deterministic retain rows can coexist in one event record. The failure taxonomy indicates that remaining errors are concentrated in protocol adherence and evidence binding rather than in hydrological constraint violations.

The ablation study clarifies the role of tools and workflow skills. Text-only generation produced no auditable accepted records because no tool-returned evaluation reference existed. Tools-only execution improved grounding but remained vulnerable to tool-order, missing-tool, and evidence-binding failures. Tools plus workflow skills achieved full acceptance in the ablation subset. This supports the central claim that tool access alone is insufficient for safety-relevant generative-AI-assisted reservoir operation. A reliable workflow must define how tools are used and must validate that the final decision is tied to current tool evidence.

The proposed methodology should not be interpreted as a new reservoir-optimization algorithm or as a claim of superiority over historical operation. Its contribution is an auditable execution and verification pattern for introducing generative AI into single-reservoir flood-operation decision support. Broader reservoir types, larger event archives, infeasible-command tests, real-time forecasting failures, multi-reservoir operation, and multi-agent coordination remain necessary before operational deployment. Under the evaluated setting, the study provides evidence that LLM agents can support safety-relevant water-operation workflows when their flexibility is bounded by deterministic tools, explicit workflow protocols, evidence binding, and fail-closed validation.

---

# Data and Code Availability

The PyResOps source code, experiment configurations, workflow skill protocols, validation scripts, and processed event records are available in the project repository. Repository URL: https://github.com/chooron/PyResOps. Raw hydrological records are subject to reservoir authority data-sharing restrictions and are not publicly released. Processed or anonymized records used for reproducibility are provided where permitted.

---

# Appendix A. Tankeng Reservoir background and parameters

This appendix reports the verified reservoir background parameters used to describe the Tankeng Reservoir case study. Engineering background parameters and experimental constraints are distinguished to avoid mixing physical reservoir attributes with scenario-imposed validation settings.

## A.1 Reservoir overview

- Reservoir name: Tankeng Reservoir / Tankeng Hydropower Station Reservoir.
- Province/country: Zhejiang Province, China.
- River basin/location: lower Xiaoxi River, Oujiang River basin; Qingtian County, Zhejiang Province.
- Main functions: hydropower generation, flood control, ecological-flow maintenance, and other comprehensive reservoir benefits.
- Catchment area above dam site: 3330 km².
- Total storage capacity: 4.19 × 10⁹ m³.
- Normal storage level: 160.00 m.
- Storage capacity at normal storage level: 3.52 × 10⁹ m³.
- Flood-control storage capacity: 3.50 × 10⁸ m³.
- Dead water level: 120.00 m.
- Regulating storage capacity: 2.126 × 10⁹ m³.
- Installed hydropower capacity: 604 MW.
- Mean annual hydropower generation: 1.023 × 10⁹ kW·h.
- Main flood season: April 15 to October 15. The Meiyu flood season is generally April 15 to June 30, followed by a transition period from July 1 to July 15 and the typhoon flood season from July 16 to October 15.

Source basis: the document gives the dam-site catchment area as 3330 km², total installed capacity as 604 MW, total storage as 4.19 billion m³, normal pool level as 160.00 m, flood-control storage as 350 million m³, and the flood-season division as April 15–October 15. :contentReference[oaicite:0]{index=0}

## A.2 Water-level references

| Parameter                                             | Value    | Role in this paper                           | Notes                                                                               |
| ----------------------------------------------------- | --------:| -------------------------------------------- | ----------------------------------------------------------------------------------- |
| Typhoon-season flood limit level                      | 156.50 m | Study-site background                        | Official typhoon-season limit and starting regulation level.                        |
| Meiyu-season flood limit level / normal storage level | 160.00 m | Study-site background and scenario reference | Also used as the scenario-imposed upper operating level in the validation settings. |
| Scenario-imposed upper operating level                | 160.00 m | Experimental hard operating threshold        | Used in validation scenarios; should be described as an experimental constraint.    |
| Flood-control high water level                        | 161.50 m | Study-site background                        | Corresponds to P = 5% / 20-year flood-control level.                                |
| Design flood level                                    | 165.87 m | Study-site background                        | Not used as the experimental hard operating threshold.                              |
| Check flood level                                     | 169.15 m | Study-site background                        | PMF check flood level.                                                              |
| Dead water level                                      | 120.00 m | Study-site background                        | Lower storage reference level.                                                      |

The verified flood-control water levels are: Meiyu-season limit and starting level 160.00 m, typhoon-season limit and starting level 156.50 m, flood-control high water level 161.50 m, design flood level 165.87 m, and check flood level 169.15 m. :contentReference[oaicite:1]{index=1}

## A.3 Release-capacity and downstream constraint

| Item                                                | Value      | Role                                        |
| --------------------------------------------------- | ----------:| ------------------------------------------- |
| Spillway maximum discharge capacity                 | 14335 m³/s | Background engineering attribute            |
| Flood-discharge tunnel maximum discharge capacity   | 1729 m³/s  | Background engineering attribute            |
| Maximum discharge at design flood level             | 12784 m³/s | Background engineering attribute            |
| Maximum discharge at check flood level              | 16091 m³/s | Background engineering attribute            |
| Flood-control high-water-level limited release      | 6361 m³/s  | Background engineering attribute            |
| Downstream Qingtian/Hecheng safe discharge          | 14000 m³/s | Official downstream flood-control reference |
| Uniform downstream release constraint in this paper | 3000 m³/s  | Experimental validation constraint          |

The main text should not use the reservoir’s design discharge capacity or outlet capacity as the downstream margin metric. In the validation scenarios, the downstream release constraint is fixed at 3000 m³/s. The engineering document instead reports larger physical and flood-control discharge references, including a spillway maximum discharge of 14335 m³/s, a flood-discharge tunnel maximum of 1729 m³/s, and a downstream Hecheng-section safe discharge of 14000 m³/s. :contentReference[oaicite:2]{index=2}

---

# Appendix B. Workflow skill protocols

## B.1 Static workflow skill

Required chain:

```text
prepare_event
  -> optimize_release_plan
  -> simulate_release_plan
  -> evaluate_release_plan
  -> final answer
```

Rules:

- Use the specified release family.
- Use the specified operation interval.
- Do not change the operator-specified release family.
- The final `evaluation_reference` must match the current `evaluate_release_plan` output.
- The final payload must include decision type, selected plan id, safety status, instruction status, evaluation reference, and one-sentence explanation.

## B.2 Dynamic workflow skill

Workflow types:

- `dynamic_replan`: full chain.
- `dynamic_retain`: short chain that reuses the prior plan.

Required chain for `dynamic_replan`:

```text
prepare_event
  -> optimize_release_plan
  -> simulate_release_plan
  -> evaluate_release_plan
  -> final answer
```

Required chain for `dynamic_retain`:

```text
simulate_release_plan
  -> evaluate_release_plan
  -> final answer
```

Branch rule:

- `initial` or `infeasible_or_deviation` -> use `dynamic_replan`.
- `plan_still_feasible` or `prior_violation` -> use `dynamic_retain`.

Rules:

- At T0, always replan.
- For retain stages, do not call `prepare_event` or `optimize_release_plan`.
- For replan stages, call the full chain exactly once.
- Do not reuse evaluation references from prior checkpoints.

Final answer format:

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

## B.3 Rolling workflow skill

Required logic:

1. Update observed state at the current 3 h check.
2. Evaluate trigger conditions.
3. If a trigger fires, execute the full replan chain.
4. If no trigger fires, retain the current plan and record a deterministic audit row.
5. Submit a final payload with the current-stage evaluation reference.

Trigger categories:

- State-risk trigger.
- Absolute forecast-error trigger.
- Relative forecast-error trigger.
- Scheduled 12 h check.
- Retain plan.

Rules:

- A retain row must still be auditable.
- LLM-called replanning is required only when a trigger fires.
- Forecast-error audit perturbs only forecast inflow, not observed inflow or observed level.

---

# Appendix C. Release-family definitions

PyResOps registers six paper-aligned base release families in
`pyresops.modules.registry.BASE_RELEASE_MODULE_REGISTRY`. The optimizer may
select among these families, or an instruction-conditioned scenario may require
one family through `requested_module_type`. Older mixed module types
(`flexible_release`, `level_tracking`, `external_constraint`, `inflow_driven`,
`storage_driven`, and `combined_driven`) are rejected by the registry.

Let `I_t` denote the forecast inflow used by the release module at step `t`,
`S_t` the current storage, `C` the total reservoir capacity, and
`r_t = S_t / C` the storage ratio. Storage-conditioned families can use either
raw storage (`storage`) or storage ratio (`storage_ratio`); the optimization
path uses `storage_ratio`.

| Release family                     | Module type                          | Outflow rule                                                                                                            | Required parameters                                                                                                                                                                                   | Optimization parameterization                                                                                                                                                                      |
| ---------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Constant release                   | `constant_release`                   | `Q_t = target_release`                                                                                                  | `target_release >= 0`                                                                                                                                                                                 | One bounded scalar over `[min_release, max_release]`.                                                                                                                                              |
| Inflow piecewise-constant release  | `inflow_piecewise_constant_release`  | `Q_t = release_values[bisect_right(breakpoints, I_t)]`                                                                  | Strictly increasing `breakpoints`; non-negative `release_values`; `len(release_values) = len(breakpoints) + 1`.                                                                                       | Breakpoints are the one-third and two-third inflow quantiles from the event forecast. The optimizer solves one release value per bin and projects the vector to a non-decreasing clipped sequence. |
| Inflow linear release              | `inflow_linear_release`              | `Q_t = max(0, slope * I_t + intercept)`                                                                                 | `slope >= 0`; `intercept` may be positive or negative.                                                                                                                                                | The optimizer solves low- and high-inflow output anchors over `[min_release, max_release]`, orders them, and decodes them to `slope` and `intercept` over `[inflow_min, inflow_max]`.              |
| Storage piecewise-constant release | `storage_piecewise_constant_release` | `x_t = S_t` or `r_t`; `Q_t = release_values[bisect_right(breakpoints, x_t)]`                                            | `metric in {storage, storage_ratio}`; strictly increasing `breakpoints`; non-negative `release_values`; `len(release_values) = len(breakpoints) + 1`.                                                 | The optimization path fixes `metric = storage_ratio`, uses breakpoints `[0.45, 0.75]`, and solves three non-decreasing clipped release values.                                                     |
| Storage nonlinear release          | `storage_nonlinear_release`          | `x_t = S_t` or `r_t`; `Q_t = interp(x_t, control_points, release_values)`                                               | `metric in {storage, storage_ratio}`; strictly increasing `control_points`; non-negative `release_values`; `len(control_points) = len(release_values)`.                                               | The optimization path fixes `metric = storage_ratio`, uses control points `[0.0, 0.5, 0.75, 1.0]`, and solves four non-decreasing clipped release values.                                          |
| Joint driven release               | `joint_driven_release`               | `i = bisect_right(inflow_breakpoints, I_t)`; `j = bisect_right(storage_breakpoints, x_t)`; `Q_t = release_matrix[i][j]` | `storage_metric in {storage, storage_ratio}`; strictly increasing inflow and storage breakpoints; non-negative `release_matrix` with shape `[len(inflow_breakpoints)+1][len(storage_breakpoints)+1]`. | The optimization path fixes `storage_metric = storage_ratio`, uses the event inflow quantile breakpoints and storage breakpoints `[0.6, 0.8]`, and solves a monotone clipped release matrix.       |

---

# Appendix D. Implementation details and tool inventory

## D.1 Codebase structure

```text
pyresops/
  __init__.py
  cli.py
  server.py
  core/
    action_resolver.py
    engine.py
    family_optimizer.py
    hydraulics.py
    orchestrator.py
    scenario_time.py
    validator.py
  domain/
    constraint.py
    decision.py
    dispatch.py
    forecast.py
    module.py
    objective.py
    policy.py
    program.py
    reservoir.py
    result.py
    rule.py
  modules/
    base.py
    registry.py
    constant_release.py
    inflow_linear_release.py
    inflow_piecewise_constant_release.py
    storage_piecewise_constant_release.py
    storage_nonlinear_release.py
    joint_driven_release.py
  services/
    dispatch_contract_compiler.py
    evaluation.py
    explanation.py
    optimization.py
    program.py
    rolling_ops.py
    simulation.py
    snapshot.py
  tools/
    common.py
    evaluation_tools.py
    explanation_tools.py
    plugin_tools.py
    program_tools.py
    rolling_ops_tools.py
    simulation_tools.py
    snapshot_tools.py
  agents/
    config_loader.py
    contracts.py
    model_builder.py
    prompts.py
    runner.py
    runtime.py
    specs.py
    tool_bundle.py
  constraints/
    base.py
    factory.py
    loader.py
    registry.py
    builtin/
      downstream.py
      ecology.py
      flow.py
      level.py
      ramp.py
  metrics/
    base.py
    builtin.py
    registry.py
  plugins/
    base.py
    builtin.py
    loader.py
    manager.py
    models.py
    orchestrator.py
    registry.py
    resolver.py
  providers/
    base.py
    builtin.py
    models.py
    registry.py
  rules/
    actions.py
    base.py
    builtin.py
    context.py
    expression.py
    factory.py
    loader.py
    registry.py
  storage/
    repository.py

experiments/
  config/
    stage1_baseline.yml
    stage1_instruction_static.yml
    stage1_dynamic_command_intervention.yml
    stage2_workflow.yml
    stage2_instruction_static.yml
    stage2_dynamic_command_intervention.yml
    stage3_llm_mcp.yml
    stage3_instruction_static.yml
    stage3_dynamic_command_intervention.yml
    real_events.yml
    paper_validation.yml
  data_adapters/
    preprocessing.py
    real_events.py
  workflows/
    contracts.py
    dynamic.py
    rolling.py
    static.py
  validation/
    deterministic.py
    manifest.py
    reporting.py
    results.py
    runner.py
    scenarios.py
  paper_validation/
    command_challenge.py
    config.py
    dataset.py
    execution.py
    mcp_audit.py
    mcp_skill_runner.py
    orchestrator.py
    runners.py
    schema.py
    tooling.py
    utils.py
    wrongtest_runner.py
    skills/
  stage1/
    checkpoints.py
    classify.py
    constraints.py
    downstream.py
    dynamic_command_intervention.py
    instruction_static.py
    metrics.py
    reporting.py
    runner.py
  stage2/
    comparator.py
    deterministic_runner.py
    dynamic_command_intervention_workflow.py
    instruction_static_workflow.py
    reporting.py
    workflows.py
  stage3/
    comparator.py
    dynamic_command_runner.py
    fail_closed_validator.py
    instruction_static_runner.py
    llm_runner.py
    mcp_tools.py
    payload_schema.py
    reporting.py
    session_trace.py
    tool_registry.py
    prompts/
    instruction_static_prompts/
    dynamic_command_prompts/
  run_stage1_baseline.py
  run_stage1_instruction_static.py
  run_stage1_dynamic_command_intervention.py
  run_stage2_workflow.py
  run_stage2_instruction_static.py
  run_stage2_dynamic_command_intervention.py
  run_stage3_llm_mcp.py
  run_stage3_instruction_static.py
  run_stage3_instruction_static_multimodel.py
  run_stage3_dynamic_command_intervention.py

data/
  flood_event/
  withpred/
  wrongtest/
  processed/flood_event/

docs/paper/
  pyresops_methodology_reframed_draft.md
  figures/

tests/
  test_core/
  test_services/
  test_modules/
  test_experiments/
  test_integration/
```

## D.2 Runtime settings

| Item                             | Value                                                                                                                                                                                          |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python version                   | Python 3.14.0 in the inspected environment; project requirement is >=3.11                                                                                                                      |
| MCP server mode                  | Local FastMCP subprocess over stdio; command: python -m pyresops.server                                                                                                                        |
| Agno version                     | agno==2.6.5                                                                                                                                                                                    |
| MCP SDK version                  | mcp==1.26.0; server wrapper fastmcp==3.2.0                                                                                                                                                     |
| MiMo temperature / max tokens    | mimo_v25: temperature 0, max tokens 8192                                                                                                                                                       |
| MiniMax temperature / max tokens | minimax_m2_5_free: temperature 0, max tokens 8192                                                                                                                                              |
| Claude temperature / max tokens  | claude_haiku_4_5: temperature 0, max tokens 4096                                                                                                                                               |
| Retry policy                     | max_attempts=1; each LLM/MCP execution records attempts: 1. No stochastic retry; selected protocol failures may trigger one bounded repair rerun, otherwise fail-closed rejection              |
| Logging format                   | JSONL trace records plus CSV result tables and Markdown summaries; logs include tool-call sequence, final payload, available/final evaluation references, validation flags, and failure reason |

## D.3 Core tool inventory

| Tool                      | Purpose                                                               | Required in workflow                   |
| ------------------------- | --------------------------------------------------------------------- | -------------------------------------- |
| prepare_event             | Load event data and initialize scenario/state payload                 | static, dynamic replan, rolling replan |
| optimize_release_plan     | Optimize a release plan and select release-family parameters          | static, dynamic replan, rolling replan |
| simulate_release_plan     | Simulate reservoir trajectory for a candidate plan                    | all executable workflows               |
| evaluate_release_plan     | Produce metrics and stable reference_id for evidence binding          | all accepted workflows                 |
| check_hard_constraints    | Check operating-level and release hard constraints                    | validation                             |
| validate_decision_payload | Validate final structured decision payload                            | all LLM/MCP workflows                  |
| run_static_workflow       | Wrapper executing prepare-optimize-simulate-evaluate for static cases | optional wrapper / audit               |
| run_dynamic_stage         | Wrapper for one dynamic replan stage                                  | optional wrapper / audit               |
| run_rolling_stage         | Wrapper for one forecast-triggered rolling stage using prediction     | optional wrapper / audit               |

---

# Appendix E. Event list and scenario grouping

| Event ID   | Group | Duration | Peak inflow | Forecast available | Used in static | Used in dynamic | Used in rolling | Notes                             |
| ---------- | ----- | --------:| -----------:| ------------------ | -------------- | --------------- | --------------- | --------------------------------- |
| 2009080920 | S4    | 63 h     | 4650.0      | no                 | yes            | yes             | no              | extreme peak-inflow case          |
| 2010052305 | S3    | 75 h     | 2977.0      | no                 | yes            | no              | no              | high-risk static case             |
| 2010062002 | S4    | 264 h    | 2716.0      | no                 | yes            | yes             | no              | extreme/high-volume dynamic case  |
| 2011041623 | S1    | 81 h     | 1132.2      | no                 | yes            | no              | no              | routine case                      |
| 2011061323 | S1    | 81 h     | 1133.0      | no                 | yes            | no              | no              | routine case                      |
| 2012022323 | S1    | 129 h    | 908.0       | no                 | yes            | no              | no              | routine case                      |
| 2012030714 | S1    | 204 h    | 1294.5      | no                 | yes            | no              | no              | routine long-duration case        |
| 2012041314 | S1    | 141 h    | 1083.0      | no                 | yes            | no              | no              | routine case                      |
| 2012051514 | S1    | 84 h     | 1265.9      | no                 | yes            | no              | no              | routine case                      |
| 2012062402 | S4    | 255 h    | 1414.0      | yes                | yes            | no              | yes             | high-volume rolling case          |
| 2013051623 | S1    | 96 h     | 1033.0      | no                 | yes            | no              | no              | routine case                      |
| 2013060217 | S2    | 84 h     | 1466.0      | no                 | yes            | no              | no              | moderate level case               |
| 2013061314 | S2    | 135 h    | 845.5       | no                 | yes            | no              | no              | moderate level case               |
| 2013082211 | S2    | 93 h     | 1828.7      | no                 | yes            | no              | no              | moderate inflow case              |
| 2013083020 | S3    | 72 h     | 2549.6      | no                 | yes            | no              | no              | high-risk inflow case             |
| 2013100711 | S4    | 93 h     | 4380.4      | yes                | yes            | yes             | yes             | extreme peak-inflow forecast case |
| 2013121702 | S2    | 111 h    | 1041.4      | no                 | yes            | no              | no              | moderate level case               |
| 2019022120 | S2    | 135 h    | 1740.9      | no                 | yes            | no              | no              | moderate case                     |
| 2019043014 | S2    | 84 h     | 1744.9      | no                 | yes            | no              | no              | moderate case                     |
| 2019061323 | S2    | 93 h     | 1445.7      | no                 | yes            | no              | no              | moderate level case               |
| 2019062323 | S2    | 102 h    | 1691.7      | no                 | yes            | no              | no              | moderate case                     |
| 2019070517 | S2    | 117 h    | 1550.1      | yes                | yes            | no              | yes             | forecast rolling case             |
| 2019071011 | S2    | 108 h    | 1439.5      | yes                | yes            | yes             | yes             | forecast dynamic/rolling case     |
| 2019081008 | S2    | 57 h     | 1505.0      | no                 | yes            | no              | no              | moderate case                     |
| 2020070914 | S1    | 87 h     | 1455.5      | no                 | yes            | no              | no              | routine case                      |
| 2021052114 | S4    | 213 h    | 3928.8      | yes                | yes            | yes             | yes             | high-volume forecast case         |
| 2022032223 | S1    | 81 h     | 1251.4      | no                 | yes            | no              | no              | routine case                      |
| 2022033117 | S1    | 105 h    | 1195.0      | no                 | yes            | no              | no              | routine case                      |
| 2022060608 | S3    | 81 h     | 2855.1      | no                 | yes            | no              | no              | high-risk case                    |
| 2022061020 | S2    | 72 h     | 1694.8      | no                 | yes            | no              | no              | moderate case                     |
| 2022061823 | S3    | 69 h     | 3246.9      | no                 | yes            | no              | no              | high-risk case                    |
| 2022062023 | S3    | 69 h     | 3939.7      | yes                | yes            | yes             | yes             | high-risk forecast case           |
| 2022113011 | S1    | 57 h     | 1066.5      | no                 | yes            | no              | no              | routine case                      |
| 2023072808 | S2    | 141 h    | 1514.5      | no                 | yes            | no              | no              | moderate case                     |
| 2024052720 | S2    | 63 h     | 1157.7      | no                 | yes            | no              | no              | moderate level case               |
| 2024060202 | S2    | 114 h    | 2268.1      | no                 | yes            | yes             | no              | dynamic case                      |
| 2024061117 | S2    | 51 h     | 2352.8      | no                 | yes            | no              | no              | moderate case                     |
| 2024061220 | S3    | 51 h     | 2735.6      | yes                | yes            | yes             | yes             | high-risk forecast case           |
| 2024061517 | S3    | 45 h     | 2304.0      | yes                | yes            | yes             | yes             | high-level forecast case          |
| 2024061623 | S3    | 66 h     | 3441.8      | yes                | yes            | yes             | yes             | high-risk forecast case           |
| 2024072617 | S1    | 90 h     | 1246.7      | yes                | yes            | no              | yes             | routine forecast case             |

---

# Appendix F. Full Stage 1 and Stage 2 deterministic/oracle tables

Include:

1. 462-record main workflow set summary.
2. 492-record static instruction-conditioned matrix.
3. Static flood-group summary.
4. Dynamic retain/replan event summary.
5. Rolling check summary.
6. Metric-tolerance comparison between Stage 1 and Stage 2.

---

# Appendix G. Full Stage 3 executor-level results

Include full records for:

- Main static workflow: 41 records.
- Static instruction subset: 96 records per executor.
- Dynamic retain/replan: 48 records per executor.
- Command intervention: 40 records per executor.
- Rolling: 373 records per executor.
- Forecast-error audit: 51 records per executor.

---

# Appendix H. Forecast-error audit details

| Event ID                                                | Perturbation type | Stages | Trigger categories observed                                                        | Accepted MiMo | Accepted MiniMax | Accepted Claude | Notes                                                     |
| ------------------------------------------------------- | ----------------- | ------:| ---------------------------------------------------------------------------------- | -------------:| ----------------:| ---------------:| --------------------------------------------------------- |
| 2012062402                                              | 6 h lag           | 21     | relative forecast error; absolute forecast error; scheduled 12 h check             | 21/21         | 21/21            | 21/21           | Long-duration case; forecast                              |
| shifted later by 6 h                                    |                   |        |                                                                                    |               |                  |                 |                                                           |
| 2022062023                                              | mild over-peak    | 11     | relative forecast error; absolute forecast error; scheduled 12 h check; state risk | 11/11         | 11/11            | 11/11           | Peak forecast                                             |
| amplified by about 12%; stresses flood-control boundary |                   |        |                                                                                    |               |                  |                 |                                                           |
| 2013100711                                              | mild under-peak   | 7      | relative forecast error; scheduled 12 h check                                      | 7/7           | 7/7              | 7/7             | High-forecast case; peak forecast reduced by about 12%    |
| 2024061623                                              | 6 h lead          | 5      | absolute forecast error; relative forecast error                                   | 5/5           | 0/5              | 5/5             | Forecast peak shifted earlier by 6 h; tests early-warning |
| sensitivity                                             |                   |        |                                                                                    |               |                  |                 |                                                           |
| 2024072617                                              | mixed mild        | 7      | scheduled 12 h check; absolute forecast error; relative forecast error             | 7/7           | 7/7              | 7/7             | Peak reduced by about 10% and lagged                      |
| by 3 h                                                  |                   |        |                                                                                    |               |                  |                 |                                                           |

---

# Appendix I. Ablation details

| Variant                   | Records | Accepted | Tool-order valid | Eval-ref valid | Schema valid | Hard viol. | Notes                             |
| ------------------------- | -------:| --------:| ----------------:| --------------:| ------------:| ----------:| --------------------------------- |
| Text-only                 | 40      | 0/40     | N/A              | 0/40           | 40/40        | 0          | No tools available                |
| Tools-only                | 32      | 27/32    | 27/32            | 27/32          | 27/32        | 0          | Protocol/evidence failures remain |
| Tools + skills / full MCP | 40      | 40/40    | 40/40            | 40/40          | 40/40        | 0          | Full workflow contract            |

---

# Appendix J. Failure taxonomy

| Failure reason               | MiMo v2.5 | MiniMax M2.5 | Claude Haiku 4.5 | Interpretation                      |
| ---------------------------- | ---------:| ------------:| ----------------:| ----------------------------------- |
| Wrong tool order             | 0         | 4            | 7                | Workflow protocol failure           |
| Missing required tool        | 0         | 3            | 3                | Incomplete tool chain               |
| Missing evaluation reference | 5         | 4            | 0                | Evidence-binding failure            |
| Hard-constraint violation    | 0         | 0            | 0                | No hydrological hard-safety failure |
| Downstream violation         | 0         | 0            | 0                | No downstream release violation     |
