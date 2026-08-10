"""Cluster-free wing-phase geometric diagnostic: marker positions at 4 phases of one wingbeat.

OpenSpec change ``fix-force-surrogate-sweep-hinge``. Cluster-free by design (D2): the bug this
diagnostic exists to catch is purely geometric (deck kinematics + hinge + wing.vertex), fully
determined without running the solver -- the same category of check that caught the original bug
during unrelated pitch-deck preparation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate.geometry_guard import assert_hinge_at_span_root
from mosquito_cfd.force_surrogate.wing_phase_diagnostic import build_wing_phase_figure

_CANONICAL_VERTEX = Path("examples/flapping_wing/wing.vertex")
DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"

_VALIDATED_KWARGS = dict(
    vertex_path=_CANONICAL_VERTEX,
    center=(4.0, 2.0, 4.0),
    hinge=(4.0, 0.5, 4.0),
    stroke_amp_deg=70.0,
    pitch_amp_deg=45.0,
    frequency_fstar=1.0,
    config_name="validated",
)


def test_build_wing_phase_figure_matches_geometry_guard_numbers(tmp_path):
    """The figure's metrics dict matches assert_hinge_at_span_root's own computation exactly."""
    result = build_wing_phase_figure(
        **_VALIDATED_KWARGS,
        docker_image_digest=DIGEST,
        timestamp=TS,
        out_dir=tmp_path,
    )
    deck_text = (
        "particle_inputs.x = 4.0\nparticle_inputs.y = 2.0\nparticle_inputs.z = 4.0\n"
        "particle_inputs.hinge_x = 4.0\nparticle_inputs.hinge_y = 0.5\nparticle_inputs.hinge_z = 4.0\n"
    )
    # Must not raise: the validated point is a known-correct root hinge.
    assert_hinge_at_span_root(deck_text, _CANONICAL_VERTEX)

    assert result["span_axis"] == "y"
    assert result["span_arm"] == pytest.approx(2.0 - 0.5)
    assert result["half_span"] == pytest.approx(1.475, abs=1e-3)


def test_build_wing_phase_figure_runs_without_any_cfd_output(tmp_path):
    """Succeeds using only the deck's kinematics/hinge parameters and the geometry file."""
    result = build_wing_phase_figure(
        **_VALIDATED_KWARGS,
        docker_image_digest=DIGEST,
        timestamp=TS,
        out_dir=tmp_path,
    )
    assert result["config_name"] == "validated"


def test_build_wing_phase_figure_writes_three_artifacts(tmp_path):
    build_wing_phase_figure(
        **_VALIDATED_KWARGS,
        docker_image_digest=DIGEST,
        timestamp=TS,
        out_dir=tmp_path,
    )
    assert (tmp_path / "validated_wing_phases.png").exists()
    metrics = json.loads((tmp_path / "validated_wing_phases_metrics.json").read_text())
    assert metrics["span_arm"] == pytest.approx(1.5)
    meta = json.loads((tmp_path / "validated_run_metadata.json").read_text())
    assert meta["timestamp"] == TS
    assert "sha256:" in meta["docker_image"]


def test_wing_phase_diagnostic_rejects_mutable_docker_tag(tmp_path):
    with pytest.raises(ValueError):
        build_wing_phase_figure(
            **_VALIDATED_KWARGS,
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=TS,
            out_dir=tmp_path,
        )
    assert not (tmp_path / "validated_wing_phases.png").exists()
