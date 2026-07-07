"""Report-only 2-grid grid-convergence grader for the flapping wing (Tier T3a), analysis-only.

Quantifies how the peak body-frame van Veen coefficients (``CF_chord``, ``CF_normal``) move under a
2x grid refinement (coarse 64x32x64 -> medium 128x64x128), for the "coarse-grid diffused-IB error"
hypothesis behind the ``CF_chord`` PARTIAL (issue #40). It is **report-only**: it emits the
coarse->medium relative change and a Grid Convergence Index reported as an **order-dependent band**
(``gci_p1``/``gci_p2`` at orders p = 1 and p = 2), with **no** pass/fail verdict, **no** loosenable
tolerance constant, and **no** Richardson ``cf_exact`` grid-independent estimate.

Why report-only, and why a band (see the OpenSpec design D3/D4):
  - **Order is unobservable from two grids.** The observed order needs a third grid (fine 256^3,
    out of scope -> H100/grant). Assuming a single p = 2 (the interior scheme's formal order) would
    *understate* the uncertainty, because **diffused-IB force extraction is expected below 2nd order
    near the boundary** — the tangential ``CF_chord`` (the #40 quantity) especially. So the GCI is
    reported across the band p in {1, 2}: at the same relative change, p = 1 gives a GCI **3x larger**
    than p = 2 (at r = 2). ``gci_p1`` is the **reported band edge, NOT a rigorous upper bound**:
    ``gci(p) -> inf`` as ``p -> 0``, so a sub-1 near-boundary order gives a true GCI exceeding
    ``gci_p1``.
  - **No Richardson extrapolant.** Part of the coarse<->medium delta is an **IB-regularization model
    change** (the marker volume ``dv = h*d_nn^2`` and the kernel support scale with the grid spacing
    ``h``), not a discretization error — so a "grid-converged value" is not defensible and would
    re-introduce the very extrapolate-the-true-answer over-claim the report-only framing removes. The
    GCI band conveys the discretization *uncertainty*, not a converged *value*.

Reuse (no re-derivation): the GCI arithmetic is the sphere
``analyze_sphere.grid_convergence_analysis`` **``if``-branch** (the ``observed_p``-finite GCI,
``Fs*|eps|/(r^p-1)`` with ``eps = (medium-coarse)/medium`` — ``analyze_sphere.py`` line ~322), made
explicit for two grids across a p-band with the assumed band order ``p`` substituted for the
unobservable ``observed_p`` (the sphere's ``else``-branch is instead the degenerate ``|eps|`` fallback
with no safety factor and no ``r^p-1`` denominator). The body-frame peaks come from the T2a
``reconstruct_wing_body_forces`` + ``body_frame_overall_match`` stack; the degeneracy floor is the
module's own ``_DEGENERATE_CF_FLOOR``.
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


def wing_grid_convergence_from_body_forces(
    coarse_csv: str | Path,
    medium_csv: str | Path,
    *,
    f_star: float,
    phi_amp_deg: float,
    pitch_amp_deg: float,
    window_t0: float = STEADY_WINDOW_T0,
) -> dict[str, dict[str, float]]:
    """Per-component report-only grid convergence from a coarse+medium pair of IB-particle CSVs.

    Reconstructs the peak body-frame ``|CF_chord|``/``|CF_normal|`` from **both** CSVs via the T2a
    ``reconstruct_wing_body_forces`` + ``body_frame_overall_match`` stack (reused, not re-derived —
    the rotation and ``F_ref`` are never re-implemented here; ``F_ref`` enters transitively through
    ``reconstruct_wing_body_forces``, which calls ``compute_force_reference``) and returns
    :func:`wing_grid_convergence` per component. Note the peaks fed to the grader are **magnitudes**
    (``|CF|`` window maxima, always >= 0), so the sign-flip branch documented on
    :func:`wing_grid_convergence` applies only to direct callers, not this body-forces path.

    Self-convergence sanity: feeding the **same** CSV as coarse and medium yields bit-identical peaks,
    so ``relative_change == 0`` and ``gci_p1 == gci_p2 == 0`` exactly. Scaling only ``Fx/Fy/Fz`` by
    ``k`` scales each peak by ``k``, giving ``relative_change == (k-1)/k`` (not ``k-1``, since the
    normalization is by ``cf_medium = k*cf_coarse``).

    Args:
        coarse_csv: Coarse-grid IB-particle CSV (e.g. the committed T2a coarse forces CSV in T3a).
        medium_csv: Medium-grid IB-particle CSV (the T3b operator run; a fixture/scaled copy in T3a).
        f_star: Dimensionless flap frequency.
        phi_amp_deg: Stroke amplitude [deg].
        pitch_amp_deg: Pitch amplitude [deg].
        window_t0: Steady-window start passed to ``body_frame_overall_match`` (default
            ``STEADY_WINDOW_T0``).

    Returns:
        A dict ``{"cf_chord": <wing_grid_convergence dict>, "cf_normal": <wing_grid_convergence dict>}``
        — report-only per component (no verdict, no ``cf_exact``).
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
    return {
        "cf_chord": wing_grid_convergence(coarse_chord, medium_chord),
        "cf_normal": wing_grid_convergence(coarse_normal, medium_normal),
    }
