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

FORBIDDEN = (
    "forces are reported in the wing body frame",
    "Unlike the forces above",
    "body-frame forces",
)
# ω squared, then S_yy, with an optional dot operator between. ``ω_peak²`` does not match.
BARE_OMEGA = re.compile(r"ω(?:²|\^2|\*\*2)\s*[·⋅]?\s*S_yy")
FWV = "flapping-wing-validation"
CC = "coordinate-convention"
# Here ω is the model's instantaneous stroke speed |φ̇| (van_veen_model.model_inputs), so
# ½ρω²S_yy is correct; the guard requires the match to still be there.
EXEMPT = "Van Veen quasi-steady force model, pinned and guarded"


# ---------------------------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------------------------


def _flat(text: str) -> str:
    return " ".join(re.sub(r"(?s)<!--.*?-->", " ", text).split())


def normalize(text: str) -> str:
    """Markdown emphasis, backticks and blockquote markers removed; whitespace collapsed.

    Underscore emphasis is stripped only when paired at word boundaries, so ``CF_chord``,
    ``F_ref`` and ``ω_peak`` survive.
    """
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)
    return " ".join(text.split())


def sentences(text: str) -> list[str]:
    """Normalized sentences: split on ``. `` or a bullet start, never on ``..`` in ``CF_x..CF_z``."""
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?m)^\s*[-*]\s+", "\x00", text)
    out = []
    for chunk in text.split("\x00"):
        for s in re.split(r"(?<!\.)\.\s+", normalize(chunk)):
            if s.strip():
                out.append(s.strip())
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
        ("plausibility_gate" in s or "fig_forces" in s) and "lab-frame components" in s
        for s in sentences(_sec(page, "## Forces"))
    )


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
    assert FRAME_CHECKS[name](_page()), name


@pytest.mark.parametrize("name", sorted(set(FRAME_CHECKS) - _PASSES_ON_OLD_PAGE))
def test_frame_check_fails_on_the_pre_change_page(name):
    """The frozen pre-#181 copy fails every check that is new (negative control, every CI run)."""
    old = _FIXTURE.read_text(encoding="utf-8")
    assert "246f0a0" in old, "fixture must name its source commit"
    assert FRAME_CHECKS[name](old) is False, name


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


@pytest.mark.parametrize("parquet", _CORPUS_PARQUETS, ids=lambda p: p.parent.name)
def test_corpus_coefficients_are_unrotated_lab_components(parquet):
    assert _parquet_on_wing(parquet) is True


def test_flapping_wing_lab_series_are_unrotated_lab_components():
    assert flapping_series_on_wing() is True


def test_corpus_check_rejects_rotated_coefficients(tmp_path):
    """Negative control: coefficients rotated 30° about lab z mix components and must fail."""
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
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    x, y = df["CF_x"].to_numpy(), df["CF_y"].to_numpy()
    df["CF_x"], df["CF_y"] = c * x - s * y, s * x + c * y
    rotated = tmp_path / "rotated.parquet"
    df.to_parquet(rotated, index=False)
    assert _parquet_on_wing(rotated) is False


# ---------------------------------------------------------------------------------------------
# Scenario: F_ref is written with ω_peak, tied to the code and to the kinematics
# ---------------------------------------------------------------------------------------------


def f_ref_expression_failures(page: str) -> list[str]:
    """Each ``F_ref =`` up to its first ``S_yy`` must contain ``ω_peak²`` and no other ``ω``."""
    flat = _flat(page)
    matches = list(re.finditer(r"F_ref\s*=", flat))
    if len(matches) < 2:
        return [f"expected at least two 'F_ref =' expressions, found {len(matches)}"]
    failures = []
    for m in matches:
        end = flat.find("S_yy", m.end())
        if end < 0:
            failures.append(f"'F_ref =' at {m.start()} has no following S_yy")
            continue
        expr = flat[m.start() : end + len("S_yy")]
        if "ω_peak²" not in expr or re.search(r"ω(?!_peak)", expr):
            failures.append(
                f"F_ref expression without ω_peak² or with a bare ω: {expr!r}"
            )
    return failures


def _omega_peak(f_star: float, phi_amp_deg: float) -> float:
    return 2 * math.pi * f_star * math.radians(phi_amp_deg)


def quoted_value_failures(page: str) -> list[str]:
    """Every ``ω_peak ≈ x`` / ``F_ref ≈ y`` equals the recomputed value at the printed precision."""
    expected = {
        "ω_peak": _omega_peak(VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG),
        "F_ref": compute_force_reference(
            VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, RHO
        ).f_ref,
    }
    flat = _flat(page)
    failures = []
    for symbol, value in expected.items():
        literals = re.findall(rf"{symbol}\s*≈\s*([0-9]+(?:\.[0-9]+)?)", flat)
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


def test_f_ref_expression_check_catches_unspaced_bare_omega():
    page = "F_ref = ½·ρ·ω_peak²·S_yy and later F_ref=½·ρ·ω²·S_yy."
    assert f_ref_expression_failures(page) != []


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
    targets = re.findall(r"\]\(([^)\s]+)\)", _page())
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
    """Negative control: ``F_ref`` with ω read as 2π (134.17) must fail."""
    page = "ω_peak ≈ 7.676 and F_ref ≈ 134.17."
    assert any("134.17" in f for f in quoted_value_failures(page))


@pytest.mark.parametrize(("f_star", "phi_amp_deg"), [(1.0, 70.0), (1.15, 55.0)])
def test_omega_peak_is_the_peak_stroke_rate_of_the_kinematics(f_star, phi_amp_deg):
    """Known answer: the formula equals max|φ̇| of the single-source stroke over one wingbeat."""
    t = np.linspace(0.0, 1.0 / f_star, 20001)
    amp = math.radians(phi_amp_deg)
    peak = max(
        abs(stroke_rate(ti, frequency=f_star, stroke_amp_rad=amp)[0]) for ti in t
    )
    assert _omega_peak(f_star, phi_amp_deg) == pytest.approx(peak, rel=1e-6)


def test_kinematics_table_keeps_its_omega():
    page = _page()
    assert "φ_amp·sin(ωt)" in page
    assert "α_amp·cos(ωt)" in page


# ---------------------------------------------------------------------------------------------
# Scenario: No bare ω in F_ref in the documents that restate the normalization
# ---------------------------------------------------------------------------------------------


def doc_bare_omega_hits() -> list[str]:
    hits = []
    for path in (_DOC, _RESULTS, _FIGURES_README):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BARE_OMEGA.search(line):
                hits.append(
                    f"{path.relative_to(_ROOT).as_posix()}:{lineno}: {line.strip()}"
                )
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
    for bare in ("ω²S_yy", "ω²·S_yy", "ω² ⋅ S_yy", "ω^2·S_yy", "ω**2 S_yy"):
        assert BARE_OMEGA.search(bare), bare
    assert not BARE_OMEGA.search("ω_peak²·S_yy")


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
