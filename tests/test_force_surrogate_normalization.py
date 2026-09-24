"""Tests for force_surrogate.normalization (TDD red phase).

van Veen convention (standardize-force-normalization): F_ref = 0.5*rho*omega^2*S_yy,
parameterized on the radius of gyration r_gyr (= R_GYRATION), NOT the tip arm. The
validated point now reproduces f_ref ~= 200.27 (was 624.79 under the old peak-tip
convention). See openspec/changes/standardize-force-normalization.
"""

import numpy as np
import pytest

from mosquito_cfd.benchmarks.van_veen_model import compute_wing_area_moments
from mosquito_cfd.force_surrogate import (
    MomentCoefficients,
    compute_force_coefficients,
    compute_force_reference,
    compute_moment_coefficient,
    compute_moment_reference,
    shift_moment_reference,
)
from mosquito_cfd.force_surrogate.constants import (
    CHORD,
    R_GYRATION,
    R_TIP,
    RHO,
    SPAN,
    VALIDATED_F_STAR,
    VALIDATED_PHI_AMP_DEG,
    VALIDATED_PITCH_AMP_DEG,
)

_VERTEX_FILE = "examples/flapping_wing/wing.vertex"  # committed geometry; 908 markers


def test_radius_of_gyration_traced_from_wing_vertex():
    """R_GYRATION is the wing's radius of gyration, traced to the committed markers.

    Spec scenario: Radius of gyration is traced to the committed wing geometry. The
    normalization arm is sqrt(mean(r^2)) (the van Veen S_yy radius), NOT a magic
    constant. NOTE: R_TIP is used *inside* the hinge-offset formula and must survive a
    rename sweep.
    """
    verts = np.loadtxt(_VERTEX_FILE, skiprows=1)  # cols x(chord), y, z
    # Span is the widest-extent axis: T2a re-orients it to y (col 1); the legacy geometry used
    # z (col 2). Detecting it keeps r_gyr orientation-invariant (it depends on the span
    # distribution, not the axis label), so this guard survives the axis-convention refactor.
    span_col = int(np.argmax(np.ptp(verts, axis=0)))
    span = verts[:, span_col]
    r = span + (R_TIP - span.max())  # hinge-distance; tip marker -> R_TIP
    r_gyr = np.sqrt(np.mean(r**2))
    assert r_gyr == pytest.approx(R_GYRATION, rel=1e-3)
    assert R_GYRATION < R_TIP  # load is tip-weighted -> gyration arm < tip arm


def test_validated_constants_reproduce_reference_point():
    """The committed baseline constants reproduce the documented validated F_ref."""
    assert (VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, VALIDATED_PITCH_AMP_DEG) == (
        1.0,
        70.0,
        45.0,
    )
    ref = compute_force_reference(
        VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, rho=RHO
    )
    assert ref.f_ref == pytest.approx(200.27, rel=1e-3)


def test_compute_force_reference_matches_validated():
    """Reference normalization reproduces the documented validated values.

    van Veen eq 1.1: F_ref = 0.5*rho*omega^2*S_yy with S_yy = r_gyr^2 * area.
    """
    ref = compute_force_reference(
        f_star=1.0,
        phi_amp_deg=70.0,
        r_gyr=R_GYRATION,
        span=3.0,
        chord=1.0,
        rho=1.0,
    )
    assert ref.u_ref == pytest.approx(13.04, rel=1e-3)
    assert ref.q_ref == pytest.approx(85.0, rel=1e-3)
    assert ref.area == pytest.approx(2.3562, rel=1e-3)
    assert ref.f_ref == pytest.approx(200.27, rel=1e-3)
    # f_ref == 0.5*rho*omega_peak^2 * S_yy, S_yy from the single-source moment helper (CC-V4).
    omega_peak = 2.0 * np.pi * 1.0 * np.radians(70.0)
    s_yy = compute_wing_area_moments().s_yy
    assert ref.f_ref == pytest.approx(0.5 * 1.0 * omega_peak**2 * s_yy, rel=1e-9)
    assert s_yy == pytest.approx(6.797, rel=1e-3)


def test_compute_force_reference_parameterized():
    """F_ref is a pure function of inputs, not hardcoded."""
    base = compute_force_reference(1.0, 70.0, R_GYRATION, 3.0, 1.0)
    smaller = compute_force_reference(1.0, 35.0, R_GYRATION, 3.0, 1.0)
    assert smaller.u_ref < base.u_ref
    assert smaller.f_ref < base.f_ref
    doubled = compute_force_reference(2.0, 70.0, R_GYRATION, 3.0, 1.0)
    assert doubled.u_ref == pytest.approx(2 * base.u_ref, rel=1e-12)


def test_compute_force_coefficients_array_and_scalar():
    """Coefficients are F / F_ref element-wise, preserving shape."""
    fx = np.array([50.0, -30.0])
    fy = np.array([0.0, 20.0])
    fz = np.array([10.0, -40.0])
    cc = compute_force_coefficients(fx, fy, fz, 100.0)
    np.testing.assert_allclose(cc.cf_x, [0.5, -0.3])
    np.testing.assert_allclose(cc.cf_y, [0.0, 0.2])
    np.testing.assert_allclose(cc.cf_z, [0.1, -0.4])
    assert cc.cf_x.shape == fx.shape
    scalar = compute_force_coefficients(50.0, 0.0, 10.0, 100.0)
    assert float(scalar.cf_x) == pytest.approx(0.5)


def test_compute_force_coefficients_nonpositive_reference_raises():
    """A zero or negative reference is rejected (avoids div-by-zero / sign flip)."""
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, 0.0)
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, -100.0)


def test_compute_force_coefficients_mismatched_shapes_raise():
    """fx/fy/fz of differing shape raise rather than silently misalign."""
    with pytest.raises(ValueError):
        compute_force_coefficients([1.0, 2.0, 3.0], [1.0, 2.0], [1.0], 100.0)


def test_compute_force_coefficients_empty_and_nan():
    """Empty input -> empty output; NaN force -> NaN coefficient (no crash)."""
    empty = compute_force_coefficients(np.array([]), np.array([]), np.array([]), 100.0)
    assert empty.cf_x.shape == (0,)
    assert empty.cf_x.size == 0
    nan_cc = compute_force_coefficients(
        np.array([np.nan, 50.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        100.0,
    )
    assert np.isnan(nan_cc.cf_x[0])
    assert nan_cc.cf_x[1] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Moment normalization (PR4) — spec: "Single-source moment normalization"
# ---------------------------------------------------------------------------


def test_compute_moment_reference_at_validated_point():
    """M_ref = q_ref*area*chord reproduces the validated value (rtol=1e-3).

    Spec scenario: Moment reference at the validated point.
    """
    ref = compute_moment_reference(
        f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=3.0, chord=1.0, rho=1.0
    )
    assert ref.m_ref == pytest.approx(200.27, rel=1e-3)
    assert ref.length == 1.0


def test_compute_moment_reference_scales_with_chord_and_reuses_force_ref():
    """m_ref scales as chord**2 and equals f_ref*chord (single-source reuse).

    Spec scenario: Moment reference scales with the chord length scale and reuses
    the force reference. Note chord enters m_ref TWICE -- once via area
    (S = pi/4*span*chord) and once via the explicit length scale L = chord -- so
    m_ref scales quadratically with chord. The robust single-source check is the
    equality m_ref == compute_force_reference(same args).f_ref * chord at a NON-unit
    chord (trivially true at chord=1.0): a divergent re-implementation of q_ref/area
    inside compute_moment_reference would break it (CC-3).
    """
    one = compute_moment_reference(1.0, 70.0, R_GYRATION, 3.0, 1.0)
    two = compute_moment_reference(1.0, 70.0, R_GYRATION, 3.0, 2.0)
    # chord enters via area AND via L -> quadratic, so 2x chord -> 4x m_ref.
    assert two.m_ref == pytest.approx(4.0 * one.m_ref, rel=1e-12)
    force_ref = compute_force_reference(1.0, 70.0, R_GYRATION, 3.0, 2.0)
    assert two.m_ref == pytest.approx(force_ref.f_ref * 2.0, rel=1e-12)


def test_compute_moment_coefficient_array_and_scalar():
    """Coefficients are M / M_ref element-wise, preserving shape.

    Spec scenario: Moment coefficients. Uses the fixture's round moments under
    M_ref=100 so the decimals are exact.
    """
    mx = np.array([20.0, -40.0])
    my = np.array([-60.0, 10.0])
    mz = np.array([80.0, 30.0])
    cc = compute_moment_coefficient(mx, my, mz, 100.0)
    np.testing.assert_allclose(cc.cf_mx, [0.2, -0.4])
    np.testing.assert_allclose(cc.cf_my, [-0.6, 0.1])
    np.testing.assert_allclose(cc.cf_mz, [0.8, 0.3])
    assert cc.cf_mx.shape == mx.shape
    scalar = compute_moment_coefficient(20.0, -60.0, 80.0, 100.0)
    assert float(scalar.cf_mx) == pytest.approx(0.2)


def test_compute_moment_coefficient_nonpositive_reference_raises():
    """A zero or negative M_ref is rejected.

    Spec scenario: Non-positive moment reference rejected.
    """
    with pytest.raises(ValueError):
        compute_moment_coefficient(1.0, 2.0, 3.0, 0.0)
    with pytest.raises(ValueError):
        compute_moment_coefficient(1.0, 2.0, 3.0, -100.0)


def test_compute_moment_coefficient_mismatched_shapes_raise():
    """mx/my/mz of differing shape raise rather than silently misalign.

    Spec scenario: Mismatched moment shapes rejected.
    """
    with pytest.raises(ValueError):
        compute_moment_coefficient([1.0, 2.0, 3.0], [1.0, 2.0], [1.0], 100.0)


def test_compute_moment_coefficient_empty_and_nan():
    """Empty -> empty; NaN moment -> NaN coefficient (no crash).

    Spec scenario: Empty and NaN moments.
    """
    empty = compute_moment_coefficient(np.array([]), np.array([]), np.array([]), 100.0)
    assert empty.cf_mx.shape == (0,)
    nan_cc = compute_moment_coefficient(
        np.array([np.nan, 20.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        100.0,
    )
    assert np.isnan(nan_cc.cf_mx[0])
    assert nan_cc.cf_mx[1] == pytest.approx(0.2)


# --- Parallel-axis moment reference shift (fix-moment-reference-hinge) ---------------


def test_shift_moment_reference_known_answer():
    """Hand-computed ``M + d x F``, with ``d x F`` nonzero in all three components.

    Pins both the cross-product ORDER and the sign convention: the reversed product
    ``F x d`` negates every component, so this case distinguishes them.

    ``F`` is chosen so ``d x F`` has three **distinct** components. With the obvious
    ``F = (4,5,6)`` the product is ``(-3, 6, -3)``, whose x and z are equal -- an x/z
    transposition would then pass this test and be caught only elsewhere. Mutation
    testing found that gap; do not "simplify" F back.

    All values are small dyadic integers, so the arithmetic is exact -- assert with
    ``==`` rather than a tolerance, which is strictly stronger and costs nothing.

    Spec scenario: Known-answer parallel-axis shift.
    """
    # d x F = (2*7-3*5, 3*4-1*7, 1*5-2*4) = (-1, 5, -3)  -- all distinct
    mx, my, mz = shift_moment_reference(
        10.0, 20.0, 30.0, 4.0, 5.0, 7.0, offset=(1.0, 2.0, 3.0)
    )
    assert float(mx) == 9.0
    assert float(my) == 25.0
    assert float(mz) == 27.0


def test_shift_moment_reference_spanwise_leaves_my_equal():
    """A purely spanwise offset leaves ``M_y`` equal; ``M_x``/``M_z`` move.

    The ``M_y`` invariance does **not** pin the cross-product order -- ``d x F`` and
    ``F x d`` both give exactly zero in y. The order is pinned by the ``M_x``/``M_z``
    clause below and by the known-answer case.

    Spec scenario: A spanwise shift leaves the M_y component invariant.
    """
    a = 1.5
    fx = np.array([2.0, -3.0, 7.5])
    fy = np.array([0.5, 0.25, -1.0])
    fz = np.array([-4.0, 6.0, 1.25])
    m = np.array([11.0, -2.0, 0.5])

    sx, sy, sz = shift_moment_reference(m, m, m, fx, fy, fz, offset=(0.0, a, 0.0))

    # ``==``, not bitwise: -0.0 + 0.0 compares equal to +0.0 but differs in bits.
    assert np.all(sy == m)
    np.testing.assert_allclose(sx, m + a * fz, rtol=1e-15)
    np.testing.assert_allclose(sz, m - a * fx, rtol=1e-15)


def test_shift_moment_reference_nonfinite_fx_or_fz_breaks_my_invariance():
    """A non-finite ``Fx``/``Fz`` contaminates ``M_y``, because ``0.0 * NaN = NaN``.

    The shift must NOT special-case the y component to preserve the invariance.

    Spec scenario: A non-finite Fx or Fz breaks the M_y invariance.
    """
    # np.errstate: 0.0 * inf raises numpy's `invalid` flag. The NaN case does not --
    # only the inf case needs suppressing, but both calls are wrapped for symmetry.
    with np.errstate(invalid="ignore"):
        _, sy_nan, _ = shift_moment_reference(
            1.0, 1.0, 1.0, np.nan, 0.0, 0.0, offset=(0.0, 1.5, 0.0)
        )
        _, sy_inf, _ = shift_moment_reference(
            1.0, 1.0, 1.0, 0.0, 0.0, np.inf, offset=(0.0, 1.5, 0.0)
        )
    assert np.isnan(sy_nan)
    assert np.isnan(sy_inf)


def test_shift_moment_reference_nonfinite_fy_leaves_my_invariant():
    """A non-finite ``Fy`` does NOT break the ``M_y`` invariance.

    Only ``Fx`` and ``Fz`` enter ``cross_y = d_z*F_x - d_x*F_z``; ``Fy`` never does.
    So the invariance is conditional on those two specifically, not on "finite forces"
    generally -- and no single non-finite component contaminates all three outputs.

    Spec scenario: A non-finite Fx or Fz breaks the M_y invariance.
    """
    d = (0.0, 1.5, 0.0)
    with np.errstate(invalid="ignore"):
        sx, sy, sz = shift_moment_reference(7.0, 7.0, 7.0, 2.0, np.inf, 3.0, offset=d)
    assert float(sy) == 7.0  # exactly invariant despite a non-finite force
    assert np.isnan(sx) and np.isnan(sz)  # the other two are contaminated

    # Each non-finite force component contaminates exactly two outputs, never three.
    for force, expect_finite in [
        ((np.nan, 2.0, 3.0), 0),  # Fx  -> Mx survives
        ((2.0, np.nan, 3.0), 1),  # Fy  -> My survives
        ((2.0, 3.0, np.nan), 2),  # Fz  -> Mz survives
    ]:
        with np.errstate(invalid="ignore"):
            out = shift_moment_reference(1.0, 1.0, 1.0, *force, offset=d)
        finite = [i for i, v in enumerate(out) if np.isfinite(v)]
        assert finite == [expect_finite], f"{force} -> finite at {finite}"


def test_shift_moment_reference_nonfinite_moments_propagate_unmasked():
    """A non-finite moment passes through; the helper never repairs its inputs.

    Guards against a ``nan_to_num`` creeping in: with finite forces the cross terms are
    finite, so only the moment's own corruption can reach the output.

    Spec scenario: Non-finite moments propagate unmasked.
    """
    sx, sy, sz = shift_moment_reference(
        np.nan, np.inf, 1.0, 2.0, 3.0, 4.0, offset=(0.0, 1.5, 0.0)
    )
    assert np.isnan(sx)
    assert np.isinf(sy)
    assert np.isfinite(sz)

    m = np.array([np.nan, 1.0])
    f = np.array([2.0, 2.0])
    ax, _, _ = shift_moment_reference(m, m, m, f, f, f, offset=(0.0, 1.5, 0.0))
    assert np.isnan(ax[0]) and np.isfinite(ax[1])


def test_shift_moment_reference_zero_offset_is_computed_not_short_circuited():
    """A zero displacement is still evaluated, so a non-finite force propagates.

    Guards against an ``if offset == 0: return inputs`` fast path, which would make the
    zero-offset fixture path behave differently from every other path.

    Spec scenario: Degenerate shift inputs.
    """
    with np.errstate(invalid="ignore"):
        sx, sy, sz = shift_moment_reference(
            1.0, 1.0, 1.0, np.nan, 0.0, np.nan, offset=(0.0, 0.0, 0.0)
        )
    assert np.isnan(sx) and np.isnan(sy) and np.isnan(sz)


def test_shift_moment_reference_zero_offset_finite_compares_equal():
    """A zero displacement leaves all-finite inputs comparing equal.

    Spec scenario: Degenerate shift inputs.
    """
    m = np.array([1.0, -2.5, 0.0])
    f = np.array([3.0, 4.0, 5.0])
    sx, sy, sz = shift_moment_reference(m, m, m, f, f, f, offset=(0.0, 0.0, 0.0))
    assert np.all(sx == m) and np.all(sy == m) and np.all(sz == m)


def test_shift_moment_reference_empty_and_mismatched_shapes():
    """Empty -> empty without error; mismatched M/F shapes raise ``ValueError``.

    Covers three mismatch topologies, not just the easy one: across the two triples,
    **within** the moments, and **within** the forces. The intra-group cases are the
    actual broadcasting hazard -- a ragged ``my`` against ``mx`` is what would pair a
    force with the wrong moment row.

    Spec scenario: Degenerate shift inputs.
    """
    e = np.array([])
    sx, sy, sz = shift_moment_reference(e, e, e, e, e, e, offset=(0.0, 1.5, 0.0))
    assert sx.shape == (0,) and sy.shape == (0,) and sz.shape == (0,)

    two = np.array([1.0, 2.0])
    one = np.array([1.0])
    mismatches = [
        # (mx, my, mz, fx, fy, fz) -- across groups, within moments, within forces
        (two, two, two, one, one, one),
        (two, one, two, two, two, two),
        (two, two, two, two, one, two),
    ]
    for args in mismatches:
        with pytest.raises(ValueError):
            shift_moment_reference(*args, offset=(0.0, 1.5, 0.0))


def test_shift_moment_reference_rejects_malformed_offset():
    """An offset that is not exactly three finite components is rejected.

    A NaN offset would silently NaN every moment; a wrong-shaped offset is a caller bug.
    The ``(3,1)`` and ``(1,3)`` cases pin that the guard is on **shape**, not element
    count -- a ``d.size == 3`` check would accept both and then broadcast or IndexError.

    Spec scenario: A malformed offset is rejected.
    """
    bad_offsets = [
        (0.0, 1.5),  # too few
        (0.0, 1.5, 0.0, 0.0),  # too many
        0.0,  # scalar
        np.array([[0.0], [1.5], [0.0]]),  # (3,1) -- right size, wrong shape
        np.array([[0.0, 1.5, 0.0]]),  # (1,3) -- right size, wrong shape
        (0.0, np.nan, 0.0),  # non-finite
        (0.0, np.inf, 0.0),
    ]
    for bad in bad_offsets:
        with pytest.raises(ValueError):
            shift_moment_reference(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, offset=bad)


def test_moment_coefficients_docstring_names_the_hinge():
    """``MomentCoefficients`` documents the reference point, not "the body center".

    NOTE on assertion choice: a bare ``"lab" in doc`` would be **unfailable** -- the
    pre-change docstring already said "carried in the lab frame". The discriminating
    claim this change adds is the *disclaimer* that the axes are not rotated, so these
    are not van Veen wing-frame moments. Assert that instead.

    Spec scenario: Reference point is named, not implied.
    """
    doc = MomentCoefficients.__doc__ or ""
    low = doc.lower()
    assert "hinge" in low
    assert "about the body center" not in low
    assert "docs/coordinate-convention.md" in doc
    # The substantive new claim: origin moves, axes do not.
    assert "wing frame" in low or "wing-frame" in low
    assert "r(t)" in low


def test_moment_coefficients_docstring_flags_the_shift_as_not_yet_applied():
    """The docstring must not describe the hinge reference as current behaviour.

    Until extraction applies the parallel-axis shift, ``dataset.py`` still emits
    particle-origin coefficients and both committed corpora satisfy
    ``CF_mx == Mx / m_ref``. A docstring asserting the hinge reference in the present
    tense would be false for every value the repo has produced -- which is the exact
    defect (docs ahead of the pipeline) that issue #108 exists to correct.

    Remove this test in the increment that wires the shift into extraction.

    Spec scenario: Documentation does not assert a reference point the pipeline does
    not yet produce.
    """
    doc = MomentCoefficients.__doc__ or ""
    low = doc.lower()
    assert "not yet applied" in low, (
        "the pending-status marker is missing; while the extractor still emits "
        "particle-origin coefficients the docstring must say so"
    )
