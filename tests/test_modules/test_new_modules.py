"""Tests for joint-driven release and registry-facing metadata."""

from pyresops.modules import (
    ALLOWED_BASE_RELEASE_MODULE_TYPES,
    JointDrivenReleaseModule,
    StorageNonlinearReleaseModule,
)


def test_joint_driven_release_uses_both_axes(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    module = JointDrivenReleaseModule(
        {
            "storage_metric": "storage_ratio",
            "inflow_breakpoints": [5000.0, 9000.0],
            "storage_breakpoints": [0.6, 0.85],
            "release_matrix": [
                [500.0, 1000.0, 1500.0],
                [2000.0, 2500.0, 3000.0],
                [3500.0, 4000.0, 4500.0],
            ],
        }
    )
    low_inflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 4000.0)
    high_inflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 9500.0)
    assert low_inflow != high_inflow


def test_registry_contains_only_paper_aligned_types() -> None:
    assert ALLOWED_BASE_RELEASE_MODULE_TYPES == frozenset(
        {
            "constant_release",
            "inflow_piecewise_constant_release",
            "inflow_linear_release",
            "storage_piecewise_constant_release",
            "storage_nonlinear_release",
            "joint_driven_release",
        }
    )


def test_storage_nonlinear_info_uses_new_module_type() -> None:
    info = StorageNonlinearReleaseModule.get_info()
    assert info.module_type == "storage_nonlinear_release"
