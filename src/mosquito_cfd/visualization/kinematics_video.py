"""Cluster-free wing-kinematics preview video.

OpenSpec change ``add-visualization-tooling`` (Phase 3). Generalizes the vault's
``make_wing_kinematics_s45_f115_p60.py`` into a config-or-explicit-override builder (`design.md`
D3) -- pure prescribed kinematics applied to the wing's own ``.vertex`` geometry, no plotfile, no
CFD run. Directly serves the "sanity-check geometry before the CFD run even starts" mid-sweep
check, a stronger version of ``flow_video.py``'s own goal.

``imageio_ffmpeg`` is imported lazily, inside the video-writing path (never at module top) --
this module must stay importable without the optional ``viz`` dependency group installed
(`design.md` D2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from mosquito_cfd.benchmarks.wing_kinematics import euler_angles
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

DEFAULT_N_FRAMES = 200
DEFAULT_FPS = 24

_COLOR_LEADING = "#C53030"
_COLOR_TRAILING = "#2D3748"
_COLOR_HINGE = "black"
_COLOR_TRAIL = "#9CA3AF"

# Tolerance for detecting tied max-|span| markers (the committed wing.vertex has 3 -- see
# _span_tip_index); dense enough sampling below (300 pts/wingbeat) that the trajectory-derived
# chord_axis_extent closely matches the closed-form 2*span_arm*sin(stroke_amp) formula.
_TIE_TOLERANCE = 1e-6
_TRAJECTORY_SAMPLES = 300


def _span_tip_index(local_markers: np.ndarray) -> int:
    """Index of the local marker at max ``|span (y)|``, nearest the chord centerline (``x~0``).

    The committed ``wing.vertex`` has 3 tied markers at max span (chord positions ~-0.06, 0,
    +0.06 per `tasks.md` task 19) -- picking the one nearest ``x=0`` keeps the tip's own
    chord-axis rest offset minimal, closest to a pure span-offset point from the hinge.
    """
    span_col = local_markers[:, 1]
    max_abs_span = float(np.abs(span_col).max())
    candidates = np.flatnonzero(
        np.abs(np.abs(span_col) - max_abs_span) < _TIE_TOLERANCE
    )
    return int(candidates[np.argmin(np.abs(local_markers[candidates, 0]))])


def _tip_trajectory(
    tip_reference: np.ndarray, hinge_arr: np.ndarray, kin_kwargs: dict[str, Any]
) -> np.ndarray:
    """Tip marker world position at ``_TRAJECTORY_SAMPLES`` phases over one full wingbeat."""
    t_end = 1.0 / kin_kwargs["frequency_fstar"]
    ts = np.linspace(0.0, t_end, _TRAJECTORY_SAMPLES)
    traj = np.zeros((_TRAJECTORY_SAMPLES, 3))
    for i, t in enumerate(ts):
        phi, alpha, theta = euler_angles(
            t,
            frequency=kin_kwargs["frequency_fstar"],
            stroke_amp_rad=np.radians(kin_kwargs["stroke_amp_deg"]),
            pitch_amp_rad=np.radians(kin_kwargs["pitch_amp_deg"]),
        )
        traj[i] = transform_markers(
            tip_reference[np.newaxis, :], hinge_arr, phi, alpha, theta
        )[0]
    return traj


def build_kinematics_video(
    *,
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
    n_frames: int = DEFAULT_N_FRAMES,
    fps: int = DEFAULT_FPS,
) -> dict[str, Any]:
    """Render a cluster-free wing-kinematics preview video and write the provenance triple.

    Never reads or otherwise references a plotfile path -- this is a pure-kinematics preview
    (no CFD data), unlike every ``flow_video.py`` field mode.

    Args:
        vertex_path: Path to the ``.vertex`` marker file.
        out_dir: Output directory.
        docker_image_digest: Pinned ``sha256:`` image digest (mutable tags rejected, CC-1).
        timestamp: Caller-supplied ISO-8601 timestamp (CC-1).
        label: Output filename label -- writes ``<label>_kinematics_preview.mp4``
            (`design.md` D5).
        config_name: Optional sweep config name; resolves center/hinge/kinematics from its deck
            (requires ``corpus_dir``). See
            :func:`mosquito_cfd.visualization.wing_render.resolve_kinematics_kwargs`.
        corpus_dir: Sweep corpus directory; required together with ``config_name``.
        center: Optional explicit wing-centre override (takes precedence over the config's deck).
        hinge: Optional explicit hinge override.
        stroke_amp_deg: Optional explicit stroke-amplitude override [deg].
        pitch_amp_deg: Optional explicit pitch-amplitude override [deg].
        frequency_fstar: Optional explicit flap-frequency override.
        n_frames: Number of rendered video frames spanning one full wingbeat.
        fps: Output video frame rate.

    Returns:
        Dict with the resolved ``center``/``hinge``/``stroke_amp_deg``/``pitch_amp_deg``/
        ``frequency_fstar``, plus ``span_arm`` (hinge-to-span-tip rest distance) and
        ``chord_axis_extent`` (the span-tip marker's chord-axis (x) peak-to-peak displacement
        over one full wingbeat -- for a pure span-offset tip this equals
        ``2 * span_arm * sin(radians(stroke_amp_deg))``). The same dict is written to
        ``<label>_kinematics_preview_metrics.json``.

    Raises:
        ValueError: If ``docker_image_digest`` is a mutable tag, ``fps`` is not positive, or the
            center/hinge/kinematics parameters cannot be fully resolved (see
            :func:`mosquito_cfd.visualization.wing_render.resolve_kinematics_kwargs`).
    """
    validate_image_digest(
        docker_image_digest
    )  # fail-fast before any computation/file I/O
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

    local_markers = read_vertex_file(str(vertex_path))
    ref_markers = local_markers + center_arr
    outline_ref = wing_outline(local_markers) + center_arr
    is_leading = leading_edge_mask(local_markers)

    tip_idx = _span_tip_index(local_markers)
    tip_reference = ref_markers[tip_idx]
    span_arm = float(np.linalg.norm(tip_reference - hinge_arr))

    tip_traj = _tip_trajectory(tip_reference, hinge_arr, kin_kwargs)
    chord_axis_extent = float(tip_traj[:, 0].max() - tip_traj[:, 0].min())

    import imageio_ffmpeg
    import matplotlib

    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    fig = plt.figure(figsize=(9, 7), facecolor="white")
    ax = fig.add_axes([0.05, 0.08, 0.9, 0.86], projection="3d")

    bbox_points = np.vstack([ref_markers, tip_traj, hinge_arr[np.newaxis, :]])
    bbox_lo = bbox_points.min(axis=0) - 0.5
    bbox_hi = bbox_points.max(axis=0) + 0.5

    t_end = 1.0 / kin_kwargs["frequency_fstar"]

    def draw(frame_idx: int) -> None:
        ax.clear()
        t = frame_idx / n_frames * t_end
        phi, alpha, theta = euler_angles(
            t,
            frequency=kin_kwargs["frequency_fstar"],
            stroke_amp_rad=np.radians(kin_kwargs["stroke_amp_deg"]),
            pitch_amp_rad=np.radians(kin_kwargs["pitch_amp_deg"]),
        )

        ax.plot(
            tip_traj[:, 0],
            tip_traj[:, 1],
            tip_traj[:, 2],
            color=_COLOR_TRAIL,
            lw=0.9,
            alpha=0.55,
            linestyle="--",
        )

        rot_outline = transform_markers(outline_ref, hinge_arr, phi, alpha, theta)
        closed = np.vstack([rot_outline, rot_outline[:1]])
        ax.plot(closed[:, 0], closed[:, 1], closed[:, 2], color=_COLOR_TRAILING, lw=1.2)

        rot_markers = transform_markers(ref_markers, hinge_arr, phi, alpha, theta)
        for mask, color in (
            (is_leading, _COLOR_LEADING),
            (~is_leading, _COLOR_TRAILING),
        ):
            ax.scatter(
                rot_markers[mask, 0],
                rot_markers[mask, 1],
                rot_markers[mask, 2],
                s=1.5,
                c=color,
                alpha=0.6,
            )

        ax.scatter(
            [hinge_arr[0]],
            [hinge_arr[1]],
            [hinge_arr[2]],
            color=_COLOR_HINGE,
            s=120,
            marker="o",
            zorder=10,
        )

        ax.set_xlim(bbox_lo[0], bbox_hi[0])
        ax.set_ylim(bbox_lo[1], bbox_hi[1])
        ax.set_zlim(bbox_lo[2], bbox_hi[2])
        ax.set_xlabel("x -- chord")
        ax.set_ylabel("y -- span")
        ax.set_zlabel("z -- vertical")
        ax.set_title(
            f"{label}: stroke amp {kin_kwargs['stroke_amp_deg']:.0f} deg, "
            f"pitch amp {kin_kwargs['pitch_amp_deg']:.0f} deg\n"
            f"stroke phi = {np.degrees(phi):+5.1f} deg   "
            f"pitch alpha = {np.degrees(alpha):+5.1f} deg"
        )

    anim = FuncAnimation(fig, draw, frames=n_frames, interval=int(1000 / fps))
    writer = FFMpegWriter(fps=fps, bitrate=2800)

    out_dir = Path(out_dir)
    try:
        # mkdir inside the try: a non-creatable out_dir (e.g. a file already at that path) must
        # not leave the Figure created above unclosed (the same leak class PR1's review found in
        # comparison_figure.py).
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = out_dir / f"{label}_kinematics_preview.mp4"
        anim.save(mp4_path, writer=writer, dpi=110)
    finally:
        plt.close(fig)

    result: dict[str, Any] = {
        **kin_kwargs,
        "span_arm": span_arm,
        "chord_axis_extent": chord_axis_extent,
    }
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(vertex_path),
        timestamp=timestamp,
        extra={"label": label},
    )
    write_json(out_dir / f"{label}_kinematics_preview_metrics.json", result)
    write_json(out_dir / f"{label}_kinematics_preview_run_metadata.json", metadata)
    return result
