import numpy as np
import pandas as pd

from experiments.common.data import load_dataset
from experiments.common.features import make_feature_fn
from experiments.common.ridge import fourier_poly_fit_predict
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS, build_features


def _df():
    df = load_dataset("fine")
    return df[df.wingbeat == 1].iloc[::50]


def test_default_feature_fn_matches_repo():
    df = _df()
    x, names = make_feature_fn()(df)
    x0, names0 = build_features(df)
    assert names == names0 and np.array_equal(x, x0)


def test_harmonics_add_columns():
    df = _df()
    x, names = make_feature_fn(harmonics=3)(df)
    assert x.shape[1] == build_features(df)[0].shape[1] + 4
    assert names[-1] == "phase_cos3"
    assert np.allclose(x[:, -1], np.cos(2 * np.pi * 3 * df.phase.to_numpy()))


def test_drop_removes_named_input():
    x, names = make_feature_fn(drop=("frequency_fstar",))(_df())
    assert "frequency_fstar" not in names and x.shape[1] == 4


def test_use_re_replaces_frequency():
    df = _df()
    x, names = make_feature_fn(use_re=True)(df)
    assert "frequency_fstar" not in names and "reynolds" in names
    assert np.array_equal(x[:, names.index("reynolds")], df.reynolds.to_numpy(dtype=float))


def _synthetic():
    rows = []
    for s in (35.0, 45.0, 55.0):
        for f in (0.85, 1.0, 1.15):
            phase = np.arange(200) / 200
            d = {"config_name": f"s{s:.0f}_f{f}", "stroke_amp_deg": s, "frequency_fstar": f, "pitch_amp_deg": 45.0,
                 "phase": phase, "wingbeat": 1}
            for t in TARGET_COLUMNS:
                d[t] = (1 + 0.05 * (s - 45) + 2.0 * (f - 1)) * np.sin(2 * np.pi * phase) + 0.3 * np.cos(4 * np.pi * phase)
            rows.append(pd.DataFrame(d))
    return pd.concat(rows, ignore_index=True)


def test_ridge_recovers_separable_waveform():
    df = _synthetic()
    test = ["s45_f1.0"]
    train = [c for c in df.config_name.unique() if c not in test]
    pred = fourier_poly_fit_predict(df, train, test, harmonics=2, degree=1)
    y = df[df.config_name.isin(test)][TARGET_COLUMNS].to_numpy()
    assert pred.shape == y.shape
    assert np.sqrt(np.mean((pred - y) ** 2)) < 1e-3
