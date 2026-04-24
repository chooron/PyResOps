"""Validation tests for paper-aligned base release modules."""

import pytest

from pyresops.modules import (
    ConstantReleaseModule,
    InflowLinearReleaseModule,
    InflowPiecewiseConstantReleaseModule,
    JointDrivenReleaseModule,
    StorageNonlinearReleaseModule,
    StoragePiecewiseConstantReleaseModule,
)


def test_constant_release_requires_target_release() -> None:
    with pytest.raises(ValueError, match="target_release"):
        ConstantReleaseModule(parameters={})


def test_inflow_linear_release_rejects_negative_slope() -> None:
    with pytest.raises(ValueError, match="slope"):
        InflowLinearReleaseModule(parameters={"slope": -1.0})


def test_inflow_piecewise_constant_release_requires_matching_shape() -> None:
    with pytest.raises(ValueError, match="len\\(breakpoints\\)"):
        InflowPiecewiseConstantReleaseModule(
            parameters={"breakpoints": [1.0, 2.0], "release_values": [1.0, 2.0]}
        )


def test_storage_piecewise_constant_release_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="metric"):
        StoragePiecewiseConstantReleaseModule(
            parameters={
                "metric": "level",
                "breakpoints": [0.5],
                "release_values": [1.0, 2.0],
            }
        )


def test_storage_nonlinear_release_requires_matching_control_points() -> None:
    with pytest.raises(ValueError, match="same length"):
        StorageNonlinearReleaseModule(
            parameters={
                "metric": "storage_ratio",
                "control_points": [0.0, 0.5, 1.0],
                "release_values": [1.0, 2.0],
            }
        )


def test_joint_driven_release_requires_matrix_shape() -> None:
    with pytest.raises(ValueError, match="row count"):
        JointDrivenReleaseModule(
            parameters={
                "storage_metric": "storage_ratio",
                "inflow_breakpoints": [1.0],
                "storage_breakpoints": [0.5],
                "release_matrix": [[1.0, 2.0]],
            }
        )
