# PyResOps 水库调度库 — 大模型调用指南

## 概述

本 skill 文件指导大模型（LLM Agent）如何通过 MCP 工具调用 `pyresops` 水库调度库，完成从快照读取、方案生成、仿真执行到评估分析的完整调度工作流。

**适用场景：** 单库实时调度、防洪决策支持、兴利发电优化、滚动调度规划  
**库能力范围：** 仿真执行、约束校核、规则决策、指标评估、决策追踪

---

## 水库基本参数（滩坑水电站）

在调用任何工具前，需了解目标水库的关键参数：

```yaml
reservoir_name: 滩坑水电站
characteristic_levels:
  calibration_flood: 169.15    # 校核洪水位 (PMF)
  design_flood: 165.87          # 设计洪水位 (P=0.1%)
  flood_high: 161.50            # 防洪高水位 (P=5%)
  normal: 160.00                # 正常蓄水位（梅汛期/非汛期上限）
  limit_typhoon: 156.50         # 台汛期限制水位
  dead: 120.00                  # 死水位

characteristic_storage:
  total: 4.19e9                 # 总库容 41.9亿m³
  normal: 3.52e9                # 正常库容 35.2亿m³
  regulation: 2.126e9           # 调节库容 21.26亿m³
  flood_control: 3.5e8          # 防洪库容 3.5亿m³

discharge_facilities:
  spillway:
    gates: 6                    # 6个弧形闸孔
    width_per_gate: 12          # 孔宽 12m
    sill_elevation: 148.0       # 堰顶高程 148m
    max_discharge: 14335        # 最大泄量 14335 m³/s（6孔全开）
  flood_tunnel:
    gates: 1
    size: "7×7m"
    inlet_elevation: 65         # 进口底坎高程 65m
    max_discharge: 1729         # 最大泄量 1729 m³/s
    activate_level: 165.27      # 超过此水位启用
  power_units:
    count: 3
    capacity_per_unit: 200      # 单机 200MW
    rated_flow: 209.17          # 单机额定流量 m³/s
    total_rated_flow: 627.51    # 三机额定总流量 m³/s

downstream:
  safety_station: 鹤城站
  safe_flow: 14000              # 下游安全泄量 m³/s（20年一遇）
  propagation_hours: 5.0        # 洪水传播时间 h

seasons:
  plum_flood: "04-15 ~ 06-30"       # 梅汛期
  transition: "07-01 ~ 07-15"       # 梅台过渡期
  typhoon_flood: "07-16 ~ 10-15"    # 台汛期
  dry_season: "10-16 ~ 04-14"       # 枯水期
```

---

## 工具清单

### 基础工具（必知）

| 工具名 | 用途 | 关键参数 |
|-------|------|---------|
| `get_reservoir_snapshot` | 获取水库当前实时状态 | 无（直接读取最新快照） |
| `list_operation_modules` | 列出可用调度模块 | 无 |
| `generate_dispatch_program` | 生成调度方案 | `snapshot`, `modules`, `forecast` |
| `simulate_program` | 执行仿真（含约束校核） | `program`, `policy_bundle` |
| `evaluate_program` | 多维度评估方案 | `result` |
| `compare_programs` | 对比多方案 | `results` (list) |
| `explain_program` | 生成自然语言说明 | `result` |

### 滚动调度工具（复杂场景）

| 工具名 | 用途 | 关键参数 |
|-------|------|---------|
| `optimize_flexible_release_plan` | 生成并优化滚动工作计划 | `snapshot`, `forecast`, `policy_bundle` |
| `reassess_plan` | 更新已有计划（来水变化时） | `plan_id`, `snapshot`, `updated_forecast` |
| `replace_working_plan` | 替换当前工作计划 | `plan_id`, `new_plan` |
| `finalize_plan` | 完成并归档计划 | `plan_id` |
| `get_working_state` | 查看当前滚动调度状态 | 无 |

---

## 核心数据结构

### PolicyBundle（策略包）

`simulate_program` 和 `optimize_flexible_release_plan` 的核心输入：

```python
policy_bundle = {
    \"constraints\": [          # 约束列表（见下方约束速查表）
        {
            \"type\": \"level_max\",
            \"parameters\": {\"max_level\": 160.0}
        }
    ],
    \"rules\": [               # 规则列表（表达式规则）
        {
            \"name\": \"规则名称\",
            \"metadata\": {\"rule_type\": \"expression\"},
            \"conditions\": {...},     # 触发条件
            \"actions\": [{\"type\": \"set_target_outflow\", ...}]
        }
    ],
    \"objectives\": [          # 优化目标
        {\"type\": \"flood_control\", \"weight\": 0.7},
        {\"type\": \"maximize_power\",  \"weight\": 0.3}
    ],
    \"directives\": {          # 动态指令（可在运行时更新）
        \"target_level\": 156.5,
        \"typhoon_warning\": False
    }
}
```

### 约束类型速查表

| 约束类型 | 参数 | 说明 |
|---------|------|------|
| `level_max` | `max_level` | 水位上限 |\n| `level_min` | `min_level` | 水位下限（死水位保护） |
| `level_range` | `min_level`, `max_level` | 水位区间 |
| `flow_max` | `max_flow` | 出库流量上限 |
| `flow_min` | `min_flow` | 出库流量下限 |
| `downstream_flow_limit` | `max_downstream_flow`, `interval_flow`, `propagation_hours` | 下游断面流量控制（错峰调度核心） |
| `ecological_min_flow` | `min_flow` | 生态基流保障 |
| `ramp_rate_max` | `max_ramp` | 最大流量爬坡速率（闸门操作平稳性） |
| `water_supply` | `required_volume` | 供水保障 |

### 规则条件语法

```python
# 单条件
{\"path\": \"state.level\", \"op\": \"gt\", \"value\": 160.0}

# 操作符：eq, ne, gt, gte, lt, lte, in
# 路径：state.level, state.inflow, state.outflow,
#        forecast.inflow, history.level, directives.xxx

# 组合条件
{\"all\": [条件1, 条件2]}    # AND
{\"any\": [条件1, 条件2]}    # OR
{\"not\": 条件1}             # NOT
```

### 规则动作类型

| 动作类型 | 参数 | 说明 |
|---------|------|------|
| `set_target_outflow` | `value` | 设置目标出库流量 |
| `clamp_outflow` | `min`, `max` | 限制出库流量范围 |
| `switch_mode` | `mode` | 切换调度模块 |
| `emit_event` | `event` | 发送调度事件（如全开溢洪道） |

### 目标类型速查

| 目标类型 | 说明 |
|---------|------|
| `flood_control` | 防洪目标（最小化超汛限时间和程度） |
| `maximize_power` | 最大化发电量 |
| `minimize_spillage` | 最小化弃水 |
| `target_level` | 末水位目标 |
| `ecology` | 生态目标（满足最小生态流量）|
| `compliance` | 合规目标（满足调度计划要求）|

---

## 标准调用工作流

### 工作流一：防洪仿真评估（标准调度）

**适用：** 汛期洪水调度、防洪约束校核

```
步骤1：获取快照
  snapshot = get_reservoir_snapshot()
  → 确认当前水位、入库流量

步骤2：生成方案
  program = generate_dispatch_program(
      snapshot=snapshot,
      forecast=inflow_forecast,    # 入库流量预报序列
      modules=[\"flexible_release\"]  # 灵活下泄模块
  )

步骤3：仿真执行
  result = simulate_program(
      program=program,
      policy_bundle={
          \"constraints\": [...],
          \"rules\": [...],
          \"objectives\": [...],
          \"directives\": {...}
      }
  )

步骤4：评估
  eval = evaluate_program(result=result)
  → 获得 flood_control_score, power_score, constraint_violations

步骤5（可选）：解释
  explain = explain_program(result=result)
  → 自然语言说明关键决策节点
```

### 工作流二：滚动调度（滚动预见期优化）

**适用：** 过渡期降水位、多日优化调度

```
初始化：
  plan = optimize_flexible_release_plan(
      snapshot=snapshot,
      forecast=forecast_N_steps,
      policy_bundle=policy_bundle
  )

每个更新周期（如每6h或每天）：
  new_snapshot = get_reservoir_snapshot()

  if inflow_changed_significantly or typhoon_alert_updated:
      plan = reassess_plan(
          plan_id=plan.id,
          snapshot=new_snapshot,
          updated_forecast=new_forecast,
          updated_directives=new_directives   # 如台风预警状态变化
      )
      replace_working_plan(plan.id, plan)

  state = get_working_state()
  → 确认当前执行状态

计划结束：
  finalize_plan(plan_id=plan.id)
```

### 工作流三：方案比对

**适用：** 多方案决策支持

```
plan_a = simulate_program(program_a, policy_bundle_conservative)
plan_b = simulate_program(program_b, policy_bundle_aggressive)

comparison = compare_programs([plan_a, plan_b])
→ 对比各方案的 overall_score, flood_score, power_score 等
```

---

## 调度决策逻辑（滩坑特化）

### 1. 汛期水位分级调度逻辑

```
IF level ≤ 台汛限制水位(156.5m):
    → 正常运行，机组发电
    → 约束：flow_max ≈ 入库量（不弃水）

IF 台汛限(156.5m) < level ≤ 防洪高水位(161.5m):
    → 补偿凑泄
    → Q_泄 = Q_安全(14000) - DQ_区间 - Q_机(400)
    → 约束：downstream_flow_limit

IF 161.5m < level ≤ 161.7m:
    → 控制下泄 6000 m³/s（缓冲区）

IF level > 161.7m:
    → 溢洪道全开 + 机组参与
    → 规则：emit_event(\"full_open_spillway\")

IF level > 165.27m（P=0.2%）:
    → 溢洪道全开 + 泄洪洞 + 停止发电
    → 规则：emit_event(\"emergency_full_release\")
```

### 2. 分期汛限水位判断

```python
import datetime

def get_current_limit_level(date: datetime.date) -> float:
    month, day = date.month, date.day
    if (month == 4 and day >= 15) or month in [5, 6]:
        return 160.0   # 梅汛期
    elif month == 7 and day <= 15:
        return 160.0   # 过渡期初（逐步降至156.5）
    elif (month == 7 and day > 15) or month in [8, 9] or (month == 10 and day <= 15):
        return 156.5   # 台汛期
    else:
        return 160.0   # 非汛期（枯水期）
```

### 3. 泄洪洞流量计算

```python
def flood_tunnel_discharge(level: float) -> float:
    \"\"\"泄洪洞泄流公式 Q = 175.736 × (Z - 72.0)^0.5\"\"\"
    if level <= 72.0:
        return 0.0
    return 175.736 * ((level - 72.0) ** 0.5)

# 示例：level=165.27m → Q ≈ 175.736 × (165.27-72.0)^0.5 ≈ 1699 m³/s
```

---

## 典型场景调用模板

### 场景：台汛期台风来临前预泄

```python
policy_bundle = {
    \"constraints\": [
        {\"type\": \"level_max\",           \"parameters\": {\"max_level\": 156.5}},
        {\"type\": \"ecological_min_flow\", \"parameters\": {\"min_flow\": 50.0}},
        {\"type\": \"ramp_rate_max\",       \"parameters\": {\"max_ramp\": 500.0}},
    ],
    \"rules\": [
        {
            \"name\": \"台汛预泄\",
            \"metadata\": {\"rule_type\": \"expression\"},
            \"conditions\": {
                \"all\": [
                    {\"path\": \"state.level\",                \"op\": \"gt\", \"value\": 156.5},
                    {\"path\": \"directives.typhoon_warning\", \"op\": \"eq\", \"value\": True}
                ]
            },
            \"actions\": [{\"type\": \"set_target_outflow\", \"parameters\": {\"value\": 3000.0}}]
        }
    ],
    \"directives\": {\"typhoon_warning\": True, \"target_level\": 156.5},
    \"objectives\": [{\"type\": \"target_level\", \"target\": 156.5}]
}
```

### 场景：梅汛期下游错峰调度

```python
policy_bundle = {
    \"constraints\": [
        {
            \"type\": \"downstream_flow_limit\",
            \"parameters\": {
                \"max_downstream_flow\": 14000,
                \"propagation_hours\": 5.0
            }
        },
        {\"type\": \"level_max\", \"parameters\": {\"max_level\": 161.5}},
    ],
    \"rules\": [
        {
            \"name\": \"补偿凑泄\",
            \"metadata\": {\"rule_type\": \"expression\"},
            \"conditions\": {
                \"all\": [
                    {\"path\": \"state.level\", \"op\": \"gt\",  \"value\": 160.0},
                    {\"path\": \"state.level\", \"op\": \"lte\", \"value\": 161.5}
                ]
            },
            \"actions\": [{\n                \"type\": \"clamp_outflow\",\n                \"parameters\": {\"min\": 400.0, \"max\": 8600.0}\n            }]\n        }\n    ],\n    \"directives\": {\n        \"downstream_interval_flow\": 5000,  # 区间流量预报\n        \"propagation_hours\": 5.0\n    },\n    \"objectives\": [\n        {\"type\": \"flood_control\", \"weight\": 0.6},\n        {\"type\": \"maximize_power\", \"weight\": 0.4}\n    ]\n}\n```\n\n---\n\n## 输出解读\n\n### simulate_program 输出\n\n```json\n{\n  \"max_level\": 159.4,          // 最高水位\n  \"min_level\": 153.8,          // 最低水位\n  \"final_level\": 156.5,        // 末水位\n  \"avg_outflow\": 2500.0,       // 平均出库流量\n  \"total_spillage\": 0,         // 弃水量（m³）\n  \"constraint_violations\": [], // 约束违反列表（空=无违反）\n  \"decision_trace_steps\": [    // 逐步决策轨迹\n    {\n      \"step_index\": 0,\n      \"inflow\": 1500,\n      \"outflow\": 1200,\n      \"level\": 159.2,\n      \"rules_fired\": [\"台汛预泄\"],\n      \"actions\": [{\"type\": \"set_target_outflow\", \"value\": 3000}],\n      \"corrections\": [{\"reason\": \"ramp_rate\", \"adjusted_to\": 1200}],\n      \"violations\": []\n    }\n  ]\n}\n```\n\n### evaluate_program 输出\n\n```json\n{\n  \"overall_score\": 0.88,         // 综合得分 [0,1]\n  \"flood_control_score\": 0.92,   // 防洪得分\n  \"water_supply_score\": 1.00,    // 供水/生态得分\n  \"power_score\": 0.78,           // 发电得分\n  \"ecology_score\": 1.00,         // 生态得分\n  \"compliance_score\": 0.90,      // 合规得分\n  \"constraint_violations\": []    // 约束违反摘要\n}\n```\n\n---\n\n## 常见问题与处理\n\n### Q1: constraint_violations 不为空怎么办？\n\n```\n检查步骤：\n1. 查看 violation.type（哪个约束违反了？）\n2. 查看 violation.step_index（哪一步违反？）\n3. 查看 violation.value vs violation.limit（超出多少？）\n4. 调整 rules 或 constraints 参数后重新仿真\n```\n\n### Q2: 如何处理区间洪水预报误差？\n\n```python\n# 区间流量误差约6%（文件规定）\ninterval_flow_with_buffer = interval_flow_forecast * 1.06\n# 在 downstream_flow_limit 约束中使用保守值\n```\n\n### Q3: 台风预警状态更新如何处理？\n\n```python\n# 方法1：更新 directives 后重新仿真\nnew_directives = {**directives, \"typhoon_warning\": True}\nnew_result = simulate_program(program, {**policy_bundle, \"directives\": new_directives})\n\n# 方法2：滚动调度中更新\nreassess_plan(plan_id, snapshot, forecast, updated_directives={\"typhoon_warning\": True})\n```\n\n### Q4: 如何验证泄洪洞在正确时机启用？\n\n```python\n# 在 decision_trace_steps 中搜索相关事件\nfor step in result.decision_trace_steps:\n    if any(a.get(\"event\") == \"emergency_full_release\" for a in step.actions):\n        print(f\"Step {step.step_index}: 泄洪洞启用，水位 {step.level:.2f}m\")\n```\n\n---\n\n## 注意事项\n\n1. **来水预报格式**：`forecast` 是时序列表，每个元素包含 `{\"step\": int, \"inflow\": float}`，step 从 0 开始，时间步长由 `program` 配置决定\n\n2. **约束优先级**：约束修正优先于规则动作。若规则设定目标出库 5000 m³/s，但 `flow_max` 约束为 4000，最终出库为 4000（约束优先）\n\n3. **生态流量来源**：当机组不发电时（水位低或检修），需通过生态小机组（4MW）保障下游 50 m³/s 生态基流\n\n4. **调度权限切换**：梅汛期水位超过 160m 后调度权归丽水市水利局；台汛期超过 156.5m 后同样如此。建议在调度事件中记录权限状态\n\n5. **步长选择建议**：\n   - 防洪仿真：1～3小时步长\n   - 过渡期降水位：6～24小时步长\n   - 枯水期兴利：24小时（日）步长\n   - 极端洪水：1小时步长（精细模拟）\n",
  "file_path": "E:\\PyCode\\PyResOps\\scenarios\\skill\\reservoir_dispatch.md"
}
