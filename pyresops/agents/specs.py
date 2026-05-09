"""Reservoir spec loading for experiment-time agent execution."""

from __future__ import annotations

from pathlib import Path

from pyresops.providers import load_reservoir_bootstrap_from_yaml


DEFAULT_EXPERIMENT_RESERVOIR_CONFIG_PATH = Path("experiments/config/default_reservoir.yaml")


def load_default_experiment_spec():
    """Load the experiment reservoir spec from the canonical YAML file."""

    bootstrap = load_reservoir_bootstrap_from_yaml(DEFAULT_EXPERIMENT_RESERVOIR_CONFIG_PATH)
    return bootstrap.spec
