"""Tests for mosquito_cfd.visualization.flow_video (OpenSpec change add-visualization-tooling).

Pure-numpy / synthetic-fixture tests only -- no real plotfile, no ``$MOSQUITO_CFD_PLOTFILE_ROOT``.
The real-plotfile-adapter tests live in ``tests/test_flow_video_plotfile.py`` (``requires_plotfile``).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

import mosquito_cfd.visualization.flow_video as flow_video
from mosquito_cfd.benchmarks.lev import q_criterion
from mosquito_cfd.visualization.flow_video import (
    DEFAULT_Q_THRESHOLD,
    FIELD_MODES,
    _box_origin,
    _lev_axis_limits,
    _velocity_slice_axis_limits,
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


def test_render_lev_frame_skips_saturated_threshold_without_crashing():
    """A q_threshold at/below the field's own minimum has n_above >= 10 but no real crossing
    boundary for marching_cubes to extract -- must return None, not propagate skimage's raw
    "Surface level must be within volume data range" ValueError.
    """
    n = 24
    dx = 0.1
    coords = (np.arange(n) - n / 2) * dx
    x, y, z = np.meshgrid(coords, coords, coords, indexing="ij")
    r2 = x**2 + y**2 + z**2
    omega = 50.0 * np.exp(-r2 / (2.0 * 0.4**2))
    u = -omega * y
    v = omega * x
    w = np.zeros_like(x)

    q = q_criterion(u, v, w, dx)
    below_min_threshold = float(q.min()) - 1.0

    result = render_lev_frame(
        u, v, w, dx, q_threshold=below_min_threshold, vort_vmin=0.0, vort_vmax=200.0
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
    assert result["center"] == list(_KINEMATICS_KWARGS["center"])
    assert result["hinge"] == list(_KINEMATICS_KWARGS["hinge"])


def _synthetic_lev_box(n: int = 20) -> dict:
    """A localized solid-body-rotation bump box (real Q > DEFAULT_Q_THRESHOLD core), so
    lev-3d's isosurface-drawing path is actually exercised, not just the below-threshold skip.
    """
    dx = 0.1
    coords = (np.arange(n) - n / 2) * dx
    x, y, z = np.meshgrid(coords, coords, coords, indexing="ij")
    r2 = x**2 + y**2 + z**2
    omega = 400.0 * np.exp(-r2 / (2.0 * 0.4**2))
    return {
        "u": -omega * y,
        "v": omega * x,
        "w": np.zeros_like(x),
        "x": coords + 0.3,
        "y": coords + 0.3,
        "z": coords + 0.3,
        "dx": np.array([dx, dx, dx]),
        "current_time": 0.0,
    }


@pytest.mark.parametrize("field_mode", ["combined-3d", "lev-3d", "zvelocity-3d"])
def test_3d_scenes_disable_computed_zorder_so_wing_renders_above_the_field(
    tmp_path, monkeypatch, field_mode
):
    """Regression: mplot3d's default computed_zorder=True depth-sorts by each artist's own
    projected centroid, NOT the explicit zorder kwargs _draw_wing_scene passes -- reproduced
    directly: an opaque plot_surface at the vault's own view angle renders IN FRONT of a wing
    scatter lifted only WING_Z_LIFT above it (confirmed visually: the scatter is essentially
    invisible with computed_zorder left at its default). computed_zorder=False makes mplot3d use
    a real painter's algorithm honoring the explicit zorder values instead, so the wing (zorder
    20-22) always draws above the field (zorder 1) regardless of view angle.
    """
    plotfile_dir = tmp_path / "plotfiles"
    (plotfile_dir / "plt00000").mkdir(parents=True)
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi, halo=0: dict(_synthetic_lev_box()),
    )

    captured_kwargs = []
    real_add_axes = matplotlib.figure.Figure.add_axes

    def spy_add_axes(self, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return real_add_axes(self, *args, **kwargs)

    monkeypatch.setattr(matplotlib.figure.Figure, "add_axes", spy_add_axes)

    build_flow_video(
        plotfile_dir=plotfile_dir,
        field_mode=field_mode,
        vertex_path=_VERTEX_PATH,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="zorder-test",
        **_KINEMATICS_KWARGS,
    )

    threed_calls = [k for k in captured_kwargs if k.get("projection") == "3d"]
    assert len(threed_calls) == 1
    assert threed_calls[0].get("computed_zorder") is False


@pytest.mark.parametrize("field_mode", ["combined-3d", "lev-3d", "zvelocity-3d"])
def test_writes_video_for_every_wing_overlay_field_mode(
    tmp_path, monkeypatch, field_mode
):
    """Non-gated coverage of the 3 field modes previously exercised only by the
    requires_plotfile-gated test_flow_video_plotfile.py (which never runs in CI) -- a crash or
    exception anywhere in the wing-overlay drawing path (_draw_wing_scene, Poly3DCollection
    construction, the marching_cubes call structure) would be caught here.
    """
    plotfile_dir = tmp_path / "plotfiles"
    (plotfile_dir / "plt00000").mkdir(parents=True)

    box = _synthetic_lev_box()

    def fake_extract_eulerian_box(plotfile_path, *, lo, hi, halo=0):
        return dict(box)

    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        fake_extract_eulerian_box,
    )

    out_dir = tmp_path / "out"
    build_flow_video(
        plotfile_dir=plotfile_dir,
        field_mode=field_mode,
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="overlay",
        **_KINEMATICS_KWARGS,
    )

    mp4_path = out_dir / f"overlay_flow_{field_mode}.mp4"
    assert mp4_path.exists()
    assert mp4_path.stat().st_size > 0


def test_zvelocity_3d_slices_the_w_field_not_u(tmp_path, monkeypatch):
    """Regression: `field_name = "w" if field_mode == "zvelocity-3d" else "u"` -- a swapped
    condition would silently plot the wrong velocity component with no non-gated test noticing
    (this exact branch was previously exercised only inside the requires_plotfile gate).
    """
    plotfile_dir = tmp_path / "plotfiles"
    (plotfile_dir / "plt00000").mkdir(parents=True)

    n = 6
    dx = np.array([0.1, 0.1, 0.1])
    box = {
        "u": np.full((n, n, n), 1.0),
        "v": np.zeros((n, n, n)),
        "w": np.full((n, n, n), 2.0),  # distinct from u, so a swap is detectable
        "x": (np.arange(n) + 0.5) * dx[0],
        "y": (np.arange(n) + 0.5) * dx[1],
        "z": (np.arange(n) + 0.5) * dx[2],
        "dx": dx,
        "current_time": 0.0,
    }
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi, halo=0: dict(box),
    )

    captured_fields = []
    real_render = flow_video.render_velocity_slice_frame

    def spy_render(field, dx, vmin, vmax):
        captured_fields.append(np.asarray(field).copy())
        return real_render(field, dx, vmin, vmax)

    monkeypatch.setattr(flow_video, "render_velocity_slice_frame", spy_render)

    build_flow_video(
        plotfile_dir=plotfile_dir,
        field_mode="zvelocity-3d",
        vertex_path=_VERTEX_PATH,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="zvel-test",
        **_KINEMATICS_KWARGS,
    )

    assert len(captured_fields) >= 1
    for field in captured_fields:
        np.testing.assert_allclose(
            field, 2.0
        )  # w's value, never u's (which would be 1.0)


def test_box_origin_reads_the_boxs_own_coordinates_not_a_nominal_request():
    """Regression: the LEV isosurface offset must come from the box's OWN returned coordinate
    arrays, not a caller's nominal (center -/+ box_margin) request -- extract_eulerian_box clips
    an over-wide request to the domain, so a near-field box near a domain boundary has an actual
    physical origin that can differ substantially from the unclamped request.
    """
    # A box simulating a clamped near-field extraction: the nominal request might have been
    # (center - box_margin) = (-8.0, -8.0, -8.0), but the domain boundary clamped it up to 0.0.
    box = {
        "x": np.array([0.0, 0.1, 0.2]),
        "y": np.array([0.05, 0.15, 0.25]),
        "z": np.array([1.0, 1.1, 1.2]),
    }

    origin = _box_origin(box)

    np.testing.assert_allclose(origin, [0.0, 0.05, 1.0])
    # Not the nominal, unclamped request this box's coordinates were clamped away from.
    assert not np.allclose(origin, [-8.0, -8.0, -8.0])


def test_rejects_non_positive_fps(tmp_path):
    """fps=0 must raise before any matplotlib Figure is created, not leak one via an unguarded
    ZeroDivisionError from `int(1000 / fps)` deep inside FuncAnimation construction.
    """
    nonexistent_plotfile_dir = tmp_path / "does-not-exist"
    open_before = len(plt.get_fignums())

    with pytest.raises(ValueError, match="fps"):
        build_flow_video(
            plotfile_dir=nonexistent_plotfile_dir,
            field_mode="wake-slice",
            vertex_path=_VERTEX_PATH,
            out_dir=tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TS,
            label="test",
            fps=0,
            **_KINEMATICS_KWARGS,
        )

    assert len(plt.get_fignums()) == open_before


def test_does_not_leak_figure_on_out_dir_mkdir_error(tmp_path, monkeypatch):
    """An out_dir that can't be created (a file already at that path) must not leave the
    matplotlib Figure created earlier in build_flow_video unclosed.
    """
    plotfile_dir = tmp_path / "plotfiles"
    (plotfile_dir / "plt00000").mkdir(parents=True)
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi, halo=0: dict(_synthetic_box()),
    )
    blocked_out_dir = tmp_path / "blocked"
    blocked_out_dir.write_text("not a directory")

    open_before = len(plt.get_fignums())
    with pytest.raises(FileExistsError):
        build_flow_video(
            plotfile_dir=plotfile_dir,
            field_mode="wake-slice",
            vertex_path=_VERTEX_PATH,
            out_dir=blocked_out_dir,
            docker_image_digest=DIGEST,
            timestamp=TS,
            label="test",
            **_KINEMATICS_KWARGS,
        )
    assert len(plt.get_fignums()) == open_before


def test_lev_axis_limits_uses_box_coordinates():
    """The returned limits are exactly the near-field box's own x/y/z coordinate range."""
    box = {
        "x": np.array([0.5, 1.0, 1.5]),
        "y": np.array([-2.0, -1.5, -1.0]),
        "z": np.array([3.0, 4.0, 5.0]),
    }

    xlim, ylim, zlim = _lev_axis_limits(box)

    assert xlim == (0.5, 1.5)
    assert ylim == (-2.0, -1.0)
    assert zlim == (3.0, 5.0)


def test_lev_axis_limits_is_independent_of_isosurface_content():
    """Regression: the returned view window must depend only on the box's coordinate range, not
    on the field content (u/v/w) that determines the isosurface's shape -- otherwise the axes
    silently rescale frame to frame as the isosurface changes, making the stationary hinge marker
    appear to move (the exact "is the hinge moving?" symptom this fix addresses).
    """
    box_a = {
        "x": np.array([0.0, 1.0, 2.0]),
        "y": np.array([0.0, 1.0, 2.0]),
        "z": np.array([0.0, 1.0, 2.0]),
        "u": np.zeros((3, 3, 3)),
    }
    box_b = {**box_a, "u": np.ones((3, 3, 3)) * 999.0}  # wildly different field content

    assert _lev_axis_limits(box_a) == _lev_axis_limits(box_b)


def test_velocity_slice_axis_limits_z_window_around_slice_height():
    """The z window is z_level +/- z_margin, and comfortably contains the wing's lifted
    position (z_level + _WING_Z_LIFT) -- otherwise the wing overlay would render outside the
    fixed viewing window this fix introduces.
    """
    box = {"x": np.array([0.0, 8.0]), "y": np.array([0.0, 4.0])}

    xlim, ylim, zlim = _velocity_slice_axis_limits(box, z_level=4.0, z_margin=2.0)

    assert xlim == (0.0, 8.0)
    assert ylim == (0.0, 4.0)
    assert zlim == (2.0, 6.0)
    assert zlim[0] < 4.0 + flow_video._WING_Z_LIFT < zlim[1]


def test_lev_3d_axis_limits_are_stable_across_frames_with_different_isosurfaces(
    tmp_path, monkeypatch
):
    """End-to-end regression: two frames whose vortex cores sit at DIFFERENT positions (so their
    isosurfaces have genuinely different shapes/extents) must still render with IDENTICAL 3-D
    axis limits, since the near-field box's own coordinate range (not the isosurface) determines
    the view. Directly reproduces the user-visible "why are the axes changing all the time? is
    the hinge moving?" bug report as a regression test.
    """
    n = 24
    dx = 0.1
    coords = (np.arange(n) - n / 2) * dx

    def _bump_box(core_offset):
        x, y, z = np.meshgrid(coords, coords, coords, indexing="ij")
        r2 = (x - core_offset) ** 2 + y**2 + z**2
        omega = 400.0 * np.exp(-r2 / (2.0 * 0.3**2))
        return {
            "u": -omega * y,
            "v": omega * x,
            "w": np.zeros_like(x),
            "x": coords + 0.3,
            "y": coords + 0.3,
            "z": coords + 0.3,
            "dx": np.array([dx, dx, dx]),
            "current_time": 0.0,
        }

    plotfile_dir = tmp_path / "plotfiles"
    for name in ("plt00000", "plt00100"):
        (plotfile_dir / name).mkdir(parents=True)

    boxes = {"plt00000": _bump_box(0.0), "plt00100": _bump_box(0.6)}

    def fake_extract_eulerian_box(plotfile_path, *, lo, hi, halo=0):
        return dict(boxes[Path(plotfile_path).name])

    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        fake_extract_eulerian_box,
    )

    # Spy on FFMpegWriter.grab_frame (the call that captures the CURRENT axes state into the
    # video stream) rather than Axes3D.set_zlim directly -- matplotlib's own internal autoscale
    # machinery calls set_zlim several times per frame during the render pass (transient states
    # never written to the video); grab_frame time is what actually ends up on screen.
    from matplotlib.animation import FFMpegWriter

    captured_zlims = []
    real_grab_frame = FFMpegWriter.grab_frame

    def spy_grab_frame(self, *args, **kwargs):
        captured_zlims.append(ax_holder["ax"].get_zlim())
        return real_grab_frame(self, *args, **kwargs)

    monkeypatch.setattr(FFMpegWriter, "grab_frame", spy_grab_frame)

    # build_flow_video's Axes3D instance isn't returned; capture it via the first Poly3DCollection
    # added to any 3-D axes during this call (there's only one axes alive in this test).
    ax_holder = {}
    from mpl_toolkits.mplot3d.axes3d import Axes3D

    real_add_collection3d = Axes3D.add_collection3d

    def spy_add_collection3d(self, *args, **kwargs):
        ax_holder["ax"] = self
        return real_add_collection3d(self, *args, **kwargs)

    monkeypatch.setattr(Axes3D, "add_collection3d", spy_add_collection3d)

    build_flow_video(
        plotfile_dir=plotfile_dir,
        field_mode="lev-3d",
        vertex_path=_VERTEX_PATH,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="stability-test",
        center=(0.3, 0.3, 0.3),
        hinge=(0.3, 0.1, 0.3),
        stroke_amp_deg=70.0,
        pitch_amp_deg=45.0,
        frequency_fstar=1.0,
        box_margin=1.2,
        q_threshold=100.0,
        vort_vmin=0.0,
        vort_vmax=800.0,
    )

    assert len(captured_zlims) >= 2
    assert len(set(captured_zlims)) == 1, (
        f"axis limits changed across frames despite identical box coordinates: {captured_zlims}"
    )
