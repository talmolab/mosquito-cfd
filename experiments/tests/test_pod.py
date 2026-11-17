import numpy as np
import pandas as pd
import pytest

from experiments.field import pod


def _rank3(n_snap=40, n_dof=500, seed=0):
    rng = np.random.default_rng(seed)
    modes, _ = np.linalg.qr(rng.normal(size=(n_dof, 3)))
    coef = rng.normal(size=(n_snap, 3)) * np.array([5.0, 2.0, 1.0])
    mean = rng.normal(size=n_dof)
    return (mean + coef @ modes.T).astype(np.float32), modes


def test_pod_recovers_rank3():
    x, modes = _rank3()
    p = pod.fit(x)
    assert pod.energy_fraction(p)[2] > 1 - 1e-6
    assert pod.recon_error(p, x, 3) < 1e-5
    # the leading three POD modes span the planted subspace
    proj = modes @ (modes.T @ p.modes[:3].T)
    assert np.allclose(proj, p.modes[:3].T, atol=1e-4)


def test_modes_are_orthonormal():
    p = pod.fit(_rank3()[0])
    g = p.modes[:3] @ p.modes[:3].T
    assert np.allclose(g, np.eye(3), atol=1e-5)


def test_recon_error_monotone_in_r():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(30, 200)).astype(np.float32)
    p = pod.fit(x)
    errs = [pod.recon_error(p, x, r) for r in (1, 2, 4, 8, 16, 29)]
    assert all(a >= b for a, b in zip(errs, errs[1:]))
    assert errs[-1] < 1e-4  # 30 mean-removed snapshots have rank 29


def test_recon_error_on_unseen_data_uses_training_mean():
    x, _ = _rank3(seed=0)
    y, _ = _rank3(seed=5)  # a different subspace and mean
    p = pod.fit(x)
    assert pod.recon_error(p, y, 3) > 0.5


def test_encode_decode_roundtrip_in_subspace():
    x, _ = _rank3()
    p = pod.fit(x)
    assert np.allclose(pod.decode(p, pod.encode(p, x, 3)), x, atol=1e-3)


def test_basis_uses_training_snapshots_only():
    idx = pd.DataFrame({"config": ["a", "a", "b", "h"], "step": [1, 2, 1, 1], "wingbeat": [1, 1, 1, 1]})
    assert set(pod.training_rows(idx, holdout=("h",)).config) == {"a", "b"}
    with pytest.raises(ValueError, match="holdout"):
        pod.assert_no_holdout(idx, holdout=("h",))


def test_gram_path_matches_direct():
    rng = np.random.default_rng(3)
    train = rng.normal(size=(25, 300)).astype(np.float32)
    test = (rng.normal(size=(7, 300)) + 0.5).astype(np.float32)
    p = pod.fit(train)
    pg = pod.fit_gram(pod.gram(train, block=64))
    assert np.allclose(pg.sing[:20], p.sing[:20], rtol=1e-6)
    assert np.allclose(pod.energy_fraction_gram(pg)[:20], pod.energy_fraction(p)[:20])
    g_xt = pod.gram(test, train, block=64)
    sq = np.sum(test.astype(np.float64) ** 2, axis=1)
    for r in (1, 5, 12):
        assert abs(pod.recon_error_gram(pg, g_xt, sq, r) - pod.recon_error(p, test, r)) < 1e-8
    assert np.allclose(np.abs(pod.encode_gram(pg, g_xt)[:, :5]), np.abs(pod.encode(p, test, 5)), atol=1e-6)
    modes, mean = pod.modes_from_gram(pg, train, 4, block=64)
    assert np.allclose(mean, p.mean, atol=1e-5) and np.allclose(np.abs(modes), np.abs(p.modes[:4]), atol=1e-4)
