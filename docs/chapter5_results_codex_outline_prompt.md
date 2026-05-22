# Chapter 5 Results：Codex 数据检索、表格整理与绘图写作大纲

## 0. 文档用途

本文档用于指导 Codex 在 PyResOps 项目中自动搜索结果文件、汇总 static / dynamic / rolling / ablation 四类实验结果，并生成 Chapter 5 Results 的第一版草稿、图表和数据审计报告。

第一版目标不是写出最终 polished manuscript，而是把真实结果完整记录下来：

1. 找到所有实验结果文件；
2. 将结果放入正确小节；
3. 生成表格和图；
4. 明确每张图展示什么；
5. 记录数据来源；
6. 保持 ESWA 写作边界。

核心定位：

- Static：面向方案制定的约束测试，强调指定下泄类型和执行间隔；
- Dynamic：面向调度需求变化的约束测试，强调中途改变约束、目标、时限和风险偏好；
- Rolling：面向真实洪水预报的滚动约束测试，强调固定初始预报、实测状态更新和 trigger-only LLM 调用；
- Ablation：面向机制必要性的测试，强调有无 tools / skills / fail-closed contract 的差异。

---

# 1. 给 Codex 的完整 Prompt

下面内容可以直接复制给 Codex。

```text
You need to prepare the first complete draft of Chapter 5 Results for the PyResOps ESWA manuscript.

This is a result-recording, table-generation, and figure-generation task. Do not invent results. Search the repository result folders and fill the chapter outline with real values only. Use [MISSING] only when a required metric or file is genuinely unavailable.

The manuscript is about an LLM-assisted reservoir release-planning framework using MCP tools and fail-closed validation. It is not an LLM leaderboard and not a claim that PyResOps is better than historical or manual operation.

Required Chapter 5 structure:

5.1 Scenario construction and deterministic oracle
5.2 Static instruction-conditioned release planning
5.3 Dynamic command-intervention operation
5.4 Rolling forecast-triggered operation
5.5 Ablation of tools and workflow skills

Do not add a separate overall model ranking section. Cross-scenario executor sensitivity can be discussed later in Discussion. In Chapter 5, report executor results inside each scenario.

Important wording:
- Use “release-level planning”, not “gate-level operation”.
- Use “executor sensitivity”, not “model benchmark”.
- Use “Oracle metric comparison: PASS”, not simply “Oracle PASS”, when fail-closed accepted count is below total.
- Use “inflow-peak attenuation rate”, not “improvement over historical operation”.
- Use “full event and check coverage was retained while reducing LLM calls”, not “no loss”.
- Do not claim operational deployment readiness.
- Do not claim PyResOps outperforms historical operation.
- Do not treat correct infeasibility rejection as a model failure.

Please search these result directories:

experiments/results/stage1/
experiments/results/stage2/
experiments/results/stage3/
experiments/results/stage3_mimo_v25/
experiments/results/stage3_claude_haiku_4_5/
experiments/results/stage1_instruction_static/
experiments/results/stage2_instruction_static/
experiments/results/stage3_instruction_static_combined/
experiments/results/stage3_instruction_static_mimo/
experiments/results/stage3_instruction_static_mimo_subset/
experiments/results/stage1_dynamic_command_intervention/
experiments/results/stage2_dynamic_command_intervention/
experiments/results/stage3_dynamic_command_mimo/
experiments/results/stage3_dynamic_command_claude/
experiments/results/stage3_dynamic_command_minimax/
experiments/results/stage3_dynamic_command_combined/
experiments/figures/chapter5/
experiments/figures/chapter5/tables/

Also inspect:

experiments/config/stage1_event_list_41.txt
experiments/config/dynamic_event_selection.csv
experiments/config/stage1_instruction_static.yml
experiments/config/stage2_instruction_static.yml
experiments/config/stage3_instruction_static.yml
experiments/config/stage1_dynamic_command_intervention.yml
experiments/config/stage2_dynamic_command_intervention.yml
experiments/config/stage3_dynamic_command_intervention.yml
experiments/config/stage3_llm_mcp.yml

Known values from logs may be used only if confirmed by files:

Main oracle:
- 462 records = 41 static + 48 dynamic + 373 rolling.
- Stage 2 reproduced Stage 1 on 462/462 records.

Static instruction-conditioned scenario:
- Deterministic Stage 1/2: 492 rows = 41 events × 6 release families × 2 operation intervals.
- Stage 1: 492/492 accepted, 492/492 command compliance, 492/492 interval compliance, 0 hard/downstream violations.
- Stage 2 vs Stage 1: 492/492 matched, 0 tolerance failures, 0 compliance mismatches.
- Stage 3 representative subset: 96 rows per executor.
- MiMo: 93/96 accepted, 96.9% command compliance, 100% interval compliance.
- Claude: 94/96 accepted, 97.9% command compliance, 100% interval compliance.
- MiniMax: 87/96 accepted, 90.6% command compliance, 100% interval compliance.

Dynamic command-intervention scenario:
- Deterministic Stage 1/2: 40 rows = 5 events × 4 commands × 2 checkpoints.
- Stage 1: 40/40 command_handling_success, 40/40 feasible_execution_success.
- Stage 2: 40/40 matched, oracle_pass=True.
- Stage 3:
  - MiMo: 38/40 accepted, CHS 38/40, FES 38/40, wrong_tool_order ×2.
  - Claude: 40/40 accepted, CHS 40/40, FES 40/40, no failures.
  - MiniMax: 39/40 accepted, CHS 39/40, FES 39/40, wrong_tool_order ×1.

Rolling forecast-triggered scenario:
- Total rolling checks: 373.
- LLM-called checks: 142.
- Deterministic retain rows: 231.
- LLM-call reduction = 231 / 373 = 61.9%.
- Rolling Stage 3:
  - MiniMax: 367/373.
  - MiMo: 368/373.
  - Claude: 370/373.
- Retain rows are accepted deterministically unless result files show otherwise.

Main Stage 3 overall results:
- MiniMax: 451/462, 97.6%.
- MiMo: 457/462, 98.9%.
- Claude: 452/462, 97.8%.

Required formulas:

Fail-closed acceptance:
A = tool_order_valid AND eval_ref_valid AND schema_valid AND NOT hard_violation AND NOT downstream_violation.

Static instruction-conditioned acceptance:
A_static = A AND command_compliance AND interval_compliance.

Dynamic command handling:
command_handling_success = (feasible command AND executed valid plan) OR (infeasible/unsafe command AND structured rejection).
feasible_execution_success = feasible command AND executed valid plan.

Rolling LLM-call reduction:
LLM-call reduction = deterministic_retain_rows / total_rolling_checks.

Inflow-peak attenuation rate:
attenuation = 1 - peak_release / peak_inflow.

Required outputs:
- manuscript_drafts/chapter5_results_first_draft.md
- experiments/figures/chapter5/tables/table5_1_scenario_coverage.csv
- experiments/figures/chapter5/tables/table5_2_static_results.csv
- experiments/figures/chapter5/tables/table5_3_dynamic_results.csv
- experiments/figures/chapter5/tables/table5_4_rolling_results.csv
- experiments/figures/chapter5/tables/table5_5_ablation_results.csv
- experiments/figures/chapter5/fig5_1_validation_framework.png and .pdf
- experiments/figures/chapter5/fig5_2_static_instruction_case.png and .pdf
- experiments/figures/chapter5/fig5_3_dynamic_command_case.png and .pdf
- experiments/figures/chapter5/fig5_4_rolling_operation_trace.png and .pdf
- experiments/figures/chapter5/fig5_5_rolling_call_reduction.png and .pdf
- experiments/figures/chapter5/fig5_6_ablation_tools_skills.png and .pdf
- experiments/figures/chapter5/data_audit_report.md

The data audit report must list:
1. which result files were read;
2. which table used which file;
3. which figure used which file;
4. any missing values;
5. any mismatch between file values and known logs.
```

---

# 2. Chapter 5 推荐结构

## 5. Results

开头段需要说明：

- 结果来自滩坑水库真实洪水事件；
- Results 按 static、dynamic、rolling 和 ablation 组织；
- Stage 1/2 建立 deterministic oracle；
- Stage 3 验证 LLM+MCP；
- 本章关注可执行性、可审计性、工具调用可靠性和水文安全约束。

建议英文骨架：

```text
This section reports the validation results of PyResOps on Tankeng Reservoir flood-event records. The experiments are organized around three operational decision layers—static release planning, dynamic command intervention, and rolling forecast-triggered operation—plus an ablation setting for tools and workflow skills. Stage 1 establishes deterministic direct-service references, Stage 2 verifies workflow-level replication, and Stage 3 evaluates LLM+MCP execution under fail-closed validation. The results focus on feasibility, auditability, tool-use reliability, and hydrological safety checks rather than comparison with historical operation.
```

---

# 3. 5.1 Scenario construction and deterministic oracle

## 3.1 写作目标

5.1 是实验地图，不是具体模型结果。需要说明：

1. 洪水事件如何筛选；
2. static、dynamic、rolling、ablation 各自对应什么实际调度任务；
3. Stage 1、Stage 2、Stage 3 的关系；
4. Stage 2 为什么作为 oracle；
5. fail-closed 的基本公式。

## 3.2 需要写入的内容

### 3.2.1 洪水事件筛选

内容：

- 原始 44 场；
- 剔除 3 场蓄水前或初蓄阶段异常水位；
- 保留 41 场；
- S1 routine、S2 moderate、S3 high-risk、S4 extreme；
- 分组只用于 stratified reporting，不用于频率分析。

数据源：

- `experiments/config/stage1_event_list_41.txt`
- `experiments/results/stage1/STAGE1_SUMMARY.md`

### 3.2.2 三类调度任务层次

需要写成整体设计，不要写成“extension”。

Static：

- 默认 full-horizon planning；
- 指令约束方案制定；
- 指定 release family；
- 指定 operation interval。

Dynamic：

- retain/replan；
- 中途命令干预；
- 改变 release cap；
- 改变 terminal target；
- 压缩 target deadline；
- 增加 risk buffer；
- 识别不可行命令。

Rolling：

- fixed initial forecast；
- 3h observed-state update；
- trigger-only LLM intervention；
- retain deterministic audit row。

Ablation：

- text-only；
- tools-only；
- tools + skills / full MCP。

### 3.2.3 三阶段 oracle

需要写：

- Stage 1：direct-service deterministic baseline；
- Stage 2：workflow replication；
- Stage 3：LLM+MCP；
- Stage 2 与 Stage 1 462/462 匹配；
- 后面 LLM 结果对照 Stage 2 oracle。

### 3.2.4 公式

建议在 5.1 写公式：

```text
A = O_tool ∧ O_ref ∧ O_schema ∧ ¬V_hard ∧ ¬V_downstream
```

其中：

- `O_tool` = tool-order valid；
- `O_ref` = eval-ref valid；
- `O_schema` = schema valid；
- `V_hard` = hard violation；
- `V_downstream` = downstream violation。

Static：

```text
A_static = A ∧ C_command ∧ C_interval
```

Dynamic：

```text
A_dynamic = command_handling_success
```

其中：

```text
command_handling_success = feasible execution OR structured infeasibility rejection
```

## 3.3 Table 5.1

标题：

**Table 5.1. Scenario design and deterministic oracle coverage.**

字段：

| Scenario | Operational role | Deterministic coverage | Stage 3 evaluation | Key success criteria |
|---|---|---:|---:|---|

建议填法：

| Scenario | Operational role | Deterministic coverage | Stage 3 evaluation | Key success criteria |
|---|---|---:|---:|---|
| Static release planning | Full-horizon planning and operator-specified release form/interval | 41 main records + 492 instruction-conditioned records | 96 representative records per executor | feasibility, command compliance, interval compliance, zero hard/downstream violations |
| Dynamic command intervention | Retain/replan and mid-event command changes | 48 main records + 40 command records | 40 command records per executor | command handling success, feasible execution success, structured rejection if infeasible |
| Rolling forecast-triggered operation | Fixed forecast with 3 h observed-state updates | 373 rolling checks | 373 checks per executor, 142 LLM-called nodes | trigger validity, fail-closed acceptance, LLM-call reduction |
| Tools/skills ablation | Mechanism validation | ablation variants | text-only, tools-only, tools+skills/full MCP | accepted rate, tool-order validity, eval-ref validity, schema validity |

## 3.4 Figure 5.1

标题：

**Figure 5.1. Scenario design and three-stage validation framework.**

图形类型：流程图。

布局：

```text
Tankeng flood-event records
44 events → 3 excluded → 41 retained
        ↓
Scenario construction
Static / Dynamic / Rolling / Ablation
        ↓
Stage 1: direct-service baseline
        ↓
Stage 2: deterministic workflow oracle
        ↓
Stage 3: LLM+MCP fail-closed execution
```

右侧标注输出指标：

- accepted rate；
- command compliance；
- interval compliance；
- tool-order validity；
- eval-ref validity；
- schema validity；
- hard/downstream violations。

---

# 4. 5.2 Static instruction-conditioned release planning

## 4.1 写作目标

Static 场景展示系统的方案制定能力。它要证明：

1. 41 场洪水的默认静态方案均可执行；
2. 系统能按指定 release family 生成方案；
3. 系统能按 6h/12h operation interval 生成分段下泄；
4. LLM+MCP 可以执行这些指令；
5. 失败主要来自 fail-closed protocol/schema/evidence gate，而不是水库约束本身。

## 4.2 内容结构

### Paragraph 1：场景定义

写：

- full-event inflow known；
- release-level planning；
- operator-specified release family；
- operation interval；
- 不与历史调度对比。

### Paragraph 2：deterministic 结果

需要填：

- default static 41/41 accepted；
- instruction deterministic 492/492 accepted；
- 492/492 command compliance；
- 492/492 interval compliance；
- 0 hard/downstream；
- Stage 2 492/492 matched。

数据源：

- `experiments/results/stage1/static/all_events_metrics.csv`
- `experiments/results/stage1_instruction_static/results.csv`
- `experiments/results/stage2_instruction_static/results.csv`
- `experiments/results/stage2_instruction_static/comparison/`

### Paragraph 3：Stage 3 三模型结果

需要填表：

| Executor | Records | Accepted | Command compliance | Interval compliance | Tool-order valid | Eval-ref valid | Schema valid | Hard viol. | Downstream viol. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MiMo v2.5 | 96 | 93 | 96.9% | 100% | 100% | 100% | 100% | [XX] | [XX] |
| Claude Haiku 4.5 | 96 | 94 | 97.9% | 100% | 97.9% | 97.9% | 97.9% | [XX] | [XX] |
| MiniMax M2.5 | 96 | 87 | 90.6% | 100% | 92.7% | 92.7% | 92.7% | [XX] | [XX] |

注意：

- 解释 IC = 100%；
- CC failure 如果由 tool/schema/eval 触发，要写成 fail-closed rejection，不写成真正下泄类型选择失败；
- 不写模型排行榜。

## 4.3 Figure 5.2

标题：

**Figure 5.2. Instruction-conditioned static release planning for a representative flood event.**

推荐事件：`2024061623`。

推荐 interval：6h。

Panel A：Inflow and release hydrographs。

- observed inflow；
- six release families；
- 不画 historical release。

Panel B：Reservoir level。

- six simulated level trajectories；
- flood-limit line；
- absolute ceiling if available。

Panel C：Metrics。

- max_level；
- max_release；
- terminal_deviation；
- inflow_peak_attenuation_rate。

Caption 要点：

- release family and operation interval are specified by command；
- figure shows executable release shapes；
- not a comparison with historical operation；
- not a universal ranking of release families。

---

# 5. 5.3 Dynamic command-intervention operation

## 5.1 写作目标

Dynamic 场景展示系统处理中途调度需求变化的能力。它要证明：

1. 系统能做 retain/replan；
2. 系统能处理中途 release cap、target level、deadline、risk buffer 变化；
3. 系统能区分可执行命令和不可行命令；
4. 不可行命令正确拒绝也算 command handling success；
5. LLM 失败会被 fail-closed gate 拦截。

## 5.2 内容结构

### Paragraph 1：场景定义

写：

- mid-event commands；
- checkpoint-based operation；
- constraint/objective/deadline/risk modifications。

### Paragraph 2：retain/replan baseline

填：

- 10 events；
- 48 checkpoints；
- 26 replan；
- 22 retain；
- 48/48 accepted；
- 0 hard/downstream。

### Paragraph 3：command-intervention deterministic oracle

填：

- 5 events；
- 4 command types；
- 2 checkpoints；
- 40 records；
- Stage 1 40/40；
- Stage 2 40/40；
- oracle_pass=True。

命令类型：

| Command | Meaning |
|---|---|
| release_cap_adjustment | stricter release cap |
| terminal_target_lowering | lower terminal target |
| target_deadline_compression | reach target earlier |
| conservative_risk_buffer | increase safety buffer |

### Paragraph 4：Stage 3 三模型结果

填：

| Executor | Records | Accepted | CHS | FES | Tool-order valid | Eval-ref valid | Schema valid | Failure reason |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| MiMo v2.5 | 40 | 38 | 38 | 38 | 38 | 38 | 38 | wrong_tool_order ×2 |
| Claude Haiku 4.5 | 40 | 40 | 40 | 40 | 40 | 40 | 40 | none |
| MiniMax M2.5 | 40 | 39 | 39 | 39 | 39 | 39 | 39 | wrong_tool_order ×1 |

补充 hard/downstream 和 oracle metric comparison。

## 5.3 Figure 5.3

标题：

**Figure 5.3. Dynamic command-intervention operation under mid-event target or constraint change.**

推荐事件：

- `2024061623`；
- 或 `2021052114`；
- 或 `2010062002`。

推荐命令：D3 target_deadline_compression。

图形 4 panel：

Panel A：Observed inflow and release before/after command。

- inflow；
- baseline release；
- intervention release；
- command time marker。

Panel B：Reservoir level。

- baseline level；
- intervention level；
- flood-limit line；
- target level；
- original deadline +12h；
- compressed deadline +9h。

Panel C：Command timeline。

```text
checkpoint → command parsed → replan attempted → executed / rejected → validation
```

Panel D：Validation gates。

- tool_order；
- eval_ref；
- schema；
- hard violation；
- downstream violation；
- CHS；
- FES。

Caption 要点：

- 展示中途调度命令如何改变剩余方案；
- 如果命令不可行，正确拒绝也算 command-handling success；
- 不与历史调度比较。

---

# 6. 5.4 Rolling forecast-triggered operation

## 6.1 写作目标

Rolling 场景展示真实预报驱动的滚动调度能力。它要证明：

1. 10 场 withpred 事件全覆盖；
2. 每 3h 更新 observed state；
3. 固定初始预报不更新；
4. trigger-only 策略减少 LLM 调用；
5. retain rows 被记录为 deterministic audit rows；
6. 三模型 rolling 表现稳定。

## 6.2 内容结构

### Paragraph 1：场景定义

写：

- fixed forecast at event start；
- observed inflow/level updates every 3h；
- trigger checker；
- LLM called only for trigger nodes。

### Paragraph 2：trigger-only 结果

填：

- total checks = 373；
- LLM-called = 142；
- deterministic retain = 231；
- reduction = 61.9%；
- retain accepted = 231/231；
- event coverage = 10/10。

### Paragraph 3：三模型 rolling 结果

填：

| Executor | Records | LLM-called | Retain rows | Accepted | Hard viol. | Downstream viol. |
|---|---:|---:|---:|---:|---:|---:|
| MiniMax M2.5 | 373 | 142 | 231 | 367 | [XX] | [XX] |
| MiMo v2.5 | 373 | 142 | 231 | 368 | [XX] | [XX] |
| Claude Haiku 4.5 | 373 | 142 | 231 | 370 | [XX] | [XX] |

## 6.3 Figure 5.4

标题：

**Figure 5.4. Forecast-triggered rolling operation under fixed initial forecast and observed-state updates.**

推荐事件：

- `2012062402`：rolling checks 最多；
- 或 `2024061623`：2024 代表性事件。

Panel A：Observed inflow and fixed forecast。

Panel B：Rolling release trajectory。

Panel C：Reservoir level and flood-limit line。

Panel D：Trigger timeline。

Trigger markers：

- initial；
- scheduled_check；
- absolute_forecast_error；
- relative_forecast_error；
- level_risk；
- retain_plan。

## 6.4 Figure 5.5

标题：

**Figure 5.5. LLM-call reduction under trigger-only rolling execution.**

堆叠柱：

- LLM-called = 142；
- deterministic retain = 231；
- total = 373。

标注：

- 61.9% call reduction；
- full event/check coverage retained。

---

# 7. 5.5 Ablation of tools and workflow skills

## 7.1 写作目标

Ablation 证明 tools / skills / fail-closed contract 的必要性。

它回答：

> 没有 tools 或没有 workflow skills 时，LLM 是否还能稳定形成可审计的调度决策？

## 7.2 对比组

| Variant | Description | Expected risk |
|---|---|---|
| Text-only | LLM directly answers without tools | hallucinated metrics, no eval-ref |
| Tools-only | tools available but no workflow skill contract | wrong order, missing evidence binding |
| Tools + skills / full MCP | tools, workflow skill, fail-closed contract | auditable execution |

## 7.3 指标

| Metric | Meaning |
|---|---|
| accepted rate | final fail-closed acceptance |
| tool-order validity | correct tool sequence |
| eval-ref validity | current-session evidence binding |
| schema validity | valid structured payload |
| hard violations | hydrological hard-safety violations |
| downstream violations | downstream-routing violations |

## 7.4 Table 5.5

| Variant | Records | Accepted | Tool-order valid | Eval-ref valid | Schema valid | Hard viol. | Downstream viol. |
|---|---:|---:|---:|---:|---:|---:|---:|

数据源需要 Codex 搜索 B2/B3/B4 或 ablation 目录。

## 7.5 Figure 5.6

标题：

**Figure 5.6. Effect of tools and workflow skills on fail-closed execution.**

图形类型：分组柱状图或热图。

变量：

- accepted rate；
- tool-order validity；
- eval-ref validity；
- schema validity。

Caption：

说明 tools 和 workflow skills 改善的是可审计执行，不是直接改变优化内核。

---

# 8. 总图表清单

## 主文图

| Figure | 内容 |
|---|---|
| Figure 5.1 | 实验设计与三阶段验证框架 |
| Figure 5.2 | Static instruction-conditioned representative operation |
| Figure 5.3 | Dynamic command-intervention representative operation |
| Figure 5.4 | Rolling forecast-triggered operation trace |
| Figure 5.5 | Rolling LLM-call reduction |
| Figure 5.6 | Ablation tools/skills effect |

## 主文表

| Table | 内容 |
|---|---|
| Table 5.1 | Scenario design and oracle coverage |
| Table 5.2 | Static results |
| Table 5.3 | Dynamic results |
| Table 5.4 | Rolling results |
| Table 5.5 | Ablation results |

---

# 9. 数据审计报告要求

Codex 必须生成：

```text
experiments/figures/chapter5/data_audit_report.md
```

内容包括：

1. 每个结果文件是否存在；
2. 每张表的数据来源；
3. 每张图的数据来源；
4. 哪些字段缺失；
5. 哪些文件中的数值和日志不一致；
6. 哪些结果仍需人工确认。

---

# 10. 最终检查清单

Codex 提交前必须检查：

- [ ] 41 + 48 + 373 = 462；
- [ ] 142 + 231 = 373；
- [ ] 231 / 373 = 61.9%；
- [ ] Static instruction deterministic = 492；
- [ ] Static instruction LLM subset = 96/model；
- [ ] Dynamic command deterministic = 40；
- [ ] Dynamic command LLM = 40/model；
- [ ] Rolling = 373/model；
- [ ] 所有图有单位；
- [ ] 所有表有数据来源；
- [ ] 不出现 “best model”；
- [ ] 不出现 “outperform historical operation”；
- [ ] 不把不可行命令正确拒绝写成失败；
- [ ] 不把 trigger-only 写成 “no loss”；
- [ ] 不把 release-level planning 写成 gate-level control；
- [ ] Ablation 不和 static/dynamic/rolling 混淆。
