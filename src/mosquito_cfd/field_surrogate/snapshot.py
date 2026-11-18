"""Plotfile -> ``FieldSnapshot`` reader: the repository's single Eulerian-box covering-grid read.

``yt`` is imported lazily inside the reader, never at module scope, so importing this module
stays cheap for callers that never read a plotfile.

Code units throughout -- values are returned exactly as the plotfile stores them, with no unit
conversion, unwrapped from yt's ``unyt_array`` to bare FP64 numpy.
"""

from __future__ import annotations

import dataclasses
import gc
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import numpy as np

from mosquito_cfd._messages import plain_repr

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
            While constant it is a read-only, zero-stride broadcast of a read-only 0-d array
            (8 bytes, not ``N``), which differs from a dense array in four ways: it cannot be
            made writable, it is not C-contiguous for ``N > 1``, its ``base`` is the 0-d array,
            and pickling it produces a dense, writable copy. Buffer-protocol consumers that need
            contiguous memory (``memoryview(...).cast``, ``np.frombuffer``, a ``double[::1]``
            argument) therefore fail on it: call ``np.ascontiguousarray`` first. Its ``nbytes``
            still reports ``8 * N``, computed from the shape, though 8 bytes are allocated.
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
        source: Path the snapshot was read from, as ``Path(path).absolute().as_posix()``: absolute,
            forward-slashed, ``..`` kept as written, no symlink or mapped-drive resolution. A
            per-host locator, not a cross-host identity -- the same plotfile read from Windows,
            WSL and the cluster is spelled differently; ``(config_id, step, run_id)`` identifies
            it across hosts.
        max_level: The plotfile's AMR level count; always ``0`` today, recorded not inferred.
        field_names: Field order, fixing the ``PointCloud`` column meaning.
        config_id: Corpus config the snapshot belongs to. ``None`` from a bare
            :func:`read_field_snapshot`; set only by ``FieldCorpus.snapshot``.
        step: Timestep of the plotfile, as a Python ``int``; ``None`` unless set by
            ``FieldCorpus.snapshot``.
        git_commit: Full 40-character mosquito-cfd **repository** commit the pod recorded (baked
            into the image at build, ``git.source == "docker-image-build-arg"``) -- not the
            solver's commit, which is pinned by the image digest. Copied from the run's own
            ``run_metadata.json``; ``None`` unless set by ``FieldCorpus.snapshot``.
        docker_image: Digest-pinned image reference (``<repo>@sha256:<64 hex>``) the run used,
            copied from the run's ``run_metadata.json``; ``None`` unless set by
            ``FieldCorpus.snapshot``. Never inferred or fabricated.
        run_id: The pod's identifier for this run attempt, copied from ``run_metadata.json``;
            ``None`` unless set by ``FieldCorpus.snapshot``. ``(config_id, step, run_id)``
            identifies a corpus snapshot across hosts and corpora -- every fine-corpus run shares
            one commit and one image, so those two pin the build, not the run.

    A snapshot survives ``pickle`` (every protocol), ``multiprocessing``'s ``ForkingPickler``,
    ``copy.copy`` and ``copy.deepcopy``, so a ``DataLoader`` worker can return one. On receipt its
    arrays are re-frozen and own their data again, whatever the transport did to them: protocols
    2-4 hand large arrays back writable over the pickle's bytes, protocol 5 as views, deepcopy as
    writable copies. Restoring that costs one extra copy of each field array on receipt. With
    ``batch_size >= 1``, torch's ``default_collate`` cannot batch snapshots: pass a ``collate_fn``
    or convert to arrays first.

    The generated ``==`` compares numpy arrays, so it can raise on two distinct snapshots; compare
    fields explicitly.
    """

    def __reduce__(self):
        """Pickle as a plain-dict state rebuilt by :func:`_rebuild_field_snapshot` (#151)."""
        named = [*(f"arrays[{n!r}]" for n in self.arrays), "x", "y", "z", "dx"]
        values = [*self.arrays.values(), self.x, self.y, self.z, self.dx]
        for name, arr in zip(named, values, strict=True):
            if np.asarray(arr).dtype != np.float64:
                # Refused here, at pickling/copying time, rather than cast on some transports and
                # not others: the reader never produces such an array, and the project refuses
                # fp32 data rather than widening it (harden-field-reader-pre-f3 D8.3).
                raise ValueError(
                    f"cannot pickle or copy a FieldSnapshot whose {name} is "
                    f"{np.asarray(arr).dtype}, not native float64"
                )
        state = {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}
        # MappingProxyType cannot be pickled; a plain dict in field order can.
        state["arrays"] = {name: self.arrays[name] for name in self.arrays}
        return _rebuild_field_snapshot, (state,)

    arrays: Mapping[str, np.ndarray]
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    dx: np.ndarray
    time: float
    source: str
    max_level: int
    field_names: tuple[str, ...]
    config_id: str | None = None
    step: int | None = None
    git_commit: str | None = None
    docker_image: str | None = None
    run_id: str | None = None

    def to_point_cloud(self) -> PointCloud:
        """Flatten to coordinates and values in C-order over ``(nx, ny, nz)``.

        The ordering is part of the published contract: ``coords`` and ``values`` stay aligned
        across calls, and ``field_names`` fixes which column is which.

        The peak allocation is ``coords`` and ``values`` coexisting: the meshgrid temporaries
        are freed once ``coords`` is built, and ``cell_volume`` is a zero-stride broadcast (see
        :class:`PointCloud`; ``np.ascontiguousarray`` gives a dense copy).

        Returns:
            The :class:`PointCloud` view of this snapshot.
        """
        gx, gy, gz = np.meshgrid(self.x, self.y, self.z, indexing="ij")
        coords = np.stack(
            (gx.ravel(order="C"), gy.ravel(order="C"), gz.ravel(order="C")), axis=1
        )
        # Three N-element temporaries; freed before `values` is built, so they never coexist
        # with it (improve-field-reader-perf-memory D6).
        del gx, gy, gz
        if self.field_names:
            values = np.stack(
                [self.arrays[name].ravel(order="C") for name in self.field_names],
                axis=1,
            )
        else:
            values = np.empty((coords.shape[0], 0), dtype=np.float64)
        for arr in (coords, values):
            arr.setflags(write=False)
        volume = np.array(float(np.prod(self.dx)), dtype=np.float64)
        volume.setflags(write=False)
        # broadcast_to returns a read-only view; over a read-only base it can never be made
        # writable, so the one shared value cannot be changed through any row.
        cell_volume = np.broadcast_to(volume, (coords.shape[0],))
        return PointCloud(
            coords=coords,
            values=values,
            field_names=self.field_names,
            cell_volume=cell_volume,
        )


def _refreeze(arr: np.ndarray) -> np.ndarray:
    """Restore the snapshot array invariant -- read-only, owning, reader's layout -- on receipt."""
    if arr.size == 0:
        # The reader allocates zero-size arrays with np.empty (all-zero strides); a pickle hands
        # them back with C strides. Rebuild them the reader's way (harden-field-reader-pre-f3 D1).
        arr = np.empty(arr.shape, dtype=np.float64)
    elif arr.base is not None or arr.flags.writeable or not arr.flags.c_contiguous:
        # Protocols 2-4 return large arrays over the pickle's bytes, protocol 5 as a view of its
        # buffer: copy so the array owns its data (`base is None`, the spec's invariant). A
        # writable array may be the caller's own (copy.copy shares it), so it is copied rather
        # than frozen in place; a non-C layout is normalized on every transport alike (D8.3).
        arr = np.array(arr, dtype=np.float64, order="C", copy=True)
    arr.setflags(write=False)
    return arr


def _rebuild_field_snapshot(state: dict) -> FieldSnapshot:
    """Unpickle target of :meth:`FieldSnapshot.__reduce__`.

    Module-level so pickle can import it. Goes through the constructor, so a field added later is
    carried (``__reduce__`` enumerates ``dataclasses.fields``) rather than silently defaulted.
    """
    state = dict(state)
    state["arrays"] = MappingProxyType(
        {name: _refreeze(arr) for name, arr in state["arrays"].items()}
    )
    for axis in ("x", "y", "z", "dx"):
        state[axis] = _refreeze(state[axis])
    state["time"] = float(state["time"])
    state["max_level"] = int(state["max_level"])
    if state.get("step") is not None:
        state["step"] = int(state["step"])
    return FieldSnapshot(**state)


def _validate_fields(fields: tuple[str, ...]) -> None:
    unknown = [name for name in fields if name not in CANONICAL_FIELDS]
    if unknown:
        raise ValueError(
            f"unknown field name(s) {unknown}; choose from {sorted(CANONICAL_FIELDS)}"
        )
    duplicates = sorted({n for n in fields if fields.count(n) > 1})
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
        raise ValueError(f"halo must be an integer, got {plain_repr(halo)}")
    if halo < 0:
        # A negative halo erodes rather than pads, and can silently yield a zero-cell region
        # indistinguishable from an out-of-domain request.
        raise ValueError(f"halo must be non-negative, got {halo}")
    return int(halo)


def _corner(value, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3,):
        # The pre-refactor adapter broadcast a scalar, so `lo=-np.inf` meant "full extent"; name
        # the replacement rather than leaving the caller to guess.
        full = "(-inf,)*3" if name == "lo" else "(inf,)*3"
        raise ValueError(
            f"{name} must be a 3-vector (x, y, z), got shape {arr.shape}; "
            f"for full extent pass {full}"
        )
    if np.isnan(arr).any():
        raise ValueError(
            f"{name} contains NaN; use -inf/+inf for 'full extent' along an axis"
        )
    return arr


def _check_not_inverted(lo: np.ndarray, hi: np.ndarray) -> None:
    # Compared on the RAW corners, not the padded indices: with halo >= 1 a slightly inverted
    # request pads back into a non-empty range, which an index check would let through. Strict
    # `>`: lo == hi is the documented zero-width point query. NaN never reaches here (_corner).
    # Values go through float() -- numpy 2's repr would print np.float64(4.0).
    inverted = [
        f"axis {axis}: lo={float(lo[i])} > hi={float(hi[i])}"
        for i, axis in enumerate(("x", "y", "z"))
        if lo[i] > hi[i]
    ]
    if inverted:
        # The legacy adapter returned a small region here (one cell at halo 0, up to 2*halo + 1
        # otherwise), hiding swapped corners or a negative margin in centre +/- margin
        # (harden-field-corpus-requests D1).
        raise ValueError("inverted region request (lo > hi): " + "; ".join(inverted))


def _validate_request(
    lo, hi, halo, fields
) -> tuple[np.ndarray, np.ndarray, int, tuple[str, ...]]:
    """Every argument check of :func:`read_field_snapshot`, in order, with no I/O.

    Shared with ``FieldCorpus.snapshot``, which runs it before touching the corpus, so an argument
    error is reported as such whatever the corpus's state (harden-field-reader-pre-f3 D4).

    Returns:
        ``(lo, hi, halo, fields)`` normalized: FP64 corners, an ``int`` halo, a ``tuple`` of names.
    """
    if isinstance(fields, (str, bytes)):
        # tuple("gradpx") is six one-letter names, and tuple("uvw") silently reads u, v, w.
        raise ValueError(
            f"fields must be a sequence of field names, not a bare "
            f"{type(fields).__name__}: got {fields!r}; did you mean {(fields,)!r}?"
        )
    fields = tuple(fields)
    _validate_fields(fields)
    halo = _validate_halo(halo)
    lo_v = _corner(lo, "lo")
    hi_v = _corner(hi, "hi")
    _check_not_inverted(lo_v, hi_v)
    return lo_v, hi_v, halo, fields


def _check_plotfile_dir(path: Path) -> None:
    """Refuse a path that is not a plotfile directory, before ``yt`` is imported.

    Without this, a run directory or an empty directory surfaces as yt's ~40-line format-sniffing
    dump (#113). Two ``stat``s; both follow symlinks, and any other ``OSError`` propagates.
    """
    if not path.is_dir():
        if path.exists():
            raise NotADirectoryError(
                f"plotfile path is not a directory: {path}; a plotfile is a pltNNNNN "
                f"directory containing a Header file"
            )
        raise FileNotFoundError(f"plotfile directory does not exist: {path}")
    if not (path / "Header").is_file():
        raise FileNotFoundError(
            f"no Header file in {path}: not an AMReX plotfile directory (a run directory "
            f"instead of a pltNNNNN, or a plotfile still being written)"
        )


def _region_bounds(
    lo: np.ndarray,
    hi: np.ndarray,
    halo: int,
    *,
    dle: np.ndarray,
    dre: np.ndarray,
    ddims: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-axis cell index bounds ``[i_lo, i_hi)`` for a physical request ("halo is reach").

    Pads the request by ``halo`` cells first, then keeps the part of the padded range that lies
    inside the domain. The corners are clipped only to one reach beyond the domain, which removes
    ``+/-inf`` and bounds the arithmetic without changing the result, except on a degenerate grid
    whose cells are narrower than the coordinate ULP (design.md D1).
    """
    dx = (dre - dle) / ddims
    margin = (halo + 1) * dx
    lo_c = np.clip(lo, dle - margin, dre + margin)
    hi_c = np.clip(hi, dle - margin, dre + margin)
    i_lo = np.floor((lo_c - dle) / dx).astype(np.int64) - halo
    i_hi = np.ceil((hi_c - dle) / dx).astype(np.int64) + halo
    # An empty or inverted padded range becomes the single cell at its start. Applied BEFORE the
    # domain intersection, so it can never add a cell outside the padded request. Through the
    # public reader only a zero-width request (lo == hi, e.g. a point on a cell face, where floor
    # and ceil agree) reaches this floor -- inverted requests are rejected upstream
    # (harden-field-corpus-requests D1). The parity sweep still feeds this helper inverted
    # triples, so the floor is load-bearing for legacy parity too: do not remove it.
    i_hi = np.maximum(i_hi, i_lo + 1)
    i_lo = np.clip(i_lo, 0, ddims)
    i_hi = np.clip(i_hi, i_lo, ddims)
    return i_lo, i_hi


def read_field_snapshot(
    plotfile_path: str | Path,
    *,
    lo,
    hi,
    halo: int = 0,
    fields: tuple[str, ...] = DEFAULT_FIELDS,
) -> FieldSnapshot:
    """Read an axis-aligned region of a single-level AMReX plotfile.

    Reads the full level-0 covering grid and slices the requested region in memory, except for a
    region with zero cells on some axis: that builds no covering grid and reads no field, after
    every plotfile guard has run, and returns empty arrays equal to the full read's. The request
    is padded by ``halo`` cells on each side, and the part of the padded request inside the
    domain is kept ("halo is reach"): a request up to ``halo`` cells outside the domain returns
    the in-domain cells it reaches, and one farther out returns zero cells on that axis. A
    zero-width request inside the domain yields one cell; a point exactly on the upper domain
    edge yields none, since cells cover the half-open ``[domain_left_edge, domain_right_edge)``.
    The edge cases are exact when the cell spacing is exactly representable (every corpus deck);
    on other grids float rounding at a face can move an edge point by one cell, as in legacy.

    Returned arrays are read-only against accidental writes, not tamper-proof: numpy lets the
    owner call ``setflags(write=True)``. Copy an array before modifying it.

    Memory: each field is copied out of yt's covering-grid cache and dropped from it before the
    next is read, so at most one full-domain field is cached at a time. Before returning a
    snapshot, the reader drops its yt references and runs a full ``gc.collect()``, so no yt
    object -- and no cached field -- outlives a successful call, and the returned snapshot
    references no yt object. A read that raises skips this; its yt objects wait for the next
    collection.

    That collection is process-wide. It runs even if the caller has disabled automatic GC
    (``gc.isenabled()`` is left as it was), it may run unrelated finalizers, and its cost grows
    with every tracked object in the calling process, not with the plotfile (design.md D4 of
    improve-field-reader-perf-memory has the measurements). A long-lived caller with a large
    heap, such as a DataLoader worker, should call ``gc.freeze()`` once after setup: frozen
    objects are not scanned, and in a forked worker that also avoids touching the inherited
    parent heap.

    This matches the pre-refactor ``benchmarks.stress_integral.extract_eulerian_box`` (frozen
    in ``tests/fixtures/legacy_extract_eulerian_box.py``; the current one delegates here)
    whenever ``lo <= hi``, ``lo <= domain_right_edge`` and ``hi > domain_left_edge`` on every
    axis. Outside that, the pre-refactor adapter clamps the corners onto the domain edge
    *before* padding and so returns edge cells however far away the request is; this reader
    never returns more cells there, and returns a sub-range of the pre-refactor cells. An
    inverted request (``lo > hi`` on any axis) raises, where the pre-refactor adapter returned a
    small region built from the padded indices.

    Args:
        plotfile_path: Path to the plotfile directory (e.g. ``.../plt00100``).
        lo: Physical lower corner ``(x, y, z)``; ``-inf`` means "full extent" on that axis.
        hi: Physical upper corner ``(x, y, z)``; ``+inf`` means "full extent" on that axis.
        halo: Extra cells sliced on every side beyond the requested region.
        fields: Short names to read, from :data:`CANONICAL_FIELDS`.

    Returns:
        The :class:`FieldSnapshot` for the requested region.

    Raises:
        ValueError: If ``fields`` is a bare ``str``/``bytes`` rather than a sequence of names, if
            a field name is unknown or absent from the plotfile, if a corner contains
            NaN, if ``lo > hi`` on any axis (checked before ``yt`` is imported), if the plotfile
            is multi-level (the open CC-F3 decision), or if a field is not FP64 (the fp32-build
            guard).
        FileNotFoundError: If ``plotfile_path`` does not exist, or is a directory without a
            ``Header`` file (checked after the argument checks, before ``yt`` is imported).
        NotADirectoryError: If ``plotfile_path`` exists but is not a directory.
    """
    lo_v, hi_v, halo, fields = _validate_request(lo, hi, halo, fields)
    _check_plotfile_dir(Path(plotfile_path))

    import yt

    # yt logs an INFO line on every dataset load (domain extent, field list, etc.) that would
    # otherwise spam stdout on every snapshot read in a per-frame loop (flow_video) or a training
    # DataLoader (F3). This only raises yt's logging threshold; genuine errors still raise
    # exceptions regardless of log level, so no failure mode is silenced by this call. It is a
    # process-global side effect, inherited from the pre-refactor adapter and kept deliberately
    # (#113).
    yt.set_log_level("error")
    ds = yt.load(str(plotfile_path))

    if ds.index.max_level != 0:
        raise ValueError(
            f"a single-level plotfile is required; {plotfile_path} has "
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
    # Compare the FORMAT, not the dtype object: np.dtype('>f8') != np.float64 on a
    # little-endian host, yet big-endian doubles are bit-exactly valid FP64 and yt emits
    # that descriptor for the other standard AMReX layout. An equality check here falsely
    # rejects such a plotfile -- and blames an "fp32 build" the user does not have.
    if on_disk.kind != "f" or on_disk.itemsize != 8:
        raise ValueError(
            f"plotfile {plotfile_path} stores {on_disk.itemsize}-byte "
            f"{on_disk.kind!r}-kind reals ({on_disk}), not 8-byte floats; yt would silently "
            f"widen them to float64"
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

    i_lo, i_hi = _region_bounds(lo_v, hi_v, halo, dle=dle, dre=dre, ddims=ddims)
    sl = tuple(slice(int(a), int(b)) for a, b in zip(i_lo, i_hi))

    arrays: dict[str, np.ndarray] = {}
    if np.any(i_hi == i_lo):
        # Zero cells on some axis: every slice of the covering grid would be empty, so building
        # it -- a full read of every requested field -- buys nothing (#112 item 5). Reached only
        # after every plotfile guard above, so a request the reader refuses is still refused;
        # only the loop's redundant per-field dtype re-check is skipped (the on-disk precision
        # guard above is the real one).
        # A fresh array is exactly what the full read's copy of an empty slice is: owning,
        # C-ordered, with the same shape and strides (improve-field-reader-perf-memory D5).
        shape = tuple(int(b - a) for a, b in zip(i_lo, i_hi))
        for name in fields:
            empty = np.empty(shape, dtype=np.float64)
            empty.setflags(write=False)
            arrays[name] = empty
    else:
        cg = ds.covering_grid(
            level=0, left_edge=ds.domain_left_edge, dims=tuple(int(d) for d in ddims)
        )
        for name, field in zip(fields, requested):
            # `.d` is a plain-ndarray VIEW of yt's cached buffer. unyt's to_ndarray() is
            # np.array(self) -- a transient full-domain copy, made only to be sliced and copied
            # again below. Skipping it saves an allocation and a copy per field; it does not
            # lower the measured peak, which yt's own read sets (improve-field-reader-perf-memory
            # D4).
            raw = cg[field].d
            if (
                raw.dtype != np.float64
            ):  # defence in depth; the real fp32 guard is on_disk above
                raise ValueError(f"field {field} is {raw.dtype}, not float64")
            # copy=True is load-bearing. np.ascontiguousarray returns the input UNCHANGED when
            # the slice is already C-contiguous -- the full-extent read and any single-axis
            # slab -- and `raw` is a view of yt's cache, so the result would alias that cache,
            # stay writable through arr.base, and keep the whole field alive for a small region
            # (measured ~5x over-retention for an x-slab at 128-cubed).
            arr = np.array(raw[sl], dtype=np.float64, order="C", copy=True)
            arr.setflags(write=False)
            arrays[name] = arr
            # The copy is the only reference this reader keeps. yt caches every field read
            # through a covering grid in cg.field_data, so without this all requested
            # full-domain buffers are held at once (#120); dropped here, at most one is
            # (improve-field-reader-perf-memory D4). `raw` is a view that would keep the
            # cached buffer alive, so it goes first.
            del raw
            cg.field_data.pop(field, None)
        cg.clear_data()
        # The grid holds the dataset only through a weakref.proxy, but sits in a cycle of its
        # own: drop it before the collection below.
        del cg

    axes = []
    for axis in range(3):
        centers = dle[axis] + (np.arange(ddims[axis]) + 0.5) * dx[axis]
        cut = np.array(centers[sl[axis]], dtype=np.float64, order="C", copy=True)
        cut.setflags(write=False)
        axes.append(cut)

    dx_out = np.array(dx, dtype=np.float64)
    dx_out.setflags(write=False)

    time = float(ds.current_time)
    max_level = int(ds.index.max_level)
    # yt's dataset, index, field-info and covering-grid objects form reference cycles, which
    # reference counting cannot free. With automatic GC enabled they are promoted to the oldest
    # generation during the read itself, so a young-generation collect (gc.collect(0) or (1))
    # frees none of them, and each read's cycle -- with any field still cached in it -- would
    # wait for Python's next full collection (measured on CPython 3.11). It frees only
    # unreachable objects. Its cost scales with the caller's tracked objects, not with this
    # read; the docstring says so and points to gc.freeze() (improve-field-reader-perf-memory
    # D4 has the numbers). Both paths -- the full read and the zero-cell one -- reach this
    # teardown.
    del ds
    gc.collect()

    return FieldSnapshot(
        arrays=MappingProxyType(arrays),
        x=axes[0],
        y=axes[1],
        z=axes[2],
        dx=dx_out,
        time=time,
        # absolute(), not resolve(): no I/O, `..` kept, and no rewrite of a mapped drive to its
        # UNC form (harden-field-reader-pre-f3 D3).
        source=Path(plotfile_path).absolute().as_posix(),
        max_level=max_level,
        field_names=fields,
    )
