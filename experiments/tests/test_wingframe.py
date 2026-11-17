import numpy as np

from experiments.field.wingframe import trilinear, wing_frame_sample
from mosquito_cfd.benchmarks.wing_kinematics import rotation_matrix


def _grid(n=(12, 10, 8), spacing=0.25, origin=(0.125, 0.125, 0.125)):
    axes = [origin[i] + spacing * np.arange(n[i]) for i in range(3)]
    g = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
    return axes, g


def test_trilinear_is_exact_for_linear_fields():
    axes, g = _grid()
    field = np.stack([2 * g[..., 0] - g[..., 1] + 0.5 * g[..., 2], g[..., 1]], axis=-1)
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.uniform(a[0], a[-1], 50) for a in axes])
    out = trilinear(field, [a[0] for a in axes], 0.25, pts)
    assert np.allclose(out[:, 0], 2 * pts[:, 0] - pts[:, 1] + 0.5 * pts[:, 2])
    assert np.allclose(out[:, 1], pts[:, 1])


def test_trilinear_returns_node_values_at_nodes():
    axes, g = _grid()
    field = np.random.default_rng(1).normal(size=g.shape[:3] + (1,))
    pts = np.array([[axes[0][3], axes[1][4], axes[2][5]]])
    assert np.allclose(trilinear(field, [a[0] for a in axes], 0.25, pts), field[3, 4, 5])


def test_trilinear_wraps_periodic_axis():
    axes, g = _grid(n=(8, 8, 8), spacing=0.5, origin=(0.25, 0.25, 0.25))  # y cell centres span a period of 4
    field = np.sin(2 * np.pi * g[..., 1:2] / 4.0)
    inside = trilinear(field, [0.25] * 3, 0.5, np.array([[1.0, 3.6, 1.0]]), periodic_len=(None, 4.0, None))
    wrapped = trilinear(field, [0.25] * 3, 0.5, np.array([[1.0, -0.4, 1.0]]), periodic_len=(None, 4.0, None))
    assert np.allclose(inside, wrapped)


def test_wing_frame_identity_rotation_samples_lab_field():
    axes, g = _grid()
    field = np.stack([g[..., 0], g[..., 1], g[..., 2]], axis=-1)
    hinge = np.array([1.0, 1.0, 1.0])
    xi = np.array([[0.3, 0.2, 0.1], [0.0, 0.5, -0.2]])
    out = wing_frame_sample(field, [a[0] for a in axes], 0.25, np.eye(3), hinge, xi)
    assert np.allclose(out, hinge + xi)


def test_wing_frame_rotates_vectors_into_body_axes():
    axes, g = _grid()
    field = np.zeros(g.shape[:3] + (3,))
    field[..., 0] = 1.0  # uniform lab velocity along x
    r = rotation_matrix(np.deg2rad(30.0), np.deg2rad(20.0))
    out = wing_frame_sample(field, [a[0] for a in axes], 0.25, r, np.array([1.5, 1.2, 1.0]), np.array([[0.1, 0.2, 0.0]]))
    assert np.allclose(out[0], r.T @ np.array([1.0, 0.0, 0.0]))
