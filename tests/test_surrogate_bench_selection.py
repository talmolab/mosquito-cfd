"""Ridge selection and diagnostics (add-surrogate-comparison-bench, 4b; CPU tier).

Scenarios "Fold errors are computed as specified", "Selection follows the one-standard-error
rule", "Cross-validation never sees the test configurations", "Ranks and fold ranks are
recorded", the fold clauses of "Degenerate folds are handled", and the recheck path of
"Committed bench results are consistent with their inputs" (surrogate-comparison-bench spec).
"""

from __future__ import annotations

import itertools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.surrogate_bench.ridge import (
    SelectionNotRecheckedWarning,
    apply_one_se_rule,
    fold_error_matrix,
    recheck_split,
    select_ridge,
)
from mosquito_cfd.surrogate_bench.splits import build_splits

REPO = Path(__file__).resolve().parents[1]
FINE_DATASET = REPO / "examples" / "prelim_sweep_fine" / "dataset.parquet"
TARGETS = ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"]
SPREAD = np.array([0.0, 0.2, -0.2, 0.1, -0.1])  # mean 0, std(ddof=1) = sqrt(0.025)


# --- Fold errors --------------------------------------------------------------------------


def test_fold_errors_follow_the_specified_formula():
    sse = np.array(
        [[[1.0, 4.0], [2.0, 2.0], [3.0, 0.0]]]
    )  # (1 candidate, 3 folds, 2 targets)
    sst = np.array([[2.0, 8.0], [4.0, 4.0], [6.0, 0.5]])  # unequal per fold and target
    e = fold_error_matrix(sse, sst)
    sbar = sst.mean(axis=0)
    expected = (sse[0] / sbar).mean(axis=1)
    np.testing.assert_allclose(e[0], expected, rtol=0, atol=1e-15)
    pooled = np.mean(sse[0].sum(axis=0) / sst.sum(axis=0))
    assert e[0].mean() == pytest.approx(pooled, rel=1e-12)
    assert np.std(e[0], ddof=1) > 0


def test_grid_sst_is_about_each_configurations_own_mean():
    from mosquito_cfd.surrogate_bench.ridge import grid_sst

    grids = np.array(
        [[[1.0], [3.0]], [[10.0], [14.0]]]
    )  # (2 configs, 2 phases, 1 target)
    np.testing.assert_array_equal(grid_sst(grids), [[2.0], [8.0]])


def test_a_zero_reference_variance_raises():
    sse = np.zeros((1, 3, 1))
    sst = np.zeros((3, 1))  # a target constant within every configuration: 0/0
    with pytest.raises(ValueError, match="non-finite fold error"):
        fold_error_matrix(sse, sst)


# --- The one-standard-error rule ----------------------------------------------------------


CANDIDATES = [
    (1, 1, 1e-2),
    (4, 1, 1e-2),
    (8, 1, 1e-4),
    (8, 1, 1e-2),
    (8, 2, 1e-2),
    (32, 1, 1e-2),
]
MEANS = [2.0, 1.1, 1.06, 1.05, 1.04, 1.0]


def _table(means, spread=SPREAD):
    """Fold errors per candidate; non-θ* candidates get half the spread (distinct se)."""
    best = int(np.argmin(means))
    return np.array(
        [m + (spread if i == best else 0.5 * spread) for i, m in enumerate(means)]
    )


def test_the_rule_picks_the_simplest_candidate_within_one_se():
    errors = _table(MEANS)
    sel = apply_one_se_rule(CANDIDATES, errors)
    se_star = np.std(errors[5], ddof=1) / np.sqrt(5)
    threshold = 1.0 + se_star
    assert sel["theta_star"] == (32, 1, 1e-2)
    assert sel["star_score"] == pytest.approx(1.0, abs=1e-15)
    assert sel["star_se"] == pytest.approx(se_star, rel=1e-12)
    assert sel["threshold"] == pytest.approx(threshold, rel=1e-12)
    # H = 8 wins over 4 (outside) and 32; among H = 8, d = 1 over d = 2; then the larger α.
    assert sel["chosen"] == (8, 1, 1e-2)
    assert sel["chosen_score"] == pytest.approx(1.05, abs=1e-15)
    margin = min(abs(m - threshold) / threshold for m in MEANS)
    assert sel["selection_margin"] == pytest.approx(margin, rel=1e-12)
    assert sel["selection_fragile"] is False
    assert sel["at_grid_edge"] == {"H": False, "d": True, "alpha": False}
    assert sel["star_at_grid_edge"] == {"H": True, "d": True, "alpha": False}
    assert sel["runner_up_gap"] == pytest.approx((1.04 - 1.0) / 1.0, rel=1e-12)
    shares = np.abs(errors[5]) / np.abs(errors[5]).sum()
    assert sel["fold_share_star"] == pytest.approx(shares.max(), rel=1e-12)


def test_d_breaks_ties_before_alpha():
    """Within the threshold: (8, 1, 1e-4) and (8, 2, 1e-2); d is compared before α."""
    errors = _table([2.0, 1.1, 1.06, 1.5, 1.04, 1.0])
    assert apply_one_se_rule(CANDIDATES, errors)["chosen"] == (8, 1, 1e-4)


def test_ties_on_the_score_of_theta_star_break_by_the_same_order():
    errors = _table([1.0, 1.0, 3.0, 3.0, 3.0, 1.0])
    assert apply_one_se_rule(CANDIDATES, errors)["theta_star"] == (1, 1, 1e-2)


@pytest.mark.parametrize(("offset", "fragile"), [(1e-7, True), (1e-5, False)])
def test_a_candidate_close_to_the_threshold_is_fragile(offset, fragile):
    star = (
        1.0 + 1.0 * SPREAD
    )  # se/threshold ≈ 0.07, so θ* itself is far from the threshold
    se = np.std(star, ddof=1) / np.sqrt(5)
    threshold = 1.0 + se
    near = np.full(5, threshold * (1 + offset))
    errors = np.array([np.full(5, 5.0), near, star])
    cands = [(1, 1, 1.0), (2, 1, 1.0), (32, 3, 1e-8)]
    assert apply_one_se_rule(cands, errors)["selection_fragile"] is fragile


def test_a_perfect_fit_has_zero_margin_and_is_fragile():
    errors = np.zeros((3, 5))
    sel = apply_one_se_rule([(1, 1, 1.0), (2, 1, 1.0), (4, 1, 1.0)], errors)
    assert sel["threshold"] == 0.0
    assert sel["selection_margin"] == 0.0 and sel["selection_fragile"] is True


# --- Real-data CV: blindness, ranks, degenerate folds ------------------------------------


@pytest.fixture(scope="module")
def fine():
    df = pd.read_parquet(FINE_DATASET)
    return df[df["wingbeat"] == 1].reset_index(drop=True)


@pytest.fixture(scope="module")
def splits(fine):
    return build_splits(fine)


def test_cv_never_sees_the_test_configurations(fine, splits):
    split = splits["control:2"]
    loud = fine.copy()
    loud.loc[loud["config_name"].isin(split.test), TARGETS] *= 1e6
    a = select_ridge(loud, TARGETS, split.train)
    b = select_ridge(fine[fine["config_name"].isin(split.train)], TARGETS, split.train)
    assert a.selection == b.selection
    assert a.beta.tobytes() == b.beta.tobytes()


@pytest.fixture(scope="module")
def e4_model(fine, splits):
    return select_ridge(fine, TARGETS, splits["control:e4_seed0"].train)


@pytest.fixture(scope="module")
def interp_model(fine, splits):
    return select_ridge(fine, TARGETS, splits["interpolation"].train)


def test_ranks_and_fold_ranks_on_e4(e4_model):
    r = e4_model.selection["ranks"][3]
    assert (r["P"], r["rank"], r["n_deficient_folds"]) == (17, 16, 18)
    assert r["sigma_dropped"] < r["tolerance"] and r["sigma_dropped"] < 1e-13


def test_ranks_and_fold_ranks_on_interpolation(interp_model):
    r = interp_model.selection["ranks"][3]
    assert (r["P"], r["rank"], r["min_fold_rank"], r["n_deficient_folds"]) == (
        17,
        17,
        16,
        1,
    )
    assert r["sigma_dropped"] is None


def test_selection_records_every_field(interp_model):
    sel = interp_model.selection
    for key in (
        "chosen",
        "chosen_score",
        "theta_star",
        "star_score",
        "star_se",
        "star_at_grid_edge",
        "runner_up_gap",
        "fold_share_star",
        "fold_share_chosen",
        "threshold",
        "selection_margin",
        "selection_fragile",
        "at_grid_edge",
        "ranks",
    ):
        assert key in sel, key
    h, d, alpha = sel["chosen"]
    assert (interp_model.n_harmonics, interp_model.degree, interp_model.alpha) == (
        h,
        d,
        alpha,
    )
    assert 0 < sel["fold_share_chosen"] <= 1 and sel["runner_up_gap"] >= 0


def _degenerate_frame():
    """Four configurations; stroke 35 appears in one only, so its fold has L_stroke = 1."""
    rows = []
    for name, s, f, p in [
        ("a", 35.0, 1.0, 30.0),
        ("b", 45.0, 0.85, 45.0),
        ("c", 45.0, 1.15, 60.0),
        ("d", 45.0, 1.0, 45.0),
    ]:
        phase = np.arange(16) / 16
        rows.append(
            pd.DataFrame(
                {
                    "config_name": name,
                    "stroke_amp_deg": s,
                    "frequency_fstar": f,
                    "pitch_amp_deg": p,
                    "phase": phase,
                    "CF_x": np.sin(2 * np.pi * phase) * f + 0.01 * p,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def test_a_one_value_setting_in_a_fold_drops_its_columns(monkeypatch):
    """Leaving out ``a`` (the only stroke 35) leaves stroke with one value: no stroke column."""
    from mosquito_cfd.surrogate_bench import ridge as ridge_module

    shapes = []
    real = ridge_module.polynomial_matrix

    def spy(z, exponents):
        out = real(z, exponents)
        shapes.append((z.shape[0], len(exponents), [e[0] for e in exponents]))
        return out

    monkeypatch.setattr(ridge_module, "polynomial_matrix", spy)
    frame = _degenerate_frame()
    select_ridge(frame, ["CF_x"], ["a", "b", "c", "d"])
    folds = [
        s for s in shapes if s[0] == 3
    ]  # the four 3-configuration fold fits, per d
    no_stroke = [s for s in folds if all(e == 0 for e in s[2])]
    with_stroke = [s for s in folds if any(e > 0 for e in s[2])]
    # Exactly the folds without ``a`` (one per degree) have no stroke exponent at all.
    assert len(no_stroke) == len(ridge_module.GRID_D)
    assert with_stroke  # the other folds keep it


def test_a_constant_target_makes_the_fold_error_zero_over_zero():
    frame = _degenerate_frame().assign(CF_x=lambda d: 0.5)
    with pytest.raises(ValueError, match="non-finite fold error"):
        select_ridge(frame, ["CF_x"], ["a", "b", "c", "d"])


# --- recheck_split -----------------------------------------------------------------------


def test_recheck_refits_a_fragile_split_with_a_warning(fine, splits):
    train = splits["interpolation"].train
    committed = {"chosen": (8, 2, 1e-2), "selection_fragile": True}
    with pytest.warns(SelectionNotRecheckedWarning, match="interpolation"):
        model = recheck_split(fine, TARGETS, train, committed, name="interpolation")
    assert (model.n_harmonics, model.degree, model.alpha) == (8, 2, 1e-2)


def test_recheck_of_a_non_fragile_split_compares_discrete_outputs(
    fine, splits, interp_model
):
    train = splits["interpolation"].train
    committed = dict(interp_model.selection)
    with warnings.catch_warnings():
        warnings.simplefilter("error", SelectionNotRecheckedWarning)
        model = recheck_split(fine, TARGETS, train, committed, name="interpolation")
    assert model.selection == interp_model.selection
    wrong = dict(committed, chosen=(4, 1, 1.0))
    with pytest.raises(ValueError, match="chosen"):
        recheck_split(fine, TARGETS, train, wrong, name="interpolation")


def test_candidate_grid_is_the_pre_registered_one():
    from mosquito_cfd.surrogate_bench.ridge import GRID_ALPHA, GRID_D, GRID_H

    assert GRID_H == (1, 2, 4, 8, 12, 16, 24, 32)
    assert GRID_D == (1, 2, 3)
    assert GRID_ALPHA == (1e-8, 1e-6, 1e-4, 1e-2, 1.0)
    assert len(list(itertools.product(GRID_H, GRID_D, GRID_ALPHA))) == 120


def test_selection_needs_four_training_configurations():
    """Spec: a fit needs 3, selection 4, so every leave-one-out fold is itself a fit."""
    frame = _degenerate_frame()
    with pytest.raises(ValueError, match="selection needs at least 4"):
        select_ridge(frame, ["CF_x"], ["a", "b", "c"])
