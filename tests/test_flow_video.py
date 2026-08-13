"""Tests for mosquito_cfd.visualization.flow_video (OpenSpec change add-visualization-tooling).

Pure-numpy / synthetic-fixture tests only -- no real plotfile, no ``$MOSQUITO_CFD_PLOTFILE_ROOT``.
The real-plotfile-adapter tests live in ``tests/test_flow_video_plotfile.py`` (``requires_plotfile``).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest

from mosquito_cfd.benchmarks.lev import q_criterion
from mosquito_cfd.visualization.flow_video import (
    DEFAULT_Q_THRESHOLD,
    FIELD_MODES,
    build_flow_video,
    render_lev_frame,
    render_velocity_slice_frame,
)
from mosquito_cfd.visualization.wing_render import resolve_kinematics_kwargs

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERTEX_PATH = _REPO_ROOT / "examples" / "flapping_wing" / "wing.vertex"

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"

_KINEMATICS_KWARGS = {
    "center": (0.3, 0.3, 0.3),
    "hinge": (0.3, 0.1, 0.3),
    "stroke_amp_deg": 70.0,
    "pitch_amp_deg": 45.0,
    "frequency_fstar": 1.0,
}


def test_rejects_mutable_docker_tag(tmp_path):
    """A mutable tag raises before any plotfile path is even touched."""
    nonexistent_plotfile_dir = tmp_path / "does-not-exist"
    with pytest.raises(ValueError, match="sha256"):
        build_flow_video(
            plotfile_dir=nonexistent_plotfile_dir,
            field_mode="wake-slice",
            vertex_path=_VERTEX_PATH,
            out_dir=tmp_path / "out",
            docker_image_digest=":latest",
            timestamp=TS,
            label="test",
            **_KINEMATICS_KWARGS,
        )
    assert not nonexistent_plotfile_dir.exists()
    assert not (tmp_path / "out").exists()


def test_rejects_unknown_field_mode(tmp_path):
    """An invalid field_mode raises before any plotfile path is touched, naming the 4 valid modes."""
    nonexistent_plotfile_dir = tmp_path / "does-not-exist"
    with pytest.raises(ValueError) as exc_info:
        build_flow_video(
            plotfile_dir=nonexistent_plotfile_dir,
            field_mode="isosurface",
            vertex_path=_VERTEX_PATH,
            out_dir=tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TS,
            label="test",
            **_KINEMATICS_KWARGS,
        )
    message = str(exc_info.value)
    assert "isosurface" in message
    for mode in FIELD_MODES:
        assert mode in message
    assert not nonexistent_plotfile_dir.exists()
    assert not (tmp_path / "out").exists()


def _write_deck(
    corpus_dir: Path, config_name: str, hinge: tuple[float, float, float]
) -> None:
    inputs_dir = corpus_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    deck_text = (
        "particle_inputs.x = 4.0\n"
        "particle_inputs.y = 2.0\n"
        "particle_inputs.z = 4.0\n"
        f"particle_inputs.hinge_x = {hinge[0]}\n"
        f"particle_inputs.hinge_y = {hinge[1]}\n"
        f"particle_inputs.hinge_z = {hinge[2]}\n"
    )
    (inputs_dir / f"inputs.3d.{config_name}").write_text(deck_text, encoding="utf-8")


def test_config_kwargs_resolves_from_deck(tmp_path):
    """resolve_kinematics_kwargs reads center/hinge/kinematics from a config's own deck."""
    corpus_dir = tmp_path / "corpus"
    _write_deck(corpus_dir, "s45_f115_p60", hinge=(4.0, 0.5, 4.0))

    kwargs = resolve_kinematics_kwargs(
        config_name="s45_f115_p60", corpus_dir=corpus_dir
    )

    assert kwargs["center"] == (4.0, 2.0, 4.0)
    assert kwargs["hinge"] == (4.0, 0.5, 4.0)
    assert kwargs["stroke_amp_deg"] == pytest.approx(45.0)
    assert kwargs["pitch_amp_deg"] == pytest.approx(60.0)
    assert kwargs["frequency_fstar"] == pytest.approx(1.15)


def test_explicit_override_takes_precedence_over_deck(tmp_path):
    """An explicit hinge override replaces the deck's own (as-run, possibly buggy) hinge."""
    corpus_dir = tmp_path / "corpus"
    _write_deck(corpus_dir, "s45_f115_p60", hinge=(4.0, 2.0, 2.5))

    kwargs = resolve_kinematics_kwargs(
        config_name="s45_f115_p60", corpus_dir=corpus_dir, hinge=(4.0, 0.5, 4.0)
    )

    assert kwargs["hinge"] == (4.0, 0.5, 4.0)
    assert kwargs["center"] == (4.0, 2.0, 4.0)  # unaffected -- still read from the deck


def test_render_lev_frame_matches_solid_body_rotation():
    """A localized solid-body-rotation bump yields a real isosurface with finite geometry and
    colors sampled within the requested vorticity range -- not an arbitrary/constant fill.
    """
    n = 24
    dx = 0.1
    coords = (np.arange(n) - n / 2) * dx
    x, y, z = np.meshgrid(coords, coords, coords, indexing="ij")
    r2 = x**2 + y**2 + z**2
    omega0 = 50.0
    sigma = 0.4
    omega = omega0 * np.exp(-r2 / (2.0 * sigma**2))
    u = -omega * y
    v = omega * x
    w = np.zeros_like(x)

    q = q_criterion(u, v, w, dx)
    threshold = float(np.percentile(q, 95))

    result = render_lev_frame(
        u, v, w, dx, q_threshold=threshold, vort_vmin=0.0, vort_vmax=2.0 * omega0
    )

    assert result is not None
    triangles = result["triangles"]
    facecolors = result["facecolors"]
    assert triangles.ndim == 3
    assert triangles.shape[1:] == (3, 3)
    assert facecolors.shape == (triangles.shape[0], 4)
    assert np.isfinite(triangles).all()
    assert ((facecolors >= 0.0) & (facecolors <= 1.0)).all()


def test_render_lev_frame_skips_below_threshold_field():
    """An entirely-below-threshold field (< 10 cells above) returns None, not an empty mesh."""
    zeros = np.zeros((10, 10, 10))
    result = render_lev_frame(
        zeros, zeros, zeros, 0.1, q_threshold=300.0, vort_vmin=40.0, vort_vmax=250.0
    )
    assert result is None


def test_render_velocity_slice_frame_matches_known_field():
    """RdBu_r-colored slice: a known min/mid/max value maps to the colormap's 0/0.5/1 colors."""
    field = np.array([[-5.0, 0.0], [2.5, 5.0]])
    result = render_velocity_slice_frame(field, dx=(0.1, 0.1), vmin=-5.0, vmax=5.0)
    cmap = matplotlib.colormaps["RdBu_r"]
    np.testing.assert_allclose(result[0, 0], cmap(0.0))
    np.testing.assert_allclose(result[0, 1], cmap(0.5))
    np.testing.assert_allclose(result[1, 1], cmap(1.0))


def test_render_velocity_slice_frame_clips_to_vmin_vmax():
    """Values outside [vmin, vmax] clip to the colormap's endpoint colors, not extrapolate."""
    field = np.array([[-100.0, 100.0]])
    result = render_velocity_slice_frame(field, dx=(0.1, 0.1), vmin=-5.0, vmax=5.0)
    cmap = matplotlib.colormaps["RdBu_r"]
    np.testing.assert_allclose(result[0, 0], cmap(0.0))
    np.testing.assert_allclose(result[0, 1], cmap(1.0))


def test_default_q_threshold_is_300():
    assert DEFAULT_Q_THRESHOLD == 300.0


def test_q_threshold_override_reaches_marching_cubes(monkeypatch):
    """An explicit q_threshold is the exact `level` skimage.measure.marching_cubes receives."""
    calls: list[float] = []

    def fake_marching_cubes(volume, level=None):
        calls.append(level)
        verts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        faces = np.array([[0, 1, 2]])
        return verts, faces, None, None

    monkeypatch.setattr("skimage.measure.marching_cubes", fake_marching_cubes)

    n = 24
    dx = 0.1
    coords = (np.arange(n) - n / 2) * dx
    x, y, z = np.meshgrid(coords, coords, coords, indexing="ij")
    r2 = x**2 + y**2 + z**2
    omega = 50.0 * np.exp(-r2 / (2.0 * 0.4**2))
    u = -omega * y
    v = omega * x
    w = np.zeros_like(x)

    custom_threshold = 123.456
    result = render_lev_frame(
        u, v, w, dx, q_threshold=custom_threshold, vort_vmin=0.0, vort_vmax=200.0
    )

    assert calls == [custom_threshold]
    assert result is not None


def _synthetic_box(n: int = 6) -> dict:
    dx = np.array([0.1, 0.1, 0.1])
    return {
        "u": np.zeros((n, n, n)),
        "v": np.zeros((n, n, n)),
        "w": np.zeros((n, n, n)),
        "x": (np.arange(n) + 0.5) * dx[0],
        "y": (np.arange(n) + 0.5) * dx[1],
        "z": (np.arange(n) + 0.5) * dx[2],
        "dx": dx,
        "current_time": 0.0,
    }


def test_writes_metadata_sidecar_without_a_plotfile(tmp_path, monkeypatch):
    """The top-level orchestration writes an .mp4 + _run_metadata.json pair even with a fully
    monkeypatched (no real yt/plotfile) box read -- this is the only non-requires_plotfile
    coverage of flow_video's sidecar-writing behavior (task 16's tests are all requires_plotfile
    and never run in CI).
    """
    plotfile_dir = tmp_path / "plotfiles"
    for name in ("plt00000", "plt00100"):
        (plotfile_dir / name).mkdir(parents=True)

    box = _synthetic_box()

    def fake_extract_eulerian_box(plotfile_path, *, lo, hi, halo=0):
        return dict(box)

    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        fake_extract_eulerian_box,
    )

    out_dir = tmp_path / "out"
    result = build_flow_video(
        plotfile_dir=plotfile_dir,
        field_mode="wake-slice",
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="synthetic",
        **_KINEMATICS_KWARGS,
    )

    mp4_path = out_dir / "synthetic_flow_wake-slice.mp4"
    metadata_path = out_dir / "synthetic_flow_wake-slice_run_metadata.json"
    assert mp4_path.exists()
    assert mp4_path.stat().st_size > 0
    assert metadata_path.exists()
    assert result["docker_image"] == DIGEST
    assert result["timestamp"] == TS
