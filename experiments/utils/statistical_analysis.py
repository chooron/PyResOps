"""
统计分析模块 - 用于论文实验结果的统计显著性检验
Statistical Analysis Module for Paper Experiment Results
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class StatTestResult:
    """统计检验结果"""

    test_name: str
    statistic: float
    p_value: float
    significant: bool
    effect_size: float
    confidence_interval: Tuple[float, float]
    interpretation: str


def wilcoxon_signed_rank_test(group_a: List[float], group_b: List[float]) -> StatTestResult:
    """
    Wilcoxon符号秩检验（非参数检验，适用于小样本）
    用于比较MCP-Agent vs 人工基线
    """
    try:
        from scipy import stats

        diffs = [a - b for a, b in zip(group_a, group_b)]
        stat, p_value = stats.wilcoxon(diffs)

        # 计算效应量 r = Z / sqrt(N)
        n = len(diffs)
        z_score = stats.norm.ppf(1 - p_value / 2)
        effect_size = abs(z_score) / np.sqrt(n)

        # Bootstrap置信区间
        ci = bootstrap_ci([a - b for a, b in zip(group_a, group_b)])

        interpretation = _interpret_effect_size(effect_size, "r")

        return StatTestResult(
            test_name="Wilcoxon Signed-Rank Test",
            statistic=stat,
            p_value=p_value,
            significant=p_value < 0.05,
            effect_size=effect_size,
            confidence_interval=ci,
            interpretation=interpretation,
        )
    except ImportError:
        # 如果scipy不可用，使用简化版本
        return _simple_comparison(group_a, group_b)


def _simple_comparison(group_a: List[float], group_b: List[float]) -> StatTestResult:
    """简化比较（不依赖scipy）"""
    diffs = [a - b for a, b in zip(group_a, group_b)]
    mean_diff = np.mean(diffs)
    std_diff = np.std(diffs, ddof=1) if len(diffs) > 1 else 0
    n = len(diffs)

    # 简单t统计量
    t_stat = mean_diff / (std_diff / np.sqrt(n)) if std_diff > 0 else 0

    # 近似p值（简化）
    p_approx = max(0.001, min(0.999, 2 * (1 - abs(t_stat) / 10)))

    ci = bootstrap_ci(diffs)
    effect_size = abs(mean_diff) / std_diff if std_diff > 0 else 0

    return StatTestResult(
        test_name="Simple T-Test (Approximated)",
        statistic=t_stat,
        p_value=p_approx,
        significant=p_approx < 0.05,
        effect_size=effect_size,
        confidence_interval=ci,
        interpretation=_interpret_effect_size(effect_size, "d"),
    )


def bootstrap_ci(
    data: List[float], n_bootstrap: int = 1000, ci: float = 0.95
) -> Tuple[float, float]:
    """Bootstrap置信区间计算"""
    if not data:
        return (0.0, 0.0)

    np.random.seed(42)
    bootstrap_means = []
    n = len(data)

    for _ in range(n_bootstrap):
        sample = np.random.choice(data, size=n, replace=True)
        bootstrap_means.append(np.mean(sample))

    lower = np.percentile(bootstrap_means, (1 - ci) / 2 * 100)
    upper = np.percentile(bootstrap_means, (1 + ci) / 2 * 100)

    return (float(lower), float(upper))


def _interpret_effect_size(effect_size: float, measure: str = "d") -> str:
    """解释效应量大小"""
    if measure == "r":
        if effect_size < 0.1:
            return "可忽略效应 (negligible effect)"
        elif effect_size < 0.3:
            return "小效应 (small effect)"
        elif effect_size < 0.5:
            return "中等效应 (medium effect)"
        else:
            return "大效应 (large effect)"
    else:  # Cohen's d
        if effect_size < 0.2:
            return "可忽略效应 (negligible effect)"
        elif effect_size < 0.5:
            return "小效应 (small effect)"
        elif effect_size < 0.8:
            return "中等效应 (medium effect)"
        else:
            return "大效应 (large effect)"


def load_result_records(results_dir: str = "experiments/results") -> List[Dict]:
    """Load all unified JSON result records and keep experiment-specific fields isolated."""
    records: List[Dict] = []
    for path in sorted(Path(results_dir).glob("**/*.json")):
        if path.name == "summary_tables.csv":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and "experiment_type" in item:
                    records.append(item)
        elif isinstance(payload, dict) and "experiment_type" in payload:
            records.append(payload)
    return records


def load_results_by_experiment_type(
    results_dir: str = "experiments/results",
) -> Dict[str, pd.DataFrame]:
    records = load_result_records(results_dir)
    if not records:
        return {}
    df = pd.DataFrame(records)
    grouped: Dict[str, pd.DataFrame] = {}
    for experiment_type, frame in df.groupby("experiment_type"):
        grouped[str(experiment_type)] = frame.reset_index(drop=True)
    return grouped


def _cohens_d(group_a: List[float], group_b: List[float]) -> float:
    if not group_a or not group_b:
        return 0.0
    mean_diff = float(np.mean(group_a) - np.mean(group_b))
    var_a = float(np.var(group_a, ddof=1)) if len(group_a) > 1 else 0.0
    var_b = float(np.var(group_b, ddof=1)) if len(group_b) > 1 else 0.0
    denominator = max(len(group_a) + len(group_b) - 2, 1)
    pooled = ((len(group_a) - 1) * var_a + (len(group_b) - 1) * var_b) / denominator
    if pooled <= 0:
        return 0.0
    return mean_diff / float(np.sqrt(pooled))


def compute_phase2_statistics(results_dir: str = "experiments/results") -> Dict:
    grouped = load_results_by_experiment_type(results_dir)
    if not grouped:
        return {}

    output: Dict[str, Dict] = {"static": {}, "dynamic": {}, "automated": {}}

    static_llm = grouped.get("static", pd.DataFrame())
    static_human = grouped.get("static_human", pd.DataFrame())
    if not static_llm.empty:
        for scenario_id, llm_frame in static_llm.groupby("scenario_id"):
            llm_scores = llm_frame["overall_score"].astype(float).tolist()
            llm_violations = llm_frame["constraint_violations"].astype(float).tolist()
            item: Dict[str, object] = {
                "overall_score_mean": float(np.mean(llm_scores)),
                "overall_score_std": float(np.std(llm_scores, ddof=1))
                if len(llm_scores) > 1
                else 0.0,
                "constraint_violations_mean": float(np.mean(llm_violations)),
                "constraint_violations_std": float(np.std(llm_violations, ddof=1))
                if len(llm_violations) > 1
                else 0.0,
                "llm_temperature_all_zero": bool(
                    (llm_frame["llm_temperature"].astype(float) == 0.0).all()
                ),
            }
            if not static_human.empty:
                human_frame = static_human[static_human["scenario_id"] == scenario_id]
                n = min(len(llm_frame), len(human_frame))
                if n > 0:
                    human_scores = human_frame["overall_score"].astype(float).tolist()[:n]
                    llm_aligned = llm_scores[:n]
                    wilcoxon_result = wilcoxon_signed_rank_test(llm_aligned, human_scores)
                    item["wilcoxon"] = {
                        "statistic": float(wilcoxon_result.statistic),
                        "p_value": float(wilcoxon_result.p_value),
                        "significant": bool(wilcoxon_result.significant),
                    }
                    item["cohens_d"] = float(_cohens_d(llm_aligned, human_scores))
            output["static"][scenario_id] = item

    dynamic = grouped.get("dynamic", pd.DataFrame())
    if not dynamic.empty:
        for scenario_id, frame in dynamic.groupby("scenario_id"):
            stage_pass = frame["task_completed"].astype(float).tolist()
            per_stage = frame.groupby("stage_id")["constraint_violations"].mean().to_dict()
            output["dynamic"][scenario_id] = {
                "stage_pass_rate_mean": float(np.mean(stage_pass)),
                "stage_pass_rate_std": float(np.std(stage_pass, ddof=1))
                if len(stage_pass) > 1
                else 0.0,
                "constraint_violations_mean_per_stage": {k: float(v) for k, v in per_stage.items()},
                "llm_temperature_all_zero": bool(
                    (frame["llm_temperature"].astype(float) == 0.0).all()
                ),
            }

        s03_t1 = dynamic[(dynamic["scenario_id"] == "S03") & (dynamic["stage_id"] == "T1")]
        if not s03_t1.empty and "partial_credit_score" in s03_t1.columns:
            pcs = s03_t1["partial_credit_score"].astype(float)
            output["dynamic"]["S03_T1_partial_credit"] = {
                "zero_count": int((pcs <= 1e-9).sum()),
                "partial_count": int(((pcs > 1e-9) & (pcs < 1.0 - 1e-9)).sum()),
                "full_count": int((pcs >= 1.0 - 1e-9).sum()),
                "mean": float(pcs.mean()),
                "std": float(pcs.std(ddof=1)) if len(pcs) > 1 else 0.0,
            }

    automated = grouped.get("automated", pd.DataFrame())
    if not automated.empty:
        for scenario_id, frame in automated.groupby("scenario_id"):
            gains = (
                frame["key_dimension_gain"].astype(float).tolist()
                if "key_dimension_gain" in frame.columns
                else []
            )
            switch_rates = (
                frame["switch_rate"].astype(float).tolist()
                if "switch_rate" in frame.columns
                else []
            )
            output["automated"][scenario_id] = {
                "key_dimension_gain_mean": float(np.mean(gains)) if gains else 0.0,
                "key_dimension_gain_std": float(np.std(gains, ddof=1)) if len(gains) > 1 else 0.0,
                "key_dimension_gain_95_ci": bootstrap_ci(gains, n_bootstrap=1000)
                if gains
                else (0.0, 0.0),
                "switch_rate_mean": float(np.mean(switch_rates)) if switch_rates else 0.0,
                "switch_rate_std": float(np.std(switch_rates, ddof=1))
                if len(switch_rates) > 1
                else 0.0,
                "constraint_violations_mean": float(
                    frame["constraint_violations"].astype(float).mean()
                ),
                "constraint_violations_std": float(
                    frame["constraint_violations"].astype(float).std(ddof=1)
                )
                if len(frame) > 1
                else 0.0,
                "strategy_oscillation_count_mean": float(
                    frame["strategy_oscillation_count"].astype(float).mean()
                )
                if "strategy_oscillation_count" in frame.columns
                else 0.0,
                "strategy_oscillation_count_std": float(
                    frame["strategy_oscillation_count"].astype(float).std(ddof=1)
                )
                if "strategy_oscillation_count" in frame.columns and len(frame) > 1
                else 0.0,
                "llm_temperature_all_zero": bool(
                    (frame["llm_temperature"].astype(float) == 0.0).all()
                ),
            }

        if "switch_threshold" in automated.columns:
            threshold_summary = automated.groupby(["scenario_id", "switch_threshold"]).agg(
                key_dimension_gain_mean=("key_dimension_gain", "mean"),
                switch_rate_mean=("switch_rate", "mean"),
                constraint_violations_mean=("constraint_violations", "mean"),
                strategy_oscillation_count_mean=("strategy_oscillation_count", "mean"),
            )
            output["automated"]["threshold_sensitivity"] = {
                f"{sid}_thr_{float(thr):.2f}": {
                    "key_dimension_gain_mean": float(row["key_dimension_gain_mean"]),
                    "switch_rate_mean": float(row["switch_rate_mean"]),
                    "constraint_violations_mean": float(row["constraint_violations_mean"]),
                    "strategy_oscillation_count_mean": float(
                        row["strategy_oscillation_count_mean"]
                    ),
                }
                for (sid, thr), row in threshold_summary.iterrows()
            }

        if "perturbation_seed" in automated.columns:
            perturbation_summary = automated.groupby(["scenario_id", "perturbation_seed"]).agg(
                key_dimension_gain_mean=("key_dimension_gain", "mean"),
                key_dimension_gain_std=("key_dimension_gain", "std"),
            )
            output["automated"]["perturbation_robustness"] = {
                f"{sid}_p{int(ps)}": {
                    "key_dimension_gain_mean": float(row["key_dimension_gain_mean"]),
                    "key_dimension_gain_std": 0.0
                    if pd.isna(row["key_dimension_gain_std"])
                    else float(row["key_dimension_gain_std"]),
                }
                for (sid, ps), row in perturbation_summary.iterrows()
            }

    return output


def compute_paper_statistics(results_dir: str = "experiments/results") -> Dict:
    """
    计算论文所需的完整统计数据

    Returns:
        包含所有统计检验结果的字典
    """
    grouped = load_results_by_experiment_type(results_dir)
    if not grouped:
        return {}

    all_stats = {}

    for experiment_type, frame in grouped.items():
        for scenario_id, scenario_frame in frame.groupby("scenario_id"):
            overall_scores = scenario_frame["overall_score"].astype(float).tolist()
            violations = scenario_frame["constraint_violations"].astype(float).tolist()
            stats_key = f"{scenario_id}_{experiment_type}"
            descriptive = {
                "count": int(len(scenario_frame)),
                "overall_score_mean": float(np.mean(overall_scores)),
                "overall_score_std": float(np.std(overall_scores, ddof=1))
                if len(overall_scores) > 1
                else 0.0,
                "constraint_violations_mean": float(np.mean(violations)),
                "constraint_violations_std": float(np.std(violations, ddof=1))
                if len(violations) > 1
                else 0.0,
            }
            if experiment_type == "dynamic" and "partial_credit_score" in scenario_frame.columns:
                descriptive["partial_credit_mean"] = float(
                    scenario_frame["partial_credit_score"].astype(float).mean()
                )
            if experiment_type == "automated" and "key_dimension_gain" in scenario_frame.columns:
                gains = scenario_frame["key_dimension_gain"].astype(float).tolist()
                descriptive["key_dimension_gain_mean"] = float(np.mean(gains))
                descriptive["key_dimension_gain_std"] = (
                    float(np.std(gains, ddof=1)) if len(gains) > 1 else 0.0
                )
                descriptive["key_dimension_gain_95_ci"] = bootstrap_ci(gains)
            all_stats[stats_key] = {"descriptive": descriptive}

    return all_stats


def generate_latex_table(stats: Dict) -> str:
    """生成LaTeX格式的统计结果表格"""
    latex = """
\\begin{table}[h]
\\centering
\\caption{MCP-Agent与对比方法的统计显著性分析}
\\label{tab:statistical_analysis}
\\begin{tabular}{lccccc}
\\hline
场景 & 方法对比 & 均值差 & p值 & 效应量 & 显著性 \\\\
\\hline
"""

    scenario_map = {
        "S01_枯水期调度": "枯水期调度",
        "S02_洪水期调度": "洪水期调度",
        "S03_蓄水期调度": "蓄水期调度",
        "S04_发电优化调度": "发电优化",
    }

    for scenario_key, scenario_name in scenario_map.items():
        if scenario_key not in stats:
            continue

        s = stats[scenario_key]
        desc = s["descriptive"]
        tests = s["statistical_tests"]

        mcp_vs_human = tests["mcp_vs_human"]
        mean_diff = desc["mcp_agent_mean"] - desc["human_mean"]
        sig_marker = (
            "***"
            if mcp_vs_human["p_value"] < 0.001
            else (
                "**"
                if mcp_vs_human["p_value"] < 0.01
                else ("*" if mcp_vs_human["p_value"] < 0.05 else "ns")
            )
        )

        latex += f"{scenario_name} & MCP vs 人工 & +{mean_diff:.3f} & {mcp_vs_human['p_value']:.4f} & {mcp_vs_human['effect_size']:.3f} & {sig_marker} \\\\\n"

        mcp_vs_no = tests["mcp_vs_no_mcp"]
        mean_diff2 = desc["mcp_agent_mean"] - desc["no_mcp_mean"]
        sig_marker2 = (
            "***"
            if mcp_vs_no["p_value"] < 0.001
            else (
                "**"
                if mcp_vs_no["p_value"] < 0.01
                else ("*" if mcp_vs_no["p_value"] < 0.05 else "ns")
            )
        )

        latex += f" & MCP vs 无MCP & +{mean_diff2:.3f} & {mcp_vs_no['p_value']:.4f} & {mcp_vs_no['effect_size']:.3f} & {sig_marker2} \\\\\n"

    latex += """\\hline
\\multicolumn{6}{l}{* p<0.05, ** p<0.01, *** p<0.001, ns: 不显著} \\\\
\\end{tabular}
\\end{table}
"""
    return latex


def main():
    print("=" * 60)
    print("论文统计分析模块 - MCP水库调度实验")
    print("=" * 60)

    stats = compute_phase2_statistics()

    # 保存统计结果
    output_dir = Path("experiments/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    stats_file = output_dir / "statistical_analysis.json"

    # 转换numpy类型为Python原生类型
    def convert_numpy(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, tuple):
            return list(obj)
        return obj

    import json

    def json_serializable(obj):
        if isinstance(obj, dict):
            return {k: json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [json_serializable(i) for i in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        return obj

    clean_stats = json_serializable(stats)

    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(clean_stats, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 统计分析结果已保存至: {stats_file}")

    # 打印摘要
    print("\n" + "=" * 60)
    print("统计分析摘要")
    print("=" * 60)

    for experiment_type, payload in stats.items():
        print(f"\n[{experiment_type}] {len(payload)} 项")
        for key, item in payload.items():
            print(f"  - {key}: {json.dumps(item, ensure_ascii=False)}")

    return stats


if __name__ == "__main__":
    main()
