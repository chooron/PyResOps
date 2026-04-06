"""Snapshot management tools."""

from typing import Any

from ..services import SnapshotService


def setup_snapshot_tools(mcp_server: Any, snapshot_service: SnapshotService) -> None:
    """Setup snapshot-related MCP tools."""

    @mcp_server.tool()
    def get_reservoir_snapshot(reservoir_id: str) -> dict[str, Any]:
        """
        获取水库当前快照.

        Args:
            reservoir_id: 水库唯一标识

        Returns:
            水库状态快照
        """
        snapshot = snapshot_service.get_snapshot(reservoir_id)

        if not snapshot:
            return {"error": f"Snapshot not found for reservoir: {reservoir_id}"}

        return {
            "reservoir_id": reservoir_id,
            "timestamp": snapshot.timestamp.isoformat(),
            "level": snapshot.level,
            "storage": snapshot.storage,
            "inflow": snapshot.inflow,
            "outflow": snapshot.outflow,
            "active_module": snapshot.active_module_id,
        }
