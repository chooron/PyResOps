# 水库调度MCP实验框架

## 研究目标

本实验框架旨在论证：
1. **MCP工具的调度能力**：大模型通过MCP工具调用能否胜任复杂的水库调度任务
2. **相较人工调度的优势**：在准确性、效率、一致性方面的量化对比
3. **消融实验**：MCP各组件对整体性能的贡献度

## 实验设计

### 基线对比（RQ1: MCP vs 传统方法）

| 方法 | 描述 |
|------|------|
| 人工调度基线 | 依据《水库控制运用计划》人工规则 |
| 纯LLM调度 | 无MCP工具，仅依赖模型内部知识 |
| MCP增强调度 | 本文提出方法 |
| 最优化求解器 | 数学规划上界 |

### 消融实验（RQ2: 各组件贡献）

- 无工具调用（plain LLM）
- 仅数据查询工具
- 仅规则验证工具
- 完整MCP工具集

### 泛化性测试（RQ3: 跨场景鲁棒性）

- 场景S01: 正常蓄水期
- 场景S02: 防洪调度
- 场景S03: 生态流量保障
- 场景S04: 干旱供水调度
- 场景S05: 极端水文事件

## 评估指标

### 效率指标
- 任务完成时间（秒）
- 工具调用次数
- API调用成本

### 质量指标
- 调度决策准确率（对比最优解）
- 规则遵从率（安全约束满足率）
- 目标函数值（综合效益）

### 鲁棒性指标
- 跨场景性能标准差
- 异常输入处理率
- 决策一致性（重复运行）

## 统计分析

- 使用 Wilcoxon 符号秩检验（非参数）
- 效应量计算（Cohen's d）
- 95% 置信区间
- 多重比较校正（Bonferroni）

## 运行实验

```bash
# 安装依赖
pip install scipy numpy pandas matplotlib seaborn

# 运行完整实验套件
python experiments/paper_experiment_runner.py

# 单独运行各模块
python experiments/run_experiments.py          # 基础对比
python experiments/ablation_study.py           # 消融实验
python experiments/statistical_analysis.py     # 统计分析
python experiments/visualization.py            # 生成图表
```

## 结果目录

```
experiments/results/
├── baseline_comparison.json      # 方法对比原始数据
├── ablation_results.json         # 消融实验结果
├── statistical_report.json       # 统计检验报告
├── figures/                      # 论文图表
│   ├── fig1_method_comparison.pdf
│   ├── fig2_ablation_heatmap.pdf
│   ├── fig3_scenario_radar.pdf
│   └── fig4_convergence.pdf
└── tables/                       # LaTeX表格
    ├── table1_main_results.tex
    ├── table2_ablation.tex
    └── table3_statistics.tex
```

## 论文对应章节

| 实验 | 论文章节 |
|------|---------|
| 基线对比 | Section 4.2 Main Results |
| 消融实验 | Section 4.3 Ablation Study |
| 统计显著性 | Section 4.4 Statistical Analysis |
| 可视化 | Section 5 Discussion |
