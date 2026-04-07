# res-ops-mcp

面向单库调度场景的可扩展水库调度内核，支持 FastMCP 工具调用，重点提供通用的规则执行、约束校核和决策编排能力。

## 项目定位

- 单库调度内核：统一仿真、校核、评估主链路
- 策略执行平台：规则与约束可注册扩展，避免硬编码分支膨胀
- 可服务化接入：通过 MCP 工具将能力暴露给上层智能体或业务系统
- 后续配置友好：内核先做通用模型，配置载体（YAML/DB/API）可后置接入

## 核心能力

1. 快照管理：读取与更新水库实时状态
2. 方案生成：模块序列 + 切换条件构建调度程序
3. 仿真执行：统一水量平衡推进 + 模块切换
4. 约束引擎：注册式约束校核（step/global）
5. 规则引擎：表达式规则匹配与动作分发
6. 决策编排：Rule -> Action -> Constraint -> Final Outflow
7. 指标评估：注册式指标评估，内置防洪/供水/发电/生态/合规
8. 决策追踪：全过程 decision trace 持久化与回放

## 扩展开发者文档

### 自定义约束（最小模板）

```python
from pyresops.constraints.base import ConstraintEvaluator


class MyConstraint(ConstraintEvaluator):
    constraint_type = "my_constraint"

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        limit = float(self.constraint.parameters.get("limit", 0.0))
        if outflow <= limit:
            return []
        return [
            self._build_violation(
                violation_type="flow_exceeded",
                scope="step",
                step_index=step_index,
                value=outflow,
                limit=limit,
            )
        ]
```

注册方式：

```python
constraint_registry.register("my_constraint", MyConstraint)
```

### 自定义规则（最小模板）

```python
from pyresops.rules.base import RuleEvaluator


class MyRule(RuleEvaluator):
    def match(self, context):
        return context.inflow > 10000
```

注册方式：

```python
rule_registry.register("my_rule_type", MyRule)
```

在 `DispatchRule.metadata["rule_type"]` 指定 `my_rule_type`。

### 自定义指标（最小模板）

```python
from pyresops.metrics.base import MetricEvaluator


class MyMetric(MetricEvaluator):
    metric_name = "my_metric"

    def evaluate(self, *, spec, result, constraint_set, proxy_options):
        return 100.0
```

注册方式：

```python
evaluation_service.register_metric("my_metric", MyMetric)
```

完整可运行模板见：`examples/extension_templates.py`

## 水库信息 YAML 加载接口

本项目已提供通用 YAML 加载接口（不绑定具体水库规则）：

- 加载入口：`pyresops.config.load_reservoir_bootstrap_from_yaml`
- 返回对象：`ReservoirBootstrap(spec, snapshot)`
- 支持两种结构：
  - 平铺 `ReservoirSpec` 字段
  - 分组结构 `reservoir.characteristic_levels/capacities/curves`

服务启动时加载顺序：

1. 环境变量 `PYRESOPS_RESERVOIR_CONFIG` 指向的 YAML
2. 默认文件 `configs/default_reservoir.yaml`
3. 若都不存在，回退到内置 demo 参数

示例：

```bash
set PYRESOPS_RESERVOIR_CONFIG=E:\path\to\reservoir.yaml
uv run python -m pyresops.server
```

## 技术栈

- Python 3.11+
- FastMCP
- Pydantic v2
- NumPy / Pandas
- SQLite
- pytest / ruff

## 快速开始

```bash
# 安装依赖
uv sync

# 运行 MCP 服务
uv run python -m pyresops.server

# 运行测试
uv run pytest tests/ -v
```

## 架构分层

```
pyresops/
├── tools/         # MCP 工具层
├── services/      # 服务编排层
├── domain/        # 领域模型层
├── core/          # 仿真/编排内核
├── constraints/   # 约束 SPI + 内置实现
├── rules/         # 规则 SPI + 内置实现
├── metrics/       # 指标 SPI + 内置实现
├── modules/       # 操作模块层
├── plugins/       # 插件与扩展注册层
└── storage/       # SQLite 持久化层
```

## 新增通用扩展能力（本次重构）

### 1) 统一策略模型

- `PolicyBundle`：统一封装 `constraints`、`rules`、`objectives`、`directives`
- `ExecutionContext`：规则与约束执行的统一上下文
- `ViolationRecord` / `DecisionOutcome` / `DecisionTraceStep`：统一决策与违反记录模型

### 2) 约束 SPI（Constraint SPI）

- 抽象接口：`ConstraintEvaluator`
- 注册器：`ConstraintRegistry`
- 工厂：`ConstraintFactory`
- 约束动态加载：`impl_class="pkg.module:ClassName"`

内置约束类型：

- `level_max`
- `level_min`
- `level_range`
- `flow_max`
- `flow_min`
- `water_supply`
- `ramp_rate_max`
- `downstream_flow_limit`
- `ecological_min_flow`

### 3) 规则 SPI（Rule SPI）

- 抽象接口：`RuleEvaluator`
- 注册器：`RuleRegistry`
- 工厂：`RuleFactory`
- 内置 evaluator：`ExpressionRuleEvaluator`

表达式规则支持：

- 逻辑：`all` / `any` / `not`
- 比较：`eq` / `ne` / `gt` / `gte` / `lt` / `lte` / `in`
- 路径：`state.*` / `forecast.*` / `history.*` / `directives.*`

动作类型支持：

- `set_target_outflow`
- `clamp_outflow`
- `switch_mode`
- `emit_event`

### 4) 决策编排器

- 组件：`DecisionOrchestrator`
- 执行链路：规则命中 -> 动作归并 -> 约束修正 -> 最终下泄
- 结果：每一步生成 trace，附带命中规则、动作、修正、违反信息

### 5) 评估体系插件化

- 抽象接口：`MetricEvaluator`
- 注册器：`MetricRegistry`
- 内置指标：`flood`、`supply`、`power`、`ecology`、`compliance`
- `EvaluationResult.additional_scores` 支持扩展指标输出

### 6) 持久化扩展

- 新增表：`decision_traces`
- 新增接口：
  - `save_decision_trace`
  - `load_decision_trace`
  - `list_decision_traces`

## 兼容性说明

- 旧接口仍可用：`constraints/objectives/directives` 仍可传入
- 新接口可用：`policy_bundle` 可直接驱动仿真与滚动调度
- `ConstraintValidator` 对外方法签名保持兼容（新增可选 `previous_outflow`）

## MCP 工具清单

基础工具：

- `get_reservoir_snapshot`
- `list_operation_modules`
- `generate_dispatch_program`
- `simulate_program`
- `evaluate_program`
- `compare_programs`
- `explain_program`

滚动调度工具：

- `optimize_flexible_release_plan`
- `reassess_plan`
- `replace_working_plan`
- `finalize_plan`
- `get_working_state`

其中 `simulate_program` 与 `optimize_flexible_release_plan` / `reassess_plan` 支持可选 `policy_bundle` 输入。

Legacy 输入扩展：

- `optimize_flexible_release_plan` / `reassess_plan` 还支持可选 `rules`（list[dict]）参数，
  在不传 `policy_bundle` 时会与 `constraints/objectives/directives` 一并转换为 `PolicyBundle`。

## 核心目录与关键文件

- `pyresops/core/orchestrator.py`
- `pyresops/core/action_resolver.py`
- `pyresops/core/validator.py`
- `pyresops/constraints/`
- `pyresops/rules/`
- `pyresops/metrics/`
- `pyresops/domain/policy.py`
- `pyresops/domain/rule.py`
- `pyresops/domain/decision.py`
- `pyresops/storage/repository.py`

## 测试

当前测试集：`233 passed`

新增覆盖方向：

- 策略模型（Policy/Rule/Decision）
- 约束注册器与内置约束
- 规则表达式与规则注册器
- 编排器链路
- policy_bundle 服务集成
- rolling_ops legacy custom rules 兼容路径
- 决策轨迹持久化

## 下一步建议

- 引入配置适配层（YAML/DB/API）仅负责组装 `PolicyBundle`
- 将特化水库规则以插件或配置注入，不改核心引擎

## 许可证

MIT

## Installation

```bash
# 推荐：使用 uv 安装项目依赖
uv sync

# 可选：使用 pip 本地可编辑安装
pip install -e .
```

## Quick start

1. 安装依赖：

   ```bash
   uv sync
   ```

2. 启动 MCP 服务：

   ```bash
   uv run python -m pyresops.server
   ```

3. （可选）运行测试确认环境：

   ```bash
   uv run pytest tests/ -v
   ```

4. （可选）加载自定义水库 YAML：

   ```bash
   set PYRESOPS_RESERVOIR_CONFIG=E:\path\to\reservoir.yaml
   uv run python -m pyresops.server
   ```

## Usage examples

### 人工使用（脚本方式）

```bash
uv run python examples/case1_flood_dispatch.py
uv run python examples/case2_program_comparison.py
uv run python examples/case3_persistence.py
```

预期结果：终端输出仿真步骤、评分结果、方案对比或持久化事件日志。

### MCP 使用（工具调用方式）

启动服务后，可由任意 MCP 客户端调用以下工具链：

1. 读取当前快照：`get_reservoir_snapshot`
2. 生成调度方案：`generate_dispatch_program`
3. 运行仿真：`simulate_program`
4. 方案评估：`evaluate_program`

示例结果字段（来自工具返回）：

- `simulate_program` 返回 `max_level`、`min_level`、`avg_outflow`、`decision_trace_steps`
- `evaluate_program` 返回 `overall_score`、`flood_control_score`、`water_supply_score`、`constraint_violations`

### MCP 滚动调度（工作态）

适用于滚动会商/复盘场景的工具：

- `optimize_flexible_release_plan`
- `reassess_plan`
- `replace_working_plan`
- `finalize_plan`
- `get_working_state`

其中 `simulate_program`、`optimize_flexible_release_plan`、`reassess_plan` 支持可选 `policy_bundle` 输入。

## License

<!-- VERIFY: License type is MIT -->
