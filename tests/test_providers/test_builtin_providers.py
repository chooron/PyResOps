"""Tests for the built-in provider layer."""

from __future__ import annotations

from pathlib import Path

from pyresops.domain import DispatchProgram, ForecastBundle
from pyresops.providers import (
    DataRequest,
    ProviderManager,
    ProviderRegistry,
    ReservoirBootstrap,
    ScenarioInputBundle,
    register_builtin_providers,
)


def _build_manager() -> ProviderManager:
    registry = ProviderRegistry()
    register_builtin_providers(registry)
    return ProviderManager(registry)


def test_reservoir_bootstrap_yaml_provider(tmp_path: Path) -> None:
    path = tmp_path / "reservoir.yaml"
    path.write_text(
        """
reservoir:
  id: demo
  name: Demo
  characteristic_levels:
    dead_level: 150
    normal_level: 175
    flood_limit_level: 145
    design_flood_level: 180
    check_flood_level: 185
  capacities:
    total_capacity: 39.3
    flood_capacity: 22.15
  curves:
    level_storage:
      levels: [135, 145, 155, 165, 175, 185]
      storages: [0, 10, 20, 30, 39.3, 51.6]
    discharge_capacity:
      levels: [135, 145, 155, 165, 175, 185]
      max_discharges: [0, 5000, 10000, 15000, 20000, 30000]
snapshot:
  level: 165
  inflow: 7000
        """,
        encoding="utf-8",
    )
    manager = _build_manager()
    result = manager.ensure(
        DataRequest(target_type="reservoir_bootstrap", source_hint="yaml", locator=str(path))
    )
    assert isinstance(result, ReservoirBootstrap)
    assert result.spec.id == "demo"


def test_forecast_csv_provider(tmp_path: Path) -> None:
    path = tmp_path / "forecast.csv"
    path.write_text(
        "timestamp,inflow\n2024-07-01T00:00:00,800\n2024-07-01T01:00:00,900\n",
        encoding="utf-8",
    )
    manager = _build_manager()
    result = manager.ensure(
        DataRequest(
            target_type="forecast_bundle",
            source_hint="csv",
            locator=str(path),
        )
    )
    assert isinstance(result, ForecastBundle)
    assert result.get_series("inflow") is not None
    assert result.get_series("inflow").values == [800.0, 900.0]


def test_dispatch_program_yaml_provider(tmp_path: Path) -> None:
    path = tmp_path / "program.yaml"
    path.write_text(
        """
id: demo_program
name: Demo Program
time_horizon:
  start: "2024-07-01T00:00:00"
  end: "2024-07-01T03:00:00"
  time_step: 3600
module_configs:
  - module_type: constant_release
    parameters:
      target_release: 800.0
        """,
        encoding="utf-8",
    )
    manager = _build_manager()
    result = manager.ensure(
        DataRequest(target_type="dispatch_program", source_hint="yaml", locator=str(path))
    )
    assert isinstance(result, DispatchProgram)
    assert result.name == "Demo Program"
    assert result.module_sequence[0].module_type == "constant_release"


def test_scenario_bundle_yaml_provider(tmp_path: Path) -> None:
    reservoir_path = tmp_path / "reservoir.yaml"
    reservoir_path.write_text(
        """
reservoir:
  id: demo
  name: Demo
  characteristic_levels:
    dead_level: 150
    normal_level: 175
    flood_limit_level: 145
    design_flood_level: 180
    check_flood_level: 185
  capacities:
    total_capacity: 39.3
    flood_capacity: 22.15
  curves:
    level_storage:
      levels: [135, 145, 155, 165, 175, 185]
      storages: [0, 10, 20, 30, 39.3, 51.6]
    discharge_capacity:
      levels: [135, 145, 155, 165, 175, 185]
      max_discharges: [0, 5000, 10000, 15000, 20000, 30000]
snapshot:
  level: 165
  inflow: 7000
        """,
        encoding="utf-8",
    )
    forecast_path = tmp_path / "forecast.yaml"
    forecast_path.write_text(
        """
forecast_time: "2024-07-01T00:00:00"
series:
  - variable: inflow
    timestamps:
      - "2024-07-01T00:00:00"
      - "2024-07-01T01:00:00"
    values: [800, 900]
    unit: "m3/s"
        """,
        encoding="utf-8",
    )
    program_path = tmp_path / "program.yaml"
    program_path.write_text(
        """
id: demo_program
name: Demo Program
time_horizon:
  start: "2024-07-01T00:00:00"
  end: "2024-07-01T01:00:00"
  time_step: 3600
module_configs:
  - module_type: constant_release
    parameters:
      target_release: 800.0
        """,
        encoding="utf-8",
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        f"""
reservoir:
  source: yaml
  path: "{reservoir_path.name}"
snapshot: bootstrap_default
forecast:
  source: yaml
  path: "{forecast_path.name}"
program:
  source: yaml
  path: "{program_path.name}"
plugin_bundle:
  input:
    name: simple_rainfall_runoff
    config:
      runoff_coefficient: 0.6
      lag_steps: 1
        """,
        encoding="utf-8",
    )
    manager = _build_manager()
    result = manager.ensure(
        DataRequest(target_type="scenario_input_bundle", source_hint="yaml", locator=str(scenario_path))
    )
    assert isinstance(result, ScenarioInputBundle)
    assert result.bootstrap.spec.id == "demo"
    assert result.forecast.get_series("inflow") is not None
    assert result.program.id == "demo_program"
