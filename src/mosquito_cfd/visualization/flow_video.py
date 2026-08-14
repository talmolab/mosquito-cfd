"""Generalized CFD-field video builder: wake-slice, combined-3d, lev-3d, zvelocity-3d.

OpenSpec change ``add-visualization-tooling`` (Phase 2). Collapses 5 hardcoded vault scripts
(``make_t3c_fine_wake_video.py``, ``make_t3c_fine_combined_3d.py``, ``make_t3c_fine_lev_3d.py``,
``make_t3c_fine_zvelocity_3d.py``, ``make_field_capture_s45_f115_p60_wake.py``) into one function
parameterized by ``field_mode`` and either a named sweep config or explicit
center/hinge/kinematics overrides (`design.md` D3).

Follows `design.md` D6's pure-render-vs-plotfile-adapter split: :func:`render_lev_frame` and
:func:`render_velocity_slice_frame` are plain-numpy, unit-tested against synthetic fields with no
plotfile/yt dependency; the ``requires_plotfile``-gated seam is isolated to the frame-loading
helpers that call :func:`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box`.

``scipy``, ``scikit-image``, and ``imageio_ffmpeg`` are imported lazily, inside the specific
functions that need them (never at module top) -- this module must stay importable without the
optional ``viz`` dependency group installed (`design.md` D2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from mosquito_cfd.benchmarks.lev import q_criterion, vorticity_magnitude
from mosquito_cfd.force_surrogate.sidecar import (
    capture_surrogate_run_metadata,
    validate_image_digest,
)
from mosquito_cfd.force_surrogate.train import write_json
from mosquito_cfd.geometry.vertex_io import read_vertex_file
from mosquito_cfd.visualization.wing_render import (
    leading_edge_mask,
    resolve_kinematics_kwargs,
    transform_markers,
    wing_outline,
)

FIELD_MODES: tuple[str, ...] = ("wake-slice", "combined-3d", "lev-3d", "zvelocity-3d")

# Empirically-tuned defaults from the T3c-fine benchmark video (`design.md` D4) -- documented,
# CLI-overridable constants, never auto-computed.
DEFAULT_Q_THRESHOLD = 300.0
DEFAULT_VORT_VMIN = 40.0
DEFAULT_VORT_VMAX = 250.0
# Isotropic near-field box half-width for lev-3d (not a `design.md` D4 constant -- D4 covers only
# Q_THRESHOLD/VORT_VMIN/VMAX). Generous relative to the vault script's own asymmetric
# BOX_LO=(1,0,1)/BOX_HI=(7,4,7) around center=(4,2,4) (margins (3,2,3), not (3,3,3)); an isotropic
# 3.0 is a deliberate simplification for arbitrary configs, not a literal reproduction of that
# tuning -- safe because extract_eulerian_box clips an over-wide request to the domain and
# _draw_lev positions the isosurface from the box's own returned coordinates (not this nominal
# value), so a clamped box is a smaller field of view, never a misaligned one.
DEFAULT_BOX_MARGIN = 3.0
DEFAULT_FPS = 4

# Minimum isosurface-worthy cell count above q_threshold (matches the vault script's own
# skip-if-empty guard) -- below this there is nothing coherent to mesh.
_MIN_CELLS_ABOVE_THRESHOLD = 10

# Vertical viewing window (+/-) around the velocity-slice plane for combined-3d/zvelocity-3d,
# matching the vault scripts' own z_level +/- 2 window. Without an explicit z-limit, mplot3d's
# per-frame autoscale fits tightly to whatever's plotted (a near-flat slice plus a wing lifted
# only WING_Z_LIFT above it), collapsing the whole scene into an unreadable sliver at the bottom
# of the axes -- a real rendering bug found by visually inspecting a rendered frame, not caught
# by any file-exists/non-zero-size test.
_Z_VIEW_MARGIN = 2.0
# Oblique viewing angle (matches the vault scripts' own view_init) -- mplot3d resets to the
# default (elev=30) on every ax.clear(), so this must be re-applied every frame, not just once.
_VIEW_ELEV = 28
_VIEW_AZIM = -60

_WING_COLOR = "#111111"
_COLOR_LEADING = "#C53030"
_COLOR_TRAILING = "#2D3748"
# Rendering-only vertical offset lifting the wing outline/markers above the velocity-slice plane
# in combined-3d/zvelocity-3d (mplot3d does not z-sort plot_surface against other collections
# reliably -- matches the vault scripts' own WING_Z_LIFT). Not applied to lev-3d, which has no
# slice plane to lift above. No physical meaning.
_WING_Z_LIFT = 0.6


def _validate_field_mode(field_mode: str) -> None:
    if field_mode not in FIELD_MODES:
        raise ValueError(f"field_mode must be one of {FIELD_MODES}, got {field_mode!r}")


def render_velocity_slice_frame(
    field: ArrayLike, dx: ArrayLike, vmin: float, vmax: float
) -> NDArray[np.float64]:
    """RGBA colormap (``RdBu_r``) of a 2-D velocity slice, clipped to ``[vmin, vmax]``.

    Serves both ``wake-slice`` (x-velocity) and ``zvelocity-3d`` (z-velocity) field modes -- the
    color-mapping math is identical; only the field array and colorbar range passed by the caller
    differ. ``dx`` is accepted (not used in the color computation, which is spacing-independent)
    for interface parity with :func:`render_lev_frame`'s spacing-aware signature and to validate
    that the caller's grid spacing is well-formed.

    Args:
        field: 2-D velocity field.
        dx: Grid spacing for this slice's two axes -- a scalar or a ``(dx0, dx1)`` pair.
        vmin: Colorbar lower bound.
        vmax: Colorbar upper bound.

    Returns:
        An RGBA float array, same leading shape as ``field`` plus a trailing size-4 axis, values
        in ``[0, 1]``.

    Raises:
        ValueError: If ``field`` is not 2-D or contains non-finite values, ``dx`` is not a finite
            positive scalar or 2-vector, or ``vmin >= vmax``.
    """
    field_arr = np.asarray(field, dtype=np.float64)
    if field_arr.ndim != 2:
        raise ValueError(f"field must be 2-D, got ndim {field_arr.ndim}")
    if not np.isfinite(field_arr).all():
        raise ValueError("field must be finite (no NaN/inf)")
    dx_arr = np.atleast_1d(np.asarray(dx, dtype=np.float64))
    if dx_arr.ndim != 1 or dx_arr.size not in (1, 2):
        raise ValueError(
            f"dx must be a scalar or a length-2 (dx0, dx1) sequence, got shape {dx_arr.shape}"
        )
    if not np.isfinite(dx_arr).all() or (dx_arr <= 0).any():
        raise ValueError(f"dx must be finite and positive, got {dx!r}")
    if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmin >= vmax:
        raise ValueError(
            f"vmin must be < vmax and both finite; got vmin={vmin}, vmax={vmax}"
        )

    import matplotlib
    import matplotlib.colors as mcolors

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    return matplotlib.colormaps["RdBu_r"](norm(field_arr))


def render_lev_frame(
    u: ArrayLike,
    v: ArrayLike,
    w: ArrayLike,
    dx: ArrayLike,
    q_threshold: float,
    vort_vmin: float,
    vort_vmax: float,
) -> dict[str, NDArray[np.float64]] | None:
    """Q-criterion isosurface (marching cubes) colored by vorticity magnitude.

    Mirrors the vault LEV script's ``load_q_isosurface``: extracts the ``q_threshold`` isosurface
    of the Q-criterion field via ``skimage.measure.marching_cubes``, then colors each triangular
    face by the local vorticity magnitude (trilinearly sampled at the isosurface vertices),
    normalized to ``[vort_vmin, vort_vmax]``.

    Lazily imports ``skimage.measure`` and ``scipy.ndimage.map_coordinates``.

    Args:
        u: x-velocity component, a 3-D array.
        v: y-velocity component (same shape as ``u``).
        w: z-velocity component (same shape as ``u``).
        dx: Grid spacing -- a scalar or a ``(dx, dy, dz)`` triple (per
            :func:`mosquito_cfd.benchmarks.lev.q_criterion`'s own convention).
        q_threshold: Isosurface level.
        vort_vmin: Vorticity-magnitude colorbar lower bound.
        vort_vmax: Vorticity-magnitude colorbar upper bound.

    Returns:
        ``None`` if fewer than 10 cells exceed ``q_threshold`` (nothing coherent to mesh --
        mirrors the vault script's own skip-if-empty guard). Otherwise a dict with
        ``"triangles"`` (shape ``(F, 3, 3)``, physical vertex coordinates relative to the input
        field's own local index origin -- the caller adds any domain offset) and ``"facecolors"``
        (shape ``(F, 4)`` RGBA, ``plasma`` colormap normalized to ``[vort_vmin, vort_vmax]``).

    Raises:
        ValueError: If ``u``/``v``/``w``/``dx`` fail :func:`mosquito_cfd.benchmarks.lev.q_criterion`'s
            own validation.
    """
    q = q_criterion(u, v, w, dx)
    n_above = int((q > q_threshold).sum())
    # marching_cubes requires `level` strictly within (q.min(), q.max()) to have any surface to
    # extract -- a threshold at/below the field's min (e.g. a small, near-uniformly-saturated box)
    # has n_above >= 10 but no actual crossing boundary, and skimage raises its own unwrapped
    # "Surface level must be within volume data range" ValueError. Both "too few cells above" and
    # "no real crossing boundary" are the same "nothing coherent to mesh" outcome for the caller.
    if n_above < _MIN_CELLS_ABOVE_THRESHOLD or not (q.min() < q_threshold < q.max()):
        return None

    from scipy.ndimage import map_coordinates
    from skimage import measure

    verts_idx, faces, _, _ = measure.marching_cubes(q, level=q_threshold)
    vort = vorticity_magnitude(u, v, w, dx)
    vort_at_verts = map_coordinates(vort, verts_idx.T, order=1, mode="nearest")
    vort_at_faces = vort_at_verts[faces].mean(axis=1)

    dx_arr = np.atleast_1d(np.asarray(dx, dtype=np.float64))
    dx_triple = np.full(3, float(dx_arr[0])) if dx_arr.size == 1 else dx_arr
    triangles = (verts_idx * dx_triple)[faces]

    import matplotlib
    import matplotlib.colors as mcolors

    norm = mcolors.Normalize(vmin=vort_vmin, vmax=vort_vmax, clip=True)
    facecolors = matplotlib.colormaps["plasma"](norm(vort_at_faces))
    return {"triangles": triangles, "facecolors": facecolors}


def _draw_wing_scene(
    ax,
    *,
    ref_markers: NDArray[np.float64],
    outline_ref: NDArray[np.float64],
    is_leading: NDArray[np.bool_],
    hinge_arr: NDArray[np.float64],
    phi: float,
    alpha: float,
    theta: float,
    z_lift: float = 0.0,
) -> None:
    """Draw the rotated wing outline + leading/trailing-edge markers + hinge on a 3-D axes.

    ``is_leading`` must be computed on the *local* (pre-``center``-offset) marker coordinates --
    :func:`mosquito_cfd.visualization.wing_render.leading_edge_mask`'s ``x >= 0`` convention
    assumes ``x=0`` is the chord centerline, which only holds before ``center``'s (generally
    nonzero) x-offset is added.
    """
    rot_outline = transform_markers(outline_ref, hinge_arr, phi, alpha, theta)
    closed = np.vstack([rot_outline, rot_outline[:1]])
    ax.plot(
        closed[:, 0],
        closed[:, 1],
        closed[:, 2] + z_lift,
        color=_WING_COLOR,
        lw=1.5,
        zorder=20,
    )
    rot_markers = transform_markers(ref_markers, hinge_arr, phi, alpha, theta)
    for mask, color in ((is_leading, _COLOR_LEADING), (~is_leading, _COLOR_TRAILING)):
        ax.scatter(
            rot_markers[mask, 0],
            rot_markers[mask, 1],
            rot_markers[mask, 2] + z_lift,
            s=5.0,
            c=color,
            alpha=1.0,
            zorder=21,
            depthshade=False,
        )
    ax.scatter(
        [hinge_arr[0]],
        [hinge_arr[1]],
        [hinge_arr[2] + z_lift],
        color=_WING_COLOR,
        s=100,
        marker="o",
        zorder=22,
        depthshade=False,
        edgecolor="white",
        linewidth=1.0,
    )


def _euler_angles(t: float, kwargs: dict[str, Any]) -> tuple[float, float, float]:
    from mosquito_cfd.benchmarks.wing_kinematics import euler_angles

    return euler_angles(
        t,
        frequency=kwargs["frequency_fstar"],
        stroke_amp_rad=np.radians(kwargs["stroke_amp_deg"]),
        pitch_amp_rad=np.radians(kwargs["pitch_amp_deg"]),
    )


def _plotfile_frames(plotfile_dir: str | Path) -> list[Path]:
    plotfile_dir = Path(plotfile_dir)
    frames = sorted(plotfile_dir.glob("plt?????"))
    if not frames:
        raise ValueError(
            f"no plotfiles found under {plotfile_dir} (expected plt##### dirs)"
        )
    return frames


def _near_field_box(
    plt_path: Path, *, center: NDArray[np.float64], box_margin: float
) -> dict[str, Any]:
    """Extract an isotropic ``center +/- box_margin`` box (``lev-3d``'s near-field region)."""
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    lo = tuple(float(c) for c in (center - box_margin))
    hi = tuple(float(c) for c in (center + box_margin))
    return extract_eulerian_box(str(plt_path), lo=lo, hi=hi)


def _box_origin(box: dict[str, Any]) -> NDArray[np.float64]:
    """The physical position of local index ``(0, 0, 0)`` in an ``extract_eulerian_box`` result.

    Reads the box's OWN returned coordinate arrays, not a caller's nominal ``lo``/``hi`` request
    -- ``extract_eulerian_box`` clips an over-wide request to the domain, so a near-field box
    whose nominal extent runs past a domain boundary has an actual physical origin that differs
    from the unclamped request. Using the nominal request instead would silently misposition
    anything placed via fractional local-index coordinates (e.g. :func:`render_lev_frame`'s
    isosurface triangles).

    Args:
        box: A dict as returned by
            :func:`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` (must contain
            ``"x"``, ``"y"``, ``"z"`` cell-center coordinate arrays).

    Returns:
        The ``(x, y, z)`` physical position of index ``(0, 0, 0)``.
    """
    return np.array([box["x"][0], box["y"][0], box["z"][0]])


def _lev_axis_limits(
    box: dict[str, Any],
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Fixed 3-D axis limits for ``lev-3d``, from the near-field box's own coordinate range.

    Using the box's own bounds -- not mplot3d's per-frame autoscale-to-plotted-data -- keeps the
    view stable across frames even as the isosurface's shape and position change frame to frame.
    Without this, the (stationary) hinge marker appears to jump around the scene as the axes
    silently rescale to fit whatever isosurface geometry happens to be present in that one frame.

    Args:
        box: A dict as returned by :func:`_near_field_box` (must contain ``"x"``, ``"y"``, ``"z"``
            coordinate arrays).

    Returns:
        ``(xlim, ylim, zlim)``, each a ``(lo, hi)`` tuple.
    """
    return (
        (float(box["x"].min()), float(box["x"].max())),
        (float(box["y"].min()), float(box["y"].max())),
        (float(box["z"].min()), float(box["z"].max())),
    )


def _velocity_slice_axis_limits(
    box: dict[str, Any], z_level: float, z_margin: float = _Z_VIEW_MARGIN
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Fixed 3-D axis limits for ``combined-3d``/``zvelocity-3d``.

    ``x``/``y`` span the full domain slice; ``z`` is a generous ``+/- z_margin`` window around
    the slice height so the wing (lifted only ``_WING_Z_LIFT`` above the plane) stays visible,
    instead of mplot3d's autoscale collapsing the whole scene down to the ``~_WING_Z_LIFT``-wide
    sliver that is actually plotted (the slice itself has essentially zero z-extent).

    Args:
        box: A dict as returned by :func:`_full_domain_box`.
        z_level: The slice's physical z height.
        z_margin: Half-width of the z viewing window around ``z_level``.

    Returns:
        ``(xlim, ylim, zlim)``, each a ``(lo, hi)`` tuple.
    """
    return (
        (float(box["x"].min()), float(box["x"].max())),
        (float(box["y"].min()), float(box["y"].max())),
        (z_level - z_margin, z_level + z_margin),
    )


def _full_domain_box(plt_path: Path) -> dict[str, Any]:
    """Extract the full domain (2-D slice modes pick their own z-index afterward)."""
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    inf = float("inf")
    return extract_eulerian_box(
        str(plt_path), lo=(-inf, -inf, -inf), hi=(inf, inf, inf)
    )


def build_flow_video(
    *,
    plotfile_dir: str | Path,
    field_mode: str,
    vertex_path: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
    label: str,
    config_name: str | None = None,
    corpus_dir: str | Path | None = None,
    center: ArrayLike | None = None,
    hinge: ArrayLike | None = None,
    stroke_amp_deg: float | None = None,
    pitch_amp_deg: float | None = None,
    frequency_fstar: float | None = None,
    q_threshold: float = DEFAULT_Q_THRESHOLD,
    vort_vmin: float = DEFAULT_VORT_VMIN,
    vort_vmax: float = DEFAULT_VORT_VMAX,
    box_margin: float = DEFAULT_BOX_MARGIN,
    fps: int = DEFAULT_FPS,
) -> dict[str, Any]:
    """Render one of the 4 generalized CFD-field videos and write the provenance triple.

    Args:
        plotfile_dir: Directory containing ``plt#####`` plotfile subdirectories.
        field_mode: One of ``"wake-slice"``, ``"combined-3d"``, ``"lev-3d"``, ``"zvelocity-3d"``.
        vertex_path: Path to the ``.vertex`` marker file (used by every mode except
            ``wake-slice``, which draws only a hinge marker, matching the vault wake script).
        out_dir: Output directory.
        docker_image_digest: Pinned ``sha256:`` image digest (mutable tags rejected, CC-1).
        timestamp: Caller-supplied ISO-8601 timestamp (CC-1).
        label: Output filename label -- writes ``<label>_flow_<field_mode>.mp4`` (`design.md` D5).
        config_name: Optional sweep config name; resolves center/hinge/kinematics from its deck
            (requires ``corpus_dir``). See :func:`mosquito_cfd.visualization.wing_render.resolve_kinematics_kwargs`.
        corpus_dir: Sweep corpus directory; required together with ``config_name``.
        center: Optional explicit wing-centre override (takes precedence over the config's deck).
        hinge: Optional explicit hinge override.
        stroke_amp_deg: Optional explicit stroke-amplitude override [deg].
        pitch_amp_deg: Optional explicit pitch-amplitude override [deg].
        frequency_fstar: Optional explicit flap-frequency override.
        q_threshold: Q-criterion isosurface level (``lev-3d`` only). Default ``300.0``
            (`design.md` D4).
        vort_vmin: Vorticity-magnitude colorbar lower bound (``lev-3d`` only). Default ``40.0``.
        vort_vmax: Vorticity-magnitude colorbar upper bound (``lev-3d`` only). Default ``250.0``.
        box_margin: Isotropic half-width of the near-field extraction box around ``center``
            (``lev-3d`` only). Default ``3.0``.
        fps: Output video frame rate.

    Returns:
        The ``capture_surrogate_run_metadata`` dict written to
        ``<label>_flow_<field_mode>_run_metadata.json``.

    Raises:
        ValueError: If ``docker_image_digest`` is a mutable tag, ``field_mode`` is not one of the
            4 valid modes, ``fps`` is not positive, no plotfiles are found under
            ``plotfile_dir``, or the center/hinge/kinematics parameters cannot be fully resolved
            (see :func:`mosquito_cfd.visualization.wing_render.resolve_kinematics_kwargs`).
    """
    validate_image_digest(docker_image_digest)  # fail-fast before any I/O
    _validate_field_mode(field_mode)
    if fps <= 0:
        # Caught here, before any Figure is created, rather than surfacing as an unguarded
        # ZeroDivisionError from `int(1000 / fps)` after a Figure already exists (which would
        # leak it -- the same class of bug PR1's review found in comparison_figure.py).
        raise ValueError(f"fps must be positive, got {fps}")

    kin_kwargs = resolve_kinematics_kwargs(
        config_name=config_name,
        corpus_dir=corpus_dir,
        center=center,
        hinge=hinge,
        stroke_amp_deg=stroke_amp_deg,
        pitch_amp_deg=pitch_amp_deg,
        frequency_fstar=frequency_fstar,
    )
    center_arr = np.asarray(kin_kwargs["center"], dtype=np.float64)
    hinge_arr = np.asarray(kin_kwargs["hinge"], dtype=np.float64)

    plot_dirs = _plotfile_frames(plotfile_dir)

    needs_wing = field_mode != "wake-slice"
    ref_markers = outline_ref = is_leading = None
    if needs_wing:
        local_markers = read_vertex_file(str(vertex_path))
        ref_markers = local_markers + center_arr
        outline_ref = wing_outline(local_markers) + center_arr
        is_leading = leading_edge_mask(local_markers)

    import imageio_ffmpeg
    import matplotlib

    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    is_3d = field_mode != "wake-slice"
    if is_3d:
        fig = plt.figure(figsize=(10, 9), facecolor="white")
        ax = fig.add_axes([0.03, 0.05, 0.86, 0.88], projection="3d")
    else:
        fig, ax = plt.subplots(figsize=(9, 8), facecolor="white")

    def _draw_lev(plt_path: Path) -> tuple[float, tuple]:
        box = _near_field_box(plt_path, center=center_arr, box_margin=box_margin)
        frame = render_lev_frame(
            box["u"],
            box["v"],
            box["w"],
            box["dx"],
            q_threshold=q_threshold,
            vort_vmin=vort_vmin,
            vort_vmax=vort_vmax,
        )
        if frame is not None:
            from mpl_toolkits.mplot3d.art3d import Poly3DCollection

            triangles = frame["triangles"] + _box_origin(box)
            mesh = Poly3DCollection(
                triangles, facecolors=frame["facecolors"], edgecolor="none", zorder=1
            )
            ax.add_collection3d(mesh)
        return float(box["current_time"]), _lev_axis_limits(box)

    def _draw_velocity_slice(plt_path: Path) -> tuple[float, tuple | None]:
        box = _full_domain_box(plt_path)
        z_idx = len(box["z"]) // 2
        field_name = "w" if field_mode == "zvelocity-3d" else "u"
        slice_2d = box[field_name][:, :, z_idx].T
        absmax = float(np.abs(slice_2d).max()) or 1.0
        facecolors = render_velocity_slice_frame(
            slice_2d, box["dx"][:2], vmin=-absmax, vmax=absmax
        )
        if field_mode == "wake-slice":
            extent = [
                float(box["x"].min()),
                float(box["x"].max()),
                float(box["y"].min()),
                float(box["y"].max()),
            ]
            ax.imshow(facecolors, origin="lower", extent=extent, aspect="equal")
            ax.scatter(
                [hinge_arr[0]],
                [hinge_arr[1]],
                color="black",
                s=80,
                marker="^",
                zorder=10,
            )
            return float(box["current_time"]), None

        x_mesh, y_mesh = np.meshgrid(box["x"], box["y"])
        z_level = float(box["z"][z_idx])
        z_plane = np.full_like(x_mesh, z_level)
        ax.plot_surface(
            x_mesh,
            y_mesh,
            z_plane,
            facecolors=facecolors,
            rstride=2,
            cstride=2,
            linewidth=0,
            antialiased=False,
            shade=False,
            zorder=1,
        )
        return float(box["current_time"]), _velocity_slice_axis_limits(box, z_level)

    def draw(plt_path: Path) -> None:
        ax.clear()
        t_sim, limits = (
            _draw_lev(plt_path)
            if field_mode == "lev-3d"
            else _draw_velocity_slice(plt_path)
        )

        if needs_wing:
            phi, alpha, theta = _euler_angles(t_sim, kin_kwargs)
            _draw_wing_scene(
                ax,
                ref_markers=ref_markers,
                outline_ref=outline_ref,
                is_leading=is_leading,
                hinge_arr=hinge_arr,
                phi=phi,
                alpha=alpha,
                theta=theta,
                z_lift=_WING_Z_LIFT if field_mode != "lev-3d" else 0.0,
            )
        ax.set_title(f"{label}: {field_mode}, t = {t_sim:.4f}")

        if is_3d:
            # Re-applied every frame: ax.clear() resets both the view angle and axis limits to
            # mplot3d's defaults, and autoscale-to-plotted-data is exactly what made the axes
            # jump around frame to frame before this fix (see _lev_axis_limits/
            # _velocity_slice_axis_limits docstrings).
            ax.view_init(elev=_VIEW_ELEV, azim=_VIEW_AZIM)
            ax.set_xlim(*limits[0])
            ax.set_ylim(*limits[1])
            ax.set_zlim(*limits[2])

    anim = FuncAnimation(fig, draw, frames=plot_dirs, interval=int(1000 / fps))
    writer = FFMpegWriter(fps=fps, bitrate=3000)

    out_dir = Path(out_dir)
    try:
        # mkdir inside the try: a non-creatable out_dir (e.g. a file already at that path) must
        # not leave the Figure created above unclosed (the same leak class PR1's review found in
        # comparison_figure.py).
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = out_dir / f"{label}_flow_{field_mode}.mp4"
        anim.save(mp4_path, writer=writer, dpi=110)
    finally:
        plt.close(fig)

    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        # No single-file `inputs_file` hash: the input is a directory of plotfiles, not one file
        # (unlike wing_phase_diagnostic's single vertex_path) -- the plotfile directory path and
        # frame count are recorded in `extra` instead.
        timestamp=timestamp,
        extra={
            "field_mode": field_mode,
            "label": label,
            "plotfile_dir": str(plotfile_dir),
            "n_frames": len(plot_dirs),
            "vertex_path": str(vertex_path),
            "config_name": config_name,
            "corpus_dir": str(corpus_dir) if corpus_dir is not None else None,
            # The resolved center/hinge/kinematics actually used to render this video -- without
            # this, a viewer of `<label>_flow_<field_mode>.mp4` has no way to tell after the fact
            # which hinge (as-run buggy vs. corrected-for-display, `design.md` D3) it was rendered
            # with, since `label`/`field_mode` alone don't disambiguate the two hinge-caveat cases.
            "center": list(kin_kwargs["center"]),
            "hinge": list(kin_kwargs["hinge"]),
            "stroke_amp_deg": kin_kwargs["stroke_amp_deg"],
            "pitch_amp_deg": kin_kwargs["pitch_amp_deg"],
            "frequency_fstar": kin_kwargs["frequency_fstar"],
        },
    )
    write_json(out_dir / f"{label}_flow_{field_mode}_run_metadata.json", metadata)
    return metadata
