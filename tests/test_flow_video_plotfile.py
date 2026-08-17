"""Real-plotfile-adapter tests for flow_video (OpenSpec change add-visualization-tooling).

Requires a real single-level plotfile under ``$MOSQUITO_CFD_PLOTFILE_ROOT`` -- auto-skipped off
the cluster/Z: drive (see ``tests/conftest.py``). Targets the T3c grid-convergence benchmark
(``examples/flapping_wing/inputs.3d.convergence_fine``, 256x128x256), the same run the vault
video scripts this module generalizes were built against.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mosquito_cfd.benchmarks.lev import q_criterion
from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box
from mosquito_cfd.visualization.flow_video import DEFAULT_Q_THRESHOLD, build_flow_video

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERTEX_PATH = _REPO_ROOT / "examples" / "flapping_wing" / "wing.vertex"

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"

# Matches examples/flapping_wing/inputs.3d.convergence_fine / inputs.3d.validation.
_KINEMATICS_KWARGS = {
    "center": (4.0, 2.0, 4.0),
    "hinge": (4.0, 0.5, 4.0),
    "stroke_amp_deg": 70.0,
    "pitch_amp_deg": 45.0,
    "frequency_fstar": 1.0,
}


def _t3c_fine_plotfile_dir() -> Path:
    root = Path(os.environ["MOSQUITO_CFD_PLOTFILE_ROOT"])
    return root / "t3c-fine"


def _assert_video_written(
    out_dir: Path, field_mode: str, label: str = "t3c-fine"
) -> None:
    mp4_path = out_dir / f"{label}_flow_{field_mode}.mp4"
    metadata_path = out_dir / f"{label}_flow_{field_mode}_run_metadata.json"
    assert mp4_path.exists()
    assert mp4_path.stat().st_size > 0
    assert metadata_path.exists()


@pytest.mark.requires_plotfile
def test_renders_wake_slice_video(tmp_path):
    out_dir = tmp_path / "out"
    build_flow_video(
        plotfile_dir=_t3c_fine_plotfile_dir(),
        field_mode="wake-slice",
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="t3c-fine",
        **_KINEMATICS_KWARGS,
    )
    _assert_video_written(out_dir, "wake-slice")


@pytest.mark.requires_plotfile
def test_renders_combined_3d_video(tmp_path):
    out_dir = tmp_path / "out"
    build_flow_video(
        plotfile_dir=_t3c_fine_plotfile_dir(),
        field_mode="combined-3d",
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="t3c-fine",
        **_KINEMATICS_KWARGS,
    )
    _assert_video_written(out_dir, "combined-3d")


@pytest.mark.requires_plotfile
def test_renders_zvelocity_3d_video(tmp_path):
    out_dir = tmp_path / "out"
    build_flow_video(
        plotfile_dir=_t3c_fine_plotfile_dir(),
        field_mode="zvelocity-3d",
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="t3c-fine",
        **_KINEMATICS_KWARGS,
    )
    _assert_video_written(out_dir, "zvelocity-3d")


@pytest.mark.requires_plotfile
def test_renders_lev_3d_video(tmp_path):
    """Also asserts at least one frame has >10 cells above Q_THRESHOLD (a real LEV core exists),
    matching the vault script's own skip-if-empty guard sanity check.
    """
    plotfile_dir = _t3c_fine_plotfile_dir()
    out_dir = tmp_path / "out"
    build_flow_video(
        plotfile_dir=plotfile_dir,
        field_mode="lev-3d",
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="t3c-fine",
        **_KINEMATICS_KWARGS,
    )
    _assert_video_written(out_dir, "lev-3d")

    center = _KINEMATICS_KWARGS["center"]
    box_margin = 3.0
    lo = tuple(c - box_margin for c in center)
    hi = tuple(c + box_margin for c in center)
    found_lev_core = False
    for plt_path in sorted(plotfile_dir.glob("plt?????")):
        box = extract_eulerian_box(str(plt_path), lo=lo, hi=hi)
        q = q_criterion(box["u"], box["v"], box["w"], box["dx"])
        if int((q > DEFAULT_Q_THRESHOLD).sum()) > 10:
            found_lev_core = True
            break
    assert found_lev_core, (
        "expected at least one frame with a coherent Q > DEFAULT_Q_THRESHOLD core"
    )


@pytest.mark.requires_plotfile
def test_lev_3d_skips_empty_isosurface_gracefully(tmp_path):
    """A near-field box positioned in quiescent flow (no coherent Q core) still renders a video
    (an empty isosurface frame, per render_lev_frame's None-on-below-threshold contract), rather
    than raising.
    """
    out_dir = tmp_path / "out"
    quiescent_kwargs = dict(_KINEMATICS_KWARGS)
    build_flow_video(
        plotfile_dir=_t3c_fine_plotfile_dir(),
        field_mode="lev-3d",
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="quiescent-corner",
        center=(0.2, 0.2, 0.2),
        hinge=quiescent_kwargs["hinge"],
        stroke_amp_deg=quiescent_kwargs["stroke_amp_deg"],
        pitch_amp_deg=quiescent_kwargs["pitch_amp_deg"],
        frequency_fstar=quiescent_kwargs["frequency_fstar"],
        box_margin=0.1,
    )
    _assert_video_written(out_dir, "lev-3d", label="quiescent-corner")
