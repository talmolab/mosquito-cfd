"""Tests for mosquito_cfd.visualization.kinematics_video (OpenSpec change add-visualization-tooling).

Pure-numpy / synthetic-fixture tests only -- this builder never opens a plotfile.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from mosquito_cfd.geometry.vertex_io import read_vertex_file, write_vertex_file
from mosquito_cfd.visualization.kinematics_video import (
    _span_tip_index,
    _swept_bounding_box,
    build_kinematics_video,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERTEX_PATH = _REPO_ROOT / "examples" / "flapping_wing" / "wing.vertex"

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"

# Matches examples/flapping_wing/inputs.3d.validation.
_VALIDATED_CENTER = (4.0, 2.0, 4.0)
_VALIDATED_HINGE = (4.0, 0.5, 4.0)


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


def test_rejects_mutable_docker_tag(tmp_path):
    with pytest.raises(ValueError, match="sha256"):
        build_kinematics_video(
            vertex_path=_VERTEX_PATH,
            out_dir=tmp_path / "out",
            docker_image_digest=":latest",
            timestamp=TS,
            label="test",
            center=_VALIDATED_CENTER,
            hinge=_VALIDATED_HINGE,
            stroke_amp_deg=70.0,
            pitch_amp_deg=45.0,
            frequency_fstar=1.0,
            n_frames=5,
        )
    assert not (tmp_path / "out").exists()


def test_config_kwargs_resolves_from_deck_with_no_override(tmp_path):
    """The plain, no-override config-resolve path (not just flow_video's)."""
    corpus_dir = tmp_path / "corpus"
    _write_deck(corpus_dir, "s45_f115_p60", hinge=(4.0, 0.5, 4.0))

    result = build_kinematics_video(
        vertex_path=_VERTEX_PATH,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="s45_f115_p60",
        config_name="s45_f115_p60",
        corpus_dir=corpus_dir,
        n_frames=5,
    )

    assert result["hinge"] == (4.0, 0.5, 4.0)
    assert result["center"] == (4.0, 2.0, 4.0)
    assert result["stroke_amp_deg"] == pytest.approx(45.0)
    assert result["pitch_amp_deg"] == pytest.approx(60.0)
    assert result["frequency_fstar"] == pytest.approx(1.15)


def test_explicit_hinge_override_takes_precedence_over_deck(tmp_path):
    """design.md D3's dual-hinge-caveat narrative is specifically about kinematics_video."""
    corpus_dir = tmp_path / "corpus"
    _write_deck(
        corpus_dir, "s45_f115_p60", hinge=(4.0, 2.0, 2.5)
    )  # as-run, buggy hinge

    result = build_kinematics_video(
        vertex_path=_VERTEX_PATH,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="s45_f115_p60",
        config_name="s45_f115_p60",
        corpus_dir=corpus_dir,
        hinge=(4.0, 0.5, 4.0),  # corrected hinge for display
        n_frames=5,
    )

    assert result["hinge"] == (4.0, 0.5, 4.0)
    assert result["center"] == (4.0, 2.0, 4.0)  # unaffected -- still read from the deck


def test_span_tip_index_picks_side_farthest_from_hinge_on_exact_tie():
    """Regression for issue #87: the committed wing.vertex has an exact 3-way tie at max
    |span| on BOTH y=-1.475 and y=+1.475. With prelim_sweep_fine's real convention
    (center=(4,2,4), hinge=(4,0.5,4) -- hinge on the negative-y side of center), the true tip
    is the y=+1.475 side (farthest from the hinge), not y=-1.475 (the root, next to the
    hinge) -- which is what the pre-fix nearest-x=0-only tie-break always picked, being the
    first array occurrence on an exact tie.
    """
    local_markers = read_vertex_file(str(_VERTEX_PATH))
    center = np.asarray(_VALIDATED_CENTER)
    hinge_local = np.asarray(_VALIDATED_HINGE) - center

    tip_idx = _span_tip_index(local_markers, hinge_local)

    assert local_markers[tip_idx, 1] == pytest.approx(1.475, abs=1e-3)


def test_span_tip_index_unique_max_span_ignores_hinge():
    """A non-regression control: when there's no tie, the unique max-|span| marker is always
    selected, regardless of where the hinge is.
    """
    markers = np.array(
        [
            [0.0, 0.5, 0.0],
            [0.0, -0.9, 0.0],  # unique max |span|
            [0.1, 0.3, 0.0],
        ]
    )

    for hinge in (np.array([0.0, 0.0, 0.0]), np.array([0.0, -5.0, 0.0])):
        assert _span_tip_index(markers, hinge) == 1


def test_span_tip_index_falls_back_to_nearest_x_when_hinge_distances_also_tie():
    """design.md D2's secondary tie-break: when candidates are tied at BOTH max |span| and
    distance from the hinge, the nearest-chord-axis-to-zero candidate wins (the original,
    pre-#87 rule), now demoted to a tie-break of last resort.

    Hinge is deliberately off the x=0 axis (x=0.1) so two candidates with DIFFERENT |x| can
    still tie on distance from the hinge (dx=+0.2 and dx=-0.2 respectively); a third candidate
    (x=0.15) is closer to the hinge and correctly excluded from the farthest-distance tie.
    """
    markers = np.array(
        [
            [0.3, 1.0, 0.0],  # tied farthest from hinge (dx=+0.2)
            [
                -0.1,
                1.0,
                0.0,
            ],  # tied farthest from hinge (dx=-0.2), nearest x=0 -- should win
            [
                0.15,
                1.0,
                0.0,
            ],  # tied max |span| but NOT tied farthest (dx=+0.05, nearer hinge)
            [0.0, 0.0, 0.0],
        ]
    )
    hinge = np.array([0.1, 0.0, 0.0])

    assert _span_tip_index(markers, hinge) == 1


def test_chord_axis_extent_matches_root_hinge_arm(tmp_path):
    """The span-tip marker's chord-axis extent over one wingbeat matches
    2 * span_arm * sin(radians(stroke_amp_deg)) -- derived independently in this test (not
    read back from the function's own returned span_arm) so the test can't pass on a
    self-consistently-wrong implementation. Also asserts span_arm directly (not just the
    derived chord_axis_extent), so a hinge-farthest-tip regression is caught unambiguously
    rather than only transitively through the trigonometric formula.
    """
    stroke_amp_deg = 70.0
    local_markers = read_vertex_file(str(_VERTEX_PATH))
    center = np.asarray(_VALIDATED_CENTER)
    hinge = np.asarray(_VALIDATED_HINGE)
    tip_idx = _span_tip_index(local_markers, hinge - center)
    tip_reference = local_markers[tip_idx] + center
    expected_span_arm = float(np.linalg.norm(tip_reference - hinge))

    result = build_kinematics_video(
        vertex_path=_VERTEX_PATH,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="validated",
        center=_VALIDATED_CENTER,
        hinge=_VALIDATED_HINGE,
        stroke_amp_deg=stroke_amp_deg,
        pitch_amp_deg=45.0,
        frequency_fstar=1.0,
        n_frames=10,
    )

    assert result["span_arm"] == pytest.approx(expected_span_arm, rel=0.01)
    expected_extent = 2.0 * expected_span_arm * np.sin(np.radians(stroke_amp_deg))
    assert result["chord_axis_extent"] == pytest.approx(expected_extent, rel=0.05)


def test_chord_axis_extent_collapses_toward_zero_for_near_zero_span_arm(tmp_path):
    """A synthetic near-zero span_arm (midspan-pivot-style: hinge placed at the tip's own rest
    position) collapses the chord-axis extent toward zero, the same geometric signature
    assert_hinge_at_span_root checks on the deck, applied here to the rendered trajectory.
    """
    vertex_path = tmp_path / "midspan.vertex"
    markers = np.array([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.5, 0.5, 0.0]])
    write_vertex_file(markers, str(vertex_path))

    result = build_kinematics_video(
        vertex_path=vertex_path,
        out_dir=tmp_path / "out",
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="midspan",
        center=(0.0, 0.0, 0.0),
        hinge=(0.0, 1.0, 0.0),  # hinge AT the span-tip's own rest position -> arm ~ 0
        stroke_amp_deg=70.0,
        pitch_amp_deg=45.0,
        frequency_fstar=1.0,
        n_frames=5,
    )

    assert result["span_arm"] < 1e-9
    assert result["chord_axis_extent"] < 1e-9


def test_writes_metadata_sidecar_with_no_plotfile_access(tmp_path):
    """Succeeds even though nothing resembling a plotfile exists anywhere -- proving this
    builder is purely kinematic (no plotfile_dir parameter, no plotfile I/O of any kind).
    """
    never_created_plotfile_like_path = tmp_path / "plt00000"
    out_dir = tmp_path / "out"

    result = build_kinematics_video(
        vertex_path=_VERTEX_PATH,
        out_dir=out_dir,
        docker_image_digest=DIGEST,
        timestamp=TS,
        label="pure-kinematics",
        center=_VALIDATED_CENTER,
        hinge=_VALIDATED_HINGE,
        stroke_amp_deg=70.0,
        pitch_amp_deg=45.0,
        frequency_fstar=1.0,
        n_frames=5,
    )

    assert not never_created_plotfile_like_path.exists()
    mp4_path = out_dir / "pure-kinematics_kinematics_preview.mp4"
    assert mp4_path.exists()
    assert mp4_path.stat().st_size > 0
    assert (out_dir / "pure-kinematics_kinematics_preview_run_metadata.json").exists()
    assert result["chord_axis_extent"] >= 0.0


def test_rejects_non_positive_fps(tmp_path):
    """fps=0 must raise before any matplotlib Figure is created, not leak one via an unguarded
    ZeroDivisionError from `int(1000 / fps)` deep inside FuncAnimation construction.
    """
    open_before = len(plt.get_fignums())

    with pytest.raises(ValueError, match="fps"):
        build_kinematics_video(
            vertex_path=_VERTEX_PATH,
            out_dir=tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TS,
            label="test",
            center=_VALIDATED_CENTER,
            hinge=_VALIDATED_HINGE,
            stroke_amp_deg=70.0,
            pitch_amp_deg=45.0,
            frequency_fstar=1.0,
            n_frames=5,
            fps=0,
        )

    assert len(plt.get_fignums()) == open_before


def test_does_not_leak_figure_on_out_dir_mkdir_error(tmp_path):
    """An out_dir that can't be created (a file already at that path) must not leave the
    matplotlib Figure created earlier in build_kinematics_video unclosed.
    """
    blocked_out_dir = tmp_path / "blocked"
    blocked_out_dir.write_text("not a directory")

    open_before = len(plt.get_fignums())
    with pytest.raises(FileExistsError):
        build_kinematics_video(
            vertex_path=_VERTEX_PATH,
            out_dir=blocked_out_dir,
            docker_image_digest=DIGEST,
            timestamp=TS,
            label="test",
            center=_VALIDATED_CENTER,
            hinge=_VALIDATED_HINGE,
            stroke_amp_deg=70.0,
            pitch_amp_deg=45.0,
            frequency_fstar=1.0,
            n_frames=5,
        )
    assert len(plt.get_fignums()) == open_before


def test_swept_bounding_box_captures_every_markers_full_sweep_not_just_rest_frame_or_tip():
    """Regression ("wing flies off the edge of the frame"): the OLD bounding box was built from
    `ref_markers` (rest-frame, UNROTATED positions) union a single tracked tip's own rotated
    trajectory -- any OTHER marker that sweeps outside its own rest-frame footprint under
    rotation was never accounted for. Uses a synthetic "decoy" marker (not the tip) whose true
    rotated range is independently computed here (ground truth), not read back from the function
    under test, so a reintroduced version of the old bug would be caught.
    """
    from mosquito_cfd.benchmarks.wing_kinematics import euler_angles
    from mosquito_cfd.visualization.wing_render import transform_markers

    markers = np.array(
        [
            [0.0, 1.0, 0.0],  # span tip
            [
                1.0,
                0.3,
                0.0,
            ],  # decoy: rest position near the hinge, but sweeps far under rotation
        ]
    )
    hinge_arr = np.array([0.0, 0.0, 0.0])
    kin_kwargs = {"stroke_amp_deg": 70.0, "pitch_amp_deg": 0.0, "frequency_fstar": 1.0}

    lo, hi = _swept_bounding_box(markers, hinge_arr, kin_kwargs, margin=0.0)

    ts = np.linspace(0.0, 1.0, 500)
    decoy = markers[1]
    rotated_decoy_x = [
        transform_markers(
            decoy[np.newaxis, :],
            hinge_arr,
            *euler_angles(
                t, frequency=1.0, stroke_amp_rad=np.radians(70.0), pitch_amp_rad=0.0
            ),
        )[0, 0]
        for t in ts
    ]
    expected_min, expected_max = min(rotated_decoy_x), max(rotated_decoy_x)

    # Sanity: the decoy's true swept range meaningfully exceeds its rest position (x=1.0) --
    # proves this is a real, non-trivial check, not one that would pass by coincidence.
    assert expected_max - expected_min > 0.5

    assert lo[0] <= expected_min + 1e-6
    assert hi[0] >= expected_max - 1e-6


def test_swept_bounding_box_contains_every_real_marker_at_every_sampled_phase():
    """Integration sanity check using the real committed wing.vertex + validated config: every
    marker's position at every one of several sampled phases across a full wingbeat lands inside
    the returned bounding box, using the DEFAULT margin (as production actually calls this
    function) -- a zero margin would be spuriously brittle here: any two independent discrete
    samplings of a continuous periodic extremum (this test's 17 phases vs. the function's own
    300) generically disagree by a small sub-grid amount, which the default margin exists to
    absorb.
    """
    local_markers = read_vertex_file(str(_VERTEX_PATH))
    center_arr = np.asarray(_VALIDATED_CENTER)
    hinge_arr = np.asarray(_VALIDATED_HINGE)
    ref_markers = local_markers + center_arr
    kin_kwargs = {"stroke_amp_deg": 70.0, "pitch_amp_deg": 45.0, "frequency_fstar": 1.0}

    lo, hi = _swept_bounding_box(ref_markers, hinge_arr, kin_kwargs)

    from mosquito_cfd.benchmarks.wing_kinematics import euler_angles
    from mosquito_cfd.visualization.wing_render import transform_markers

    for t in np.linspace(0.0, 1.0, 17):
        phi, alpha, theta = euler_angles(
            t,
            frequency=kin_kwargs["frequency_fstar"],
            stroke_amp_rad=np.radians(kin_kwargs["stroke_amp_deg"]),
            pitch_amp_rad=np.radians(kin_kwargs["pitch_amp_deg"]),
        )
        rotated = transform_markers(ref_markers, hinge_arr, phi, alpha, theta)
        assert np.all(rotated >= lo)
        assert np.all(rotated <= hi)
