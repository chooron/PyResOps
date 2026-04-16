# 重构 dynamic_experiment.py — 场景二动态多阶段调度实施计划

> 版本：v1.0  
> 日期：2026-04-10  
> 目标文件：`experiments/dynamic_experiment.py`

---

## 一、RALPLAN-DR 摘要

### 原则

1. **预报不变**：入库预报由 `scenarios/*.md` 固定，`DYNAMIC_TRIGGERS` 中不再有 `adjusted_inflow`
2. **状态真实演变**：每次指令之间通过 pyresops 仿真推进，LLM 看到的是真实的当前水库状态
3. **指令达标评估**：每次指令后评估"是否达标"，而非累积 delta 评分
4. **困难任务宽松 Pass**：物理矛盾场景（S03 T1）Pass 条件为"在大坝安全前提下尽可能接近目标，并说明约束冲突"
5. **向后兼容**：保留 `run_dynamic_experiments()` 旧接口，不破坏 `paper_experiment_runner.py` 调用

### 决策驱动

1. `AgnoMCPExperiment.run_scenario(scenario)` 接受 `scenario: dict`，其中 `current_level`、`initial_storage`、`initial_inflow` 决定 LLM 看到的初始状态——只需在每次触发前更新这三个字段即可注入真实状态
2. `SimulationEngine.simulate()` 支持从任意 `ReservoirState` 出发，`snapshots[-1]` 即为末态，可直接构造下一阶段初始状态
3. `_run_pyresops_eval()` 已有完整仿真逻辑，`_advance_state()` 复用其模式即可

### 可选方案

| 方案 | 描述 | 决策 |
|------|------|------|
| A（采用） | 用 `SimulationEngine` 跑完整段仿真取末态，注入下一阶段 scenario | 与现有评估逻辑一致，状态完整 |
| B（不采用） | 用 `HydraulicsCalculator.water_balance_step()` 逐步推进 | 不经过模块调度逻辑，状态不完整 |
| C（不采用） | 在 `run_scenario()` 内部维护状态 | 需修改 `paper_experiment_runner.py`，侵入性大 |

---

## 二、实施步骤

### Step 1：重写 `DYNAMIC_TRIGGERS` 数据结构

**文件**：`experiments/dynamic_experiment.py`（顶部常量区）

**改动**：将现有结构替换为新格式，废弃 `adjusted_inflow`，每场景 4 条指令：

```python
{
    "stage": "T1",
    "trigger_hours": 6,               # 距场景开始的小时偏移
    "sim_hours_before": 6,            # 触发前需仿真推进的小时数
    "type": "instruction_change",
    "description": "...",
    "natural_lang": "...",            # 传给 LLM 的完整指令文本
    "pass_condition": {
        "type": "level_target",       # level_target / flow_limit / direction
        "target": 156.5,
        "tolerance": 0.3,
    },
    "is_hard_task": False,
}
```

**各场景指令（T0~T3）**：

S01 台汛期预泄（步长 3h）：
- T0 trigger_hours=0：将水位从 157.5m 降至 156.5m
- T1 trigger_hours=6：加快预泄，6h 内必须降至 156.5m
- T2 trigger_hours=12：进一步降至 155.5m 腾出额外库容
- T3 trigger_hours=24：台风减弱，恢复 156.5m 目标，减小出库

S02 梅汛期错峰（步长 3h）：
- T0 trigger_hours=0：控制鹤城站 ≤14000 m³/s
- T1 trigger_hours=6：鹤城站上限降至 12000 m³/s
- T2 trigger_hours=12：关闸（出库 ≤400 m³/s）为青田减压
- T3 trigger_hours=24：逐步恢复出库，水位不超 161.5m

S03 极端洪水应急（步长 1h）：
- T0 trigger_hours=0：按分级规则应急调度
- T1 trigger_hours=6：大坝监测异常，最大出库限制至 8000 m³/s（is_hard_task=True）
- T2 trigger_hours=12：监测恢复，解除限制，全力泄洪
- T3 trigger_hours=36：退水阶段，控制出库 ≤6000 m³/s

S04 枯水期发电优化（步长 24h）：
- T0 trigger_hours=0：按计划消落曲线优化发电
- T1 trigger_hours=720（30天）：电网要求提升出力至额定（400 m³/s）
- T2 trigger_hours=1080（45天）：来水偏枯，出库降至最小生态流量 50 m³/s
- T3 trigger_hours=1440（60天）：恢复正常，12月末水位达 147.52m

S05 梅台过渡期（步长 3h）：
- T0 trigger_hours=0：15天内水位从 160m 降至 156.5m
- T1 trigger_hours=72（3天）：台风提前，5天内完成降水位
- T2 trigger_hours=120（5天）：台风偏移，恢复原计划节奏
- T3 trigger_hours=240（10天）：最终目标降至 155.5m

**验收**：`DYNAMIC_TRIGGERS["S01"]` 有 4 条记录，无 `adjusted_inflow` 字段，每条有 `trigger_hours` 和 `sim_hours_before`。

---

### Step 2：新增 `_advance_state()` 仿真推进函数

**文件**：`experiments/dynamic_experiment.py`

**改动**：在 `_eval_scenario()` 下方新增纯函数，**不调用 `SimulationEngine`**，仅做水量平衡代数计算：

```python
def _advance_state(scenario: dict, outflow: float, advance_hours: int) -> dict:
    """
    纯函数：用给定出库流量做水量平衡推进 advance_hours 小时，返回末态字典。
    不调用 SimulationEngine（SimulationEngine 只用于评估，不用于状态推进）。

    水量平衡公式（每时步）：
        delta_storage = (inflow - outflow) * step_seconds  [m³]
        new_storage = current_storage + delta_storage       [亿m³]
        new_level = spec.level_storage_curve.storage_to_level(new_storage)

    Args:
        scenario:      当前场景字典（含 current_level, initial_storage, inflow,
                       time_step_hours, flood_limit_level）
        outflow:       本阶段 LLM 决定的出库流量 (m³/s)，视为常数
        advance_hours: 需要推进的小时数（必须是 time_step_hours 的整数倍）

    Returns:
        {"level": float, "storage": float, "inflow": float}
    """
```

实现逻辑：
1. 从 `scenario` 读取 `current_level`、`initial_storage`（亿m³）、`inflow`、`time_step_hours`
2. 计算步数：`n_steps = advance_hours // time_step_hours`
3. 逐步迭代水量平衡：`storage += (inflow - outflow) * step_seconds / 1e8`
4. 用 `_build_tankan_spec()` 的库容曲线将 storage 转换为 level
5. 返回末态 `{"level": float, "storage": float, "inflow": float}`

注意：`advance_hours` 不整除 `time_step_hours` 时向下取整；`storage` 不低于死库容（13.94 亿m³）。

**验收**：`_advance_state(s01_scenario, 1200.0, 6)` 返回的 `level` 低于 `157.5`（预泄有效）。

---

### Step 3：新增 `evaluate_instruction_compliance()` 评估函数

**文件**：`experiments/evaluation_metrics.py`

**改动**：新增函数，Pass 条件通过 `pass_condition` 字段外置配置，不在函数内硬编码场景分支：

```python
def evaluate_instruction_compliance(
    trigger: dict,
    llm_outflow: float,
    state_before: dict,
    state_after_sim: dict,
) -> dict:
    """
    评估 LLM 响应是否达到本次指令目标。
    Pass 条件完全由 trigger["pass_condition"] 驱动，无场景硬编码。

    Returns:
        {
            "pass": bool,
            "constraint_violations": int,
            "response_direction_correct": bool,
            "is_hard_task": bool,
            "partial_credit": float,   # 0.0~1.0，接近程度（困难任务时有意义）
            "detail": str,
        }
    """
```

`pass_condition` 字段结构（在 `DYNAMIC_TRIGGERS` 中定义，不在函数内硬编码）：

```python
# 水位目标型
{"type": "level_target", "target": 156.5, "tolerance": 0.3}

# 流量上限型
{"type": "flow_limit", "max_flow": 400.0}

# 方向型（出库相对上一阶段增/减）
{"type": "direction", "expected": "decrease"}

# 困难任务型（物理矛盾，放宽 Pass 条件）
{"type": "best_effort", "primary": {"type": "flow_limit", "max_flow": 8000.0},
 "safety_constraint": {"type": "level_max", "max_level": 169.15},
 "tolerance_multiplier": 2.0}
```

`partial_credit` 计算：`1.0 - abs(actual - target) / abs(worst_case - target)`，夹紧到 [0, 1]。

**验收**：S02 T2 关闸场景（`pass_condition={"type":"flow_limit","max_flow":400}`），`llm_outflow=350` 时 `pass=True`；`llm_outflow=5000` 时 `pass=False`。S03 T1 困难任务（`type=best_effort`），任何满足大坝安全的方案均 `pass=True`，`partial_credit` 反映接近 8000 的程度。

---

### Step 4：重构 `run_multi_round_dynamic_experiment()` 主函数

**文件**：`experiments/dynamic_experiment.py`

**改动**：完全重写该函数，实现时间轴分散执行：

```
T0: 初始状态 S0 → LLM 制定方案 P0 → 评估 → _advance_state(S0, P0.outflow, sim_hours) → 状态 S1
T1: S1 + 指令 I1 → LLM 调整方案 P1 → 评估 → _advance_state(S1, P1.outflow, sim_hours) → 状态 S2
T2: S2 + 指令 I2 → LLM 调整方案 P2 → 评估 → _advance_state(S2, P2.outflow, sim_hours) → 状态 S3
T3: S3 + 指令 I3 → LLM 调整方案 P3 → 评估
```

关键实现细节：
- 每次触发前，将 `current_scenario["current_level"]`、`initial_storage`、`initial_inflow` 更新为上一阶段末态
- 将指令文本拼接到 `current_scenario["description"]` 中传给 LLM
- 每个阶段调用 `experiment.run_scenario(current_scenario)` 获取 LLM 出库流量
- 调用 `evaluate_instruction_compliance()` 评估达标情况
- 调用 `_advance_state()` 推进状态

输出结构：
```python
{
    "scenario_id": "S01",
    "stages": [
        {
            "stage": "T0",
            "trigger_hours": 0,
            "instruction": "...",
            "state_before": {"level": 157.5, "storage": ..., "inflow": ...},
            "llm_outflow": 1200.0,
            "compliance": {"pass": True, "constraint_violations": 0, ...},
            "state_after_sim": {"level": 157.1, ...},
        },
        ...
    ],
    "overall_pass_rate": 0.75,
    "stage_pass_count": 3,
    "stage_total": 4,
}
```

**验收**：S01 运行后 `stages` 有 4 条，`stages[1]["state_before"]["level"]` 不等于初始 `157.5`（状态已演变）。

---

### Step 5：更新 `_apply_trigger()` 函数

**文件**：`experiments/dynamic_experiment.py`

**改动**：
- 移除 `adjusted_inflow` 相关逻辑
- 只更新 `description`（拼接指令文本）和 `dynamic_trigger` / `trigger_type` 字段
- 新增 `current_level` / `initial_storage` / `initial_inflow` 的注入逻辑（从 `state_dict` 参数传入）

---

### Step 6：更新输出格式和批量接口

**文件**：`experiments/dynamic_experiment.py`

**改动**：
- `run_all_multi_round()`：更新为调用新版主函数，输出包含 `overall_pass_rate`
- `run_dynamic_experiments()`：保留旧接口签名，内部适配新版输出格式，确保 `paper_experiment_runner.py` 不需要修改
- 结果文件路径：`results/dynamic/{sid}_stages.json`（新格式）+ 保留 `{sid}_summary.json`（兼容旧格式）

---

### Step 7：更新 `paper_experiment_runner.py` 动态汇总

**文件**：`experiments/paper_experiment_runner.py`

**改动**：`run_all_multi_round()` 的汇总逻辑从"delta 评分趋势"改为"指令达标率"：

```python
dynamic_summary = {
    "total": len(valid_dynamic),
    "overall_pass_rate": avg([r["overall_pass_rate"] for r in valid_dynamic]),
    "per_scenario_pass_rates": {r["scenario_id"]: r["overall_pass_rate"] for r in valid_dynamic},
    "hard_task_partial_credits": {...},
}
```

---

## 三、风险点与缓解措施

| 风险 | 可能性 | 缓解措施 |
|------|--------|---------|
| `_advance_state()` 中 `ForecastBundle` 构造方式与 `_run_pyresops_eval()` 不一致 | 中 | 直接复用 `_run_pyresops_eval()` 的构造模式，提取公共函数 |
| S03 T1 困难任务 LLM 完全无视约束冲突 | 高 | `is_hard_task=True` 时 Pass 条件放宽，记录 `hard_task_partial_credit` |
| S04 步长 24h 导致 `advance_hours` 计算偏差 | 低 | `sim_hours_before` 必须是 `time_step_hours` 整数倍，加断言检查 |
| 旧版 `run_dynamic_experiments()` 接口被 `paper_experiment_runner.py` 依赖 | 高 | Step 6 保留旧接口签名；在回归测试中用固定 fixture（mock LLM 返回固定出库值）对比重构前后输出，确保 `adjustment_effective` / `constraint_achievement_rate` / `score_change` 字段值不变 |

---

## 四、验收标准（可测试）

### 单元级
```python
# _advance_state 正确推进状态
state = _advance_state(s01_scenario, 1200.0, 6)
assert state["level"] < 157.5

# evaluate_instruction_compliance 正确判断
result = evaluate_instruction_compliance(s02_t2_trigger, 350.0, state_before, state_after)
assert result["pass"] == True
result2 = evaluate_instruction_compliance(s02_t2_trigger, 5000.0, state_before, state_after)
assert result2["pass"] == False
```

### 集成级
```python
# 状态真实演变
summary = run_multi_round_dynamic_experiment("S01", ...)
assert len(summary["stages"]) == 4
assert summary["stages"][1]["state_before"]["level"] != 157.5  # 状态已演变
assert summary["stages"][2]["state_before"]["level"] != summary["stages"][1]["state_before"]["level"]
assert "overall_pass_rate" in summary
```

### 回归级
```python
# 旧接口不崩溃
results = run_dynamic_experiments(scenario_ids=["S01"])
assert "adjustment_effective" in results[0]
assert "constraint_achievement_rate" in results[0]
```

### 语义级（人工核查）
- S01 T3（台风减弱）：LLM 出库应低于 T2 阶段
- S02 T2（关闸）：`llm_outflow` ≤ 400 m³/s
- S03 T1（困难任务）：LLM 回复文本中应包含对约束冲突的说明

---

## 五、实施顺序

```
Step 1（重写 DYNAMIC_TRIGGERS）
    ↓
Step 5（更新 _apply_trigger）
    ↓
Step 2（新增 _advance_state）  ←→  Step 3（新增 evaluate_instruction_compliance）
    ↓
Step 4（重构主函数）
    ↓
Step 6（更新输出格式和批量接口）
    ↓
Step 7（更新 paper_experiment_runner 汇总）
```

Step 2 和 Step 3 可并行；其余按顺序执行。

---

## 六、不在本次范围内

- `automated_experiment.py`（场景三）：独立新文件，不在本次重构范围
- `static_experiment.py`：无需修改
- `pyresops` 核心库：只读调用，不修改
- `scenarios/*.md`：入库预报数据来源，只读

---

## 七、ADR（架构决策记录）

**决策**：用 `SimulationEngine` 做阶段间状态推进，而非简单水量平衡计算

**驱动**：需要完整的约束校核和模块调度逻辑，确保推进后的状态与 pyresops 评估体系一致

**替代方案**：`HydraulicsCalculator.water_balance_step()`（简单但不完整）

**为何选择**：`SimulationEngine` 已在 `_run_pyresops_eval()` 中验证可用，复用成本低，状态完整性高

**后果**：每次阶段推进需要构造完整的 `ForecastBundle` 和 `DispatchProgram`，代码量稍多，但逻辑清晰

**后续**：若性能成为问题，可考虑缓存 `ReservoirSpec` 对象
