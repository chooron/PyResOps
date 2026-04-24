"""Linear release as a function of inflow."""

from __future__ import annotations

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule, ModuleOptimizationSpec


class InflowLinearReleaseModule(BaseOperationModule):
    """Qout = slope * Qin + intercept."""

    MODULE_TYPE = "inflow_linear_release"
    MODULE_NAME = "Inflow Linear Release"
    MODULE_DESCRIPTION = "Linear release rule driven by inflow."

    def validate_parameters(self) -> None:
        slope = self.parameters.get("slope", self.parameters.get("coefficient", 1.0))
        intercept = self.parameters.get("intercept", self.parameters.get("offset", 0.0))
        self._require_non_negative("slope", float(slope))
        self.parameters["slope"] = float(slope)
        self.parameters["intercept"] = float(intercept)

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        return max(
            0.0,
            float(self.parameters["slope"]) * float(inflow_forecast)
            + float(self.parameters["intercept"]),
        )

    @classmethod
    def get_optimization_spec(cls, *, context: dict[str, float]) -> ModuleOptimizationSpec:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        initial_release = cls._clip_value(
            float(context["initial_release_guess"]),
            lower=min_release,
            upper=max_release,
        )
        span = max_release - min_release
        low_start = cls._clip_value(initial_release - 0.1 * span, lower=min_release, upper=max_release)
        high_start = cls._clip_value(initial_release + 0.1 * span, lower=min_release, upper=max_release)
        ramp_start = (min_release, max_release)
        flat_start = (initial_release, initial_release)
        return ModuleOptimizationSpec(
            solver_kind="local_continuous",
            bounds=((min_release, max_release), (min_release, max_release)),
            initial_guesses=(
                flat_start,
                (low_start, high_start),
                ramp_start,
            ),
            max_iterations=120,
        )

    @classmethod
    def decode_optimization_vector(
        cls,
        vector,
        *,
        context: dict[str, float],
    ) -> dict[str, float]:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        inflow_min = float(context["inflow_min"])
        inflow_max = float(context["inflow_max"])
        low_output = cls._clip_value(float(vector[0]), lower=min_release, upper=max_release)
        high_output = cls._clip_value(float(vector[1]), lower=min_release, upper=max_release)
        if high_output < low_output:
            low_output, high_output = high_output, low_output

        inflow_span = max(inflow_max - inflow_min, 1.0)
        slope = max(0.0, (high_output - low_output) / inflow_span)
        intercept = low_output - slope * inflow_min
        return {
            "slope": round(float(slope), 6),
            "intercept": round(float(intercept), 6),
        }

    @classmethod
    def get_info(cls) -> ModuleInfo:
        return ModuleInfo(
            module_type=cls.MODULE_TYPE,
            name=cls.MODULE_NAME,
            description=cls.MODULE_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "slope": {
                        "type": "number",
                        "minimum": 0,
                        "default": 1.0,
                        "description": "Linear slope applied to inflow.",
                    },
                    "intercept": {
                        "type": "number",
                        "default": 0.0,
                        "description": "Linear intercept applied after slope * inflow.",
                    },
                },
            },
        )
