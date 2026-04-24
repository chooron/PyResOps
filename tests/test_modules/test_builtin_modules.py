"""Tests for paper-aligned base release modules."""

from pyresops.modules import (
    ConstantReleaseModule,
    InflowLinearReleaseModule,
    InflowPiecewiseConstantReleaseModule,
    StorageNonlinearReleaseModule,
    StoragePiecewiseConstantReleaseModule,
)


def test_constant_release_info() -> None:
    info = ConstantReleaseModule.get_info()
    assert info.module_type == "constant_release"
    assert "target_release" in info.parameters_schema["properties"]


def test_inflow_linear_release_computes_expected_outflow(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    module = InflowLinearReleaseModule({"slope": 0.5, "intercept": 100.0})
    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
    assert outflow == 4100.0


def test_inflow_piecewise_constant_release_selects_expected_bin(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    module = InflowPiecewiseConstantReleaseModule(
        {"breakpoints": [5000.0, 9000.0], "release_values": [1000.0, 2000.0, 3000.0]}
    )
    assert module.compute_outflow(sample_initial_state, sample_reservoir_spec, 4000.0) == 1000.0
    assert module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0) == 2000.0
    assert module.compute_outflow(sample_initial_state, sample_reservoir_spec, 9500.0) == 3000.0


def test_storage_piecewise_constant_release_uses_storage_ratio(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    module = StoragePiecewiseConstantReleaseModule(
        {
            "metric": "storage_ratio",
            "breakpoints": [0.5, 0.8],
            "release_values": [500.0, 1500.0, 3000.0],
        }
    )
    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
    assert outflow == 1500.0


def test_storage_nonlinear_release_interpolates(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    module = StorageNonlinearReleaseModule(
        {
            "metric": "storage_ratio",
            "control_points": [0.0, 0.5, 1.0],
            "release_values": [500.0, 1500.0, 3500.0],
        }
    )
    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
    assert 1500.0 < outflow < 3500.0
