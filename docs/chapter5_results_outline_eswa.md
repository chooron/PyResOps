# PyResOps Chapter 5 Results 大纲与图表设计说明

## 使用目的

本文档用于指导 ESWA 投稿版 **Chapter 5 Results** 的重写、图表绘制和结果叙述。当前版本采用紧凑的 **4 小节结构**，以避免 Results 章节过度碎片化，同时保留 Stage 1、Stage 2 和 Stage 3 的完整证据链。

本章核心主线为：

> 真实洪水场景构建 → 确定性调度基准 → 滚动触发式 LLM 介入 → LLM+MCP fail-closed 执行验证与执行器敏感性。

本章不应写成 LLM 排行榜，也不应声称 PyResOps 是更优的水库优化算法。重点应放在：

- 工具调用链是否正确；
- 决策结果是否可审计；
- evaluation reference 是否可追溯；
- 水位、下泄、下游演进等约束是否通过校验；
- 失败是否集中于协议/证据绑定，而不是水文安全。

---

# 5 Results 推荐大纲

## 5.1 Scenario construction and deterministic oracle

### 5.1.1 写作目标

本节用于建立 Results 的实验基础。主要回答三个问题：

1. 本文使用哪些真实洪水场景；
2. 为什么最终使用 41 场而不是 44 场；
3. Stage 1 和 Stage 2 如何构成 Stage 3 的 deterministic oracle。

本节应放在 Results 开头，避免直接进入 LLM 结果。这样可以让 ESWA 审稿人先看到：实验场景来自水库调度实际，而不是为了测试 LLM 随机设计的玩具任务。

### 5.1.2 建议段落结构

第一段：说明原始洪水过程数据包括 44 场，其中 3 场因蓄水前或初蓄阶段水位异常被排除，最终保留 41 场用于正式实验。这里要明确：排除不是为了提升结果，而是为了保证水位状态符合滩坑水库投运后的实际运行范围。

第二段：说明 41 场洪水按水文特征分为 S1–S4。分类指标包括入库洪峰、最高水位、总洪量和洪峰历时。S1–S4 不应写成复杂聚类模型，而应写成用于场景覆盖和结果分层汇总的工程化分类。

第三段：说明三类 workflow：static、dynamic、rolling。Static 对应完整洪水过程的离线下泄方案制定；dynamic 对应洪水过程中的阶段性 retain/replan；rolling 对应 withpred 场景下基于固定初始预报和观测状态更新的滚动复核。

第四段：说明三阶段验证关系。Stage 1 是 direct-service deterministic baseline；Stage 2 是 deterministic workflow replication；Stage 2 在 462/462 行上复现 Stage 1，因此作为 Stage 3 的 workflow oracle。

第五段：定义 oracle metric comparison 的通过标准。建议用真实项目中已经采用的容差：max level ±0.5 m、terminal deviation ±0.5 m、inflow-peak attenuation rate ±0.05。如果最终论文中使用其他标准，应以实际配置为准。

### 5.1.3 本节建议表格

**Table 5.1 Scenario and oracle coverage**

建议列：

| Flood group / workflow | Events | Static rows | Dynamic rows | Rolling rows | Total rows | Role in evaluation |
|---|---:|---:|---:|---:|---:|---|
| S1 Routine | [XX] | [XX] | [XX] | [XX] | [XX] | Low-risk baseline cases |
| S2 Moderate | [XX] | [XX] | [XX] | [XX] | [XX] | Moderate release-planning cases |
| S3 High-risk | [XX] | [XX] | [XX] | [XX] | [XX] | Dynamic/event-stress cases |
| S4 Extreme | [XX] | [XX] | [XX] | [XX] | [XX] | Extreme/high-volume cases |
| Static workflow | 41 | 41 | — | — | 41 | Whole-event release planning |
| Dynamic workflow | 10 | — | 48 | — | 48 | Stage-wise retain/replan |
| Rolling workflow | 10 | — | — | 373 | 373 | 3h rolling check with fixed forecast |
| Total oracle rows | — | 41 | 48 | 373 | 462 | Stage 2 oracle for Stage 3 |

注意：如果 S1–S4 与 workflow 不是同一个统计维度，可以在表中分为上下两块，避免重复相加造成误解。

### 5.1.4 Figure 5.1 设计说明

**Figure 5.1 Stage 1–3 validation pipeline**

#### 图的目的

展示 PyResOps Results 章节的验证逻辑，而不是展示某一个单独算法流程。审稿人应该从这张图中立即看懂：Stage 1 验证计算内核，Stage 2 验证 workflow 抽象层，Stage 3 验证 LLM+MCP 工具调用层。

#### 推荐图形类型

三层横向流程图或纵向流程图均可。推荐横向三段式，因为更适合 ESWA 系统论文。

#### 推荐结构

从左到右设置三个大框：

1. **Stage 1: Direct-service deterministic baseline**
   - 输入：41 static events、10 dynamic high-risk events、10 withpred rolling events；
   - 执行：OptimizationService / SimulationService / EvaluationService；
   - 输出：462 deterministic rows；
   - 验证目标：scenario feasibility and kernel-level execution。

2. **Stage 2: Deterministic workflow replication**
   - 输入：Stage 1 scenarios and constraints；
   - 执行：StaticWorkflow / DynamicWorkflow / RollingWorkflow；
   - 输出：462 workflow rows；
   - 验证目标：workflow abstraction reproduces Stage 1；
   - 标注：462/462 matched, oracle metric comparison PASS。

3. **Stage 3: LLM + MCP tool-use evaluation**
   - 输入：Stage 2 workflow oracle；
   - 执行：LLM calls MCP tools under fail-closed validation；
   - 输出：fail-closed accepted/rejected records；
   - 验证目标：tool order, evidence binding, schema, safety checks。

#### 必须标注的数字

- 41 static rows；
- 48 dynamic rows；
- 373 rolling rows；
- total 462 rows；
- Stage 2: 462/462 matched；
- Stage 3: 三模型 attempted 462 each。

#### 视觉重点

- Stage 1 和 Stage 2 用蓝色/灰色系，表示 deterministic layers；
- Stage 3 用橙色/绿色系，表示 LLM/tool-use layer；
- 箭头方向清楚，避免复杂交叉线；
- 图中不要出现“better optimizer”等表述。

#### Caption 建议

**Figure 5.1. Three-stage validation pipeline used in Chapter 5.** Stage 1 establishes a direct-service deterministic reference, Stage 2 verifies that the workflow abstraction reproduces the deterministic reference, and Stage 3 evaluates whether LLM executors can reproduce the same workflow decisions through MCP tools under fail-closed validation.

#### 绘图数据来源

- `experiments/results/stage1/STAGE1_SUMMARY.md`
- `experiments/results/stage2/STAGE2_SUMMARY.md`
- `experiments/results/stage3_mimo_v25/STAGE3_SUMMARY.md`
- MiniMax / Claude Stage 3 summary files

#### 检查项

- [ ] 图中总行数必须满足 41 + 48 + 373 = 462；
- [ ] Stage 2 应写为 workflow oracle；
- [ ] Stage 3 应写为 LLM+MCP tool-use evaluation；
- [ ] 不要把 Stage 3 写成优化算法改进。

---

## 5.2 Deterministic release planning under static and dynamic workflows

### 5.2.1 写作目标

本节展示在没有 LLM 的情况下，PyResOps 能否在真实洪水事件上生成满足约束的下泄方案。这里主要承接 Stage 1 结果，重点是 static 和 dynamic。

本节不是为了证明系统优于历史调度，也不是与原调度计划进行对比。图和文字只需要展示：

- 入库流量如何变化；
- 下泄流量如何响应；
- 水库水位如何变化；
- 动态场景中何时 retain、何时 replan；
- 所有结果是否通过 hard-safety 和 downstream check。

### 5.2.2 建议段落结构

第一段：说明 static 工作流对 41 场保留洪水事件逐一制定完整下泄方案。强调 static 是 whole-event release planning，不涉及闸门级操作。

第二段：报告 static 总体结果：41/41 accepted，0 hard violations，0 downstream violations。按 S1–S4 报告 mean max level、terminal deviation 和 inflow-peak attenuation rate。

第三段：说明 dynamic 工作流选择 10 场高风险事件，在自适应检查点 T0–T4 执行 retain/replan 决策。这里要说明 dynamic 不是每 3 小时都重新优化，而是在代表性阶段检查当前方案是否仍然满足剩余调度要求。

第四段：报告 dynamic 结果：48 stages，26 replan，22 retain，48/48 accepted，0 hard violations。强调 retain/replan 逻辑成功触发，并且没有引入安全违规。

第五段：引出 Figure 5.2，说明代表性案例图展示真实洪水过程中入库、下泄、水位和决策阶段的变化。

### 5.2.3 本节建议表格

**Table 5.2 Static deterministic results by flood group**

| Flood group | Events | Accepted | Hard viol. | Downstream viol. | Mean max level | Max level | Mean terminal dev. | Mean inflow-peak attenuation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S1 Routine | [XX] | [XX] | 0 | 0 | [XX] | [XX] | [XX] | [XX] |
| S2 Moderate | [XX] | [XX] | 0 | 0 | [XX] | [XX] | [XX] | [XX] |
| S3 High-risk | [XX] | [XX] | 0 | 0 | [XX] | [XX] | [XX] | [XX] |
| S4 Extreme | [XX] | [XX] | 0 | 0 | [XX] | [XX] | [XX] | [XX] |
| Total | 41 | 41 | 0 | 0 | [XX] | [XX] | [XX] | [XX] |

**Table 5.3 Dynamic deterministic results**

| Event | Checkpoints | Replan | Retain | Accepted | Hard viol. | Notes |
|---|---:|---:|---:|---:|---:|---|
| [event_id] | [XX] | [XX] | [XX] | [XX] | 0 | [high-risk / long-duration / high-level] |
| Total | 48 | 26 | 22 | 48 | 0 | — |

如果主文表格过长，可以只放 total summary，将 per-event dynamic table 放 Appendix。

### 5.2.4 Figure 5.2 设计说明

**Figure 5.2 Representative static and dynamic release-planning cases**

#### 图的目的

这是 Chapter 5 中最重要的水库调度过程图。它需要把“系统真的在调度洪水过程”展示出来，而不是只展示 acceptance rate。图中不需要与原调度规划或历史调度进行对比，只展示 PyResOps 下泄方案、入库过程、水位过程和动态决策变化。

#### 推荐图形类型

多面板时间序列图。推荐采用 **3 个代表事件 × 每个事件 3 个子图** 的布局。

推荐事件选择：

1. 一个 routine/moderate 洪水事件：展示普通洪水下系统维持低风险运行；
2. 一个 high-risk 洪水事件：展示高入库洪峰下下泄响应；
3. 一个 extreme 或 2024 典型事件，优先考虑 `2024061623`：展示大洪量/高水位风险下的水位控制与动态决策。

如果版面有限，可以只画 2 个事件：一个常规事件 + `2024061623`。

#### 每个事件的子图设计

每个事件建议包含三个纵向子图，共享 x 轴时间。

**Panel A: Inflow and release hydrographs**

- x 轴：时间，格式建议为 `MM-DD HH` 或相对时间 `hours since event start`；
- y 轴：flow，单位 m³/s；
- 曲线 1：observed inflow；
- 曲线 2：optimized release；
- 不画 historical release，避免与原调度对比；
- 在洪峰点标注 peak inflow；
- 在最大下泄点标注 peak release；
- 如果 dynamic 事件包含 replan/retain，使用竖线标出检查点。

**Panel B: Reservoir level trajectory**

- x 轴：同 Panel A；
- y 轴：reservoir level，单位 m；
- 曲线：simulated reservoir level；
- 加水平线：seasonal flood limit；
- 加水平线：absolute level ceiling / flood-control high level，如 161.5 m；
- 若事件跨梅汛/台汛/过渡期，应标注应用的 flood limit；
- 不画原计划水位；
- 在最高水位处标注 max level；
- 若全程未超过控制线，可在图中标注 “no hard violation”。

**Panel C: Dynamic decision timeline**

- x 轴：同 Panel A；
- y 轴：decision state；
- 使用点或竖线标注 T0/T1/T2-peak/T3/T4；
- replan 用实心标记，retain 用空心标记；
- 可在每个检查点下方标注 action；
- 若该事件只用于 static，则 Panel C 可显示 “static plan generated once at event start”；
- 对 `2024061623` 等 dynamic case，建议展示 replan/retain 的实际切换过程。

#### 数据字段要求

绘图脚本需要读取以下字段或等价字段：

- `event_id`
- `timestamp` 或 `relative_hour`
- `inflow`
- `optimized_release` 或 `release`
- `simulated_level` 或 `level`
- `flood_limit_applied`
- `hard_violation`
- `workflow_stage`
- `action`，取值 `retain` / `replan`
- `max_level`
- `peak_inflow`
- `peak_release`

#### 数据来源建议

- Stage 1 static trajectories：`experiments/results/stage1/static/trajectories/`
- Stage 1 dynamic stage results：`experiments/results/stage1/dynamic/stage_results.csv`
- 若 trajectory JSON 当前只是 stub，需要从原始 event CSV 和优化结果重新生成完整过程线。

#### 视觉要求

- 入库和下泄曲线颜色要区分明显；
- 水位线不能和流量线放在同一个 y 轴，避免误读；
- 检查点竖线不要过密，最多显示关键 T0–T4；
- 图中不要出现 “better than historical operation” 等字样；
- 图例中使用 “Inflow”, “Optimized release”, “Simulated level”, “Flood limit”, “Replan”, “Retain”。

#### Caption 建议

**Figure 5.2. Representative deterministic release-planning cases under static and dynamic workflows.** Each case shows the observed inflow, optimized release, simulated reservoir level, and stage-wise retain/replan decisions where applicable. The figure illustrates the executable release-planning process under reservoir-level constraints without comparing against historical operation.

#### 质量检查

- [ ] 每个事件的 inflow 和 release 时间轴必须对齐；
- [ ] 水位曲线应由同一 release plan 模拟得到；
- [ ] flood limit 应随季节正确应用；
- [ ] replan/retain 标记应来自 dynamic stage log，不可手工猜测；
- [ ] 不绘制历史调度或原调度计划对比线。

---

## 5.3 Rolling operation with trigger-only LLM intervention

### 5.3.1 写作目标

本节展示最贴近实时生产的滚动调度场景。重点不是证明每个时间步都让 LLM 决策，而是证明：系统每 3 小时检查一次状态，但只有在触发条件出现时才调用 LLM+MCP，其他时刻通过 deterministic retain 记录保留当前方案。

这节应突出两个结果：

1. 全部 10 场 withpred 事件和 373 个 rolling checks 都被覆盖；
2. LLM 调用次数从 373 降至 142，同时保留完整事件/检查点覆盖。

### 5.3.2 建议段落结构

第一段：说明 rolling 数据设置。10 场 withpred 事件；预报在事件开始时发布一次，不更新；每 3 小时更新观测状态；每个 rolling check 都会判断是否触发重优化。

第二段：说明 trigger-only 策略。触发类型包括 initial、scheduled_check、relative_forecast_error、absolute_forecast_error 和 level_risk。未触发时记录 deterministic retain row，llm_called = false。

第三段：报告 rolling 结果。总 checks = 373；LLM-called = 142；deterministic retain = 231；调用减少率 = 61.9%；retain rows 231/231 accepted；hard violations = 0；downstream violations = 0。

第四段：引出 Figure 5.3 和 Figure 5.4。Figure 5.3 展示机制；Figure 5.4 展示调用减少和一个真实 rolling 事件中的决策变化。

### 5.3.3 本节建议表格

**Table 5.4 Rolling trigger-only results**

| Metric | Value |
|---|---:|
| Rolling events | 10 |
| Total rolling checks | 373 |
| LLM-called checks | 142 |
| Deterministic retain rows | 231 |
| LLM-call reduction | 61.9% |
| Accepted retain rows | 231/231 |
| Accepted LLM decisions, MiMo | 137/142 |
| Hard violations | 0 |
| Downstream violations | 0 |
| Forecast setting | One fixed forecast at event start |

### 5.3.4 Figure 5.3 设计说明

**Figure 5.3 Rolling trigger-only mechanism**

#### 图的目的

展示 rolling 策略的系统机制。审稿人应从图中看出：PyResOps 并不是让 LLM 在每个 3 小时时间步都自由决策，而是先由 deterministic trigger checker 判断是否需要 LLM 介入。

#### 推荐图形类型

流程图。

#### 推荐流程

从左到右或自上而下：

1. **3h observed-state update**
   - 输入：current level、observed inflow、elapsed time、fixed forecast；
2. **Trigger checker**
   - 判断 initial；
   - 判断 scheduled_check；
   - 判断 relative_forecast_error；
   - 判断 absolute_forecast_error；
   - 判断 level_risk；
3. **Branch A: trigger fired**
   - 调用 LLM+MCP workflow；
   - 工具链：prepare → optimize → simulate → evaluate → payload submission → fail-closed validation；
4. **Branch B: no trigger**
   - deterministic retain row；
   - llm_called = false；
   - 保留当前方案并记录 audit row；
5. **Unified audit output**
   - result row；
   - session trace；
   - validation flags；
   - comparison with Stage 2 oracle。

#### 必须标注的数字

- total rolling checks = 373；
- LLM-called checks = 142；
- deterministic retain rows = 231；
- event coverage = 10/10。

#### Caption 建议

**Figure 5.3. Trigger-only rolling execution mechanism.** Each rolling step updates the observed reservoir state and evaluates trigger conditions. LLM+MCP execution is invoked only when a trigger fires; otherwise, the current plan is retained deterministically and recorded for audit.

#### 质量检查

- [ ] 不要把 retain branch 画成“没有记录”；retain 仍然必须输出 row；
- [ ] 图中必须显示 fixed forecast is not updated；
- [ ] 图中必须显示 observed state updates every 3h；
- [ ] 图中不要写 “no loss”；改写为 full event/check coverage retained。

### 5.3.5 Figure 5.4 设计说明

**Figure 5.4 Rolling call reduction and representative decision changes**

#### 图的目的

同时展示 rolling 策略的效率和真实调度过程中的决策变化。该图应包含两个层面：

1. 全局层面：373 个 rolling checks 中，142 次调用 LLM，231 次 deterministic retain；
2. 事件层面：以一个代表性 withpred 事件展示入库、下泄、水位和 rolling trigger/replan/retain 的实际变化过程。

#### 推荐图形类型

建议采用 **双面板或三面板组合图**。

**Panel A: Call distribution stacked bar**

- 单个堆叠柱；
- 总高度 373；
- 下半部分：LLM-called checks = 142；
- 上半部分：deterministic retain rows = 231；
- 标注：LLM-call reduction = 61.9%。

**Panel B: Representative rolling event hydrograph**

- 选择一个代表性事件，建议优先 `2024061623` 或 rolling 中触发较多的事件；
- x 轴：时间或 event hour；
- y 轴：flow，单位 m³/s；
- 曲线 1：observed inflow；
- 曲线 2：fixed forecast inflow，如果数据可用；
- 曲线 3：release plan / rolling release；
- 使用竖线标注 trigger-fired LLM calls；
- 使用浅色点标注 deterministic retain checks；
- trigger 类型可以用不同符号表示。

**Panel C: Reservoir level and trigger state**

- x 轴同 Panel B；
- y 轴：reservoir level，单位 m；
- 曲线：simulated/observed-updated reservoir level；
- 水平线：seasonal flood limit；
- 水平线：flood-control high level if applicable；
- 在下方用事件条显示 action：replan / retain；
- 对于 replan 节点，可标注 trigger reason。

如果版面有限，可省略 Panel C，但建议保留水位过程，因为水库调度场景需要展示水位变化。

#### 数据字段要求

- `event_id`
- `relative_hour` 或 `timestamp`
- `observed_inflow`
- `forecast_inflow` 或 `predict`
- `release`
- `reservoir_level`
- `trigger_type`
- `action`
- `llm_called`
- `accepted`
- `flood_limit_applied`

#### Caption 建议

**Figure 5.4. Rolling call reduction and representative rolling-operation process.** Panel A shows that trigger-only execution reduced LLM calls from 373 rolling checks to 142 while retaining all check records. Panels B–C illustrate a representative event, including observed inflow, fixed forecast, release decisions, reservoir-level trajectory, and trigger-driven retain/replan changes.

#### 质量检查

- [ ] 142 + 231 必须等于 373；
- [ ] call reduction 应写为 231/373 = 61.9%；
- [ ] retain checks 不调用 LLM，但必须显示为已记录；
- [ ] 代表事件中每个 replan/retain 标记应来自 rolling trigger log；
- [ ] 不绘制历史调度或原计划对比线。

---

## 5.4 LLM+MCP execution under fail-closed validation and executor sensitivity

### 5.4.1 写作目标

本节合并主执行器结果和三模型敏感性结果。这样可以保持 Results 为 4 小节结构，同时不丢失 Stage 3 的核心证据。

本节应重点回答：

1. MiMo v2.5 作为 primary executor 的 fail-closed 通过情况如何；
2. MiniMax、MiMo、Claude 三个执行器是否都保持水文安全；
3. 失败类型主要是什么；
4. 模型差异体现在哪里。

### 5.4.2 建议段落结构

第一段：框架级整体结果。说明 Stage 3 对 462 行记录进行全量尝试，三种执行器均完成全量测试，均通过 Oracle metric comparison，均无 hard violations 和 downstream violations。强调这是 executor sensitivity，不是 LLM leaderboard。

第二段：主执行器 MiMo v2.5。报告 MiMo 结果：457/462 accepted，98.9%；static 41/41；dynamic 48/48；rolling 368/373。说明 rolling 中 368 = 231 deterministic retains + 137 LLM-accepted；5 条失败均来自 142 个 LLM-called rolling records，原因均为 missing_eval_ref。

第三段：三模型对比。报告 MiniMax 451/462，MiMo 457/462，Claude 452/462。说明三者 acceptance rate 都较高，差异主要体现在 dynamic 和 failure type，而不是安全违规。

第四段：失败分类。说明 MiMo 主要是 missing_eval_ref；Claude 主要是 wrong_tool_order 和 missing_required_tool；MiniMax 两类兼有。强调所有失败均被 fail-closed gate 拒绝，因此不会被计为成功决策。

### 5.4.3 本节建议表格

**Table 5.5 Executor-level Stage 3 summary**

| Executor | Total attempted | Accepted | Acceptance rate | Oracle metric comparison | Hard viol. | Downstream viol. |
|---|---:|---:|---:|---|---:|---:|
| MiniMax M2.5 | 462 | 451 | 97.6% | PASS | 0 | 0 |
| MiMo v2.5 | 462 | 457 | 98.9% | PASS | 0 | 0 |
| Claude Haiku 4.5 | 462 | 452 | 97.8% | PASS | 0 | 0 |

**Table 5.6 Results by workflow and executor**

| Workflow | MiniMax M2.5 | MiMo v2.5 | Claude Haiku 4.5 |
|---|---:|---:|---:|
| Static | 41/41 | 41/41 | 41/41 |
| Dynamic | 43/48 | 48/48 | 41/48 |
| Rolling | 367/373 | 368/373 | 370/373 |
| Total | 451/462 | 457/462 | 452/462 |

**Table 5.7 Failure taxonomy by executor**

| Failure reason | MiniMax M2.5 | MiMo v2.5 | Claude Haiku 4.5 |
|---|---:|---:|---:|
| wrong_tool_order | 4 | 0 | 7 |
| missing_required_tool | 3 | 0 | 3 |
| missing_eval_ref | 4 | 5 | 0 |
| Total rejected | 11 | 5 | 10 |

### 5.4.4 Figure 5.5 设计说明

**Figure 5.5 Fail-closed acceptance by workflow and executor**

#### 图的目的

展示三种执行器在 static、dynamic 和 rolling 三类 workflow 上的 fail-closed 接受情况。重点是执行成功率和水库调度工作流之间的关系，而不是模型排名。

#### 推荐图形类型

分组柱状图。

#### x 轴和 y 轴

- x 轴：workflow type，即 static、dynamic、rolling、total；
- y 轴：fail-closed acceptance rate，0–100%；
- 每组包含三根柱：MiniMax、MiMo、Claude；
- 在柱顶标注 accepted/total，如 48/48、368/373。

#### 必须体现的信息

- static 三个模型均为 100%；
- MiMo dynamic 为 48/48；
- rolling 三个模型差异较小；
- total acceptance rates 分别为 97.6%、98.9%、97.8%。

#### 视觉要求

- y 轴建议从 80% 开始或从 0 开始均可。如果从 80% 开始，必须在 caption 中说明；
- 推荐从 0 开始，更稳妥；
- 不要用排名箭头或冠军标识；
- 使用简洁颜色，不要过度强调模型优劣。

#### Caption 建议

**Figure 5.5. Fail-closed acceptance rates by workflow and executor.** All three executors completed the full 462-record evaluation without hard-safety or downstream-routing violations. Differences mainly reflect workflow-protocol and evidence-binding behavior rather than hydrological computation failures.

#### 数据字段要求

- `executor`
- `workflow`
- `accepted`
- `total`
- `acceptance_rate`

#### 质量检查

- [ ] static 三个模型均为 41/41；
- [ ] MiMo total 为 457/462；
- [ ] Claude rolling 为 370/373；
- [ ] 不要将图标题写成 model benchmark。

### 5.4.5 Figure 5.6 设计说明

**Figure 5.6 Failure modes under fail-closed validation**

#### 图的目的

展示被拒绝记录的失败类型，说明 LLM 层的主要问题是协议遵循和证据绑定，而不是水文安全失败。

#### 推荐图形类型

分组柱状图或堆叠柱状图。推荐堆叠柱状图：

- x 轴：executor；
- y 轴：number of rejected records；
- 堆叠类别：wrong_tool_order、missing_required_tool、missing_eval_ref。

也可以采用分组柱状图：

- x 轴：failure reason；
- 不同颜色：executor。

若论文版面紧张，堆叠柱状图更紧凑。

#### 必须体现的信息

- MiniMax 总失败 11；
- MiMo 总失败 5，全部 missing_eval_ref；
- Claude 总失败 10，其中 wrong_tool_order 7、missing_required_tool 3；
- hard violation 和 downstream violation 不应放进堆叠柱，因为它们均为 0；可以在图注中说明。

#### Caption 建议

**Figure 5.6. Failure taxonomy of rejected LLM+MCP decisions.** Rejected records were caused by protocol-order errors, missing required tools, or missing evaluation references. No rejected or accepted record involved a hydrological hard-safety or downstream-routing violation.

#### 数据字段要求

- `executor`
- `failure_reason`
- `count`

#### 质量检查

- [ ] MiniMax: 4 + 3 + 4 = 11；
- [ ] MiMo: 0 + 0 + 5 = 5；
- [ ] Claude: 7 + 3 + 0 = 10；
- [ ] 图注必须说明 0 hard violations 和 0 downstream violations；
- [ ] 不要用“模型失败”这种宽泛说法，应写“rejected by fail-closed validation”。

---

# 主文图表总清单

## 主文图

| Figure | Title | Main purpose | Data source |
|---|---|---|---|
| Figure 5.1 | Stage 1–3 validation pipeline | 展示三阶段验证链条 | Stage 1/2/3 summaries |
| Figure 5.2 | Representative static and dynamic release-planning cases | 展示入库、下泄、水位和 retain/replan 过程 | Stage 1 trajectories + dynamic logs |
| Figure 5.3 | Rolling trigger-only mechanism | 展示 rolling 触发逻辑 | Stage 3 design / logs |
| Figure 5.4 | Rolling call reduction and representative decision changes | 展示 LLM 调用减少和真实 rolling 决策变化 | Stage 3 rolling logs + trajectories |
| Figure 5.5 | Fail-closed acceptance by workflow and executor | 展示执行成功情况 | Stage 3 model summaries |
| Figure 5.6 | Failure modes under fail-closed validation | 展示失败类型 | Stage 3 failure taxonomy |

## 主文表

| Table | Title | Main purpose |
|---|---|---|
| Table 5.1 | Scenario and oracle coverage | 场景、行数和 oracle 覆盖 |
| Table 5.2 | Static deterministic results by flood group | static 分组结果 |
| Table 5.3 | Dynamic deterministic results | dynamic retain/replan 结果 |
| Table 5.4 | Rolling trigger-only results | rolling 调用减少与覆盖结果 |
| Table 5.5 | Executor-level Stage 3 summary | 三模型总体结果 |
| Table 5.6 | Results by workflow and executor | 三模型分 workflow 结果 |
| Table 5.7 | Failure taxonomy by executor | 三模型失败类型 |

---

# 绘图脚本总体要求

## 输出目录

建议将所有第 5 章图表输出到：

```text
experiments/figures/chapter5/
```

建议文件名：

```text
fig5_1_validation_pipeline.png
fig5_2_static_dynamic_cases.png
fig5_3_rolling_trigger_mechanism.png
fig5_4_rolling_call_reduction_process.png
fig5_5_acceptance_by_workflow_executor.png
fig5_6_failure_taxonomy.png
```

表格导出到：

```text
experiments/figures/chapter5/tables/
```

## 绘图风格

- 面向 ESWA 正文图，优先简洁、清晰、可读；
- 不使用 3D 图；
- 不使用过多颜色；
- 时间序列图必须单位清晰；
- 水位和流量不要放在同一个 y 轴；
- 图中英文术语要统一：inflow、release、reservoir level、replan、retain、fail-closed accepted；
- 图注中不要出现过度宣传语。

## 必须进行的数字一致性检查

绘图前后都要检查：

- [ ] 41 + 48 + 373 = 462；
- [ ] 142 + 231 = 373；
- [ ] 231 / 373 = 61.9%；
- [ ] MiMo: 41 + 48 + 368 = 457；
- [ ] MiMo rolling: 231 + 137 = 368；
- [ ] MiniMax: 41 + 43 + 367 = 451；
- [ ] Claude: 41 + 41 + 370 = 452；
- [ ] MiniMax failures: 4 + 3 + 4 = 11；
- [ ] MiMo failures: 5；
- [ ] Claude failures: 7 + 3 = 10；
- [ ] hard violations = 0 for all executors；
- [ ] downstream violations = 0 for all executors。

---

# 给 Codex 的执行指令

下面这段可直接发给 Codex 或代码助手。

```text
Please implement Chapter 5 figure and table generation for the PyResOps ESWA manuscript.

Use the 4-section Results structure:
5.1 Scenario construction and deterministic oracle
5.2 Deterministic release planning under static and dynamic workflows
5.3 Rolling operation with trigger-only LLM intervention
5.4 LLM+MCP execution under fail-closed validation and executor sensitivity

Do not create a 5-section or 7-section structure.

Generate figures and table CSVs under:
experiments/figures/chapter5/
experiments/figures/chapter5/tables/

Required figures:
1. fig5_1_validation_pipeline.png
   - Three-stage validation pipeline: Stage 1 direct service → Stage 2 workflow oracle → Stage 3 LLM+MCP.
   - Include row counts: static 41, dynamic 48, rolling 373, total 462.

2. fig5_2_static_dynamic_cases.png
   - Representative reservoir-operation process figure.
   - Show observed inflow, optimized release, reservoir level, flood-limit line, and dynamic retain/replan decisions.
   - Do not compare with historical operation or original operation plan.
   - Use 2–3 representative events, preferably including 2024061623 if data are available.

3. fig5_3_rolling_trigger_mechanism.png
   - Flowchart of rolling trigger-only mechanism.
   - Show 3h observed-state update, fixed forecast, trigger checker, LLM+MCP branch, deterministic retain branch, and fail-closed audit output.

4. fig5_4_rolling_call_reduction_process.png
   - Panel A: stacked bar showing LLM-called checks = 142 and deterministic retain rows = 231 out of total 373.
   - Panel B/C: representative rolling event process showing observed inflow, fixed forecast if available, release, reservoir level, and trigger/replan/retain markers.
   - Do not write “no loss”; use “full event/check coverage retained”.

5. fig5_5_acceptance_by_workflow_executor.png
   - Grouped bar chart of fail-closed acceptance rate by workflow and executor.
   - Executors: MiniMax M2.5, MiMo v2.5, Claude Haiku 4.5.
   - Workflows: static, dynamic, rolling, total.
   - Label bars with accepted/total.

6. fig5_6_failure_taxonomy.png
   - Stacked or grouped bar chart of failure taxonomy.
   - Failure categories: wrong_tool_order, missing_required_tool, missing_eval_ref.
   - Do not include hard_violation/downstream_violation bars because they are zero; mention zero safety violations in caption.

Required table CSV exports:
- table5_1_scenario_oracle_coverage.csv
- table5_2_static_by_flood_group.csv
- table5_3_dynamic_results.csv
- table5_4_rolling_trigger_only.csv
- table5_5_executor_stage3_summary.csv
- table5_6_workflow_by_executor.csv
- table5_7_failure_taxonomy.csv

Data sources:
- experiments/results/stage1/
- experiments/results/stage2/
- experiments/results/stage3/                 # MiniMax
- experiments/results/stage3_mimo_v25/        # MiMo
- experiments/results/stage3_claude_haiku_4_5/ # Claude

Important constraints:
- Do not plot historical operation or original operation plan.
- For hydrological process figures, only plot reservoir process: inflow, release, water level, flood-limit line, and decision markers.
- Use “inflow-peak attenuation rate”.
- Use “Oracle metric comparison: PASS”.
- Treat model comparison as executor sensitivity, not LLM ranking.
- Verify all numeric consistency checks before saving figures.
```

---

# 最终建议

第 5 章采用 4 节结构是合适的。图表中最关键的是 **Figure 5.2** 和 **Figure 5.4**，因为它们把系统执行成功情况与真实水库调度过程连接起来。其余图表负责证明 fail-closed 接受率、LLM 调用减少和失败模式。

Results 章节应保持克制：说明系统在这些真实洪水场景下可以生成可执行、可审计、无水文安全违规的下泄方案；不要把结果写成对历史人工调度或原计划的优劣比较。
