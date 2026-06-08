"""Force-surrogate foundation: normalization, units sidecar, and run provenance.

PR1 of the Track B force-surrogate program (see ``docs/force_surrogate/roadmap.md``).
Provides the single source of force-coefficient normalization, a dimensionless units
sidecar convention, and a provenance wrapper that pins the Docker image digest.
"""

from mosquito_cfd.force_surrogate.normalization import (
    ForceCoefficients,
    ForceReference,
    compute_force_coefficients,
    compute_force_reference,
)
from mosquito_cfd.force_surrogate.sidecar import (
    UNITS_VOCABULARY,
    capture_surrogate_run_metadata,
    read_units_sidecar,
    write_units_sidecar,
)

__all__ = [
    "ForceCoefficients",
    "ForceReference",
    "compute_force_coefficients",
    "compute_force_reference",
    "UNITS_VOCABULARY",
    "capture_surrogate_run_metadata",
    "read_units_sidecar",
    "write_units_sidecar",
]
