"""The sinusoidal flapping waveform is this project's, not van Veen et al. (2022)'s (issue #142).

The paper supplies the axes, the rotation order, the force normalization and the quasi-steady
model. Each of its simulations is a single stroke at a constant angle of attack; it prescribes no
flapping waveform. These tests keep the waveform from being attributed to the paper again, and
keep the citations that are correct.
"""

import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from mosquito_cfd.benchmarks import wing_kinematics

_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_convention_page_separates_geometric_pitch_from_angle_of_attack():
    """Scenario: the page distinguishes pitch from angle of attack."""
    page = _read("docs/coordinate-convention.md")
    flat = _flat(page)
    # One paragraph makes the statement. Each part is looked for inside it: the page mentions
    # `decompose_wing_force` and "geometric pitch" elsewhere too, which must not satisfy this.
    start = page.index("**Pitch and angle of attack.**")
    statement = _flat(page[start : page.index("\n\n", start)])
    assert "is the wing's **geometric pitch**" in statement
    assert "the angle of attack is `|α|`" in statement
    assert "`decompose_wing_force` derives the angle of attack" in statement
    assert "only while the wing moves in the positive stroke direction" in statement
    assert "| **α** geometric pitch |" in page
    # The kinematics table is located by its header, which must exist, and no longer has a
    # column presenting the waveform as van Veen's.
    headers = [
        ln for ln in page.splitlines() if ln.startswith("| Angle | Rotation axis |")
    ]
    assert len(headers) == 1, "kinematics table header not found exactly once"
    assert "van Veen" not in headers[0]
    table = page[page.index(headers[0]) :]
    table = table[: table.index("\n\n")]
    assert "φ_amp·sin(ωt)" in table and "α_amp·cos(ωt)" in table
    assert "angle of attack" not in table
    # The citations that are correct stay: axes, rotation order, normalization, hinge.
    assert "# Wing coordinate convention (van Veen 2022 / Bomphrey 2017)" in page
    assert "Sourced verbatim from van Veen 2022 §2.4" in flat
    assert "van Veen §2.4" in flat  # the rotation order
    assert "van Veen (2022, eq 1.1) normalization" in flat
    assert "#142" in flat


def test_python_mirror_does_not_attribute_the_waveform():
    """``euler_angles`` describes a generic waveform; the rotation keeps its van Veen citation."""
    doc = _flat(wing_kinematics.euler_angles.__doc__)
    assert "van Veen kinematics" not in doc
    assert doc.startswith("Generic sinusoidal validation kinematics")
    assert "not from van Veen" in doc
    module_doc = _flat(wing_kinematics.__doc__)
    assert "pitch/angle-of-attack" not in module_doc
    assert "geometric pitch" in module_doc
    assert "angle-of-attack" not in _flat(wing_kinematics.rotation_matrix.__doc__)
    # Keep-list: the rotation order and the axes are the paper's.
    assert "van Veen 2022" in _flat(wing_kinematics.rotation_matrix.__doc__)
    assert "matches the paper verbatim (§2.4, fig 1f" in module_doc
    assert "van Veen quasi-steady model" in _flat(wing_kinematics.stroke_rate.__doc__)


@pytest.mark.parametrize(
    "rel, stale, required",
    [
        (
            "examples/flapping_wing/RESULTS.md",
            (
                "follows van Veen et al. (2022) sinusoidal kinematics",
                "## Kinematics (van Veen et al. 2022)",
                "van Veen Eq. 1–2",
                "| Stroke amplitude | 70 deg | 70 deg | MATCH |",
                "| Pitch amplitude | 45 deg | 45 deg | MATCH |",
                "| mid-stroke | MATCH |",
            ),
            (
                "generic sinusoidal validation kinematics",
                "## Kinematics (generic sinusoidal validation waveform)",
                "the paper does not simulate a flapping wing",
                "Rotation convention (T2a, van Veen)",  # keep-list: the rotation order
                "**van Veen (2022, JFM 936:A3) convention** (eq 1.1)",  # keep-list: F_ref
            ),
        ),
        (
            "examples/flapping_wing/figures/README.md",
            ("(the van Veen translational stroke)",),
            (
                "van Veen's rotation order",
                "**Axis convention** (van Veen 2022 / Bomphrey 2017",
            ),
        ),
        (
            "benchmarks/METHODS.md",
            ("φ=70°, α=45° (van Veen)",),
            ("φ=70°, α=45° (generic sinusoidal waveform)",),
        ),
        (
            "openspec/project.md",
            ("(van Veen kinematics)",),
            ("(generic sinusoidal kinematics, van Veen axis convention)",),
        ),
        (
            "examples/flapping_wing/inputs.3d.production",
            ("PRODUCTION (van Veen parameters)",),
            (
                "PRODUCTION (generic sinusoidal kinematics)",
                "non-dimensionalization matching van Veen et al. (2022)",  # keep-list
            ),
        ),
    ],
)
def test_documents_do_not_attribute_the_waveform(rel, stale, required):
    """Each document names the waveform as this project's and keeps its correct citations."""
    flat = _flat(_read(rel))
    for phrase in stale:
        assert phrase not in flat, f"{rel}: stale attribution {phrase!r}"
    for phrase in required:
        assert phrase in flat, f"{rel}: missing {phrase!r}"


def test_k1_figure_title_changes_and_its_curves_do_not(tmp_path, monkeypatch):
    """K1 plots the same two curves as before; only the title stops citing the paper."""
    script = _ROOT / "examples/flapping_wing/generate_all_figures.py"
    spec = importlib.util.spec_from_file_location("gaf_k1", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    real_close = plt.close
    figures = []
    monkeypatch.setattr(mod.plt, "close", lambda fig=None: figures.append(fig))
    mod.plot_k1_kinematics(tmp_path)
    try:
        (fig,) = figures
        ax_stroke, ax_pitch = fig.axes
        title = ax_stroke.get_title()
        assert "van Veen" not in title
        assert "generic sinusoidal" in title.lower()
        assert "phi_amp = 70 deg" in title and "alpha_amp = 45 deg" in title
        # The plotted data are the waveform as it was before the relabel, computed independently.
        t = np.linspace(0, 1.0, 1000)
        (stroke,) = [ln for ln in ax_stroke.lines if ln.get_label() == "Stroke φ(t)"]
        (pitch,) = [ln for ln in ax_pitch.lines if ln.get_label() == "Pitch α(t)"]
        np.testing.assert_array_equal(stroke.get_xdata(), t)
        np.testing.assert_allclose(
            stroke.get_ydata(), 70.0 * np.sin(2 * np.pi * t), rtol=0, atol=1e-12
        )
        np.testing.assert_allclose(
            pitch.get_ydata(), 45.0 * np.cos(2 * np.pi * t), rtol=0, atol=1e-12
        )
    finally:
        for fig in figures:
            real_close(fig)
    assert (tmp_path / "fig_kinematics.png").exists()
    assert b"/CreationDate" not in (tmp_path / "fig_kinematics.pdf").read_bytes()


def test_validation_deck_is_deliberately_untouched():
    """``inputs.3d.validation`` still says "van Veen kinematics": its hash is pinned by the run
    metadata, so its comment is left as it is and is the one known exception."""
    import hashlib
    import json

    deck = _ROOT / "examples/flapping_wing/inputs.3d.validation"
    meta = json.loads(_read("examples/flapping_wing/run_metadata_t2a.json"))
    assert meta["inputs"]["hash"] == hashlib.sha256(deck.read_bytes()).hexdigest()
    assert "prescribed van Veen kinematics" in deck.read_text(encoding="utf-8")


def test_reynolds_row_quotes_the_papers_range():
    """The paper's mid-span Reynolds range is 36-252 (section 2.6, p. A3-18), not 100-500."""
    flat = _flat(_read("examples/flapping_wing/RESULTS.md"))
    assert "| Re (midspan) | ~100 | 36–252 (§2.6) | within the paper's range |" in flat
    assert "100–500" not in flat
