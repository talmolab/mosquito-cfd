"""Ridge reference fit (add-surrogate-comparison-bench, 4a; CPU tier).

Scenarios of the requirement "Ridge reference model" (surrogate-comparison-bench spec): the
identifiability cap, both known answers, standardisation over configurations, the unpenalised
intercept, equal weight, ill-conditioning, malformed input, the 2-configuration clause of
"Degenerate folds", the E4 rank, "The reference is never a checkpoint", and `ridge_fixed`.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.surrogate_bench import ridge
from mosquito_cfd.surrogate_bench.ridge import (
    N_GRID,
    RIDGE_FIXED_POINT,
    config_coefficients,
    fit_ridge,
    fit_ridge_fixed,
    fourier_coefficients,
    monomial_exponents,
    rank_record,
    resample_beat,
    solve_ridge,
)
from mosquito_cfd.surrogate_bench.splits import SETTINGS, build_splits

REPO = Path(__file__).resolve().parents[1]
FINE_DATASET = REPO / "examples" / "prelim_sweep_fine" / "dataset.parquet"
RIDGE_SOURCE = REPO / "src" / "mosquito_cfd" / "surrogate_bench" / "ridge.py"
GRID_PHASES = np.arange(N_GRID) / N_GRID
STROKE, FSTAR, PITCH = (35.0, 45.0, 55.0), (0.85, 1.0, 1.15), (30.0, 45.0, 60.0)


def _truth(s, f, p, phase):
    """An exact degree-2 polynomial in the settings times [1, cos 2πφ, sin 4πφ]."""
    p0 = 1.0 + 0.02 * s - 0.5 * f + 0.001 * s * p + 0.3 * f * f
    p1 = 0.5 - 0.01 * p + 0.2 * s * f / 45.0 + 0.0001 * s * s
    p2 = -0.3 + 0.004 * p * f - 0.00005 * p * p
    return p0 + p1 * np.cos(2 * np.pi * phase) + p2 * np.sin(4 * np.pi * phase)


def _grid_frame(phases_for, targets=("CF_x",), truth=_truth):
    rows = []
    for s, f, p in itertools.product(STROKE, FSTAR, PITCH):
        phase = phases_for(s, f, p)
        frame = pd.DataFrame(
            {
                "config_name": f"s{s:g}_f{f:g}_p{p:g}",
                "stroke_amp_deg": s,
                "frequency_fstar": f,
                "pitch_amp_deg": p,
                "phase": phase,
            }
        )
        for t in targets:
            frame[t] = truth(s, f, p, phase)
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def _held_out(frame, names):
    is_test = frame["config_name"].isin(names)
    return frame[~is_test], frame[is_test]


HELD = ["s45_f1_p45", "s35_f1.15_p45", "s55_f0.85_p60"]


# --- Identifiability cap -------------------------------------------------------------------


def test_cap_on_three_levels_gives_seventeen_columns():
    exps = monomial_exponents((3, 3, 3), 3)
    assert len(exps) == 17
    assert all(max(e) <= 2 for e in exps)
    assert (3, 0, 0) not in exps and (0, 0, 3) not in exps
    assert exps[0] == (0, 0, 0)  # the intercept is column 0


def test_cap_on_a_two_level_setting():
    exps = monomial_exponents((2, 3, 3), 3)
    assert len(exps) == 14
    assert all(e[0] <= 1 for e in exps)


def test_a_one_level_setting_contributes_no_column():
    exps = monomial_exponents((1, 3, 3), 3)
    assert all(e[0] == 0 for e in exps)


# --- Fourier projection ---------------------------------------------------------------------


def test_fourier_projection_is_exact_for_a_band_limited_signal():
    h = np.arange(1, 33)
    rng = np.random.default_rng(3)
    a0, ac, as_ = rng.normal(), rng.normal(size=32), rng.normal(size=32)
    signal = a0 + (
        ac[None, :] * np.cos(2 * np.pi * np.outer(GRID_PHASES, h))
        + as_[None, :] * np.sin(2 * np.pi * np.outer(GRID_PHASES, h))
    ).sum(axis=1)
    coeffs = fourier_coefficients(signal[:, None], 32)[:, 0]
    expected = np.empty(65)
    expected[0], expected[1::2], expected[2::2] = a0, ac, as_
    np.testing.assert_allclose(coeffs, expected, rtol=0, atol=1e-12)


def test_resampling_on_grid_samples_is_exact_and_periodic():
    values = np.sin(2 * np.pi * GRID_PHASES)[:, None]
    shuffled = np.random.default_rng(0).permutation(N_GRID)
    out = resample_beat(GRID_PHASES[shuffled], values[shuffled])
    assert out.tobytes() == values.tobytes()


# --- Known answers ----------------------------------------------------------------------------


def test_known_answer_on_the_phase_grid():
    frame = _grid_frame(lambda *_: GRID_PHASES)
    train, test = _held_out(frame, HELD)
    model = fit_ridge(train, ["CF_x"], n_harmonics=2, degree=2, alpha=1e-12)
    pred = model.predict(test)[:, 0]
    truth = test["CF_x"].to_numpy()
    assert np.max(np.abs(pred - truth)) / np.max(np.abs(truth)) <= 1e-8


@pytest.fixture(scope="module")
def real_phases():
    df = pd.read_parquet(FINE_DATASET, columns=["config_name", "phase", "wingbeat"])
    rows = df[(df["config_name"] == "s45_f100_p45") & (df["wingbeat"] == 1)]
    return np.sort(rows["phase"].to_numpy())


def test_known_answer_at_realistic_sampling(real_phases):
    """Non-uniform real phases: the resample error only; predictions at each row's own phase."""
    frame = _grid_frame(lambda *_: real_phases)
    train, test = _held_out(frame, HELD)
    model = fit_ridge(train, ["CF_x"], n_harmonics=2, degree=2, alpha=1e-12)
    pred = model.predict(test)[:, 0]
    truth = test["CF_x"].to_numpy()
    assert np.max(np.abs(pred - truth)) / np.max(np.abs(truth)) <= 1e-5


# --- Standardisation, intercept, equal weight ----------------------------------------------


def test_kinematics_are_standardised_over_configurations():
    """α = 1 at the fixed point H = 1, d = 1: a hand computation with one value per config."""
    rng = np.random.default_rng(5)

    def phases(s, f, p):
        n = 8 if s == 35.0 else 40  # unequal row counts per configuration
        return np.arange(n) / n

    frame = _grid_frame(phases, truth=lambda s, f, p, ph: 0.01 * s + f + 0.0 * ph)
    frame["CF_x"] += 0.001 * rng.normal(size=len(frame))
    model = fit_ridge(frame, ["CF_x"], n_harmonics=1, degree=1, alpha=1.0)

    names, settings, coeffs = config_coefficients(frame, ["CF_x"], 1)
    mean, std = settings.mean(axis=0), settings.std(axis=0)
    z = (settings - mean) / std
    m = np.column_stack([np.ones(len(z)), z])  # degree 1: [1, z_s, z_f, z_p]
    lam = 1.0 * len(z)
    d = np.diag([0.0, 1.0, 1.0, 1.0])
    beta = np.linalg.solve(m.T @ m + lam * d, m.T @ coeffs.reshape(len(z), -1))
    np.testing.assert_allclose(model.beta, beta, rtol=1e-10, atol=1e-12)

    rows = frame[list(SETTINGS)].to_numpy()
    z_rows = (settings - rows.mean(axis=0)) / rows.std(axis=0)
    beta_rows = np.linalg.solve(
        np.column_stack([np.ones(len(z)), z_rows]).T
        @ np.column_stack([np.ones(len(z)), z_rows])
        + lam * d,
        np.column_stack([np.ones(len(z)), z_rows]).T @ coeffs.reshape(len(z), -1),
    )
    assert not np.allclose(model.beta, beta_rows, rtol=1e-6)


def test_the_intercept_is_not_shrunk():
    frame = _grid_frame(lambda *_: GRID_PHASES[::8], truth=lambda *a: 10.0 + 0 * a[3])
    model = fit_ridge(frame, ["CF_x"], n_harmonics=1, degree=1, alpha=1.0)
    np.testing.assert_allclose(model.predict(frame)[:, 0], 10.0, rtol=0, atol=1e-10)


def test_each_configuration_weighs_once():
    """k/256 and k/768 samplings of the same truth give bitwise-equal coefficient vectors."""
    fine = np.arange(768) / 768
    a = pd.DataFrame({"phase": GRID_PHASES, "CF_x": np.sin(2 * np.pi * GRID_PHASES)})
    b = pd.DataFrame({"phase": fine, "CF_x": np.sin(2 * np.pi * fine)})
    for frame, name in ((a, "a"), (b, "b")):
        frame["config_name"] = name
        frame["stroke_amp_deg"], frame["frequency_fstar"], frame["pitch_amp_deg"] = (
            45.0,
            1.0,
            45.0,
        )
    names, _, coeffs = config_coefficients(pd.concat([a, b]), ["CF_x"], 4)
    assert names == ["a", "b"] and coeffs.shape[0] == 2
    assert coeffs[0].tobytes() == coeffs[1].tobytes()


# --- solve_ridge under ill-conditioning ----------------------------------------------------


def _ill_conditioned(seed=0):
    rng = np.random.default_rng(seed)
    n, s, lam = 27, np.logspace(0, -7, 16), 1e-12
    g = rng.standard_normal((n, 16))
    u, _ = np.linalg.qr(g - g.mean(axis=0))
    v, _ = np.linalg.qr(rng.standard_normal((16, 16)))
    a = rng.standard_normal((n, 3))
    m = np.column_stack([np.ones(n), u @ np.diag(s) @ v.T])
    closed = np.vstack([a.mean(axis=0), v @ np.diag(s / (s**2 + lam)) @ u.T @ a])
    return m, a, lam, closed


def _rel(beta, closed):
    return np.max(np.abs(beta - closed)) / np.max(np.abs(closed))


def test_solve_ridge_survives_ill_conditioning():
    m, a, lam, closed = _ill_conditioned()
    assert _rel(solve_ridge(m, a, lam), closed) <= 1e-8
    d = np.eye(m.shape[1])
    d[0, 0] = 0.0
    normal = np.linalg.solve(m.T @ m + lam * d, m.T @ a)
    assert _rel(normal, closed) >= 1e-7


# --- Malformed input and degenerate training sets ------------------------------------------


def _small_frame(n_configs=4):
    rows = []
    for i in range(n_configs):
        rows.append(
            pd.DataFrame(
                {
                    "config_name": f"c{i}",
                    "stroke_amp_deg": 35.0 + 10 * (i % 3),
                    "frequency_fstar": 1.0,
                    "pitch_amp_deg": 30.0 + 15 * (i // 3),
                    "phase": np.arange(8) / 8,
                    "CF_x": np.sin(2 * np.pi * np.arange(8) / 8) + i,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _break(kind):
    frame = _small_frame()
    if kind == "nan":
        frame.loc[3, "CF_x"] = np.nan
    elif kind == "phase_one":
        frame.loc[3, "phase"] = 1.0
    elif kind == "phase_negative":
        frame.loc[3, "phase"] = -0.1
    elif kind == "one_row":
        frame = frame[~((frame["config_name"] == "c1") & (frame["phase"] > 0))]
    elif kind == "duplicate_phase":
        frame.loc[4, "phase"] = frame.loc[3, "phase"]
    elif kind == "two_configs":
        frame = frame[frame["config_name"].isin(["c0", "c1"])]
    return frame


@pytest.mark.parametrize(
    ("kind", "match"),
    [
        ("nan", "non-finite"),
        ("phase_one", "phase"),
        ("phase_negative", "phase"),
        ("one_row", "fewer than 2 rows"),
        ("duplicate_phase", "duplicate phase"),
        ("two_configs", "at least 3"),
    ],
)
def test_malformed_input_is_rejected(kind, match):
    with pytest.raises(ValueError, match=match):
        fit_ridge(_break(kind), ["CF_x"], n_harmonics=1, degree=1, alpha=1.0)


# --- Ranks, ridge_fixed and the parameter count ---------------------------------------------


@pytest.fixture(scope="module")
def fine_target_beat():
    df = pd.read_parquet(FINE_DATASET)
    return df[df["wingbeat"] == 1].reset_index(drop=True)


TARGETS = ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"]


def test_e4_split_is_rank_deficient_at_degree_three(fine_target_beat):
    split = build_splits(fine_target_beat)["control:e4_seed0"]
    train = fine_target_beat[fine_target_beat["config_name"].isin(split.train)]
    model = fit_ridge_fixed(train, TARGETS)
    record = model.rank
    assert record["P"] == 17 and record["rank"] == 16
    assert record["sigma_dropped"] is not None
    assert (
        record["sigma_dropped"] < record["tolerance"]
        and record["sigma_dropped"] < 1e-13
    )
    assert record["tolerance"] == max(18, 17) * np.finfo(float).eps


def test_interpolation_is_full_rank_with_no_dropped_value(fine_target_beat):
    split = build_splits(fine_target_beat)["interpolation"]
    train = fine_target_beat[fine_target_beat["config_name"].isin(split.train)]
    record = rank_record(fit_ridge_fixed(train, TARGETS).config_matrix)
    assert record["P"] == 17 and record["rank"] == 17
    assert record["sigma_dropped"] is None
    assert 0 < record["sigma_retained"] <= 1


@pytest.mark.parametrize("face", ["face:stroke_amp_deg=55", "face:pitch_amp_deg=30"])
def test_a_face_fit_recomputes_the_cap_from_its_own_training_levels(
    fine_target_beat, face
):
    """Spec "The identifiability cap": a face leaves its setting 2 levels, so P = 14 at d = 3."""
    split = build_splits(fine_target_beat)[face]
    train = fine_target_beat[fine_target_beat["config_name"].isin(split.train)]
    model = fit_ridge_fixed(train, TARGETS)
    assert model.rank["P"] == 14
    assert model.n_params == 6 * (2 * 16 + 1) * 14


def test_ridge_fixed_is_the_pre_registered_point_without_selection(fine_target_beat):
    assert RIDGE_FIXED_POINT == {"n_harmonics": 16, "degree": 3, "alpha": 1e-6}
    split = build_splits(fine_target_beat)["interpolation"]
    train = fine_target_beat[fine_target_beat["config_name"].isin(split.train)]
    model = fit_ridge_fixed(train, TARGETS)
    assert (model.n_harmonics, model.degree, model.alpha) == (16, 3, 1e-6)
    assert model.selection is None
    assert model.n_params == 6 * (2 * 16 + 1) * 17


def test_lambda_scales_with_the_number_of_configurations():
    """λ = α · n_train_configs: doubling the configurations at fixed α keeps β unchanged."""
    frame = _grid_frame(lambda *_: GRID_PHASES[::16])
    twice = pd.concat(
        [frame, frame.assign(config_name=frame["config_name"] + "_copy")],
        ignore_index=True,
    )
    one = fit_ridge(frame, ["CF_x"], n_harmonics=1, degree=2, alpha=1e-2)
    two = fit_ridge(twice, ["CF_x"], n_harmonics=1, degree=2, alpha=1e-2)
    np.testing.assert_allclose(one.beta, two.beta, rtol=1e-10, atol=1e-12)


# --- The reference is never a checkpoint ---------------------------------------------------


def test_ridge_module_imports_and_names_no_model_io():
    tree = ast.parse(RIDGE_SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {
        "torch",
        "physicsnemo",
        "scipy",
        "sklearn",
        "pickle",
        "joblib",
    }
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"save", "load", "load_surrogate", "dump"}
    assert hasattr(ridge, "solve_ridge")
