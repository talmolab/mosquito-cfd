import numpy as np
import pandas as pd

from experiments.field import pod
from experiments.field.kin2field import field_error_sq, fit_predict, nearest_snapshot_error_sq


def _index(n_cfg=6, n_phase=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_cfg):
        s, f, p = rng.uniform(35, 55), rng.uniform(0.85, 1.15), rng.uniform(30, 60)
        for ph in (np.arange(n_phase) + rng.uniform(0, 1)) / n_phase:
            rows.append((f"c{c}", ph, s, f, p))
    return pd.DataFrame(rows, columns=["config", "phase", "stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"])


def test_fit_predict_recovers_a_function_inside_the_model_family():
    idx = _index(n_cfg=16)  # degree 2 in 3 inputs has 10 terms, so more than 10 training configs
    s = (idx.stroke_amp_deg - 45) / 10
    y = np.column_stack(
        [np.sin(2 * np.pi * idx.phase) * (1 + s), np.cos(4 * np.pi * idx.phase) * s**2 + 0.3 * idx.pitch_amp_deg]
    )
    tr, te = idx.config != "c15", idx.config == "c15"
    pred = fit_predict(idx[tr], y[tr.to_numpy()], idx[te], harmonics=2, degree=2, alpha=1e-12)
    assert pred.shape == (te.sum(), 2)
    assert np.allclose(pred, y[te.to_numpy()], atol=1e-6)


def test_field_error_sq_matches_the_dense_field_difference():
    rng = np.random.default_rng(1)
    x_tr, x_te = rng.normal(size=(12, 40)), rng.normal(size=(5, 40))
    p = pod.fit(x_tr)
    r = 4
    z_true = pod.encode(p, x_te, r)
    z_pred = z_true + rng.normal(scale=0.3, size=z_true.shape)
    xc = x_te - p.mean
    expect = ((pod.decode(p, z_pred) - x_te) ** 2).sum(axis=1)
    assert np.allclose(field_error_sq(z_true, z_pred, (xc**2).sum(axis=1)), expect)


def test_field_error_sq_with_exact_coefficients_is_the_truncation_error():
    rng = np.random.default_rng(2)
    x_tr, x_te = rng.normal(size=(12, 40)), rng.normal(size=(5, 40))
    p = pod.fit(x_tr)
    z = pod.encode(p, x_te, 3)
    centred = ((x_te - p.mean) ** 2).sum(axis=1)
    assert np.isclose(np.sqrt(field_error_sq(z, z, centred).sum() / centred.sum()), pod.recon_error(p, x_te, 3))


def test_nearest_snapshot_error_sq_picks_the_closest_training_row_in_kinematics_and_phase():
    idx = _index(n_cfg=4, n_phase=8, seed=3)
    rng = np.random.default_rng(4)
    x = rng.normal(size=(len(idx), 30))
    g = x @ x.T
    tr, te = np.flatnonzero(idx.config != "c3"), np.flatnonzero(idx.config == "c3")
    err, pick = nearest_snapshot_error_sq(idx, g, tr, te)
    assert np.allclose(err, ((x[te] - x[pick]) ** 2).sum(axis=1))
    assert set(pick) <= set(tr) and len(set(idx.config.iloc[pick])) == 1  # one nearest config
    d = np.abs(idx.phase.to_numpy()[te] - idx.phase.to_numpy()[pick])
    assert np.all(np.minimum(d, 1 - d) <= 0.5 / 8 + 1e-12)  # nearest phase, circular
