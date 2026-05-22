"""Muskingum downstream routing check for Stage 1 baseline."""

from __future__ import annotations


class MuskingumDownstreamCheck:
    """Route reservoir release to Hecheng via Muskingum method and check the 14000 m3/s limit.

    Parameters from 控制运用计划:
      K = 5.0 h, x = 0.2, Δt = 3.0 h
    Courant condition: 2Kx ≤ Δt ≤ 2K(1-x) → 2.0 ≤ 3.0 ≤ 8.0 ✓
    """

    def __init__(
        self,
        K: float = 5.0,
        x: float = 0.2,
        dt: float = 3.0,
        safety: float = 14000.0,
    ) -> None:
        self.K = K
        self.x = x
        self.dt = dt
        self.safety = safety
        # Muskingum coefficients
        denom = 2.0 * K * (1.0 - x) + dt
        self.c0 = (dt - 2.0 * K * x) / denom
        self.c1 = (dt + 2.0 * K * x) / denom
        self.c2 = (2.0 * K * (1.0 - x) - dt) / denom

    def route(self, release_series: list[float]) -> list[float]:
        """Return routed flow series at Hecheng (same length as input)."""
        if not release_series:
            return []
        routed: list[float] = [release_series[0]]
        for i in range(1, len(release_series)):
            q_out = (
                self.c0 * release_series[i]
                + self.c1 * release_series[i - 1]
                + self.c2 * routed[i - 1]
            )
            routed.append(max(0.0, q_out))
        return routed

    def check_violation(self, release_series: list[float]) -> tuple[bool, float]:
        """Return (violated, max_routed_flow).

        violated is True if any routed step exceeds self.safety.
        """
        routed = self.route(release_series)
        max_flow = max(routed) if routed else 0.0
        return max_flow > self.safety, max_flow
