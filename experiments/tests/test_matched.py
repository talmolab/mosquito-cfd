import numpy as np

from experiments.field import pod
from experiments.field.matched import box_mask, masked_gram, restricted_residuals
from mosquito_cfd.benchmarks.wing_kinematics import rotation_matrix


def _axes(n=(40, 32, 24), dx=0.125):
    return [dx / 2 + dx * np.arange(k) for k in n]


def test_box_mask_identity_rotation_is_axis_aligned_box():
    x, y, z = _axes()
    hinge = np.array([2.0, 1.0, 1.5])
    m = box_mask(x, y, z, np.eye(3), hinge, lo=(-1.0, 0.0, -0.5), hi=(1.0, 2.0, 0.5))
    expect = (
        ((x >= 1.0) & (x < 3.0))[:, None, None]
        & ((y >= 1.0) & (y < 3.0))[None, :, None]
        & ((z >= 1.0) & (z < 2.0))[None, None, :]
    )
    assert m.shape == (40, 32, 24) and np.array_equal(m, expect)


def test_box_mask_rotated_keeps_volume_and_only_cells_inside_the_box():
    x, y, z = _axes(n=(64, 64, 64), dx=0.0625)
    hinge = np.array([2.0, 2.0, 2.0])
    r = rotation_matrix(np.deg2rad(40.0), np.deg2rad(25.0))
    lo, hi = np.array([-0.5, -1.0, -0.75]), np.array([0.5, 1.0, 0.75])
    m = box_mask(x, y, z, r, hinge, lo=lo, hi=hi)
    assert abs(m.sum() * 0.0625**3 / np.prod(hi - lo) - 1.0) < 0.02
    g = np.stack(np.meshgrid(x, y, z, indexing="ij"), axis=-1)[m]
    xi = (g - hinge) @ r  # R^T (p - h)
    assert np.all(xi >= lo - 1e-12) and np.all(xi < hi + 1e-12)


def test_box_mask_wraps_the_periodic_axis():
    x, y, z = _axes(n=(16, 32, 16), dx=0.125)  # y period 4
    hinge = np.array([1.0, 0.25, 1.0])
    m = box_mask(x, y, z, np.eye(3), hinge, lo=(-0.5, -0.5, -0.5), hi=(0.5, 0.5, 0.5), period_y=4.0)
    cols = np.flatnonzero(m.any(axis=(0, 2)))
    assert set(cols) == set(np.flatnonzero((y < 0.75) | (y >= 3.75)))
    no_wrap = box_mask(x, y, z, np.eye(3), hinge, lo=(-0.5, -0.5, -0.5), hi=(0.5, 0.5, 0.5))
    assert no_wrap.sum() < m.sum()


def _random_case(seed=0, n=14, ncell=37, ncomp=3):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, ncell * ncomp)).astype(np.float32)
    masks = rng.random((n, ncell)) < 0.6
    scale = rng.uniform(0.5, 2.0, n)
    return a, masks, scale


def test_masked_gram_matches_dense_computation():
    a, masks, scale = _random_case()
    am = a.astype(np.float64) * scale[:, None] * np.repeat(masks, 3, axis=1)
    assert np.allclose(masked_gram(a, masks, scale=scale, block_cells=5), am @ am.T)


def test_restricted_residuals_match_in_memory_pod():
    a, masks, scale = _random_case(seed=3, n=16)
    train, test = np.arange(0, 11), np.arange(11, 16)
    x = a.astype(np.float64) * scale[:, None]
    p_mem = pod.fit(x[train])
    g = x @ x.T
    p = pod.fit_gram(g[np.ix_(train, train)])
    z_test = pod.encode_gram(p, g[np.ix_(test, train)])
    ranks = (1, 3, 6)
    out = restricted_residuals(a, masks, train, test, p, z_test, ranks, scale=scale, block_cells=7)
    m3 = np.repeat(masks[test], 3, axis=1)
    xc = x[test] - p_mem.mean
    assert np.allclose(out["centred"], (xc**2 * m3).sum(axis=1))
    assert np.allclose(out["total"], (x[test] ** 2 * m3).sum(axis=1))
    for j, r in enumerate(ranks):
        res = xc - (xc @ p_mem.modes[:r].T) @ p_mem.modes[:r]
        assert np.allclose(out["residual"][:, j], (res**2 * m3).sum(axis=1))


def test_restricted_residuals_with_full_mask_reproduce_the_gram_error():
    a, _, scale = _random_case(seed=5, n=16)
    masks = np.ones((16, a.shape[1] // 3), dtype=bool)
    train, test = np.arange(0, 11), np.arange(11, 16)
    x = a.astype(np.float64) * scale[:, None]
    g = x @ x.T
    p = pod.fit_gram(g[np.ix_(train, train)])
    g_ht = g[np.ix_(test, train)]
    out = restricted_residuals(a, masks, train, test, p, pod.encode_gram(p, g_ht), (4,), scale=scale, block_cells=7)
    err = np.sqrt(out["residual"][:, 0].sum() / out["centred"].sum())
    assert np.isclose(err, pod.recon_error_gram(p, g_ht, np.diag(g)[test], 4))


def test_half_cell_smoothed_equals_trilinear_at_half_cell_offsets():
    from experiments.field.matched import HalfCellSmoothed
    from experiments.field.wingframe import trilinear

    shape, dx = (6, 8, 5, 3), 0.5  # y period = 8 * 0.5 = 4
    rng = np.random.default_rng(7)
    a = rng.normal(size=(4, int(np.prod(shape)))).astype(np.float32)
    view = HalfCellSmoothed(a, shape)
    assert view.shape == a.shape
    axes = [dx / 2 + dx * np.arange(n) for n in shape[:3]]
    pts = np.stack(np.meshgrid(*[ax + dx / 2 for ax in axes], indexing="ij"), axis=-1).reshape(-1, 3)
    layer = shape[1] * shape[2] * shape[3]
    for i in range(4):
        expect = trilinear(a[i].reshape(shape).astype(float), [dx / 2] * 3, dx, pts, periodic_len=(None, 4.0, None))
        got = np.concatenate([view[:, lo : lo + 2 * layer][i] for lo in range(0, a.shape[1], 2 * layer)])
        assert np.allclose(got.reshape(-1, 3), expect, atol=1e-6)


def test_half_cell_smoothed_rejects_ranges_that_split_an_x_layer():
    import pytest

    from experiments.field.matched import HalfCellSmoothed

    view = HalfCellSmoothed(np.zeros((2, 6 * 8 * 5 * 3), dtype=np.float32), (6, 8, 5, 3))
    with pytest.raises(ValueError):
        view[:, 0:7]
