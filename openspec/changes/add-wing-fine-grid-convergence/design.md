# Design — add-wing-fine-grid-convergence (T3c)

## D1: Richardson extrapolant with IB coupling caveat (report-only, illustrative)

The standard Richardson extrapolant assumes `CF(h) = CF_exact + C·h^p` — a fixed discrete operator
converging as h→0. The diffused-IB scheme violates this: the marker volume `dv = h·d_nn²` and the
kernel support scale with the grid spacing `h`, so refining the grid also sharpens the IB-
regularization model. Each δᵢⱼ = CF_finer − CF_coarser reflects **combined spatial + IB-model
refinement**, not purely discretization error.

**Consequence for observed order:** p_obs = log|δ₁₂/δ₂₃|/log(r) mixes spatial and IB contributions
in each ratio; the ratio of two mixed deltas is still a finite, computable number that characterizes
how rapidly CF is changing under refinement — but it is not the formal convergence order of a fixed
PDE discretization.

**Consequence for cf_exact_richardson:** The extrapolated value `CF_fine + δ₂₃/(r^p_obs − 1)` is an
*illustrative* Richardson estimate, not a definitive h→0 physical limit. The IB sharpening means there
is no single fixed h→0 target — the IB model itself changes with h.

**Decision:** Report `observed_order` and `cf_exact_richardson` as report-only values **with an
explicit written caveat** in RESULTS and in the function docstring, consistent with the 2-grid
design (which explicitly avoided Richardson for this reason). We add Richardson in T3c *because* three
grids enable an observed rate that characterizes the convergence trend — the value is informative for
the science (#50) even if not a rigorous grid-converged limit. Never gate a verdict on cf_exact_richardson.

## D2: Non-monotone convergence returns NaN, not ValueError

If δ₁₂ = CF_medium − CF_coarse and δ₂₃ = CF_fine − CF_medium have **opposite signs** (the sequence
is oscillating — CF went down then up, or vice versa), observed_order is undefined (log of negative
number). This is a valid and informative scientific finding: the fine grid reversed the trend, which
could indicate the simulation is not in the asymptotic regime.

**Decision:** Return `observed_order = float('nan')`, `cf_exact_richardson = float('nan')`,
`gci_fine = float('nan')`, `monotone = False`. Do NOT raise ValueError — oscillating refinement is
a real result, not a bug. Tests verify `np.isnan` behavior and that `monotone=False` is the signal.

The same applies to the degenerate case where δ₂₃ is at or below `_DEGENERATE_CF_FLOOR` (the
fine-grid change is numerically zero — essentially self-convergent at the medium→fine step). Return
NaN for p_obs, cf_exact, gci_fine and set `monotone = True` (the direction didn't oscillate).

**p_obs ≤ 0 — negative or zero denominator guard:** When δ₁₂ and δ₂₃ have the same sign (monotone)
but |δ₂₃| ≥ |δ₁₂| (convergence is decelerating or exactly flat-rate), `p_obs ≤ 0`. The GCI and
Richardson formulas both divide by `r**p_obs − 1`. When p_obs ≤ 0, this denominator is ≤ 0; when
p_obs is small-positive, it is near-zero. Both cases produce a meaningless GCI (negative or ±∞).

**Decision:** Guard as `r**p_obs − 1 ≤ _DEGENERATE_DENOM_FLOOR` (a small positive threshold): if
the denominator is ≤ this floor, return NaN for `gci_fine` and `cf_exact_richardson`. Return
`observed_order` as-is — a negative or near-zero order is scientifically informative (tells you
convergence has stalled). `monotone` remains `True` (no oscillation). This guard is additional to,
not a replacement for, the δ₂₃-near-zero guard above.

Test: `cf_coarse=1.0, cf_medium=0.9, cf_fine=0.5` → δ₁₂=−0.1, δ₂₃=−0.4, |δ₁₂/δ₂₃|=0.25,
p_obs = log(0.25)/log(2) = −2.0 (monotone, decelerating) → observed_order=−2.0, gci_fine=NaN,
cf_exact_richardson=NaN, monotone=True.

## D3: Backward-compatible optional fine_csv parameter

`wing_grid_convergence_from_body_forces` gains `fine_csv: str | Path | None = None` as the
**third positional parameter** (before the keyword-only block). When `None`, behavior is identical to
the current 2-grid implementation (no code paths touched, same return dict). When provided, calls the
new `wing_grid_convergence_3grid` scalar. This is DRY (one function, one call site per grid count)
and backward-compatible (all existing callers with positional `coarse_csv, medium_csv` are unchanged).

**Alternative rejected:** A separate `wing_grid_convergence_3grid_from_body_forces` function. Rejected
because: (a) it duplicates the `_peaks()` helper logic; (b) it creates two parallel call paths that
could drift; (c) the user explicitly requested extending the existing function. The optional-parameter
design has been confirmed by the user.

## D4: 3-grid gradeability guard as a new function, not an overloaded assert_gradeable_pair

`assert_gradeable_triple(coarse, medium, fine, ...)` is a **new function**, not an optional-argument
extension of `assert_gradeable_pair`. Rationale: the pair guard is already called by name in existing
tests; adding `fine=None` to it would make the existing `test_assert_gradeable_pair_guards` tests
technically exercise a different code path (the `fine=None` branch), creating brittle coupling. A
separate function is unambiguous: the pair guard is for 2-grid, the triple guard is for 3-grid.
Internally, `assert_gradeable_triple` calls `assert_gradeable_pair(coarse, medium)` and
`assert_gradeable_pair(medium, fine)` to reuse the existing per-pair checks, then adds the cross-triple
`ns.fixed_dt` check when all three decks are supplied.

## D5: amrex.the_arena_init_size = 28 in the committed deck (proactive cap)

The A40 has 40 GB GPU RAM. AMReX default arena = 3/4 × 40 = 30 GB. The fine grid (8.4M cells FP64)
is 8× the medium grid. The medium run succeeded without a cap; if the medium needed ~3 GB of arena,
the fine may need ~24 GB — within the 30 GB cap. However, AMReX also allocates memory for ghost cells,
multi-level temporary arrays, and the Poisson solver, so the effective multiplier may exceed 8.

**Decision:** Proactively set `amrex.the_arena_init_size = 28` in the committed deck. This caps
AMReX's arena at 28 GB, leaving ~12 GB for OS/MPI/CUDA driver overhead. If the run still OOMs, the
operator notes this as a blocker in `run_metadata_t3c.json["oom_blocker"] = true` and #50 stays open.
The cap is documented in the deck header. 28 is not a magic number — the user confirmed this value.

## D6: CFL at fine grid — try dt=5e-4, fall back to dt=2.5e-4 if unstable

At Δx = 0.03125 and max |u| ≈ 28, CFL ≈ 0.45. The AMReX/IAMReX CFL criterion in the deck is
`ns.cfl = 0.3`, but with `ns.fixed_dt = 5e-4` the solver uses the fixed timestep regardless of the
CFL criterion (it's an inputs cap, not an enforcement). CFL = 0.45 is borderline.

**Decision:** The deck commits with `ns.fixed_dt = 5e-4`. If the operator observes diverging
velocities, they may reduce to `ns.fixed_dt = 2.5e-4` (a documented runtime fallback, NOT baked into
the deck). If dt is reduced:
- `run_metadata_t3c.json["dt_reduced"] = true` and `["fixed_dt"] = 2.5e-4`
- The `assert_gradeable_triple` guard will detect the dt mismatch from the deck vs the data and
  raise — the operator must pass the reduced dt explicitly via metadata, not deck
- RESULTS must explicitly flag: "dt reduced to 2.5e-4 for stability; temporal confounding introduced;
  the medium→fine delta reflects both spatial refinement and temporal refinement; the coarse/medium
  (same dt=5e-4) 2-grid comparison remains temporally isolated"

## D7: Session A / Session B split (operator-run gate)

The fine-grid run is an hours-long operator job that cannot run in this session. Structure:

- **Session A (this session):** reviewed + approved proposal (commit OpenSpec dir), fine-grid
  input deck, and all TDD code cluster-free (3-grid grader, guards, tests that skip when fine CSV absent)
- **Session B (post-run, /openspec:apply):** commit `forces_fine.csv` + `run_metadata_t3c.json`,
  fill RESULTS T3c numbers, run reproducibility guard, update roadmap to ✅
