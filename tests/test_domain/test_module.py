"""Domain-facing module tests."""

import pytest

from pyresops.modules import (
    ConstantReleaseModule,
    InflowLinearReleaseModule,
    StoragePiecewiseConstantReleaseModule,
)


def test_constant_release_module(sample_reservoir_spec, sample_initial_state):
    module = ConstantReleaseModule(parameters={"target_release": 5000.0})
    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
    assert outflow == pytest.approx(5000.0)


def test_inflow_linear_release_module(sample_reservoir_spec, sample_initial_state):
    module = InflowLinearReleaseModule(parameters={"slope": 1.2})
    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
    assert outflow == pytest.approx(9600.0)


def test_storage_piecewise_constant_release_module(sample_reservoir_spec, sample_initial_state):
    module = StoragePiecewiseConstantReleaseModule(
        {
            "metric": "storage_ratio",
            "breakpoints": [0.3, 0.8],
            "release_values": [3000.0, 5000.0, 7000.0],
        }
    )
    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
    assert outflow == 5000.0
