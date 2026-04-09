# experiments/ 重构总结文档

## 重构背景

原 `experiments/` 目录存在根本性架构错误：**完全没有使用已构建好的 `pyresops` 库**，而是自行重新实现了一套假工具（硬编码参数如 `FLOOD_LIMIT_LEVEL=985.0`），与实际滩坑水电站参数（`flood_limit_level=156.5m` 台汛期 / `160.0m` 梅汛期）严重不符。

---

## 重构后架构

```
experiments/
├── paper_experiment_runner.py   # 核心：agno Agent + pyresops 真实工具
├── baseline_human.py            # 人工基线：调用 SimulationEngine + EvaluationService
├── evaluation_metrics.py        # 评估指标：调用 EvaluationService 对比两种方法
└── run_experiments.py           # 入口：5个场景完整实验
```

---

## pyresops 核心接口（已确认）

### 1. SimulationEngine
```python
from pyresops.core import SimulationEngine

engine = SimulationEngine(spec)
result = engine.simulate(
    program,       # DispatchProgram
    state,         # ReservoirState
    forecast,      # ForecastData
    modules_map,   # dict[str, Module]
    policy_bundle=policy  # PolicyBundle（可选）
)
```

### 2. EvaluationService
```python
from pyresops.core import EvaluationService

svc = EvaluationService(spec)
eval_result = svc.evaluate(result, constraint_set=cs)
# 返回 EvaluationResult:
#   overall_score, flood_control_score, water_supply_score,
#   power_generation_score, ecological_score
```

### 3. OptimizationService
```python
from pyresops.core import OptimizationService

opt = OptimizationService(spec, program_svc)
opt_result = opt.optimize_flexible_release_plan(...)
```

### 4. ConstraintValidator
```python
from pyresops.core import ConstraintValidator

validator = ConstraintValidator(constraint_set)
violations = validator.validate_simulation(result)
```

---

## 滩坑水电站真实参数

| 参数 | 值 |
|------|-----|
| dead_level | 120 m |
| normal_level | 160 m |
| flood_limit_level（台汛期） | 156.5 m |
| flood_limit_level（梅汛期） | 160.0 m |
| installed_capacity | 600 MW |

---

## 五个调度场景

| 场景 | 名称 | flood_limit_level |
|------|------|-------------------|
| S01 | 台汛预泄优化 | 156.5 m |
| S02 | 梅汛洪峰错峰 | 160.0 m |
| S03 | 极端洪水应急响应 | 156.5 m |
| S04 | 枯水期发电优化 | 160.0 m |
| S05 | 梅台过渡期综合调度 | 158.0 m |

---

## agno 工具定义（paper_experiment_runner.py）

```python
from agno.tools import tool as agno_tool

def _make_tools(spec: ReservoirSpec):
    @agno_tool
    def get_reservoir_status(...) -> dict:
        """查询水库当前状态"""
        ...

    @agno_tool
    def simulate_dispatch_program(...) -> dict:
        """调用 SimulationEngine.simulate()"""
        engine = SimulationEngine(spec)
        result = engine.simulate(program, state, forecast, modules_map)
        ...

    @agno_tool
    def evaluate_dispatch_result(...) -> dict:
        """调用 EvaluationService.evaluate()"""
        svc = EvaluationService(spec)
        eval_result = svc.evaluate(result, constraint_set=cs)
        ...

    @agno_tool
    def check_safety_constraints(...) -> dict:
        """调用 spec.discharge_capacity.get_max_discharge()"""
        ...

    @agno_tool
    def optimize_release_plan(...) -> dict:
        """调用 OptimizationService.optimize_flexible_release_plan()"""
        ...

    @agno_tool
    def query_dispatch_rules(...) -> dict:
        """返回《水库控制运用计划》真实规程"""
        ...

    return [get_reservoir_status, simulate_dispatch_program,
            evaluate_dispatch_result, check_safety_constraints,
            optimize_release_plan, query_dispatch_rules]
```

---

## 下一步操作（新对话中执行）

### 1. 安装 agno
```bash
cd E:/PyCode/PyResOps
.venv/Scripts/pip.exe install agno
```

### 2. 验证导入
```bash
.venv/Scripts/python.exe -c "
from experiments.paper_experiment_runner import SCENARIOS
print(f'场景数量: {len(SCENARIOS)}')
for s in SCENARIOS:
    print(f'  {s[\"id\"]}: {s[\"name\"]}')
"
```
期望输出：5个场景

### 3. 测试人工基线（S04枯水期，不需要 agno）
```bash
.venv/Scripts/python.exe -c "
from experiments.baseline_human import HumanBaselineScheduler
from experiments.paper_experiment_runner import SCENARIOS
r = HumanBaselineScheduler().schedule(SCENARIOS[3])
print('出力:', r['outflow'])
print('综合评分:', r['overall_score'])
"
```

### 4. 运行完整实验
```bash
.venv/Scripts/python.exe experiments/run_experiments.py
```

---

## 已知问题

- **Git Bash 退出码49**：当前 Git Bash 环境异常，所有 Bash 命令返回退出码49，无法获取标准输出。建议在新对话中使用 PowerShell 或 CMD 终端验证代码。
- **agno 未安装**：需要手动安装 `agno` 包。

---

*文档生成时间：2026-04-09*
