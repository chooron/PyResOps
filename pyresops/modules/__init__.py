"""Paper-aligned base release modules."""

from .base import BaseOperationModule
from .constant_release import ConstantReleaseModule
from .inflow_linear_release import InflowLinearReleaseModule
from .inflow_piecewise_constant_release import InflowPiecewiseConstantReleaseModule
from .joint_driven_release import JointDrivenReleaseModule
from .registry import (
    ALLOWED_BASE_RELEASE_MODULE_TYPES,
    BASE_RELEASE_MODULE_REGISTRY,
    REMOVED_MODULE_MESSAGE,
    REMOVED_MODULE_TYPES,
    assert_supported_base_release_module_type,
)
from .storage_nonlinear_release import StorageNonlinearReleaseModule
from .storage_piecewise_constant_release import StoragePiecewiseConstantReleaseModule

__all__ = [
    "ALLOWED_BASE_RELEASE_MODULE_TYPES",
    "BASE_RELEASE_MODULE_REGISTRY",
    "BaseOperationModule",
    "ConstantReleaseModule",
    "InflowPiecewiseConstantReleaseModule",
    "InflowLinearReleaseModule",
    "StoragePiecewiseConstantReleaseModule",
    "StorageNonlinearReleaseModule",
    "JointDrivenReleaseModule",
    "REMOVED_MODULE_TYPES",
    "REMOVED_MODULE_MESSAGE",
    "assert_supported_base_release_module_type",
]
