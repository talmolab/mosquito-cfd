"""Plotfile -> ``FieldSnapshot`` reader: the repository's single Eulerian-box covering-grid read.

``yt`` is imported lazily inside the reader, never at module scope, so importing this module (or
``benchmarks.stress_integral``, which delegates to it) stays cheap.

Code units throughout -- values are returned exactly as the plotfile stores them, with no unit
conversion, unwrapped from yt's ``unyt_array`` to bare FP64 numpy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import numpy as np

#: Short name -> the ``('boxlib', <name>)`` tuple the plotfile stores it under. Covers all eight
#: components a real wing plotfile writes.
CANONICAL_FIELDS: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "u": ("boxlib", "x_velocity"),
        "v": ("boxlib", "y_velocity"),
        "w": ("boxlib", "z_velocity"),
        "gradpx": ("boxlib", "gradpx"),
        "gradpy": ("boxlib", "gradpy"),
        "gradpz": ("boxlib", "gradpz"),
        "density": ("boxlib", "density"),
        "tracer": ("boxlib", "tracer"),
    }
)

#: The six the LEV and control-volume callers require; the legacy adapter's exact set.
DEFAULT_FIELDS: tuple[str, ...] = ("u", "v", "w", "gradpx", "gradpy", "gradpz")


@dataclass(frozen=True)
class PointCloud:
    """Flattened view of a :class:`FieldSnapshot`, the format point-cloud encoders consume.

    Attributes:
        coords: ``(N, 3)`` cell-center coordinates.
        values: ``(N, F)`` field values, column order given by ``field_names``.
        field_names: Column meaning for ``values``.
        cell_volume: ``(N,)`` per-point cell volume. Constant on a uniform grid; it exists so a
            future multi-level reader can vary it without changing this type (CC-F3 is open).
    """

    coords: np.ndarray
    values: np.ndarray
    field_names: tuple[str, ...]
    cell_volume: np.ndarray


@dataclass(frozen=True)
class FieldSnapshot:
    """An axis-aligned region of a single-level AMReX plotfile, in code units.

    Attributes:
        arrays: Field name -> ``(nx, ny, nz)`` FP64 array, indexed ``[ix, iy, iz]``.
        x: Cell-center coordinates along x.
        y: Cell-center coordinates along y.
        z: Cell-center coordinates along z.
        dx: ``(3,)`` per-axis grid spacing.
        time: Physical simulation time of the plotfile (the phase).
        source: Path the snapshot was read from (provenance).
        max_level: The plotfile's AMR level count; always ``0`` today, recorded not inferred.
        field_names: Field order, fixing the ``PointCloud`` column meaning.
    """

    arrays: Mapping[str, np.ndarray]
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    dx: np.ndarray
    time: float
    source: str
    max_level: int
    field_names: tuple[str, ...]

    def to_point_cloud(self) -> PointCloud:
        """Flatten to coordinates and values in C-order over ``(nx, ny, nz)``.

        The ordering is part of the published contract: ``coords`` and ``values`` stay aligned
        across calls, and ``field_names`` fixes which column is which.

        Returns:
            The :class:`PointCloud` view of this snapshot.
        """
        gx, gy, gz = np.meshgrid(self.x, self.y, self.z, indexing="ij")
        coords = np.stack(
            (gx.ravel(order="C"), gy.ravel(order="C"), gz.ravel(order="C")), axis=1
        )
        if self.field_names:
            values = np.stack(
                [self.arrays[name].ravel(order="C") for name in self.field_names],
                axis=1,
            )
        else:
            values = np.empty((coords.shape[0], 0), dtype=np.float64)
        cell_volume = np.full(
            coords.shape[0], float(np.prod(self.dx)), dtype=np.float64
        )
        for arr in (coords, values, cell_volume):
            arr.setflags(write=False)
        return PointCloud(
            coords=coords,
            values=values,
            field_names=self.field_names,
            cell_volume=cell_volume,
        )


def _validate_fields(fields: tuple[str, ...]) -> None:
    unknown = [name for name in fields if name not in CANONICAL_FIELDS]
    if unknown:
        raise ValueError(
            f"unknown field name(s) {unknown}; choose from {sorted(CANONICAL_FIELDS)}"
        )
    seen: set[str] = set()
    duplicates = sorted({n for n in fields if n in seen or seen.add(n)})
    if duplicates:
        # A duplicate desynchronises `arrays` (a dict, which collides) from `field_names`
        # (a tuple, which does not): the point cloud gains a duplicated column and the same
        # field is read once per repetition.
        raise ValueError(
            f"duplicate field name(s) {duplicates} in fields={list(fields)}"
        )


def _validate_halo(halo: int) -> int:
    if isinstance(halo, bool) or not isinstance(halo, (int, np.integer)):
        # Each face truncates independently (int() of i_lo - halo and i_hi + halo), so a
        # fractional halo pads ASYMMETRICALLY -- halo=1.9 gives 2 cells low and 1 high, a
        # wrong answer for anything that differentiates across the pad.
        raise ValueError(f"halo must be an integer, got {halo!r}")
    if halo < 0:
        # A negative halo erodes rather than pads, and can silently yield a zero-cell region
        # indistinguishable from an out-of-domain request.
        raise ValueError(f"halo must be non-negative, got {halo}")
    return int(halo)


def _corner(value, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3,):
        raise ValueError(f"{name} must be a 3-vector, got shape {arr.shape}")
    if np.isnan(arr).any():
        raise ValueError(
            f"{name} contains NaN; use -inf/+inf for 'full extent' along an axis"
        )
    return arr


def read_field_snapshot(
    plotfile_path: str | Path,
    *,
    lo,
    hi,
    halo: int = 0,
    fields: tuple[str, ...] = DEFAULT_FIELDS,
) -> FieldSnapshot:
    """Read an axis-aligned region of a single-level AMReX plotfile.

    Reads the full level-0 covering grid and slices the requested region in memory, padded by
    ``halo`` cells on each side and clamped to the domain. Region semantics are identical to the
    legacy ``benchmarks.stress_integral.extract_eulerian_box``, which delegates here.

    Note that the ``i_hi = min(max(i_hi, i_lo + 1), ddims)`` clamp guarantees at least one cell
    per axis only for regions beginning **inside** the domain: a request at or beyond the upper
    domain edge correctly yields a zero-cell region.

    Args:
        plotfile_path: Path to the plotfile directory (e.g. ``.../plt00100``).
        lo: Physical lower corner ``(x, y, z)``; ``-inf`` means "full extent" on that axis.
        hi: Physical upper corner ``(x, y, z)``; ``+inf`` means "full extent" on that axis.
        halo: Extra cells sliced on every side beyond the requested region.
        fields: Short names to read, from :data:`CANONICAL_FIELDS`.

    Returns:
        The :class:`FieldSnapshot` for the requested region.

    Raises:
        ValueError: If a field name is unknown or absent from the plotfile, if a corner contains
            NaN, if the plotfile is multi-level (the open CC-F3 decision), or if a field is not
            FP64 (the fp32-build guard).
    """
    fields = tuple(fields)
    _validate_fields(fields)
    halo = _validate_halo(halo)
    lo_v = _corner(lo, "lo")
    hi_v = _corner(hi, "hi")

    import yt

    yt.set_log_level("error")
    ds = yt.load(str(plotfile_path))

    if ds.index.max_level != 0:
        raise ValueError(
            f"read_field_snapshot requires a single-level plotfile; "
            f"max_level={ds.index.max_level}. Handling refined levels (interpolate to a uniform "
            f"grid vs. keep a native multi-resolution point cloud) is the open CC-F3 decision -- "
            f"see docs/field_surrogate/roadmap.md. Reading level 0 alone would silently return "
            f"coarse data and discard the refined patches."
        )

    # The on-disk precision is the only place an fp32 build is visible. yt's AMReX frontend
    # allocates output buffers float64 unconditionally and widens the FAB into them, so every
    # array it returns reports float64 even for a genuine single-precision plotfile (verified:
    # ds.index._dtype float32, returned dtype float64, values carrying ~1.9e-07 of truncation).
    # A returned-dtype check can therefore never catch an fp32 build.
    # `_dtype` is private yt API. Defaulting it would re-create the very hole this guard closes
    # -- a silent pass for every plotfile -- so a missing attribute is a hard failure instead.
    if not hasattr(ds.index, "_dtype"):
        raise ValueError(
            "cannot determine the plotfile's on-disk precision: this yt build "
            f"({getattr(yt, '__version__', 'unknown')}) does not expose ds.index._dtype, so the "
            "fp32-build guard cannot run. Refusing rather than silently accepting."
        )
    on_disk = np.dtype(ds.index._dtype)
    if on_disk != np.float64:
        raise ValueError(
            f"plotfile {plotfile_path} stores {on_disk} reals, not float64 (fp32 build?); "
            f"yt would silently widen them to float64"
        )

    requested = [CANONICAL_FIELDS[name] for name in fields]
    present = set(ds.field_list)
    missing = [f for f in requested if f not in present]
    if missing:
        raise ValueError(f"plotfile is missing required fields {missing}")

    dle = np.asarray(ds.domain_left_edge.to_ndarray(), dtype=np.float64)
    dre = np.asarray(ds.domain_right_edge.to_ndarray(), dtype=np.float64)
    ddims = np.asarray(ds.domain_dimensions, dtype=np.int64)
    dx = (dre - dle) / ddims

    lo_c = np.clip(lo_v, dle, dre)
    hi_c = np.clip(hi_v, dle, dre)
    i_lo = np.floor((lo_c - dle) / dx).astype(np.int64) - halo
    i_hi = np.ceil((hi_c - dle) / dx).astype(np.int64) + halo
    i_lo = np.maximum(i_lo, 0)
    i_hi = np.minimum(np.maximum(i_hi, i_lo + 1), ddims)

    cg = ds.covering_grid(
        level=0, left_edge=ds.domain_left_edge, dims=tuple(int(d) for d in ddims)
    )
    sl = tuple(slice(int(a), int(b)) for a, b in zip(i_lo, i_hi))

    arrays: dict[str, np.ndarray] = {}
    for name, field in zip(fields, requested):
        raw = cg[field].to_ndarray()
        if (
            raw.dtype != np.float64
        ):  # defence in depth; the real fp32 guard is on_disk above
            raise ValueError(f"field {field} is {raw.dtype}, not float64")
        # copy=True is load-bearing. np.ascontiguousarray returns the input UNCHANGED when the
        # slice is already C-contiguous -- the full-extent read and any single-axis slab -- and
        # marking such a view non-writable leaves its base reachable and writable, so the array
        # stays mutable through arr.base and a small region pins the whole covering grid alive.
        arr = np.array(raw[sl], dtype=np.float64, order="C", copy=True)
        arr.setflags(write=False)
        arrays[name] = arr

    axes = []
    for axis in range(3):
        centers = dle[axis] + (np.arange(ddims[axis]) + 0.5) * dx[axis]
        cut = np.array(centers[sl[axis]], dtype=np.float64, order="C", copy=True)
        cut.setflags(write=False)
        axes.append(cut)

    dx_out = np.array(dx, dtype=np.float64)
    dx_out.setflags(write=False)

    return FieldSnapshot(
        arrays=MappingProxyType(arrays),
        x=axes[0],
        y=axes[1],
        z=axes[2],
        dx=dx_out,
        time=float(ds.current_time),
        source=str(plotfile_path),
        max_level=int(ds.index.max_level),
        field_names=fields,
    )
