"""Guard: the false "IAMReX diffused-IB force ~2.4x low" claim stays retired.

standardize-force-normalization (#32) established that the wing/Track-B "~2.4x" was a
NORMALIZATION-convention mismatch (peak-tip vs van Veen radius of gyration, 3.12x), NOT a
diffused-IB force deficit and NOT the sphere's real 2.64x extraction bug (T1b/#29). This
test prevents the false claim from creeping back into the wing/Track-B figure files, while
leaving the legitimate sphere-extraction story (#29 docs) and the "~2.4 min/wingbeat" CFD
cost reference untouched.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Wing + Track-B figure files: the diffused-IB force claim must be entirely absent.
_CLAIM_FREE_FILES = [
    "src/mosquito_cfd/force_surrogate/evidence_figure.py",
    "examples/prelim_sweep/README.md",
    "examples/prelim_sweep/figures/evidence_figure_metrics.json",
    "examples/flapping_wing/RESULTS.md",
]

# Affirmative phrasings that must not reappear (the roadmap may discuss the *retraction*).
_FORBIDDEN_AFFIRMATIVE = [
    "still applies",
    "dominated by the ~2.4× diffused-ib",
    "force is systematically",
    "force output is systematically",
]


def test_wing_and_trackb_files_have_no_diffused_ib_force_claim():
    """The wing/Track-B figure files carry no diffused-IB force claim or correction factor."""
    for rel in _CLAIM_FREE_FILES:
        text = (REPO / rel).read_text(encoding="utf-8").lower()
        assert "diffused-ib" not in text, (
            f"{rel} still references a diffused-IB force claim"
        )
        # no post-hoc correction factor applied to coefficients
        assert not re.search(r"[×x]\s*2\.4\b", text), (
            f"{rel} applies a ~2.4x correction"
        )
        assert "2.64" not in text, f"{rel} conflates the sphere 2.64x extraction factor"


def test_force_surrogate_roadmap_has_no_affirmative_underestimate_claim():
    """The force-surrogate roadmap may note the retraction, not assert the false claim."""
    text = (
        (REPO / "docs/force_surrogate/roadmap.md").read_text(encoding="utf-8").lower()
    )
    for phrase in _FORBIDDEN_AFFIRMATIVE:
        assert phrase not in text, f"roadmap still affirms: {phrase!r}"
    # the legitimate CFD-cost reference (~2.4 min/wingbeat) must survive
    assert "2.4 min" in text


def test_roadmap_t4_row_flipped_and_reframed():
    """Tier T4 is marked done, its body carries the {transl, AM, Wagner} / Fig 13 reframe, and no
    stale {rotational} / bare-"validated" / "digitize Fig 3–4" / "T4 is next" claim survives (T4)."""
    text = (REPO / "docs/aerodynamics_validation/roadmap.md").read_text(
        encoding="utf-8"
    )
    lines = text.splitlines()
    # The T4 row is marked ✅ and references its PR.
    t4_row = next(ln for ln in lines if ln.startswith("| ✅ **T4**"))
    assert "PR [#" in t4_row, "T4 row missing a PR reference"
    # Reframe present (van Veen's actual components + the correct figures).
    assert "translational + added-mass + Wagner" in text
    assert "Fig 13" in text
    # Stale framing gone: the old component list, the bare "earns the word validated", the
    # affirmative "digitize van Veen Fig 3–4", and "T4 … is next" must all be absent.
    assert "translational + rotational + added-mass" not in text
    assert "earns the word" not in text
    assert (
        "digitize van Veen Fig 3–4" not in text
    )  # negated "not a digitized Fig 3–4" is fine
    assert "#40) is next" not in text and "T4 … is next" not in text
    # The only new reconciliation-log entry is the phase-reported note (an evidence-based scoping
    # decision, NOT a loosened-tolerance relaxation).
    assert "peak-PHASE reported, not gated" in text
    assert "NOT a loosened tolerance" in text
