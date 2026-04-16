from __future__ import annotations

import json
from datetime import timedelta

from pyresops.core import resolve_scenario_start_time


SUPPORTED_MODULE_TYPES = {"constant_release", "flexible_release"}


def resolve_tool_bundle_start_time(scenario: dict):
    return resolve_scenario_start_time(scenario)


class ReservoirToolBundleFactory:
    """Compose experiment-agent tools only; no MCP server registration here."""

    def __init__(self, scenario_resolver=None):
        self._scenario_resolver = scenario_resolver

    def resolve_scenario_config(
        self, scenario_id: str, runtime_scenario: dict | None = None
    ) -> dict | None:
        if runtime_scenario and runtime_scenario.get("id") == scenario_id:
            return runtime_scenario
        if self._scenario_resolver is None:
            return None
        return self._scenario_resolver(scenario_id)

    def make_tools(self, spec, runtime_scenario: dict | None = None):
        from agno.tools import tool as agno_tool

        def _get_scenario(scenario_id: str) -> dict | None:
            return self.resolve_scenario_config(scenario_id, runtime_scenario)

        @agno_tool
        def get_reservoir_status(scenario_id: str) -> str:
            sc = _get_scenario(scenario_id)
            if sc is None:
                return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)
            current_inflow = sc.get("initial_inflow", sc["inflow"])
            return json.dumps(
                {
                    "scenario_id": scenario_id,
                    "current_level_m": sc["current_level"],
                    "initial_storage_billion_m3": sc["initial_storage"],
                    "current_inflow_m3s": current_inflow,
                    "forecast_inflow_m3s": sc["inflow"],
                    "dead_level_m": spec.dead_level,
                    "normal_level_m": spec.normal_level,
                    "flood_limit_level_m": sc["flood_limit_level"],
                    "design_flood_level_m": spec.design_flood_level,
                    "total_capacity_billion_m3": spec.total_capacity,
                    "flood_capacity_billion_m3": spec.flood_capacity,
                    "season": sc["season"],
                    "flood_risk": sc["flood_risk"],
                },
                ensure_ascii=False,
                indent=2,
            )

        @agno_tool
        def simulate_dispatch_program(
            scenario_id: str,
            target_outflow: float,
            module_type: str = "constant_release",
        ) -> str:
            from pyresops.core import SimulationEngine
            from pyresops.domain.forecast import ForecastBundle, ForecastSeries
            from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
            from pyresops.domain.reservoir import ReservoirState
            from pyresops.modules import ConstantReleaseModule, FlexibleReleaseModule

            sc = _get_scenario(scenario_id)
            if sc is None:
                return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

            if module_type not in SUPPORTED_MODULE_TYPES:
                return json.dumps(
                    {
                        "error": "unsupported_module_type",
                        "message": (
                            "simulate_dispatch_program only supports "
                            "constant_release and flexible_release"
                        ),
                        "module_type": module_type,
                        "supported_module_types": ["constant_release", "flexible_release"],
                        "scenario_id": scenario_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                )

            start = resolve_tool_bundle_start_time(sc)
            step_seconds = sc["time_step_hours"] * 3600
            n_steps = sc["duration_hours"] // sc["time_step_hours"]
            end = start + timedelta(hours=sc["duration_hours"])

            state = ReservoirState(
                timestamp=start,
                level=sc["current_level"],
                storage=sc["initial_storage"],
                inflow=sc["initial_inflow"],
                outflow=sc["initial_inflow"],
            )

            inflow_base = sc["inflow"]
            timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
            values = [float(inflow_base)] * n_steps
            forecast = ForecastBundle(
                forecast_time=start,
                series=[
                    ForecastSeries(
                        variable="inflow",
                        timestamps=timestamps,
                        values=values,
                        unit="m³/s",
                    )
                ],
            )

            horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)
            program = DispatchProgram(
                id=f"{scenario_id}_sim",
                name=f"{sc['name']} 仿真",
                time_horizon=horizon,
                module_sequence=[
                    ModuleInstance(
                        id="m01",
                        module_type=module_type,
                        parameters={
                            "target_flow": target_outflow,
                            "target_outflow": target_outflow,
                            "min_flow": 50.0,
                            "max_flow": spec.discharge_capacity.get_max_discharge(
                                sc["current_level"]
                            ),
                        },
                    )
                ],
            )

            if module_type == "flexible_release":
                release_vals = [float(target_outflow)] * n_steps
                modules_map = {
                    "flexible_release": FlexibleReleaseModule(
                        {
                            "control_interval_seconds": step_seconds,
                            "release_values": release_vals,
                        }
                    )
                }
            else:
                modules_map = {
                    "constant_release": ConstantReleaseModule({"target_flow": target_outflow})
                }

            engine = SimulationEngine(spec)
            result = engine.simulate(program, state, forecast, modules_map)

            snapshots_summary = [
                {
                    "step": i,
                    "timestamp": snap.timestamp.isoformat(),
                    "level_m": round(snap.level, 3),
                    "inflow_m3s": round(snap.inflow, 1),
                    "outflow_m3s": round(snap.outflow, 1),
                }
                for i, snap in enumerate(result.snapshots[:: max(1, len(result.snapshots) // 10)])
            ]

            return json.dumps(
                {
                    "scenario_id": scenario_id,
                    "declared_outflow": target_outflow,
                    "target_outflow": target_outflow,
                    "max_level_m": round(result.max_level, 3),
                    "min_level_m": round(result.min_level, 3),
                    "final_level_m": round(result.snapshots[-1].level, 3),
                    "avg_outflow_m3s": round(result.avg_outflow, 1),
                    "total_steps": len(result.snapshots),
                    "snapshots_sample": snapshots_summary,
                },
                ensure_ascii=False,
                indent=2,
            )

        @agno_tool
        def evaluate_dispatch_result(
            scenario_id: str,
            target_outflow: float,
            eco_min_flow: float = 50.0,
        ) -> str:
            from pyresops.core import SimulationEngine
            from pyresops.domain.constraint import Constraint, ConstraintSet
            from pyresops.domain.forecast import ForecastBundle, ForecastSeries
            from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
            from pyresops.domain.reservoir import ReservoirState
            from pyresops.modules import ConstantReleaseModule
            from pyresops.services import EvaluationService

            sc = _get_scenario(scenario_id)
            if sc is None:
                return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

            start = resolve_tool_bundle_start_time(sc)
            step_seconds = sc["time_step_hours"] * 3600
            n_steps = sc["duration_hours"] // sc["time_step_hours"]
            end = start + timedelta(hours=sc["duration_hours"])

            state = ReservoirState(
                timestamp=start,
                level=sc["current_level"],
                storage=sc["initial_storage"],
                inflow=sc["initial_inflow"],
                outflow=sc["initial_inflow"],
            )

            timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
            forecast = ForecastBundle(
                forecast_time=start,
                series=[
                    ForecastSeries(
                        variable="inflow",
                        timestamps=timestamps,
                        values=[float(sc["inflow"])] * n_steps,
                        unit="m³/s",
                    )
                ],
            )

            horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)
            program = DispatchProgram(
                id=f"{scenario_id}_eval",
                name=f"{sc['name']} 评估",
                time_horizon=horizon,
                module_sequence=[
                    ModuleInstance(
                        id="m01",
                        module_type="constant_release",
                        parameters={"target_flow": target_outflow},
                    )
                ],
            )

            modules_map = {
                "constant_release": ConstantReleaseModule({"target_flow": target_outflow})
            }
            engine = SimulationEngine(spec)
            sim_result = engine.simulate(program, state, forecast, modules_map)

            constraint_set = ConstraintSet(
                constraints=[
                    Constraint(
                        id="level_min",
                        name="死水位下限",
                        constraint_type="level_min",
                        parameters={"min_level": spec.dead_level},
                        priority=10,
                    ),
                    Constraint(
                        id="level_max",
                        name="正常蓄水位上限",
                        constraint_type="level_max",
                        parameters={"max_level": spec.normal_level},
                        priority=10,
                    ),
                    Constraint(
                        id="eco_flow",
                        name="生态最小流量",
                        constraint_type="ecological_min_flow",
                        parameters={"min_flow": eco_min_flow},
                        priority=9,
                    ),
                ]
            )

            ev = EvaluationService(spec)
            eval_result = ev.evaluate(sim_result, constraint_set=constraint_set)

            return json.dumps(
                {
                    "scenario_id": scenario_id,
                    "declared_outflow": target_outflow,
                    "target_outflow": target_outflow,
                    "overall_score": round(eval_result.overall_score, 4),
                    "flood_control_score": round(eval_result.flood_control_score, 4),
                    "water_supply_score": round(eval_result.water_supply_score, 4),
                    "power_generation_score": round(eval_result.power_generation_score, 4),
                    "ecological_score": round(eval_result.ecological_score, 4),
                    "constraint_violations_count": len(eval_result.constraint_violations),
                    "constraint_violations": eval_result.constraint_violations[:5],
                },
                ensure_ascii=False,
                indent=2,
            )

        @agno_tool
        def check_safety_constraints(
            scenario_id: str,
            proposed_outflow: float,
        ) -> str:
            sc = _get_scenario(scenario_id)
            if sc is None:
                return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

            violations = []
            checks = {}

            max_discharge = spec.discharge_capacity.get_max_discharge(sc["current_level"])
            if proposed_outflow > max_discharge:
                violations.append(
                    f"出库 {proposed_outflow} m³/s 超过当前水位泄流能力 {max_discharge:.1f} m³/s"
                )
            checks["discharge_capacity"] = {
                "ok": proposed_outflow <= max_discharge,
                "proposed": proposed_outflow,
                "max_allowed": round(max_discharge, 1),
            }

            eco_min = 50.0
            checks["ecological_flow"] = {
                "ok": proposed_outflow >= eco_min,
                "proposed": proposed_outflow,
                "min_required": eco_min,
            }
            if proposed_outflow < eco_min:
                violations.append(f"出库 {proposed_outflow} m³/s 低于生态最小流量 {eco_min} m³/s")

            if (
                sc["flood_risk"] in ("high", "extreme")
                and sc["current_level"] > sc["flood_limit_level"]
            ):
                recommended_min_outflow = sc.get("initial_inflow", sc["inflow"]) * 0.8
                if proposed_outflow < recommended_min_outflow:
                    violations.append(
                        f"防洪高风险时出库 {proposed_outflow} m³/s 偏小，"
                        f"建议 ≥ {recommended_min_outflow:.0f} m³/s"
                    )
            checks["flood_risk_compliance"] = {
                "flood_risk": sc["flood_risk"],
                "current_level_m": sc["current_level"],
                "flood_limit_level_m": sc["flood_limit_level"],
                "level_above_limit": round(sc["current_level"] - sc["flood_limit_level"], 2),
            }

            return json.dumps(
                {
                    "scenario_id": scenario_id,
                    "proposed_outflow": proposed_outflow,
                    "safe": len(violations) == 0,
                    "violations": violations,
                    "checks": checks,
                },
                ensure_ascii=False,
                indent=2,
            )

        @agno_tool
        def optimize_release_plan(
            scenario_id: str,
            horizon_hours: int = 24,
            min_flow: float = 50.0,
            max_flow: float = 5000.0,
        ) -> str:
            from pyresops.domain.forecast import ForecastBundle, ForecastSeries
            from pyresops.domain.reservoir import ReservoirState
            from pyresops.services import OptimizationService, ProgramService

            sc = _get_scenario(scenario_id)
            if sc is None:
                return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

            start = resolve_tool_bundle_start_time(sc)
            step_seconds = sc["time_step_hours"] * 3600
            n_steps = horizon_hours // sc["time_step_hours"]

            state = ReservoirState(
                timestamp=start,
                level=sc["current_level"],
                storage=sc["initial_storage"],
                inflow=sc["initial_inflow"],
                outflow=sc["initial_inflow"],
            )

            timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
            forecast = ForecastBundle(
                forecast_time=start,
                series=[
                    ForecastSeries(
                        variable="inflow",
                        timestamps=timestamps,
                        values=[float(sc["inflow"])] * n_steps,
                        unit="m³/s",
                    )
                ],
            )

            program_svc = ProgramService()
            opt_svc = OptimizationService(spec, program_svc)

            constraints = {
                "min_environmental_flow": min_flow,
                "max_outflow": max_flow,
                "min_release": min_flow,
            }
            objectives = {
                "power_priority": sc["flood_risk"] == "none",
                "flood_control": sc["flood_risk"] in ("high", "extreme"),
            }
            directives = {
                "safety_factor": 0.9 if sc["flood_risk"] in ("high", "extreme") else 0.85,
                "season": sc["season"],
            }

            program, schedule = opt_svc.optimize_flexible_release_plan(
                initial_state=state,
                forecast=forecast,
                horizon_hours=horizon_hours,
                control_interval_seconds=step_seconds,
                constraints=constraints,
                objectives=objectives,
                directives=directives,
                name=f"{sc['id']}_optimized",
            )

            return json.dumps(
                {
                    "scenario_id": scenario_id,
                    "program_id": program.id,
                    "horizon_hours": horizon_hours,
                    "n_segments": len(schedule.release_values),
                    "release_values_m3s": [round(v, 1) for v in schedule.release_values],
                    "avg_release_m3s": round(
                        sum(schedule.release_values) / len(schedule.release_values)
                        if schedule.release_values
                        else 0,
                        1,
                    ),
                    "min_release_m3s": round(
                        min(schedule.release_values) if schedule.release_values else 0, 1
                    ),
                    "max_release_m3s": round(
                        max(schedule.release_values) if schedule.release_values else 0, 1
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )

        @agno_tool
        def query_dispatch_rules(scenario_id: str) -> str:
            sc = _get_scenario(scenario_id)
            if sc is None:
                return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

            rules_db = {
                "S01": {
                    "场景": "台汛期预泄调度",
                    "适用规程": "《2025年度水库控制运用计划》第3.1节 台汛期调度规则",
                    "核心要求": [
                        "汛期限制水位 156.5m（7月1日至9月30日台汛期）",
                        "水位超过156.5m时须主动预泄至156.5m",
                        "预泄期间出库不超过下游安全泄量",
                        "台风预报48小时内须完成预泄",
                    ],
                    "关键参数": {
                        "flood_limit_level_m": 156.5,
                        "downstream_safe_flow_m3s": 14000,
                        "eco_min_flow_m3s": 50,
                        "max_discharge_at_160m_m3s": 5861,
                    },
                },
                "S02": {
                    "场景": "梅汛期错峰调度",
                    "适用规程": "《2025年度水库控制运用计划》第3.2节 梅汛期调度规则",
                    "核心要求": [
                        "梅汛期限制水位 160.0m（4月1日至6月30日）",
                        "水位在160~161.5m时执行补偿凑泄，控鹤城站≤14000 m³/s",
                        "马斯京根算法演算传播时间约5小时",
                        "错峰调度须提前5小时预报区间流量",
                    ],
                    "关键参数": {
                        "flood_limit_level_m": 160.0,
                        "hecheng_safe_flow_m3s": 14000,
                        "muskingum_propagation_hours": 5,
                        "max_level_for_spill_m": 161.5,
                        "eco_min_flow_m3s": 50,
                    },
                },
                "S03": {
                    "场景": "极端洪水应急调度",
                    "适用规程": "《2025年度水库控制运用计划》第4节 超标准洪水应急预案",
                    "核心要求": [
                        "水位超设计洪水位(165.87m)时启动应急预案",
                        "全力开启溢洪道，最大泄洪能力11085 m³/s",
                        "向下游发布预警，疏散安全区群众",
                        "水库大坝安全优先，允许下游超安全流量",
                    ],
                    "关键参数": {
                        "design_flood_level_m": 165.87,
                        "check_flood_level_m": 169.15,
                        "max_discharge_at_165m_m3s": 11085,
                        "emergency_trigger_level_m": 165.87,
                    },
                },
                "S04": {
                    "场景": "枯水期发电优化",
                    "适用规程": "《2025年度水库控制运用计划》第5节 枯水期发电调度",
                    "核心要求": [
                        "死水位以上（120m）最大化发电量",
                        "最小下泄流量不低于50 m³/s（生态基流）",
                        "水位低于135m时降低出力，保护水位",
                        "额定发电流量约400 m³/s（机组满发）",
                    ],
                    "关键参数": {
                        "dead_level_m": 120.0,
                        "eco_min_flow_m3s": 50,
                        "rated_power_flow_m3s": 400,
                        "low_level_threshold_m": 135.0,
                        "low_level_power_flow_m3s": 80,
                    },
                },
                "S05": {
                    "场景": "梅台过渡期降水位",
                    "适用规程": "《2025年度水库控制运用计划》第3.3节 汛期过渡规则",
                    "核心要求": [
                        "6月30日～7月1日梅汛期转台汛期",
                        "水位须从160m降至156.5m，预留防洪库容",
                        "3天内完成降水位操作",
                        "降水位期间加大出库，同时监测下游",
                    ],
                    "关键参数": {
                        "start_level_m": 160.0,
                        "target_level_m": 156.5,
                        "level_drop_m": 3.5,
                        "transition_days": 3,
                        "eco_min_flow_m3s": 50,
                    },
                },
            }

            rule_info = rules_db.get(scenario_id, {"error": f"未找到场景 {scenario_id} 的规程信息"})
            return json.dumps(rule_info, ensure_ascii=False, indent=2)

        return [
            get_reservoir_status,
            simulate_dispatch_program,
            evaluate_dispatch_result,
            check_safety_constraints,
            optimize_release_plan,
            query_dispatch_rules,
        ]
