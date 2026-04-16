"""Experiment C rolling-control evaluation under forecast-actual deviation scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from experiments.scenario_config import get_automated_scenarios
from experiments.result_schema import RollingControlResult
from experiments.dynamic_experiment import _advance_state
from experiments.evaluation_metrics import _build_tankan_spec, _run_pyresops_eval


AUTOMATED_SCENARIOS: dict[str, dict] = get_automated_scenarios()


RESULTS_DIR = Path(__file__).parent / "results"
AUTOMATED_RESULTS_DIR = RESULTS_DIR / "automated"


@dataclass
class DeviationUpdate:
    update_index: int
    elapsed_hours: float
    remaining_hours: float
    forecast_inflow: float
    actual_inflow: float
    deviation_id: str


class DeviationScenarioSimulator:
    """Generate deterministic deviation-update sequences for Experiment C."""

    def __init__(self, scenario_cfg: dict, deviation_cfg: dict):
        self.scenario_cfg = scenario_cfg
        self.deviation_cfg = deviation_cfg

    def _generation_cfg(self) -> dict:
        cfg = self.scenario_cfg.get("deviation_generation", {})
        return cfg if isinstance(cfg, dict) else {}

    def _expected_update_count(self) -> int | None:
        reproducibility = self.scenario_cfg.get("reproducibility", {})
        if (
            isinstance(reproducibility, dict)
            and reproducibility.get("expected_update_count") is not None
        ):
            return int(reproducibility["expected_update_count"])
        return None

    @staticmethod
    def _interpolate_series(
        sample_times: list[float], sample_values: list[float], target_times: list[float]
    ) -> list[float]:
        if len(sample_times) != len(sample_values):
            raise ValueError("sample_times and sample_values length mismatch")
        if not sample_times:
            raise ValueError("sample_times must not be empty")

        result: list[float] = []
        for target in target_times:
            if target <= sample_times[0]:
                result.append(float(sample_values[0]))
                continue
            if target >= sample_times[-1]:
                result.append(float(sample_values[-1]))
                continue

            for idx in range(1, len(sample_times)):
                left_t = float(sample_times[idx - 1])
                right_t = float(sample_times[idx])
                if left_t <= target <= right_t:
                    left_v = float(sample_values[idx - 1])
                    right_v = float(sample_values[idx])
                    span = max(right_t - left_t, 1e-9)
                    ratio = (target - left_t) / span
                    result.append(left_v + (right_v - left_v) * ratio)
                    break
        return result

    def _transform_reference_series(
        self,
        reference_times: list[float],
        reference_values: list[float],
        target_times: list[float],
        target_peak_flow: float,
        target_peak_hour: float,
        base_flow: float,
        clamp_min_flow: float,
    ) -> list[float]:
        peak_idx = max(range(len(reference_values)), key=lambda idx: float(reference_values[idx]))
        reference_peak_hour = float(reference_times[peak_idx])
        reference_peak_flow = float(reference_values[peak_idx])
        shift_hours = float(target_peak_hour) - reference_peak_hour
        shifted_sample_times = [float(t) - shift_hours for t in target_times]
        shifted_values = self._interpolate_series(
            reference_times, reference_values, shifted_sample_times
        )

        if abs(reference_peak_flow - base_flow) <= 1e-9:
            scale = 1.0
        else:
            scale = (float(target_peak_flow) - base_flow) / (reference_peak_flow - base_flow)

        return [
            max(clamp_min_flow, round(base_flow + (float(value) - base_flow) * scale, 4))
            for value in shifted_values
        ]

    def _build_flood_hydrograph(
        self, peak_flow: float, peak_hour: int, total_hours: int, step_hours: int
    ) -> list[float]:
        base_flow = float(
            self.scenario_cfg.get("initial_inflow", self.scenario_cfg.get("inflow", peak_flow))
        )
        values: list[float] = []
        for hour in range(0, total_hours, step_hours):
            if hour <= peak_hour:
                ratio = hour / max(peak_hour, 1)
                flow = base_flow + (peak_flow - base_flow) * ratio
            else:
                tail_hours = max(total_hours - peak_hour, 1)
                ratio = (hour - peak_hour) / tail_hours
                flow = peak_flow + (base_flow - peak_flow) * ratio
            values.append(max(0.0, float(flow)))
        return values

    def _build_sequence_s02(self) -> tuple[list[float], list[float], list[int]]:
        total_hours = int(self.scenario_cfg["duration_hours"])
        interval = int(self.scenario_cfg["forecast_interval_hours"])
        generation_cfg = self._generation_cfg()
        if interval <= 0:
            raise ValueError("forecast_interval_hours must be positive")

        required = [
            "forecast_peak_flow",
            "forecast_peak_hour",
            "actual_peak_flow",
            "actual_peak_hour",
        ]
        missing = [key for key in required if key not in self.deviation_cfg]
        if missing:
            raise ValueError(f"Missing S02 deviation fields: {missing}")

        for key in ("forecast_peak_hour", "actual_peak_hour"):
            peak_hour = int(self.deviation_cfg[key])
            if peak_hour < 0 or peak_hour > total_hours:
                raise ValueError(f"{key}={peak_hour} is out of range for total_hours={total_hours}")

        elapsed = generation_cfg.get("reference_elapsed_hours") or list(
            range(0, total_hours, interval)
        )
        elapsed = [int(hour) for hour in elapsed]
        reference_forecast = generation_cfg.get("reference_forecast_sequence")
        if reference_forecast:
            reference_forecast = [float(v) for v in reference_forecast]
            if len(reference_forecast) != len(elapsed):
                raise ValueError(
                    "S02 reference_forecast_sequence length must match reference_elapsed_hours"
                )
            base_flow = float(generation_cfg.get("reference_base_flow", reference_forecast[0]))
            clamp_min_flow = float(generation_cfg.get("clamp_min_flow", 0.0))
            forecast_series = self._transform_reference_series(
                reference_times=[float(hour) for hour in elapsed],
                reference_values=reference_forecast,
                target_times=[float(hour) for hour in elapsed],
                target_peak_flow=float(self.deviation_cfg["forecast_peak_flow"]),
                target_peak_hour=float(self.deviation_cfg["forecast_peak_hour"]),
                base_flow=base_flow,
                clamp_min_flow=clamp_min_flow,
            )
            actual_series = self._transform_reference_series(
                reference_times=[float(hour) for hour in elapsed],
                reference_values=reference_forecast,
                target_times=[float(hour) for hour in elapsed],
                target_peak_flow=float(self.deviation_cfg["actual_peak_flow"]),
                target_peak_hour=float(self.deviation_cfg["actual_peak_hour"]),
                base_flow=base_flow,
                clamp_min_flow=clamp_min_flow,
            )
        else:
            forecast_series = self._build_flood_hydrograph(
                peak_flow=float(self.deviation_cfg["forecast_peak_flow"]),
                peak_hour=int(self.deviation_cfg["forecast_peak_hour"]),
                total_hours=total_hours,
                step_hours=interval,
            )
            actual_series = self._build_flood_hydrograph(
                peak_flow=float(self.deviation_cfg["actual_peak_flow"]),
                peak_hour=int(self.deviation_cfg["actual_peak_hour"]),
                total_hours=total_hours,
                step_hours=interval,
            )
        return forecast_series, actual_series, elapsed

    def _build_sequence_s04(self) -> tuple[list[float], list[float], list[int]]:
        interval = int(self.scenario_cfg["forecast_interval_hours"])
        generation_cfg = self._generation_cfg()
        if interval <= 0:
            raise ValueError("forecast_interval_hours must be positive")
        if "xun_forecast" not in self.deviation_cfg or "xun_actual" not in self.deviation_cfg:
            raise ValueError("S04 deviation config must include xun_forecast and xun_actual")
        forecast_xun = [float(v) for v in self.deviation_cfg["xun_forecast"]]
        actual_xun = [float(v) for v in self.deviation_cfg["xun_actual"]]
        if len(forecast_xun) != len(actual_xun):
            raise ValueError(
                "S04 deviation sequence length mismatch: "
                f"forecast length {len(forecast_xun)} != actual length {len(actual_xun)}"
            )
        if not forecast_xun:
            raise ValueError("S04 deviation sequences must not be empty")
        elapsed = generation_cfg.get("reference_elapsed_hours") or [
            idx * interval for idx in range(len(actual_xun))
        ]
        elapsed = [int(hour) for hour in elapsed]
        if len(elapsed) != len(actual_xun):
            raise ValueError("S04 reference_elapsed_hours length must match xun sequence length")
        return forecast_xun, actual_xun, elapsed

    def generate_sequence(self) -> list[DeviationUpdate]:
        scenario_id = str(self.scenario_cfg["id"])
        if scenario_id == "S02":
            forecast_series, actual_series, elapsed = self._build_sequence_s02()
        elif scenario_id == "S04":
            forecast_series, actual_series, elapsed = self._build_sequence_s04()
        else:
            raise ValueError(
                f"DeviationScenarioSimulator only supports S02/S04, got {scenario_id}."
            )

        total_hours = int(self.scenario_cfg["duration_hours"])
        updates: list[DeviationUpdate] = []
        for idx, (fc, ac, elp) in enumerate(zip(forecast_series, actual_series, elapsed)):
            updates.append(
                DeviationUpdate(
                    update_index=idx,
                    elapsed_hours=float(elp),
                    remaining_hours=float(max(total_hours - elp, 0)),
                    forecast_inflow=round(float(fc), 2),
                    actual_inflow=round(float(ac), 2),
                    deviation_id=str(self.deviation_cfg["id"]),
                )
            )
        expected_count = self._expected_update_count()
        if expected_count is not None and len(updates) != expected_count:
            raise ValueError(
                f"Deviation update count mismatch: expected {expected_count}, got {len(updates)}"
            )
        return updates


def _extract_key_scores(eval_result: dict, key_dims: list[str]) -> float:
    scores = [float(eval_result.get(dim, 0.0)) for dim in key_dims]
    return sum(scores) / len(scores) if scores else 0.0


def _eval_scenario(scenario: dict, outflow: float) -> dict:
    return _run_pyresops_eval(
        scenario,
        outflow,
        _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5)),
    )


def _should_trigger_correction(
    state: dict,
    scenario_cfg: dict,
    update: DeviationUpdate,
    update_index: int,
    update_interval: int,
) -> tuple[bool, str]:
    if update_interval > 0 and update_index % update_interval == 0:
        return True, "scheduled"

    warning_level = scenario_cfg.get("warning_level")
    if warning_level is not None and float(state["level"]) > float(warning_level):
        return True, "safety_level"

    deviation_threshold = float(scenario_cfg.get("state_deviation_threshold", 0.05))
    denom = max(float(update.forecast_inflow), 1e-6)
    if (
        abs(float(state.get("inflow", update.actual_inflow)) - float(update.forecast_inflow))
        / denom
        > deviation_threshold
    ):
        return True, "safety_deviation"

    return False, ""


def _compute_recovery_steps(
    score_sequence: list[float],
    anomaly_start_index: int,
    recovery_threshold: float = 0.9,
    baseline_score: float = 1.0,
) -> int:
    target = float(baseline_score) * float(recovery_threshold)
    for idx in range(max(anomaly_start_index, 0), len(score_sequence)):
        if float(score_sequence[idx]) >= target:
            return idx - anomaly_start_index
    return -1


def _compute_performance_degradation(scenario_score: float, baseline_score: float) -> float:
    if baseline_score <= 0:
        return 0.0
    return max(0.0, (baseline_score - scenario_score) / baseline_score)


def _build_runtime_from_deviation(base_cfg: dict, state: dict, update: DeviationUpdate) -> dict:
    runtime = base_cfg.copy()
    runtime["current_level"] = float(state["level"])
    runtime["initial_storage"] = float(state["storage"])
    runtime["initial_inflow"] = float(state["inflow"])
    runtime["inflow"] = float(update.forecast_inflow)
    runtime["duration_hours"] = max(int(runtime["time_step_hours"]), int(update.remaining_hours))
    return runtime


def _controller_config(scenario_cfg: dict) -> dict:
    cfg = scenario_cfg.get("controller_config", {})
    return cfg if isinstance(cfg, dict) else {}


def _extract_key_dimension_scores(eval_result: dict, scenario_cfg: dict) -> dict:
    key_dims = list(scenario_cfg.get("key_dims", []))
    return {dim: float(eval_result.get(dim, 0.0)) for dim in key_dims}


def _resolve_static_outflow(scenario_cfg: dict) -> float:
    controller_cfg = _controller_config(scenario_cfg)
    configured = controller_cfg.get("static_outflow", scenario_cfg.get("initial_inflow"))
    outflow = float(configured)
    if outflow <= 0:
        raise RuntimeError(
            f"Invalid static outflow for scenario {scenario_cfg.get('id')}: {configured!r}"
        )
    return outflow


class StaticPlanController:
    """Static controller: use one fixed outflow throughout the run."""

    def __init__(self, scenario_cfg: dict):
        self.scenario_cfg = scenario_cfg

    def run(
        self, updates: list[DeviationUpdate], deviation_cfg: dict, baseline_score: float = 1.0
    ) -> RollingControlResult:
        if not updates:
            return RollingControlResult(
                scenario_id=self.scenario_cfg["id"],
                deviation_id=str(deviation_cfg["id"]),
                deviation_type=str(deviation_cfg.get("deviation_type", "unknown")),
                controller_type="static",
                total_constraint_violations=0,
                max_level_exceedance=0.0,
                has_critical_risk=False,
                key_dimension_scores={},
                overall_score=0.0,
                performance_degradation=0.0,
                correction_count=0,
                effective_correction_count=0,
                effective_correction_rate=0.0,
                recovery_steps=-1,
                forecast_steps=0,
                switch_occurred=False,
                is_heuristic_baseline=False,
                raw_eval_results=[],
            )

        state = {
            "level": float(self.scenario_cfg["current_level"]),
            "storage": float(self.scenario_cfg["initial_storage"]),
            "inflow": float(self.scenario_cfg["initial_inflow"]),
            "outflow": float(self.scenario_cfg["initial_inflow"]),
        }
        interval = int(self.scenario_cfg["forecast_interval_hours"])
        fixed_outflow = _resolve_static_outflow(self.scenario_cfg)

        evals: list[dict] = []
        levels: list[float] = []
        scores: list[float] = []

        for update in updates:
            runtime = _build_runtime_from_deviation(self.scenario_cfg, state, update)
            runtime["inflow"] = float(update.actual_inflow)
            ev = _eval_scenario(runtime, fixed_outflow)
            evals.append(ev)
            levels.append(float(state["level"]))
            scores.append(float(ev.get("overall_score", 0.0)))

            advance_hours = min(interval, int(update.remaining_hours))
            actual_runtime = runtime.copy()
            actual_runtime["inflow"] = float(update.actual_inflow)
            state = _advance_state(actual_runtime, fixed_outflow, advance_hours)
            state["inflow"] = float(update.actual_inflow)

        overall_score = float(evals[-1].get("overall_score", 0.0)) if evals else 0.0
        total_violations = int(sum(int(ev.get("constraint_violations", 0)) for ev in evals))
        max_exceed = max(
            [max(0.0, lv - float(self.scenario_cfg.get("normal_level", 160.0))) for lv in levels]
            or [0.0]
        )
        key_scores = _extract_key_dimension_scores(evals[-1], self.scenario_cfg) if evals else {}

        return RollingControlResult(
            scenario_id=self.scenario_cfg["id"],
            deviation_id=str(deviation_cfg["id"]),
            deviation_type=str(deviation_cfg.get("deviation_type", "unknown")),
            controller_type="static",
            total_constraint_violations=total_violations,
            max_level_exceedance=round(max_exceed, 4),
            has_critical_risk=bool(max_exceed > 0.0),
            key_dimension_scores=key_scores,
            overall_score=overall_score,
            performance_degradation=round(
                _compute_performance_degradation(overall_score, baseline_score), 4
            ),
            correction_count=1,
            effective_correction_count=0,
            effective_correction_rate=0.0,
            recovery_steps=_compute_recovery_steps(scores, 0, baseline_score=baseline_score),
            forecast_steps=len(updates),
            switch_occurred=False,
            is_heuristic_baseline=False,
            raw_eval_results=evals,
        )


class RuleBasedAdjustmentController:
    """Rule-based controller for Experiment C without any LLM usage."""

    def __init__(self, scenario_cfg: dict, deviation_cfg: dict):
        self.scenario_cfg = scenario_cfg
        self.deviation_cfg = deviation_cfg

    def _compute_rule_outflow(
        self, state: dict, forecast_inflow: float, actual_inflow: float
    ) -> float:
        sid = str(self.scenario_cfg["id"])
        level = float(state["level"])
        controller_cfg = _controller_config(self.scenario_cfg)
        min_ecological_flow = float(controller_cfg.get("min_ecological_flow", 50.0))
        if sid == "S02":
            downstream_limit = float(self.scenario_cfg.get("downstream_limit", 14000.0))
            outflow = min(float(actual_inflow), downstream_limit)
            if level > float(self.scenario_cfg.get("warning_level", 161.0)):
                outflow = min(
                    downstream_limit,
                    outflow * float(controller_cfg.get("warning_release_multiplier", 1.15)),
                )
            if level < float(controller_cfg.get("dead_level", 121.0)):
                outflow = max(
                    min_ecological_flow,
                    outflow * float(controller_cfg.get("low_level_release_multiplier", 0.85)),
                )
            return max(min_ecological_flow, outflow)

        if sid == "S04":
            generation_ratio = float(controller_cfg.get("generation_ratio", 0.9))
            outflow = max(min_ecological_flow, float(actual_inflow) * generation_ratio)
            if level < float(controller_cfg.get("min_level", 145.0)):
                outflow = max(
                    min_ecological_flow,
                    outflow * float(controller_cfg.get("low_level_release_multiplier", 0.8)),
                )
            return outflow

        return max(min_ecological_flow, float(actual_inflow))

    def run(
        self, updates: list[DeviationUpdate], baseline_score: float = 1.0
    ) -> RollingControlResult:
        state = {
            "level": float(self.scenario_cfg["current_level"]),
            "storage": float(self.scenario_cfg["initial_storage"]),
            "inflow": float(self.scenario_cfg["initial_inflow"]),
            "outflow": float(self.scenario_cfg["initial_inflow"]),
        }
        interval = int(self.scenario_cfg["forecast_interval_hours"])
        scheduled_interval = int(
            _controller_config(self.scenario_cfg).get("scheduled_update_interval_steps", 1)
        )
        evals: list[dict] = []
        levels: list[float] = []
        scores: list[float] = []
        corrections = 0
        effective = 0
        prev_score = None

        for idx, update in enumerate(updates):
            should_trigger, _ = _should_trigger_correction(
                state=state,
                scenario_cfg=self.scenario_cfg,
                update=update,
                update_index=idx,
                update_interval=scheduled_interval,
            )
            if should_trigger:
                corrections += 1
            runtime = _build_runtime_from_deviation(self.scenario_cfg, state, update)
            outflow = self._compute_rule_outflow(
                state, update.forecast_inflow, update.actual_inflow
            )
            actual_runtime = runtime.copy()
            actual_runtime["inflow"] = float(update.actual_inflow)
            ev = _eval_scenario(actual_runtime, outflow)
            score = float(ev.get("overall_score", 0.0))
            if prev_score is not None and score > prev_score:
                effective += 1
            prev_score = score
            evals.append(ev)
            levels.append(float(state["level"]))
            scores.append(score)

            advance_hours = min(interval, int(update.remaining_hours))
            state = _advance_state(actual_runtime, outflow, advance_hours)
            state["inflow"] = float(update.actual_inflow)

        overall_score = float(evals[-1].get("overall_score", 0.0)) if evals else 0.0
        total_violations = int(sum(int(ev.get("constraint_violations", 0)) for ev in evals))
        max_exceed = max(
            [max(0.0, lv - float(self.scenario_cfg.get("normal_level", 160.0))) for lv in levels]
            or [0.0]
        )
        key_scores = _extract_key_dimension_scores(evals[-1], self.scenario_cfg) if evals else {}
        eff_rate = float(effective / corrections) if corrections > 0 else 0.0

        return RollingControlResult(
            scenario_id=self.scenario_cfg["id"],
            deviation_id=str(self.deviation_cfg["id"]),
            deviation_type=str(self.deviation_cfg.get("deviation_type", "unknown")),
            controller_type="rule_based",
            total_constraint_violations=total_violations,
            max_level_exceedance=round(max_exceed, 4),
            has_critical_risk=bool(max_exceed > 0.0),
            key_dimension_scores=key_scores,
            overall_score=overall_score,
            performance_degradation=round(
                _compute_performance_degradation(overall_score, baseline_score), 4
            ),
            correction_count=corrections,
            effective_correction_count=effective,
            effective_correction_rate=round(eff_rate, 4),
            recovery_steps=_compute_recovery_steps(scores, 0, baseline_score=baseline_score),
            forecast_steps=len(updates),
            switch_occurred=False,
            is_heuristic_baseline=True,
            raw_eval_results=evals,
        )


class LLMToolBasedController:
    """LLM controller that updates plans through real tool-assisted calls."""

    def __init__(self, scenario_cfg: dict, experiment, switch_threshold: float = 0.10):
        self.scenario_cfg = scenario_cfg
        self.experiment = experiment
        self.switch_threshold = float(switch_threshold)

    @staticmethod
    def _require_real_tool_call(llm_result: dict) -> float:
        if not isinstance(llm_result, dict):
            raise RuntimeError("LLM tool response must be a dict.")
        if llm_result.get("success") is False:
            raise RuntimeError(f"LLM tool execution failed: {llm_result}")
        try:
            tool_call_count = int(llm_result.get("tool_call_count", 0))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("LLM tool response has invalid tool_call_count.") from exc
        if tool_call_count <= 0:
            raise RuntimeError("LLM tool response did not include any real tool call.")

        raw_outflow = llm_result.get("outflow")
        if raw_outflow is None:
            decision_text = llm_result.get("final_decision_text", "")
            if not isinstance(decision_text, str) or not decision_text.strip():
                raise RuntimeError("LLM output missing outflow and final_decision_text.")
            try:
                parsed = json.loads(decision_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError("LLM final_decision_text is not valid JSON.") from exc
            raw_outflow = parsed.get("outflow")

        try:
            outflow = float(raw_outflow)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"LLM output outflow is not numeric: {raw_outflow!r}") from exc
        if outflow <= 0:
            raise RuntimeError(f"LLM output outflow must be positive, got {outflow}.")
        return outflow

    def run(
        self, updates: list[DeviationUpdate], deviation_cfg: dict, baseline_score: float = 1.0
    ) -> RollingControlResult:
        state = {
            "level": float(self.scenario_cfg["current_level"]),
            "storage": float(self.scenario_cfg["initial_storage"]),
            "inflow": float(self.scenario_cfg["initial_inflow"]),
            "outflow": float(self.scenario_cfg["initial_inflow"]),
        }
        interval = int(self.scenario_cfg["forecast_interval_hours"])
        scheduled_interval = int(
            _controller_config(self.scenario_cfg).get("scheduled_update_interval_steps", 1)
        )
        active_outflow = float(self.scenario_cfg["initial_inflow"])
        evals: list[dict] = []
        levels: list[float] = []
        scores: list[float] = []
        corrections = 0
        effective = 0
        switch_occurred = False

        for idx, update in enumerate(updates):
            should_trigger, _ = _should_trigger_correction(
                state=state,
                scenario_cfg=self.scenario_cfg,
                update=update,
                update_index=idx,
                update_interval=scheduled_interval,
            )
            runtime = _build_runtime_from_deviation(self.scenario_cfg, state, update)

            if should_trigger:
                corrections += 1
                llm_result = self.experiment.run_scenario(runtime)
                candidate = self._require_real_tool_call(llm_result)

                current_eval = _eval_scenario(
                    {**runtime, "inflow": float(update.actual_inflow)}, active_outflow
                )
                candidate_eval = _eval_scenario(
                    {**runtime, "inflow": float(update.actual_inflow)}, candidate
                )
                key_dims = list(self.scenario_cfg.get("key_dims", []))
                current_score = _extract_key_scores(current_eval, key_dims)
                candidate_score = _extract_key_scores(candidate_eval, key_dims)
                gain = (candidate_score - current_score) / max(current_score, 1e-6)
                if gain > self.switch_threshold:
                    active_outflow = candidate
                    switch_occurred = True
                    if candidate_score > current_score:
                        effective += 1

            actual_runtime = runtime.copy()
            actual_runtime["inflow"] = float(update.actual_inflow)
            ev = _eval_scenario(actual_runtime, active_outflow)
            evals.append(ev)
            scores.append(float(ev.get("overall_score", 0.0)))
            levels.append(float(state["level"]))

            advance_hours = min(interval, int(update.remaining_hours))
            state = _advance_state(actual_runtime, active_outflow, advance_hours)
            state["inflow"] = float(update.actual_inflow)

        overall_score = float(evals[-1].get("overall_score", 0.0)) if evals else 0.0
        total_violations = int(sum(int(ev.get("constraint_violations", 0)) for ev in evals))
        max_exceed = max(
            [max(0.0, lv - float(self.scenario_cfg.get("normal_level", 160.0))) for lv in levels]
            or [0.0]
        )
        key_scores = _extract_key_dimension_scores(evals[-1], self.scenario_cfg) if evals else {}
        eff_rate = float(effective / corrections) if corrections > 0 else 0.0

        return RollingControlResult(
            scenario_id=self.scenario_cfg["id"],
            deviation_id=str(deviation_cfg["id"]),
            deviation_type=str(deviation_cfg.get("deviation_type", "unknown")),
            controller_type="llm_tool",
            total_constraint_violations=total_violations,
            max_level_exceedance=round(max_exceed, 4),
            has_critical_risk=bool(max_exceed > 0.0),
            key_dimension_scores=key_scores,
            overall_score=overall_score,
            performance_degradation=round(
                _compute_performance_degradation(overall_score, baseline_score), 4
            ),
            correction_count=corrections,
            effective_correction_count=effective,
            effective_correction_rate=round(eff_rate, 4),
            recovery_steps=_compute_recovery_steps(scores, 0, baseline_score=baseline_score),
            forecast_steps=len(updates),
            switch_occurred=switch_occurred,
            is_heuristic_baseline=False,
            raw_eval_results=evals,
        )


def run_deviation_experiment(
    scenario_id: str,
    deviation_id: str,
    controller_type: str,
    experiment=None,
    model_profile: str | None = None,
    save_result: bool = True,
) -> RollingControlResult:
    if scenario_id not in AUTOMATED_SCENARIOS:
        raise ValueError(f"Scenario {scenario_id} is missing automated configuration.")
    scenario_cfg = AUTOMATED_SCENARIOS[scenario_id].copy()
    deviation_list = list(scenario_cfg.get("deviation_scenarios", []))
    deviation_cfg = next((cfg for cfg in deviation_list if cfg.get("id") == deviation_id), None)
    if deviation_cfg is None:
        raise ValueError(f"Deviation scenario {deviation_id} does not exist under {scenario_id}.")

    simulator = DeviationScenarioSimulator(scenario_cfg, deviation_cfg)
    updates = simulator.generate_sequence()

    if experiment is None and controller_type == "llm_tool":
        from pyresops.agents import ReservoirAgentRuntime

        experiment = ReservoirAgentRuntime(model_profile=model_profile)

    baseline_deviation_id = str(scenario_cfg.get("baseline_deviation_id", "")).strip()
    if not baseline_deviation_id:
        raise ValueError(
            f"Scenario {scenario_id} must define baseline_deviation_id in scenarios_config.yaml"
        )
    baseline_cfg = next(
        (cfg for cfg in deviation_list if cfg.get("id") == baseline_deviation_id), None
    )
    if baseline_cfg is None:
        raise ValueError(
            f"Scenario {scenario_id} is missing an explicit D0 baseline deviation configuration"
        )
    baseline_updates = DeviationScenarioSimulator(scenario_cfg, baseline_cfg).generate_sequence()

    if controller_type == "static":
        baseline_ctrl = StaticPlanController(scenario_cfg)
        baseline_result = baseline_ctrl.run(baseline_updates, baseline_cfg, baseline_score=1.0)
        result = StaticPlanController(scenario_cfg).run(
            updates,
            deviation_cfg,
            baseline_score=baseline_result.overall_score,
        )
    elif controller_type == "rule_based":
        baseline_ctrl = RuleBasedAdjustmentController(scenario_cfg, baseline_cfg)
        baseline_result = baseline_ctrl.run(baseline_updates, baseline_score=1.0)
        result = RuleBasedAdjustmentController(scenario_cfg, deviation_cfg).run(
            updates,
            baseline_score=baseline_result.overall_score,
        )
    elif controller_type == "llm_tool":
        threshold = float(scenario_cfg.get("switch_threshold", 0.10))
        baseline_ctrl = LLMToolBasedController(scenario_cfg, experiment, switch_threshold=threshold)
        baseline_result = baseline_ctrl.run(baseline_updates, baseline_cfg, baseline_score=1.0)
        result = LLMToolBasedController(scenario_cfg, experiment, switch_threshold=threshold).run(
            updates,
            deviation_cfg,
            baseline_score=baseline_result.overall_score,
        )
    else:
        raise ValueError(f"Unknown controller_type: {controller_type}")

    if save_result:
        out_dir = AUTOMATED_RESULTS_DIR / "deviation"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{scenario_id}_{deviation_id}_{controller_type}.json"
        out_path.write_text(result.to_json(), encoding="utf-8")

    return result


def run_all_deviation_experiments(
    scenario_ids: list[str] | tuple[str, ...] = ("S02", "S04"),
    controller_types: list[str] | tuple[str, ...] = ("static", "rule_based", "llm_tool"),
    model_profile: str | None = None,
) -> list[RollingControlResult]:
    outputs: list[RollingControlResult] = []
    experiment = None
    if any(ct == "llm_tool" for ct in controller_types):
        from pyresops.agents import ReservoirAgentRuntime

        experiment = ReservoirAgentRuntime(model_profile=model_profile)

    for scenario_id in scenario_ids:
        scenario_cfg = AUTOMATED_SCENARIOS.get(scenario_id, {})
        for deviation_cfg in scenario_cfg.get("deviation_scenarios", []):
            deviation_id = str(deviation_cfg["id"])
            for controller_type in controller_types:
                outputs.append(
                    run_deviation_experiment(
                        scenario_id=scenario_id,
                        deviation_id=deviation_id,
                        controller_type=controller_type,
                        experiment=experiment,
                        model_profile=model_profile,
                        save_result=True,
                    )
                )
    return outputs


def aggregate_results(results: list[RollingControlResult]) -> dict:
    summary: dict[str, dict] = {}
    if not results:
        return summary
    grouped: dict[str, list[RollingControlResult]] = {}
    for result in results:
        grouped.setdefault(result.controller_type, []).append(result)

    for controller, items in grouped.items():
        scores = [float(item.overall_score) for item in items]
        violations = [int(item.total_constraint_violations) for item in items]
        effective_rates = [float(item.effective_correction_rate) for item in items]
        summary[controller] = {
            "count": len(items),
            "mean_score": round(sum(scores) / len(scores), 4),
            "worst_case_score": round(min(scores), 4),
            "mean_constraint_violations": round(sum(violations) / len(violations), 4),
            "mean_effective_correction_rate": round(sum(effective_rates) / len(effective_rates), 4),
        }
    return summary


if __name__ == "__main__":
    import sys

    scenario_ids = tuple(sys.argv[1:]) if len(sys.argv) > 1 else ("S02", "S04")
    results = run_all_deviation_experiments(scenario_ids=scenario_ids)
    print(json.dumps(aggregate_results(results), ensure_ascii=False, indent=2))
