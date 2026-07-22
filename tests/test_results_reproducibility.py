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
    # The Validation-Status row is updated BY T4 (not by the interim) from PARTIAL to
    # validated-against-model; the interim is not the edit that changed the verdict (T4's is).
    assert "| Body-frame van Veen comparison | PARTIAL |" not in doc
    assert (
        "| Body-frame van Veen comparison | VALIDATED (vs QS model, magnitude) |" in doc
    )


# --- Tier T4: per-component decomposition numbers recompute + verdict updated ------------------

_MEDIUM_T4 = "examples/flapping_wing/forces_medium.csv"
# The T4 subsection lives under its OWN `### ` header (NOT one of _HEADLINE_TABLES) so its decimal
# cells cannot collide with the two headline tables under the existing enumeration guard.
_T4_HEADER_SUB = "per-component decomposition"
# Decimal cells of the T4 table: CFD totals (= body-frame table) + van Veen model peaks (recomputed).
_T4_TABLE_VERIFIED = {2.61, 2.48, 0.92, 0.43}


def test_t4_decomposition_numbers_reproduce():
    """The Tier T4 decomposition numbers recompute from the committed CSV AND appear in RESULTS.md,
    the verdict is updated to validated-against-model / chord-grid-limited, and the pre-existing
    enumeration guards + the T3b section are unperturbed.

    Scenario: T4 decomposition numbers recompute and are asserted present.
    """
    r = decompose_wing_force(_NEWCONV, medium_csv=_MEDIUM_T4, **_T3B_KIN)
    # (a) recompute — graded magnitude, reported phase / known-answer chord / chord total.
    assert r["normal_peak_model"] == pytest.approx(2.48, abs=0.02)
    assert r["normal_peak_cfd"] == pytest.approx(2.61, abs=0.02)
    assert r["normal_mag_gap_rel"] == pytest.approx(0.05, abs=0.01)
    assert r["normal_mag_pass"] is True
    assert r["normal_peak_phase_gap"] == pytest.approx(0.058, abs=0.01)
    assert r["transl_chord_peak"] == pytest.approx(0.42, abs=0.01)
    assert r["chord_peak_model"] == pytest.approx(0.43, abs=0.02)
    assert r["chord_converges_toward_model"] is True

    doc = _doc()
    # (b) the T4 literals are present in the doc.
    for lit in ("2.48", "0.43", "0.058", "0.42"):
        assert lit in doc, f"T4 literal {lit!r} missing from RESULTS.md"

    # (c) the T4 subsection uses a distinct `### ` header not containing the two scanned substrings,
    # and its table cells are asserted-complete (a new T4 decimal cell fails here).
    t4_header = next(
        ln
        for ln in doc.splitlines()
        if ln.startswith("### ") and _T4_HEADER_SUB in ln.lower()
    )
    assert "lab-frame magnitudes" not in t4_header
    assert "Body-frame per-component van Veen comparison" not in t4_header
    t4_nums = _table_numbers(doc.lower(), _T4_HEADER_SUB)
    assert t4_nums == _T4_TABLE_VERIFIED, (
        f"T4-table numbers changed — unexpected {sorted(t4_nums - _T4_TABLE_VERIFIED)}, "
        f"missing {sorted(_T4_TABLE_VERIFIED - t4_nums)}"
    )

    # (d) the wing Validation-Status row is updated to validated-against-model / chord-grid-limited,
    # references #50 (the grid complement), and no longer reads PARTIAL / an open #40 for the wing.
    assert "validated against van veen" in doc.lower()
    assert "| Body-frame van Veen comparison | PARTIAL |" not in doc
    assert "#50" in doc

    # (e) the pre-existing headline-table + interim enumeration guards are unperturbed, and the T3b
    # "Grid convergence" section and the new figure's Output Files row are present.
    existing = set().union(*(_table_numbers(doc, h) for h in _HEADLINE_TABLES))
    assert existing == (_HEADLINE_VERIFIED | _HEADLINE_REFERENCE)
    interim_nums = _table_numbers(doc, _INTERIM_HEADER_SUB)
    assert interim_nums == (_INTERIM_TABLE_VERIFIED | _INTERIM_TABLE_REFERENCE)
    assert "Grid convergence (T3b" in doc
    assert "fig_force_decomposition" in doc


def test_t4_resolution_attributed_to_t4_not_the_interim():
    """The verdict change is attributed to T4, and the interim still frames itself as isolating the
    share (not itself resolving #40).

    Scenario: Honest framing — verdict updated BY T4 (not by the interim).
    """
    doc = _doc()
    section = _interim_section(doc).lower()
    # The interim still isolates a share and points the RESOLUTION at the T4 decomposition.
    assert "isolat" in section
    assert "t4" in section
    assert ("resolved by" in section) or ("resolves" in section)
    # The interim itself does not resolve #40 (that framing survives).
    assert "does not resolve" in section or "not resolve" in section


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

_FINE = "examples/flapping_wing/forces_fine.csv"
_T3C_META = Path("examples/flapping_wing/run_metadata_t3c.json")
_FINE_DECK = "examples/flapping_wing/inputs.3d.convergence_fine"
_T3C_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0, "pitch_amp_deg": 45.0}


@pytest.mark.skipif(
    not Path(_FINE).exists(), reason="fine forces CSV not present (T3c run)"
)
def test_3grid_convergence_recomputes_from_committed_csvs():
    """The RESULTS T3c convergence headlines recompute from the committed coarse+medium+fine CSVs.

    CF_normal is monotone → assert p_obs, Richardson extrapolant, and GCI_fine are present in the doc.
    CF_chord is non-monotone → assert the non-monotone call-out is in the doc and observed_order is NaN.
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
