"""Simulation and evaluation result objects."""

from datetime import datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field


class StateSnapshot(BaseModel):
    """状态快照 (State Snapshot)."""

    timestamp: datetime
    level: float
    storage: float
    inflow: float
    outflow: float
    active_module: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepScore(BaseModel):
    """单步评分 (Step Score)."""

    step_index: int = Field(description="步序号")
    timestamp: datetime = Field(description="时刻")
    risk_score: float = Field(default=100.0, description="单步风险分 (0-100)")
    constraint_score: float = Field(default=100.0, description="过程约束分 (0-100)")
    benefit_score: float = Field(default=100.0, description="阶段性收益分 (0-100)")
    violations: list[dict[str, Any]] = Field(default_factory=list, description="该步违反记录")


class SimulationResult(BaseModel):
    """仿真结果 (Simulation Result)."""

    program_id: str = Field(description="调度方案ID")
    start_time: datetime = Field(description="仿真开始时间")
    end_time: datetime = Field(description="仿真结束时间")

    # 状态轨迹 (State Trajectory)
    snapshots: list[StateSnapshot] = Field(description="状态快照序列")

    # 统计信息 (Statistics)
    max_level: float = Field(description="最高水位 (m)")
    min_level: float = Field(description="最低水位 (m)")
    avg_outflow: float = Field(description="平均出库流量 (m³/s)")

    # 元数据 (Metadata)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """转换为 Pandas DataFrame."""
        data = [
            {
                "timestamp": s.timestamp,
                "level": s.level,
                "storage": s.storage,
                "inflow": s.inflow,
                "outflow": s.outflow,
                "active_module": s.active_module,
            }
            for s in self.snapshots
        ]
        return pd.DataFrame(data)


class EvaluationResult(BaseModel):
    """评估结果 (Evaluation Result)."""

    program_id: str = Field(description="调度方案ID")
    simulation_result_id: str = Field(description="仿真结果ID")

    # 评估指标 (Evaluation Metrics)
    flood_control_score: float = Field(default=0.0, description="防洪效果评分")
    water_supply_score: float = Field(default=0.0, description="供水效果评分")
    power_generation_score: float = Field(default=0.0, description="发电效果评分")
    ecological_score: float = Field(default=0.0, description="生态效果评分")

    # 约束违反情况 (Constraint Violations)
    constraint_violations: list[dict[str, Any]] = Field(
        default_factory=list, description="约束违反记录"
    )

    # 综合评分 (Overall Score)
    overall_score: float = Field(default=0.0, description="综合评分")

    # 逐步评分 (Step-by-Step Scores)
    step_scores: list[StepScore] = Field(default_factory=list, description="逐步评分序列")

    # 元数据 (Metadata)
    metadata: dict[str, Any] = Field(default_factory=dict)
    additional_scores: dict[str, float] = Field(default_factory=dict, description="扩展指标")

    def to_dataframe(self) -> pd.DataFrame:
        """将逐步评分转换为 DataFrame."""
        if not self.step_scores:
            return pd.DataFrame()
        data = [
            {
                "step_index": s.step_index,
                "timestamp": s.timestamp,
                "risk_score": s.risk_score,
                "constraint_score": s.constraint_score,
                "benefit_score": s.benefit_score,
                "violation_count": len(s.violations),
            }
            for s in self.step_scores
        ]
        return pd.DataFrame(data)
