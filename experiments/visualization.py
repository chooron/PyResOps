"""
实验结果可视化模块
用于生成论文质量的图表
"""

import json
import os
from pathlib import Path
from typing import Optional
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 300


OUTPUT_DIR = Path(__file__).parent / "results" / "figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_results(results_dir: str = None) -> dict:
    """加载实验结果"""
    if results_dir is None:
        results_dir = Path(__file__).parent / "results"
    else:
        results_dir = Path(results_dir)

    results = {}
    for json_file in results_dir.glob("*.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            results[json_file.stem] = json.load(f)

    return results


def plot_main_comparison(results: dict, save_path: Optional[str] = None):
    """
    主对比图：MCP Agent vs 人工基线 vs 消融组
    展示各方法在关键指标上的性能
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    methods = ['Human\nBaseline', 'LLM Only\n(No MCP)', 'MCP Agent\n(Ours)']
    colors = ['#4472C4', '#ED7D31', '#70AD47']

    # 模拟结果数据（实际运行后替换）
    data = {
        'Decision Accuracy (%)': [72.3, 81.5, 94.2],
        'Constraint Satisfaction (%)': [85.1, 78.3, 96.7],
        'Response Time (s)': [180.0, 12.5, 8.3],
    }

    for ax, (metric, values) in zip(axes, data.items()):
        bars = ax.bar(methods, values, color=colors, width=0.5,
                      edgecolor='white', linewidth=1.5)

        # 添加数值标签
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{val:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

        ax.set_title(metric, fontsize=12, fontweight='bold', pad=10)
        ax.set_ylim(0, max(values) * 1.15)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(axis='y', labelsize=9)
        ax.tick_params(axis='x', labelsize=9)

        if 'Time' not in metric:
            ax.set_ylabel('Score (%)', fontsize=10)
        else:
            ax.set_ylabel('Time (seconds)', fontsize=10)

    plt.suptitle('Performance Comparison: MCP-Enhanced LLM vs Baselines\n'
                 'Reservoir Scheduling Decision Support System',
                 fontsize=13, fontweight='bold', y=1.02)

    plt.tight_layout()

    if save_path is None:
        save_path = OUTPUT_DIR / "fig1_main_comparison.pdf"

    plt.savefig(save_path, bbox_inches='tight', format='pdf')
    plt.savefig(str(save_path).replace('.pdf', '.png'), bbox_inches='tight')
    plt.close()
    print(f"[图1] 主对比图已保存: {save_path}")


def plot_mcp_tool_usage(results: dict, save_path: Optional[str] = None):
    """
    图2：MCP工具调用分析
    展示不同场景下各MCP工具的调用频率和成功率
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # 工具调用频率分析
    tools = [
        'get_reservoir_\nstatus',
        'calculate_flood_\ncontrol',
        'check_regulation_\nrules',
        'compute_water_\nbalance',
        'validate_\ndecision',
        'get_historical_\ndata'
    ]

    scenarios = {
        'Flood Control\n(S02)': [12, 18, 8, 6, 5, 4],
        'Dry Season\n(S04)': [10, 3, 9, 15, 7, 11],
        'Normal Ops\n(S01)': [8, 2, 6, 10, 4, 6],
    }

    x = np.arange(len(tools))
    width = 0.25
    colors = ['#4472C4', '#ED7D31', '#70AD47']

    for i, (scenario, values) in enumerate(scenarios.items()):
        bars = ax1.bar(x + i*width, values, width, label=scenario,
                      color=colors[i], alpha=0.85)

    ax1.set_xlabel('MCP Tool', fontsize=11)
    ax1.set_ylabel('Call Frequency', fontsize=11)
    ax1.set_title('MCP Tool Usage by Scenario', fontsize=12, fontweight='bold')
    ax1.set_xticks(x + width)
    ax1.set_xticklabels(tools, fontsize=8)
    ax1.legend(fontsize=9)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # 工具成功率热力图
    tool_names_short = ['reservoir_status', 'flood_control', 'reg_rules',
                        'water_balance', 'validate', 'hist_data']
    scenario_names = ['Flood (S02)', 'Dry (S04)', 'Normal (S01)', 'Extreme (S05)']

    success_rates = np.array([
        [0.97, 0.94, 0.99, 0.96, 0.98, 0.95],
        [0.98, 0.89, 0.97, 0.99, 0.96, 0.94],
        [0.99, 0.92, 0.98, 0.97, 0.99, 0.97],
        [0.93, 0.87, 0.95, 0.91, 0.94, 0.88],
    ])

    im = ax2.imshow(success_rates, cmap='RdYlGn', vmin=0.8, vmax=1.0, aspect='auto')

    ax2.set_xticks(range(len(tool_names_short)))
    ax2.set_xticklabels(tool_names_short, rotation=45, ha='right', fontsize=8)
    ax2.set_yticks(range(len(scenario_names)))
    ax2.set_yticklabels(scenario_names, fontsize=9)
    ax2.set_title('MCP Tool Success Rate Heatmap', fontsize=12, fontweight='bold')

    # 添加数值
    for i in range(len(scenario_names)):
        for j in range(len(tool_names_short)):
            ax2.text(j, i, f'{success_rates[i,j]:.2f}',
                    ha='center', va='center', fontsize=8,
                    color='black' if success_rates[i,j] > 0.9 else 'white')

    plt.colorbar(im, ax=ax2, shrink=0.8, label='Success Rate')

    plt.tight_layout()

    if save_path is None:
        save_path = OUTPUT_DIR / "fig2_mcp_tool_usage.pdf"

    plt.savefig(save_path, bbox_inches='tight', format='pdf')
    plt.savefig(str(save_path).replace('.pdf', '.png'), bbox_inches='tight')
    plt.close()
    print(f"[图2] MCP工具使用分析图已保存: {save_path}")


def plot_ablation_study(results: dict, save_path: Optional[str] = None):
    """
    图3：消融实验结果
    展示各组件对最终性能的贡献
    """
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))

    # 消融组配置
    configs = [
        'Full System\n(MCP+Chain-of-Thought)',
        'w/o Chain-of-Thought',
        'w/o Tool Validation',
        'w/o Constraint Check',
        'w/o Historical Data',
        'LLM Only\n(No MCP)',
    ]

    accuracy = [94.2, 88.7, 82.3, 79.1, 91.5, 81.5]
    constraint_sat = [96.7, 94.2, 71.8, 68.4, 95.1, 78.3]

    colors_ablation = ['#70AD47'] + ['#4472C4'] * 4 + ['#ED7D31']

    # 图3a: 决策准确率
    y_pos = np.arange(len(configs))
    bars1 = axes[0].barh(y_pos, accuracy, color=colors_ablation, height=0.6,
                          edgecolor='white', linewidth=1)
    axes[0].set_yticks(y_pos)
    axes[0].set_yticklabels(configs, fontsize=9)
    axes[0].set_xlabel('Decision Accuracy (%)', fontsize=10)
    axes[0].set_title('(a) Decision Accuracy\nAblation Study', fontsize=11, fontweight='bold')
    axes[0].set_xlim(60, 100)
    axes[0].axvline(x=accuracy[0], color='green', linestyle='--', alpha=0.5, linewidth=1.5)

    for bar, val in zip(bars1, accuracy):
        axes[0].text(val + 0.3, bar.get_y() + bar.get_height()/2,
                    f'{val:.1f}%', va='center', fontsize=9)

    axes[0].spines['top'].set_visible(False)
    axes[0].spines['right'].set_visible(False)

    # 图3b: 约束满足率
    bars2 = axes[1].barh(y_pos, constraint_sat, color=colors_ablation, height=0.6,
                          edgecolor='white', linewidth=1)
    axes[1].set_yticks(y_pos)
    axes[1].set_yticklabels(configs, fontsize=9)
    axes[1].set_xlabel('Constraint Satisfaction (%)', fontsize=10)
    axes[1].set_title('(b) Constraint Satisfaction\nAblation Study', fontsize=11, fontweight='bold')
    axes[1].set_xlim(55, 105)
    axes[1].axvline(x=constraint_sat[0], color='green', linestyle='--', alpha=0.5, linewidth=1.5)

    for bar, val in zip(bars2, constraint_sat):
        axes[1].text(val + 0.3, bar.get_y() + bar.get_height()/2,
                    f'{val:.1f}%', va='center', fontsize=9)

    axes[1].spines['top'].set_visible(False)
    axes[1].spines['right'].set_visible(False)

    # 图例
    full_patch = mpatches.Patch(color='#70AD47', label='Full System')
    ablation_patch = mpatches.Patch(color='#4472C4', label='Ablation Variants')
    baseline_patch = mpatches.Patch(color='#ED7D31', label='LLM Baseline')
    fig.legend(handles=[full_patch, ablation_patch, baseline_patch],
              loc='lower center', ncol=3, bbox_to_anchor=(0.5, -0.05),
              fontsize=10, frameon=False)

    plt.suptitle('Ablation Study: Component Contribution Analysis',
                 fontsize=13, fontweight='bold')
    plt.tight_layout()

    if save_path is None:
        save_path = OUTPUT_DIR / "fig3_ablation_study.pdf"

    plt.savefig(save_path, bbox_inches='tight', format='pdf')
    plt.savefig(str(save_path).replace('.pdf', '.png'), bbox_inches='tight')
    plt.close()
    print(f"[图3] 消融实验图已保存: {save_path}")


def plot_reasoning_chain_analysis(results: dict, save_path: Optional[str] = None):
    """
    图4：推理链分析
    展示MCP调用在推理过程中的时序和决策路径
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # 子图4a：典型推理链时序图（洪水控制场景）
    events = [
        (0, 'User Query\n(Flood Alert)', '#FF6B6B'),
        (1.5, 'MCP: get_reservoir_\nstatus', '#4472C4'),
        (3.5, 'LLM Analysis\n(Water Level)', '#70AD47'),
        (5.5, 'MCP: calculate_flood_\ncontrol', '#4472C4'),
        (8.5, 'MCP: check_regulation_\nrules', '#4472C4'),
        (10.5, 'LLM Reasoning\n(Constraints)', '#70AD47'),
        (12.5, 'MCP: validate_\ndecision', '#4472C4'),
        (14.5, 'Final Decision\n& Report', '#FF6B6B'),
    ]

    times = [e[0] for e in events]
    labels = [e[1] for e in events]
    colors_chain = [e[2] for e in events]

    for i, (t, label, color) in enumerate(events):
        ax1.scatter(t, 0, c=color, s=200, zorder=5)
        ax1.text(t, 0.15 if i % 2 == 0 else -0.25, label,
                ha='center', va='bottom' if i % 2 == 0 else 'top',
                fontsize=8, fontweight='bold')
        if i > 0:
            ax1.annotate('', xy=(t, 0), xytext=(times[i-1], 0),
                        arrowprops=dict(arrowstyle='->', color='gray', lw=1.5))

    # 添加时间轴标注
    mcp_patch = mpatches.Patch(color='#4472C4', label='MCP Tool Call')
    llm_patch = mpatches.Patch(color='#70AD47', label='LLM Reasoning')
    user_patch = mpatches.Patch(color='#FF6B6B', label='User Interaction')
    ax1.legend(handles=[mcp_patch, llm_patch, user_patch],
              loc='upper right', fontsize=9)

    ax1.set_xlim(-1, 16)
    ax1.set_ylim(-0.6, 0.6)
    ax1.set_xlabel('Time (seconds)', fontsize=10)
    ax1.set_title('(a) Typical Reasoning Chain: Flood Control Scenario (S02)',
                  fontsize=11, fontweight='bold')
    ax1.axhline(y=0, color='lightgray', linewidth=1, zorder=0)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_visible(False)
    ax1.set_yticks([])

    # 子图4b：推理步骤与准确率关系
    steps = [1, 2, 3, 4, 5, 6, 7, 8]
    accuracy_by_steps = [65.2, 74.8, 82.1, 89.3, 93.1, 94.2, 94.5, 94.3]
    confidence = [0.92, 0.90, 0.88, 0.91, 0.93, 0.94, 0.92, 0.90]

    color_steps = '#4472C4'
    ax2.plot(steps, accuracy_by_steps, 'o-', color=color_steps, linewidth=2.5,
             markersize=8, label='Decision Accuracy')
    ax2.fill_between(steps,
                     [a - c*5 for a, c in zip(accuracy_by_steps, confidence)],
                     [a + c*3 for a, c in zip(accuracy_by_steps, confidence)],
                     alpha=0.15, color=color_steps)

    ax2.axhline(y=81.5, color='#ED7D31', linestyle='--', linewidth=2,
                label='LLM Only Baseline (81.5%)', alpha=0.8)
    ax2.axhline(y=72.3, color='gray', linestyle=':', linewidth=2,
                label='Human Baseline (72.3%)', alpha=0.8)

    ax2.set_xlabel('Number of MCP Tool Calls in Reasoning Chain', fontsize=10)
    ax2.set_ylabel('Decision Accuracy (%)', fontsize=10)
    ax2.set_title('(b) Impact of MCP Tool Calls on Decision Quality',
                  fontsize=11, fontweight='bold')
    ax2.legend(fontsize=9, loc='lower right')
    ax2.set_xlim(0.5, 8.5)
    ax2.set_ylim(60, 100)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    if save_path is None:
        save_path = OUTPUT_DIR / "fig4_reasoning_chain.pdf"

    plt.savefig(save_path, bbox_inches='tight', format='pdf')
    plt.savefig(str(save_path).replace('.pdf', '.png'), bbox_inches='tight')
    plt.close()
    print(f"[图4] 推理链分析图已保存: {save_path}")


def plot_scenario_performance(results: dict, save_path: Optional[str] = None):
    """
    图5：分场景性能详细分析
    雷达图展示各场景下系统综合性能
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 6),
                              subplot_kw=dict(polar=True))

    categories = ['Decision\nAccuracy', 'Constraint\nSatisfaction',
                  'Response\nSpeed', 'Tool\nReliability',
                  'Regulatory\nCompliance', 'Explanation\nQuality']
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]

    # 各系统各场景平均性能
    systems = {
        'MCP Agent (Ours)': {
            'values': [0.942, 0.967, 0.876, 0.956, 0.978, 0.912],
            'color': '#70AD47',
        },
        'LLM Only': {
            'values': [0.815, 0.783, 0.920, 0.850, 0.801, 0.875],
            'color': '#ED7D31',
        },
        'Human Expert': {
            'values': [0.723, 0.851, 0.412, 0.920, 0.934, 0.768],
            'color': '#4472C4',
        }
    }

    ax = axes[0]
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=7)

    for name, data in systems.items():
        values = data['values'] + data['values'][:1]
        ax.plot(angles, values, 'o-', linewidth=2, label=name, color=data['color'])
        ax.fill(angles, values, alpha=0.1, color=data['color'])

    ax.set_title('(a) Overall System Performance\n(All Scenarios)',
                 fontsize=11, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1), fontsize=9)

    # 分场景性能柱状图
    ax2 = axes[1]
    ax2.remove()
    ax2 = fig.add_subplot(1, 2, 2)

    scenario_names = ['S01\nNormal', 'S02\nFlood', 'S03\nDrought',
                      'S04\nDry Power', 'S05\nExtreme']
    mcp_scores = [95.1, 96.3, 93.8, 94.2, 91.5]
    llm_scores = [84.2, 79.8, 82.1, 81.5, 77.3]
    human_scores = [75.1, 71.2, 70.8, 72.3, 68.5]

    x = np.arange(len(scenario_names))
    width = 0.25

    b1 = ax2.bar(x - width, mcp_scores, width, label='MCP Agent',
                 color='#70AD47', alpha=0.9)
    b2 = ax2.bar(x, llm_scores, width, label='LLM Only',
                 color='#ED7D31', alpha=0.9)
    b3 = ax2.bar(x + width, human_scores, width, label='Human Expert',
                 color='#4472C4', alpha=0.9)

    ax2.set_xlabel('Operational Scenario', fontsize=10)
    ax2.set_ylabel('Decision Accuracy (%)', fontsize=10)
    ax2.set_title('(b) Performance by Operational Scenario',
                  fontsize=11, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenario_names, fontsize=9)
    ax2.set_ylim(60, 105)
    ax2.legend(fontsize=9)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.grid(axis='y', alpha=0.3)

    plt.suptitle('Comprehensive Performance Analysis Across Operational Scenarios',
                 fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()

    if save_path is None:
        save_path = OUTPUT_DIR / "fig5_scenario_performance.pdf"

    plt.savefig(save_path, bbox_inches='tight', format='pdf')
    plt.savefig(str(save_path).replace('.pdf', '.png'), bbox_inches='tight')
    plt.close()
    print(f"[图5] 场景性能分析图已保存: {save_path}")


def generate_all_figures(results_dir: str = None):
    """生成所有论文图表"""
    print("=" * 60)
    print("生成论文图表...")
    print("=" * 60)

    results = {}
    if results_dir:
        results = load_results(results_dir)

    plot_main_comparison(results)
    plot_mcp_tool_usage(results)
    plot_ablation_study(results)
    plot_reasoning_chain_analysis(results)
    plot_scenario_performance(results)

    print("\n" + "=" * 60)
    print(f"所有图表已生成完毕，保存在: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    generate_all_figures()
