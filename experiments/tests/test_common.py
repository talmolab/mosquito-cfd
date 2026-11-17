"""Tests for the shared experiment helpers (plan Task 1)."""

import numpy as np
import pandas as pd

from experiments.common.data import TARGETS, holdout_configs, load_dataset, waveforms
from experiments.common.splits import carve_validation, nested_subsets


def _fake_df() -> pd.DataFrame:
    frames = []
    for name, n in (("a", 1739), ("b", 2353)):
        phase = np.arange(n) / n
        d = {"config_name": name, "wingbeat": 1, "phase": phase}
        for t in TARGETS:
            d[t] = np.sin(2 * np.pi * phase)
        frames.append(pd.DataFrame(d))
    return pd.concat(frames, ignore_index=True)


def _pool() -> list[str]:
    df = load_dataset("fine")
    return sorted(set(df.config_name) - set(holdout_configs()))


def test_waveform_resamples_known_sinusoid():
    w = waveforms(_fake_df(), n_phase=256)
    assert set(w) == {"a", "b"}
    for cfg in w:
        assert w[cfg].shape == (256, 6)
        assert np.allclose(w[cfg][:, 0], np.sin(2 * np.pi * np.arange(256) / 256), atol=1e-4)


def test_waveform_selects_requested_beat():
    df = _fake_df()
    other = df.copy()
    other["wingbeat"] = 0
    other[list(TARGETS)] = 7.0
    w = waveforms(pd.concat([df, other]), wingbeat=0, n_phase=16)
    assert np.allclose(w["a"], 7.0)


def test_carve_never_touches_holdout():
    pool = _pool()
    train, val = carve_validation(pool, seed=1234)
    assert not (set(train) | set(val)) & set(holdout_configs())
    assert not set(train) & set(val)
    assert len(val) == 3 and len(train) == 18


def test_carve_min_one_at_n3():
    train, val = carve_validation(["a", "b", "c"], seed=0)
    assert len(val) == 1 and len(train) == 2


def test_carve_is_seeded():
    pool = _pool()
    assert carve_validation(pool, seed=5) == carve_validation(pool, seed=5)
    assert any(carve_validation(pool, seed=s)[1] != carve_validation(pool, seed=5)[1] for s in range(6, 12))


def test_nested_subsets_are_nested():
    s = nested_subsets(_pool(), [3, 6, 9], seed=0)
    assert [len(s[n]) for n in (3, 6, 9)] == [3, 6, 9]
    assert set(s[3]) < set(s[6]) < set(s[9])


def test_holdout_matches_committed_split_column():
    df = load_dataset("fine")
    assert set(df[df.split == "holdout"].config_name) == set(holdout_configs())
    assert len(holdout_configs()) == 6


def test_coarse_and_fine_share_holdout():
    c = load_dataset("coarse")
    assert set(c[c.split == "holdout"].config_name) == set(holdout_configs())
