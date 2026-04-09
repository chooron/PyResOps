"""Tests for reservoir YAML loading utilities."""

from pathlib import Path

import pytest

from pyresops.config import ReservoirYamlError, load_reservoir_bootstrap_from_yaml


def test_load_structured_yaml(tmp_path: Path) -> None:
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
snapshot:
  level: 165
  inflow: 7000
"""
    path = tmp_path / "res.yaml"
    path.write_text(payload, encoding="utf-8")

    bootstrap = load_reservoir_bootstrap_from_yaml(path)
    assert bootstrap.spec.id == "demo"
    state = bootstrap.create_initial_state()
    assert state.level == 165.0
    assert state.inflow == 7000.0


def test_load_flat_yaml(tmp_path: Path) -> None:
    payload = """
id: flat_demo
name: Flat Demo
dead_level: 150
normal_level: 175
flood_limit_level: 145
design_flood_level: 180
check_flood_level: 185
total_capacity: 39.3
flood_capacity: 22.15
level_storage_curve:
  levels: [135, 145, 155, 165, 175, 185]
  storages: [0, 10, 20, 30, 39.3, 51.6]
discharge_capacity:
  levels: [135, 145, 155, 165, 175, 185]
  max_discharges: [0, 5000, 10000, 15000, 20000, 30000]
"""
    path = tmp_path / "flat.yaml"
    path.write_text(payload, encoding="utf-8")

    bootstrap = load_reservoir_bootstrap_from_yaml(path)
    assert bootstrap.spec.id == "flat_demo"


def test_yaml_error_on_missing_file() -> None:
    with pytest.raises(ReservoirYamlError):
        load_reservoir_bootstrap_from_yaml("missing-file.yaml")
