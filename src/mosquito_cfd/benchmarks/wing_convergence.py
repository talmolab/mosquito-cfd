"""Report-only grid-convergence grader for the flapping wing (Tiers T3a/T3b/T3c), analysis-only.

Quantifies how the peak body-frame van Veen coefficients (``CF_chord``, ``CF_normal``) move under
grid refinement (coarse 64x32x64 -> medium 128x64x128 -> fine 256x128x256). The module provides:

- **2-grid GCI band** (``wing_grid_convergence``, T3a/T3b): ``gci_p1``/``gci_p2`` at p = 1..2
  without an assumed observed order; **no Richardson ``cf_exact``** (IB-regularization model change
  is not modelable by Richardson — see below).
- **3-grid observed order + Richardson estimate** (``wing_grid_convergence_3grid``, T3c): adds
  ``observed_order`` and an **illustrative** ``cf_exact_richardson`` from the three-grid triple.
  The IB coupling caveat applies (see D1 in the design doc): because the marker volume
  ``dv = h*d_nn^2`` and the kernel support scale with the grid spacing ``h``, refining the grid
  also sharpens the IB-regularization model — each delta reflects **combined spatial + IB-model
  refinement**, not purely discretization error. So ``cf_exact_richardson`` is an *illustrative*
  Richardson estimate, not a definitive h→0 limit, and is NEVER gated in a verdict.
- **Gradeability guards** (``assert_gradeable_pair``, ``assert_gradeable_triple``): fail loudly on
  empty / truncated / dt-reduced / wrong-pair inputs.
- **Body-forces wrapper** (``wing_grid_convergence_from_body_forces``): 2-grid path when
  ``fine_csv=None`` (default, backward-compat); 3-grid path when ``fine_csv`` is provided.

Why report-only, and why a band for 2-grid (see the OpenSpec design D3/D4):
  - **Order is unobservable from two grids.** The observed order needs a third grid (fine 256^3).
    Assuming a single p = 2 (the interior scheme's formal order) would *understate* the uncertainty,
    because **diffused-IB force extraction is expected below 2nd order near the boundary** — the
    tangential ``CF_chord`` (the #40 quantity) especially. So the 2-grid GCI is reported across the
    band p in {1, 2}: at the same relative change, p = 1 gives a GCI **3x larger** than p = 2 (at
    r = 2). ``gci_p1`` is the **reported band edge, NOT a rigorous upper bound**.
  - **IB coupling caveat for Richardson.** Part of the coarse<->medium<->fine delta is an
    **IB-regularization model change** (``dv = h*d_nn^2`` scales with h), not a discretization error
    — so ``cf_exact_richardson`` is an *illustrative* estimate, not a defensible grid-converged limit.

Reuse (no re-derivation): the GCI arithmetic is the sphere
``analyze_sphere.grid_convergence_analysis`` **``if``-branch** (``Fs*|eps|/(r^p-1)`` with
``eps = (medium-coarse)/medium`` — ``analyze_sphere.py`` line ~322). The body-frame peaks come from
the T2a ``reconstruct_wing_body_forces`` + ``body_frame_overall_match`` stack.

p_obs ≤ 0 guard (design D2): when the denominator ``r**p_obs − 1 ≤ _DEGENERATE_DENOM_FLOOR``
(covering p_obs ≤ 0 AND p_obs ≈ 0+), GCI and Richardson are meaningless (negative or ±∞); the guard
returns NaN for both while preserving ``observed_order`` as-is (a negative order is scientifically
informative — it signals convergence has stalled or reversed).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.benchmarks.flapping_wing import (
    _DEGENERATE_CF_FLOOR,
    STEADY_WINDOW_T0,
    body_frame_overall_match,
    reconstruct_wing_body_forces,
)

# Stop time (physical) both convergence decks reach; the grading window endpoint.
_STOP_TIME = 1.0

# Guard threshold for the GCI / Richardson denominator r**p_obs − 1 (design D2).
# When the denominator is at or below this floor (p_obs ≤ 0 or p_obs ≈ 0+), the GCI and
# Richardson extrapolant are meaningless (negative or ±∞); return NaN for those values
# while preserving observed_order (informative even when negative).
_DEGENERATE_DENOM_FLOOR = 1e-10


def _deck_float(deck_path: str | Path, key: str) -> float:
    """Read a single scalar ParmParse value (e.g. ``ns.fixed_dt``) from an IAMReX inputs deck."""
    for line in Path(deck_path).read_text().splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith(key) and "=" in stripped:
            lhs, rhs = stripped.split("=", 1)
            if lhs.strip() == key:
                return float(rhs.split()[0])
    raise ValueError(f"key {key!r} not found in deck {deck_path}")


def assert_gradeable_pair(
    coarse_csv: str | Path,
    medium_csv: str | Path,
    *,
    coarse_deck: str | Path | None = None,
    medium_deck: str | Path | None = None,
    stop_time: float = _STOP_TIME,
) -> None:
    """Guard that a coarse+medium IB-particle CSV pair is safely gradeable, else raise loudly.

    The grader compares each CSV's **independent** window-max peak, so a wrong-pair, truncated, or
    run-time-dt-reduced write-out would silently return a plausible-but-wrong convergence number. This
    pre-flight check fails loudly instead. It asserts (self-describing ``ValueError`` on each):

      1. **non-empty** — a header-only CSV raises ``"no data rows"`` (not a low-level error from the
         reused reconstruction downstream);
      2. **covers the window** — each ``max(time)`` is within a few ``dt`` of ``stop_time`` (a truncated
         write-out raises ``"window"``);
      3. **same time grid** — the two CSVs share the same **set of unique ``iStep`` values** and matching
         unique sample times (compared deduplicated, since ``ns.init_iter = 2`` writes duplicate ``t=0``
         rows, so a raw row-count/``allclose`` check would false-reject a valid same-dt run). A run-time
         ``dt`` reduction (twice as many distinct steps) raises ``"time-grid"`` — this is the temporal
         confound the deck-invariance requirement forbids, caught at the data level.

    When both decks are supplied, it also asserts ``ns.fixed_dt`` is equal between them (the
    hash-pinned decks are the authoritative dt source; ``run_metadata_t2a.json`` carries no ``fixed_dt``
    field, so the guard never reads it from there).

    Args:
        coarse_csv: Coarse-grid IB-particle CSV.
        medium_csv: Medium-grid IB-particle CSV.
        coarse_deck: Optional coarse deck path for the ``ns.fixed_dt`` equality check.
        medium_deck: Optional medium deck path for the ``ns.fixed_dt`` equality check.
        stop_time: Physical window endpoint both runs must reach (default 1.0).

    Raises:
        ValueError: with a ``"no data rows"`` / ``"window"`` / ``"time-grid"`` / ``"fixed_dt"`` substring
            identifying which gradeability precondition failed.
    """
    dc = pd.read_csv(coarse_csv)
    dm = pd.read_csv(medium_csv)
    for tag, d in (("coarse", dc), ("medium", dm)):
        if len(d) == 0:
            raise ValueError(
                f"{tag} CSV has no data rows (header-only or empty write-out)"
            )
    # A few dt of slack: the last written sample sits one dt short of stop_time (t = 0.9995).
    for tag, d in (("coarse", dc), ("medium", dm)):
        t_max = float(d["time"].max())
        if abs(t_max - stop_time) > 5e-3:
            raise ValueError(
                f"{tag} CSV does not cover the stop_time={stop_time} window "
                f"(max time {t_max:.4g}); a truncated write-out is not gradeable"
            )
    # Same time grid, deduplicated (init_iter=2 writes duplicate t=0 rows).
    steps_c = np.unique(dc["iStep"].to_numpy())
    steps_m = np.unique(dm["iStep"].to_numpy())
    if steps_c.shape != steps_m.shape or not np.array_equal(steps_c, steps_m):
        raise ValueError(
            "time-grid mismatch: coarse and medium have different unique iStep sets "
            f"({steps_c.size} vs {steps_m.size} distinct steps) — a run-time dt reduction or a "
            "wrong-pair; the coarse<->medium peaks would be sampled on incongruent time grids"
        )
    times_c = np.unique(dc["time"].to_numpy())
    times_m = np.unique(dm["time"].to_numpy())
    if times_c.shape != times_m.shape or not np.allclose(times_c, times_m):
        raise ValueError(
            "time-grid mismatch: coarse and medium unique sample times differ (same step count but "
            "different dt) — not gradeable without a common time grid"
        )
    if coarse_deck is not None and medium_deck is not None:
        dt_c = _deck_float(coarse_deck, "ns.fixed_dt")
        dt_m = _deck_float(medium_deck, "ns.fixed_dt")
        if dt_c != dt_m:
            raise ValueError(
                f"deck ns.fixed_dt mismatch: coarse {dt_c} vs medium {dt_m}; holding dt fixed is what "
                "isolates the spatial convergence delta from temporal error"
            )


def assert_gradeable_triple(
    coarse_csv: str | Path,
    medium_csv: str | Path,
    fine_csv: str | Path,
    *,
    coarse_deck: str | Path | None = None,
    medium_deck: str | Path | None = None,
    fine_deck: str | Path | None = None,
    stop_time: float = _STOP_TIME,
) -> None:
    """Guard that a coarse+medium+fine IB-particle CSV triple is safely gradeable (design D4).

    Internally delegates to :func:`assert_gradeable_pair` twice — once for the coarse+medium pair
    and once for the medium+fine pair — to reuse all per-pair checks (non-empty, covers the window,
    same time grid). This composition proof means the middle grid (medium) is validated against
    BOTH the coarse and the fine grid; a truncated or wrong medium CSV raises regardless of which
    pair check catches it.

    When all three decks are supplied, also checks that ``ns.fixed_dt`` is consistent across all
    three decks (cross-triple dt invariance, on top of the per-pair deck check inside
    ``assert_gradeable_pair``).

    Args:
        coarse_csv: Coarse-grid IB-particle CSV.
        medium_csv: Medium-grid IB-particle CSV.
        fine_csv: Fine-grid IB-particle CSV.
        coarse_deck: Optional coarse deck path for the ``ns.fixed_dt`` consistency check.
        medium_deck: Optional medium deck path for the ``ns.fixed_dt`` consistency check.
        fine_deck: Optional fine deck path for the ``ns.fixed_dt`` consistency check.
        stop_time: Physical window endpoint all three runs must reach (default 1.0).

    Raises:
        ValueError: with a ``"no data rows"`` / ``"window"`` / ``"time-grid"`` / ``"fixed_dt"``
            substring identifying which gradeability precondition failed — delegated from
            :func:`assert_gradeable_pair` for per-pair failures, or raised directly here for the
            cross-triple ``fixed_dt`` mismatch.
    """
    assert_gradeable_pair(
        coarse_csv,
        medium_csv,
        coarse_deck=coarse_deck,
        medium_deck=medium_deck,
        stop_time=stop_time,
    )
    assert_gradeable_pair(
        medium_csv,
        fine_csv,
        coarse_deck=medium_deck,
        medium_deck=fine_deck,
        stop_time=stop_time,
    )
    # Cross-triple dt check: when all three decks supplied, verify all share the same fixed_dt.
    if coarse_deck is not None and medium_deck is not None and fine_deck is not None:
        dt_c = _deck_float(coarse_deck, "ns.fixed_dt")
        dt_m = _deck_float(medium_deck, "ns.fixed_dt")
        dt_f = _deck_float(fine_deck, "ns.fixed_dt")
        if not (dt_c == dt_m == dt_f):
            raise ValueError(
                f"deck ns.fixed_dt mismatch across all three decks: "
                f"coarse {dt_c}, medium {dt_m}, fine {dt_f}; "
                "holding dt fixed across all grids isolates the spatial convergence delta from "
                "temporal error"
            )


def wing_grid_convergence(
    cf_coarse: float,
    cf_medium: float,
    *,
    r: float = 2.0,
    safety_factor: float = 1.25,
) -> dict[str, float]:
    """Report-only 2-grid GCI **band** (orders p = 1..2) for one body-frame peak coefficient.

    Computes the coarse->medium relative change ``(cf_medium - cf_coarse)/cf_medium`` (normalized by
    ``cf_medium``, matching the reused sphere ``epsilon``) and the GCI at orders p = 1 and p = 2 using
    the sphere's formula ``Fs*|relative_change|/(r^p - 1)``. It is **report-only** — no pass/fail
    verdict, no single assumed order, and **no Richardson ``cf_exact``** grid-independent estimate
    (part of the coarse<->medium delta is an IB-regularization model change with no Richardson limit;
    the GCI band already conveys the discretization uncertainty).

    Interpretation caveats (reported, not gated):
      - The order is **unobservable from two grids**, and **diffused-IB force extraction is expected
        below the formal 2nd order near the boundary** (the tangential ``CF_chord`` especially), so a
        single assumed p = 2 would *understate* the uncertainty — hence the p = 1..2 band.
      - ``gci_p1`` is the **reported band edge, NOT a rigorous upper bound**: ``gci(p) -> inf`` as
        ``p -> 0``, so a sub-1 near-boundary order gives a true GCI larger than ``gci_p1``.
      - ``relative_change < 0`` means the coefficient **dropped** under refinement (the #40 direction);
        an opposite-sign coarse/medium pair returns finite values with ``|relative_change| > 1``
        (honestly "not converged"), never an error.

    Args:
        cf_coarse: Peak body-frame coefficient on the coarse grid.
        cf_medium: Peak body-frame coefficient on the medium grid; the normalization denominator.
        r: Grid refinement ratio (default 2.0).
        safety_factor: GCI safety factor ``Fs`` (default 1.25, the standard Roache value).

    Returns:
        A dict with exactly ``cf_coarse``, ``cf_medium``, ``relative_change``, ``gci_p1``, ``gci_p2``,
        ``r`` — no verdict field and no ``cf_exact``.

    Raises:
        ValueError: if ``cf_coarse``/``cf_medium`` are non-finite; if ``|cf_medium|`` is below
            ``_DEGENERATE_CF_FLOOR`` (the denominator is degenerate — raised loudly rather than a
            ``ZeroDivisionError``, a silent ``nan``, or a huge finite garbage ratio); or if
            ``r <= 1`` (``r^p - 1`` would be non-positive) or ``safety_factor < 0``.
    """
    if not (np.isfinite(cf_coarse) and np.isfinite(cf_medium)):
        raise ValueError(
            f"cf_coarse and cf_medium must be finite (got {cf_coarse}, {cf_medium})"
        )
    # `<=` (inclusive): a denominator AT the floor still yields a ~1/floor huge-finite ratio, the
    # exact "silent garbage" the spec forbids. The floor gates NUMERICAL degeneracy (~8 orders below
    # any physical CF peak); a physically-small-but-real cf_medium above it legitimately produces a
    # large relative_change (honestly "not converged", like the opposite-sign case), not an error.
    if abs(cf_medium) <= _DEGENERATE_CF_FLOOR:
        raise ValueError(
            f"cf_medium is {cf_medium:.3g}, at or below the numerical degeneracy floor "
            f"{_DEGENERATE_CF_FLOOR:g}; the relative change (normalized by cf_medium) and the GCI "
            "band are undefined for a (near-)zero degenerate denominator (check the input run)"
        )
    if not (np.isfinite(r) and r > 1.0):
        raise ValueError(f"refinement ratio r must be finite and > 1 (got {r})")
    if not (np.isfinite(safety_factor) and safety_factor >= 0.0):
        raise ValueError(
            f"safety_factor must be finite and non-negative (got {safety_factor})"
        )

    relative_change = (cf_medium - cf_coarse) / cf_medium

    def gci(p: float) -> float:
        # The sphere's if-branch GCI (analyze_sphere.py:322, observed_p-finite), made explicit for
        # one assumed order p in place of the unobservable observed_p (reuse, not re-derivation).
        return safety_factor * abs(relative_change) / (r**p - 1.0)

    return {
        "cf_coarse": float(cf_coarse),
        "cf_medium": float(cf_medium),
        "relative_change": float(relative_change),
        "gci_p1": float(gci(1.0)),
        "gci_p2": float(gci(2.0)),
        "r": float(r),
    }


def wing_grid_convergence_3grid(
    cf_coarse: float,
    cf_medium: float,
    cf_fine: float,
    *,
    r: float = 2.0,
    safety_factor: float = 1.25,
) -> dict[str, float | bool]:
    """Report-only 3-grid Richardson convergence analysis for one body-frame peak coefficient.

    Computes from the three-grid triple (coarse → medium → fine, refinement ratio r = 2):

    - ``observed_order`` = log|δ₁₂/δ₂₃| / log(r), where δ₁₂ = cf_medium − cf_coarse and
      δ₂₃ = cf_fine − cf_medium; ``NaN`` if non-monotone (opposite-sign δ values) or degenerate
      (δ₂₃ at or below ``_DEGENERATE_CF_FLOOR``). Returned as-is even when negative (a negative
      order is scientifically informative — convergence is stalled or decelerating).
    - ``cf_exact_richardson`` = cf_fine + δ₂₃ / (r^p_obs − 1); ``NaN`` when observed_order is
      ``NaN`` OR when the denominator r^p_obs − 1 ≤ ``_DEGENERATE_DENOM_FLOOR`` (p_obs ≤ 0 or ≈ 0+).
      **IB coupling caveat (design D1):** this is an *illustrative* Richardson estimate — the
      diffused-IB regularization sharpens with the grid (dv = h·d_nn²), so each δ reflects combined
      spatial + IB-model refinement; cf_exact_richardson is NOT a definitive h→0 limit.
    - ``gci_fine`` = safety_factor · |ε₂₃| / (r^p_obs − 1), ε₂₃ = δ₂₃/cf_fine; ``NaN`` when NaN.
    - ``monotone`` = ``bool(sign(δ₁₂) == sign(δ₂₃))``; always a bool, never NaN.
    - ``cf_coarse``, ``cf_medium``, ``cf_fine``, ``r`` — always returned as-is.

    **Report-only, no verdict.** The return dict has exactly
    ``{cf_coarse, cf_medium, cf_fine, observed_order, cf_exact_richardson, gci_fine, r, monotone}``.
    "Not converged", "non-monotone", and p_obs ≤ 0 are valid, informative outcomes — not errors.

    Args:
        cf_coarse: Peak body-frame coefficient on the coarse grid.
        cf_medium: Peak body-frame coefficient on the medium grid.
        cf_fine: Peak body-frame coefficient on the fine grid; also the GCI normalization denominator.
        r: Grid refinement ratio (default 2.0, the coarse/medium/fine doubling factor).
        safety_factor: GCI safety factor Fs (default 1.25, the standard Roache value).

    Returns:
        A dict with exactly ``{cf_coarse, cf_medium, cf_fine, observed_order, cf_exact_richardson,
        gci_fine, r, monotone}`` — no verdict field and no pass/fail key.

    Raises:
        ValueError: if any of ``cf_coarse``/``cf_medium``/``cf_fine`` are non-finite; if ``|cf_fine|``
            is at or below ``_DEGENERATE_CF_FLOOR`` (the GCI ε₂₃ denominator is degenerate); if
            ``r <= 1`` or ``safety_factor < 0``.
    """
    if not (np.isfinite(cf_coarse) and np.isfinite(cf_medium) and np.isfinite(cf_fine)):
        raise ValueError(
            f"cf_coarse, cf_medium, and cf_fine must be finite "
            f"(got {cf_coarse}, {cf_medium}, {cf_fine})"
        )
    if abs(cf_fine) <= _DEGENERATE_CF_FLOOR:
        raise ValueError(
            f"cf_fine is {cf_fine:.3g}, at or below the numerical degeneracy floor "
            f"{_DEGENERATE_CF_FLOOR:g}; the GCI epsilon (normalized by cf_fine) and the "
            "Richardson extrapolant are undefined for a (near-)zero degenerate denominator"
        )
    if not (np.isfinite(r) and r > 1.0):
        raise ValueError(f"refinement ratio r must be finite and > 1 (got {r})")
    if not (np.isfinite(safety_factor) and safety_factor >= 0.0):
        raise ValueError(
            f"safety_factor must be finite and non-negative (got {safety_factor})"
        )

    delta_12 = cf_medium - cf_coarse
    delta_23 = cf_fine - cf_medium

    # monotone: same sign (or self-convergent zero). sign(0) treated as same-direction.
    monotone = bool(
        np.sign(delta_12) == np.sign(delta_23) or delta_12 == 0 or delta_23 == 0
    )

    _nan = float("nan")

    if not monotone or abs(delta_23) <= _DEGENERATE_CF_FLOOR:
        # Non-monotone (oscillating refinement) or self-convergent (δ₂₃ ≈ 0).
        return {
            "cf_coarse": float(cf_coarse),
            "cf_medium": float(cf_medium),
            "cf_fine": float(cf_fine),
            "observed_order": _nan,
            "cf_exact_richardson": _nan,
            "gci_fine": _nan,
            "r": float(r),
            "monotone": monotone,
        }

    p_obs = np.log(abs(delta_12 / delta_23)) / np.log(r)
    denom = r**p_obs - 1.0

    if denom <= _DEGENERATE_DENOM_FLOOR:
        # p_obs ≤ 0 or ≈ 0+: denominator is non-positive or near-zero → GCI/Richardson meaningless.
        # Return p_obs as-is (informative: negative order signals convergence stalled or reversed).
        return {
            "cf_coarse": float(cf_coarse),
            "cf_medium": float(cf_medium),
            "cf_fine": float(cf_fine),
            "observed_order": float(p_obs),
            "cf_exact_richardson": _nan,
            "gci_fine": _nan,
            "r": float(r),
            "monotone": monotone,
        }

    epsilon_23 = delta_23 / cf_fine
    gci_fine = safety_factor * abs(epsilon_23) / denom
    cf_exact = cf_fine + delta_23 / denom

    return {
        "cf_coarse": float(cf_coarse),
        "cf_medium": float(cf_medium),
        "cf_fine": float(cf_fine),
        "observed_order": float(p_obs),
        "cf_exact_richardson": float(cf_exact),
        "gci_fine": float(gci_fine),
        "r": float(r),
        "monotone": monotone,
    }


def wing_grid_convergence_from_body_forces(
    coarse_csv: str | Path,
    medium_csv: str | Path,
    fine_csv: str | Path | None = None,
    *,
    f_star: float,
    phi_amp_deg: float,
    pitch_amp_deg: float,
    window_t0: float = STEADY_WINDOW_T0,
) -> dict[str, dict[str, float]]:
    """Per-component report-only grid convergence from a coarse+medium (or coarse+medium+fine) CSV set.

    Reconstructs the peak body-frame ``|CF_chord|``/``|CF_normal|`` from each CSV via the T2a
    ``reconstruct_wing_body_forces`` + ``body_frame_overall_match`` stack (reused, not re-derived —
    the rotation and ``F_ref`` are never re-implemented here; ``F_ref`` enters transitively through
    ``reconstruct_wing_body_forces``, which calls ``compute_force_reference``) and returns
    :func:`wing_grid_convergence` (2-grid) or :func:`wing_grid_convergence_3grid` (3-grid) per
    component. Note the peaks fed to the grader are **magnitudes** (``|CF|`` window maxima, always
    >= 0).

    **Backward-compat (design D3):** when ``fine_csv`` is ``None`` (the default), behavior is
    identical to the pre-T3c implementation — the same 2-grid return dict per component
    (``cf_coarse``, ``cf_medium``, ``relative_change``, ``gci_p1``, ``gci_p2``, ``r``). All T3b
    tests pass unmodified. When ``fine_csv`` is provided, each component returns the 3-grid dict
    (``cf_coarse``, ``cf_medium``, ``cf_fine``, ``observed_order``, ``cf_exact_richardson``,
    ``gci_fine``, ``r``, ``monotone``).

    Args:
        coarse_csv: Coarse-grid IB-particle CSV (e.g. the committed T2a ``forces_t2a_newconv.csv``).
        medium_csv: Medium-grid IB-particle CSV (T3b operator run; a fixture/scaled copy in T3a).
        fine_csv: Fine-grid IB-particle CSV (T3c operator run), or ``None`` (default) for 2-grid.
        f_star: Dimensionless flap frequency.
        phi_amp_deg: Stroke amplitude [deg].
        pitch_amp_deg: Pitch amplitude [deg].
        window_t0: Steady-window start passed to ``body_frame_overall_match`` (default
            ``STEADY_WINDOW_T0``).

    Returns:
        ``{"cf_chord": <grader dict>, "cf_normal": <grader dict>}`` — report-only per component
        (no verdict, no pass/fail). 2-grid dict when ``fine_csv=None``; 3-grid dict otherwise.
    """

    def _peaks(csv_path: str | Path) -> tuple[float, float]:
        decomp = reconstruct_wing_body_forces(
            csv_path,
            f_star=f_star,
            phi_amp_deg=phi_amp_deg,
            pitch_amp_deg=pitch_amp_deg,
        )
        match = body_frame_overall_match(decomp, window_t0=window_t0)
        return match["peak_cf_chord"], match["peak_cf_normal"]

    coarse_chord, coarse_normal = _peaks(coarse_csv)
    medium_chord, medium_normal = _peaks(medium_csv)

    if fine_csv is None:
        return {
            "cf_chord": wing_grid_convergence(coarse_chord, medium_chord),
            "cf_normal": wing_grid_convergence(coarse_normal, medium_normal),
        }

    fine_chord, fine_normal = _peaks(fine_csv)
    return {
        "cf_chord": wing_grid_convergence_3grid(coarse_chord, medium_chord, fine_chord),
        "cf_normal": wing_grid_convergence_3grid(
            coarse_normal, medium_normal, fine_normal
        ),
    }
