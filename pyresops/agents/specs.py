from __future__ import annotations


def build_tankan_spec(flood_limit_level: float = 156.5):
    """Build Tankan reservoir spec for agent-side simulation/evaluation tools."""
    from pyresops.domain.reservoir import (
        DischargeCapacity,
        LevelStorageCurve,
        ReservoirSpec,
    )

    levels = [120.0, 130.0, 140.0, 150.0, 156.5, 160.0, 161.5, 165.87, 169.15]
    storages = [13.94, 18.14, 23.05, 28.72, 32.51, 35.20, 36.17, 39.37, 41.90]
    d_levels = [148.0, 150.0, 155.0, 160.0, 161.5, 165.87]
    d_discharges = [0.0, 361.0, 2456.0, 5861.0, 6649.0, 11085.0]
    return ReservoirSpec(
        id="tankan_2025",
        name="滩坑水电站",
        dead_level=120.0,
        normal_level=160.0,
        flood_limit_level=flood_limit_level,
        design_flood_level=165.87,
        check_flood_level=169.15,
        total_capacity=41.90,
        flood_capacity=3.50,
        level_storage_curve=LevelStorageCurve(levels=levels, storages=storages),
        discharge_capacity=DischargeCapacity(levels=d_levels, max_discharges=d_discharges),
    )
