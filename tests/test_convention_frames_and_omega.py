"""The convention page names the frame of each force and writes ``ω_peak`` in ``F_ref`` (#181, #161).

``docs/coordinate-convention.md`` once said every reported force is wing-body-frame (#181); in fact
the corpus and surrogate ``CF_x..CF_z`` and the flapping-wing lab series are lab-frame. It also used
``ω`` both for ``2πf`` and for the peak stroke rate in ``F_ref`` (#161), which read literally makes
``F_ref`` 1.49x too small.

The text checks are pure functions of a string. They run on the live page and on a committed frozen
copy of the pre-change sections (``tests/fixtures/convention_page/pre_181_161.md``), on which each
must fail, so "the guard fails on the old wording" holds on every CI run.

The bare-``ω`` scan covers the page, ``examples/flapping_wing/RESULTS.md``, its figures README and
the effective coordinate-convention and flapping-wing-validation specs. ``src/`` is not scanned yet;
#202 tracks the remaining bare ``ω`` there and in the force-surrogate roadmap.

Spec: coordinate-convention "Project-wide axis convention matches van Veen 2022, documented
atomically" (scenarios "Each reported force quantity is named with its frame", "F_ref is written
with ω_peak, tied to the code and to the kinematics", "No bare ω in F_ref in the documents that
restate the normalization").
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from _readme_guards import _section
from _spec_claims import effective_spec, format_like
from test_coordinate_convention_sign import (
    _CORPUS_PARQUETS,
    _parquet_on_wing,
    flapping_series_on_wing,
)

from mosquito_cfd.benchmarks.wing_kinematics import stroke_rate
from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import (
    CHORD,
    R_GYRATION,
    RHO,
    SPAN,
    VALIDATED_F_STAR,
    VALIDATED_PHI_AMP_DEG,
)

_ROOT = Path(__file__).resolve().parents[1]
_DOC = _ROOT / "docs" / "coordinate-convention.md"
_FIXTURE = _ROOT / "tests" / "fixtures" / "convention_page" / "pre_181_161.md"
_RESULTS = _ROOT / "examples" / "flapping_wing" / "RESULTS.md"
_FIGURES_README = _ROOT / "examples" / "flapping_wing" / "figures" / "README.md"
_FORCE_SURROGATE_SPEC = _ROOT / "openspec" / "specs" / "force-surrogate" / "spec.md"

_FIXTURE_SOURCE_SHA = "246f0a0"
_ROTATION_DEG = 30.0

FORBIDDEN = (
    "forces are reported in the wing body frame",
    "Unlike the forces above",
    "body-frame forces",
)
# Phrases that put something in the wing frame. A sentence holding one of them together with the
# lab-frame CF_x..CF_z, or with "force" in general, must also name CF_chord (the contrast sentences
# do), so a reworded #181 claim cannot come back (PR review).
WING_FRAME_PHRASES = (
    "wing body frame",
    "wing frame",
    "wing-frame",
    "body frame",
    "body-frame",
)
# ω (or \omega) squared, then S_yy later in the same clause. ``ω_peak²`` does not match. Scanned on
# flattened text, so a formula wrapped across a line break is still seen.
BARE_OMEGA = re.compile(
    r"(?:ω|\\omega)\s*\)?\s*(?:²|\^\{?2\}?|\*\*2|<sup>2</sup>)[^.;,\n]{0,24}?S_?\{?yy"
)
_COMMENT = re.compile(r"(?s)<!--.*?-->")
# Abbreviations whose period must not end a sentence.
_ABBREVIATIONS = ("e.g.", "i.e.", "cf.", "vs.")
FWV = "flapping-wing-validation"
CC = "coordinate-convention"
# Here ω is the model's instantaneous stroke speed |φ̇| (van_veen_model.model_inputs), so
# ½ρω²S_yy is correct; the guard requires the match to still be there.
EXEMPT = "Van Veen quasi-steady force model, pinned and guarded"


# ---------------------------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------------------------


def _flat(text: str) -> str:
    return " ".join(_COMMENT.sub(" ", text).split())


def normalize(text: str) -> str:
    """Markdown emphasis, backticks and blockquote markers removed; whitespace collapsed.

    Underscore emphasis is stripped only when paired at word boundaries, so ``CF_chord``,
    ``F_ref`` and ``ω_peak`` survive. HTML comments are not on the page and are dropped.
    """
    text = _COMMENT.sub(" ", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)
    return " ".join(text.split())


def sentences(text: str) -> list[str]:
    """Normalized sentences.

    Splits on ``. `` or a bullet start, never on the ``..`` in ``CF_x..CF_z`` or after the
    abbreviations in ``_ABBREVIATIONS``.
    """
    text = _COMMENT.sub(" ", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "\x00", text)
    out: list[str] = []
    for chunk in text.split("\x00"):
        flat = normalize(chunk)
        for abbr in _ABBREVIATIONS:
            flat = flat.replace(abbr, abbr.replace(".", "\x01"))
        for s in re.split(r"(?<!\.)\.\s+", flat):
            s = s.replace("\x01", ".").strip()
            if s:
                out.append(s)
    return out


def _sec(page: str, heading: str) -> str:
    section, _ = _section(page, heading)
    return section


def _any_sentence(
    section: str, must: tuple[str, ...], must_not: tuple[str, ...] = ()
) -> bool:
    return any(
        all(m in s for m in must) and not any(n in s for n in must_not)
        for s in sentences(section)
    )


# --- frame checks (each takes the whole page text) -------------------------------------------


def body_frame_sentence(page: str) -> bool:
    return _any_sentence(
        _sec(page, "## Forces"),
        ("CF_chord", "CF_normal", "wing body frame"),
        ("lab-frame",),
    )


def lab_corpus_sentence(page: str) -> bool:
    return _any_sentence(
        _sec(page, "## Forces"),
        ("CF_x..CF_z", "lab-frame components of the IB force"),
        ("wing body frame",),
    )


def flapping_lab_sentence(page: str) -> bool:
    return any(
        ("plausibility_gate" in s or "fig_forces" in s)
        and "lab-frame components" in s
        and "wing body frame" not in s
        for s in sentences(_sec(page, "## Forces"))
    )


def no_contradicting_frame_sentence(page: str) -> bool:
    """No sentence puts ``CF_x..CF_z``, or forces in general, in the wing frame.

    A sentence that also names ``CF_chord`` is a contrast ("wing-frame CF_chord/CF_normal beside
    lab-frame CF_x..CF_z") and is allowed.
    """
    for s in sentences(page):
        low = s.casefold()
        if "CF_chord" in s or not any(p in low for p in WING_FRAME_PHRASES):
            continue
        if "CF_x..CF_z" in s or re.search(r"\bforces?\b", low):
            return False
    return True


def keeps_spanwise_drop(page: str) -> bool:
    return "intentionally dropped" in normalize(_sec(page, "## Forces"))


def no_forbidden_phrase(page: str) -> bool:
    flat = normalize(page).casefold()
    return not any(p.casefold() in flat for p in FORBIDDEN)


def moments_sentence(page: str) -> bool:
    return _any_sentence(
        _sec(page, "## Moments"), ("lab-frame components about the hinge", "CF_x..CF_z")
    )


FRAME_CHECKS = {
    "body_frame_sentence": body_frame_sentence,
    "lab_corpus_sentence": lab_corpus_sentence,
    "flapping_lab_sentence": flapping_lab_sentence,
    "keeps_spanwise_drop": keeps_spanwise_drop,
    "no_forbidden_phrase": no_forbidden_phrase,
    "no_contradicting_frame_sentence": no_contradicting_frame_sentence,
    "moments_sentence": moments_sentence,
}
# The old page already says the spanwise force is "intentionally dropped".
_PASSES_ON_OLD_PAGE = {"keeps_spanwise_drop"}


def _page() -> str:
    return _DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Scenario: Each reported force quantity is named with its frame
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FRAME_CHECKS))
def test_page_names_the_frame_of_each_force_family(name):
    assert FRAME_CHECKS[name](_page()), (
        f"{_DOC.name}: frame check {name} fails; see the coordinate-convention scenario "
        "'Each reported force quantity is named with its frame'"
    )


@pytest.mark.parametrize("name", sorted(set(FRAME_CHECKS) - _PASSES_ON_OLD_PAGE))
def test_frame_check_fails_on_the_pre_change_page(name):
    """The frozen pre-#181 copy fails every check that is new (negative control, every CI run)."""
    old = _FIXTURE.read_text(encoding="utf-8")
    assert _FIXTURE_SOURCE_SHA in old, "fixture must name its source commit"
    assert FRAME_CHECKS[name](old) is False, f"{name} passes on the pre-#181 fixture"


_LAB_FORCES = (
    "## Forces\n\nThe flapping-wing benchmark's `CF_chord`/`CF_normal` are in the **wing body "
    "frame**. The corpus `CF_x..CF_z` are lab-frame components of the IB force on the wing. "
    "The `plausibility_gate` input is lab-frame components of the IB force.{extra}\n"
)


@pytest.mark.parametrize(
    "extra",
    [
        " The corpus `CF_x..CF_z` are rotated into the wing frame by `R(t)ᵀ`.",
        " Forces are given in the wing body frame.",
        " All force coefficients are wing-frame (chord, normal).",
    ],
)
def test_contradicting_frame_sentence_is_rejected(extra):
    """Negative control: a reworded #181 claim added beside the correct sentences fails (PR review)."""
    page = _LAB_FORCES.format(extra=extra)
    assert no_contradicting_frame_sentence(_LAB_FORCES.format(extra="")) is True
    assert no_contradicting_frame_sentence(page) is False


def test_flapping_sentence_must_not_call_the_series_wing_frame():
    page = (
        "## Forces\n\nThe `plausibility_gate` input is lab-frame components, not the wing "
        "body frame.\n"
    )
    assert flapping_lab_sentence(page) is False


def test_forbidden_phrases_survive_markdown_emphasis():
    """The old page wraps the frame in ``**…**``; normalization must still see the phrase."""
    for phrase in (
        "forces are reported in the **wing body frame**",
        "body-frame *forces*",
    ):
        assert no_forbidden_phrase(f"## Forces\n\n{phrase}\n") is False, phrase


def test_sentence_split_keeps_the_component_range_whole():
    assert sentences("The corpus `CF_x..CF_z` are lab-frame. Next.") == [
        "The corpus CF_x..CF_z are lab-frame",
        "Next.",
    ]


def test_sentence_split_ignores_abbreviations():
    assert sentences("The corpus (e.g. the parquet) is lab-frame, i.e. unrotated.") == [
        "The corpus (e.g. the parquet) is lab-frame, i.e. unrotated."
    ]


@pytest.mark.parametrize("parquet", _CORPUS_PARQUETS, ids=lambda p: p.parent.name)
def test_corpus_coefficients_are_unrotated_lab_components(parquet):
    assert _parquet_on_wing(parquet) is True


def test_flapping_wing_lab_series_are_unrotated_lab_components():
    assert flapping_series_on_wing() is True


def test_corpus_check_rejects_rotated_coefficients(tmp_path):
    """Negative control: coefficients rotated about lab z mix components and must fail."""
    cols = [
        "stroke_amp_deg",
        "frequency_fstar",
        "Fx",
        "Fy",
        "Fz",
        "CF_x",
        "CF_y",
        "CF_z",
    ]
    df = pd.read_parquet(_CORPUS_PARQUETS[0], columns=cols)
    c, s = math.cos(math.radians(_ROTATION_DEG)), math.sin(math.radians(_ROTATION_DEG))
    x, y = df["CF_x"].to_numpy(), df["CF_y"].to_numpy()
    df["CF_x"], df["CF_y"] = c * x - s * y, s * x + c * y
    rotated = tmp_path / "rotated.parquet"
    df.to_parquet(rotated, index=False)
    assert _parquet_on_wing(rotated) is False


# ---------------------------------------------------------------------------------------------
# Scenario: F_ref is written with ω_peak, tied to the code and to the kinematics
# ---------------------------------------------------------------------------------------------


_F_REF_ASSIGN = re.compile(r"F_ref`?\s*(?::=|≡|=)")
_OMEGA_PEAK_SQUARED = re.compile(r"ω_peak(?:²|\^2|\*\*2)")


def f_ref_expressions(page: str) -> list[str]:
    """Each ``F_ref =`` (or ``:=``, ``≡``, ``F_ref`` in backticks), read to its clause end.

    The expression ends at the first ``,``, ``;``, backtick or line end of the raw text, so a
    later, unrelated ``S_yy`` is never pulled in. A formula wrapped across a line break is cut
    short, and the bare-ω scan (which reads flattened text) still sees it.
    """
    text = _COMMENT.sub(" ", page)
    out = []
    for m in _F_REF_ASSIGN.finditer(text):
        cut = re.search(r"[,;`\n]", text[m.end() :])
        end = m.end() + (cut.start() if cut else len(text) - m.end())
        expr = text[m.start() : end].strip()
        if not expr[m.end() - m.start() :].strip():
            # Nothing after ``=`` before the cut: the right-hand side is the next code span
            # (`` `F_ref` = `½·ρ·…` ``), so read that span as the expression (re-review).
            nxt = re.match(r"`?\s*`([^`\n]*)`", text[end:])
            if nxt:
                expr = f"{expr} {nxt.group(1)}"
        out.append(expr)
    return out


def f_ref_expression_failures(page: str) -> list[str]:
    """``F_ref`` expressions with an ``ω`` use ``ω_peak²`` only; at least two do.

    An expression with ``S_yy`` but no ``ω_peak`` (``½·ρ·(2πf)²·S_yy``) also fails. One with
    neither (``F_ref = q_ref·S``) is another form and is skipped.
    """
    failures = []
    good = 0
    for expr in f_ref_expressions(page):
        if "ω" in expr:
            if _OMEGA_PEAK_SQUARED.search(expr) and not re.search(r"ω(?!_peak)", expr):
                good += 1
            else:
                failures.append(f"F_ref expression with a bare ω: {expr!r}")
        elif "S_yy" in expr:
            failures.append(f"F_ref expression with S_yy but no ω_peak: {expr!r}")
    if good < 2:
        failures.append(
            f"expected at least two F_ref expressions with ω_peak², found {good}"
        )
    return failures


def _omega_peak(f_star: float, phi_amp_deg: float) -> float:
    return 2 * math.pi * f_star * math.radians(phi_amp_deg)


def quoted_value_failures(page: str) -> list[str]:
    """Every quoted ``ω_peak`` / ``F_ref`` value equals the recomputed one at its precision.

    Reads the normalized page, so bold or backticked numbers count. A quote is the symbol, then
    ``≈``, ``~`` or ``=``, then a number. Every such quote must be the validated point, so a
    historical value (the old peak-tip ``624.79``) must not be written as ``F_ref ≈ …``.
    """
    expected = {
        "ω_peak": _omega_peak(VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG),
        "F_ref": compute_force_reference(
            VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, RHO
        ).f_ref,
    }
    flat = normalize(page)
    failures = []
    for symbol, value in expected.items():
        # A number that continues into a symbol or formula (``ω_peak = 2π·…``) is a definition.
        # ``\.?`` in the lookahead stops backtracking to the integer part (``200.27·k`` → ``200``).
        quotes = re.findall(
            rf"{symbol}\s*([≈~=])\s*([0-9]+(?:\.[0-9]+)?)(?!\.?[\w·⋅π(*/^])", flat
        )
        literals = [lit for _, lit in quotes]
        if literals and not any(op == "≈" for op, _ in quotes):
            failures.append(f"no quoted '{symbol} ≈ …' value")
        if not literals:
            failures.append(f"no quoted '{symbol} ≈ …' value")
        for lit in literals:
            decimals = len(lit.split(".")[1]) if "." in lit else 0
            if decimals < 2:
                failures.append(f"{symbol} ≈ {lit}: quote at least two decimals")
            elif format_like(value, lit) != lit:
                failures.append(
                    f"{symbol} ≈ {lit}, but the code gives {format_like(value, lit)}"
                )
    return failures


def test_every_f_ref_expression_uses_omega_peak():
    assert f_ref_expression_failures(_page()) == []


@pytest.mark.parametrize(
    "bad",
    [
        "F_ref=½·ρ·ω²·S_yy",
        "`F_ref` = ½·ρ·ω²·S_yy",
        "F_ref := ½·ρ·(2π·f·φ_amp)²·S_yy",
        "F_ref ≡ ½·ρ·ω²S_yy",
        "`F_ref` = `½·ρ·(2πf)²·S_yy`",
        "`F_ref` = `½·ρ·ω²·S_yy`",
    ],
)
def test_f_ref_expression_check_rejects_bare_forms(bad):
    good = "`F_ref = ½·ρ·ω_peak²·S_yy`, and `F_ref = ½·ρ_f·ω_peak^2·S_yy`."
    assert f_ref_expression_failures(good) == []
    assert f_ref_expression_failures(f"{good}\n{bad}\n") != [], bad


def test_f_ref_expression_ends_at_its_clause():
    """An equivalent form without ω, and a later unrelated S_yy, are not misread (PR review)."""
    page = (
        "`F_ref = ½·ρ·ω_peak²·S_yy`. `F_ref = ½·ρ_f·ω_peak²·S_yy`. Equivalently "
        "`F_ref = ½ρ·u_ref²·S` with `ω = 2πf`; later, S_yy is the second moment.\n"
    )
    assert f_ref_expression_failures(page) == []


def test_page_defines_omega_peak_and_names_the_single_source():
    flat = _flat(_page())
    for required in (
        "ω_peak = 2π·f_star·radians(phi_amp_deg)",
        "`ω = 2πf`",
        "compute_force_reference",
        "computed per configuration",
    ):
        assert required in flat, required


def test_page_links_the_force_surrogate_spec():
    targets = re.findall(r"\]\(([^)\s]+)\)", _COMMENT.sub(" ", _page()))
    resolved = {
        (_DOC.parent / t.split("#")[0]).resolve()
        for t in targets
        if not t.startswith(("http:", "https:", "#"))
    }
    assert _FORCE_SURROGATE_SPEC.is_file()
    assert _FORCE_SURROGATE_SPEC.resolve() in resolved


def test_quoted_values_match_the_code():
    assert quoted_value_failures(_page()) == []


def test_quoted_value_check_rejects_the_two_pi_reading():
    """Negative control: ``F_ref`` with ω read as 2π (134.17) must fail, however it is marked up."""
    for quote in (
        "F_ref ≈ 134.17",
        "`F_ref` ≈ 134.17",
        "F_ref ≈ **134.17**",
        "F_ref = 134.17",
    ):
        page = f"ω_peak ≈ 7.676 and F_ref ≈ 200.27; also {quote}."
        assert any("134.17" in f for f in quoted_value_failures(page)), quote


def test_quoted_value_check_skips_numbers_that_continue_into_a_formula():
    """``F_ref = 200.27·k`` is a scaled expression, not a quote; no backtracking to ``200``."""
    base = "ω_peak ≈ 7.676 and F_ref ≈ 200.27"
    for tail in (
        "F_ref = 200.27·k",
        "F_ref = 134.17e0",
        "F_ref = 134.17²",
        "F_ref ≈ 200.27.",
    ):
        assert quoted_value_failures(f"{base}; {tail} here") == [], tail


def test_quoted_value_check_requires_an_approximate_quote():
    """``=`` quotes alone do not satisfy "at least one ``≈`` quote of each"."""
    failures = quoted_value_failures("ω_peak = 7.676 and F_ref = 200.27.")
    assert "no quoted 'ω_peak ≈ …' value" in failures
    assert "no quoted 'F_ref ≈ …' value" in failures


@pytest.mark.parametrize(("f_star", "phi_amp_deg"), [(1.0, 70.0), (1.15, 55.0)])
def test_omega_peak_is_the_peak_stroke_rate_of_the_kinematics(f_star, phi_amp_deg):
    """Known answer: max|φ̇| of the single-source stroke equals the formula and the code.

    The grid is offset by half a step, so the peak (at t = 0) is never sampled exactly and the
    maximum is found, not read off. ``compute_force_reference(...).u_ref / R_GYRATION`` ties the
    code's ``ω_peak`` to the kinematics, not just the test's own formula.
    """
    n = 20001
    t = (np.arange(n) + 0.5) / (n * f_star)
    amp = math.radians(phi_amp_deg)
    peak = max(
        abs(stroke_rate(ti, frequency=f_star, stroke_amp_rad=amp)[0]) for ti in t
    )
    code = compute_force_reference(f_star, phi_amp_deg, R_GYRATION, SPAN, CHORD, RHO)
    assert _omega_peak(f_star, phi_amp_deg) == pytest.approx(peak, rel=1e-6)
    assert code.u_ref / R_GYRATION == pytest.approx(peak, rel=1e-6)


def test_kinematics_table_keeps_its_omega():
    page = _page()
    assert "φ_amp·sin(ωt)" in page
    assert "α_amp·cos(ωt)" in page


# ---------------------------------------------------------------------------------------------
# Scenario: No bare ω in F_ref in the documents that restate the normalization
# ---------------------------------------------------------------------------------------------


def bare_omega_hits_in(text: str, label: str) -> list[str]:
    """Each bare ``ω²…S_yy`` in ``text``, read flattened so a wrapped formula is still seen."""
    flat = _flat(text).replace("`", "")
    return [
        f"{label}: …{flat[max(0, m.start() - 40) : m.end() + 20]}…"
        for m in BARE_OMEGA.finditer(flat)
    ]


def doc_bare_omega_hits() -> list[str]:
    hits = []
    for path in (_DOC, _RESULTS, _FIGURES_README):
        label = path.relative_to(_ROOT).as_posix()
        hits += bare_omega_hits_in(path.read_text(encoding="utf-8"), label)
    return hits


def exemption_failures(fwv: dict) -> list[str]:
    """The exempt block must exist and still contain a bare ``ω²·S_yy`` (or drop the exemption)."""
    variants = fwv.get(EXEMPT)
    if not variants or not any(b for _, b in variants):
        return [
            f"{FWV}: exempt requirement {EXEMPT!r} is missing; remove the exemption"
        ]
    if not any(b and BARE_OMEGA.search(_flat(b)) for _, b in variants):
        return [f"{FWV}: {EXEMPT!r} no longer has a bare ω²·S_yy; remove the exemption"]
    return []


def spec_bare_omega_hits(changes_dir: Path | None = None) -> list[str]:
    kw = {} if changes_dir is None else {"changes_dir": changes_dir}
    hits = []
    for cap in (CC, FWV):
        for name, variants in effective_spec(cap, **kw).items():
            if cap == FWV and name == EXEMPT:
                continue
            for source, block in variants:
                if block and BARE_OMEGA.search(_flat(block)):
                    hits.append(f"{cap} [{source}] {name!r}")
    return hits


def test_documents_have_no_bare_omega_in_f_ref():
    assert doc_bare_omega_hits() == []


def test_effective_specs_have_no_bare_omega_in_f_ref():
    assert spec_bare_omega_hits() == []


def test_exemption_is_still_needed():
    assert exemption_failures(effective_spec(FWV)) == []


def test_exemption_check_fails_when_the_block_no_longer_matches():
    synthetic = {
        EXEMPT: [("live", f"### Requirement: {EXEMPT}\nF_ref uses ω_peak² here.")]
    }
    assert exemption_failures(synthetic) != []
    assert exemption_failures({}) != []


def test_bare_omega_pattern_spellings():
    for bare in (
        "ω²S_yy",
        "ω²·S_yy",
        "ω² ⋅ S_yy",
        "ω^2·S_yy",
        "ω**2 S_yy",
        "ω ²·S_yy",
        "ω²*S_yy",
        "ω² × S_yy",
        "ω^{2}·S_{yy}",
        "\\omega^2 S_yy",
        "ω<sup>2</sup>·S_yy",
        "(ω)²·S_yy",
        "½ρω²·r²·S_yy",
    ):
        assert BARE_OMEGA.search(bare), bare
    for fine in ("ω_peak²·S_yy", "ω_peak^2·S_yy", "ω² is the rate; S_yy is the moment"):
        assert not BARE_OMEGA.search(fine), fine


def test_doc_scan_sees_a_formula_wrapped_across_lines():
    text = "Coefficients use `F_ref = ½ρ·ω²·`\n`S_yy` here."
    assert bare_omega_hits_in(text, "synthetic") != []


def test_results_links_the_convention_page_forces_section():
    results = _COMMENT.sub(" ", _RESULTS.read_text(encoding="utf-8"))
    assert "](../../docs/coordinate-convention.md#forces)" in results
    assert (
        _RESULTS.parent / "../../docs/coordinate-convention.md"
    ).resolve() == _DOC.resolve()
    assert re.search(r"(?m)^## Forces\s*$", _page())


def _line_with(path: Path, marker: str) -> str:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if marker in ln]
    assert len(lines) == 1, (path.name, marker, len(lines))
    return lines[0]


def test_results_and_figures_rows_write_omega_peak():
    results = _RESULTS.read_text(encoding="utf-8")
    norm_section = _sec(results, "### Reference normalization")
    paragraph = norm_section.split("| Quantity")[0]
    assert "ω_peak²" in paragraph
    assert "ω_peak²" in _line_with(_RESULTS, "Force reference F_ref")
    assert "radians(phi_amp)" in _line_with(_RESULTS, "Reference speed u_ref")
    assert "ω_peak²" in _line_with(_FIGURES_README, "`fig_forces`")
