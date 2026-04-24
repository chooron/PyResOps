"""Shared registry for allowed base release modules."""

from __future__ import annotations

from .constant_release import ConstantReleaseModule
from .inflow_linear_release import InflowLinearReleaseModule
from .inflow_piecewise_constant_release import InflowPiecewiseConstantReleaseModule
from .joint_driven_release import JointDrivenReleaseModule
from .storage_nonlinear_release import StorageNonlinearReleaseModule
from .storage_piecewise_constant_release import StoragePiecewiseConstantReleaseModule

BASE_RELEASE_MODULE_REGISTRY = {
    ConstantReleaseModule.MODULE_TYPE: ConstantReleaseModule,
    InflowPiecewiseConstantReleaseModule.MODULE_TYPE: InflowPiecewiseConstantReleaseModule,
    InflowLinearReleaseModule.MODULE_TYPE: InflowLinearReleaseModule,
    StoragePiecewiseConstantReleaseModule.MODULE_TYPE: StoragePiecewiseConstantReleaseModule,
    StorageNonlinearReleaseModule.MODULE_TYPE: StorageNonlinearReleaseModule,
    JointDrivenReleaseModule.MODULE_TYPE: JointDrivenReleaseModule,
}

ALLOWED_BASE_RELEASE_MODULE_TYPES = frozenset(BASE_RELEASE_MODULE_REGISTRY)

REMOVED_MODULE_TYPES = frozenset(
    {
        "flexible_release",
        "level_tracking",
        "external_constraint",
        "inflow_driven",
        "storage_driven",
        "combined_driven",
    }
)

REMOVED_MODULE_MESSAGE = (
    "flexible_release has been fully removed, and the old mixed module types "
    "level_tracking, external_constraint, inflow_driven, storage_driven, and "
    "combined_driven are no longer valid base release modules. Use one of the "
    "six paper-aligned base release module types instead: constant_release, "
    "inflow_piecewise_constant_release, inflow_linear_release, "
    "storage_piecewise_constant_release, storage_nonlinear_release, "
    "joint_driven_release."
)


def assert_supported_base_release_module_type(module_type: str) -> None:
    if module_type in ALLOWED_BASE_RELEASE_MODULE_TYPES:
        return
    if module_type in REMOVED_MODULE_TYPES:
        raise ValueError(REMOVED_MODULE_MESSAGE)
    raise ValueError(
        f"Unsupported base release module type: {module_type}. "
        f"Allowed types: {sorted(ALLOWED_BASE_RELEASE_MODULE_TYPES)}"
    )
