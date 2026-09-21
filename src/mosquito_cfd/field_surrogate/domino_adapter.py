"""Emit the DoMINO keys this corpus can honestly fill -- the volume half only.

Imports neither ``physicsnemo`` nor ``torch`` at any scope, so the package stays importable on the
CPU-only CI runner and this change adds no dependency.

**What this adapter does not do, and why it matters (CC-4).** Verified 2026-09-21 against
``NVIDIA/physicsnemo`` ``main`` and the PhysicsNeMo 26.05 API docs:

- Stock DoMINO is a **geometry -> fields** surrogate. Its ``forward()`` consumes geometry and
  sampled point coordinates and *returns* the flow field. So ``volume_fields`` here is a training
  **target**, and is **not an encoder input** -- the Stage-2 roadmap's "DoMINO encoder: field
  snapshot -> latent z" does not describe stock DoMINO. Resolving that is F3's job.
- ``geometry_coordinates``, ``sdf_grid``, ``sdf_nodes``, ``surf_grid``, ``sdf_surf_grid``,
  ``surface_mesh_centers``, ``surface_normals`` and ``surface_areas`` are **not produced here**,
  and **DoMINO cannot train without them**. They need the wing's pose at the snapshot's instant:
  either the plotfile's IB markers (which the synthetic CI fixture does not carry, so it could not
  be tested cluster-free) or a regenerated planform, whose phase convention must match the
  solver's exactly. Both belong with F3, where the encoder that consumes them exists. They are
  **absent from the returned dict rather than zero-filled**, because a zero-filled ``sdf_nodes``
  yields a dict that looks trainable and silently is not.
- IAMReX plotfiles carry **no pressure field** -- only ``gradpx``/``gradpy``/``gradpz``. Our
  ``volume_fields`` is therefore velocity plus pressure-*gradient*, not the
  velocity/pressure/turbulent-viscosity set DoMINO's own examples assume.

No batch dimension is added: DoMINO's datapipe adds one itself, and a second would be wrong.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from mosquito_cfd.field_surrogate.snapshot import FieldSnapshot

#: The DoMINO keys this corpus can honestly supply.
VOLUME_HALF_KEYS: tuple[str, ...] = (
    "volume_mesh_centers",
    "volume_fields",
    "grid",
    "global_params_values",
    "global_params_reference",
)

#: The DoMINO keys deliberately NOT produced here (F3's, see the module docstring).
GEOMETRY_HALF_KEYS: tuple[str, ...] = (
    "geometry_coordinates",
    "sdf_grid",
    "sdf_nodes",
    "surf_grid",
    "sdf_surf_grid",
    "surface_mesh_centers",
    "surface_normals",
    "surface_areas",
)


def to_domino_volume(
    snapshot: FieldSnapshot,
    *,
    global_params_values: Sequence[float],
    global_params_reference: Sequence[float],
) -> dict[str, np.ndarray]:
    """Convert a snapshot into DoMINO's volume-half input arrays.

    Global parameters are caller-supplied rather than derived here: DoMINO treats them as
    per-case physical conditions against normalization baselines, and choosing the baseline is a
    training-time policy that belongs to F3, not to the reader.

    Args:
        snapshot: The field snapshot to convert.
        global_params_values: This case's parameter values (e.g. the kinematics from
            ``FieldCorpus.global_params``).
        global_params_reference: Normalization baselines, same length and order.

    Returns:
        A dict with exactly :data:`VOLUME_HALF_KEYS` and **no** leading batch dimension. The
        :data:`GEOMETRY_HALF_KEYS` are absent; see the module docstring for why.

    Raises:
        ValueError: If ``global_params_values`` and ``global_params_reference`` differ in length.
    """
    values = np.asarray(global_params_values, dtype=np.float64).reshape(-1, 1)
    reference = np.asarray(global_params_reference, dtype=np.float64).reshape(-1, 1)
    if values.shape != reference.shape:
        raise ValueError(
            f"global_params_values and global_params_reference must have the same length; "
            f"got {values.shape[0]} and {reference.shape[0]}"
        )

    cloud = snapshot.to_point_cloud()
    gx, gy, gz = np.meshgrid(snapshot.x, snapshot.y, snapshot.z, indexing="ij")

    return {
        "volume_mesh_centers": cloud.coords,
        "volume_fields": cloud.values,
        "grid": np.stack((gx, gy, gz), axis=-1),
        "global_params_values": values,
        "global_params_reference": reference,
    }
