"""van Veen (2022) quasi-steady flapping-wing force model — pure, analysis-only.

Implements the three-component quasi-steady force model of van Veen, van Leeuwen,
van Oudheusden & Muijres (2022), "The unsteady aerodynamics of insect wings with
rotational stroke accelerations, a systematic numerical study," *J. Fluid Mech.* **936**,
A3, DOI 10.1017/jfm.2022.31 (CC BY). Their master decomposition (eq 2.7) is

    F_total = F_transl + F_AM + F_WE      (translational + added-mass + Wagner)

The paper's *"rotational"* denotes rotational **stroke acceleration** (the ``omega_dot``-
dependent added-mass and Wagner terms); there is **no** Sane-Dickinson rotational-circulation
term and **no** Bomphrey rotational-drag term. Each component is returned in the **wing body
frame** ``(F_x chord/tangential, F_z normal)`` as a function of ``(alpha, omega, omega_dot)``
and the wing area-moments, so it is directly comparable to the CFD body-frame ``CF`` (no
rotation needed). ``alpha`` is in **radians**.

Component forms (eqs 3.9-3.15 / 4.1-4.7; alpha in radians):
  - translational:  F_z = 0.5*rho*omega**2*S_yy * C_FZA_TRANSL*sin(alpha)
                    F_x = 0.5*rho*omega**2*S_yy * (A*alpha**2 + B*alpha + C)
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

# --- Fitted coefficients (van Veen 2022, eqs 3.9-3.15 / 4.1-4.7; alpha in radians) -----------
# Each is a pinned constant with its published 95% CI. assert_coefficients_not_loosened() fails
# if any value or CI is widened (CC-V2 — the model cannot be silently retuned to pass).
C_FZA_TRANSL = 3.13  # translational normal:  C_Fz,transl(alpha) = C_FZA_TRANSL*sin(alpha)  (eq 3.9)
C_FZA_TRANSL_CI = (3.10, 3.15)
# translational tangential (viscous): C_Fx,transl(alpha) = A*alpha**2 + B*alpha + C  (eq 3.12)
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


def translational_force(
    alpha: NDArray[np.floating] | float,
    omega: NDArray[np.floating] | float,
    *,
    s_yy: float,
    rho: float = RHO,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Translational (quasi-steady circulatory) body-frame force ``(F_x, F_z)`` (eqs 3.9, 3.12).

    ``F_z = 0.5*rho*omega**2*S_yy * C_FZA_TRANSL*sin(alpha)``;
    ``F_x = 0.5*rho*omega**2*S_yy * (A*alpha**2 + B*alpha + C)``. ``alpha`` in radians.
    """
    a = np.asarray(alpha, dtype=float)
    w = np.asarray(omega, dtype=float)
    _finite(a, w)
    q = 0.5 * rho * w**2 * s_yy
    A, B, C = TRANSL_TANGENTIAL_POLY
    f_z = q * C_FZA_TRANSL * np.sin(a)
    f_x = q * (A * a**2 + B * a + C)
    return f_x, f_z


def added_mass_force_component(
    alpha: NDArray[np.floating] | float,
    omega_dot: NDArray[np.floating] | float,
    *,
    s_cy: float,
    rho: float = RHO,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Added-mass body-frame force ``(F_x, F_z)`` (eqs 3.10, 3.13; both scale on chord ``S_cy``).

    ``F_z = rho*omega_dot*S_cy * C_FZA_AM*sin(alpha)``;
    ``F_x = rho*omega_dot*S_cy * C_FXA_AM*cos(alpha)``. Proportional to the stroke angular
    acceleration ``omega_dot`` (keeps its sign; reverses at the stroke extremes).
    """
    a = np.asarray(alpha, dtype=float)
    wd = np.asarray(omega_dot, dtype=float)
    _finite(a, wd)
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
    """Wagner-effect body-frame force ``(F_x, F_z)`` (eqs 3.11, 3.14/4.1; tangential = 0).

    ``F_z = 0.5*rho*omega*sign(omega_dot)*sqrt(|omega_dot|)*S_WE * C_FZA_WE*sin(alpha)``,
    ``F_x = 0``. Uses van Veen's ``sign(omega_dot)*sqrt(|omega_dot|)`` generalization (eq 3.15/4.1)
    so the term is finite and correctly signed for decelerating wings (``omega_dot < 0``); the
    negative ``C_FZA_WE`` reduces lift on an accelerating wing.
    """
    a = np.asarray(alpha, dtype=float)
    w = np.asarray(omega, dtype=float)
    wd = np.asarray(omega_dot, dtype=float)
    _finite(a, w, wd)
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

    ``s_yy`` and ``s_cy`` are ``R_GYRATION**2 * area`` (single-source with ``F_ref``); ``s_we``
    is the new Wagner moment ``integral sqrt(c(y)**3 * y**3) dy`` from a marker quadrature.
    """

    s_yy: float
    s_cy: float
    s_we: float


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

    ``S_yy = r_gyr**2 * area`` (via the committed ``R_GYRATION``, the *same* single source
    ``compute_force_reference`` uses for ``F_ref = 200.27`` — **not** re-derived as a marker
    ``integral c*y**2 dy`` quadrature, which gives ~6.24 because the marker planform area differs
    from the analytic elliptic area by ~7%). ``S_cy == S_yy`` (identical integrand). The **new**
    ``S_WE = integral sqrt(c(y)**3 * y**3) dy`` is a hinge-origin marker quadrature over the
    committed planform (``y`` from the stroke axis: ``y = span_coord + (r_tip - span_coord.max())``).

    Args:
        vertex_path: Committed wing.vertex (908 surface markers; cols x=chord, y, z).
        r_gyr: Radius of gyration about the hinge (``R_GYRATION``).
        span: Wing span [chord units].
        chord: Reference chord length [chord units].
        r_tip: Hinge-to-tip arm (the tip marker maps to this hinge distance).
        nbins: Spanwise bins for the S_WE quadrature (matches the V2 figure binning).

    Returns:
        A :class:`WingAreaMoments` with ``s_yy``, ``s_cy`` (== ``s_yy``), ``s_we``.

    Raises:
        ValueError: if the planform is degenerate (zero area / zero span extent).
    """
    area = np.pi / 4.0 * span * chord
    if not (np.isfinite(area) and area > 0):
        raise ValueError(
            f"degenerate planform: area={area} (span={span}, chord={chord})"
        )
    s_yy = r_gyr**2 * area
    s_we = _s_we_marker_quadrature(vertex_path, r_tip=r_tip, nbins=nbins)
    return WingAreaMoments(s_yy=s_yy, s_cy=s_yy, s_we=s_we)


def _s_we_marker_quadrature(
    vertex_path: str | Path, *, r_tip: float = R_TIP, nbins: int = _SWE_NBINS
) -> float:
    """Hinge-origin marker quadrature of ``S_WE = integral sqrt(c(y)**3 * y**3) dy``.

    Bins the committed surface markers by hinge distance ``y`` (the span axis is the
    widest-extent column, orientation-invariant per the V2 figure), takes the chord ``c(y)`` as
    the x-extent within each bin, and trapezoidally integrates ``sqrt(c**3 * y**3)`` over the bin
    centres. ``y > 0`` throughout, so the ``sqrt`` is real.
    """
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
    edges = np.linspace(y.min(), y.max(), nbins + 1)
    ctr = 0.5 * (edges[:-1] + edges[1:])
    counts = np.array(
        [int(np.sum((y >= edges[i]) & (y < edges[i + 1]))) for i in range(nbins)]
    )
    # A bin with <=1 marker cannot resolve the chord (ptp needs >=2 points) -> chord=0 there,
    # which silently UNDER-estimates S_WE as nbins grows past the marker density. Guard it: the
    # binning must be coarse enough to resolve every spanwise station of the contiguous planform.
    n_empty = int(np.sum(counts <= 1))
    if n_empty > 0.05 * nbins:
        raise ValueError(
            f"nbins={nbins} is too fine for {len(y)} markers: {n_empty} bin(s) hold <=1 marker "
            "and cannot resolve the chord, silently under-estimating S_WE. Use fewer bins "
            f"(the calibrated default is {_SWE_NBINS})."
        )
    chord_y = np.array(
        [
            np.ptp(x[(y >= edges[i]) & (y < edges[i + 1])]) if counts[i] > 1 else 0.0
            for i in range(nbins)
        ]
    )
    integrand = np.sqrt(chord_y**3 * ctr**3)
    return float(np.trapezoid(integrand, ctr))
