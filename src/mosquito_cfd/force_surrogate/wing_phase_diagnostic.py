"""Cluster-free wing-phase geometric diagnostic: marker positions at 4 phases of one wingbeat.

OpenSpec change ``fix-force-surrogate-sweep-hinge``. Generalizes
``examples/flapping_wing/generate_all_figures.py::plot_k2_wing_phases`` (hardcoded to one example)
into a reusable function parameterized per sweep config, following the established evidence-figure
provenance convention: a ``<name>.png`` + ``<name>_metrics.json`` + ``<name>_run_metadata.json``
triple, ``capture_surrogate_run_metadata`` provenance, digest validated before any file is written.

Deliberately cluster-free: the bug this catches is purely geometric (kinematics + hinge +
wing.vertex), fully determined without running the solver -- no plotfile or force CSV required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from mosquito_cfd.benchmarks.wing_kinematics import (  # noqa: E402
    euler_angles,
    rotation_matrix,
)
from mosquito_cfd.force_surrogate.sidecar import (  # noqa: E402
    capture_surrogate_run_metadata,
    validate_image_digest,
)
from mosquito_cfd.force_surrogate.train import write_json  # noqa: E402
from mosquito_cfd.geometry.vertex_io import read_vertex_file  # noqa: E402

_PHASES = [(0.0, "t=0"), (0.25, "t=T/4"), (0.5, "t=T/2"), (0.75, "t=3T/4")]
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def _transform_markers(
    ref_markers: np.ndarray, hinge: np.ndarray, rotation: np.ndarray
) -> np.ndarray:
    """Rotate body-frame markers about the hinge and translate into the domain frame."""
    return (rotation @ (ref_markers - hinge).T).T + hinge


def build_wing_phase_figure(
    *,
    vertex_path: str | Path,
    center: tuple[float, float, float],
    hinge: tuple[float, float, float],
    stroke_amp_deg: float,
    pitch_amp_deg: float,
    frequency_fstar: float,
    config_name: str,
    docker_image_digest: str,
    timestamp: str,
    out_dir: str | Path,
    span_axis: str = "y",
) -> dict[str, Any]:
    """Render marker positions at 4 phases of one wingbeat and write the provenance triple.

    Args:
        vertex_path: Path to the ``.vertex`` marker file (origin-centred, as the solver loads it).
        center: Wing centre ``(x, y, z)`` in the domain frame (``particle_inputs.{x,y,z}``).
        hinge: Hinge position ``(x, y, z)`` in the domain frame (``particle_inputs.hinge_{x,y,z}``).
        stroke_amp_deg: Stroke amplitude [deg].
        pitch_amp_deg: Pitch amplitude [deg].
        frequency_fstar: Dimensionless flap frequency (unused in the phase fractions themselves,
            recorded for provenance/titling only -- the 4 phases are fractions of one wingbeat).
        config_name: Sweep configuration name; used to namespace all three output files.
        docker_image_digest: Pinned ``sha256:`` image digest (mutable tags rejected, CC-1).
        timestamp: Caller-supplied ISO-8601 timestamp (CC-1).
        out_dir: Output directory (e.g. ``examples/prelim_sweep/figures/``).
        span_axis: Which axis is the wing's span (default "y", the current van Veen convention).

    Returns:
        The metrics dict written to ``<config_name>_wing_phases_metrics.json`` -- the same
        span-arm/hinge numbers ``assert_hinge_at_span_root`` computes for the same deck.

    Raises:
        ValueError: If ``docker_image_digest`` is a mutable tag.
    """
    validate_image_digest(
        docker_image_digest
    )  # fail-fast before any computation/file I/O

    center_arr = np.asarray(center, dtype=float)
    hinge_arr = np.asarray(hinge, dtype=float)
    ref_markers = read_vertex_file(str(vertex_path))

    axis_idx = _AXIS_INDEX[span_axis]
    half_span = float(ref_markers[:, axis_idx].max())
    span_arm = float(center_arr[axis_idx] - hinge_arr[axis_idx])

    fig, axes = plt.subplots(1, 4, figsize=(12, 3.5), sharey=True)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for ax, (t_frac, label), color in zip(axes, _PHASES, colors, strict=True):
        phi, alpha, theta = euler_angles(
            t_frac,
            frequency=1.0,  # phase FRACTION of one wingbeat, independent of f*
            stroke_amp_rad=np.radians(stroke_amp_deg),
            pitch_amp_rad=np.radians(pitch_amp_deg),
        )
        rotation = rotation_matrix(phi, alpha, theta)
        markers = _transform_markers(ref_markers + center_arr, hinge_arr, rotation)
        ax.scatter(
            markers[:, 0], markers[:, 1], s=1.0, color=color, alpha=0.7, rasterized=True
        )
        ax.scatter(
            hinge_arr[0], hinge_arr[1], s=50, color="black", zorder=5, marker="^"
        )
        ax.set_title(
            f"{label}\nphi={np.degrees(phi):.0f} alpha={np.degrees(alpha):.0f}",
            fontsize=8,
        )
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
    fig.suptitle(
        f"{config_name}: wing marker positions at key phases (hinge = black triangle)"
    )
    fig.tight_layout()

    fig_metrics: dict[str, Any] = {
        "config_name": config_name,
        "span_axis": span_axis,
        "half_span": half_span,
        "span_arm": span_arm,
        "center": list(center),
        "hinge": list(hinge),
        "stroke_amp_deg": stroke_amp_deg,
        "pitch_amp_deg": pitch_amp_deg,
        "frequency_fstar": frequency_fstar,
    }
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(vertex_path),
        timestamp=timestamp,
        extra={"config_name": config_name},
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        out_dir / f"{config_name}_wing_phases.png", dpi=150, bbox_inches="tight"
    )
    plt.close(fig)
    write_json(out_dir / f"{config_name}_wing_phases_metrics.json", fig_metrics)
    write_json(out_dir / f"{config_name}_run_metadata.json", metadata)
    return fig_metrics
