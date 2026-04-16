# PyResOps Experiments 当前执行总结（中文）

生成时间：2026-04-10  
项目路径：`E:\PyCode\PyResOps`  
分析范围：`experiments/*.py` 与 `experiments/results/**/*`

## 1. 总体结论

当前实验代码已经形成完整的“静态基线 + 动态多轮触发”评估框架，主入口清晰、结果落盘结构完整。  
从现有结果文件看，静态基线结果整体稳定；动态结果存在明显“不同时间批次混写/覆盖”的现象，导致部分场景（尤其 S02/S03/S04/S05）的动态结论不能直接与最新静态基线横向比较。

## 2. 执行入口与产物结构

主要入口：

1. `experiments/run_experiments.py`
2. `experiments/paper_experiment_runner.py`
3. `experiments/dynamic_experiment.py`
4. `experiments/scripts/run_scenario_experiment.py`

核心执行路径（论文实验）：

1. `run_experiments.py --paper`
2. 调用 `run_paper_experiments()`
3. 先执行 `run_all_static_baselines()`
4. 再执行 `run_all_multi_round(max_rounds=3)`
5. 汇总成 `paper_summary_*.json`（若执行该入口）

结果目录约定：

1. `experiments/results/static/{scenario}_baseline.json`
2. `experiments/results/dynamic/{scenario}_round{n}.json`
3. `experiments/results/dynamic/{scenario}_summary.json`

## 3. 代码层执行逻辑（简要）

### 3.1 模型与 Agent 逻辑

`paper_experiment_runner.py` 中：

1. `_load_model_config()` 从 `experiments/config.yml` 读取 `models.<profile>`
2. `_build_agno_model()` 按 `provider` 构建模型实例（`anthropic/deepseek/dashscope/openai_like/opencode`）
3. `AgnoMCPExperiment.run_scenario()` 执行 Agent：
4. 读取 `run_response.tools` 统计工具调用次数
5. 从最终文本里用正则抽取 `outflow`
6. 返回结构化结果（`outflow/tool_call_count/final_decision_text`）

### 3.2 评估逻辑

`evaluation_metrics.py` 中 `_run_pyresops_eval()` 固定用 pyresops 做同构评估：

1. 构造统一 `ReservoirSpec`
2. 用 `ConstantReleaseModule(target_flow=outflow)` 做仿真
3. 用 `EvaluationService` 输出五维评分
4. 统计 3 条约束下的违反数（死水位、正常蓄水位、最小生态流量）

`DynamicAdjustmentEvaluator` 额外定义：

1. `constraint_achievement_rate = (3 - violations) / 3`
2. 趋势阈值：`after-before > 0.01` 为 improved；`< -0.01` 为 degraded；否则 maintained

## 4. 动态实验执行逻辑（重点，`dynamic_experiment.py`）

### 4.1 场景与触发建模

每个场景（S01~S05）预定义 3 个按顺序触发的动态事件 `DYNAMIC_TRIGGERS`。  
每个触发项包含：

1. `round`
2. `type`
3. `natural_lang`
4. `adjusted_inflow`（可为空，空表示不改入流）

`_apply_trigger()` 的行为：

1. 若 `adjusted_inflow` 非空，则同步改写 `scenario["inflow"]` 与 `scenario["initial_inflow"]`
2. 写入 `dynamic_trigger` 与 `trigger_type`
3. 在 `description` 上拼接“动态调整 + 触发文本”

### 4.2 单场景多轮算法（`run_multi_round_dynamic_experiment`）

执行流程：

1. Phase 0 先跑“无触发 baseline”
2. baseline 结果作为所有轮次共同参照（`baseline_score/baseline_rate`）
3. 对第 `n` 轮（n=1..max_rounds）：
4. 从原始场景重新开始（`current_scenario = scenario.copy()`）
5. 顺序应用前 `n` 个触发（累积触发）
6. 每触发一次就调用一次 `experiment.run_scenario(adjusted_scenario)`
7. 对每次调整后的出库流量调用 `_eval_scenario()` 打分
8. 记录单步 delta（出流、score、约束率、trend）
9. 汇总成 `round_result` 写入 `.../dynamic/{sid}_round{n}.json`
10. 全部轮次完成后写 `.../dynamic/{sid}_summary.json`

关键点：

1. 轮次是“前 n 个触发事件的累积响应”，不是在上一轮产物文件上直接续跑
2. 每轮总工具调用数 = baseline 调用数 + 本轮每次触发后的调用数累加
3. `best_round` 以 `final_score` 最大值确定

### 4.3 批量接口

1. `run_all_multi_round()`：默认跑 S01~S05，通常用于论文实验主流程
2. `run_dynamic_experiments()`：兼容旧接口，只跑单轮（`max_rounds=1`，默认 S01~S03）

## 5. 当前 results 快照（基于现有文件）

### 5.1 静态基线（`experiments/results/static`）

| 场景 | overall | 约束达成率 | 违反数 | 工具调用 | 出流(m3/s) | 文件时间 |
|---|---:|---:|---:|---:|---:|---|
| S01 | 78.2413 | 1.0000 | 0 | 10 | 300.0 | 2026-04-09 21:46:35 |
| S02 | 91.6710 | 1.0000 | 0 | 15 | 3380.0 | 2026-04-09 22:20:51 |
| S03 | 36.0390 | 0.6667 | 1 | 8 | 8000.0 | 2026-04-09 21:48:50 |
| S04 | 80.7531 | 1.0000 | 0 | 10 | 70.0 | 2026-04-09 21:49:51 |
| S05 | 73.3017 | 1.0000 | 0 | 13 | 500.0 | 2026-04-09 21:51:12 |

静态基线均值：

1. 平均 overall：`72.0012`
2. 平均约束达成率：`0.9333`
3. 平均工具调用：`11.2`

### 5.2 动态多轮（`experiments/results/dynamic`）

当前 `*_summary.json` 反映的数据：

| 场景 | baseline_score | baseline_rate | 已汇总轮次 | best_round | 关键现象 |
|---|---:|---:|---|---:|---|
| S01 | 78.2413 | 1.0000 | round_1~round_3 | 3 | 3轮持续增益，R3=80.2365，工具调用43 |
| S02 | 91.6710 | 1.0000 | round_1 | 1 | summary 仅含1轮，且与 baseline 持平 |
| S03 | 13.5000 | 0.3333 | round_1~round_3 | 1 | 各轮工具调用均为0，出流0 |
| S04 | 34.4375 | 0.6667 | round_1~round_3 | 1 | 各轮工具调用均为0，R1后下降到30.2353 |
| S05 | 29.4623 | 0.3333 | round_1~round_3 | 1 | 各轮工具调用均为0，出流0 |

## 6. 当前执行状态判断

### 6.1 可确认的正向信号

1. 动态框架本身逻辑完整，数据结构设计合理
2. S01 的多轮动态结果符合预期（触发越多，评分越高，出流响应明显）
3. S02 的 round1/round2 文件显示在高分约束满足状态下“策略保持”是可解释的

### 6.2 结果一致性风险（当前最需要注意）

1. `S02_summary.json` 只包含 round_1，但 `S02_round2.json`、`S02_round3.json` 存在且时间戳更早，说明 summary 被后续单轮运行覆盖
2. S03/S04/S05 动态结果大量出现 `tool_calls=0` 与 `outflow=0`，与较晚时间的静态基线表现明显不一致
3. 结果目录是“按场景固定文件名覆盖写入”，不同批次运行会混合在同一目录，导致当前快照不具备严格同批可比性

## 7. 建议的下一步（为了得到可发布结论）

1. 用同一个模型配置一次性重跑 `run_experiments.py --paper --model <profile>`
2. 运行前清理或归档 `experiments/results/static` 与 `experiments/results/dynamic`
3. 每次运行输出到带时间戳的独立子目录，避免 summary 被后续单场景执行覆盖
4. 对 S03/S04/S05 增加“工具调用数为0时的告警字段”，并在 summary 中标注为无效轮次

