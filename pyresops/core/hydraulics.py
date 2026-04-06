"""Hydraulics calculations: water balance, level-storage, discharge capacity."""

from datetime import timedelta

from ..domain.reservoir import ReservoirSpec, ReservoirState


class HydraulicsCalculator:
    """水力学计算器 (Hydraulics Calculator)."""

    def __init__(self, spec: ReservoirSpec):
        """初始化水力学计算器."""
        self.spec = spec

    def compute_storage_from_level(self, level: float) -> float:
        """根据水位计算库容."""
        return self.spec.level_storage_curve.get_storage(level)

    def compute_level_from_storage(self, storage: float) -> float:
        """根据库容计算水位."""
        return self.spec.level_storage_curve.get_level(storage)

    def compute_max_discharge(self, level: float) -> float:
        """根据水位计算最大泄流能力."""
        return self.spec.discharge_capacity.get_max_discharge(level)

    def water_balance_step(
        self, state: ReservoirState, inflow: float, outflow: float, dt: int
    ) -> ReservoirState:
        """
        执行一步水量平衡计算.

        Args:
            state: 当前状态
            inflow: 入库流量 (m³/s)
            outflow: 出库流量 (m³/s)
            dt: 时间步长 (秒)

        Returns:
            下一时刻的状态
        """
        # 水量平衡方程: dS = (Q_in - Q_out) * dt
        # 单位转换: 流量 (m³/s) * 时间 (s) = 体积 (m³) -> 亿m³ 需除以 1e8
        delta_storage = (inflow - outflow) * dt / 1e8  # 亿m³

        new_storage = state.storage + delta_storage
        new_storage = max(
            self.spec.level_storage_curve.storages[0],
            min(new_storage, self.spec.total_capacity),
        )

        new_level = self.compute_level_from_storage(new_storage)
        new_timestamp = state.timestamp + timedelta(seconds=dt)

        return state.copy_with_update(
            timestamp=new_timestamp,
            level=new_level,
            storage=new_storage,
            inflow=inflow,
            outflow=outflow,
        )

    def validate_outflow(self, level: float, outflow: float) -> tuple[bool, float]:
        """
        校核出库流量是否满足泄流能力约束.

        Args:
            level: 当前水位 (m)
            outflow: 期望出库流量 (m³/s)

        Returns:
            (是否合法, 调整后的流量)
        """
        max_discharge = self.compute_max_discharge(level)

        if outflow > max_discharge:
            return False, max_discharge

        if outflow < 0:
            return False, 0.0

        return True, outflow
