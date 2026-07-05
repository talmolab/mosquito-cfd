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

from mosquito_cfd.benchmarks.flapping_wing import (
    STEADY_WINDOW_T0,
    VAN_VEEN_CF_TARGETS,
    VAN_VEEN_MATCH_TOL,
    added_mass_fraction,
    body_frame_added_mass_subtracted,
    body_frame_overall_match,
    reconstruct_wing_body_forces,
    reconstruct_wing_forces,
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
# van Veen reference targets + derived gap/tol carried in the tables (NOT our data, not recomputed).
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

    Scenario: Lab-frame ranges recompute from the committed new-convention CSV.
    """
    d = reconstruct_wing_forces(_NEWCONV, **_KIN)
    assert d.f_ref == pytest.approx(200.27, abs=0.02)
    m = d.time >= STEADY_WINDOW_T0
    assert d.cf_x_ib[m].min() == pytest.approx(-2.35, abs=0.02)
    assert d.cf_x_ib[m].max() == pytest.approx(+2.37, abs=0.02)
    assert d.cf_z_ib[m].min() == pytest.approx(-1.46, abs=0.02)
    assert d.cf_z_ib[m].max() == pytest.approx(+0.03, abs=0.02)
    assert np.abs(d.cf_x_ib[m]).max() == pytest.approx(2.37, abs=0.02)
    assert np.abs(d.cf_z_ib[m]).max() == pytest.approx(1.46, abs=0.02)
    doc = _doc()
    for lit in ("−2.35", "+2.37", "−1.46", "+0.03", "2.37", "1.46", "200.27"):
        assert lit in doc, f"RESULTS.md headline literal {lit!r} missing"


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
    # (a) recompute — peaks, signed peak-to-peak drops, body-frame added-mass RMS shares.
    assert out["peak_cf_chord_total"] == pytest.approx(0.923, abs=0.02)
    assert out["peak_cf_chord_subtracted"] == pytest.approx(0.652, abs=0.02)
    assert out["peak_cf_normal_total"] == pytest.approx(2.606, abs=0.02)
    assert out["peak_cf_normal_subtracted"] == pytest.approx(2.285, abs=0.02)
    assert out["chord_drop_frac"] == pytest.approx(0.29, abs=0.01)
    assert out["normal_drop_frac"] == pytest.approx(0.12, abs=0.01)
    assert out["am_rms_share_chord"] == pytest.approx(0.84, abs=0.02)
    assert out["am_rms_share_normal"] == pytest.approx(0.13, abs=0.02)
    doc = _doc()
    # (b) the interim literals are present in the doc (share phrases are load-bearing linkages).
    for lit in ("0.923", "0.652", "2.606", "2.285"):
        assert lit in doc, f"interim literal {lit!r} missing from RESULTS.md"
    assert "chord 84" in doc and "normal 13" in doc
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
    section = _interim_section(doc).lower()
    # Honest framing: isolates a share, does NOT resolve; residual ~2x van Veen's 0.3; deferred to T4.
    assert "isolat" in section
    assert "does not resolve" in section or "not resolve" in section
    assert ("~2×" in section) or ("~2x" in section) or ("2×" in section)
    assert "0.3" in section
    assert "t4" in section and "#40" in section
    # Metric-type caveat: the -29% is a peak-to-peak ratio at different phases, not per-instant,
    # and distinct from the ~47% instantaneous drop at the total peak (pinned in test_wing_body_frame).
    assert "peak-to-peak" in section
    assert "different phase" in section or "different phases" in section
    assert "47 %" in section
    # Disambiguation: body-frame shares vs lab-frame fractions — different frame + axis pairing.
    assert "stroke 37" in section and "lift 29" in section
    assert "different frame" in section
    # "Same peaks" note tying the 3-sig-fig totals to the body-frame table's 0.92 / 2.61.
    assert "same peaks" in section
    assert "0.92" in section and "2.61" in section
    # The Validation-Status row is unchanged: body-frame verdict still PARTIAL, still references #40.
    assert "| Body-frame van Veen comparison | PARTIAL |" in doc
