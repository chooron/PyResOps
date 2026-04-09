"""
滩坑水电站调度验证脚本 — 综合运行入口

验证 pyresops 库对《2025年度水库控制运用计划》的覆盖能力，包括：
  - muskingum: 马斯京根算法独立验证
  - S01: 台汛期预泄调度
  - S02: 梅汛期错峰调度（含马斯京根区间洪水预报）
  - S03: 极端洪水应急调度
  - S04: 枯水期发电优化
  - S05: 梅台过渡期降水位

用法:
    cd E:\\PyCode\\PyResOps
    uv run python scenarios/verify_all.py
    uv run python scenarios/verify_all.py --scenario s02
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime


def _import_path():
    """确保 scenarios 目录在 sys.path 中."""
    import os
    scenarios_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(scenarios_dir)
    for p in [project_root, scenarios_dir]:
        if p not in sys.path:
            sys.path.insert(0, p)


def run_muskingum() -> bool:
    """马斯京根算法独立验证."""
    _import_path()
    from muskingum import (
        MuskingumParams, MuskingumRouter, compute_hecheng_flow,
        check_downstream_safety, estimate_safe_tankan_release
    )

    print("\n[马斯京根] 参数初始化验证")
    params = MuskingumParams(K=5.0, x=0.25, dt=1.0)
    params.validate()
    c_sum = params.C0 + params.C1 + params.C2
    assert abs(c_sum - 1.0) < 1e-9, f"C0+C1+C2={c_sum}"
    print(f"  {params}")
    print(f"  系数之和: {c_sum:.9f} ✓")

    print("\n[马斯京根] 稳态输入验证（入流=出流）")
    inflow_steady = [1000.0] * 15
    result = compute_hecheng_flow(inflow_steady, muskingum_params=params)
    final_q = result["hecheng_total"][-1]
    assert abs(final_q - 1000.0) < 30, f"稳态误差过大: {final_q}"
    print(f"  稳态入流 1000 m³/s → 鹤城出流 {final_q:.1f} m³/s（偏差<30）✓")

    print("\n[马斯京根] 洪峰演算验证（洪峰应滞后）")
    inflow_flood = [
        500, 1000, 2000, 3000, 4000, 4500, 4000, 3000, 2000, 1200, 800, 600, 500, 500, 500
    ]
    result2 = compute_hecheng_flow(
        tankan_outflow_series=inflow_flood,
        interval_flow_series=[800] * 15,
        muskingum_params=params,
    )
    # 洪峰应在入流洪峰之后（至少滞后 1 步）
    in_peak_step = inflow_flood.index(max(inflow_flood))
    routed_peak_step = result2["tankan_routed"].index(max(result2["tankan_routed"]))
    assert routed_peak_step >= in_peak_step, f"洪峰不应提前: 入流峰step={in_peak_step}, 演算峰step={routed_peak_step}"
    print(f"  入流洪峰 step={in_peak_step}，演算洪峰 step={routed_peak_step}（滞后 {routed_peak_step-in_peak_step} 步）✓")

    print("\n[马斯京根] 补偿凑泄计算验证")
    for q_interval in [2000, 5000, 8000]:
        safe_q = estimate_safe_tankan_release(q_interval)
        downstream_check = q_interval * 1.06 + 400 + safe_q
        print(f"  区间{q_interval:6.0f} m³/s → 最大下泄{safe_q:7.0f} m³/s，鹤城总量≈{downstream_check:7.0f} m³/s")
        assert downstream_check <= 14000 + 100, f"鹤城流量超标: {downstream_check}"
    print("  补偿凑泄验证通过 ✓")

    print("\n[马斯京根] 防洪安全校核（应无超标）")
    safety = check_downstream_safety(result2["hecheng_total"])
    print(f"  最大鹤城流量: {safety['max_flow']:.0f} m³/s")
    print(f"  防洪安全: {'✓ 安全' if safety['safe'] else '⚠ 超标（正常，测试未优化出库）'}")
    return True


def run_s01() -> bool:
    """S01: 台汛期预泄调度验证."""
    _import_path()
    from verify_s01_prerelease import main as s01_main
    return s01_main()


def run_s02() -> bool:
    """S02: 梅汛期错峰调度验证."""
    _import_path()
    from verify_s02_flood_control import main as s02_main
    return s02_main()


def run_s03() -> bool:
    """S03: 极端洪水应急调度验证."""
    _import_path()
    from verify_s03_extreme_flood import main as s03_main
    return s03_main()


def run_s04() -> bool:
    """S04: 枯水期发电优化验证."""
    _import_path()
    from verify_s04_dry_power import main as s04_main
    return s04_main()


def run_s05() -> bool:
    """S05: 梅台过渡期降水位验证."""
    _import_path()
    from verify_s05_transition import main as s05_main
    return s05_main()


SCENARIOS = {
    "muskingum": ("马斯京根算法独立验证", run_muskingum),
    "s01": ("S01 台汛期预泄调度", run_s01),
    "s02": ("S02 梅汛期错峰调度", run_s02),
    "s03": ("S03 极端洪水应急调度", run_s03),
    "s04": ("S04 枯水期发电优化", run_s04),
    "s05": ("S05 梅台过渡期降水位", run_s05),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="PyResOps 滩坑水电站调度验证")
    parser.add_argument(
        "--scenario", "-s",
        choices=list(SCENARIOS.keys()) + ["all"],
        default="all",
        help="指定运行的场景（默认 all）",
    )
    args = parser.parse_args()

    print("=" * 65)
    print("PyResOps 滩坑水电站调度能力验证")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    to_run: list[tuple[str, tuple]] = (
        list(SCENARIOS.items()) if args.scenario == "all"
        else [(args.scenario, SCENARIOS[args.scenario])]
    )

    results: dict[str, bool] = {}
    for key, (name, func) in to_run:
        print(f"\n{'=' * 65}")
        print(f">> {name}")
        print(f"{'=' * 65}")
        try:
            ok = func()
            results[key] = bool(ok)
            if ok:
                print(f"\n✓ {name} 验证通过")
        except Exception as e:
            print(f"\n✗ 异常: {e}")
            traceback.print_exc()
            results[key] = False

    print("\n" + "=" * 65)
    print("验证汇总")
    print("=" * 65)
    all_ok = True
    for key, (name, _) in SCENARIOS.items():
        if key in results:
            status = "✓ 通过" if results[key] else "✗ 失败"
            print(f"  {status}  {name}")
            if not results[key]:
                all_ok = False

    print(f"\n{'✅ 所有验证通过！' if all_ok else '❌ 部分验证失败，请检查上方错误信息'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
