"""Hover-gate errors and yardsticks (add-surrogate-comparison-bench, 6a; CPU tier).

Scenarios of the requirement "Provisional hover gate": "GCI constants trace to their sources",
"Body-frame peaks use the phase grid", "Body-frame rotation known answers", "Yardstick values are
known answers", "Beat yardstick and its error share a window" (with the windowed normaliser),
the `late_beat` clauses of "Late-beat boundary", and "The wrap jump is recorded".
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.surrogate_bench import gate
from mosquito_cfd.surrogate_bench.ridge import N_GRID, PHASE_GRID

REPO = Path(__file__).resolve().parents[1]
FINE_DATASET = REPO / "examples" / "prelim_sweep_fine" / "dataset.parquet"
RESULTS = REPO / "examples" / "flapping_wing" / "RESULTS.md"
T3C = {
    "coarse": REPO / "examples" / "flapping_wing" / "forces_t2a_newconv.csv",
    "medium": REPO / "examples" / "flapping_wing" / "forces_medium.csv",
    "fine": REPO / "examples" / "flapping_wing" / "forces_fine.csv",
}
TARGETS = ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"]
STROKE, PITCH, FSTAR = 55.0, 45.0, 0.85


# --- GCI constants -----------------------------------------------------------------------


@pytest.mark.skipif(not T3C["fine"].exists(), reason="T3c fine forces CSV not present")
def test_gci_constants_equal_the_computed_t3c_values():
    from mosquito_cfd.benchmarks.wing_convergence import (
        wing_grid_convergence_from_body_forces,
    )

    out = wing_grid_convergence_from_body_forces(
        str(T3C["coarse"]),
        str(T3C["medium"]),
        str(T3C["fine"]),
        f_star=1.0,
        phi_amp_deg=70.0,
        pitch_amp_deg=45.0,
    )
    assert gate.GCI_FINE["normal_peak"] == pytest.approx(
        out["cf_normal"]["gci_fine"], abs=1e-4
    )
    assert gate.GCI_FINE["chord_peak"] == pytest.approx(
        out["cf_chord"]["gci_fine"], abs=1e-4
    )
    assert gate.OBSERVED_ORDER["normal_peak"] == pytest.approx(
        out["cf_normal"]["observed_order"], abs=1e-4
    )
    assert gate.OBSERVED_ORDER["chord_peak"] == pytest.approx(
        out["cf_chord"]["observed_order"], abs=1e-4
    )


def test_gci_constants_equal_the_results_document():
    parsed = gate.parse_gci_from_results(RESULTS.read_text(encoding="utf-8"))
    assert parsed == {"normal_peak": 3.7, "chord_peak": 27.6}
    for comp, percent in parsed.items():
        assert round(100 * gate.GCI_FINE[comp], 1) == percent


def test_a_missing_gci_table_is_named():
    with pytest.raises(ValueError, match="CF_chord"):
        gate.parse_gci_from_results(
            "**CF_normal (z, lift)** —\n\n| GCI_fine | 3.7 % |\n"
        )


# --- Body-frame rotation -----------------------------------------------------------------


def _angles(phase):
    phi = np.deg2rad(STROKE) * np.sin(2 * np.pi * phase)
    alpha = np.deg2rad(PITCH) * np.cos(2 * np.pi * phase)
    return phi, alpha


@pytest.mark.parametrize("phase", [0.0, 0.25])
def test_the_wing_normal_rotates_to_unit_normal_force(phase):
    phi, alpha = _angles(phase)
    normal = np.array(
        [np.cos(phi) * np.sin(alpha), np.sin(phi) * np.sin(alpha), np.cos(alpha)]
    )
    out = gate.body_frame_series(
        np.array([phase]), normal[None, :], stroke=STROKE, fstar=FSTAR, pitch=PITCH
    )
    assert out["normal"][0] == pytest.approx(1.0, abs=1e-12)
    assert out["chord"][0] == pytest.approx(0.0, abs=1e-12)


def test_lab_unit_vectors_at_phase_one_eighth():
    phi, alpha = _angles(0.125)
    lab = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    out = gate.body_frame_series(
        np.array([0.125, 0.125]), lab, stroke=STROKE, fstar=FSTAR, pitch=PITCH
    )
    np.testing.assert_allclose(
        [out["normal"][0], out["chord"][0], out["span"][0]],
        [np.cos(phi) * np.sin(alpha), np.cos(phi) * np.cos(alpha), -np.sin(phi)],
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        [out["normal"][1], out["chord"][1]],
        [np.sin(phi) * np.sin(alpha), np.sin(phi) * np.cos(alpha)],
        rtol=0,
        atol=1e-12,
    )
    assert out["normal"][0] == pytest.approx(0.410381, abs=1e-6)
    assert out["normal"][1] == pytest.approx(0.331028, abs=1e-6)


@pytest.fixture(scope="module")
def fine():
    return pd.read_parquet(FINE_DATASET)


def _config_beat(fine, name, beat=1):
    rows = fine[(fine["config_name"] == name) & (fine["wingbeat"] == beat)]
    return rows.sort_values("phase")


def test_body_frame_peaks_use_the_phase_grid(fine):
    rows = _config_beat(fine, "s55_f085_p45")
    settings = dict(stroke=55.0, fstar=0.85, pitch=45.0)
    grid = gate.lab_grid(rows)
    peaks = gate.peak_values(grid, **settings)
    assert peaks["normal_peak"] == pytest.approx(1.988, abs=1e-3)
    raw = gate.body_frame_series(
        rows["phase"].to_numpy(), rows[["CF_x", "CF_y", "CF_z"]].to_numpy(), **settings
    )
    assert np.abs(raw["normal"]).max() == pytest.approx(2.054, abs=1e-3)


# --- Yardstick known answers --------------------------------------------------------------


def _synthetic_beats(n_beats=2, scale=1.0):
    """Per-beat grid values (256, 6) for one configuration; beat 0 differs on the window."""
    phi = PHASE_GRID
    base = np.column_stack(
        [
            np.sin(2 * np.pi * phi) + 0.3,
            0.5 * np.cos(2 * np.pi * phi),
            1.2 * np.sin(2 * np.pi * phi + 0.4),
            0.2 * np.sin(4 * np.pi * phi),
            0.7 * np.cos(2 * np.pi * phi),
            0.1 * np.sin(2 * np.pi * phi),
        ]
    )
    beats = {k: scale * base.copy() for k in range(n_beats)}
    return beats


SETTINGS = dict(stroke=45.0, fstar=1.0, pitch=45.0)
PEAKS = {t: 2.0 for t in TARGETS}


def test_coarse_vs_fine_known_answers():
    fine_beats = _synthetic_beats()
    coarse = 1.1 * fine_beats[1]
    ys = gate.config_yardsticks(
        beats=fine_beats,
        coarse=coarse,
        settings=SETTINGS,
        peaks=PEAKS,
        targets=TARGETS,
    )
    assert ys["normal_peak"]["coarse_vs_fine"]["value"] == pytest.approx(0.1, abs=1e-12)
    assert ys["chord_peak"]["coarse_vs_fine"]["value"] == pytest.approx(0.1, abs=1e-12)
    assert ys["normal_peak"]["coarse_vs_fine"]["upper_bound"] is True
    rms = np.sqrt(np.mean(fine_beats[1][:, 3] ** 2))
    assert ys["CF_mx"]["coarse_vs_fine"]["value"] == pytest.approx(
        0.1 * rms / 2.0, rel=1e-12
    )
    for comp, p in (("normal_peak", 1.3773), ("chord_peak", 1.3655), ("CF_mx", 1.3773)):
        assert ys[comp]["coarse_vs_fine_scaled"]["value"] == pytest.approx(
            ys[comp]["coarse_vs_fine"]["value"] / (4**p - 1), rel=1e-12
        )


def test_beat_one_versus_two_known_answer_and_shared_window():
    beats = _synthetic_beats()
    diff = 0.05 * np.sin(6 * np.pi * PHASE_GRID)
    beats[0][:, 0] = beats[1][:, 0] - diff
    ys = gate.config_yardsticks(
        beats=beats, coarse=None, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    window = slice(13, None)
    assert 13 / N_GRID >= 0.05 > 12 / N_GRID
    expected = np.sqrt(np.mean(diff[window] ** 2)) / 2.0
    assert ys["CF_x"]["beat1_vs_beat2"]["value"] == pytest.approx(expected, rel=1e-12)
    assert ys["CF_y"]["beat1_vs_beat2"]["value"] == pytest.approx(0.0, abs=1e-15)
    # A difference only before the window leaves the yardstick at zero.
    early = _synthetic_beats()
    early[0][:13, 0] += 5.0
    ys_early = gate.config_yardsticks(
        beats=early, coarse=None, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    assert ys_early["CF_x"]["beat1_vs_beat2"]["value"] == 0.0
    model = early[1].copy()
    model[:13, 0] += 3.0  # a model error only before the window
    errors = gate.config_errors(
        model=model, cfd=early[1], settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    assert errors["CF_x"]["window"] == 0.0 and errors["CF_x"]["full"] > 0


def test_the_beat_peak_normaliser_is_windowed():
    """Beat 1's global maximum lies at phase 5/256 ≈ 0.02, outside the window."""
    beats = _synthetic_beats()
    beat1 = beats[1]
    big = np.zeros(N_GRID)
    big[5] = 50.0  # larger than anything inside the window
    for j in range(3):
        beat1[:, j] = beat1[:, j] + big
    beat0 = beat1.copy()
    beat0[13:] = 0.9 * beat1[13:]  # 0.9 x beat 1 on the window only
    beats[0] = beat0
    ys = gate.config_yardsticks(
        beats=beats, coarse=None, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    assert ys["normal_peak"]["beat1_vs_beat2"]["value"] == pytest.approx(0.1, abs=1e-12)
    model = beat0.copy()  # off by 10 % on the window, exact outside it
    errors = gate.config_errors(
        model=model, cfd=beat1, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    assert errors["normal_peak"]["window"] == pytest.approx(0.1, abs=1e-12)
    assert errors["normal_peak"]["full"] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_a_non_finite_model_grid_gives_nan_errors_not_a_crash(bad):
    """A diverged seed reaches the verdict as NaN (spec "Gate boundaries"), never raises."""
    cfd = _synthetic_beats()[1]
    model = cfd.copy()
    model[40, 0] = bad
    errors = gate.config_errors(
        model=model, cfd=cfd, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    # The poisoned column and both body-frame peaks (built from CF_x..CF_z) are NaN, inf
    # included, so the verdict takes the spec's NaN path rather than a finite margin of 0.
    for comp in ("CF_x", *gate.PEAKS):
        assert np.isnan(errors[comp]["full"]) and np.isnan(errors[comp]["window"]), comp
    # Untouched columns keep their real (zero) error.
    for comp in TARGETS[1:]:
        assert errors[comp]["full"] == 0.0 and errors[comp]["window"] == 0.0, comp


def test_the_late_beat_yardstick_needs_four_beats():
    ys3 = gate.config_yardsticks(
        beats=_synthetic_beats(3),
        coarse=None,
        settings=SETTINGS,
        peaks=PEAKS,
        targets=TARGETS,
    )
    assert ys3["CF_z"]["late_beat"] == {"unavailable": "fewer than 4 beats"}
    beats = _synthetic_beats(4)
    beats[3][:, 1] = beats[2][:, 1] + 0.02
    ys4 = gate.config_yardsticks(
        beats=beats, coarse=None, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    assert ys4["CF_y"]["late_beat"]["value"] == pytest.approx(0.02 / 2.0, rel=1e-12)
    assert ys4["CF_y"]["late_beat"]["compares"] == [3, 2]


def test_a_coarse_corpus_without_the_target_beat_is_unavailable():
    ys = gate.config_yardsticks(
        beats=_synthetic_beats(4),
        coarse=None,
        coarse_reason="coarse corpus lacks target beat 3",
        settings=SETTINGS,
        peaks=PEAKS,
        targets=TARGETS,
    )
    assert ys["CF_x"]["coarse_vs_fine"] == {
        "unavailable": "coarse corpus lacks target beat 3"
    }
    assert ys["normal_peak"]["late_beat"]["value"] >= 0.0


def test_grid_gci_applies_to_the_peaks_only():
    ys = gate.config_yardsticks(
        beats=_synthetic_beats(),
        coarse=None,
        settings=SETTINGS,
        peaks=PEAKS,
        targets=TARGETS,
    )
    assert ys["normal_peak"]["grid_gci"]["value"] == gate.GCI_FINE["normal_peak"]
    assert ys["CF_mx"]["grid_gci"] == {"not_applicable": True}


# --- Wrap jump ------------------------------------------------------------------------------


def test_the_wrap_jump_of_s55_f085_p45(fine):
    rows = _config_beat(fine, "s55_f085_p45")
    jumps = gate.config_wrap_jumps(
        rows, stroke=55.0, fstar=0.85, pitch=45.0, peaks=PEAKS
    )
    normal = jumps["normal_peak"]
    assert normal["last_but_one"] == pytest.approx(0.0242, abs=1e-3)
    assert normal["raw"] == pytest.approx(0.0352, abs=1e-3)
    assert normal["slope_corrected"] == pytest.approx(0.0260, abs=1e-3)
    assert normal["gap_spacings"] == pytest.approx(0.941, abs=1e-3)


def test_wrap_jump_sawtooth_known_answer():
    a, h, phi0, delta, peak = -3.0, 1 / 50, 0.01, 0.37, 2.0
    phase = phi0 + h * np.arange(50)
    values = a * phase
    values[-1] += delta
    out = gate.wrap_jump(phase, values, peak)
    assert out["slope_corrected"] == pytest.approx(abs(a) / peak, rel=1e-12)
    assert out["raw"] == pytest.approx(
        abs(a * (phase[-1] - phi0) + delta) / peak, rel=1e-12
    )
    assert out["last_but_one"] == pytest.approx(
        abs(a) * (phase[-2] - phi0) / peak, rel=1e-12
    )
    assert out["gap_spacings"] == pytest.approx((1 + phi0 - phase[-1]) / h, rel=1e-9)


def test_a_non_finite_value_before_the_window_spares_the_windowed_peaks():
    cfd = _synthetic_beats()[1]
    model = cfd.copy()
    model[2, 0] = np.nan  # before WINDOW_START
    errors = gate.config_errors(
        model=model, cfd=cfd, settings=SETTINGS, peaks=PEAKS, targets=TARGETS
    )
    for comp in gate.PEAKS:
        assert np.isnan(errors[comp]["full"]), comp
        assert errors[comp]["window"] == pytest.approx(0.0, abs=1e-12), comp
    assert np.isnan(errors["CF_x"]["full"]) and errors["CF_x"]["window"] == 0.0
