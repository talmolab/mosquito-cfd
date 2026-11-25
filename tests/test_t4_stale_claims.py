"""No document states a T4 result the corrected van Veen model does not support (design D13).

One case per document, each with a positive anchor so the guard cannot pass on an empty or
unrelated file. The guard itself is in ``_stale_claims``; this file also proves its polarity on
the sentences review round 3 listed.
"""

import re
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
    "The chord question is unsettled.",
    "CF_chord drops 66.5 % and CF_normal is grid-settled.",
    "T4_NORMAL_MAG_TOL is resolved from its sourced inputs.",
    "This PR closes #401.",
    "The viscosity is 0.115 % of that.",
    "Coarse-grid under-resolution was a major contributor to the #40 chord excess.",
    "T4 doesn’t resolve the chord PARTIAL.",
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
    # A negation after the claim, or in another sentence, does not excuse it.
    "T4 resolves the chord PARTIAL, so #40 is no longer blocking.",
    "The CFD chord is no longer far from the model: T4 resolves the PARTIAL.",
    "(The grid is not converged.) T4 resolves the chord PARTIAL.",
    # A colon between a claim and what it is about does not hide it.
    "#40: resolved.",
    "#40: closed",
    "Issue #40: done.",
    "Closes: #40",
    "The reading is pending: #133.",
    "The chord: explained by the model.",
    "The chord PARTIAL: resolved.",
    "CF_chord_PARTIAL is resolved.",
    # Issue references are usually links; the URL does not hide the state word.
    "[#40](https://github.com/talmolab/mosquito-cfd/issues/40) is closed.",
    "The reading is pending [#133](https://github.com/talmolab/mosquito-cfd/issues/133).",
    "[#133](https://github.com/talmolab/mosquito-cfd/issues/133) is pending.",
)

# Structure matters: a negation in a neighbouring heading, bullet, table cell or paragraph must
# not excuse a claim. Each of these survived the first version of the guard (review of the PR).
_MUST_FAIL_STRUCTURED = {
    "heading then a negated paragraph": (
        "### T4 resolves the chord PARTIAL (#40)\n\nThis was not expected.\n"
    ),
    "bullet under a negated label": (
        "**Reported, not gated:**\n\n- T4 resolves the chord PARTIAL\n- another item\n"
    ),
    "two bullets, the second negated": (
        "- T4 resolves the chord PARTIAL\n- this one is not graded\n"
    ),
    "table row with a negated cell": (
        "| T4 | resolves the chord PARTIAL (#40) | not graded |\n"
    ),
    "table row next to a negated row": (
        "| CF_chord | 0.41 | not explained |\n"
        "| T4 | resolves the chord PARTIAL | graded |\n"
    ),
    "blockquote": "> T4 resolves the\n> chord PARTIAL\n>\n> It is not graded.\n",
    # The negation comes first here, so only the block boundary keeps it from excusing the claim.
    "negated cell before the claim cell": (
        "| not graded | T4 resolves the chord PARTIAL (#40) |\n"
    ),
    "negated bullet before the claim bullet": (
        "- this one is not graded\n- T4 resolves the chord PARTIAL\n"
    ),
    "negated paragraph running into a heading": (
        "This part is not final\n### T4 resolves the chord PARTIAL\n"
    ),
    # The claim and what it is about sit in different cells, or under a heading or label.
    "status table: issue and state in two cells": "| #40 | resolved |\n",
    "status table: closed": "| #40 | closed |\n",
    "status table: PARTIAL resolved": "| Chord PARTIAL | resolved |\n",
    "status table: chord explained": "| CF_chord | explained by the model |\n",
    "status table: pending": "| pending | #133 |\n",
    "linked issue in a status table": (
        "| [#40](https://github.com/talmolab/mosquito-cfd/issues/40) | closed |\n"
    ),
}

# Known misses, pinned so nobody assumes the guard covers them: a claim whose subject is in a
# heading, a label line or a parent list item above it. Connecting them was tried and removed
# (it reached only the first block after the label and rejected true sentences across the join).
_KNOWN_STRUCTURAL_MISSES = {
    "heading names the issue": "### #40\n\nResolved.\n",
    "heading names the chord": "### Chord\n\nExplained by the model.\n",
    "nested list item": "- #40\n  - resolved\n",
    "label line then a bullet": "**Chord PARTIAL:**\n\n- resolved\n",
}

# True statements that sit under a heading or label naming the issue: they must be accepted.
_TRUE_UNDER_A_HEADING = {
    "heading with the issue, paragraph about grids": (
        "### Chord question (#40)\n\nResolved on both grids, the vortex is sharper.\n"
    ),
    "heading with the issue, progress note": "### Open question (#40)\n\nDone so far: nothing.\n",
    "label with the issue, follow-ups": (
        "Follow-ups to #133:\n\nPending items are listed in #154.\n"
    ),
    "T4 heading, unrelated resolved": (
        "### T4 per-component decomposition\n\nThe sign convention was resolved in #109.\n"
    ),
    "heading directly above its paragraph": (
        "### Chord question (#40)\nResolved on both grids, the vortex is sharper.\n"
    ),
    "sibling bullets": "- Issues\n  - tracked in #40\n  - done: the sign fix\n",
}

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


@pytest.mark.parametrize("name", list(_MUST_FAIL_STRUCTURED))
def test_guard_reads_document_structure(name):
    """A negation in a neighbouring block does not excuse a stale claim."""
    assert stale_claims(_MUST_FAIL_STRUCTURED[name]), name


@pytest.mark.parametrize("name", list(_KNOWN_STRUCTURAL_MISSES))
def test_guard_does_not_connect_a_claim_to_a_heading_or_label(name):
    """Pinned known misses: adding that connection back is a visible change."""
    assert stale_claims(_KNOWN_STRUCTURAL_MISSES[name]) == []


@pytest.mark.parametrize("name", list(_TRUE_UNDER_A_HEADING))
def test_guard_accepts_true_statements_under_a_heading_naming_the_issue(name):
    """A heading or label is not joined to the text below it."""
    assert stale_claims(_TRUE_UNDER_A_HEADING[name]) == []


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
    # Comments that are not on consecutive lines are separate: a distant "not" excuses nothing.
    apart = "x = 1  # not used\ny = 2\nz = 3\nw = 4  # T4 resolves the chord PARTIAL\n"
    assert stale_claims(python_prose(apart))
    # A phrase wrapped over two comment lines is found only if the lines are joined.
    phrase = "x = 1\n# The chord sits close to\n# the model.\n"
    assert stale_claims(python_prose(phrase))


def _results_md() -> str:
    return (_ROOT / "examples/flapping_wing/RESULTS.md").read_text(encoding="utf-8")


def _figures_readme() -> str:
    return (_ROOT / "examples/flapping_wing/figures/README.md").read_text(
        encoding="utf-8"
    )


_LOG_HEADER = "## Reconciliation log"


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _aero_roadmap() -> str:
    """The aerodynamics roadmap without its dated reconciliation log (a record, not rewritten)."""
    text = _read("docs/aerodynamics_validation/roadmap.md")
    assert text.count(_LOG_HEADER) == 1, (
        "reconciliation-log header not found exactly once"
    )
    return text[: text.index(_LOG_HEADER)]


def _aero_roadmap_log() -> str:
    text = _read("docs/aerodynamics_validation/roadmap.md")
    return text[text.index(_LOG_HEADER) :]


def _slug(header: str) -> str:
    """GitHub's anchor for a Markdown header line."""
    title = header.lstrip("#").strip().lower()
    return re.sub(r"[^\w\- ]", "", title).replace(" ", "-")


def _t4_anchor() -> str:
    """Markdown link target of the T4 subsection of RESULTS.md, from its header as written today."""
    header = next(
        ln
        for ln in _results_md().splitlines()
        if ln.startswith("### T4 per-component decomposition")
    )
    # The closing parenthesis is part of the match: a link to a shorter, stale anchor that is a
    # prefix of this one must not satisfy it.
    return "RESULTS.md#" + _slug(header) + ")"


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
    "aerodynamics roadmap": (_aero_roadmap, ("| ✅ **T4**", "#40 is open")),
    "prelim_sweep_fine/README.md": (
        lambda: _read("examples/prelim_sweep_fine/README.md"),
        (_t4_anchor,),
    ),
    "force_surrogate/roadmap.md": (
        lambda: _read("docs/force_surrogate/roadmap.md"),
        ("`CF_chord`", "0.923"),
    ),
    "fine-grid-pilot-report.md": (
        lambda: _read("docs/force_surrogate/fine-grid-pilot-report.md"),
        ("`CF_chord`",),
    ),
    "CHANGELOG.md": (lambda: _read("docs/CHANGELOG.md"), ("#141",)),
    # Its §2/§3 discuss the CFD chord vs the QS model, where such a claim is likeliest to creep in.
    "future-work.md": (
        lambda: _read("docs/future-work.md"),
        ("`CF_chord`", "#40"),
    ),
}


@pytest.mark.parametrize("name", list(_DOCUMENTS))
def test_no_stale_t4_claim(name):
    """Scenario: claims the corrected model no longer supports are absent from every doc."""
    loader, anchors = _DOCUMENTS[name]
    text = loader()
    for anchor in anchors:
        anchor = anchor() if callable(anchor) else anchor
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
    # Both normal curves dip below zero before each reversal (pinned in the RESULTS test), and
    # the CFD's second peak is the lower one.
    assert "small negative dip before each reversal" in section
    assert "keeps one sign" not in section and "keep one sign" not in section
    assert "The CFD's second normal peak is lower than its first" in section
    assert "at mid-stroke is its Wagner term changing sign" in section
    # Grid and tier labels ("256³", "T3c/#52") are not decimals; a model or CFD value would be.
    assert re.findall(r"\d+\.\d+", section) == []
    # The sign anchor other tests rely on stays on the rewritten row.
    assert "coordinate-convention.md#force-and-moment-sign" in section


def test_slug_matches_github_for_a_known_header():
    """The anchor helper reproduces the one link RESULTS.md already uses to its own header."""
    header = "### Added-mass-subtracted body-frame diagnostic (#40 cheap interim)"
    assert (
        _slug(header) == "added-mass-subtracted-body-frame-diagnostic-40-cheap-interim"
    )
    assert f"(#{_slug(header)})" in _results_md()
    assert header in _results_md()


def test_roadmap_t4_row_gives_the_verdict_in_words():
    """The roadmap's T4 row states the verdict and points to RESULTS.md for the numbers."""
    text = _read("docs/aerodynamics_validation/roadmap.md")
    row = next(ln for ln in text.splitlines() if ln.startswith("| ✅ **T4**"))
    assert "PR [#" in row
    assert "translational + added-mass + Wagner" in row and "Fig 13" in row
    assert "does not resolve the T2a CF_chord PARTIAL" in row
    assert "does not explain" in row and "#40 is open" in row
    assert "a finer run is [#165](" in row and "#50" not in row
    assert "RESULTS.md" in row
    # The only decimal in the row is the CFD chord's GCI_fine, pinned by the T3c test.
    assert set(re.findall(r"\d+\.\d+", row)) == {"27.6"}
    assert "digitize van Veen Fig 3–4" not in text


def test_roadmap_log_is_kept_and_carries_the_dated_addendum():
    """The dated log is a record: its T4 phase note stays, marked superseded, plus an addendum."""
    log = _aero_roadmap_log()
    assert "peak-PHASE reported, not gated" in log
    assert "NOT a loosened tolerance" in log
    phase_note = log[log.index("### T4 normal peak-PHASE reported, not gated") :]
    phase_note = phase_note[: phase_note.index("\n### ", 1)]
    assert "**Superseded figure (2026-11-17).**" in phase_note
    addendum = log[log.index("### T4 re-graded on the corrected model (2026-11-17") :]
    for phrase in (
        "#141",
        "#133",
        "RESULTS.md",
        "#40 is open",
        "tolerance is unchanged",
    ):
        assert phrase in addendum, phrase


@pytest.mark.parametrize("phrase", ["deferred to T4", "rotational drag"])
def test_t4_is_described_as_delivered(phrase):
    """The convention page and the module docstring describe T4 as delivered, with its real terms."""
    import ast

    convention = _read("docs/coordinate-convention.md")
    assert "decompose_wing_force" in convention
    assert phrase not in convention
    source = _read("src/mosquito_cfd/benchmarks/flapping_wing.py")
    docstring = ast.get_docstring(ast.parse(source))
    assert "decompose_wing_force" in docstring
    assert phrase not in docstring


def test_changelog_states_what_ships():
    """Unreleased entries describe the shipped state, and one entry describes this change."""
    changelog = " ".join(_read("docs/CHANGELOG.md").split())
    unreleased = changelog[changelog.index("## [Unreleased]") :]
    later = unreleased.find("## [", 5)  # the next release header, if any
    unreleased = unreleased if later < 0 else unreleased[:later]
    entry = next(e for e in unreleased.split(" - ") if "#141" in e)
    for phrase in (
        "#133",
        "`S_cy`",
        "degrees",
        "angle of attack",
        "#154",
        "#155",
        "#156",
    ):
        assert phrase in entry, phrase
    assert "`normal_curve_corr`" in entry and "tests/fixtures/van_veen_2022/" in entry
    # Superseded statements are corrected, not annotated.
    for stale in (
        "The T4 figure flags the normal",
        "The figure and RESULTS.md flag this, for the chord comparison",
        "it is fed the signed pitch rather than the angle of attack",
        "mark the chord comparison and the T4 status pending",
    ):
        assert stale not in changelog, stale


def test_fine_readme_points_to_results_for_the_t4_numbers():
    """The fine-corpus README gives the T4 verdict in words and links the T4 subsection."""
    readme = _read("examples/prelim_sweep_fine/README.md")
    bullet = readme[readme.index("**Comparison with a model, not a measurement**") :]
    bullet = bullet[: bullet.index("\n- **")]
    assert _t4_anchor() in bullet
    assert "not explained" in bullet
    assert re.findall(r"\d+\.\d+", bullet) == []
