"""The canonical force/moment sign section and its guards (issue #109).

``docs/coordinate-convention.md#force-and-moment-sign`` is the one place the sign convention and its
evidence are stated. These tests pin three things:

- the section exists once and says what it must;
- the work-inequality evidence appears nowhere else in the prose;
- the listed documents link the section.

The section also carries pinned "pending" phrases while a path still has the solver's on-fluid sign.
Each phrase is present if and only if its condition holds, so the page can neither run ahead of the
data nor lag behind it.

Spec: coordinate-convention "The canonical convention page states the force and moment sign".
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from _readme_guards import _section

from mosquito_cfd.benchmarks import flapping_wing
from mosquito_cfd.force_surrogate import (
    ForceCoefficients,
    MomentCoefficients,
    compute_force_reference,
    force_on_wing,
)
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN

_ROOT = Path(__file__).resolve().parents[1]
_DOC = _ROOT / "docs" / "coordinate-convention.md"
_HEADING = "## Force and moment sign"
_ANCHOR = "coordinate-convention.md#force-and-moment-sign"
_EVIDENCE_TOKENS = ("work from rest", "work-from-rest", "M_hinge · Ω")
_EXEMPT_PREFIXES = ("openspec/", "tests/")
_EXEMPT_FILES = {"docs/CHANGELOG.md"}

CORPUS_PHRASE = "Pending #109: the committed corpus coefficients still carry the solver's on-fluid sign."
FLAPPING_PHRASE = (
    "Pending #109: the flapping-wing series still carry the solver's on-fluid sign."
)
SURROGATE_PHRASE = (
    "Pending #109: the committed surrogates still predict the solver's on-fluid sign; "
    "negate their outputs."
)
_BANNER = "are stale against `dataset.parquet`"
_COARSE_PARQUET = _ROOT / "examples" / "prelim_sweep" / "dataset.parquet"
_T2A_CSV = _ROOT / "examples" / "flapping_wing" / "forces_t2a_newconv.csv"
_CORPUS_READMES = (
    _ROOT / "examples" / "prelim_sweep" / "README.md",
    _ROOT / "examples" / "prelim_sweep_fine" / "README.md",
)

# The fixed link list, staged per PR (the CC requirement's table). Each later PR extends it in the
# same commit as the link it adds.
_LINKED_OBJECTS = (ForceCoefficients, MomentCoefficients, force_on_wing, flapping_wing)
_LINKED_FILES: tuple[str, ...] = ()


def _flat(text: str) -> str:
    """Collapse whitespace so a reflowed line break cannot hide or break a phrase."""
    return " ".join(text.split())


def _sign_section() -> str:
    section, _ = _section(_DOC.read_text(encoding="utf-8"), _HEADING)
    return _flat(section)


def _github_slug(heading: str) -> str:
    text = heading.lstrip("#").strip().lower()
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", text))


def corpus_coefficients_on_wing(parquet: Path = _COARSE_PARQUET) -> bool:
    """Whether the corpus ``CF_x`` is the on-wing ``−Fx/f_ref`` (the corpus phrase's condition)."""
    df = pd.read_parquet(
        parquet, columns=["stroke_amp_deg", "frequency_fstar", "Fx", "CF_x"]
    )
    f_ref = np.array(
        [
            compute_force_reference(f, s, R_GYRATION, SPAN, CHORD, RHO).f_ref
            for s, f in zip(df["stroke_amp_deg"], df["frequency_fstar"], strict=True)
        ]
    )
    return bool(np.allclose(df["CF_x"], -df["Fx"] / f_ref, rtol=1e-9, atol=1e-12))


def flapping_series_on_wing(
    reconstruct=flapping_wing.reconstruct_wing_forces,
) -> bool:
    """Whether the flapping-wing ``cf_x_ib`` is the on-wing ``−Fx/f_ref`` (tied to the code path)."""
    decomp = reconstruct(_T2A_CSV, f_star=1.0, phi_amp_deg=70.0)
    fx = pd.read_csv(_T2A_CSV)["Fx"].to_numpy(float)
    return bool(np.allclose(decomp.cf_x_ib, -fx / decomp.f_ref, rtol=1e-9, atol=1e-12))


def surrogates_stale(readmes: tuple[Path, ...] = _CORPUS_READMES) -> bool:
    """Whether both corpus READMEs carry the staleness banner (the surrogate phrase's condition)."""
    return all(_BANNER in p.read_text(encoding="utf-8") for p in readmes)


def test_sign_section_exists_once_and_states_the_convention():
    doc = _DOC.read_text(encoding="utf-8")
    headings = [ln for ln in doc.splitlines() if ln.startswith("## ")]
    assert headings.count(_HEADING) == 1
    assert _github_slug(_HEADING) == "force-and-moment-sign"
    section = _sign_section()
    for required in (
        "`ib_force`",
        "`ib_moment`",
        "**on the fluid**",
        "IB force and moment on the wing",
        "Newton's third law",
        "`ρ_f·SumU`",
        "sphere",
        "ellipsoid",
        "`tests/test_ib_force_sign_convention.py`",
        "(#moments)",
        "force_on_wing",
    ):
        assert required in section, required


def test_work_inequality_evidence_lives_only_in_the_sign_section():
    """The evidence tokens appear in the section, and nowhere else in the prose or src docstrings.

    The search set is every tracked ``*.md`` under ``docs/``, ``examples/`` and the repository root,
    plus every ``.py`` file under ``src/`` (docstrings and comments). ``openspec/``, ``tests/`` and the
    CHANGELOG are exempt. The negative check shares this test with the positive one.
    """
    section = _sign_section()
    assert any(tok in section for tok in _EVIDENCE_TOKENS)
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    candidates = [
        p
        for p in tracked
        if (
            (
                p.endswith(".md")
                and ("/" not in p or p.startswith(("docs/", "examples/")))
            )
            or (p.startswith("src/") and p.endswith(".py"))
        )
        and not p.startswith(_EXEMPT_PREFIXES)
        and p not in _EXEMPT_FILES
    ]
    assert len(candidates) > 20  # the search set is not empty by accident
    hits = []
    for rel in candidates:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        if rel == "docs/coordinate-convention.md":
            _, text = _section(text, _HEADING)
        text = _flat(text)
        hits += [f"{rel}: {tok!r}" for tok in _EVIDENCE_TOKENS if tok in text]
    assert not hits, "evidence restated outside the sign section:\n" + "\n".join(hits)


def test_listed_documents_link_the_sign_section():
    for obj in _LINKED_OBJECTS:
        assert _ANCHOR in (obj.__doc__ or ""), getattr(obj, "__name__", obj)
    for rel in _LINKED_FILES:
        assert _ANCHOR in (_ROOT / rel).read_text(encoding="utf-8"), rel


def test_each_pending_phrase_tracks_its_condition():
    """Each pinned phrase occurs exactly once iff its path still has the on-fluid sign, else never."""
    section = _sign_section()
    required = {
        CORPUS_PHRASE: not corpus_coefficients_on_wing(),
        FLAPPING_PHRASE: not flapping_series_on_wing(),
        SURROGATE_PHRASE: surrogates_stale(),
    }
    for phrase, needed in required.items():
        assert section.count(phrase) == (1 if needed else 0), (phrase, needed)


def test_corpus_condition_flips_on_a_negated_coefficient_copy(tmp_path):
    """Both directions of the corpus phrase's condition, on a saved copy with only ``CF_*`` negated."""
    assert corpus_coefficients_on_wing() is False
    df = pd.read_parquet(_COARSE_PARQUET)
    cf = [c for c in df.columns if c.startswith("CF_")]
    df[cf] = -df[cf]
    flipped = tmp_path / "dataset.parquet"
    df.to_parquet(flipped, index=False)
    assert corpus_coefficients_on_wing(flipped) is True


def test_flapping_condition_flips_with_the_code_path():
    """The flapping-wing condition depends on the code path, not the data.

    Negating the CSV would negate both sides, so the direction is exercised by swapping the
    reconstruction instead. Once PR2a routes ``reconstruct_wing_forces`` through ``force_on_wing``,
    this is tested by monkeypatching ``force_on_wing`` at that use site.
    """
    assert flapping_series_on_wing() is False

    def negated(*args, **kwargs):
        d = flapping_wing.reconstruct_wing_forces(*args, **kwargs)
        return type(d)(**{**d.__dict__, "cf_x_ib": -d.cf_x_ib})

    assert flapping_series_on_wing(negated) is True


def test_surrogate_condition_needs_the_banner_in_both_readmes(tmp_path):
    with_banner = tmp_path / "a.md"
    with_banner.write_text(f"Surrogate artifacts {_BANNER}.\n", encoding="utf-8")
    without = tmp_path / "b.md"
    without.write_text("No banner.\n", encoding="utf-8")
    assert surrogates_stale((with_banner, with_banner)) is True
    assert surrogates_stale((with_banner, without)) is False
    assert surrogates_stale() is False


@pytest.mark.parametrize("phrase", [CORPUS_PHRASE, FLAPPING_PHRASE, SURROGATE_PHRASE])
def test_pending_phrases_are_single_sentences_naming_109(phrase):
    assert phrase.startswith("Pending #109: ") and phrase.endswith(".")
    assert ast.literal_eval(repr(phrase)) == phrase


def test_flapping_wing_no_longer_calls_ib_force_the_total_hydrodynamic_force():
    """``ib_force`` acts on the fluid and omits the free-body balance's internal-fluid term.

    So it is not "the TOTAL hydrodynamic force" (the old comment at ``flapping_wing.py:58-59``).
    """
    source = Path(flapping_wing.__file__).read_text(encoding="utf-8")
    flat = re.sub(r"\s*#\s*", " ", source)
    assert "ib_force is the TOTAL hydrodynamic force" not in flat
    assert "TOTAL hydrodynamic" not in flat
