"""Dynamic checkpoint computation for Stage 1 baseline."""

from __future__ import annotations


def compute_dynamic_checkpoints(
    inflow_series: list[float],
    time_step_hours: int = 3,
) -> list[int]:
    """Return list of time-step indices for dynamic checkpoints.

    Strategy (adaptive, not fixed offsets):
      T0 = 0 (event start)
      T1 = 25% of duration
      T2 = peak inflow index
      T3 = peak + 2 steps (6h post-peak)
      T4 = 75% of duration
    Max 5 stages. Duplicates and out-of-bounds indices are removed.
    """
    n = len(inflow_series)
    if n == 0:
        return []

    peak_idx = int(max(range(n), key=lambda i: inflow_series[i]))

    candidates = [
        0,
        max(0, n // 4),
        peak_idx,
        min(n - 1, peak_idx + 2),
        min(n - 1, 3 * n // 4),
    ]

    seen: set[int] = set()
    result: list[int] = []
    for idx in candidates:
        if idx not in seen and 0 <= idx < n:
            seen.add(idx)
            result.append(idx)

    return result
