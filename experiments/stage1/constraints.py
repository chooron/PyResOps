"""Season-aware Tankeng (滩坑) constraint builder for Stage 1 baseline."""

from __future__ import annotations

from datetime import date


# Season flood limits (m) from 控制运用计划
_MEIXUN_LIMIT = 160.0   # 梅汛期 Apr 15 – Jun 30
_TAIXUN_LIMIT = 156.5   # 台汛期 Jul 16 – Oct 15
_TRANSITION_START_LIMIT = 160.0  # Jul 1 start
_TRANSITION_END_LIMIT = 156.5   # Jul 15 end
_NON_FLOOD_LIMIT = 160.0

# Hard ceiling before full-open spillway
ABSOLUTE_LEVEL_CEILING = 161.5

# Downstream safety limit at Hecheng (鹤城)
DOWNSTREAM_LIMIT_M3S = 14000.0

# Turbine capacity (soft preference, not a hard constraint)
TURBINE_CAPACITY_M3S = 627.0


def get_flood_limit(event_month: int, event_day: int = 1) -> float:
    """Return the season-dependent flood limit level (m) for Tankeng."""
    if event_month == 4 and event_day >= 15:
        return _MEIXUN_LIMIT
    if event_month in (5, 6):
        return _MEIXUN_LIMIT
    if event_month == 7:
        if event_day <= 15:
            # Linear transition Jul 1–15: 160.0 → 156.5
            frac = (event_day - 1) / 14.0
            return round(_TRANSITION_START_LIMIT - frac * (_TRANSITION_START_LIMIT - _TRANSITION_END_LIMIT), 3)
        return _TAIXUN_LIMIT
    if event_month in (8, 9, 10) and event_day <= 15:
        return _TAIXUN_LIMIT
    return _NON_FLOOD_LIMIT


def get_season_name(event_month: int, event_day: int = 1) -> str:
    """Return a human-readable season label."""
    if event_month == 4 and event_day >= 15:
        return "梅汛期"
    if event_month in (5, 6):
        return "梅汛期"
    if event_month == 7 and event_day <= 15:
        return "过渡期"
    if event_month == 7 or (event_month in (8, 9, 10) and event_day <= 15):
        return "台汛期"
    return "非汛期"


def build_tankan_constraints(event_month: int, event_day: int = 1) -> dict:
    """Return constraint dict for OptimizationService.optimize_release_plan().

    Keys match what _resolve_policy_bundle() recognises:
      - level_max  → LevelMaxConstraint
      - downstream_flow_limit → DownstreamFlowLimitConstraint
    """
    flood_limit = get_flood_limit(event_month, event_day)
    return {
        "level_max": flood_limit,
        "downstream_flow_limit": DOWNSTREAM_LIMIT_M3S,
    }


def build_tankan_task_constraints(flood_limit: float) -> dict:
    """Return task_constraints for terminal-level soft target.

    Terminal level should return to flood_limit ± 0.5 m.
    """
    return {
        "target_level": flood_limit,
        "target_tolerance": 0.5,
    }
