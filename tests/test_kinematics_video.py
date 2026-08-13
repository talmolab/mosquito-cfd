"""Tests for mosquito_cfd.visualization.kinematics_video (OpenSpec change add-visualization-tooling).

Pure-numpy / synthetic-fixture tests only -- this builder never opens a plotfile.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from mosquito_cfd.geometry.vertex_io import write_vertex_file
from mosquito_cfd.visualization.kinematics_video import build_kinematics_video

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


def test_chord_axis_extent_matches_root_hinge_arm(tmp_path):
    """The span-tip marker's chord-axis extent over one wingbeat matches
    2 * span_arm * sin(radians(stroke_amp_deg)) -- derived independently in this test (not
    read back from the function's own returned span_arm) so the test can't pass on a
    self-consistently-wrong implementation.
    """
    from mosquito_cfd.geometry.vertex_io import read_vertex_file

    stroke_amp_deg = 70.0
    local_markers = read_vertex_file(str(_VERTEX_PATH))
    span_col = local_markers[:, 1]
    max_abs_span = np.abs(span_col).max()
    tie_idx = np.flatnonzero(np.abs(np.abs(span_col) - max_abs_span) < 1e-6)
    tip_idx = tie_idx[np.argmin(np.abs(local_markers[tie_idx, 0]))]
    tip_reference = local_markers[tip_idx] + np.asarray(_VALIDATED_CENTER)
    expected_span_arm = float(
        np.linalg.norm(tip_reference - np.asarray(_VALIDATED_HINGE))
    )

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
