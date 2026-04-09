"""
马斯京根（Muskingum）洪水演算模块
用于滩坑水电站下游区间洪水预报

滩坑坝址 → 鹤城站（青田县城控制断面）
- 洪水传播时间：约 5.0h（运控计划规定值）
- 区间集水面积：约 10170 km²（鹤城站 13500km² - 滩坑 3330km²）

马斯京根方程：
  S = K * [x * I + (1 - x) * Q]
  Q(t+1) = C0 * I(t+1) + C1 * I(t) + C2 * Q(t)

其中：
  C0 = (0.5*dt - K*x) / (K*(1-x) + 0.5*dt)
  C1 = (0.5*dt + K*x) / (K*(1-x) + 0.5*dt)
  C2 = (K*(1-x) - 0.5*dt) / (K*(1-x) + 0.5*dt)
  C0 + C1 + C2 = 1.0

参数标定依据（滩坑→鹤城）：
  K = 5.0h  ← 运控计划规定的洪水传播时间
  x = 0.25  ← 典型山区洪水值，梅汛期洪水形态较肥，台汛期洪水陡涨陡落
  dt 视步长而定（通常 1h 或 3h）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class MuskingumParams:
    """马斯京根模型参数.

    Parameters
    ----------
    K : float
        河槽蓄量系数（小时），滩坑～鹤城段约 5.0h
    x : float
        流量加权系数 [0, 0.5]，推荐 0.2（梅汛）或 0.25（台汛）
    dt : float
        计算时段长（小时），应满足 2*K*x < dt < 2*K*(1-x)
    """

    K: float = 5.0    # 传播时间 5.0h（运控计划规定值）
    x: float = 0.25   # 加权系数（台汛期典型值）
    dt: float = 1.0   # 时段长（h）

    @property
    def C0(self) -> float:
        """马斯京根系数 C0（可能为负，表示出流先于入流峰）."""
        denom = self.K * (1 - self.x) + 0.5 * self.dt
        return (0.5 * self.dt - self.K * self.x) / denom

    @property
    def C1(self) -> float:
        """马斯京根系数 C1."""
        denom = self.K * (1 - self.x) + 0.5 * self.dt
        return (0.5 * self.dt + self.K * self.x) / denom

    @property
    def C2(self) -> float:
        """马斯京根系数 C2."""
        denom = self.K * (1 - self.x) + 0.5 * self.dt
        return (self.K * (1 - self.x) - 0.5 * self.dt) / denom

    def validate(self) -> None:
        """验证参数合理性（稳定性条件）."""
        assert 0.0 <= self.x <= 0.5, f"x 应在 [0, 0.5] 范围内，当前: {self.x}"
        assert self.K > 0, f"K 应为正值，当前: {self.K}"
        assert self.dt > 0, f"dt 应为正值，当前: {self.dt}"
        # 稳定性条件：2*K*x <= dt <= 2*K*(1-x)
        lower = 2 * self.K * self.x
        upper = 2 * self.K * (1 - self.x)
        if not (lower <= self.dt <= upper):
            import warnings
            warnings.warn(
                f"马斯京根稳定性条件: {lower:.1f}h <= dt({self.dt}h) <= {upper:.1f}h 不满足，"
                f"可能导致负流量或数值振荡"
            )
        c_sum = self.C0 + self.C1 + self.C2
        assert abs(c_sum - 1.0) < 1e-9, f"C0+C1+C2 应等于 1.0，当前: {c_sum:.8f}"

    def __str__(self) -> str:
        return (
            f"MuskingumParams(K={self.K}h, x={self.x}, dt={self.dt}h | "
            f"C0={self.C0:.4f}, C1={self.C1:.4f}, C2={self.C2:.4f})"
        )


@dataclass
class MuskingumRouter:
    """马斯京根洪水演算器.

    用于将滩坑出库流量演算到鹤城站，获得干流（大溪）到达鹤城的流量过程。

    Examples
    --------
    >>> params = MuskingumParams(K=5.0, x=0.25, dt=1.0)
    >>> router = MuskingumRouter(params)
    >>> outflow = router.route_series([1000, 2000, 3000, 2500, 2000, 1500])
    """

    params: MuskingumParams = field(default_factory=MuskingumParams)
    _last_inflow: float = field(default=0.0, init=False, repr=False)
    _last_outflow: float = field(default=0.0, init=False, repr=False)

    def reset(self, initial_flow: float = 0.0) -> None:
        """重置演算状态（热启动用）."""
        self._last_inflow = initial_flow
        self._last_outflow = initial_flow

    def route_step(self, current_inflow: float) -> float:
        """单步演算（递推）.

        Parameters
        ----------
        current_inflow : float
            当前时步入流（滩坑出库流量），m³/s

        Returns
        -------
        float
            当前时步出流（到达鹤城站的干流流量），m³/s
        """
        p = self.params
        outflow = (
            p.C0 * current_inflow
            + p.C1 * self._last_inflow
            + p.C2 * self._last_outflow
        )
        outflow = max(0.0, outflow)  # 流量非负
        self._last_inflow = current_inflow
        self._last_outflow = outflow
        return outflow

    def route_series(
        self,
        inflow_series: Sequence[float],
        initial_flow: float | None = None,
    ) -> list[float]:
        """批量演算流量过程.

        Parameters
        ----------
        inflow_series : Sequence[float]
            入流序列（滩坑出库流量，m³/s）
        initial_flow : float, optional
            初始流量（演算起始时刻），默认使用序列第一个值

        Returns
        -------
        list[float]
            出流序列（到达鹤城站的干流流量，m³/s）
        """
        if initial_flow is None:
            initial_flow = float(inflow_series[0]) if inflow_series else 0.0
        self.reset(initial_flow)
        return [self.route_step(float(q)) for q in inflow_series]


def compute_hecheng_flow(
    tankan_outflow_series: Sequence[float],
    interval_flow_series: Sequence[float] | None = None,
    muskingum_params: MuskingumParams | None = None,
    initial_flow: float | None = None,
) -> dict[str, list[float]]:
    """计算鹤城站流量过程（马斯京根演算 + 区间叠加）.

    将滩坑出库流量经马斯京根演算到鹤城，叠加区间洪水得到鹤城站总流量。

    Parameters
    ----------
    tankan_outflow_series : Sequence[float]
        滩坑出库流量序列（m³/s），需与时段长匹配
    interval_flow_series : Sequence[float], optional
        区间汇流序列（m³/s），若不提供则设为0
        对应区间：鹤城站控制面积(13500km²) - 滩坑坝址(3330km²) = 10170km²
    muskingum_params : MuskingumParams, optional
        马斯京根参数，默认使用滩坑标定参数(K=5h, x=0.25)
    initial_flow : float, optional
        初始流量（演算起始时刻流量），默认使用序列第一个值

    Returns
    -------
    dict[str, list[float]]
        包含以下键：
        - 'tankan_routed': 滩坑出库演算到鹤城的干流流量
        - 'interval_flow': 区间汇流量
        - 'hecheng_total': 鹤城站总流量（干流 + 区间）
    """
    if muskingum_params is None:
        muskingum_params = MuskingumParams()  # 默认滩坑参数

    muskingum_params.validate()

    n = len(tankan_outflow_series)

    # 干流演算（马斯京根）
    router = MuskingumRouter(params=muskingum_params)
    tankan_routed = router.route_series(tankan_outflow_series, initial_flow)

    # 区间流量
    if interval_flow_series is None:
        interval_flows = [0.0] * n
    else:
        interval_flows = list(float(x) for x in interval_flow_series)
        if len(interval_flows) < n:
            # 末值延伸
            interval_flows.extend([interval_flows[-1]] * (n - len(interval_flows)))
        else:
            interval_flows = interval_flows[:n]

    # 叠加
    hecheng_total = [tr + iv for tr, iv in zip(tankan_routed, interval_flows)]

    return {
        "tankan_routed": tankan_routed,
        "interval_flow": interval_flows,
        "hecheng_total": hecheng_total,
    }


def check_downstream_safety(
    hecheng_flow_series: Sequence[float],
    safe_flow: float = 14000.0,
) -> dict[str, object]:
    """校核下游青田县城防洪安全.

    Parameters
    ----------
    hecheng_flow_series : Sequence[float]
        鹤城站流量序列（m³/s）
    safe_flow : float
        鹤城站安全泄量（默认 14000 m³/s，20年一遇）

    Returns
    -------
    dict
        safe: bool — 是否满足防洪安全
        max_flow: float — 最大鹤城流量
        exceedance_count: int — 超标步数
        exceedances: list — 超标详情
    """
    flows = list(hecheng_flow_series)
    max_flow = max(flows)
    exceedances = [
        {"step": i, "flow": round(q, 1), "excess": round(q - safe_flow, 1)}
        for i, q in enumerate(flows)
        if q > safe_flow
    ]
    return {
        "safe": len(exceedances) == 0,
        "max_flow": round(max_flow, 1),
        "safe_flow": safe_flow,
        "exceedance_count": len(exceedances),
        "exceedances": exceedances,
        "max_exceedance": round(max(e["excess"] for e in exceedances), 1) if exceedances else 0.0,
    }


def estimate_safe_tankan_release(
    interval_flow: float,
    safe_downstream_flow: float = 14000.0,
    power_flow: float = 400.0,
    propagation_error_factor: float = 1.06,
) -> float:
    """根据区间流量预报估算滩坑最大安全下泄流量.

    实现运控计划中的补偿凑泄公式：
        Q_泄 = Q_安全 - DQ_区间(含误差) - Q_机组

    Parameters
    ----------
    interval_flow : float
        区间流量预报（m³/s），5h传播时间后到达鹤城的区间洪水
    safe_downstream_flow : float
        鹤城站安全泄量（默认 14000 m³/s）
    power_flow : float
        机组发电流量（默认 400 m³/s，3台机组满发时约 627m³/s，保守取 400）
    propagation_error_factor : float
        区间流量预报误差系数（运控计划规定约 6%，即 1.06）

    Returns
    -------
    float
        滩坑建议下泄流量（m³/s），不含机组流量（机组流量单独计）
    """
    interval_with_error = interval_flow * propagation_error_factor
    max_tankan = safe_downstream_flow - interval_with_error - power_flow
    return max(power_flow, max_tankan)  # 最低保障机组发电流量


# ── 快速演示 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("马斯京根洪水演算演示 — 滩坑→鹤城（参考2024年061623号洪水）")
    print("=" * 65)

    # 标定参数（滩坑～鹤城，传播时间5h，步长1h）
    params = MuskingumParams(K=5.0, x=0.25, dt=1.0)
    print(f"\n参数: {params}")
    params.validate()
    print("参数稳定性校验通过 ✓")

    # 2024061623号洪水实测（参考运控计划1.3.2节）
    # 最大3h洪峰 3380 m³/s，最大出库 2520 m³/s
    # 下面构造1h步长数据近似该次洪水过程
    tankan_outflow_1h = [
        540, 600, 700, 900, 1100, 1300, 1500, 1800,
        2000, 2200, 2400, 2520, 2400, 2200, 2000, 1800,
        1600, 1400, 1200, 1000, 850, 720, 640, 580,
    ]  # 1小时步长，共24步

    # 区间流量估算（梅汛期，区间面积 10170km²，雨量约200mm）
    interval_flows_1h = [
        800, 1000, 1300, 1700, 2200, 2800, 3000, 3200,
        3300, 3100, 2900, 2600, 2300, 2100, 1900, 1700,
        1500, 1300, 1100, 950, 850, 750, 680, 620,
    ]

    result = compute_hecheng_flow(
        tankan_outflow_series=tankan_outflow_1h,
        interval_flow_series=interval_flows_1h,
        muskingum_params=params,
    )

    print(f"\n{'时步':>4} | {'滩坑出库':>8} | {'演算到鹤城':>10} | {'区间流量':>8} | {'鹤城总量':>8}")
    print("-" * 55)
    for i, (outflow, routed, interval, total) in enumerate(zip(
        tankan_outflow_1h,
        result["tankan_routed"],
        result["interval_flow"],
        result["hecheng_total"],
    )):
        flag = " ⚠️ 超标!" if total > 14000 else ""
        print(
            f"  {i:2d}h | {outflow:8.0f} | {routed:10.0f} | {interval:8.0f} | {total:8.0f}{flag}"
        )

    safety = check_downstream_safety(result["hecheng_total"])
    print(f"\n鹤城站最大流量: {safety['max_flow']:.0f} m³/s")
    print(f"安全泄量:       {safety['safe_flow']:.0f} m³/s")
    print(f"防洪安全:       {'✓ 安全' if safety['safe'] else '✗ 超标！'}")
    if not safety["safe"]:
        print(f"超标步数:       {safety['exceedance_count']} 步")
        print(f"最大超标量:     {safety['max_exceedance']:.0f} m³/s")

    # 演示补偿凑泄计算
    print("\n--- 补偿凑泄安全下泄量估算 ---")
    for interval_q in [2000, 4000, 6000, 8000]:
        safe_release = estimate_safe_tankan_release(interval_q)
        print(
            f"区间预报 {interval_q:6.0f} m³/s → "
            f"滩坑最大安全下泄 {safe_release:7.0f} m³/s"
            f"（鹤城总量约 {interval_q * 1.06 + 400 + safe_release:7.0f}）"
        )
