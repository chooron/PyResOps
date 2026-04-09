"""Simulation engine for reservoir operation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..domain.forecast import ForecastBundle
from ..domain.module import OperationModule
from ..domain.policy import PolicyBundle
from ..domain.program import DispatchProgram, SwitchCondition
from ..domain.reservoir import ReservoirSpec, ReservoirState
from ..domain.result import SimulationResult, StateSnapshot
from .hydraulics import HydraulicsCalculator
from .orchestrator import DecisionOrchestrator


class SimulationEngine:
    """仿真引擎 (Simulation Engine)."""

    def __init__(self, spec: ReservoirSpec):
        """初始化仿真引擎."""
        self.spec = spec
        self.hydraulics = HydraulicsCalculator(spec)

    def _evaluate_switch_condition(
        self,
        condition: SwitchCondition,
        state: ReservoirState,
        inflow: float,
    ) -> bool:
        """评估单个切换条件是否满足."""
        ctype = condition.condition_type
        params = condition.parameters

        if ctype == "level_threshold":
            # 水位阈值切换: level_above / level_below
            threshold = params.get("threshold", 0.0)
            direction = params.get("direction", "above")
            if direction == "above":
                return state.level >= threshold
            else:
                return state.level <= threshold

        elif ctype == "inflow_threshold":
            # 入流阈值切换
            threshold = params.get("threshold", 0.0)
            direction = params.get("direction", "above")
            if direction == "above":
                return inflow >= threshold
            else:
                return inflow <= threshold

        elif ctype == "time_based":
            # 时间触发切换
            trigger_time_str = params.get("trigger_time")
            if trigger_time_str:
                trigger_time = datetime.fromisoformat(trigger_time_str)
                return state.timestamp >= trigger_time

        elif ctype == "storage_threshold":
            # 库容阈值切换
            threshold = params.get("threshold", 0.0)
            direction = params.get("direction", "above")
            if direction == "above":
                return state.storage >= threshold
            else:
                return state.storage <= threshold

        return False

    def _resolve_active_module(
        self,
        current_module_type: str,
        state: ReservoirState,
        inflow: float,
        switch_conditions: list[SwitchCondition],
    ) -> str:
        """根据切换条件决定当前激活模块."""
        for condition in switch_conditions:
            if condition.from_module != current_module_type:
                continue
            if self._evaluate_switch_condition(condition, state, inflow):
                return condition.to_module
        return current_module_type

    def simulate(
        self,
        program: DispatchProgram,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        modules: dict[str, OperationModule],
        policy_bundle: PolicyBundle | None = None,
        orchestrator: DecisionOrchestrator | None = None,
    ) -> SimulationResult:
        """
        执行调度方案仿真.

        Args:
            program: 调度方案
            initial_state: 初始状态
            forecast: 预报数据
            modules: 操作模块字典 {module_type: module_instance}

        Returns:
            仿真结果
        """
        # 准备预报数据
        inflow_series = forecast.get_series("inflow")
        if not inflow_series:
            raise ValueError("Forecast must contain 'inflow' series")

        # 构建时间-入流映射
        inflow_map = dict(zip(inflow_series.timestamps, inflow_series.values))

        # 初始化仿真
        current_state = initial_state
        snapshots: list[StateSnapshot] = []
        time_step = program.time_horizon.time_step

        # 确定初始激活模块
        current_module_type = (
            program.module_sequence[0].module_type if program.module_sequence else None
        )

        # 时间循环
        current_time = program.time_horizon.start
        end_time = program.time_horizon.end
        step_index = 0
        if policy_bundle and orchestrator:
            orchestrator.reset()

        while current_time <= end_time:
            step_time = current_time
            step_state = current_state.copy_with_update(timestamp=step_time)

            # 获取入流预报
            inflow = inflow_map.get(step_time, step_state.inflow)

            # 评估切换条件，决定当前激活模块
            if program.switch_conditions and current_module_type:
                current_module_type = self._resolve_active_module(
                    current_module_type, step_state, inflow, program.switch_conditions
                )

            # 计算出库流量
            if current_module_type and current_module_type in modules:
                module = modules[current_module_type]
                outflow = float(module.compute_outflow(step_state, self.spec, inflow))
            else:
                # 默认: 入流等于出流
                outflow = float(inflow)

            decision_metadata: dict[str, Any] = {}
            if policy_bundle and orchestrator:
                decision = orchestrator.decide(
                    timestamp=step_time,
                    step_index=step_index,
                    state_payload=step_state.model_dump(mode="python"),
                    inflow=float(inflow),
                    baseline_outflow=float(outflow),
                    active_module=current_module_type,
                    policy_bundle=policy_bundle,
                    forecast_payload={"inflow": float(inflow)},
                    history_payload={
                        "previous_outflow": float(current_state.outflow),
                    },
                )
                outflow = float(decision.outflow)
                decision_metadata = {
                    "rule_hits": list(decision.rule_hits),
                    "actions": [action.model_dump(mode="json") for action in decision.actions],
                    "adjustments": list(decision.adjustments),
                    "violations": [violation.to_legacy_dict() for violation in decision.violations],
                    "fallback_used": decision.fallback_used,
                }

            # 泄流能力约束校核
            _, adjusted_outflow = self.hydraulics.validate_outflow(step_state.level, outflow)
            if adjusted_outflow != outflow:
                decision_metadata.setdefault("adjustments", []).append(
                    {
                        "source": "hydraulics",
                        "type": "discharge_capacity_clamp",
                        "before": outflow,
                        "after": adjusted_outflow,
                    }
                )
            outflow = float(adjusted_outflow)

            # 水量平衡推进
            next_state = self.hydraulics.water_balance_step(step_state, inflow, outflow, time_step)
            next_state = next_state.copy_with_update(active_module_id=current_module_type)

            # 记录快照
            snapshots.append(
                StateSnapshot(
                    timestamp=step_time,
                    level=step_state.level,
                    storage=step_state.storage,
                    inflow=inflow,
                    outflow=outflow,
                    active_module=current_module_type,
                    metadata=decision_metadata,
                )
            )

            # 推进到下一时刻
            current_state = next_state
            current_time += timedelta(seconds=time_step)
            step_index += 1

        # 计算统计量
        levels = [s.level for s in snapshots]
        outflows = [s.outflow for s in snapshots]

        metadata: dict[str, Any] = {}
        if policy_bundle and orchestrator:
            metadata["decision_trace"] = [
                item.model_dump(mode="json") for item in orchestrator.state.trace
            ]
            metadata["policy_global_violations"] = [
                violation.to_legacy_dict()
                for violation in orchestrator.global_violations(
                    simulation_result=SimulationResult(
                        program_id=program.id,
                        start_time=program.time_horizon.start,
                        end_time=program.time_horizon.end,
                        snapshots=snapshots,
                        max_level=max(levels),
                        min_level=min(levels),
                        avg_outflow=sum(outflows) / len(outflows) if outflows else 0.0,
                    ),
                    policy_bundle=policy_bundle,
                )
            ]

        return SimulationResult(
            program_id=program.id,
            start_time=program.time_horizon.start,
            end_time=program.time_horizon.end,
            snapshots=snapshots,
            max_level=max(levels),
            min_level=min(levels),
            avg_outflow=sum(outflows) / len(outflows) if outflows else 0.0,
            metadata=metadata,
        )
