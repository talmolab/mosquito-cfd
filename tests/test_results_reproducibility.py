"""Issue #3 re-validation: every RESULTS.md headline number recomputes from committed CSVs (T2b).

This is the DURABLE regression guard that closes issue #3: each headline number in
``examples/flapping_wing/RESULTS.md`` is recomputed from the committed force CSVs by its own
definition (coefficients via ``compute_force_coefficients``; the phase-table ``Fz`` as RAW forces at
named phase rows; added-mass fractions as RMS ``added_mass_fraction``) AND asserted present in the doc
text — so a future edit that introduces a non-reproducible headline, or that drifts a number away from
the data, fails-closed here. It runs (and must pass) BEFORE any RESULTS.md edit.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks import van_veen_model as vv
from mosquito_cfd.benchmarks.flapping_wing import (
    STEADY_WINDOW_T0,
    T4_NORMAL_MAG_TOL,
    VAN_VEEN_CF_TARGETS,
    VAN_VEEN_MATCH_TOL,
    added_mass_fraction,
    body_frame_added_mass_subtracted,
    body_frame_overall_match,
    decompose_wing_force,
    reconstruct_wing_body_forces,
    reconstruct_wing_forces,
)
from mosquito_cfd.benchmarks.wing_convergence import (
    assert_gradeable_pair,
    wing_grid_convergence_from_body_forces,
)

_NEWCONV = (
    "examples/flapping_wing/forces_t2a_newconv.csv"  # van Veen convention (headline)
)
_OLD = "examples/flapping_wing/forces.csv"  # superseded run (contrast baseline)
_RESULTS = Path("examples/flapping_wing/RESULTS.md")
_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0}


def _doc() -> str:
    return _RESULTS.read_text(encoding="utf-8")


_NUM_RE = re.compile(r"[−+\-]?\d+\.\d+")

# The two headline coefficient TABLES, by their `### ` header substring.
_HEADLINE_TABLES = (
    "lab-frame magnitudes",
    "Body-frame per-component van Veen comparison",
)
# Magnitudes recomputed from the committed CSVs by the tests above.
_HEADLINE_VERIFIED = {0.03, 1.46, 2.35, 2.37, 2.61, 0.92, 1.06, 0.52}
# T2a targets + derived gap/tol carried in the tables (NOT our data, not recomputed).
_HEADLINE_REFERENCE = {2.4, 0.3, 0.21, 0.6}

# The #40 cheap-interim subsection (added-mass-subtracted body-frame diagnostic). It lives under its
# OWN `### ` header (NOT one of _HEADLINE_TABLES) so its 3-sig-fig totals 0.923/2.606 cannot collide
# with the body-frame table's 0.92/2.61 under the existing enumeration guard.
_INTERIM_HEADER_SUB = "Added-mass-subtracted body-frame"
_INTERIM_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0, "pitch_amp_deg": 45.0}
# Decimal cells of the interim TABLE: our recomputed totals/subtracted + the van Veen references.
_INTERIM_TABLE_VERIFIED = {0.923, 0.652, 2.606, 2.285}
_INTERIM_TABLE_REFERENCE = {0.3, 2.4}


def _interim_section(doc: str) -> str:
    """Text of the `### Added-mass-subtracted body-frame …` subsection up to the next `##`/`###`."""
    lines = doc.splitlines()
    start = next(
        k
        for k, ln in enumerate(lines)
        if ln.startswith("### ") and _INTERIM_HEADER_SUB in ln
    )
    end = next(
        (
            k
            for k, ln in enumerate(lines[start + 1 :], start + 1)
            if ln.startswith("## ") or ln.startswith("### ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _table_numbers(doc: str, header_sub: str) -> set[float]:
    """Magnitudes of the numeric cells in the markdown table under a `### <header_sub>` heading."""
    lines = doc.splitlines()
    start = next(
        k for k, ln in enumerate(lines) if ln.startswith("### ") and header_sub in ln
    )
    nums: set[float] = set()
    in_table = False
    for ln in lines[start + 1 :]:
        if ln.lstrip().startswith("|"):
            in_table = True
            for tok in _NUM_RE.findall(ln):
                nums.add(round(abs(float(tok.replace("−", "-"))), 4))
        elif in_table:
            break
    return nums


def test_lab_frame_ranges_recompute():
    """Lab-frame CF ranges/peaks recompute from forces_t2a_newconv.csv (F_ref=200.27, t>=0.05).

    Scenario: Lab-frame ranges recompute from the committed new-convention CSV. The coefficients are
    the IB force on the wing (issue #109), so the ranges are the negated solver ranges.
    """
    d = reconstruct_wing_forces(_NEWCONV, **_KIN)
    assert d.f_ref == pytest.approx(200.27, abs=0.02)
    m = d.time >= STEADY_WINDOW_T0
    assert d.cf_x_ib[m].min() == pytest.approx(-2.37, abs=0.02)
    assert d.cf_x_ib[m].max() == pytest.approx(+2.35, abs=0.02)
    assert d.cf_z_ib[m].min() == pytest.approx(-0.03, abs=0.02)
    assert d.cf_z_ib[m].max() == pytest.approx(+1.46, abs=0.02)
    assert np.abs(d.cf_x_ib[m]).max() == pytest.approx(2.37, abs=0.02)
    assert np.abs(d.cf_z_ib[m]).max() == pytest.approx(1.46, abs=0.02)
    doc = _doc()
    for lit in ("[−2.37, +2.35]", "[−0.03, +1.46]", "2.37", "1.46", "200.27"):
        assert lit in doc, f"RESULTS.md headline literal {lit!r} missing"
    for stale in ("[−2.35, +2.37]", "[−1.46, +0.03]"):
        assert stale not in doc, f"stale on-fluid range {stale!r} still in RESULTS.md"


def test_body_frame_peaks_reproduce_partial_verdict():
    """Body-frame peaks recompute and reproduce the T2a PARTIAL verdict (normal PASS, chord FAIL).

    Scenario: Body-frame peaks recompute and reproduce the PARTIAL verdict.
    """
    b = reconstruct_wing_body_forces(
        _NEWCONV, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    r = body_frame_overall_match(b, targets=VAN_VEEN_CF_TARGETS, tol=VAN_VEEN_MATCH_TOL)
    assert r["peak_cf_normal"] == pytest.approx(2.61, abs=0.02)
    assert r["peak_cf_chord"] == pytest.approx(0.92, abs=0.02)
    assert r["mean_cf_normal"] == pytest.approx(1.06, abs=0.02)
    assert r["mean_cf_chord"] == pytest.approx(0.52, abs=0.02)
    assert r["cf_normal_match"] is True
    assert r["cf_chord_match"] is False
    assert (
        r["match"] is False
    )  # PARTIAL: not a full match — chord unresolved (#40 / T4)
    doc = _doc()
    for lit in ("2.61", "0.92", "PARTIAL"):
        assert lit in doc, f"RESULTS.md body-frame literal {lit!r} missing"


def test_phase_table_raw_fz_recompute():
    """Phase-table Fz are RAW forces at named phase rows (phase=(time*f*) mod 1); peak at ~0.49.

    Scenario: Every stated headline value has a committed-data source, by its own definition.
    """
    df = pd.read_csv(_NEWCONV)
    t = df["time"].to_numpy(float)
    fz = df["Fz"].to_numpy(float)
    phase = (t * _KIN["f_star"]) % 1.0
    expected = {0.25: -9.9, 0.50: -290.3, 0.75: -18.4}
    for target, want in expected.items():
        i = int(np.argmin(np.abs(phase - target)))
        assert fz[i] == pytest.approx(want, abs=0.5), (
            f"phase {target}: Fz {fz[i]} != {want}"
        )
    # Peak |Fz| in the steady window, ~-292 near phase 0.49.
    m = t >= STEADY_WINDOW_T0
    idx = int(np.argmax(np.abs(fz[m])))
    assert fz[m][idx] == pytest.approx(-292, abs=2)
    assert phase[m][idx] == pytest.approx(0.49, abs=0.02)
    # CF_z (lab) is the IB force on the wing, -Fz/F_ref (issue #109); the Fz cells stay solver-native.
    d = reconstruct_wing_forces(_NEWCONV, **_KIN)
    for target, want in {0.25: "+0.049", 0.50: "+1.449", 0.75: "+0.092"}.items():
        i = int(np.argmin(np.abs(phase - target)))
        assert f"{d.cf_z_ib[i]:+.3f}" == want, (target, d.cf_z_ib[i])
    assert f"{d.cf_z_ib[m][idx]:+.3f}" == "+1.459"
    table = _phase_table(_doc())
    for cell in ("+0.049", "+1.449", "+0.092", "+1.459"):
        assert cell in table, cell
    for stale in ("−0.049", "−1.449", "−0.092", "−1.459"):
        assert stale not in table, stale
    assert "solver `ib_force`, on the fluid" in table
    assert "−Fz / F_ref" in table
    assert "coordinate-convention.md#force-and-moment-sign" in table


def _flat(text: str) -> str:
    """Whitespace collapsed and blockquote markers dropped, so a reflowed line cannot split a phrase."""
    return " ".join(re.sub(r"(?m)^>[ \t]?", "", text).split())


def _phase_table(doc: str) -> str:
    """The `### Force at key phases` subsection, caption and table (flattened)."""
    start = doc.index("### Force at key phases")
    end = doc.index("\n#", start + 1)
    return _flat(doc[start:end])


def test_added_mass_fractions_are_rms(_kin=_KIN):
    """Added-mass fractions are the RMS added_mass_fraction values (stroke ~37% / lift ~29%)."""
    d = reconstruct_wing_forces(_NEWCONV, **_KIN)
    frac = added_mass_fraction(d)
    assert frac["stroke"] == pytest.approx(0.37, abs=0.02)
    assert frac["lift"] == pytest.approx(0.29, abs=0.02)
    doc = _doc()
    # Load-bearing doc linkage (not the near-ubiquitous bare "37"/"29" substrings).
    assert "stroke 37" in doc and "lift 29" in doc


def test_headline_tables_enumeration_complete():
    """Every numeric cell in the two headline tables is enumerated (verified-from-data or reference).

    'Asserted complete' guard for issue #3: a headline number appearing in the lab-frame or body-frame
    table that is in NEITHER the verified nor the reference set fails here — forcing the author to
    classify + verify a newly added headline, the exact regression #3's guard is meant to close.
    """
    doc = _doc()
    extracted: set[float] = set()
    for header in _HEADLINE_TABLES:
        extracted |= _table_numbers(doc, header)
    # Limitation: this is a magnitude-set comparison, so a newly added headline whose magnitude
    # collides with an already-enumerated value (e.g. a second 0.6) would be absorbed silently. A
    # new *distinct* headline number fails here (verified by injecting a spurious value in review).
    known = _HEADLINE_VERIFIED | _HEADLINE_REFERENCE
    assert extracted == known, (
        f"headline-table numbers changed — unexpected {sorted(extracted - known)}, "
        f"missing {sorted(known - extracted)}; update the enumeration + verify reproducibility"
    )


def test_contrast_baseline_recomputes():
    """The contrast-baseline (old forces.csv) lab peaks recompute to 1.41 / 0.68."""
    d = reconstruct_wing_forces(_OLD, **_KIN)
    m = d.time >= STEADY_WINDOW_T0
    assert np.abs(d.cf_x_ib[m]).max() == pytest.approx(1.41, abs=0.02)
    assert np.abs(d.cf_z_ib[m]).max() == pytest.approx(0.68, abs=0.02)
    doc = _doc()
    assert "1.41" in doc and "0.68" in doc


def test_added_mass_subtracted_interim_recomputes():
    """The #40 interim numbers recompute from the committed CSV AND appear in RESULTS.md.

    Scenario: Interim added-mass-subtracted numbers recompute and are asserted present. Guards the
    added-mass-subtracted subsection the same way issue #3's guard covers the two headline tables:
    every interim number is regenerated by its own definition, the interim-table cells are
    asserted-complete (set-equality), and the two pre-existing headline tables are proven unperturbed.
    """
    out = body_frame_added_mass_subtracted(_NEWCONV, **_INTERIM_KIN)
    # (a) recompute — the 6-DOF and ib_w peaks, the rises from dropping rho_f*SumU, the RMS shares.
    assert out["peak_cf_chord_ib"] == pytest.approx(0.923, abs=5e-4)
    assert out["peak_cf_chord_6dof"] == pytest.approx(0.652, abs=5e-4)
    assert out["peak_cf_normal_ib"] == pytest.approx(2.606, abs=5e-4)
    assert out["peak_cf_normal_6dof"] == pytest.approx(2.285, abs=5e-4)
    rise = {
        c: out[f"peak_cf_{c}_ib"] / out[f"peak_cf_{c}_6dof"] - 1
        for c in ("chord", "normal")
    }
    assert round(100 * rise["chord"]) == 42 and round(100 * rise["normal"]) == 14
    assert out["am_rms_share_chord"] == pytest.approx(0.84, abs=0.005)
    assert out["am_rms_share_normal"] == pytest.approx(0.13, abs=0.005)
    doc = _doc()
    # (b) the interim literals are present in the doc (share phrases are load-bearing linkages).
    for lit in ("0.923", "0.652", "2.606", "2.285"):
        assert lit in doc, f"interim literal {lit!r} missing from RESULTS.md"
    assert "chord 84" in doc and "normal 13" in doc
    section = _flat(_interim_section(doc))
    assert (
        "6-DOF `ρ_f·(SumU + ib_w)`" in section and "IB force on wing `ib_w`" in section
    )
    assert "raises the peak 42 %" in section and "14 %" in section
    for stale in ("−29 %", "−12 %", "−42 %", "subtracted `ib − ρ_f·SumU`"):
        assert stale not in section, stale
    # (c) interim-table enumeration is asserted-complete (a new interim decimal cell fails here).
    interim_nums = _table_numbers(doc, _INTERIM_HEADER_SUB)
    known = _INTERIM_TABLE_VERIFIED | _INTERIM_TABLE_REFERENCE
    assert interim_nums == known, (
        f"interim-table numbers changed — unexpected {sorted(interim_nums - known)}, "
        f"missing {sorted(known - interim_nums)}; update the enumeration + verify reproducibility"
    )
    # (d) the two pre-existing headline tables are unperturbed by the interim subsection.
    existing = set().union(*(_table_numbers(doc, h) for h in _HEADLINE_TABLES))
    assert existing == (_HEADLINE_VERIFIED | _HEADLINE_REFERENCE)


def test_interim_framing_is_honest_and_disambiguated():
    """The interim subsection frames a share (not a resolution) and disambiguates the metrics/frames.

    Scenario: Honest framing — isolates the share, does not resolve the PARTIAL. Guards the load-bearing
    WORDING (not just the numbers): the anti-overclaim framing, the body-frame-vs-lab-frame
    disambiguation, the metric-type caveat, the "same peaks" note, and that the Validation-Status row
    still reads PARTIAL + references #40.
    """
    doc = _doc()
    section = _flat(_interim_section(doc)).lower()
    # Honest framing: isolates a share, does NOT resolve; residual ~2x the 0.3 target. Neither the
    # interim nor T4 resolves the chord PARTIAL, so the section must not say either does.
    assert "isolat" in section
    assert "does not resolve" in section or "not resolve" in section
    assert "resolved by" not in section and "resolves" not in section
    assert "t2a target" in section and "van veen's translational" not in section
    assert ("~2×" in section) or ("~2x" in section) or ("2×" in section)
    assert "0.3" in section
    assert "t4" in section and "#40" in section
    # Metric-type caveat: the -29% is a peak-to-peak ratio at different phases, not per-instant,
    # and distinct from the ~47% instantaneous drop at the total peak (pinned in test_wing_body_frame).
    assert "peak-to-peak" in section
    assert "different phase" in section or "different phases" in section
    assert "1094" in section and "39 %" in section and "47 %" not in section
    assert "added mass dominates" not in section
    # The IB-only residual is ~3x van Veen's 0.3; the 6-DOF 0.652 is ~2x.
    assert "neither candidate does" in section and "~3×" in section
    assert "#135" in section
    # Disambiguation: body-frame shares vs lab-frame fractions — different frame + axis pairing.
    assert "stroke 37" in section and "lift 29" in section
    assert "different frame" in section
    # "Same peaks" note tying the 3-sig-fig totals to the body-frame table's 0.92 / 2.61.
    assert "same peaks" in section
    assert "0.92" in section and "2.61" in section
    # The Validation-Status row states what T4 supports: the normal peak magnitude is validated
    # against the model; the chord is reported, not explained.
    assert "| Body-frame van Veen comparison | PARTIAL |" not in doc
    assert (
        "| Body-frame van Veen comparison | VALIDATED against van Veen's quasi-steady model "
        "(normal peak magnitude); chord reported, not explained by the model |" in doc
    )


# --- Tier T4: per-component decomposition numbers recompute + verdict updated ------------------

# `_FINE` (the T3c fine-grid CSV) is the single module-level definition, reused below by the T3c
# section too -- defined here (its first use site) rather than duplicated as a second constant.
_FINE = "examples/flapping_wing/forces_fine.csv"
# The T4 subsection lives under its OWN `### ` header (NOT one of _HEADLINE_TABLES) so its decimal
# cells cannot collide with the two headline tables under the existing enumeration guard.
_T4_HEADER_SUB = "per-component decomposition"
# Decimal cells of the T4 table: CFD totals (fine grid, T3c) + van Veen model peaks (recomputed).
_T4_TABLE_VERIFIED = {2.23, 2.27, 0.41, 0.107}


def _t4_section(doc: str) -> str:
    """Text of the `### T4 per-component decomposition …` subsection up to the next header."""
    lines = doc.splitlines()
    start = next(
        k
        for k, ln in enumerate(lines)
        if ln.startswith("### ") and _T4_HEADER_SUB in ln.lower()
    )
    end = next(
        (
            k
            for k, ln in enumerate(lines[start + 1 :], start + 1)
            if ln.startswith("## ") or ln.startswith("### ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _has_number(text: str, literal: str) -> bool:
    """``literal`` occurs in ``text`` as a whole number (not inside a longer one)."""
    return re.search(rf"(?<![\d.]){re.escape(literal)}(?!\d)", text) is not None


def _decimals(text: str) -> set[str]:
    """Every decimal number in ``text``, as written.

    Section, equation and figure references (``§3.1.2``, ``eq 3.12``) and labels such as ``S1.1``
    are not numbers and are skipped; a number that ends a sentence is still found.
    """
    text = re.sub(r"§\d+(\.\d+)*|\b(eq|fig)\s+\d+(\.\d+)*", " ", text)
    return set(re.findall(r"(?<![\w.])\d+\.\d+(?!\.?\d)", text))


def test_t4_decomposition_numbers_reproduce():
    """The Tier T4 decomposition numbers recompute from the committed CSVs AND appear in the T4
    subsection of RESULTS.md; the pre-existing enumeration guards + the T3b section are unperturbed.

    Scenario: T4 decomposition numbers recompute (fine grid) and are asserted present. No
    ``medium_csv`` is passed — pairing the finest grid as the 2-grid function's "coarse" role would
    invert the GCI-band semantics; the T3c 3-grid Richardson/GCI numbers are reported separately.

    Together the pins fail under the reversion of any one model correction: the gaps move with
    ``S_cy``, the chord peaks with the unit of eq 3.12, and a signed pitch raises.
    """
    r = decompose_wing_force(_FINE, **_T3B_KIN)
    # (a) recompute — graded magnitude, then the reported numbers.
    assert r["normal_peak_model"] == pytest.approx(2.2663, abs=5e-4)
    assert r["normal_peak_cfd"] == pytest.approx(2.2277, abs=5e-4)
    assert r["normal_mag_gap_rel"] == pytest.approx(0.0174, abs=5e-4)
    assert r["normal_mag_pass"] is True
    assert r["normal_peak_phase_gap"] == pytest.approx(0.0277, abs=5e-4)
    assert r["normal_curve_rmse"] == pytest.approx(0.163, abs=5e-4)
    assert r["normal_curve_corr"] == pytest.approx(0.978, abs=5e-4)
    assert r["chord_curve_corr"] == pytest.approx(0.970, abs=5e-4)
    assert r["chord_peak_model"] == pytest.approx(0.1070, abs=5e-4)
    assert r["chord_peak_cfd"] == pytest.approx(0.4114, abs=5e-4)
    assert r["transl_chord_peak"] == pytest.approx(0.0573, abs=5e-4)
    assert r["chord_gci_band"] is None
    assert r["chord_converges_toward_model"] is None
    # "The CFD peak comes first": its phase precedes the model's within the same half-stroke.
    assert r["normal_peak_phase_cfd"] < r["normal_peak_phase_model"]
    assert abs(r["normal_peak_phase_model"] - r["normal_peak_phase_cfd"]) < 0.25
    # "The model's peak falls just after mid-stroke, where its Wagner term changes sign": the
    # Wagner normal force is negative while the wing speeds up and positive while it slows.
    assert 0.5 < r["normal_peak_phase_model"] < 0.52
    phase, wagner = r["series"]["phase"], r["series"]["model_wagner"][1]
    assert (wagner[(phase > 0.45) & (phase < 0.499)] < 0).all()
    assert (wagner[(phase > 0.501) & (phase < 0.55)] > 0).all()
    # Coarse is graded too; medium is reported.
    coarse = decompose_wing_force(_NEWCONV, **_T3B_KIN)
    medium = decompose_wing_force(_MEDIUM, **_T3B_KIN)
    assert coarse["normal_mag_gap_rel"] == pytest.approx(0.1303, abs=5e-4)
    assert coarse["normal_mag_pass"] is True
    assert medium["normal_mag_gap_rel"] == pytest.approx(0.0285, abs=5e-4)

    doc = _doc()
    section = _t4_section(doc)
    # (b) every number the T4 subsection states is the recomputed one, matched as a whole number
    # inside the subsection (a stray copy elsewhere in the file does not satisfy this).
    a_mid, b_mid, c_mid = vv.TRANSL_TANGENTIAL_POLY
    literals = {
        "model normal peak": f"{r['normal_peak_model']:.2f}",
        "CFD normal peak": f"{r['normal_peak_cfd']:.2f}",
        "relative gap": f"{100 * r['normal_mag_gap_rel']:.1f} %",
        "tolerance": f"{100 * T4_NORMAL_MAG_TOL:.0f} %",
        "phase gap": f"{r['normal_peak_phase_gap']:.3f}",
        "curve RMSE": f"{r['normal_curve_rmse']:.3f}",
        "normal correlation": f"{r['normal_curve_corr']:+.2f}",
        "chord correlation": f"{r['chord_curve_corr']:+.2f}",
        "model chord peak": f"{r['chord_peak_model']:.3f}",
        "CFD chord peak": f"{r['chord_peak_cfd']:.2f}",
        "chord ratio": f"{r['chord_peak_cfd'] / r['chord_peak_model']:.1f} times",
        "translational-chord window peak": f"{r['transl_chord_peak']:.3f}",
        "translational chord at mid-stroke": f"{a_mid * 45.0**2 + b_mid * 45.0 + c_mid:.3f}",
        "coarse gap": f"{100 * coarse['normal_mag_gap_rel']:.1f} %",
        "medium gap": f"{100 * medium['normal_mag_gap_rel']:.1f} %",
    }
    # The window holds a second CFD normal peak, on the following half-stroke. The grade uses the
    # larger one; the docs state the other and the gap against it.
    series = r["series"]
    later = series["time"] >= 0.75
    second_peak = float(series["cfd_normal"][later].max())
    assert second_peak == pytest.approx(2.0065, abs=5e-4)
    assert second_peak < r["normal_peak_cfd"]
    second_gap = abs(r["normal_peak_model"] - second_peak) / second_peak
    assert second_gap == pytest.approx(0.1295, abs=5e-4)
    assert second_gap < T4_NORMAL_MAG_TOL  # it would also pass, with a small margin
    literals["second CFD normal peak"] = f"{second_peak:.2f}"
    literals["gap against the second peak"] = f"{100 * second_gap:.1f} %"
    lower_by = f"{100 * (1 - second_peak / r['normal_peak_cfd']):.0f} % lower"
    assert lower_by == "10 % lower" and lower_by in section
    # Both curves dip slightly below zero before each reversal (the docs say so).
    assert 0.05 < float((series["model_normal"] < 0).mean()) < 0.2
    assert 0.05 < float((series["cfd_normal"] < 0).mean()) < 0.2
    assert (
        literals["model normal peak"] == "2.27" and literals["relative gap"] == "1.7 %"
    )
    for what, lit in literals.items():
        assert _has_number(section, lit), (
            f"T4 {what} {lit!r} missing from the T4 subsection"
        )
    # Each number sits in the phrase that names it, so two numbers cannot be swapped.
    flat_section = _flat(section)
    m_n, c_n = literals["model normal peak"], literals["CFD normal peak"]
    m_c, c_c = literals["model chord peak"], literals["CFD chord peak"]
    bound = (
        f"| **CF_normal** (lift) | {c_n} | {m_n} |",
        f"| **CF_chord** (tangential) | {c_c} | {m_c} |",
        f"model {m_n} vs CFD {c_n} on the fine grid, a relative gap of "
        f"{literals['relative gap']}",
        f"`T4_NORMAL_MAG_TOL` ({literals['tolerance']})",
        f"coarse grid (gap {literals['coarse gap']})",
        f"medium-grid gap ({literals['medium gap']})",
        f"The two peaks are {literals['phase gap']} cycle apart",
        f"over the window: {literals['curve RMSE']}",
        f"normal {literals['normal correlation']}, chord {literals['chord correlation']}",
        f"the model's chord peak is {m_c} and the CFD's is {c_c}",
        f"the CFD peak is {literals['chord ratio']} the model's",
        f"**Translational-chord window peak**: "
        f"{literals['translational-chord window peak']}",
        f"it is {literals['translational chord at mid-stroke']} at mid-stroke",
        f"a second normal peak, {literals['second CFD normal peak']}",
        f"the model's peak is {literals['gap against the second peak']} high",
    )
    for phrase in bound:
        assert phrase in flat_section, phrase
    # ...and the subsection states no other decimal: a wrong copy of a number in the prose fails
    # even when the right one is also present. The CFD numbers it cross-references are recomputed
    # here too (grid peaks, the T3c Richardson extrapolant and GCI_fine, the window start).
    grid = wing_grid_convergence_from_body_forces(_NEWCONV, _MEDIUM, _FINE, **_T3B_KIN)
    cross_referenced = {
        f"{STEADY_WINDOW_T0:.2f}",
        f"{coarse['chord_peak_cfd']:.2f}",
        f"{medium['chord_peak_cfd']:.3f}",
        f"{grid['cf_chord']['cf_exact_richardson']:.2f}",
        f"{100 * grid['cf_chord']['gci_fine']:.1f}",
    }
    assert cross_referenced == {"0.05", "0.92", "0.554", "0.32", "27.6"}
    recomputed = _decimals(" ".join(literals.values())) | cross_referenced
    stated = _decimals(section)
    assert stated == recomputed, (
        f"T4 subsection decimals: unexpected {sorted(stated - recomputed)}, "
        f"missing {sorted(recomputed - stated)}"
    )

    # (c) the T4 subsection uses a distinct `### ` header not containing the two scanned substrings,
    # and its table cells are asserted-complete (a new T4 decimal cell fails here).
    t4_header = section.splitlines()[0]
    assert "lab-frame magnitudes" not in t4_header
    assert "Body-frame per-component van Veen comparison" not in t4_header
    t4_nums = _table_numbers(doc.lower(), _T4_HEADER_SUB)
    assert t4_nums == _T4_TABLE_VERIFIED, (
        f"T4-table numbers changed — unexpected {sorted(t4_nums - _T4_TABLE_VERIFIED)}, "
        f"missing {sorted(_T4_TABLE_VERIFIED - t4_nums)}"
    )

    # (d) the wing Validation-Status row reads validated-against-model, references #50 (the grid
    # complement), and no longer reads PARTIAL.
    assert "validated against van veen" in doc.lower()
    assert "| Body-frame van Veen comparison | PARTIAL |" not in doc
    assert "#50" in doc
    status = next(
        ln
        for ln in doc.splitlines()
        if ln.startswith("| Body-frame van Veen comparison |")
    )
    for phrase in (
        f"CF_normal {c_n} vs model {m_n}",
        f"rel gap {literals['relative gap']} < {literals['tolerance']} tol",
        f"CF_chord {c_c} vs model {m_c}",
        f"peak-phase gap ({literals['phase gap']} cycle)",
        f"second half-stroke's CFD peak, {literals['second CFD normal peak']}, the gap is "
        f"{literals['gap against the second peak']}",
    ):
        assert phrase in status, f"status row lacks {phrase!r}"
    assert _decimals(status) <= recomputed | {"0.3"}, sorted(
        _decimals(status) - recomputed
    )

    # (e) the pre-existing headline-table + interim enumeration guards are unperturbed, and the T3b
    # "Grid convergence" section and the new figure's Output Files row are present.
    existing = set().union(*(_table_numbers(doc, h) for h in _HEADLINE_TABLES))
    assert existing == (_HEADLINE_VERIFIED | _HEADLINE_REFERENCE)
    interim_nums = _table_numbers(doc, _INTERIM_HEADER_SUB)
    assert interim_nums == (_INTERIM_TABLE_VERIFIED | _INTERIM_TABLE_REFERENCE)
    assert "Grid convergence (T3b" in doc
    assert "fig_force_decomposition" in doc


def test_t4_subsection_states_the_limits_of_the_comparison():
    """The T4 subsection says what the comparison cannot show, and names the open issues.

    Scenario: RESULTS.md states the graded normal, the reported chord and the limits.
    """
    section = _flat(_t4_section(_doc())).lower()
    for phrase in (
        "validated against van veen's quasi-steady model at matched kinematics",
        "different phases",  # the two peaks are not the same instant
        "just after mid-stroke",
        "wagner term changes sign",
        "the grade uses the larger",
        "about eleven times",  # pinned by tests/test_van_veen_dataset.py
        "decelerat",
        "divided by an `f_ref` built on that same `s_yy`",
        "first wingbeat",
        "impulsive start",
        "mixed planform bases",
        "§3.1.2",
        "§4.4",
        "the graded normal does not",
        "no pitch-rotation term",
        "s1.1",
        "not published with the article",
        "fig 1c–e",
        "#40 is open",
        "#135",
        "#155",
        "#156",
        "reported, not gated",
    ):
        assert phrase in section, phrase
    # The chord is stated side by side, naming the grid, and is not called explained.
    assert "does not explain" in section
    assert "does not resolve the cf_chord partial" in section
    # The digits of the §4.4 coefficient set are not quoted (its constant is a superseded number).
    assert "1.0e-4" not in section


def test_t2a_note_names_the_targets_and_their_follow_up():
    """The T2a targets are called targets, with one note under the first T2a table (design D10)."""
    doc = _doc()
    flat = _flat(doc)
    note = flat[flat.index("**About the targets.**") :]
    note = note[: note.index("**Honest framing")]
    assert "VAN_VEEN_CF_TARGETS" in note
    assert "[#154](https://github.com/talmolab/mosquito-cfd/issues/154)" in note
    assert "not re-graded" in note
    # The paper's printed values at 45 degrees, recomputed from the pinned coefficients.
    a, b, c = vv.TRANSL_TANGENTIAL_POLY
    assert _has_number(note, f"{vv.C_FZA_TRANSL * np.sin(np.radians(45.0)):.2f}")
    assert _has_number(note, f"{a * 45.0**2 + b * 45.0 + c:.3f}")
    # The note sits under the first T2a table, before the lab-frame section.
    assert doc.index("**About the targets.**") < doc.index("## Summary")
    # No section still attributes the pinned targets to van Veen's translational coefficients.
    for stale in (
        "van Veen (**translational-only**, Fig 4)",
        "van Veen's translational ~0.3",
        "van Veen's **translational-only**",
        "van Veen (transl.)",
        "`C_Fz,transl`",
        "`C_Fx,transl`",
    ):
        assert stale not in flat, stale


def test_interim_does_not_claim_t4_resolves_the_chord():
    """The interim isolates a share; neither it nor T4 resolves the chord PARTIAL.

    Scenario: Honest framing. This inverts the earlier assertion that the interim points the
    resolution at T4: the corrected model leaves the chord unexplained.
    """
    doc = _doc()
    section = _interim_section(doc).lower()
    assert "isolat" in section
    assert "t4" in section
    assert "resolved by" not in section and "resolves" not in section
    assert "does not resolve" in section or "not resolve" in section
    assert "#40" in section


# --- Tier T3b: grid-convergence numbers recompute from the committed coarse + medium CSVs ------

_MEDIUM = "examples/flapping_wing/forces_medium.csv"
_COARSE_DECK = "examples/flapping_wing/inputs.3d.validation"
_MEDIUM_DECK = "examples/flapping_wing/inputs.3d.convergence_medium"
_T2A_META = Path("examples/flapping_wing/run_metadata_t2a.json")
_T3B_META = Path("examples/flapping_wing/run_metadata_t3b.json")
_T3B_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0, "pitch_amp_deg": 45.0}


@pytest.mark.skipif(
    not Path(_MEDIUM).exists(), reason="medium forces CSV not present (T3b run)"
)
def test_grid_convergence_recomputes_from_committed_csvs():
    """The RESULTS T3b convergence headline recomputes from the committed CSVs; both decks are pinned.

    The LEV numbers are plotfile-derived (plt*/ is gitignored) and are deliberately NOT recomputed
    here — they are covered by the requires_plotfile real-data test + the synthetic-fixture CI check.
    """
    import hashlib
    import json

    # Pre-grade guard first (same non-empty / same-window / same-time-grid contract RESULTS relies on).
    assert_gradeable_pair(
        _NEWCONV, _MEDIUM, coarse_deck=_COARSE_DECK, medium_deck=_MEDIUM_DECK
    )
    out = wing_grid_convergence_from_body_forces(_NEWCONV, _MEDIUM, **_T3B_KIN)
    doc = _doc()

    # Recompute -> RESULTS literal, per component. Each recomputed number is asserted present in the doc,
    # so a doc edit that drifts a headline off the data fails closed (the T2b pattern).
    chord, normal = out["cf_chord"], out["cf_normal"]
    assert chord["cf_medium"] == pytest.approx(0.554, abs=0.02)
    assert chord["relative_change"] == pytest.approx(-0.665, abs=0.02)
    assert chord["gci_p1"] == pytest.approx(0.83, abs=0.02)
    assert chord["gci_p2"] == pytest.approx(0.28, abs=0.02)
    assert normal["cf_medium"] == pytest.approx(2.333, abs=0.02)
    assert normal["relative_change"] == pytest.approx(-0.117, abs=0.02)
    assert normal["gci_p1"] == pytest.approx(0.15, abs=0.02)
    assert normal["gci_p2"] == pytest.approx(0.05, abs=0.02)
    # r=2 fixed by the deck pair; both GCI orders load-bearing (p1 = 3*p2).
    assert chord["r"] == 2.0 and chord["gci_p1"] == pytest.approx(3.0 * chord["gci_p2"])

    for lit in (
        f"{chord['cf_medium']:.3f}",  # 0.554
        f"{normal['cf_medium']:.3f}",  # 2.333
        f"{abs(chord['relative_change']) * 100:.1f}",  # 66.5
        f"{abs(normal['relative_change']) * 100:.1f}",  # 11.7
        f"{chord['gci_p1']:.2f}",  # 0.83
        f"{chord['gci_p2']:.2f}",  # 0.28
        f"{normal['gci_p1']:.2f}",  # 0.15
        f"{normal['gci_p2']:.2f}",  # 0.05
    ):
        assert lit in doc, (
            f"headline {lit!r} not found in RESULTS.md convergence section"
        )

    # Both decks of the graded pair are cryptographically pinned to their committed metadata.
    def _sha(p: str) -> str:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    assert json.loads(_T2A_META.read_text())["inputs"]["hash"] == _sha(_COARSE_DECK)
    assert json.loads(_T3B_META.read_text())["inputs"]["hash"] == _sha(_MEDIUM_DECK)
    # #40 stays open in the convergence section (a CF_chord drop is not misread as resolving it).
    assert "#40 remains open" in doc


# --- Tier T3c: 3-grid numbers recompute from the committed coarse + medium + fine CSVs -----------
# (reuses `_FINE`, defined above in the T4 section)

_T3C_META = Path("examples/flapping_wing/run_metadata_t3c.json")
_FINE_DECK = "examples/flapping_wing/inputs.3d.convergence_fine"
_T3C_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0, "pitch_amp_deg": 45.0}


@pytest.mark.skipif(
    not Path(_FINE).exists(), reason="fine forces CSV not present (T3c run)"
)
def test_3grid_convergence_recomputes_from_committed_csvs():
    """The RESULTS T3c convergence headlines recompute from the committed coarse+medium+fine CSVs.

    Both CF_normal and CF_chord are monotone (post-contamination-fix, forces_fine.csv clean segment
    rows 2063–6062). Asserts finite p_obs, Richardson extrapolant, and GCI_fine for both components,
    and that the RESULTS.md headline literals match the computed values to 2 decimal places.
    The fine deck is cryptographically pinned via run_metadata_t3c.json.
    """
    import hashlib
    import json

    out = wing_grid_convergence_from_body_forces(_NEWCONV, _MEDIUM, _FINE, **_T3C_KIN)
    doc = _doc()

    chord, normal = out["cf_chord"], out["cf_normal"]

    # CF_normal: monotone, finite observed order and Richardson extrapolant.
    # Tolerances are tight (abs=1e-4) — the CSVs are committed and the computation is
    # fully deterministic; loose tolerances would miss real regressions.
    assert normal["monotone"] is True
    assert normal["observed_order"] == pytest.approx(1.3773, abs=1e-4)
    assert normal["cf_exact_richardson"] == pytest.approx(2.1619, abs=1e-4)
    assert normal["gci_fine"] == pytest.approx(0.03692, abs=1e-4)

    # CF_chord: monotone, finite observed order and Richardson extrapolant.
    assert chord["monotone"] is True
    assert chord["cf_fine"] == pytest.approx(0.4114, abs=1e-4)
    assert chord["observed_order"] == pytest.approx(1.3655, abs=1e-4)
    assert chord["cf_exact_richardson"] == pytest.approx(0.3206, abs=1e-4)
    assert chord["gci_fine"] == pytest.approx(0.2758, abs=1e-4)

    # Headline literals present in RESULTS.md (so a drift edit fails closed).
    for lit in (
        "1.38",  # p_obs CF_normal
        "2.162",  # Richardson extrapolant CF_normal
        "3.7 %",  # GCI_fine CF_normal — "3.7 %" is specific; bare "3.7" would match "3.71" etc.
        "1.37",  # p_obs CF_chord
        "0.321",  # Richardson extrapolant CF_chord
        "27.6 %",  # GCI_fine CF_chord
    ):
        assert lit in doc, f"T3c headline {lit!r} not found in RESULTS.md"

    # Fine deck cryptographically pinned.
    def _sha(p: str) -> str:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    assert json.loads(_T3C_META.read_text())["inputs"]["hash"] == _sha(_FINE_DECK)


def test_results_vocabulary_states_the_sign_and_the_open_question():
    """RESULTS.md says what "total" means, that the diagnostic's name is historical, and what is open.

    Design D5: "total" keeps one meaning, the IB force on the wing ``ib_w``; the solver's ``ρ_f·SumU`` is
    an internal-fluid term, not van Veen's added mass; which force van Veen should be compared with is
    #135; and no stale "total hydrodynamic force" claim survives.
    """
    doc = _doc()
    flat = _flat(doc)
    assert "'Total' here means all aerodynamic mechanisms" in flat
    assert "measured as the IB force on the wing `ib_w`" in flat
    assert "not van Veen's added-mass component" in flat
    assert "the name is historical" in flat
    assert "#135" in flat
    assert "is the **total** hydrodynamic force" not in flat
    assert "coordinate-convention.md#force-and-moment-sign" in flat
