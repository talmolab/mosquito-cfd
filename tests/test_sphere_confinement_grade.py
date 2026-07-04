"""Confinement-corrected sphere Cd literature grade (H1', Tier T2b).

Grades the T1b control-volume Cd against the literature point Cd = 1.087 (Johnson & Patel 1999) by
DIVIDING out the transverse-array confinement offset (+3-6%) and checking the isolated-equivalent
bracket lands within +/-5% of 1.087. Cluster-free: takes Cd *values* as inputs (CC-V4 — no extractor
internals). The verdict rests on the two-grid Richardson value 1.131, NOT a single grid.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mosquito_cfd.benchmarks.analyze_sphere import (
    LITERATURE_CD,
    SPHERE_CONFINEMENT_OFFSET_BAND,
    SPHERE_LITERATURE_TOL,
    extract_sphere_cd,
    grade_sphere_cd_confinement_corrected,
)
from mosquito_cfd.benchmarks.stress_integral import sphere_cv_drag_cd


def _sphere_plt(grid: str, step: int = 10000) -> str:
    root = os.environ.get("MOSQUITO_CFD_PLOTFILE_ROOT", "")
    sub = {"coarse": "flow_past_sphere_coarse", "medium": "flow_past_sphere_10k"}[grid]
    return str(Path(root) / sub / f"plt{step:05d}")


def test_richardson_grades_h1prime():
    """Richardson-extrapolated 1.131 -> isolated bracket [1.067, 1.098] within +/-5% -> H1'.

    Scenario: Richardson-extrapolated Cd grades as H1' within tolerance.
    """
    result = grade_sphere_cd_confinement_corrected(1.131)
    lo, hi = result["isolated_bracket"]
    # bracket via division: larger offset -> smaller value (lo), smaller offset -> larger value (hi)
    assert lo == pytest.approx(1.131 / 1.06, abs=1e-4)  # 1.06698
    assert hi == pytest.approx(1.131 / 1.03, abs=1e-4)  # 1.09806
    assert (lo, hi) == pytest.approx((1.067, 1.098), abs=1e-3)
    # lies within +/-5% of 1.087 == [1.033, 1.141]
    assert result["within"] is True
    assert result["verdict"] == "H1'"


def test_tolerance_and_offset_not_loosened():
    """Constants are pinned; an out-of-range confined Cd grades not-H1'; loosening would flip it.

    Scenario: Tolerance and offset band are pinned and not loosened.
    """
    # Named constants pinned to their stated values (a PR that widens them is caught here).
    assert SPHERE_CONFINEMENT_OFFSET_BAND == (0.03, 0.06)
    assert SPHERE_LITERATURE_TOL == 0.05
    assert LITERATURE_CD == 1.087

    # The single medium-grid CV Cd 1.18 does NOT grade H1' (bracket [1.113, 1.146], 1.146 > 1.141).
    medium = grade_sphere_cd_confinement_corrected(1.18)
    assert medium["verdict"] == "not H1'"
    assert medium["within"] is False

    # A clearly-high confined Cd is also rejected.
    assert grade_sphere_cd_confinement_corrected(1.30)["verdict"] == "not H1'"

    # The guard has teeth: loosening the tolerance to +/-10% WOULD admit 1.18 -> so the pinned
    # 5% must not be widened (this demonstrates the not-loosened invariant, it does not change it).
    loosened = grade_sphere_cd_confinement_corrected(1.18, tol=0.10)
    assert loosened["verdict"] == "H1'"


def test_tolerance_edge_is_deterministic():
    """A bracket endpoint exactly at the tolerance edge is decided inclusively (documented).

    Scenario: Tolerance-edge boundary case is decided deterministically.
    """
    # Construct cd so the (single-offset) isolated value equals the upper tol edge exactly:
    # cd / (1 + 0.03) == 1.087 * 1.05  ->  cd = 1.087 * 1.05 * 1.03
    cd_edge = LITERATURE_CD * (1 + SPHERE_LITERATURE_TOL) * 1.03
    at_edge = grade_sphere_cd_confinement_corrected(cd_edge, offset_band=(0.03, 0.03))
    assert at_edge["isolated_bracket"][1] == pytest.approx(
        LITERATURE_CD * (1 + SPHERE_LITERATURE_TOL), abs=1e-9
    )
    assert at_edge["within"] is True  # inclusive edge
    # A hair above the edge falls outside.
    just_over = grade_sphere_cd_confinement_corrected(
        cd_edge * (1 + 1e-6), offset_band=(0.03, 0.03)
    )
    assert just_over["within"] is False


def test_bad_inputs_raise():
    """Non-positive Cd or a degenerate/negative offset band is rejected, not silently mis-graded."""
    with pytest.raises(ValueError):
        grade_sphere_cd_confinement_corrected(0.0)
    with pytest.raises(ValueError):
        grade_sphere_cd_confinement_corrected(
            1.131, offset_band=(0.06, 0.03)
        )  # misordered
    with pytest.raises(ValueError):
        grade_sphere_cd_confinement_corrected(1.131, tol=-0.01)


@pytest.mark.requires_plotfile
def test_cv_regrade_is_traceable():
    """Companion: the CV extractor reproduces the pinned medium Cd; the H1' verdict is on Richardson.

    Scenario: Companion re-grade verifies CV extraction traceability (verdict stays on Richardson).

    The medium single grid (~1.18) does NOT grade H1' (bracket [1.113, 1.146], 1.146 > 1.141) — the
    literature verdict rests on the two-grid Richardson value 1.131, which a single plotfile cannot
    reproduce. This test therefore verifies *extraction traceability* only, not the verdict.
    """
    plt = _sphere_plt("medium")
    # method="cv" (NOT the marker default ~0.45) — guard the marker/CV confusion.
    cv = extract_sphere_cd(plt, method="cv", x_inlet=2.0, x_outlet=8.0)["cd"]
    direct = sphere_cv_drag_cd(plt, x_inlet=2.0, x_outlet=8.0)["cd"]
    assert cv == pytest.approx(
        direct, rel=1e-9
    )  # the entry point delegates to the CV core
    assert cv == pytest.approx(1.18, abs=0.05)  # pinned committed medium CV value

    # Feeding the single medium value to the grade yields not-H1' (verdict belongs to Richardson).
    assert grade_sphere_cd_confinement_corrected(cv)["verdict"] == "not H1'"
