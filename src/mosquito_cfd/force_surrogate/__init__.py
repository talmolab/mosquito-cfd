"""Force-surrogate prep for the Track B program (see ``docs/force_surrogate/roadmap.md``).

Provides the single source of force/moment-coefficient normalization, a dimensionless
units-sidecar convention, a provenance wrapper that pins the Docker image digest, the
Aedes-anchored kinematic sweep generator (PR2), and the forces-to-tidy-dataset extractor
(PR4: ``build_dataset``/``write_dataset``/``build_run_metadata``).
"""

from mosquito_cfd.force_surrogate.dataset import (
    build_dataset,
    build_run_metadata,
    load_manifest_configs,
    write_dataset,
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
from mosquito_cfd.force_surrogate.runner import (
    Completion,
    ExecResult,
    RunOutcome,
    build_run_command,
    build_wsl_command,
    check_completion,
    run_sweep,
)
from mosquito_cfd.force_surrogate.sidecar import (
    UNITS_VOCABULARY,
    capture_surrogate_run_metadata,
    read_units_sidecar,
    validate_image_digest,
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
    "build_run_metadata",
    "load_manifest_configs",
    "write_dataset",
    "UNITS_VOCABULARY",
    "capture_surrogate_run_metadata",
    "read_units_sidecar",
    "validate_image_digest",
    "write_units_sidecar",
    "build_kinematic_grid",
    "compute_reynolds",
    "derive_run_duration",
    "generate_sweep",
    "render_inputs",
    "select_holdout",
    "Completion",
    "ExecResult",
    "RunOutcome",
    "build_run_command",
    "build_wsl_command",
    "check_completion",
    "run_sweep",
]
