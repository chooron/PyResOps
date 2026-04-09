# PyResOps 项目深度探索报告

## 📋 项目概述

**项目名称**: res-ops-mcp  
**核心定位**: 面向单库调度场景的可扩展水库调度内核  
**技术栈**: Python 3.11+, FastMCP, Pydantic v2, NumPy, Pandas, SQLite  
**关键特性**: 支持规则执行、约束校核、决策编排、评估体系插件化

---

## 🏗️ 架构分层

```
pyresops/
├── tools/         # MCP 工具层（12个工具）
├── services/      # 服务编排层（仿真、优化、评估）
├── domain/        # 领域模型层（约束、规则、决策、政策）
├── core/          # 仿真/编排内核（水量平衡、决策编排）
├── constraints/   # 约束 SPI + 内置实现
├── rules/         # 规则 SPI + 内置实现
├── metrics/       # 指标 SPI + 内置实现
├── modules/       # 操作模块层（常流量模块、灵活下泄模块）
├── plugins/       # 插件与扩展注册层
└── storage/       # SQLite 持久化层
```

---

## 🧪 Experiments 目录详解（论文实验设计）

### 1. **paper_experiment_runner.py** - 论文实验核心运行器
- **用途**: 使用 agno 框架 + pyresops 真实库，对标 5 个调度场景
- **5个实验场景**:
  - S01: 台汛期预泄调度（水位超汛限，主动预泄至 156.5m）
  - S02: 梅汛期错峰调度（控制鹤城站流量 ≤14000 m³/s）
  - S03: 极端洪水应急调度（水位超设计洪水位 165.87m）
  - S04: 枯水期发电优化（满足最小下泄流量 50m³/s 的发电优化）
  - S05: 梅台过渡期降水位（从 160m 降至 156.5m）

- **MCP 工具包装** (6个主要工具):
  - `get_reservoir_status`: 获取水库快照状态
  - `simulate_dispatch_program`: 水量平衡仿真
  - `evaluate_dispatch_result`: 方案评估（综合评分、防洪/供水/发电评分）
  - `check_safety_constraints`: 约束合规检查
  - `optimize_release_plan`: 优化下泄计划
  - `query_dispatch_rules`: 查询《2025年度水库控制运用计划》规程

- **核心特点**: 
  - 使用滩坑水电站真实参数（2025年度运控计划）
  - Agent 通过工具调用完成完整分析流程
  - 自动提取出库流量、工具调用次数、决策时间

### 2. **evaluation_metrics.py** - 评估指标模块
- **核心功能**: 使用 pyresops EvaluationService 计算真实评估指标
- **论文8个主要指标**:
  1. 综合评分 (Overall Score)
  2. 防洪评分 (Flood Control Score)
  3. 供水评分 (Water Supply Score)
  4. 发电评分 (Power Generation Score)
  5. 生态评分 (Ecological Score)
  6. 约束违反数 (Constraint Violations)
  7. 决策时间 (Decision Time)
  8. 工具调用次数 (Tool Call Count)

- **对比分析**:
  - 人工调度 vs MCP Agent 调度的性能对标
  - 相对改进计算（百分比）
  - 约束违反变化追踪

### 3. **baseline_human.py** - 人工调度基线
- **用途**: 模拟调度员按照《水库控制运用计划》的手动决策过程
- **决策逻辑**: 基于防洪风险等级的简化规则
  - extreme: 全力泄洪
  - high: 入库×1.05，不超泄洪能力
  - medium: 入库×1.2（预泄加大出库）
  - low: 入库×0.85（蓄水计划）
  - none: 入库×0.9（枯水期发电）

- **仿真评估**: 使用 pyresops 真实引擎执行水量平衡仿真 + 评估

### 4. **mcp_agent_experiment.py** - MCP Agent 实验框架
- **实验场景定义**: 5个复杂度递增的场景
- **评估维度**: 
  - 任务完成率 (weight: 30%)
  - 规程遵守率 (weight: 25%)
  - 工具调用效率 (weight: 20%)
  - 决策质量 (weight: 15%)
  - 错误恢复能力 (weight: 10%)

### 5. **run_experiments.py** - 实验主运行脚本
- **用法**: 支持多个LLM模型配置
  ```bash
  python run_experiments.py --model deepseek      # 使用DeepSeek
  python run_experiments.py --model claude        # 使用Claude
  python run_experiments.py --model qwen          # 使用通义千问
  ```

- **关键功能**:
  - 5个场景的人工调度 vs MCP Agent 调度对比
  - 自动记录响应时间、工具调用次数、评分结果
  - JSON 结果输出到 experiments/results/

### 6. **statistical_analysis.py** - 统计显著性分析
- **功能**: 为论文提供统计支持
- **检验方法**:
  - Wilcoxon符号秩检验（非参数检验）
  - Bootstrap置信区间计算
  - 效应量评估（Cohen's d / Pearson's r）

- **输出**:
  - 统计结果 JSON
  - LaTeX 格式的结果表格

---

## 📊 Scenarios 目录（5个场景验证脚本）

### 关键验证脚本

1. **verify_s01_prerelease.py** - 台汛期预泄验证
   - 验证水位超 156.5m 时预泄规则触发
   - 末水位是否降至 ≤156.5m
   - 防洪评分 > 0.8 验证

2. **verify_s02_flood_control.py** - 梅汛期错峰验证（核心）
   - 包含 **马斯京根区间洪水预报** 演算
   - 验证鹤城站流量控制 ≤ 14000 m³/s
   - 洪峰削减率 ≥ 30% 验证
   - 区间流量预报接入演示

3. **muskingum.py** - 马斯京根洪水演算模块
   - 参数: K=5.0, x=0.25, 时间步 3h
   - 用于滩坑→鹤城流量演算

4. **verify_s03_extreme_flood.py** - 极端洪水应急验证

5. **verify_s04_dry_power.py** - 枯水期发电优化验证

6. **verify_s05_transition.py** - 过渡期降水位验证

---

## 🔧 .omc 目录（Deep Interview 规范文档）

**deep-interview-mcp-paper.md** - 论文实验的深度需求分析
- **模糊度**: 11%（通过验收标准 ✓）
- **访谈轮次**: 12 轮，实体稳定率 100%

### 核心验收标准

#### 集成实验部分
- [ ] 5 个调度场景均完成 LLM-MCP 调度流程演示
- [ ] 每个场景有量化的响应时间数据（秒）
- [ ] 每个场景有量化的工具调用次数数据
- [ ] 与人工调度流程对比的时间/步骤数据

#### 消融实验部分
- [ ] 3 种消融条件:
  - 完整 MCP（全部 12 工具）
  - 部分 MCP（仅核心仿真工具）
  - 无 MCP（纯 LLM 文本推理）
- [ ] 至少 2 个代表性场景（S03 极端洪水 + S01 台汛期预泄）
- [ ] 统计对比（均值、方差或置信区间）

#### 论文论证部分
- [ ] 定量结果：响应时间和调用次数有明确数值
- [ ] 定性分析：LLM 决策轨迹的合理性解释
- [ ] 可重复性说明：LLM 输出随机性处理
- [ ] 框架可扩展性：通过不同场景展示通用性

---

## 📝 config.yml 配置解析

**支持的 LLM 模型配置**:
1. **Claude** (Anthropic)
   - 模型: claude-sonnet-4-6
   - API: 官方直连

2. **DeepSeek** (国内大模型)
   - 模型: deepseek-chat / deepseek-reasoner
   - 兼容 OpenAI API

3. **通义千问** (Qwen)
   - 模型: qwen-plus / qwen-max
   - DashScope 接口

4. **MiniMax** (OpenCode 平台)
   - 模型: MiniMax-Text-01 / MiniMax-M1
   - 兼容 OpenAI API

5. **OpenAI GPT**
   - 模型: gpt-4o / gpt-4o-mini
   - 支持自定义代理地址

**默认配置**: deepseek

---

## 🎯 核心实验设计（两层设计）

### 实验一：集成实验（Integration Experiment）
```
[场景描述] → LLM 接收 → LLM 调用工具链 → 记录 T_total & N_calls → 输出决策报告
```

**测量指标**:
- T_total: 端到端响应时间（秒）
- N_calls: MCP 工具调用总次数
- Q_score: 调度方案综合评分
- N_violations: 约束违反次数

### 实验二：消融实验（Ablation Study）
| 条件 | 工具可用 | 预期 |
|-----|--------|------|
| Full-MCP | 全部 12 工具 | 最优效率 |
| Core-MCP | 仅仿真+评估 | 中等效率 |
| No-MCP | 纯文本推理 | 最低效率 |

---

## 🏆 三大技术创新点

1. **自然语言交互层**: 大模型理解自然语言场景描述，自主决定调用哪些 MCP 工具
2. **工具链集成层**: FastMCP 框架将水文仿真引擎封装为标准化工具接口
3. **可扩展框架层**: 约束/规则/指标的 SPI 架构支持不同水库快速适配

---

## 📚 水库参数（滩坑水电站）

**基本参数** (来自《2025年度水库控制运用计划》):
- 死水位: 120.0 m
- 正常蓄水位: 160.0 m
- 台汛期汛限: 156.5 m
- 梅汛期汛限: 160.0 m
- 设计洪水位: 165.87 m
- 校核洪水位: 169.15 m
- 总库容: 41.90 亿 m³
- 防洪库容: 3.50 亿 m³

**泄洪能力曲线** (6 孔溢洪道全开):
- 160.0m: 5861 m³/s
- 165.87m: 11085 m³/s

---

## ✅ 验收标准与进度

**当前状态**: 框架设计完成，实验脚本完成，ready for execution

**下一步**:
1. 执行完整的 5 场景集成实验
2. 运行消融实验（3 种条件 × 2 场景）
3. 统计分析与显著性检验
4. 论文撰写与提交

