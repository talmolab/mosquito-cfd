"""Guard the new-convention deck + the coordinate-convention doc (Tier T2a).

Cluster-free string/key checks: the validation deck must encode the van Veen convention
(infinite-span periodic in y, z wall->outflow, span-along-y hinge, ns.init_iter=2), and the
canonical convention doc must state the axes + normalization. Nothing here runs the solver.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_DECK = Path("examples/flapping_wing/inputs.3d.validation")
_DOC = Path("docs/coordinate-convention.md")
_FIG_SCRIPTS = [
    Path("examples/flapping_wing/generate_all_figures.py"),
    Path("examples/flapping_wing/visualize.py"),
    Path("examples/flapping_wing/generate_validation_figures.py"),
]


def test_no_duplicate_rotation_matrix_in_figure_scripts():
    """DRY: figure scripts use the canonical kinematics mirror, not a re-implemented rotation.

    The single code source of R(t) is mosquito_cfd.benchmarks.wing_kinematics. A figure script may
    keep a thin `rotation_matrix` wrapper, but must NOT re-derive the matrix inline.
    """
    uses_mirror = any(
        f.exists() and "wing_kinematics" in f.read_text(encoding="utf-8")
        for f in _FIG_SCRIPTS
    )
    assert uses_mirror, (
        "no figure script imports the canonical wing_kinematics rotation"
    )


def test_no_legacy_rotation_composition_anywhere():
    """Tree-wide: the OLD span-∥-z composition (R = Rz·Ry(θ)·Rx(α)) lives nowhere in src/tests/examples.

    Guards against a legacy rotation drifting back into ANY .py (the figure-only scan missed the
    stale copy that used to live in test_geometry.py — B4). Scans for the old composition's
    tell-tale products; the new van Veen composition (Rz·Ry(α)·Rx(θ)) has different products
    (``cp*ca``, ``cp*sa*st``) so the C++-conformance transcription is not flagged.
    """
    self_path = Path(__file__).resolve()
    tell_tale = ("sp*st*sa", "cp*st*ca", "sp * st * sa", "cp * st * ca")
    for root in (Path("src"), Path("tests"), Path("examples")):
        for f in root.rglob("*.py"):
            if (
                f.resolve() == self_path
            ):  # this guard file lists the literals as search strings
                continue
            src = f.read_text(encoding="utf-8")
            for lit in tell_tale:
                assert lit not in src, (
                    f"{f} contains the OLD span-∥-z rotation composition ({lit!r}); "
                    f"use the canonical mosquito_cfd.benchmarks.wing_kinematics mirror"
                )


def _kv(text: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*(?:#.*)?$", text, re.MULTILINE)
    assert m is not None, f"key {key!r} not found in the deck"
    return m.group(1).strip()


@pytest.mark.skipif(not _DECK.exists(), reason="validation deck not present")
def test_deck_infinite_span_periodic():
    """Deck: periodic in y (span, retained), outflow x AND z (z wall->outflow), init_iter=2, hinge on y."""
    text = _DECK.read_text()
    assert _kv(text, "geometry.is_periodic") == "0 1 0"  # periodic in y (span)
    assert (
        _kv(text, "ns.lo_bc") == "2 0 2"
    )  # outflow x, periodic y, OUTFLOW z (was wall 4)
    assert _kv(text, "ns.hi_bc") == "2 0 2"
    assert (
        _kv(text, "ns.init_iter") == "2"
    )  # velocity fix -> non-zero plotfile velocity
    # Hinge (root) is on the span (y) end, not the legacy z=2.5 span-z artifact.
    assert float(_kv(text, "particle_inputs.hinge_y")) == pytest.approx(0.5)
    assert float(_kv(text, "particle_inputs.hinge_z")) == pytest.approx(4.0)
    # Plot output stays enabled so the re-run persists visualization plotfiles.
    assert int(_kv(text, "amr.plot_int")) > 0


@pytest.mark.skipif(not _DOC.exists(), reason="coordinate-convention doc not present")
def test_coordinate_convention_doc_states_axes():
    """The canonical convention doc states the van Veen axes, Euler order, and normalization."""
    text = _DOC.read_text(encoding="utf-8").lower()
    assert "x" in text and "chord" in text
    assert "y" in text and "span" in text
    assert "wing-normal" in text or "normal" in text
    # Euler order and normalization present.
    assert "rz(" in text and "ry(" in text  # R = Rz(phi) Ry(alpha) ...
    assert "s_yy" in text or "½·ρ·ω²·s_yy" in text or "f_ref" in text
    # Cites both sources.
    assert "van veen" in text and "bomphrey" in text
