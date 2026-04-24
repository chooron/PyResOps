"""Built-in provider plugins."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..domain.forecast import ForecastBundle, ForecastSeries
from ..domain.policy import PolicyBundle
from ..domain.program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from ..domain.reservoir import ReservoirState
from ..plugins import ExecutionConfig, PluginBundleConfig
from .base import ProviderPluginBase
from .models import (
    DataRequest,
    InitialSnapshotConfig,
    ReservoirBootstrap,
    ReservoirYamlError,
    ScenarioInputBundle,
)


class ReservoirBootstrapYamlProvider(ProviderPluginBase):
    provider_name = "reservoir_bootstrap_yaml"
    target_type = "reservoir_bootstrap"
    supported_sources = ("yaml",)

    def provide(self, request: DataRequest, resolver) -> ReservoirBootstrap:
        if request.locator is None:
            raise ValueError("Reservoir bootstrap YAML provider requires locator")
        return load_reservoir_bootstrap_from_yaml(request.locator)


class ForecastYamlProvider(ProviderPluginBase):
    provider_name = "forecast_yaml"
    target_type = "forecast_bundle"
    supported_sources = ("yaml",)

    def provide(self, request: DataRequest, resolver) -> ForecastBundle:
        path = resolver.resolve_path(request.locator)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return _build_forecast_bundle(payload)


class ForecastCsvProvider(ProviderPluginBase):
    provider_name = "forecast_csv"
    target_type = "forecast_bundle"
    supported_sources = ("csv",)

    def provide(self, request: DataRequest, resolver) -> ForecastBundle:
        import csv

        path = resolver.resolve_path(request.locator)
        variable = str(request.options.get("variable", "inflow"))
        time_column = str(request.options.get("time_column", "timestamp"))
        value_column = str(request.options.get("value_column", variable))
        time_format = request.options.get("time_format")
        unit = str(request.options.get("unit", ""))

        timestamps: list[datetime] = []
        values: list[float] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_timestamp = str(row[time_column]).strip()
                timestamp = (
                    datetime.strptime(raw_timestamp, str(time_format))
                    if time_format
                    else datetime.fromisoformat(raw_timestamp)
                )
                timestamps.append(timestamp)
                values.append(float(row[value_column]))

        return ForecastBundle(
            forecast_time=timestamps[0] if timestamps else datetime.now(),
            series=[
                ForecastSeries(
                    variable=variable,
                    timestamps=timestamps,
                    values=values,
                    unit=unit,
                )
            ],
        )


class DispatchProgramYamlProvider(ProviderPluginBase):
    provider_name = "dispatch_program_yaml"
    target_type = "dispatch_program"
    supported_sources = ("yaml",)

    def provide(self, request: DataRequest, resolver) -> DispatchProgram:
        path = resolver.resolve_path(request.locator)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return _build_dispatch_program(payload)


class ScenarioBundleYamlProvider(ProviderPluginBase):
    provider_name = "scenario_input_bundle_yaml"
    target_type = "scenario_input_bundle"
    supported_sources = ("yaml",)

    def provide(self, request: DataRequest, resolver) -> ScenarioInputBundle:
        path = resolver.resolve_path(request.locator)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("Scenario bundle YAML root must be a mapping")

        base_dir = path.parent
        reservoir_section = payload.get("reservoir")
        if not isinstance(reservoir_section, dict):
            raise ValueError("Scenario bundle requires a 'reservoir' section")
        bootstrap = resolver.ensure(
            DataRequest(
                target_type="reservoir_bootstrap",
                source_hint=str(reservoir_section.get("source", "yaml")),
                locator=str(base_dir / str(reservoir_section["path"])),
            )
        )
        assert isinstance(bootstrap, ReservoirBootstrap)

        snapshot_section = payload.get("snapshot")
        initial_state = (
            bootstrap.create_initial_state()
            if snapshot_section in (None, "bootstrap_default")
            else _build_reservoir_state(snapshot_section, bootstrap=bootstrap)
        )

        forecast_section = payload.get("forecast")
        if not isinstance(forecast_section, dict):
            raise ValueError("Scenario bundle requires a 'forecast' section")
        forecast = resolver.ensure(
            DataRequest(
                target_type="forecast_bundle",
                source_hint=str(forecast_section.get("source", "yaml")),
                locator=str(base_dir / str(forecast_section["path"])),
                options=dict(forecast_section.get("options", {})),
            )
        )
        assert isinstance(forecast, ForecastBundle)

        program_section = payload.get("program")
        if not isinstance(program_section, dict):
            raise ValueError("Scenario bundle requires a 'program' section")
        program = resolver.ensure(
            DataRequest(
                target_type="dispatch_program",
                source_hint=str(program_section.get("source", "yaml")),
                locator=str(base_dir / str(program_section["path"])),
            )
        )
        assert isinstance(program, DispatchProgram)

        policy_payload = payload.get("policy_bundle")
        plugin_payload = payload.get("plugin_bundle")
        return ScenarioInputBundle(
            bootstrap=bootstrap,
            initial_state=initial_state,
            forecast=forecast,
            program=program,
            policy_bundle=None if not isinstance(policy_payload, dict) else PolicyBundle(**policy_payload),
            plugin_bundle=None
            if not isinstance(plugin_payload, dict)
            else PluginBundleConfig(**plugin_payload).model_dump(mode="json"),
            metadata={"source_path": str(path)},
        )


def register_builtin_providers(registry) -> None:
    """Register built-in providers."""
    registry.register(ReservoirBootstrapYamlProvider())
    registry.register(ForecastYamlProvider())
    registry.register(ForecastCsvProvider())
    registry.register(DispatchProgramYamlProvider())
    registry.register(ScenarioBundleYamlProvider())


def load_reservoir_bootstrap_from_yaml(file_path: str | Path) -> ReservoirBootstrap:
    """Load reservoir bootstrap from a YAML file path."""
    path = Path(file_path)
    if not path.exists():
        raise ReservoirYamlError(f"Reservoir YAML not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise ReservoirYamlError("Reservoir YAML root must be a mapping")

    raw_spec = payload.get("reservoir", payload)
    if not isinstance(raw_spec, dict):
        raise ReservoirYamlError("`reservoir` section must be a mapping")

    spec_payload = _normalize_spec_payload(raw_spec)
    try:
        from ..domain.reservoir import ReservoirSpec

        spec = ReservoirSpec(**spec_payload)
    except Exception as exc:
        raise ReservoirYamlError(f"Invalid reservoir spec payload: {exc}") from exc

    raw_snapshot = payload.get("snapshot") or payload.get("initial_snapshot")
    raw_execution = payload.get("execution")
    snapshot = InitialSnapshotConfig(**raw_snapshot) if isinstance(raw_snapshot, dict) else None
    execution = ExecutionConfig(**raw_execution) if isinstance(raw_execution, dict) else None
    return ReservoirBootstrap(spec=spec, snapshot=snapshot, execution=execution)


def _build_forecast_bundle(payload: dict[str, Any]) -> ForecastBundle:
    raw_forecast_time = payload.get("forecast_time")
    forecast_time = (
        datetime.fromisoformat(str(raw_forecast_time))
        if raw_forecast_time is not None
        else datetime.now()
    )
    raw_series = payload.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise ValueError("Forecast YAML requires a non-empty 'series' list")
    series: list[ForecastSeries] = []
    for item in raw_series:
        if not isinstance(item, dict):
            raise ValueError("Forecast series items must be mappings")
        series.append(
            ForecastSeries(
                variable=str(item["variable"]),
                timestamps=[datetime.fromisoformat(str(value)) for value in item["timestamps"]],
                values=[float(value) for value in item["values"]],
                unit=str(item.get("unit", "")),
            )
        )
    return ForecastBundle(
        forecast_time=forecast_time,
        series=series,
        metadata=dict(payload.get("metadata", {})),
    )


def _build_dispatch_program(payload: dict[str, Any]) -> DispatchProgram:
    horizon_payload = payload.get("time_horizon")
    if not isinstance(horizon_payload, dict):
        raise ValueError("Dispatch program YAML requires 'time_horizon'")
    module_payloads = payload.get("module_configs")
    if not isinstance(module_payloads, list) or not module_payloads:
        raise ValueError("Dispatch program YAML requires non-empty 'module_configs'")
    switch_payloads = payload.get("switch_conditions", [])
    return DispatchProgram(
        id=str(payload.get("id", "program_from_yaml")),
        name=str(payload.get("name", "program_from_yaml")),
        time_horizon=TimeHorizon(**horizon_payload),
        module_sequence=[
            ModuleInstance(
                module_type=str(item["module_type"]),
                parameters=dict(item.get("parameters", {})),
                active_period=item.get("active_period"),
                metadata=dict(item.get("metadata", {})),
            )
            for item in module_payloads
        ],
        switch_conditions=[
            SwitchCondition(
                from_module=str(item["from_module"]),
                to_module=str(item["to_module"]),
                condition_type=str(item["condition_type"]),
                parameters=dict(item.get("parameters", {})),
            )
            for item in switch_payloads
        ],
        metadata=dict(payload.get("metadata", {})),
    )


def _build_reservoir_state(
    payload: dict[str, Any],
    *,
    bootstrap: ReservoirBootstrap,
) -> ReservoirState:
    level = float(payload["level"])
    storage = (
        float(payload["storage"])
        if payload.get("storage") is not None
        else float(bootstrap.spec.level_storage_curve.get_storage(level))
    )
    return ReservoirState(
        timestamp=datetime.fromisoformat(str(payload["timestamp"])),
        level=level,
        storage=storage,
        inflow=float(payload["inflow"]),
        outflow=float(payload["outflow"]),
        metadata=dict(payload.get("metadata", {})),
    )


def _normalize_spec_payload(raw_spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize structured spec payload into `ReservoirSpec` fields."""
    normalized = dict(raw_spec)

    levels = normalized.pop("characteristic_levels", None)
    if isinstance(levels, dict):
        normalized.update(levels)

    capacities = normalized.pop("capacities", None)
    if isinstance(capacities, dict):
        normalized.update(capacities)

    curves = normalized.pop("curves", None)
    if isinstance(curves, dict):
        if "level_storage_curve" not in normalized:
            curve_payload = curves.get("level_storage") or curves.get("level_storage_curve")
            if curve_payload is not None:
                normalized["level_storage_curve"] = curve_payload

        if "discharge_capacity" not in normalized:
            discharge_payload = curves.get("discharge_capacity") or curves.get("discharge")
            if discharge_payload is not None:
                normalized["discharge_capacity"] = discharge_payload

    return normalized
