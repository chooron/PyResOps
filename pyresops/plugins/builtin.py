"""Built-in execution plugins."""

from __future__ import annotations

from math import sqrt
from typing import Any

from ..domain.forecast import ForecastSeries
from .base import InputPluginBase, PostPluginBase, StepPluginBase
from .models import (
    BasePluginContext,
    InputPluginContext,
    PluginExecutionResult,
    PluginStage,
    PostPluginContext,
    StepPluginContext,
)
from .registry import ExecutionPluginRegistry


class SimpleRainfallRunoffPlugin(InputPluginBase):
    """Simple rainfall-runoff transformation for inflow generation."""

    plugin_name = "simple_rainfall_runoff"
    stage = PluginStage.INFLOW_GENERATION
    summary = "Generate inflow series from rainfall using a runoff coefficient and lag."
    applicable_scenarios = [
        "Rainfall-only forecast inputs",
        "Rapid scenario generation when inflow is unavailable",
    ]
    required_inputs = ["forecast.series[rainfall]"]
    optional_inputs = ["initial_state", "forecast.series[inflow]"]
    config_schema = {
        "type": "object",
        "properties": {
            "runoff_coefficient": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "lag_steps": {"type": "integer", "minimum": 0},
            "baseflow": {"type": "number", "minimum": 0.0, "default": 0.0},
        },
        "required": ["runoff_coefficient", "lag_steps"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "generated_series": {
                "type": "object",
                "properties": {
                    "variable": {"const": "inflow"},
                    "timestamps": {"type": "array"},
                    "values": {"type": "array"},
                    "unit": {"type": "string"},
                },
            }
        },
    }
    limitations = [
        "Engineering placeholder only; not a calibrated hydrologic model.",
        "Assumes rainfall values can be scaled directly into inflow-like magnitudes.",
    ]
    capability_tags = ["rainfall", "inflow_generation"]
    provides = ["forecast.series[inflow]"]

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if "runoff_coefficient" not in config:
            raise ValueError("simple_rainfall_runoff requires 'runoff_coefficient'")
        if "lag_steps" not in config:
            raise ValueError("simple_rainfall_runoff requires 'lag_steps'")
        coefficient = float(config["runoff_coefficient"])
        if coefficient < 0.0 or coefficient > 1.0:
            raise ValueError("runoff_coefficient must be within [0, 1]")
        lag_steps = int(config["lag_steps"])
        if lag_steps < 0:
            raise ValueError("lag_steps must be >= 0")
        baseflow = float(config.get("baseflow", 0.0))
        if baseflow < 0.0:
            raise ValueError("baseflow must be >= 0")
        return {
            "runoff_coefficient": coefficient,
            "lag_steps": lag_steps,
            "baseflow": baseflow,
        }

    def validate_inputs(self, context: BasePluginContext) -> None:
        super().validate_inputs(context)
        assert isinstance(context, InputPluginContext)
        rainfall = context.forecast.get_series("rainfall")
        if rainfall is None:
            raise ValueError("simple_rainfall_runoff requires forecast series 'rainfall'")
        if len(rainfall.timestamps) != len(rainfall.values):
            raise ValueError("rainfall timestamps and values length mismatch")
        if not rainfall.timestamps:
            raise ValueError("rainfall series must not be empty")

    def execute(
        self,
        context: BasePluginContext,
        config: dict[str, Any],
    ) -> PluginExecutionResult:
        self.validate_inputs(context)
        assert isinstance(context, InputPluginContext)
        normalized = self.validate_config(config)
        rainfall = context.forecast.get_series("rainfall")
        assert rainfall is not None

        baseflow = float(normalized["baseflow"])
        coefficient = float(normalized["runoff_coefficient"])
        lag_steps = int(normalized["lag_steps"])
        raw_values = [baseflow + coefficient * float(value) for value in rainfall.values]
        shifted_values = [baseflow] * lag_steps + raw_values[:-lag_steps] if lag_steps > 0 else raw_values

        warnings: list[str] = []
        if "baseflow" not in config:
            warnings.append("baseflow not provided; defaulted to 0.0")

        generated = ForecastSeries(
            variable="inflow",
            timestamps=list(rainfall.timestamps),
            values=[float(value) for value in shifted_values],
            unit="m3/s",
        )
        return PluginExecutionResult(
            payload={"generated_series": generated.model_dump(mode="json")},
            diagnostics={
                "input_length": len(rainfall.values),
                "output_length": len(shifted_values),
                "lag_applied": lag_steps > 0,
                "rainfall_total": round(sum(float(value) for value in rainfall.values), 6),
                "generated_total": round(sum(float(value) for value in shifted_values), 6),
            },
            used_config=normalized,
            warnings=warnings,
            metadata={
                "plugin_name": self.plugin_name,
                "plugin_kind": self.plugin_kind,
                "stage": self.stage,
            },
        )

    def generate(self, *, forecast, initial_state, config: dict[str, Any]) -> PluginExecutionResult:
        """Compatibility adapter for the legacy professional API."""
        return self.execute(
            InputPluginContext(forecast=forecast, initial_state=initial_state),
            config,
        )


class GateReleaseCalculatorPlugin(StepPluginBase):
    """Estimate release from gate geometry and reservoir head."""

    plugin_name = "gate_release_calculator"
    stage = PluginStage.DISPATCH_STEP
    summary = "Estimate gate-controlled release using water level, opening, and structure parameters."
    applicable_scenarios = [
        "Gate-controlled release estimation",
        "Convert operation intent into physically constrained release",
    ]
    required_inputs = ["state.level", "config.gate_opening", "config.gate_width"]
    optional_inputs = ["baseline_outflow", "active_module"]
    config_schema = {
        "type": "object",
        "properties": {
            "discharge_coefficient": {"type": "number", "exclusiveMinimum": 0.0},
            "gate_width": {"type": "number", "exclusiveMinimum": 0.0},
            "gate_count": {"type": "integer", "minimum": 1, "default": 1},
            "gate_height": {"type": "number", "exclusiveMinimum": 0.0, "default": 1.0},
            "gate_opening": {"type": "number", "minimum": 0.0},
            "gate_sill_level": {"type": "number", "default": 0.0},
        },
        "required": ["discharge_coefficient", "gate_width", "gate_opening"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "estimated_outflow": {"type": "number"},
            "opening_fraction": {"type": "number"},
            "hydraulic_head": {"type": "number"},
        },
    }
    limitations = [
        "Simplified orifice-style equation; does not represent detailed gate hydraulics.",
        "Assumes submerged and transition effects can be ignored.",
    ]
    capability_tags = ["gate", "release", "hydraulics"]
    provides = ["step.estimated_outflow"]

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        required = ("discharge_coefficient", "gate_width", "gate_opening")
        missing = [name for name in required if name not in config]
        if missing:
            raise ValueError(f"gate_release_calculator missing config: {missing}")
        normalized = {
            "discharge_coefficient": float(config["discharge_coefficient"]),
            "gate_width": float(config["gate_width"]),
            "gate_count": int(config.get("gate_count", 1)),
            "gate_height": float(config.get("gate_height", 1.0)),
            "gate_opening": float(config["gate_opening"]),
            "gate_sill_level": float(config.get("gate_sill_level", 0.0)),
        }
        if normalized["discharge_coefficient"] <= 0.0:
            raise ValueError("discharge_coefficient must be > 0")
        if normalized["gate_width"] <= 0.0:
            raise ValueError("gate_width must be > 0")
        if normalized["gate_count"] < 1:
            raise ValueError("gate_count must be >= 1")
        if normalized["gate_height"] <= 0.0:
            raise ValueError("gate_height must be > 0")
        if normalized["gate_opening"] < 0.0:
            raise ValueError("gate_opening must be >= 0")
        return normalized

    def validate_inputs(self, context: BasePluginContext) -> None:
        super().validate_inputs(context)
        assert isinstance(context, StepPluginContext)
        if context.state.level is None:
            raise ValueError("gate_release_calculator requires state.level")

    def execute(
        self,
        context: BasePluginContext,
        config: dict[str, Any],
    ) -> PluginExecutionResult:
        self.validate_inputs(context)
        assert isinstance(context, StepPluginContext)
        normalized = self.validate_config(config)

        gate_height = float(normalized["gate_height"])
        raw_opening = float(normalized["gate_opening"])
        clipped_opening = max(0.0, min(raw_opening, gate_height))
        head = max(float(context.state.level) - float(normalized["gate_sill_level"]), 0.0)
        estimated_outflow = (
            float(normalized["discharge_coefficient"])
            * float(normalized["gate_count"])
            * float(normalized["gate_width"])
            * clipped_opening
            * sqrt(2.0 * 9.81 * head)
        )

        warnings: list[str] = []
        if raw_opening > gate_height:
            warnings.append("gate_opening exceeded gate_height and was clipped")

        return PluginExecutionResult(
            payload={
                "estimated_outflow": max(0.0, float(estimated_outflow)),
                "opening_fraction": 0.0 if gate_height == 0 else clipped_opening / gate_height,
                "hydraulic_head": head,
                "baseline_outflow": float(context.baseline_outflow),
            },
            diagnostics={
                "step_index": context.step_index,
                "raw_gate_opening": raw_opening,
                "effective_gate_opening": clipped_opening,
                "gate_area": float(normalized["gate_count"])
                * float(normalized["gate_width"])
                * clipped_opening,
            },
            used_config=normalized,
            warnings=warnings,
            metadata={
                "plugin_name": self.plugin_name,
                "plugin_kind": self.plugin_kind,
                "stage": self.stage,
                "active_module": context.active_module,
            },
        )

    def compute(
        self,
        *,
        state,
        inflow: float,
        baseline_outflow: float,
        active_module: str | None,
        config: dict[str, Any],
        step_index: int,
    ) -> PluginExecutionResult:
        """Compatibility adapter for the legacy professional API."""
        return self.execute(
            StepPluginContext(
                step_index=step_index,
                state=state,
                inflow=inflow,
                baseline_outflow=baseline_outflow,
                active_module=active_module,
            ),
            config,
        )


class MuskingumRoutingPlugin(PostPluginBase):
    """Classic Muskingum routing for downstream flow propagation."""

    plugin_name = "muskingum_routing"
    stage = PluginStage.POST_SIMULATION
    summary = "Route reservoir outflow downstream with a Muskingum channel model."
    applicable_scenarios = [
        "Downstream section impact estimation",
        "Peak attenuation and timing analysis",
    ]
    required_inputs = [
        "simulation_result.snapshots[outflow]",
        "config.k",
        "config.x",
        "config.dt_hours",
    ]
    config_schema = {
        "type": "object",
        "properties": {
            "k": {"type": "number", "exclusiveMinimum": 0.0},
            "x": {"type": "number", "minimum": 0.0, "maximum": 0.5},
            "dt_hours": {"type": "number", "exclusiveMinimum": 0.0},
        },
        "required": ["k", "x", "dt_hours"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "downstream_flow_series": {"type": "object"},
            "peak_flow": {"type": "number"},
            "peak_time": {"type": "string"},
            "attenuation_summary": {"type": "object"},
        },
    }
    limitations = [
        "Assumes a lumped reach with fixed K/X parameters.",
        "Not suitable for highly dynamic backwater or storage-dominated routing.",
    ]
    capability_tags = ["routing", "downstream_impact"]
    provides = ["post.downstream_flow_series", "post.attenuation_summary"]

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        required = ("k", "x", "dt_hours")
        missing = [name for name in required if name not in config]
        if missing:
            raise ValueError(f"muskingum_routing missing config: {missing}")
        normalized = {
            "k": float(config["k"]),
            "x": float(config["x"]),
            "dt_hours": float(config["dt_hours"]),
        }
        if normalized["k"] <= 0.0:
            raise ValueError("k must be > 0")
        if normalized["x"] < 0.0 or normalized["x"] > 0.5:
            raise ValueError("x must be within [0, 0.5]")
        if normalized["dt_hours"] <= 0.0:
            raise ValueError("dt_hours must be > 0")
        return normalized

    def validate_inputs(self, context: BasePluginContext) -> None:
        super().validate_inputs(context)
        assert isinstance(context, PostPluginContext)
        if not context.simulation_result.snapshots:
            raise ValueError("muskingum_routing requires simulation snapshots")

    def execute(
        self,
        context: BasePluginContext,
        config: dict[str, Any],
    ) -> PluginExecutionResult:
        self.validate_inputs(context)
        assert isinstance(context, PostPluginContext)
        normalized = self.validate_config(config)

        inflow = [float(snapshot.outflow) for snapshot in context.simulation_result.snapshots]
        timestamps = [snapshot.timestamp for snapshot in context.simulation_result.snapshots]
        k = float(normalized["k"])
        x = float(normalized["x"])
        dt = float(normalized["dt_hours"])
        denominator = (2.0 * k * (1.0 - x)) + dt
        c0 = (dt - 2.0 * k * x) / denominator
        c1 = (dt + 2.0 * k * x) / denominator
        c2 = (2.0 * k * (1.0 - x) - dt) / denominator

        downstream = [inflow[0]]
        for index in range(1, len(inflow)):
            downstream.append(float(c0 * inflow[index] + c1 * inflow[index - 1] + c2 * downstream[index - 1]))

        peak_inflow = max(inflow)
        peak_flow = max(downstream)
        peak_index = downstream.index(peak_flow)
        return PluginExecutionResult(
            payload={
                "downstream_flow_series": {
                    "variable": "downstream_flow",
                    "timestamps": [timestamp.isoformat() for timestamp in timestamps],
                    "values": downstream,
                    "unit": "m3/s",
                },
                "peak_flow": peak_flow,
                "peak_time": timestamps[peak_index].isoformat(),
                "attenuation_summary": {
                    "peak_inflow": peak_inflow,
                    "peak_outflow": peak_flow,
                    "peak_reduction": peak_inflow - peak_flow,
                    "peak_reduction_ratio": 0.0 if peak_inflow == 0 else (peak_inflow - peak_flow) / peak_inflow,
                },
            },
            diagnostics={"coefficients": {"c0": c0, "c1": c1, "c2": c2}, "step_count": len(downstream)},
            used_config=normalized,
            warnings=[],
            metadata={
                "plugin_name": self.plugin_name,
                "plugin_kind": self.plugin_kind,
                "stage": self.stage,
            },
        )

    def route(self, *, simulation_result, config: dict[str, Any]) -> PluginExecutionResult:
        """Compatibility adapter for the legacy professional API."""
        return self.execute(PostPluginContext(simulation_result=simulation_result), config)


def register_builtin_plugins(registry: ExecutionPluginRegistry) -> None:
    """Register built-in execution plugins."""
    registry.register(SimpleRainfallRunoffPlugin())
    registry.register(GateReleaseCalculatorPlugin())
    registry.register(MuskingumRoutingPlugin())
