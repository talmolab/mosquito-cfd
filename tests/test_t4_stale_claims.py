"""No document states a T4 result the corrected van Veen model does not support (design D13).

One case per document, each with a positive anchor so the guard cannot pass on an empty or
unrelated file. The guard itself is in ``_stale_claims``; this file also proves its polarity on
the sentences review round 3 listed.
"""

from pathlib import Path

import pytest
from _stale_claims import python_prose, stale_claims

_ROOT = Path(__file__).resolve().parents[1]

# The docs are required to make these statements, so the guard must accept them.
_MUST_PASS = (
    "T4 does not fully resolve the CF_chord PARTIAL.",
    "The chord PARTIAL remains unresolved by T4.",
    "It is neither resolved by T4 nor explained by the model.",
    "T4 never resolves the chord PARTIAL.",
    "T4 can't resolve the chord PARTIAL.",
    "The CFD chord is not fully explained by the model.",
    "T4 does not resolve the CF_chord PARTIAL; the model does not explain the CFD chord.",
    "**#40 remains open** — T3b advances it, does not resolve it.",
    "#40 advanced, not resolved",
    "the peak ratio is drop_frac ≈ −0.42",
)

# Statements the corrected model does not support: each must be reported.
_MUST_FAIL = (
    "T4 resolves the T2a PARTIAL.",
    "T4 resolved the chord PARTIAL (#40).",
    "This is the resolution of the CF_chord PARTIAL by T4.",
    "T4 settles the chord question.",
    "The model accounts for the chord excess.",
    "The CFD chord total now sits close to the model.",
    "The chord total (0.41) now sits very close to the model.",
    "The chord is in close agreement with the model.",
    "The CFD chord converges to the QS model.",
    "The CFD chord **converges toward the\nmodel** across all three grids.",
    "The total-chord should never have been compared to the translational-only 0.3.",
    "The PARTIAL was an apples-to-oranges comparison.",
    "The CFD is approaching the physical chord target.",
    "CF_chord is ~5 % off the QS-model target.",
    "CF_chord is +115 % off the target.",
    "The chord is 4–5 % off.",
    "The issue #40 is done.",
    "#40 closed.",
    "T4 does not close #40.",
    "The reading is pending [#133](https://example.invalid).",
    "Added-mass (+) and Wagner (−) roughly **cancel** in the wing-normal.",
    "It sits below the full QS model total.",
    "The corrected chord peak is near 0.18.",
    "The target range is ~0.3–0.43.",
    "The model normal peak is 2.48.",
    "The model chord peak is 0.43.",
    "The translational-chord peak is 0.42.",
    "The phase gap is 0.055 cycle.",
    "The phase gap is ~0.058 cycle.",
)

# Known miss, kept here so nobody assumes the guard covers it: "agrees" is needed for the
# normal force, so there is no pattern for it. The deletion list and the repo-wide grep cover it.
_KNOWN_MISS = "CF_chord agrees with the van Veen model."


@pytest.mark.parametrize("sentence", _MUST_PASS)
def test_guard_accepts_required_negated_statements(sentence):
    """Negated statements, and unrelated numbers that only look stale, are accepted."""
    assert stale_claims(sentence) == []


@pytest.mark.parametrize("sentence", _MUST_FAIL)
def test_guard_reports_each_stale_statement(sentence):
    """Each stale statement is reported, in plain, bold and line-wrapped form."""
    assert stale_claims(sentence), sentence
    assert stale_claims(f"**{sentence}**"), sentence
    assert stale_claims(sentence.replace(" ", "\n", 2)), sentence


def test_guard_known_miss_is_recorded():
    """The one phrasing with no pattern is pinned, so adding a pattern for it is a visible change."""
    assert stale_claims(_KNOWN_MISS) == []


def test_python_prose_joins_wrapped_comments_and_reads_docstrings():
    """A claim wrapped over two comment lines, or sitting in a docstring, is found."""
    wrapped = "x = 1  # T4 resolves the chord\n# PARTIAL by building the model.\n"
    assert stale_claims(python_prose(wrapped))
    docstring = 'def f():\n    """The chord converges to the model."""\n'
    assert stale_claims(python_prose(docstring))
    assert stale_claims(python_prose("x = 1  # an ordinary comment\n")) == []


def _results_md() -> str:
    return (_ROOT / "examples/flapping_wing/RESULTS.md").read_text(encoding="utf-8")


def _figures_readme() -> str:
    return (_ROOT / "examples/flapping_wing/figures/README.md").read_text(
        encoding="utf-8"
    )


def _flapping_wing_prose() -> str:
    source = (_ROOT / "src/mosquito_cfd/benchmarks/flapping_wing.py").read_text(
        encoding="utf-8"
    )
    return python_prose(source)


# name -> (loader, anchors that must be present in the raw text)
_DOCUMENTS = {
    "RESULTS.md": (
        _results_md,
        (
            "### T4 per-component decomposition — validated against van Veen's "
            "quasi-steady model",
            "#40 is open",
        ),
    ),
    "flapping_wing.py": (
        _flapping_wing_prose,
        ("decompose_wing_force", "issue #40"),
    ),
    "figures/README.md": (
        _figures_readme,
        ("| `fig_force_decomposition` |", "#40 is open"),
    ),
}


@pytest.mark.parametrize("name", list(_DOCUMENTS))
def test_no_stale_t4_claim(name):
    """Scenario: claims the corrected model no longer supports are absent from every doc."""
    loader, anchors = _DOCUMENTS[name]
    text = loader()
    for anchor in anchors:
        assert anchor in text, (
            f"{name}: anchor {anchor!r} missing; the guard would be vacuous"
        )
    hits = stale_claims(text)
    assert not hits, f"{name}: " + "; ".join(f"[{n}] {s[:140]}" for n, s in hits)


def test_figures_readme_gives_the_t4_verdict_in_words():
    """The figures README states no T4 number: RESULTS.md is the one place they are stated."""
    import re

    text = _figures_readme()
    start = text.index("## Per-component decomposition (T4)")
    section = text[start : text.index("\n## ", start + 1)]
    assert "RESULTS.md" in section
    assert "not explained by the model" in section
    assert "within the graded tolerance" in section
    # Grid and tier labels ("256³", "T3c/#52") are not decimals; a model or CFD value would be.
    assert re.findall(r"\d+\.\d+", section) == []
    # The sign anchor other tests rely on stays on the rewritten row.
    assert "coordinate-convention.md#force-and-moment-sign" in section
