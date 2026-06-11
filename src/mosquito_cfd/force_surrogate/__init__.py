"""Force-surrogate foundation: normalization, units sidecar, and run provenance.

PR1 of the Track B force-surrogate program (see ``docs/force_surrogate/roadmap.md``).
Provides the single source of force-coefficient normalization, a dimensionless units
sidecar convention, and a provenance wrapper that pins the Docker image digest.
"""

from mosquito_cfd.force_surrogate.dataset import (
    build_dataset,
)
from mosquito_cfd.force_surrogate.normalization import (
    ForceCoefficients,
    ForceReference,
    MomentCoefficients,
    MomentReference,
    compute_force_coefficients,
    compute_force_reference,
    compute_moment_coefficient,
    compute_moment_reference,
)
from mosquito_cfd.force_surrogate.sidecar import (
    UNITS_VOCABULARY,
    capture_surrogate_run_metadata,
    read_units_sidecar,
    write_units_sidecar,
)
from mosquito_cfd.force_surrogate.sweep import (
    build_kinematic_grid,
    compute_reynolds,
    derive_run_duration,
    generate_sweep,
    render_inputs,
    select_holdout,
)

__all__ = [
    "ForceCoefficients",
    "ForceReference",
    "MomentCoefficients",
    "MomentReference",
    "compute_force_coefficients",
    "compute_force_reference",
    "compute_moment_coefficient",
    "compute_moment_reference",
    "build_dataset",
    "UNITS_VOCABULARY",
    "capture_surrogate_run_metadata",
    "read_units_sidecar",
    "write_units_sidecar",
    "build_kinematic_grid",
    "compute_reynolds",
    "derive_run_duration",
    "generate_sweep",
    "render_inputs",
    "select_holdout",
]
