# PyResOps

[English](README.md) | **中文**

PyResOps 是一个面向单水库调度的 Python 框架，支持调度方案建模、仿真、优化、评估、插件执行，以及基于 LLM/MCP 的工具化验证流程。

项目的核心原则是：不能让 LLM 凭空生成水库调度决策。有效决策必须能够转化为可执行的调度程序，通过结构化 schema 校验，经过仿真和评估，并留下可追溯证据。如果缺少必要工具、工具调用顺序错误、输出无法信任，或违反硬安全约束，流程应 fail closed，而不是把自然语言文本当作有效结果。

## 仓库内容

- `pyresops`：可复用的水库调度内核，包括领域模型、仿真、优化、评估、规则、约束、插件、持久化、FastMCP 工具和 Agno Agent 集成。
- `experiments`：基于真实洪水事件 CSV 数据的研究和论文验证层，包括静态、动态、滚动三类调度场景。
- `tests`：覆盖内核、服务、插件、模块、约束、provider 和实验 workflow 的单元测试与集成测试。
- `docs`：架构说明、示例和论文相关文档。

本仓库适合作为工程研究框架和实验复现内核。它不是开箱即用的生产级水文预报系统，也不能替代具体水库的率定、运行管理权限或正式安全审查。

## 主要能力

- 基于水量平衡和泄流能力曲线的单水库仿真。
- 使用可执行调度程序，而不是纯文本下泄建议。
- 六类与论文 taxonomy 对齐的基础下泄模块。
- 规则、约束、指标、provider 和执行插件扩展点。
- 候选方案、工作方案、归档方案组成的滚动调度状态管理。
- FastMCP 服务，暴露水库、方案、仿真、评估、优化、插件和滚动调度工具。
- Agno runtime，支持受约束工具调用、JSON payload 校验和工具 trace 检查。
- 静态、动态、滚动三类真实数据验证 workflow。
- 面向论文的消融、命令挑战、MCP skill、gate check 和表格导出实验流水线。

## 设计原则

### 工具优先的决策

每个调度决策都应可执行、可仿真、可评估。有效决策是 `DispatchProgram` 加上必要元数据和证据，而不是一段文字建议。

### 明确边界

`pyresops` 负责核心工程逻辑；`experiments` 负责研究协议、场景展开、论文阶段和结果导出。这样内核不会被某一次论文实验绑定，实验层也可以独立演进。

### 结构化数据契约

水库状态、预报、调度程序、policy bundle、评估结果、编译后的 dispatch contract、workflow stage 和 MCP payload 都使用类型模型或明确 schema 表示。无法解析或不符合契约的模型输出应视为失败。

### 硬约束优先于操作指令

安全约束与操作指令完成度分开判断。目标水位尚未完全达到可以记录为 `in_progress`，但硬安全约束违规、工具链无效或工具结果不可信会导致流程失败。

### 真实数据和显式质量标签

实验 workflow 使用真实洪水事件 CSV。数据质量会显式标注，例如 `strict_clean`、`repaired_executable` 或 `diagnostic_only`，而不是被预处理过程隐藏。

## 仓库结构

```text
pyresops/
  domain/        水库、预报、方案、模块、policy、结果、规则、约束、目标和
                 dispatch contract 等领域对象。
  core/          仿真引擎、水力计算、编排、校验、动作解析、场景时间契约和
                 模块族优化。
  modules/       支持的下泄模块族。
  services/      snapshot、program、simulation、optimization、evaluation、
                 explanation、dispatch-contract compiler 和 rolling ops 服务。
  constraints/   约束 SPI、注册表、loader、factory 和内置约束。
  rules/         规则 SPI、表达式求值、注册表和动作规范化。
  metrics/       指标 SPI 和内置评估指标。
  plugins/       执行插件框架，以及内置 input、step、post 插件。
  providers/     从 YAML/CSV 物化水库、预报、方案和场景对象。
  tools/         FastMCP 工具注册模块。
  agents/        Agno 模型配置、prompt、runtime、runner 和工具 bundle。
  storage/       SQLite repository，保存方案、结果、快照、事件、归档方案和
                 decision trace。
  server.py      FastMCP 服务组装入口。
  cli.py         `pyresops-server` 命令入口。

experiments/
  config/              水库、模型、场景和验证 YAML 配置。
  data_adapters/       真实洪水事件加载与预处理。
  workflows/           静态、动态、滚动 workflow 契约。
  validation/          场景展开、执行、JSONL 记录、CSV/Markdown 汇总。
  paper_validation/    论文阶段 runner、MCP-skill runner、gate、命令挑战、
                       数据冻结、失败分类和表格导出。
  stage1/ stage2/ stage3/
                       分阶段实验实现。
  run_*.py             实验入口脚本。
```

## 安装

PyResOps 要求 Python 3.11 或更高版本。

本地 editable 安装：

```bash
pip install -e .
```

或使用 `uv`：

```bash
uv pip install -e .
```

安装开发依赖：

```bash
uv sync --group dev
```

构建 wheel：

```bash
uv build
```

## 启动 MCP 服务

安装后运行：

```bash
pyresops-server
```

或：

```bash
python -m pyresops.server
```

指定水库配置：

```powershell
$env:PYRESOPS_RESERVOIR_CONFIG="E:\PyCode\PyResOps\experiments\config\default_reservoir.yaml"
pyresops-server
```

## 最小 Python 示例

```python
from datetime import datetime

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import TimeHorizon
from pyresops.domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
    ReservoirState,
)
from pyresops.services import ProgramService, SimulationService

spec = ReservoirSpec(
    id="demo",
    name="Demo Reservoir",
    dead_level=150.0,
    normal_level=175.0,
    flood_limit_level=145.0,
    design_flood_level=180.0,
    check_flood_level=185.0,
    total_capacity=39.3,
    flood_capacity=22.15,
    level_storage_curve=LevelStorageCurve(
        levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
        storages=[0.0, 10.0, 20.0, 30.0, 39.3, 51.6],
    ),
    discharge_capacity=DischargeCapacity(
        levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
        max_discharges=[0.0, 5000.0, 10000.0, 15000.0, 20000.0, 30000.0],
    ),
)

program_service = ProgramService()
simulation_service = SimulationService(spec, program_service.get_module_registry())

start = datetime(2024, 7, 1, 0, 0, 0)
program = program_service.create_program(
    name="demo_program",
    time_horizon=TimeHorizon(start=start, end=start.replace(hour=3), time_step=3600),
    module_configs=[
        {"module_type": "constant_release", "parameters": {"target_release": 800.0}},
    ],
)

initial_state = ReservoirState(
    timestamp=start,
    level=165.0,
    storage=30.0,
    inflow=800.0,
    outflow=800.0,
)

forecast = ForecastBundle(
    forecast_time=start,
    series=[
        ForecastSeries(
            variable="inflow",
            timestamps=[
                datetime(2024, 7, 1, 0, 0, 0),
                datetime(2024, 7, 1, 1, 0, 0),
                datetime(2024, 7, 1, 2, 0, 0),
                datetime(2024, 7, 1, 3, 0, 0),
            ],
            values=[800.0, 900.0, 850.0, 780.0],
            unit="m3/s",
        )
    ],
)

result = simulation_service.run_simulation(program, initial_state, forecast)
print(result.max_level, result.avg_outflow)
```

## 实验命令

只检查真实数据 workflow contract，不调用 Agno 模型：

```bash
uv run python experiments/run_realdata_workflows.py --contract-only --workflow all
```

使用模型 profile 运行真实数据 workflow：

```bash
uv run python experiments/run_realdata_workflows.py --workflow static --model-profile deepseek
```

运行论文验证 phase：

```bash
uv run python experiments/run_paper_validation.py --phase data-freeze
uv run python experiments/run_paper_validation.py --phase mcp-skill-smoke --model-profile deepseek_v4_pro --limit-events 1
uv run python experiments/run_paper_validation.py --phase component-ablation --model-profile deepseek_v4_pro
uv run python experiments/run_paper_validation.py --phase command-challenge --model-profile deepseek_v4_pro
```

检查论文验证 gate：

```bash
uv run python experiments/check_paper_validation_gates.py --latest
```

模型调用需要通过本地配置或环境变量提供 provider 配置和 API key，例如 `DEEPSEEK_API_KEY`。不要提交本地 provider 密钥。

## 数据策略

仓库只保留少量代表性样例数据。批量真实事件数据、派生数据、日志、JSONL trace、生成图表和本地 provider 凭据都应由 `.gitignore` 忽略。

## 测试和 Lint

运行完整测试：

```bash
uv run pytest tests -q
```

运行重点测试：

```bash
uv run pytest tests/test_experiments/test_paper_validation.py -q
uv run pytest tests/test_services -q
uv run pytest tests/test_modules -q
```

运行 lint：

```bash
uv run ruff check pyresops experiments tests
```

## 当前成熟度和边界

PyResOps 适合用于：

- 本地包开发；
- 确定性的单水库调度仿真；
- 规则、约束、指标和插件扩展实验；
- 支持的下泄模块族参数优化；
- 静态、动态、滚动真实数据 workflow 验证；
- MCP 驱动的 Agent 工具流程验证；
- 论文消融、命令挑战和 gate-checking 实验。

PyResOps 不应被描述为：

- 生产级水文预报系统；
- 任意水库的完整率定水动力模型；
- 替代水库调度管理权限的系统；
- 不经工具验证即可保证 LLM 决策安全的系统。

## License

MIT
