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
# Any spelling of the evidence: case, hyphens, and the dot operator's spacing or code point.
_EVIDENCE = re.compile(r"(?i)work[\s-]+from[\s-]+rest|M_hinge\s*[·⋅]\s*Ω")
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
_CORPUS_PARQUETS = (
    _ROOT / "examples" / "prelim_sweep" / "dataset.parquet",
    _ROOT / "examples" / "prelim_sweep_fine" / "dataset.parquet",
)
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
    """The section, with HTML comments removed (a commented-out phrase is not on the page)."""
    section, _ = _section(_DOC.read_text(encoding="utf-8"), _HEADING)
    return _flat(re.sub(r"(?s)<!--.*?-->", " ", section))


def _github_slug(heading: str) -> str:
    text = heading.lstrip("#").strip().lower()
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", text))


def _on_wing(coefficients, raw, f_ref) -> bool:
    """Whether every coefficient component is ``−raw/f_ref``; all-zero raw data is not evidence."""
    for c, r in zip(coefficients, raw, strict=True):
        assert np.abs(r).max() > 0, (
            "all-zero raw component: the condition would be vacuous"
        )
        if not np.allclose(c, -r / f_ref, rtol=1e-9, atol=1e-12):
            return False
    return True


def _parquet_on_wing(parquet: Path) -> bool:
    """Whether one corpus's ``CF_x..CF_z`` are the on-wing ``−F/f_ref``."""
    cf, raw = ["CF_x", "CF_y", "CF_z"], ["Fx", "Fy", "Fz"]
    df = pd.read_parquet(
        parquet, columns=["stroke_amp_deg", "frequency_fstar", *raw, *cf]
    )
    pairs = df[["frequency_fstar", "stroke_amp_deg"]].itertuples(index=False, name=None)
    refs = {
        p: compute_force_reference(*p, R_GYRATION, SPAN, CHORD, RHO).f_ref
        for p in set(pairs)
    }
    f_ref = np.array(
        [refs[p] for p in zip(df["frequency_fstar"], df["stroke_amp_deg"], strict=True)]
    )
    return _on_wing(
        [df[c].to_numpy() for c in cf], [df[r].to_numpy() for r in raw], f_ref
    )


def corpus_coefficients_on_wing(parquets: tuple[Path, ...] = _CORPUS_PARQUETS) -> bool:
    """The corpus phrase's condition: **both** corpora carry the on-wing sign.

    One corpus flipped without the other must keep the phrase, so the page cannot run ahead of
    either corpus.
    """
    return all(_parquet_on_wing(p) for p in parquets)


def flapping_series_on_wing(
    reconstruct=flapping_wing.reconstruct_wing_forces,
) -> bool:
    """Whether the flapping-wing ``cf_x_ib``/``cf_z_ib`` are the on-wing ``−F/f_ref`` (code path)."""
    decomp = reconstruct(_T2A_CSV, f_star=1.0, phi_amp_deg=70.0)
    raw = pd.read_csv(_T2A_CSV)
    return _on_wing(
        [decomp.cf_x_ib, decomp.cf_z_ib],
        [raw["Fx"].to_numpy(float), raw["Fz"].to_numpy(float)],
        decomp.f_ref,
    )


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
        # The coefficient list: every derived wing series the convention covers.
        "- the lab-frame `CF_x..CF_z`;",
        "- the hinge-referenced moment coefficients `CF_mx..CF_mz`;",
        "- the flapping-wing lab-frame series;",
        "- the body-frame `CF_chord`/`CF_normal`;",
        "- the T4 CFD series.",
    ):
        assert required in section, required


def test_work_inequality_evidence_lives_only_in_the_sign_section():
    """The evidence appears in the section, and nowhere else in the prose or src docstrings.

    The search set is every tracked ``*.md`` under ``docs/``, ``examples/`` and the repository root,
    plus every ``.py`` file under ``src/`` (docstrings and comments); ``openspec/`` and ``tests/`` are
    outside it, and the CHANGELOG is exempt. The negative check shares this test, and its pattern,
    with the positive one.
    """
    section = _sign_section()
    assert _EVIDENCE.search(section)
    # -z: NUL-separated, so a non-ASCII path is not C-quoted; skip tracked-but-deleted paths.
    tracked = [
        p
        for p in subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.split("\0")
        if p and (_ROOT / p).is_file()
    ]
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
        and p not in _EXEMPT_FILES
    ]
    assert len(candidates) > 20  # the search set is not empty by accident
    hits = []
    for rel in candidates:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        if rel == "docs/coordinate-convention.md":
            _, text = _section(text, _HEADING)
        hits += [f"{rel}: {m.group()!r}" for m in _EVIDENCE.finditer(text)]
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


def _parquet_copy(src: Path, dst: Path, negate: list[str]) -> Path:
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
    df = pd.read_parquet(src, columns=cols)
    df[negate] = -df[negate]
    df.to_parquet(dst, index=False)
    return dst


def test_corpus_condition_flips_on_negated_coefficient_copies(tmp_path):
    """Both directions of the corpus phrase's condition, whichever sign the committed corpus has.

    Each corpus and its ``CF_*``-negated copy disagree. Only both on-wing versions satisfy the
    condition: one corpus on-wing alone, or an on-wing copy with a single component re-negated, does
    not. All-zero raw forces raise rather than satisfy it vacuously.
    """
    cf = ["CF_x", "CF_y", "CF_z"]
    on_wing, on_fluid = [], []
    for i, src in enumerate(_CORPUS_PARQUETS):
        kept = _parquet_copy(src, tmp_path / f"kept_{i}.parquet", [])
        flipped = _parquet_copy(src, tmp_path / f"flipped_{i}.parquet", cf)
        assert _parquet_on_wing(kept) != _parquet_on_wing(flipped), src
        wing, fluid = (kept, flipped) if _parquet_on_wing(kept) else (flipped, kept)
        on_wing.append(wing)
        on_fluid.append(fluid)
    assert corpus_coefficients_on_wing(tuple(on_wing)) is True
    assert corpus_coefficients_on_wing((on_wing[0], on_fluid[1])) is False
    assert corpus_coefficients_on_wing((on_fluid[0], on_wing[1])) is False
    for i, column in enumerate(cf):
        half = _parquet_copy(on_wing[0], tmp_path / f"half_{i}.parquet", [column])
        assert corpus_coefficients_on_wing((half, on_wing[1])) is False, column
    zeroed = pd.read_parquet(on_wing[0])
    zeroed[["Fx", "Fy", "Fz", *cf]] = 0.0
    zeroed.to_parquet(tmp_path / "zeroed.parquet", index=False)
    with pytest.raises(AssertionError, match="vacuous"):
        corpus_coefficients_on_wing((tmp_path / "zeroed.parquet", on_wing[1]))


def test_flapping_condition_flips_with_the_code_path():
    """The flapping-wing condition depends on the code path, not the data.

    Negating the CSV would negate both sides, so the direction is exercised by swapping the
    reconstruction instead, whichever sign the committed path has: the path and its negation
    disagree, and negating only one of ``cf_x_ib``/``cf_z_ib`` is never on-wing. Once PR2a routes
    ``reconstruct_wing_forces`` through ``force_on_wing``, this is tested by monkeypatching
    ``force_on_wing`` at that use site.
    """

    def both(*args, **kwargs):
        d = flapping_wing.reconstruct_wing_forces(*args, **kwargs)
        return type(d)(**{**d.__dict__, "cf_x_ib": -d.cf_x_ib, "cf_z_ib": -d.cf_z_ib})

    assert flapping_series_on_wing() != flapping_series_on_wing(both)
    wing = (
        both if flapping_series_on_wing(both) else flapping_wing.reconstruct_wing_forces
    )
    for field in ("cf_x_ib", "cf_z_ib"):

        def half(*args, _field=field, **kwargs):
            d = wing(*args, **kwargs)
            return type(d)(**{**d.__dict__, _field: -getattr(d, _field)})

        assert flapping_series_on_wing(half) is False, field


def test_surrogate_condition_needs_the_banner_in_both_readmes(tmp_path):
    with_banner = tmp_path / "a.md"
    with_banner.write_text(f"Surrogate artifacts {_BANNER}.\n", encoding="utf-8")
    without = tmp_path / "b.md"
    without.write_text("No banner.\n", encoding="utf-8")
    assert surrogates_stale((with_banner, with_banner)) is True
    assert surrogates_stale((with_banner, without)) is False
    assert surrogates_stale((without, with_banner)) is False


@pytest.mark.parametrize("phrase", [CORPUS_PHRASE, FLAPPING_PHRASE, SURROGATE_PHRASE])
def test_pending_phrases_are_single_sentences_naming_109(phrase):
    assert phrase.startswith("Pending #109: ") and phrase.endswith(".")


def test_flapping_wing_no_longer_calls_ib_force_the_total_hydrodynamic_force():
    """``ib_force`` acts on the fluid and omits the free-body balance's internal-fluid term.

    So it is not "the TOTAL hydrodynamic force" (the old comment at ``flapping_wing.py:58-59``).
    """
    source = Path(flapping_wing.__file__).read_text(encoding="utf-8")
    flat = re.sub(r"\s*#\s*", " ", source)
    assert "ib_force is the TOTAL hydrodynamic force" not in flat
    assert "TOTAL hydrodynamic" not in flat
