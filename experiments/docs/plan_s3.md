# 实验三重设计计划 v2 — 预测-实际偏差场景下的滚动控制能力对比

## 一、定位与研究问题

**新定位**：不再测试"自动化是否会滚动更新"，而是测试：
> 在预测与实际来水存在结构化偏差的异常场景下，静态执行、规则型修正、LLM 调用现有调度工具三种控制方式，谁更能在规则约束下维持安全、有效、稳定的滚动调度？

**核心研究问题**：
当预测过程与实际来水过程存在偏差、运行状态持续变化时，
1. 静态方案直接执行（Static Plan）
2. 基于既有调度规程的规则型修正（Rule-based Adjustment）
3. 在相同规则边界内由 LLM 调用现有调度工具进行方案修正（LLM-based Control）

三种方式谁更能维持安全、有效、稳定的滚动调度？

---

## 二、与现有代码的映射关系

| 新设计概念 | 现有代码对应 | 改动方向 |
|---|---|---|
| StaticPlanController | `run_no_switch_baseline()` (no_switch_mode=True) | 重命名 + 接入 DeviationScenario |
| RuleBasedAdjustmentController | `HeuristicRollingBaseline` in baseline_heuristic.py | 扩展规则逻辑，接入 DeviationScenario |
| LLMToolBasedController | `AutoDispatchController` | 替换 ForecastUpdateSimulator → DeviationScenarioSimulator |
| DeviationScenarioSimulator | `ForecastUpdateSimulator` | 重写：接受预定义 forecast_sequence + actual_inflow_sequence |
| RollingControlResult | `AutomatedResult` in result_schema.py | 新增 rolling control 指标字段 |
| scenarios_config.yaml deviation_config | `automated_config` | 新增 deviation_scenarios 子节点 |

**可直接复用（不改动）**：
- `_advance_state()` — 水量平衡状态推进
- `_eval_scenario()` / `_run_pyresops_eval()` — pyresops 统一评估
- `evaluate_instruction_compliance()` — 约束检查
- `AgnoMCPExperiment.run_scenario()` — LLM 工具调用执行器

---

## 三、场景配置设计

### 3.1 scenarios_config.yaml 新增结构

在 S02 和 S04 的 `automated_config` 下新增 `deviation_scenarios` 列表：

```yaml
automated_config:
  S02:
    # 保留原有字段（向后兼容）
    true_inflow: 3380.0
    forecast_interval_hours: 6
    error_near: 0.05
    error_mid: 0.20
    error_far: 0.40
    key_dims: [flood_control_score, ecological_score]
    switch_threshold: 0.10
    # 新增：结构化偏差场景
    deviation_scenarios:
      - id: S02-D0
        name: "无偏差基线"
        deviation_type: none
        # forecast_sequence 与 actual_inflow_sequence 相同
        actual_peak_flow: 3380.0
        actual_peak_hour: 24          # 洪峰出现时刻（相对起始小时）
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D1a
        name: "峰现提前6h"
        deviation_type: timing_early
        actual_peak_flow: 3380.0
        actual_peak_hour: 18          # 实际提前6h
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D1b
        name: "峰现滞后6h"
        deviation_type: timing_late
        actual_peak_flow: 3380.0
        actual_peak_hour: 30
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D2a
        name: "峰值增大20%"
        deviation_type: magnitude_high
        actual_peak_flow: 4056.0      # 3380 * 1.20
        actual_peak_hour: 24
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D2b
        name: "峰值增大40%"
        deviation_type: magnitude_high
        actual_peak_flow: 4732.0      # 3380 * 1.40
        actual_peak_hour: 24
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D2c
        name: "峰值减小20%"
        deviation_type: magnitude_low
        actual_peak_flow: 2704.0      # 3380 * 0.80
        actual_peak_hour: 24
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D3a
        name: "峰现提前+峰值增大（压力测试）"
        deviation_type: combined_worst
        actual_peak_flow: 4732.0      # +40%
        actual_peak_hour: 18          # 提前6h
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24
      - id: S02-D3b
        name: "峰现滞后+峰值减小"
        deviation_type: combined_mild
        actual_peak_flow: 2704.0      # -20%
        actual_peak_hour: 30
        forecast_peak_flow: 3380.0
        forecast_peak_hour: 24

  S04:
    # 保留原有字段
    true_inflow: 70.0
    forecast_interval_hours: 240
    error_xun: 0.15
    key_dims: [power_generation_score, ecological_score]
    switch_threshold: 0.10
    # 新增：结构化偏差场景
    deviation_scenarios:
      - id: S04-D0
        name: "无偏差基线"
        deviation_type: none
        xun_actual: [70.0, 70.0, 70.0]   # 三旬实际来水
        xun_forecast: [70.0, 70.0, 70.0]
      - id: S04-D1a
        name: "单旬偏枯-15%"
        deviation_type: single_xun_low
        xun_actual: [59.5, 70.0, 70.0]   # 第一旬 -15%
        xun_forecast: [70.0, 70.0, 70.0]
      - id: S04-D1b
        name: "单旬偏枯-30%"
        deviation_type: single_xun_low
        xun_actual: [49.0, 70.0, 70.0]   # 第一旬 -30%
        xun_forecast: [70.0, 70.0, 70.0]
      - id: S04-D2
        name: "连续偏枯"
        deviation_type: consecutive_low
        xun_actual: [49.0, 52.5, 70.0]   # 前两旬持续偏枯
        xun_forecast: [70.0, 70.0, 70.0]
      - id: S04-D3a
        name: "前丰后枯"
        deviation_type: phase_shift
        xun_actual: [91.0, 49.0, 70.0]   # 第一旬偏丰，第二旬偏枯
        xun_forecast: [70.0, 70.0, 70.0]
      - id: S04-D3b
        name: "前枯后丰"
        deviation_type: phase_shift
        xun_actual: [49.0, 91.0, 70.0]
        xun_forecast: [70.0, 70.0, 70.0]
```

### 3.2 DeviationScenarioSimulator 设计

替换 `ForecastUpdateSimulator`，接受预定义序列而非随机扰动：

```python
@dataclass
class DeviationUpdate:
    update_index: int
    elapsed_hours: float
    remaining_hours: float
    forecast_inflow: float    # 当前时刻可见的预测来水
    actual_inflow: float      # 真实来水（驱动状态推进）
    deviation_id: str         # 对应哪个偏差场景

class DeviationScenarioSimulator:
    """
    基于预定义 forecast_sequence + actual_inflow_sequence 生成更新序列。
    不使用随机扰动，而是使用结构化偏差场景。
    """
    def __init__(self, scenario_cfg: dict, deviation_cfg: dict):
        self.scenario_cfg = scenario_cfg
        self.deviation_cfg = deviation_cfg

    def generate_sequence(self) -> list[DeviationUpdate]:
        """
        根据 deviation_cfg 中的 actual/forecast 参数，
        生成与 ForecastUpdate 接口兼容的 DeviationUpdate 列表。
        S02: 基于三角波形生成洪水过程，按 peak_flow/peak_hour 参数化
        S04: 按 xun_actual/xun_forecast 列表逐旬生成
        """
        ...

    def _build_flood_hydrograph(
        self, peak_flow: float, peak_hour: int, total_hours: int
    ) -> list[float]:
        """生成三角形洪水过程线（简化版）"""
        ...
```

---

## 四、三类控制器设计

### 4.1 StaticPlanController

```python
class StaticPlanController:
    """
    初始时刻生成一份静态方案，后续不做任何调整。
    对应现有 run_no_switch_baseline() 逻辑。
    """
    def __init__(self, scenario_cfg: dict, experiment: AgnoMCPExperiment):
        self.scenario_cfg = scenario_cfg
        self.experiment = experiment
        self.initial_outflow: float | None = None

    def run(self, updates: list[DeviationUpdate]) -> RollingControlResult:
        # Step 1: T0 时刻用预测来水生成初始方案
        # Step 2: 后续所有步骤沿用 initial_outflow，不调用 LLM
        # Step 3: 用 actual_inflow 推进真实状态
        # Step 4: 统一评估
        ...
```

### 4.2 RuleBasedAdjustmentController

```python
class RuleBasedAdjustmentController:
    """
    按既有水库调度规程进行规则型修正，不调用优化算法。
    扩展自 HeuristicRollingBaseline，增加 DeviationUpdate 接口。

    S02 规则：
      - 正常：outflow = min(actual_inflow, downstream_limit)
      - 安全触发：若 current_level > warning_level，强制加大出库
      - 安全触发：若 current_level < dead_level，强制减小出库

    S04 规则：
      - 正常：outflow = max(min_ecological_flow, actual_inflow * generation_ratio)
      - 安全触发：若 current_level < min_level，减小出库保水
    """
    def __init__(self, scenario_cfg: dict, deviation_cfg: dict):
        ...

    def _compute_rule_outflow(
        self, state: dict, forecast_inflow: float, actual_inflow: float
    ) -> float:
        """核心规则逻辑，不调用 LLM，不调用优化算法"""
        ...

    def run(self, updates: list[DeviationUpdate]) -> RollingControlResult:
        ...
```

### 4.3 LLMToolBasedController

```python
class LLMToolBasedController:
    """
    LLM 在规则约束下调用现有调度工具进行方案修正。
    基于 AutoDispatchController 重构，替换 ForecastUpdateSimulator。
    
    关键约束：
    - LLM 不直接生成调度数值
    - 必须通过 query_dispatch_rules / simulate_dispatch_program /
      evaluate_dispatch_result / optimize_release_plan 等工具完成决策
    - 输出方案必须通过 check_safety_constraints 验证
    """
    def __init__(
        self,
        scenario_cfg: dict,
        experiment: AgnoMCPExperiment,
        switch_threshold: float = 0.10,
    ):
        ...

    def run(self, updates: list[DeviationUpdate]) -> RollingControlResult:
        # 与 AutoDispatchController.run() 结构相同
        # 区别：使用 actual_inflow 推进状态，forecast_inflow 传给 LLM
        ...
```

---

## 五、触发机制

两类触发，简化实现：

```python
def _should_trigger_correction(
    state: dict,
    scenario_cfg: dict,
    update: DeviationUpdate,
    update_index: int,
    update_interval: int,
) -> tuple[bool, str]:
    """
    返回 (should_trigger, reason)
    reason: "scheduled" | "safety_level" | "safety_deviation"
    """
    # 1. 固定周期触发
    if update_index % update_interval == 0:
        return True, "scheduled"

    # 2. 安全异常触发（轻量级）
    warning_level = scenario_cfg.get("warning_level")
    if warning_level and state["level"] > warning_level:
        return True, "safety_level"

    # 3. 状态明显偏离原方案假设
    deviation_threshold = scenario_cfg.get("state_deviation_threshold", 0.05)
    if abs(state["inflow"] - update.forecast_inflow) / update.forecast_inflow > deviation_threshold:
        return True, "safety_deviation"

    return False, ""
```

---

## 六、结果 Schema 扩展

在 `result_schema.py` 新增 `RollingControlResult`（或扩展 `AutomatedResult`）：

```python
@dataclass
class RollingControlResult:
    # 基础标识
    scenario_id: str
    deviation_id: str
    deviation_type: str
    controller_type: str          # "static" | "rule_based" | "llm_tool"

    # 安全类指标
    total_constraint_violations: int
    max_level_exceedance: float   # 最大超限水位（m），0 表示无超限
    has_critical_risk: bool       # 是否出现明显风险状态

    # 调度效果类指标
    key_dimension_scores: dict    # S02: {flood_control, ecological}; S04: {power_generation, ecological}
    overall_score: float
    performance_degradation: float  # 相比无偏差基线的性能下降幅度（0~1）

    # 滚动控制类指标
    correction_count: int         # 修正次数
    effective_correction_count: int  # 有效修正次数（修正后得分提升）
    effective_correction_rate: float  # 有效修正率 = effective / correction_count
    recovery_steps: int           # 从异常出现到恢复稳定所需步数（-1 表示未恢复）

    # 鲁棒性（跨偏差场景聚合时使用）
    # worst_case_score 和 mean_score 在 aggregate() 中计算

    # 原有字段保留（向后兼容）
    forecast_steps: int = 0
    switch_occurred: bool = False
    is_heuristic_baseline: bool = False
    raw_eval_results: list[dict] = field(default_factory=list)
```

---

## 七、主运行函数设计

```python
def run_deviation_experiment(
    scenario_id: str,           # "S02" or "S04"
    deviation_id: str,          # e.g. "S02-D3a"
    controller_type: str,       # "static" | "rule_based" | "llm_tool"
    experiment: AgnoMCPExperiment | None = None,
    save_result: bool = True,
) -> RollingControlResult:
    """单个偏差场景 × 单个控制器的完整运行"""
    ...

def run_all_deviation_experiments(
    scenario_ids: list[str] = ("S02", "S04"),
    controller_types: list[str] = ("static", "rule_based", "llm_tool"),
    model_profile: str = "default",
) -> list[RollingControlResult]:
    """
    全量运行：2 场景 × N 偏差子场景 × 3 控制器
    S02: 8 偏差场景 × 3 = 24 runs
    S04: 6 偏差场景 × 3 = 18 runs
    共 42 runs
    """
    ...

def aggregate_results(
    results: list[RollingControlResult],
) -> dict:
    """
    按 controller_type 聚合，计算：
    - mean_score per controller
    - worst_case_score per controller
    - mean_constraint_violations per controller
    - mean_effective_correction_rate (rule_based, llm_tool only)
    """
    ...
```

---

## 八、需要修改的文件清单

### 8.1 `experiments/scenarios_config.yaml`
- 在 S02 和 S04 的 `automated_config` 下新增 `deviation_scenarios` 列表（见第三节）
- 新增 `warning_level`、`state_deviation_threshold` 字段

### 8.2 `experiments/automated_experiment.py`
- 新增 `DeviationUpdate` dataclass（替代 `ForecastUpdate`）
- 新增 `DeviationScenarioSimulator` 类（替代 `ForecastUpdateSimulator`）
- 新增 `StaticPlanController` 类
- 新增 `RuleBasedAdjustmentController` 类
- 新增 `LLMToolBasedController` 类（重构自 `AutoDispatchController`）
- 新增 `run_deviation_experiment()` 和 `run_all_deviation_experiments()`
- 保留原有 `ForecastUpdateSimulator`、`AutoDispatchController`、`run_automated_experiment()` 不删除（向后兼容）
- 更新模块 docstring：从"滚动预报更新自动化调度"改为"预测-实际偏差场景下的滚动控制能力对比"

### 8.3 `experiments/result_schema.py`
- 新增 `RollingControlResult` dataclass
- 保留 `AutomatedResult` 不变

### 8.4 `experiments/baseline_heuristic.py`
- 扩展 `HeuristicRollingBaseline`，增加 `run_deviation(updates: list[DeviationUpdate])` 方法
- 或直接在 `RuleBasedAdjustmentController` 中内联规则逻辑（推荐，避免跨文件依赖）

### 8.5 `experiments/unified_runner.py`
- 新增 `run_deviation_tier()` 函数，调用 `run_all_deviation_experiments()`
- 在 `run_all()` 中增加 `deviation` 实验类型分支

### 8.6 `experiments/paper_experiment_runner.py`
- `summarize_all_results()` 新增 `deviation_results` 参数（默认 None，向后兼容）
- 新增 `summarize_deviation_results()` 函数，输出按控制器类型分组的聚合表

---

## 九、评价指标实现要点

### 9.1 有效修正率计算

```python
def compute_effective_correction_rate(
    correction_events: list[dict],  # [{before_score, after_score, trigger_reason}]
) -> float:
    if not correction_events:
        return 0.0
    effective = sum(1 for e in correction_events if e["after_score"] > e["before_score"])
    return effective / len(correction_events)
```

### 9.2 恢复步数计算

```python
def compute_recovery_steps(
    score_sequence: list[float],
    anomaly_start_index: int,
    recovery_threshold: float = 0.9,  # 恢复到基线得分的 90%
    baseline_score: float = 1.0,
) -> int:
    target = baseline_score * recovery_threshold
    for i in range(anomaly_start_index, len(score_sequence)):
        if score_sequence[i] >= target:
            return i - anomaly_start_index
    return -1  # 未恢复
```

### 9.3 性能下降幅度

```python
def compute_performance_degradation(
    scenario_score: float,
    baseline_score: float,  # 对应 D0（无偏差基线）的得分
) -> float:
    if baseline_score <= 0:
        return 0.0
    return max(0.0, (baseline_score - scenario_score) / baseline_score)
```

---

## 十、实现顺序（推荐）

1. **Step 1**：更新 `scenarios_config.yaml`，添加 `deviation_scenarios` 配置
2. **Step 2**：在 `result_schema.py` 新增 `RollingControlResult`
3. **Step 3**：在 `automated_experiment.py` 实现 `DeviationUpdate` + `DeviationScenarioSimulator`
4. **Step 4**：实现 `StaticPlanController`（最简单，无 LLM 调用）
5. **Step 5**：实现 `RuleBasedAdjustmentController`（规则逻辑，无 LLM）
6. **Step 6**：实现 `LLMToolBasedController`（基于 AutoDispatchController 重构）
7. **Step 7**：实现 `run_deviation_experiment()` 和 `run_all_deviation_experiments()`
8. **Step 8**：更新 `unified_runner.py` 和 `paper_experiment_runner.py`
9. **Step 9**：运行 D0（无偏差基线）验证三个控制器输出一致
10. **Step 10**：运行 S02-D3a（最危险场景）验证 LLM 控制器优势

---

## 十一、ADR — DeviationScenarioSimulator 设计决策

**决策**：用 `DeviationScenarioSimulator` 替换 `ForecastUpdateSimulator`，接受预定义序列而非随机扰动。

**驱动因素**：
- 实验可重复性：随机扰动导致每次运行结果不同，无法做公平对比
- 场景可解释性：结构化偏差类型（峰现时间偏差、量级偏差、联合偏差）比随机噪声更有工程意义
- 论文叙事需要：需要明确说明"在 X 类偏差下，LLM 控制器比规则控制器好 Y%"

**替代方案**：保留随机扰动，增加 seed 固定 → 拒绝，因为随机扰动无法构造"峰现提前"这类有方向性的偏差

**后果**：
- 需要为 S02 实现三角波形洪水过程线生成器（`_build_flood_hydrograph`）
- 需要为 S04 实现逐旬来水序列生成器
- `ForecastUpdateSimulator` 保留不删除，供原有 automated 实验向后兼容

---

## 十二、一句话版本

实验三不再测试"自动化是否会滚动更新"，而是测试：
**在预测与实际存在结构化偏差的异常场景下，静态执行、规则型修正和 LLM 调用现有调度工具三种控制方式，谁更能在规则约束下维持安全、有效、稳定的滚动调度。**
