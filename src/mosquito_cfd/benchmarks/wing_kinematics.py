"""Python mirror of the IAMReX ``WingKinematics.H`` prescribed-motion rotation.

Tier T2a (refactor-wing-axis-convention). This module is the **single canonical Python source** for
the analytic wing rotation ``R(t)`` — imported by the body-frame force decomposition
(``benchmarks.flapping_wing``) and the flapping-wing figure scripts, so there is exactly one code
copy of the kinematics (force-surrogate CC-3 / the coordinate-convention DRY requirement).

**New (van Veen 2022) convention** — matches the paper verbatim (§2.4, fig 1f; JFM 936:A3):
``R = Rz(φ)·Ry(α)·Rx(θ)`` with stroke ``φ`` about the lab vertical **z**, pitch/angle-of-attack
``α`` about the **span (y)** axis, and deviation ``θ`` about the chord (x). Axes: **x = chord**
(toward the trailing edge), **y = span** (toward the tip), **z = wing-normal / vertical**. van Veen
labels stroke ``γ`` and pitch ``φ``; this repo uses ``φ`` (stroke) and ``α`` (pitch) — the *same*
composition, different letters (do not conflate). See ``docs/coordinate-convention.md``.

Because the C++ solver is not exercised by CI, :func:`rotation_matrix` is pinned to hand-computed
golden matrices by ``test_python_mirror_matches_design_composition`` — the design's target composition
is the source of truth, and the refactored ``WingKinematics.H`` must conform to it (a matching
fork-side golden test closes the loop bidirectionally).

The pre-T2a composition is retained as :func:`rotation_matrix_legacy` for the **contrast baseline
only** (task 3.7 — showing the old stroke-∥-span motion differs); it is never used for
new-convention analysis.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _rz(a: float) -> NDArray[np.float64]:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _ry(a: float) -> NDArray[np.float64]:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _rx(a: float) -> NDArray[np.float64]:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rotation_matrix(
    phi: float, alpha: float, theta: float = 0.0
) -> NDArray[np.float64]:
    """New-convention wing rotation ``R = Rz(φ)·Ry(α)·Rx(θ)`` (van Veen 2022).

    Transforms a body-frame point to the lab frame. Stroke ``φ`` rotates about the lab vertical
    ``z`` (perpendicular to the span), pitch ``α`` about the span ``y``, deviation ``θ`` about the
    chord ``x``.

    Args:
        phi: Stroke angle [rad] (about lab z).
        alpha: Pitch / angle-of-attack [rad] (about the span y).
        theta: Deviation angle [rad] (about the chord x); default 0 (planar stroke).

    Returns:
        The 3x3 rotation matrix (FP64).
    """
    return _rz(phi) @ _ry(alpha) @ _rx(theta)


def rotation_matrix_legacy(
    phi: float, alpha: float, theta: float = 0.0
) -> NDArray[np.float64]:
    """Pre-T2a composition ``R = Rz(φ)·Ry(θ)·Rx(α)`` — **contrast baseline only**.

    This is the old convention (span along z, stroke ``Rz(φ)`` about the span axis, so a span-tip
    barely sweeps). Retained solely to demonstrate that the old motion differs from van Veen's
    translational sweep (task 3.7); never used for new-convention analysis.
    """
    return _rz(phi) @ _ry(theta) @ _rx(alpha)


def euler_angles(
    time: float,
    *,
    frequency: float,
    stroke_amp_rad: float,
    pitch_amp_rad: float,
    deviation_amp_rad: float = 0.0,
) -> tuple[float, float, float]:
    """Sinusoidal van Veen kinematics (mirror of ``WingKinematics.H::ComputeEulerAngles``).

    ``φ(t) = φ_amp·sin(ωt)`` (stroke), ``α(t) = α_amp·cos(ωt)`` (pitch, 90° lead),
    ``θ(t) = θ_amp·sin(2ωt)`` (deviation), with ``ω = 2π·frequency``.

    Args:
        time: Simulation time [dimensionless].
        frequency: Flap frequency ``f*`` (wingbeats per time unit).
        stroke_amp_rad: Stroke amplitude [rad].
        pitch_amp_rad: Pitch amplitude [rad].
        deviation_amp_rad: Deviation amplitude [rad]; default 0.

    Returns:
        ``(phi, alpha, theta)`` in radians.
    """
    omega = 2.0 * np.pi * frequency
    phi = stroke_amp_rad * np.sin(omega * time)
    alpha = pitch_amp_rad * np.cos(omega * time)
    theta = deviation_amp_rad * np.sin(2.0 * omega * time)
    return float(phi), float(alpha), float(theta)
