"""van Veen (2022) quasi-steady flapping-wing force model — pure, analysis-only.

Implements the three-component quasi-steady force model of van Veen, van Leeuwen,
van Oudheusden & Muijres (2022), "The unsteady aerodynamics of insect wings with
rotational stroke accelerations, a systematic numerical study," *J. Fluid Mech.* **936**,
A3, DOI 10.1017/jfm.2022.31 (CC BY). Their master decomposition (eq 2.7) is

    F_total = F_transl + F_AM + F_WE      (translational + added-mass + Wagner)

The paper's *"rotational"* denotes rotational **stroke acceleration** (the ``omega_dot``-
dependent added-mass and Wagner terms); there is **no** Sane-Dickinson rotational-circulation
term, **no** Bomphrey rotational-drag term and **no** pitch-rotation term (section 2.8: "we
did not include a (wing-pitch-rate-related) rotational-lift mechanisms in our model"). Each
component returns ``(F_x tangential, F_z normal)`` as a function of ``(alpha, omega,
omega_dot)`` and the wing area-moments.

Input contract (this project's, not a statement of how the paper treats a reversing wing):
``alpha`` is the **angle of attack** in radians within ``[0, pi/2]``, ``omega >= 0`` is the
stroke **speed**, and ``omega_dot`` is the stroke acceleration **along the motion** (positive
while the wing speeds up). The paper fits single strokes at 9-90 degrees with ``omega > 0``
(section 2.5) and says "there is no difference between the pitch angle and the angle of attack"
in those simulations (section 2.4). A signed geometric pitch is not a valid input and raises.
The returned ``F_x`` and ``F_z`` oppose the wing's chord-wise and wing-normal motion; mapping
them onto the wing body axes on both half-strokes is done by :func:`model_inputs`.

Component forms (eqs 3.9-3.15 / 4.1-4.7):
  - translational:  F_z = 0.5*rho*omega**2*S_yy * C_FZA_TRANSL*sin(alpha)
                    F_x = 0.5*rho*omega**2*S_yy * (A*alpha_deg**2 + B*alpha_deg + C)
  - added-mass:     F_z = rho*omega_dot*S_cy * C_FZA_AM*sin(alpha)
                    F_x = rho*omega_dot*S_cy * C_FXA_AM*cos(alpha)
  - Wagner:         F_z = 0.5*rho*omega*sign(omega_dot)*sqrt(|omega_dot|)*S_WE * C_FZA_WE*sin(alpha)
                    F_x = 0

Both added-mass components scale on the **chord-based** ``S_cy`` (the paper's *fitted revised*
model rebased the tangential added mass on chord and made it viscous — its stated novelty),
NOT the analytic thickness-based ``S_tau_y``. Do not "correct" this back to ``S_tau_y``.

Coefficients are pinned module constants with their published 95% CIs, guarded by
:func:`assert_coefficients_not_loosened` (CC-V2). See project memory ``van-veen-force-model-t4``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, R_TIP, RHO, SPAN

# --- Fitted coefficients (van Veen 2022, eqs 3.9-3.15 / 4.1-4.7) -----------------------------
# Each is a pinned constant with its published 95% CI. assert_coefficients_not_loosened() fails
# if any value or CI is widened (CC-V2 — the model cannot be silently retuned to pass).
C_FZA_TRANSL = 3.13  # translational normal:  C_Fz,transl(alpha) = C_FZA_TRANSL*sin(alpha)  (eq 3.9)
C_FZA_TRANSL_CI = (3.10, 3.15)
# translational tangential (viscous): C_Fx,transl = A*alpha_deg**2 + B*alpha_deg + C  (eq 3.12),
# with the angle of attack in DEGREES. The paper prints no unit. Degrees is the reading that
# reproduces its own statements (section 3.1.1: above 36 deg the tangential-to-normal ratio is
# -0.01 +/- 0.01; section 3.1.2: the coefficient decreases with angle of attack; fig 4b), and a
# least-squares refit of the paper's published fruit-fly dataset returns these coefficients in
# degrees (tests/test_van_veen_dataset.py). Section 4.4 (eq 4.7) restates the polynomial with a
# different coefficient set, (1.0e-4, -1.4e-2, 0.43); the values pinned here are section 3.1.2's,
# the fit eq 3.12 belongs to. The choice affects only the tangential output. The polynomial is
# fitted on 9-90 deg and is slightly negative for roughly 58-83 deg.
TRANSL_TANGENTIAL_POLY = (8.5e-5, -1.2e-2, 0.41)  # (A, B, C)
TRANSL_TANGENTIAL_POLY_CI = ((6.8e-5, 10.2e-5), (-1.4e-2, -1.0e-2), (0.37, 0.44))
C_FZA_AM = 0.96  # added-mass normal:  C_Fz,AM(alpha) = C_FZA_AM*sin(alpha)  (eq 3.10; fitted, vs analytic pi/4)
C_FZA_AM_CI = (0.95, 0.97)
C_FXA_AM = (
    0.104  # added-mass tangential:  C_Fx,AM(alpha) = C_FXA_AM*cos(alpha)  (eq 3.13)
)
C_FXA_AM_CI = (0.101, 0.107)
C_FZA_WE = (
    -1.02
)  # Wagner normal:  C_Fz,WE(alpha) = C_FZA_WE*sin(alpha)  (eq 3.11); NEGATIVE
C_FZA_WE_CI = (-1.06, -0.98)

# Erratum provenance (JFM 956 E1, 2023): a "publisher-introduced" (production) correction — the
# malformed data-availability DOI printed as ``10.1017/jfm.2019`` — NOT the fitted coefficients.
# Pinned as a testable artifact so "verified before trust" is committed, not only a human step
# (design D9). If a future check shows the erratum DID change a coefficient, update the constant
# + CI above and this literal, and record the deviation in design.md D9.
ERRATUM_CHECKED = "JFM 956 E1 (2023): publisher-introduced (data-availability DOI); no coefficient change"

# Default committed wing geometry for the area-moment quadrature (908 surface markers).
_DEFAULT_VERTEX_FILE = (
    Path(__file__).resolve().parents[3] / "examples/flapping_wing/wing.vertex"
)
_SWE_NBINS = (
    30  # spanwise bins for the S_WE marker quadrature (matches the V2 figure binning)
)


def assert_coefficients_not_loosened() -> None:
    """Raise ``AssertionError`` if any pinned coefficient or its 95% CI has been widened (CC-V2).

    The model cannot be silently retuned to pass a grade. Each coefficient must equal its
    published van Veen value and each CI must be no wider than published.
    """
    assert C_FZA_TRANSL == 3.13, "C_FZA_TRANSL retuned"
    assert C_FZA_TRANSL_CI == (3.10, 3.15), "C_FZA_TRANSL_CI widened"
    assert TRANSL_TANGENTIAL_POLY == (8.5e-5, -1.2e-2, 0.41), (
        "translational polynomial retuned"
    )
    assert TRANSL_TANGENTIAL_POLY_CI == (
        (6.8e-5, 10.2e-5),
        (-1.4e-2, -1.0e-2),
        (0.37, 0.44),
    ), "translational polynomial CI widened"
    assert C_FZA_AM == 0.96, "C_FZA_AM retuned"
    assert C_FZA_AM_CI == (0.95, 0.97), "C_FZA_AM_CI widened"
    assert C_FXA_AM == 0.104, "C_FXA_AM retuned"
    assert C_FXA_AM_CI == (0.101, 0.107), "C_FXA_AM_CI widened"
    assert C_FZA_WE == -1.02, "C_FZA_WE retuned"
    assert C_FZA_WE_CI == (-1.06, -0.98), "C_FZA_WE_CI widened"


def _finite(*arrays: NDArray[np.floating]) -> None:
    """Raise ``ValueError`` on any non-finite input (no silent NaN coefficient)."""
    for a in arrays:
        if not np.isfinite(np.asarray(a, dtype=float)).all():
            raise ValueError(
                "van Veen model input contains non-finite values (NaN/inf)"
            )


def _in_domain(
    *, alpha: NDArray[np.floating], omega: NDArray[np.floating] | None = None
) -> None:
    """Raise ``ValueError`` naming the input if any element is outside the input contract.

    ``alpha`` must lie in ``[0, pi/2]`` and ``omega`` (where the component takes it) must be
    non-negative. A signed geometric pitch fails here instead of flipping the normal force.
    """
    if ((alpha < 0.0) | (alpha > np.pi / 2)).any():
        raise ValueError(
            "alpha must be an angle of attack in [0, pi/2] rad; got values in "
            f"[{float(np.min(alpha))!r}, {float(np.max(alpha))!r}] (pi/2 is {np.pi / 2!r}). A "
            "signed geometric pitch is not a valid input: derive the inputs with model_inputs(). "
            "A float32 pi/2 is above the float64 one; compute the angle in float64."
        )
    if omega is not None and (omega < 0.0).any():
        raise ValueError(
            "omega must be a non-negative stroke speed; got a minimum of "
            f"{float(np.min(omega)):.6g}. Derive the inputs with model_inputs()."
        )


@dataclass(frozen=True)
class ModelInputs:
    """Inputs for the model components and the body-frame directions their forces act along.

    ``alpha`` (angle of attack, rad, in ``[0, pi/2]``), ``omega`` (stroke speed, >= 0) and
    ``omega_dot`` (acceleration along the motion) are what the component functions take.
    ``chord_dir`` and ``normal_dir`` are -1, 0 or +1: multiply a component's ``F_x`` by
    ``chord_dir`` and its ``F_z`` by ``normal_dir`` to get the force along the body x (chord) and
    z (normal) axes.
    """

    alpha: NDArray[np.float64]
    omega: NDArray[np.float64]
    omega_dot: NDArray[np.float64]
    chord_dir: NDArray[np.float64]
    normal_dir: NDArray[np.float64]


# A velocity component smaller than this (in units of the span-point speed) is treated as zero,
# so pitch = pi/2, whose floating-point cosine is 6e-17, has no chord-wise motion.
_ZERO_COMPONENT = 1e-15


def model_inputs(
    pitch: NDArray[np.floating] | float,
    phi_dot: NDArray[np.floating] | float,
    phi_ddot: NDArray[np.floating] | float,
) -> ModelInputs:
    """Model inputs and force directions from the wing's pitch, stroke rate and acceleration.

    Under ``R = Rz(phi)*Ry(pitch)`` with zero deviation, a point on the span axis at hinge distance
    ``r`` has body-frame velocity ``-phi_dot*r*(cos pitch, 0, sin pitch)``. The pitch rate does not
    enter, because ``Ry`` leaves the span axis fixed. With ``s = sign(phi_dot)``, or
    ``sign(phi_ddot)`` where ``phi_dot`` is exactly zero (the way the wing is about to move), and
    ``u = -s*(cos pitch, 0, sin pitch)``:

    - angle of attack ``atan2(|u_z|, |u_x|)``;
    - speed ``|phi_dot|`` and acceleration along the motion ``s*phi_ddot``;
    - chord direction ``-sign(u_x)`` and normal direction ``-sign(u_z)``: each force opposes the
      motion along its axis.

    Where a component of ``u`` is zero its direction is 0, so that force component is zero.
    Where ``phi_dot = phi_ddot = 0`` every output is zero.

    This folds any pitch into ``[0, pi/2]``, which relies on two symmetries of the wing: about its
    chord midline (either edge may lead) and about its own plane (flat, uncambered, zero thickness:
    either face may lead). The elliptic plate has both. Limits: the model has no pitch-rotation
    term, and the velocity above is for points on the span axis; off it, the pitch rate adds a
    normal velocity the model does not see. The paper's own recipe for a reversing wing is in
    supplementary text that is not published with the article; this derivation follows its
    fig 1c-e and section 3.3.

    Args:
        pitch: Geometric pitch about the span axis [rad], any sign.
        phi_dot: Stroke rate [rad/time], signed.
        phi_ddot: Stroke acceleration [rad/time**2], signed.

    Returns:
        A :class:`ModelInputs` of float arrays with the broadcast shape of the inputs.

    Raises:
        ValueError: on a non-finite input.
    """
    p, w, wd = np.broadcast_arrays(
        np.asarray(pitch, dtype=float),
        np.asarray(phi_dot, dtype=float),
        np.asarray(phi_ddot, dtype=float),
    )
    _finite(p, w, wd)
    s = np.where(w != 0.0, np.sign(w), np.sign(wd))
    cos_p, sin_p = np.cos(p), np.sin(p)
    cos_p = np.where(np.abs(cos_p) < _ZERO_COMPONENT, 0.0, cos_p)
    sin_p = np.where(np.abs(sin_p) < _ZERO_COMPONENT, 0.0, sin_p)
    u_x, u_z = -s * cos_p, -s * sin_p
    return ModelInputs(
        alpha=np.arctan2(np.abs(u_z), np.abs(u_x)),
        omega=np.abs(w),
        omega_dot=s * wd,
        # "+ 0.0" turns a negative zero into a positive one.
        chord_dir=-np.sign(u_x) + 0.0,
        normal_dir=-np.sign(u_z) + 0.0,
    )


def translational_force(
    alpha: NDArray[np.floating] | float,
    omega: NDArray[np.floating] | float,
    *,
    s_yy: float,
    rho: float = RHO,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Translational (quasi-steady circulatory) force ``(F_x, F_z)`` (eqs 3.9, 3.12).

    Like every component here, ``F_x`` and ``F_z`` oppose the wing's chord-wise and wing-normal
    motion; multiply them by :func:`model_inputs`' directions to get body-frame forces.

    ``F_z = 0.5*rho*omega**2*S_yy * C_FZA_TRANSL*sin(alpha)``;
    ``F_x = 0.5*rho*omega**2*S_yy * (A*alpha_deg**2 + B*alpha_deg + C)``, where ``alpha_deg`` is
    the angle of attack in degrees (``alpha`` itself is passed in radians).

    Raises:
        ValueError: on a non-finite input, an ``alpha`` outside ``[0, pi/2]`` or a negative
            ``omega`` (see the module docstring's input contract).
    """
    a = np.asarray(alpha, dtype=float)
    w = np.asarray(omega, dtype=float)
    _finite(a, w)
    _in_domain(alpha=a, omega=w)
    q = 0.5 * rho * w**2 * s_yy
    A, B, C = TRANSL_TANGENTIAL_POLY
    a_deg = np.degrees(a)
    f_z = q * C_FZA_TRANSL * np.sin(a)
    f_x = q * (A * a_deg**2 + B * a_deg + C)
    return f_x, f_z


def added_mass_force_component(
    alpha: NDArray[np.floating] | float,
    omega_dot: NDArray[np.floating] | float,
    *,
    s_cy: float,
    rho: float = RHO,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Added-mass force ``(F_x, F_z)`` (eqs 3.10, 3.13; both scale on chord ``S_cy``).

    Signed against the motion; see :func:`model_inputs` for the body-frame directions.

    ``F_z = rho*omega_dot*S_cy * C_FZA_AM*sin(alpha)``;
    ``F_x = rho*omega_dot*S_cy * C_FXA_AM*cos(alpha)``. Proportional to the stroke acceleration
    along the motion, ``omega_dot`` (positive while the wing speeds up).

    Raises:
        ValueError: on a non-finite input or an ``alpha`` outside ``[0, pi/2]``.
    """
    a = np.asarray(alpha, dtype=float)
    wd = np.asarray(omega_dot, dtype=float)
    _finite(a, wd)
    _in_domain(alpha=a)
    scale = rho * wd * s_cy
    f_z = scale * C_FZA_AM * np.sin(a)
    f_x = scale * C_FXA_AM * np.cos(a)
    return f_x, f_z


def wagner_force(
    alpha: NDArray[np.floating] | float,
    omega: NDArray[np.floating] | float,
    omega_dot: NDArray[np.floating] | float,
    *,
    s_we: float,
    rho: float = RHO,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Wagner-effect force ``(F_x, F_z)`` (eqs 3.11, 3.14/4.1; tangential = 0).

    Signed against the motion; see :func:`model_inputs` for the body-frame directions.

    ``F_z = 0.5*rho*omega*sign(omega_dot)*sqrt(|omega_dot|)*S_WE * C_FZA_WE*sin(alpha)``,
    ``F_x = 0``. Uses van Veen's ``sign(omega_dot)*sqrt(|omega_dot|)`` generalization (eq 3.15/4.1)
    so the term is finite and correctly signed for decelerating wings (``omega_dot < 0``); the
    negative ``C_FZA_WE`` reduces lift on an accelerating wing.

    Raises:
        ValueError: on a non-finite input, an ``alpha`` outside ``[0, pi/2]`` or a negative
            ``omega``.
    """
    a = np.asarray(alpha, dtype=float)
    w = np.asarray(omega, dtype=float)
    wd = np.asarray(omega_dot, dtype=float)
    _finite(a, w, wd)
    _in_domain(alpha=a, omega=w)
    signed_root = np.sign(wd) * np.sqrt(np.abs(wd))
    f_z = 0.5 * rho * w * signed_root * s_we * C_FZA_WE * np.sin(a)
    f_x = np.zeros_like(f_z)
    return f_x, f_z


def total_force(
    alpha: NDArray[np.floating] | float,
    omega: NDArray[np.floating] | float,
    omega_dot: NDArray[np.floating] | float,
    *,
    s_yy: float,
    s_cy: float,
    s_we: float,
    rho: float = RHO,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Total body-frame force ``F_total = F_transl + F_AM + F_WE`` (eq 2.7), ``(F_x, F_z)``."""
    tx, tz = translational_force(alpha, omega, s_yy=s_yy, rho=rho)
    ax, az = added_mass_force_component(alpha, omega_dot, s_cy=s_cy, rho=rho)
    wx, wz = wagner_force(alpha, omega, omega_dot, s_we=s_we, rho=rho)
    return tx + ax + wx, tz + az + wz


@dataclass(frozen=True)
class WingAreaMoments:
    """Wing area-moments for the van Veen model (hinge-origin convention; design D3).

    The three are on three planform bases: ``s_yy`` is ``R_GYRATION**2 * area`` (single-source
    with ``F_ref``); ``s_cy`` is the closed form of ``integral c(y)**2 * y dy`` for the nominal
    ellipse; ``s_we`` is ``integral sqrt(c(y)**3 * y**3) dy`` from a marker quadrature.
    """

    s_yy: float
    s_cy: float
    s_we: float


def profile_moments(
    c: NDArray[np.floating], y: NDArray[np.floating]
) -> tuple[float, float]:
    """``(S_cy, S_WE)`` of a chord profile ``c(y)`` by trapezoidal integration.

    ``S_cy = integral c**2 * y dy`` (van Veen eq 1.8) and
    ``S_WE = integral sqrt(max(c**3 * y**3, 0)) dy``. The radicand is clipped at zero because a
    measured profile can start a hair inboard of the hinge (the paper's mosquito profile has three
    rows with ``y < 0``).

    Args:
        c: Chord at each spanwise station.
        y: Hinge distance of each station, non-decreasing.

    Returns:
        ``(s_cy, s_we)``.

    Raises:
        ValueError: if the two are not 1-D arrays of the same length with at least two stations,
            if either holds a non-finite value, or if ``y`` decreases
            anywhere (a descending or shuffled profile would integrate to a wrong number).
    """
    c = np.asarray(c, dtype=float)
    y = np.asarray(y, dtype=float)
    if c.ndim != 1 or y.ndim != 1 or c.shape != y.shape or c.size < 2:
        raise ValueError(
            "profile_moments: c and y must be 1-D arrays of the same length with at least two "
            f"stations (got shapes {c.shape} and {y.shape})"
        )
    if not (np.isfinite(c).all() and np.isfinite(y).all()):
        raise ValueError("profile_moments: c and y must be finite")
    if (np.diff(y) < 0).any():
        raise ValueError("profile_moments: y must be non-decreasing (root to tip)")
    s_cy = float(np.trapezoid(c**2 * y, y))
    s_we = float(np.trapezoid(np.sqrt(np.clip(c**3 * y**3, 0.0, None)), y))
    return s_cy, s_we


def s_cy_closed_form(
    *, span: float = SPAN, chord: float = CHORD, r_tip: float = R_TIP
) -> float:
    """``S_cy = integral c(y)**2 * y dy`` (van Veen eq 1.8) for the nominal elliptic planform.

    With ``c(y)**2 = chord**2 * (1 - ((y - y_c)/a)**2)``, ``a = span/2`` and
    ``y_c = r_tip - span/2`` the integral is ``(2/3)*chord**2*span*(r_tip - span/2)``:
    ``chord**2*span**2/3 = 3.0`` for span 3, chord 1 and the root at the hinge.

    The paper's eq 2.11, evaluated as printed, gives ``(pi/8)*chord**2*span**2`` (3.53 here)
    because its integrand omits a factor. The paper's fig 2e and the ``Scy`` stored in its
    published dataset match ``chord**2*span**2/3``. Do not "correct" this to 3.53.

    The ellipse spans ``y`` from ``r_tip - span`` (root) to ``r_tip`` (tip), so the root is
    at or outboard of the hinge only when ``r_tip >= span``.

    Raises:
        ValueError: if ``span`` or ``chord`` is not finite and positive, or if ``r_tip`` is not
            finite or is less than ``span`` (the ellipse would extend inboard of the hinge).
    """
    if not (np.isfinite(span) and np.isfinite(chord) and span > 0 and chord > 0):
        raise ValueError(
            f"span and chord must be finite and positive (got span={span}, chord={chord})"
        )
    if not (np.isfinite(r_tip) and r_tip >= span):
        raise ValueError(
            f"r_tip={r_tip} must be finite and at least the span ({span}): the ellipse runs from "
            "r_tip - span to r_tip, so a smaller r_tip puts its root inboard of the hinge"
        )
    return (2.0 / 3.0) * chord**2 * span * (r_tip - span / 2.0)


# compute_wing_area_moments raises when the marker S_cy of the wing file differs from the nominal
# closed form by more than this fraction. The committed wing differs by 9.9 %.
_PLANFORM_MISMATCH_TOL = 0.15
# Fewer bins than this cannot describe a planform (3 bins read the committed wing 16 % low).
_MIN_NBINS = 5


def compute_wing_area_moments(
    vertex_path: str | Path = _DEFAULT_VERTEX_FILE,
    *,
    r_gyr: float = R_GYRATION,
    span: float = SPAN,
    chord: float = CHORD,
    r_tip: float = R_TIP,
    nbins: int = _SWE_NBINS,
) -> WingAreaMoments:
    """Wing area-moments under the pinned **hinge-origin** convention (design D3, review B3).

    - ``S_yy = r_gyr**2 * area`` (via the committed ``R_GYRATION``, the *same* single source
      ``compute_force_reference`` uses for ``F_ref = 200.27``; **not** a marker
      ``integral c*y**2 dy`` quadrature, which gives ~6.24 because the marker planform is smaller
      than the nominal ellipse).
    - ``S_cy = integral c(y)**2 * y dy`` (eq 1.8), the closed form for the nominal ellipse
      (:func:`s_cy_closed_form`; 3.0). A different integral from ``S_yy``.
    - ``S_WE = integral sqrt(c(y)**3 * y**3) dy``, a hinge-origin marker quadrature over the
      committed planform (``y = span_coord + (r_tip - span_coord.max())``).

    The three moments therefore do not share one planform basis (see :class:`WingAreaMoments`).

    Planform guard: the closed-form ``S_cy`` is right only for the nominal ellipse. The marker
    quadrature of ``S_cy`` is computed from the same wing file, and a difference of more than
    ``_PLANFORM_MISMATCH_TOL`` (15 %) from the closed form raises. This catches gross planform
    errors only (a rectangle, a chord a few per cent too small or about a tenth too large,
    the committed markers being 9.9 % low already); a mosquito-shaped wing
    of the same span differs by about 8 % and passes, and a wrong span is not seen at all,
    because the markers are placed by ``r_tip``. A zero-area planform, a bad ``r_tip`` or
    ``nbins``, a missing wing file and a too-fine ``nbins`` are reported by their own errors
    first.

    Args:
        vertex_path: Committed wing.vertex (908 surface markers; cols x=chord, y, z).
        r_gyr: Radius of gyration about the hinge (``R_GYRATION``).
        span: Wing span [chord units].
        chord: Reference chord length [chord units].
        r_tip: Hinge-to-tip arm (the tip marker maps to this hinge distance).
        nbins: Spanwise bins for the marker quadrature (matches the V2 figure binning).

    Returns:
        A :class:`WingAreaMoments` with ``s_yy``, ``s_cy``, ``s_we``.

    Raises:
        ValueError: if the planform is degenerate (zero area / zero span extent), if
            ``r_tip < span``, if ``nbins`` is not an integer of at least 5 or is too fine for the
            markers, or if the wing file's marker ``S_cy`` differs from the closed form by more
            than 15 %.
        FileNotFoundError: if the wing file does not exist.
    """
    area = np.pi / 4.0 * span * chord
    if not (np.isfinite(area) and area > 0):
        raise ValueError(
            f"degenerate planform: area={area} (span={span}, chord={chord})"
        )
    s_yy = r_gyr**2 * area
    s_cy = s_cy_closed_form(span=span, chord=chord, r_tip=r_tip)
    s_cy_marker, s_we = _marker_moment_quadrature(vertex_path, r_tip=r_tip, nbins=nbins)
    mismatch = abs(s_cy_marker - s_cy) / s_cy
    if mismatch > _PLANFORM_MISMATCH_TOL:
        raise ValueError(
            f"planform mismatch: the marker S_cy of {vertex_path} is {s_cy_marker:.4f}, but the "
            f"closed form for the nominal ellipse (span={span}, chord={chord}, r_tip={r_tip}) is "
            f"{s_cy:.4f}, a difference of {100 * mismatch:.1f} % at nbins={nbins} (limit "
            f"{100 * _PLANFORM_MISMATCH_TOL:.0f} %). The wing file is not the nominal ellipse, so "
            "the closed-form S_cy, S_yy and F_ref do not describe it."
        )
    return WingAreaMoments(s_yy=s_yy, s_cy=s_cy, s_we=s_we)


def s_cy_marker_quadrature(
    vertex_path: str | Path = _DEFAULT_VERTEX_FILE,
    *,
    r_tip: float = R_TIP,
    nbins: int = _SWE_NBINS,
) -> float:
    """Marker quadrature of ``S_cy = integral c(y)**2 * y dy``: a reported cross-check.

    It is never fed to the model. For the committed wing it is 2.70, below the closed form
    (3.0) because the marker planform is smaller than the nominal ellipse in chord and span.
    See :func:`_marker_moment_quadrature` for the estimator and its bias.
    """
    return _marker_moment_quadrature(vertex_path, r_tip=r_tip, nbins=nbins)[0]


def _marker_moment_quadrature(
    vertex_path: str | Path, *, r_tip: float = R_TIP, nbins: int = _SWE_NBINS
) -> tuple[float, float]:
    """Hinge-origin marker quadrature ``(S_cy, S_WE)`` of a wing file, from one binning.

    Bins the surface markers by hinge distance ``y`` (the span axis is the widest-extent column,
    orientation-invariant per the V2 figure), takes the chord ``c(y)`` as the x-extent within
    each bin, and integrates over the bin centres with :func:`profile_moments`.

    The estimator takes the widest chord in each bin, so on a densely sampled planform it is
    biased high at a finite bin count (about 4 % for ``S_cy`` on an ellipse at 30 bins), and the
    bias shrinks as bins are added. With too few markers per bin it collapses instead, which the
    too-fine guard below reports.
    """
    # A bool is an int, and True (1) fails the minimum like any other small count.
    is_integer = isinstance(nbins, (int, np.integer))
    if not is_integer or nbins < _MIN_NBINS:
        raise ValueError(f"nbins must be an integer >= {_MIN_NBINS} (got {nbins!r})")
    if not (np.isfinite(r_tip) and r_tip > 0):
        raise ValueError(f"r_tip={r_tip} must be finite and positive")
    if not Path(vertex_path).exists():
        raise FileNotFoundError(
            f"wing.vertex not found at {vertex_path}. The committed geometry is not shipped in the "
            "installed wheel — pass an explicit vertex_path to compute_wing_area_moments()."
        )
    verts = np.loadtxt(vertex_path, skiprows=1)  # cols x(chord), y, z
    x = verts[:, 0]
    span_col = int(np.argmax(np.ptp(verts, axis=0)))
    span_coord = verts[:, span_col]
    extent = np.ptp(span_coord)
    if not (np.isfinite(extent) and extent > 0):
        raise ValueError("degenerate planform: zero spanwise extent in wing.vertex")
    y = span_coord + (r_tip - span_coord.max())  # hinge distance; tip marker -> r_tip
    if y.min() < -1e-9:
        raise ValueError(
            f"r_tip={r_tip} is less than the markers' spanwise extent ({extent:.6g}): markers "
            "would fall inboard of the hinge"
        )
    edges = np.linspace(y.min(), y.max(), nbins + 1)
    ctr = 0.5 * (edges[:-1] + edges[1:])
    counts = np.array(
        [int(np.sum((y >= edges[i]) & (y < edges[i + 1]))) for i in range(nbins)]
    )
    # A bin with <=1 marker cannot resolve the chord (ptp needs >=2 points) -> chord=0 there,
    # which silently UNDER-estimates both moments as nbins grows past the marker density. Guard
    # it: the binning must be coarse enough to resolve every spanwise station of the planform.
    n_empty = int(np.sum(counts <= 1))
    if n_empty > 0.05 * nbins:
        raise ValueError(
            f"nbins={nbins} is too fine for {len(y)} markers: {n_empty} bin(s) hold <=1 marker "
            "and cannot resolve the chord, silently under-estimating S_cy and S_WE. Use "
            f"fewer bins (the calibrated default is {_SWE_NBINS})."
        )
    chord_y = np.array(
        [
            np.ptp(x[(y >= edges[i]) & (y < edges[i + 1])]) if counts[i] > 1 else 0.0
            for i in range(nbins)
        ]
    )
    return profile_moments(chord_y, ctr)
