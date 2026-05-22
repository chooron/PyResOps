# Experiments Results README

本文档说明 `experiments/results/` 下已经开展的实验、使用的模型、各文件夹用途和主要结果。目录中保留了多轮中间实验、修复前后对比实验和论文用冻结结果；阅读时建议优先看“推荐主结果”部分，不要把历史中间 run 混同为最终论文统计。

## 快速结论

- 数据集冻结：`41` 场真实洪水事件，其中 `29` 场 `strict_clean`，`12` 场 `repaired_executable`，`0` 场 `diagnostic_only`。
- 工具基线：`tools_only` / `deterministic_tools_only` 在主要大样本验证中达到 `166/166 = 100%`，硬约束违规为 `0`。
- MiMo 主模型：主要使用 `mimo_v25`，底层模型记录为 MiMo v2.5，用于 MCPTools、MCP skill、命令挑战和 10 场真实预测滚动调度。
- 10 场真实预测 rolling 主结果：`mimo-rolling_20260512_082639_713975`，`93` 个 rolling stage，成功 `87/93 = 93.55%`，硬约束违规 `0`。失败集中在 evidence-binding / auditability，不是水库调度硬约束失败。
- rolling targeted rerun：只重跑原始 6 个 evidence/protocol failure stage，`6/6` 成功，硬约束违规 `0`，reference valid `6/6`。该 rerun 作为 robustness check，不能替代原始 93-stage 主统计。
- 命令挑战冻结：`command-challenge_20260509_102905_489757`，B4/MCPTools+Skill 在 40 个 frozen command cases 上 command following、结构化输出、协议遵循和 evaluation reference valid 均为 `0.9750`，硬约束违规 `0`。
- 消融实验：B4/MCPTools+Skill 在 component ablation 子集上 static/dynamic/rolling 均达到 `1.0` success/protocol/structured/reference rates；B2 无工具输出缺少真实 evaluation reference，B3 暴露工具顺序和协议问题。

## 模型与方法说明

| 名称 | 含义 | 用途 |
|---|---|---|
| `tools_only` / `deterministic_tools_only` | 不调用 LLM，直接使用 PyResOps 工具链 | 数据与调度可执行性基线 |
| `pyresops_direct` | 直接库调用基线 | L0/L4 对照中的直接执行层 |
| `mimo_without_tools` / L2 | MiMo 纯文本输出，不接真实工具 | 验证无工具时的 evidence/reference 缺口 |
| `mimo_mcp_no_skill` / B3 | MiMo + MCPTools，但没有 skill 协议约束 | 验证工具可用但协议未强化时的失败模式 |
| `mimo_mcp_skill` / B4 | MiMo + MCPTools + workflow skill contract | 论文主系统之一，强调工具链、协议和 evidence binding |
| `mimo_mcp_validator` / L4 | MiMo + MCPTools + final payload validator | MiMo 主验证 runner，滚动预测实验使用该方法 |
| `mimo_v25` | MiMo v2.5 profile | 主要论文实验模型 |
| `deepseek_v4_pro` / `deepseek_v4_flash` | DeepSeek profile | 交叉模型补充；部分 run 受 provider/account 或协议兼容问题影响 |
| `gemini_3_1_flash_lite` | Gemini profile | 交叉模型补充 |
| `minimax_m2_5_free` | MiniMax profile | 交叉模型补充 |
| `qwen3_6_flash` | Qwen profile | smoke / cross-model 补充 |

## 文件命名规则

多数 run 目录遵循同一组输出文件：

| 文件后缀 | 内容 |
|---|---|
| `*.jsonl` | stage 级原始记录，包含 payload、工具调用、final answer、trace 等 |
| `*_summary.csv` | stage 级汇总表，适合统计成功率、失败原因、硬约束违规 |
| `*_summary.md` | 对应 run 的简短文字汇总 |
| `*_failure_audit.csv` | 失败 stage 明细，用于定位 failure taxonomy 和 failure reason |
| `*_metadata.json` | run_id、phase、model_profile、git hash、数据/配置 hash |
| `*_config_snapshot.json` | 当次运行使用的配置快照 |
| `tables/*.csv` | 面向论文表格或跨实验汇总的派生表 |

## 顶层目录说明

### `data_quality/`

用途：冻结真实洪水数据集和数据质量分类。

关键文件：

- `dataset_freeze_report.md`
- `event_quality_manifest.csv`

主要结果：

- 总事件数：`41`
- `strict_clean`：`29`
- `repaired_executable`：`12`
- `diagnostic_only`：`0`
- 修复策略包括：缺失 outflow 用 inflow fallback、缺失 inflow 行删除、缺失水位线性插值。

论文使用建议：作为所有真实数据实验的 dataset freeze 依据。若论文报告 denominator，应明确区分 strict clean 与 repaired executable。

### `mcp_schema_audit/`

用途：审计 MCP server 暴露的工具 schema 和核心工具是否存在。

关键文件：

- `mcp_schema_audit.md`
- `mcp_schema_audit.json`

主要结果：

- MCP tool count：`26`
- 核心 paper-validation 工具均存在：`prepare_event`、`optimize_release_plan`、`simulate_release_plan`、`evaluate_release_plan`、`run_static_workflow`、`run_dynamic_stage`、`run_rolling_stage`、`validate_decision_payload`、`check_hard_constraints`。

论文使用建议：作为 MCPTools 工具链可审计性的基础证据。

### `minimal_validation/`

用途：早期最小真实数据验证，覆盖 static / dynamic / rolling，包含 deterministic tools 和早期 `deepseek` full_agent。

关键 run：

- `minimal_validation_20260507_172404`：`90` records，成功 `88/90 = 97.78%`
- `minimal_validation_20260507_174129`：`68` records，成功 `65/68 = 95.59%`
- `minimal_validation_20260507_175340`：`67` records，成功 `63/67 = 94.03%`

主要失败：真实数据窗口中缺失 outflow、dynamic carry-over evaluation 缺失等。

论文使用建议：这是早期 smoke/minimal validation，不建议作为最终主表；可用于说明实验管线演进。

### `large_validation/`

用途：大样本真实数据验证和工具基线迭代，主要是 deterministic `tools_only` 验证 static / dynamic / rolling 的可执行性。

关键稳定 run：

- `large_validation_20260508_145408_194581`
- `large_validation_20260508_151930_727432`
- `large_validation_20260508_152903_448600`
- `large_validation_20260508_152956_889627`

这些稳定 run 均为：

- `166` stage records
- `166/166 = 100%`
- strict clean / repaired executable 成功率均为 `100%`
- 硬约束违规 `0`
- 覆盖 static、dynamic、rolling

目录中更早的 `20260507` 和 `20260508` 中间 run 保留了数据清洗和协议修复前的失败记录，例如缺失 inflow/outflow、非单调时间轴、`non_positive_outflow` 等。

论文使用建议：使用最新稳定 `166/166` 工具基线，历史 run 只用于内部追溯。

### `paper_validation/`

用途：论文实验主目录，包含 data freeze、MCP skill、MiMo L0-L4 对照、component ablation、command challenge、cross-model validation、payload repair audit 和 rolling targeted rerun。

建议优先阅读：

- `paper_results_outline.md`
- `mcp_skill_validation_v1_freeze.md`
- `ablation_current_status.md`
- `phase_g_mimo_command_challenge_freeze.md`
- `success_semantics_report.md`
- `tables/`

主要实验系列如下。

#### Tools baseline

文件：

- `tools-baseline_20260508_094658_921724_summary.csv`
- `tables/library_baseline_tools_only.csv`

结果：

- `166/166 = 100%`
- 覆盖 static / dynamic / rolling
- 硬约束违规 `0`

用途：证明 PyResOps 工具链在冻结数据集上可执行，LLM 失败不应归因于水库计算不可行。

#### L0-L4 对照

关键 run：

- `l0-l4_20260508_123528_056280`

结果：

- `160/160 = 100%`
- 模型/方法包括 `pyresops_direct`、`tools_only`、`mimo_without_tools`、`mimo_with_pyresops_tools`、`mimo_mcp_validator`

用途：比较从直接工具、无工具 LLM、带工具 LLM 到 MCP validator 的层级效果。

#### MiMo static / dynamic / rolling validator

关键 run：

- `mimo-static_20260508_103148_257687`：`41/41 = 100%`
- `mimo-dynamic_20260508_104505_491153`：`44/44 = 100%`
- `mimo-rolling_20260508_110501_847133`：`10/10 = 100%`

用途：MiMo + MCP validator 在代表性 static / dynamic / rolling 任务上的早期稳定验证。注意它们不是后续 10 场真实预测 rolling 的 93-stage 主实验。

#### MCPTools + Skill validation

关键文件：

- `mcp_skill_latest_combined_summary.csv`
- `mcp_skill_validation_v1_freeze.md`
- `tables/mcp_skill_static_summary.csv`
- `tables/mcp_skill_dynamic_summary.csv`
- `tables/mcp_skill_rolling_summary.csv`

主要结果：

- latest combined：`119/121 = 98.35%`
- MCP transport / tools list / tool call success 在主 run 中均可审计
- 失败主要是少量 final payload 或 protocol 问题

用途：验证 workflow skill contract 对工具调用顺序、结构化输出和 evidence reference 的约束作用。

#### Component ablation

关键 run：

- `component-ablation_20260509_041755_523620`

关键表：

- `tables/ablation_b2_b3_b4_summary.csv`
- `tables/component_contribution_summary.csv`

总体结果：

- 全部方法合计：`107/112 = 95.54%`
- 硬约束违规 `0`
- B4/MCPTools+Skill 在 static、dynamic、rolling 三类子集上均为 `1.0` success、protocol、structured 和 evaluation reference valid。
- B2/L2 虽然能输出格式化数值，但 `evaluation_reference_valid_rate = 0.0`，说明无真实工具 evidence。
- B3 提供 MCPTools 后 reference valid 明显改善，但 static/rolling 仍有协议和工具顺序问题。

用途：论文中用于说明 Skill+Validator 相比单纯 LLM 或单纯 MCPTools 的贡献。

#### Command challenge

冻结 run：

- `command-challenge_20260509_102905_489757`

关键文件：

- `phase_g_mimo_command_challenge_freeze.md`
- `tables/command_challenge_summary.csv`
- `tables/command_challenge_b4_failure_audit.csv`

结果：

- 总记录：`120`
- 方法：B2/L2、B3、B4，各 `40` 条 command cases
- B4 command cases：static `10`、dynamic `20`、rolling `10`
- B4 指标：
  - command_following_success_rate：`0.9750`
  - feasible_command_success_rate：`0.9643`
  - infeasible_command_detection_rate：`1.0000`
  - unsafe_command_rejection_rate：`1.0000`
  - structured_output_valid_rate：`0.9750`
  - protocol_adherence_rate：`0.9750`
  - evaluation_reference_valid_rate：`0.9750`
  - hard_constraint_violation_count：`0`

用途：验证 agent 面对正常、保守、削峰、多目标、模糊、冲突、不可能和不完整指令时的命令遵循与安全拒绝能力。

#### Payload repair audit

关键 run：

- `payload-repair-audit_20260509_142153_056064`

关键表：

- `tables/payload_repair_audit.csv`

用途：对已存在的 invalid payload 做 repair-only audit，不调用 MCP tools，不删除原始失败记录。用于区分格式/结构化输出问题与实际调度失败。

#### Cross-model validation

目录：

- `paper_validation/cross_model_runs/`
- `paper_validation/compact_context_validation/cross_model_runs/`
- `paper_validation/cross_model_feedback_checks/`
- `paper_validation/compact_context_validation/cross_model_feedback_checks/`

模型：

- `deepseek_v4_flash`
- `gemini_3_1_flash_lite`
- `minimax_m2_5_free`
- `qwen3_6_flash`
- `mimo_v25`（compact context run 中也有）

原始 cross-model summary：

- `deepseek_v4_flash`：`3/56 = 5.36%`
- `gemini_3_1_flash_lite`：`2/56 = 3.57%`
- `minimax_m2_5_free`：`48/66 = 72.73%`
- `qwen3_6_flash`：smoke `0/2`

compact context validation summary：

- `mimo_v25`：`75/77 = 97.40%`
- `minimax_m2_5_free`：`49/63 = 77.78%`
- `gemini_3_1_flash_lite`：`13/56 = 23.21%`
- `deepseek_v4_flash`：smoke `0/2`

解释：

- Cross-model 结果主要用于补充说明模型迁移性和协议执行差异。
- DeepSeek 早期记录包含 provider/account 或 reasoning-content 兼容问题，不能简单解释为水库调度能力失败。
- MiMo 是本项目主模型，非 MiMo 结果建议放在 supplemental / robustness discussion。

#### Model call smoke

文件：

- `model_call_smoke_*.json`

用途：检查不同模型 profile 的 API 连通性、base_url、token 返回和错误状态。最新 smoke 显示 DeepSeek、Gemini、MiniMax、Qwen 等 profile 均曾完成连通性检查，但个别历史文件保留了 429、503 或模型路由错误。

#### Rolling targeted rerun

目录：

- `paper_validation/rolling_targeted_rerun/`

关键 run：

- `rolling_targeted_rerun_20260512_124508_332029`

关键文件：

- `rolling_targeted_rerun_report.md`
- `rolling_targeted_rerun_comparison.csv`
- `rolling_targeted_rerun_20260512_124508_332029_summary.csv`

结果：

- 原始来源：`mimo-rolling_20260512_082639_713975`
- 只重跑原始 6 个 evidence/protocol failure stage
- targeted rerun：`6/6` 成功
- hard constraint violation：`0`
- reference valid：`6/6`
- 不覆盖原始 93-stage 主结果

用途：证明 evidence-binding 修复后，原始 rolling 失败没有系统性复现；用于 robustness check，不用于提高主实验成功率。

### `mimo_rolling_2024072617/`

用途：10 场真实预测 rolling 重点实验目录。这里是当前 rolling 场景最重要的主结果之一。

关键文件：

- `mimo-rolling_20260512_082639_713975.jsonl`
- `mimo-rolling_20260512_082639_713975_summary.csv`
- `mimo-rolling_20260512_082639_713975_failure_audit.csv`
- `rolling_mimo_10_event_comprehensive_analysis.md`
- `rolling_mimo_10_event_event_summary.csv`
- `rolling_mimo_10_event_trigger_summary.csv`

主结果：

- 事件数：`10`
- rolling stages：`93`
- success：`87/93 = 93.55%`
- hard_constraint_violation_count：`0`
- MCP tool calls：`391` success / `0` failed
- failures：`6`
  - `hallucinated_evaluation_reference`：`4`
  - `missing_evaluation_reference`：`1`
  - `missing_required_tool`：`1`

解释：

- 失败定位为 auditability / evidence-binding failure，而不是 hydrological operation failure。
- 原始结果必须保留，不能被 targeted rerun 覆盖。
- 对应 targeted rerun 在 `paper_validation/rolling_targeted_rerun/` 中。

### `realdata/`

当前仅保留占位文件 `.gitkeep`，没有主要结果。真实数据实验结果已经归档到 `minimal_validation/`、`large_validation/`、`paper_validation/` 和 `mimo_rolling_2024072617/`。

## 推荐论文主结果引用顺序

1. 数据集：`data_quality/dataset_freeze_report.md`
2. 工具可执行基线：`paper_validation/tools-baseline_20260508_094658_921724_summary.csv` 和 `paper_validation/tables/library_baseline_tools_only.csv`
3. L0-L4 总体对照：`paper_validation/l0-l4_20260508_123528_056280_summary.csv`
4. MCPTools + Skill freeze：`paper_validation/mcp_skill_validation_v1_freeze.md`
5. Component ablation：`paper_validation/tables/ablation_b2_b3_b4_summary.csv`
6. Command challenge：`paper_validation/phase_g_mimo_command_challenge_freeze.md`
7. 10-event real forecast rolling 主实验：`mimo_rolling_2024072617/rolling_mimo_10_event_comprehensive_analysis.md`
8. Rolling evidence-binding robustness check：`paper_validation/rolling_targeted_rerun/rolling_targeted_rerun_report.md`
9. Cross-model supplemental：`paper_validation/compact_context_validation/tables/cross_model_phase_g_summary.csv`

## 注意事项

- 不要把 `rolling_targeted_rerun` 的 `6/6` 成功率替代原始 10-event rolling 的 `87/93` 主统计。
- 不要把早期失败 run 删除或从统计中静默排除；这些文件用于追踪数据清洗、协议修复和 evidence-binding 修复过程。
- 对 LLM agent 的成功应优先使用 auditable success：需要真实工具调用、结构化 final payload、有效 evaluation reference、协议遵循和硬约束验证。
- `jsonl` 中包含大量 tool trace 和 final text，日常汇报优先读 `summary.csv`、`failure_audit.csv`、`tables/*.csv` 和对应 `*.md` 报告。


