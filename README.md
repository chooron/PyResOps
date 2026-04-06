# res-ops-mcp

面向单库的、模块化的、可服务化调用的水库调度内核系统，支持 FastMCP 工具调用。

## 项目定位

- **单库调度**: 专注于单个水库的精细化调度决策
- **模块化**: 通过可插拔的操作模块表达调度策略
- **服务化**: 基于 FastMCP 提供工具调用接口
- **内核驱动**: 所有操作通过仿真引擎验证，确保水量平衡与约束满足

## 核心功能

1. **快照管理**: 获取/更新水库当前状态
2. **方案生成**: 基于模块组合构建结构化调度方案
3. **仿真推演**: 含模块切换条件的时序推进仿真
4. **约束校核**: 水位/流量/供水等多维约束逐步校核
5. **指标评估**: 防洪、供水、综合评分 + 逐步评分
6. **方案比较**: 多方案对比分析与排序
7. **决策解释**: 生成调度方案的可解释性报告
8. **数据持久化**: SQLite 存储方案、仿真结果、事件日志

## 技术栈

- Python 3.11+
- FastMCP (工具接口)
- Pydantic v2 (领域对象)
- NumPy / Pandas (数值计算)
- SQLite (持久化)
- pytest (测试框架)

## 快速开始

```bash
# 安装依赖
uv sync

# 运行 MCP 服务
uv run python -m res_ops.server

# 运行演示
uv run python examples/demo.py

# 运行测试
uv run pytest tests/ -v
```

---

## 架构设计

### 六层分层结构

```
┌─────────────────────────────────────────────────────────┐
│  1. 接口层 (Tools Layer)                                 │
│     src/res_ops/tools/                                  │
│     snapshot_tools  program_tools  simulation_tools     │
│     evaluation_tools  explanation_tools                 │
├─────────────────────────────────────────────────────────┤
│  2. 服务编排层 (Service Layer)                           │
│     src/res_ops/services/                               │
│     SnapshotService  ProgramService  SimulationService  │
│     EvaluationService  ExplanationService               │
├─────────────────────────────────────────────────────────┤
│  3. 领域对象层 (Domain Layer)                            │
│     src/res_ops/domain/                                 │
│     ReservoirSpec  ReservoirState  DispatchProgram      │
│     ForecastBundle  Constraint  Objective  Result       │
├─────────────────────────────────────────────────────────┤
│  4. 调度表达层 (Modules Layer)                           │
│     src/res_ops/modules/                                │
│     ConstantRelease  InflowDriven  StorageDriven        │
│     CombinedDriven  LevelTracking  ExternalConstraint   │
├─────────────────────────────────────────────────────────┤
│  5. 内核层 (Core Layer)                                  │
│     src/res_ops/core/                                   │
│     SimulationEngine  HydraulicsCalculator              │
│     ConstraintValidator                                 │
├─────────────────────────────────────────────────────────┤
│  6. 插件与知识层 (Plugin + Storage Layer)                │
│     src/res_ops/plugins/  src/res_ops/storage/          │
│     PluginBase  PluginRegistry  Repository (SQLite)     │
└─────────────────────────────────────────────────────────┘
```

### 核心概念

| 概念 | 类 | 说明 |
|------|-----|------|
| 水库规范 | `ReservoirSpec` | 静态参数：特征水位、水位-库容曲线、泄流能力曲线 |
| 水库状态 | `ReservoirState` | 实时状态：水位、库容、入流、出流、激活模块 |
| 预报数据包 | `ForecastBundle` | 预报来水序列，支持多变量 |
| 调度方案 | `DispatchProgram` | 结构化方案：模块序列 + 切换条件 + 时间范围 |
| 操作模块 | `OperationModule` | 可插拔的出流计算策略 |
| 模块切换条件 | `SwitchCondition` | 水位/入流/时间/库容触发模块切换 |
| 约束集合 | `ConstraintSet` | 水位/流量/供水等约束规则 |
| 仿真结果 | `SimulationResult` | 状态快照序列 + 统计量 |
| 评估结果 | `EvaluationResult` | 评分 + 违反记录 + 逐步评分 |

---

## 操作模块 (6 类)

| 模块类型 | 类名 | 说明 |
|----------|------|------|
| `constant_release` | `ConstantReleaseModule` | 恒定下泄，维持固定出流 |
| `inflow_driven` | `InflowDrivenModule` | 入流驱动，出流 = 系数 × 入流 |
| `storage_driven` | `StorageDrivenModule` | 蓄水量驱动，按库容比例调整出流 |
| `combined_driven` | `CombinedDrivenModule` | 联合驱动，加权组合入流与库容 |
| `level_tracking` | `LevelTrackingModule` | 目标水位跟踪，比例控制 |
| `external_constraint` | `ExternalConstraintModule` | 外部约束响应，下游断面控制 |

### 模块切换条件

引擎支持在仿真过程中根据条件自动切换模块：

| 条件类型 | 参数 | 说明 |
|----------|------|------|
| `level_threshold` | `threshold`, `direction` | 水位达到阈值时切换 |
| `inflow_threshold` | `threshold`, `direction` | 入流达到阈值时切换 |
| `time_based` | `trigger_time` | 到达指定时间时切换 |
| `storage_threshold` | `threshold`, `direction` | 库容达到阈值时切换 |

---

## 约束校核

### 支持的约束类型

| 类型 | 参数 | 校核范围 |
|------|------|----------|
| `level_max` | `max_level` | 最高水位限制 (全局 + 逐步) |
| `level_min` | `min_level` | 最低水位限制 (全局 + 逐步) |
| `level_range` | `min_level`, `max_level` | 水位范围限制 (全局) |
| `flow_max` | `max_flow` | 最大出流限制 (全局 + 逐步) |
| `flow_min` | `min_flow` | 最小出流限制 (全局 + 逐步) |
| `water_supply` | `demand` | 供水需求保障 (全局) |

### 逐步校核

除全局校核外，`ConstraintValidator` 还支持对仿真过程中的每一步进行独立校核，返回包含 `step_index` 的违反记录。

---

## 评估体系

### 终局评分

- **防洪评分**: 基于最高水位与汛限水位/设计洪水位的距离
- **供水评分**: 基于最低水位与死水位/正常蓄水位的距离
- **综合评分**: 加权平均 + 约束违反惩罚

### 逐步评分 (Step-by-Step)

通过 `include_step_scores=True` 开启，每步输出：

| 维度 | 说明 |
|------|------|
| `risk_score` | 单步风险分 (0-100)，水位越接近洪水位越低 |
| `constraint_score` | 过程约束分 (0-100)，该步有违反则扣分 |
| `benefit_score` | 阶段性收益分 (0-100)，供水能力评估 |

---

## 数据持久化

`Repository` 类基于 SQLite 提供以下持久化能力：

| 方法 | 说明 |
|------|------|
| `save_program` / `load_program` / `list_programs` | 调度方案存取 |
| `save_simulation_result` / `load_simulation_result` | 仿真结果存取 |
| `save_evaluation_result` | 评估结果存储 |
| `save_snapshot` | 水库状态快照存储 |
| `log_event` / `list_events` | 事件日志 (供未来案例检索) |

---

## MCP 工具清单

| 工具 | 功能 |
|------|------|
| `get_reservoir_snapshot` | 获取当前快照 |
| `list_operation_modules` | 列出可用操作模块 |
| `generate_dispatch_program` | 生成调度方案 |
| `simulate_program` | 仿真调度方案 |
| `evaluate_program` | 评估方案指标 |
| `compare_programs` | 比较多个方案 |
| `explain_program` | 解释方案决策 |

---

## 主流程

```
输入状态与预报
    ↓
生成候选调度程序 (DispatchProgram)
    ↓
内核仿真 (含模块切换)
    ↓
约束校核 (全局 + 逐步)
    ↓
指标评估 (终局 + 逐步)
    ↓
输出结构化方案 + 可回放轨迹
```

---

## 项目结构

```
src/res_ops/
├── __init__.py
├── server.py                    # FastMCP 应用入口
├── domain/                      # 领域对象层
│   ├── reservoir.py             #   ReservoirSpec, ReservoirState
│   ├── program.py               #   DispatchProgram, SwitchCondition
│   ├── module.py                #   OperationModule (ABC)
│   ├── forecast.py              #   ForecastBundle
│   ├── constraint.py            #   Constraint, ConstraintSet
│   ├── objective.py             #   Objective, ObjectiveSet
│   └── result.py                #   SimulationResult, EvaluationResult, StepScore
├── core/                        # 内核层
│   ├── engine.py                #   SimulationEngine (含切换逻辑)
│   ├── hydraulics.py            #   HydraulicsCalculator
│   └── validator.py             #   ConstraintValidator
├── modules/                     # 调度表达层
│   ├── base.py                  #   BaseOperationModule
│   ├── constant_release.py      #   恒定下泄
│   ├── inflow_driven.py         #   入流驱动
│   ├── storage_driven.py        #   蓄水量驱动
│   ├── combined_driven.py       #   联合驱动
│   ├── level_tracking.py        #   目标水位跟踪
│   └── external_constraint.py   #   外部约束响应
├── services/                    # 服务编排层
│   ├── snapshot.py              #   SnapshotService
│   ├── program.py               #   ProgramService
│   ├── simulation.py            #   SimulationService
│   ├── evaluation.py            #   EvaluationService
│   └── explanation.py           #   ExplanationService
├── tools/                       # MCP 工具层
│   ├── snapshot_tools.py
│   ├── program_tools.py
│   ├── simulation_tools.py
│   ├── evaluation_tools.py
│   └── explanation_tools.py
├── plugins/                     # 插件层 (预留)
│   ├── base.py                  #   PluginBase
│   └── registry.py              #   PluginRegistry
└── storage/                     # 持久化层
    └── repository.py            #   Repository (SQLite)
```

---

## 测试

63 个测试覆盖：

| 测试目录 | 覆盖范围 |
|----------|----------|
| `test_core/` | 仿真引擎、模块切换、水力学计算、约束校核(基础+扩展) |
| `test_domain/` | 领域对象验证 |
| `test_modules/` | 内置模块 + 新增模块 |
| `test_services/` | 仿真服务、逐步评估 |
| `test_storage/` | SQLite 持久化 |
| `test_integration/` | 端到端 MCP 工作流 |

---

## 基础版能力边界

### 已实现

- [x] 单库调度
- [x] 6 类操作模块
- [x] 模块切换 (水位/入流/时间/库容触发)
- [x] 统一仿真内核
- [x] 多维约束校核 (水位/流量/供水)
- [x] 终局评分 + 逐步评分
- [x] 方案结构化输出
- [x] FastMCP 调用接口
- [x] SQLite 数据持久化
- [x] 事件日志 (案例沉淀基础)

### 预留扩展位

- [ ] 多库联合联算
- [ ] 复杂随机优化 (Pyomo + HiGHS)
- [ ] CBR 案例检索插件 (`CaseRetrievalPlugin`)
- [ ] 博弈搜索器 (`PlannerPlugin`)
- [ ] LLM 编排器
- [ ] 多情景预报 (场景集输入)

---

## 许可证

MIT
