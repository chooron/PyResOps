"""Snapshot service for reservoir state management."""

from datetime import datetime

from ..domain.reservoir import ReservoirSpec, ReservoirState


class SnapshotService:
    """快照服务 (Snapshot Service)."""

    def __init__(self):
        """初始化快照服务."""
        self._snapshots: dict[str, ReservoirState] = {}

    def get_snapshot(self, reservoir_id: str) -> ReservoirState | None:
        """获取水库当前快照."""
        return self._snapshots.get(reservoir_id)

    def update_snapshot(self, reservoir_id: str, state: ReservoirState) -> None:
        """更新水库快照."""
        self._snapshots[reservoir_id] = state

    def create_initial_snapshot(
        self, reservoir_id: str, spec: ReservoirSpec, level: float, inflow: float = 0.0
    ) -> ReservoirState:
        """创建初始快照."""
        storage = spec.level_storage_curve.get_storage(level)

        state = ReservoirState(
            timestamp=datetime.now(),
            level=level,
            storage=storage,
            inflow=inflow,
            outflow=inflow,
            metadata={"reservoir_id": reservoir_id},
        )

        self.update_snapshot(reservoir_id, state)
        return state
