# 水库调度实验说明

## 概览

本目录当前包含三类主要实验：

1. 实验1：静态场景对比
2. 实验2：动态指令变更场景
3. 实验3：预测-实际偏差场景下的滚动控制能力对比

当前默认模型配置在 `experiments/config/llm_config.yml` 中，默认使用 `deepseek`。实验3建议只使用这一条模型链路做正式验证，避免不同提供方的接口兼容差异影响结果可重复性。

## 关键配置文件

- `experiments/config/llm_config.yml`
  - 控制模型 profile、默认模型、API 配置
- `experiments/config/scenarios_config.yaml`
  - 控制场景参数、动态触发、自动化实验参数、实验3偏差场景与控制器参数

实验3相关设置已经尽量外置到 `config/scenarios_config.yaml`，包括：

- 偏差基线场景 ID：`baseline_deviation_id`
- 伪数据生成方式：`deviation_generation`
- 可重复性参数：`reproducibility.llm_seed`、`reproducibility.expected_update_count`
- 控制器参数：`controller_config`
- 偏差场景定义：`deviation_scenarios`

## 实验3是什么

实验3不再测试“系统会不会滚动更新”，而是测试：

- `static`：初始方案固定执行
- `rule_based`：按既有规则做确定性修正
- `llm_tool`：LLM 在规则边界内调用现有调度工具修正方案

在预测来水与实际来水存在结构化偏差时，三种控制方式谁能更稳定地维持安全、效果和修正能力。

当前实验3仅覆盖：

- `S02`：梅汛期错峰调度
- `S04`：枯水期发电优化

## 实验3配置结构

### 1. 偏差基线

每个实验3场景都必须显式配置：

```yaml
baseline_deviation_id: S02-D0
```

系统会先使用这个无偏差基线计算同控制器的参考得分，再计算其他偏差场景的 `performance_degradation`。

缺少这个配置时，代码会直接失败，不再静默回退。

### 2. 伪数据生成

`S02` 使用基于“参考洪水过程线”的确定性变换：

```yaml
deviation_generation:
  mode: hydrograph_transform
  reference_elapsed_hours: [0, 6, 12, 18, 24, 30, 36, 42]
  reference_forecast_sequence: [2800.0, 2945.0, 3090.0, 3235.0, 3380.0, 3235.0, 3090.0, 2945.0]
  reference_base_flow: 2800.0
  reference_peak_flow: 3380.0
  reference_peak_hour: 24
  clamp_min_flow: 0.0
```

生成逻辑：

1. 以 `reference_forecast_sequence` 作为原始洪水过程
2. 按偏差场景中的 `forecast_peak_flow/forecast_peak_hour` 对预测过程做确定性平移和缩放
3. 按偏差场景中的 `actual_peak_flow/actual_peak_hour` 对真实过程做确定性平移和缩放
4. 输出固定时间格点上的 `forecast_inflow` 与 `actual_inflow`

这意味着：

- 洪峰提前/滞后是可解释、可复现的时间偏差
- 洪峰增大/减小是可解释、可复现的量级偏差
- 不是随机噪声，不会出现同配置多次运行得到不同伪数据的情况

`S04` 使用逐旬确定性序列：

```yaml
deviation_generation:
  mode: xun_sequence
  reference_elapsed_hours: [0, 240, 480]
  reference_forecast_sequence: [70.0, 70.0, 70.0]
  reference_actual_sequence: [70.0, 70.0, 70.0]
```

每个偏差场景直接在 `xun_forecast` / `xun_actual` 中给出序列。长度不一致会直接报错。

### 3. 可重复性设置

```yaml
reproducibility:
  llm_seed: 2025
  expected_update_count: 8
```

说明：

- `expected_update_count` 用于校验伪数据生成是否完整
- `llm_seed` 会传递给支持该参数的模型客户端
- 同时配合 `temperature_override: 0.0` 降低 LLM 运行波动

### 4. 控制器参数

```yaml
controller_config:
  scheduled_update_interval_steps: 1
  min_ecological_flow: 50.0
  warning_release_multiplier: 1.15
  dead_level: 121.0
  low_level_release_multiplier: 0.85
```

实验3中规则型控制器不再依赖代码里的魔法常量，主要修正规则都来自 YAML。

## 实验3执行流程

下面是一次 `run_deviation_experiment()` 的实际执行顺序。

### Step 1. 读取场景与偏差配置

入口函数：`experiments/automated_experiment.py:run_deviation_experiment`

流程：

1. 从 `AUTOMATED_SCENARIOS` 读取 `scenario_id`
2. 找到当前偏差场景 `deviation_id`
3. 读取 `baseline_deviation_id`
4. 如果基线缺失，立即失败

### Step 2. 生成确定性伪数据

入口类：`DeviationScenarioSimulator`

输出为 `DeviationUpdate` 列表，每一步包含：

- `elapsed_hours`
- `remaining_hours`
- `forecast_inflow`
- `actual_inflow`
- `deviation_id`

这里的 `forecast_inflow` 用于决策，`actual_inflow` 用于真实状态推进。

### Step 3. 先计算 D0 基线得分

系统会用同一个控制器先跑 `D0`：

- `static` 控制器先跑 `D0`
- `rule_based` 控制器先跑 `D0`
- `llm_tool` 控制器先跑 `D0`

这个 D0 得分作为 `performance_degradation` 的参考基线。

### Step 4. 执行三类控制器

#### A. StaticPlanController

1. 在第一个时间步根据预测来水生成一次初始方案
2. 后续所有时间步都固定执行这个 outflow
3. 每一步都用 `actual_inflow` 推进真实状态
4. 每一步都调用 pyresops 评估

#### B. RuleBasedAdjustmentController

1. 在每个调度更新点，根据 `controller_config` 和当前状态计算规则型出库
2. 不调用 LLM，不调用优化器
3. 用 `actual_inflow` 推进真实状态
4. 记录修正次数、有效修正率、恢复步数等指标

#### C. LLMToolBasedController

1. 在触发修正时，LLM 使用 `forecast_inflow` 调用现有调度工具
2. 当前方案与候选方案都在 `actual_inflow` 下做统一评估
3. 只有收益提升超过 `switch_threshold` 才切换执行方案
4. `switch_occurred` 只在真正切换时为 `True`

### Step 5. 统一评估与落盘

所有控制器最终都会输出 `RollingControlResult`，包含：

- 安全指标：约束违反、最大超限、风险状态
- 效果指标：关键维度得分、综合得分、性能下降幅度
- 滚动控制指标：修正次数、有效修正率、恢复步数

单次运行默认落盘到：

```text
experiments/results/automated/deviation/
```

## 运行方式

### 运行单个实验3样例

规则基线：

```bash
uv run python -c "from experiments.automated_experiment import run_deviation_experiment; import json; r=run_deviation_experiment('S02','S02-D0','rule_based',save_result=False); print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))"
```

LLM 工具控制：

```bash
uv run python -c "from experiments.automated_experiment import run_deviation_experiment; import json; r=run_deviation_experiment('S02','S02-D0','llm_tool',model_profile='deepseek',save_result=False); print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))"
```

### 运行实验3完整批次

推荐直接调用：

```bash
uv run python -c "from experiments.unified_runner import run_deviation_tier; import json; r=run_deviation_tier(scenario_ids=['S02','S04'], controller_types=['static','rule_based','llm_tool'], model_profile='deepseek', output_dir='experiments/results'); print(json.dumps(r['summary'], ensure_ascii=False, indent=2))"
```

这会输出：

- `experiments/results/deviation/deviation_results.json`
- `experiments/results/deviation/deviation_summary.json`

## 当前校验策略

为了避免“实验看起来能跑，实际上数据不可信”，当前实验3包含以下 fail-fast 行为：

- 缺少 `baseline_deviation_id` 直接失败
- 基线 ID 找不到对应偏差场景直接失败
- `S04` 预测/实际序列长度不一致直接失败
- `forecast_interval_hours <= 0` 直接失败
- `expected_update_count` 不匹配直接失败
- LLM 没有真实工具调用或没有严格 JSON 输出时直接失败

## 注意事项

1. `paper_experiment_runner.py` 的默认 `run_all()` 目前不自动包含实验3。
2. 实验3建议优先使用 `run_deviation_tier()` 或 `run_deviation_experiment()`。
3. 若你修改了 `config/scenarios_config.yaml` 后在长生命周期 Python 进程内重复运行，需要清理缓存：

```python
from experiments.scenario_config import clear_scenarios_config_cache
clear_scenarios_config_cache()
```

4. 如果要做正式结果统计，优先先验证：
   - `S02-D0`
   - `S02-D3a`
   - `S04-D2`

这样能先覆盖：无偏差基线、极端洪峰压力、持续偏枯三类代表场景。

## 目录说明

- `experiments/` 主路径仅保留实验 A/B/C 的执行主链。
- `experiments/utils/` 放统计、可视化、ablation 等辅助脚本。
- `experiments/tmp/` 放旧 automated 兼容链路和不再属于主实验主链的归档代码。
