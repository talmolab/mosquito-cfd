"""Frozen pre-refactor copy of ``extract_eulerian_box`` -- the differential oracle for PR B.

Copied **byte-for-byte** from ``src/mosquito_cfd/benchmarks/stress_integral.py`` as of commit
86c729e1a98dbb46562b9f3c31a662a93f1fa910
(the last commit to touch that file before the delegation refactor in
``add-field-surrogate-reader``), renamed only at the ``def`` line.

This exists because comparing the refactored wrapper against a re-pack of
``read_field_snapshot`` is **tautological** -- after the refactor the wrapper *is* that re-pack,
so such a test compares an implementation to itself and proves nothing about behavioural
continuity, which is the entire claim of the change's ``design.md`` D1/D10.

Do not "fix", reformat, or modernize this file. Its value is that it is the old behaviour.
"""

from __future__ import annotations

import numpy as np

_REQUIRED_FIELDS = (
    ("boxlib", "x_velocity"),
    ("boxlib", "y_velocity"),
    ("boxlib", "z_velocity"),
    ("boxlib", "gradpx"),
    ("boxlib", "gradpy"),
    ("boxlib", "gradpz"),
)


def legacy_extract_eulerian_box(
    plotfile_path: str,
    *,
    lo: tuple[float, float, float],
    hi: tuple[float, float, float],
    halo: int = 0,
) -> dict[str, np.ndarray]:
    """Read velocity + pressure-gradient over an axis-aligned region of an AMReX plotfile.

    Isolates all yt / plotfile / cluster I/O from the numpy core. Reads the full level-0 covering
    grid (exact for the single-level sphere runs; ~0.2 GB for 4.2M cells, and free of yt's
    ghost-cell boundary check on interior sub-regions) and slices the requested region in memory,
    padded by ``halo`` cells on each side. Fields are read by their ``('boxlib', name)`` tuple
    identifiers; all are asserted present. Arrays are unwrapped from yt's ``unyt_array`` to bare
    ``float64`` numpy (yt may return ``float32`` for an fp32 build — the assert doubles as the
    fp64-build check). Code units throughout (no conversion).

    Args:
        plotfile_path: Path to the plotfile directory (e.g. ``.../plt10000``).
        lo: Physical lower corner ``(x, y, z)`` (``-inf`` allowed for "full extent").
        hi: Physical upper corner ``(x, y, z)`` (``+inf`` allowed for "full extent").
        halo: Extra cells sliced on every side beyond the requested region.

    Returns:
        Dict with FP64 arrays ``u, v, w, gradpx, gradpy, gradpz`` (indexed ``[ix, iy, iz]``),
        cell-center coordinate arrays ``x, y, z``, and ``dx`` (per-axis spacing).
    """
    import yt

    yt.set_log_level("error")
    ds = yt.load(str(plotfile_path))
    if ds.index.max_level != 0:
        raise ValueError(
            f"extract_eulerian_box requires a single-level plotfile; "
            f"max_level={ds.index.max_level}"
        )
    present = set(ds.field_list)
    missing = [f for f in _REQUIRED_FIELDS if f not in present]
    if missing:
        raise ValueError(f"plotfile is missing required fields {missing}")

    dle = np.asarray(ds.domain_left_edge.to_ndarray(), dtype=np.float64)
    dre = np.asarray(ds.domain_right_edge.to_ndarray(), dtype=np.float64)
    ddims = np.asarray(ds.domain_dimensions, dtype=np.int64)
    dx = (dre - dle) / ddims

    # Clamp to the domain (accepts +/-inf for "full extent" along an axis).
    lo_c = np.clip(np.asarray(lo, dtype=np.float64), dle, dre)
    hi_c = np.clip(np.asarray(hi, dtype=np.float64), dle, dre)
    i_lo = np.floor((lo_c - dle) / dx).astype(np.int64) - halo
    i_hi = np.ceil((hi_c - dle) / dx).astype(np.int64) + halo
    i_lo = np.maximum(i_lo, 0)
    i_hi = np.minimum(np.maximum(i_hi, i_lo + 1), ddims)  # >=1 cell/axis, within domain

    cg = ds.covering_grid(
        level=0, left_edge=ds.domain_left_edge, dims=tuple(int(d) for d in ddims)
    )
    sl = tuple(slice(int(a), int(b)) for a, b in zip(i_lo, i_hi))
    names = ("u", "v", "w", "gradpx", "gradpy", "gradpz")
    out: dict[str, np.ndarray] = {}
    for key, field in zip(names, _REQUIRED_FIELDS):
        raw = cg[field].to_ndarray()
        if raw.dtype != np.float64:  # check BEFORE casting, so an fp32 build is caught
            raise ValueError(f"field {field} is {raw.dtype}, not float64 (fp32 build?)")
        out[key] = np.asarray(raw, dtype=np.float64)[sl]
    out["x"] = (dle[0] + (np.arange(ddims[0]) + 0.5) * dx[0])[sl[0]]
    out["y"] = (dle[1] + (np.arange(ddims[1]) + 0.5) * dx[1])[sl[1]]
    out["z"] = (dle[2] + (np.arange(ddims[2]) + 0.5) * dx[2])[sl[2]]
    out["dx"] = dx
    # Physical simulation time of the plotfile (the phase). Additive: existing callers ignore it; the
    # T3b LEV composition uses it to guard that coarse and medium are compared at the same phase.
    out["current_time"] = float(ds.current_time)
    return out
