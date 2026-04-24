"""Tests for execution plugin configuration loading."""

from pathlib import Path

from pyresops.providers import load_reservoir_bootstrap_from_yaml


def test_load_execution_plugins_from_yaml(tmp_path: Path) -> None:
    payload = """
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
execution:
  plugins:
    input:
      name: simple_rainfall_runoff
      config:
        runoff_coefficient: 0.6
        lag_steps: 1
    step:
      name: gate_release_calculator
      config:
        discharge_coefficient: 0.8
        gate_width: 8.0
        gate_opening: 0.5
    post:
      name: muskingum_routing
      config:
        k: 3.0
        x: 0.2
        dt_hours: 1.0
"""
    path = tmp_path / "execution.yaml"
    path.write_text(payload, encoding="utf-8")

    bootstrap = load_reservoir_bootstrap_from_yaml(path)

    assert bootstrap.execution is not None
    assert bootstrap.execution.plugins is not None
    assert bootstrap.execution.plugins.input is not None
    assert bootstrap.execution.plugins.input.name == "simple_rainfall_runoff"
    assert bootstrap.execution.plugins.post is not None
    assert bootstrap.execution.plugins.post.config["k"] == 3.0
