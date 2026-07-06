# Design — wing grid-convergence tooling + medium deck (T3a)

## Context

T3 quantifies how the coarse (64³) body-frame wing coefficients move under a 2× refinement to medium
(128³) — testing the "coarse-grid diffused-IB error" hypothesis for the `CF_chord` PARTIAL (#40). The
medium run is an hours-long operator-run A40 job, so the tier splits T3a (cluster-free tooling+deck, this
change) / T3b (the graded run). This doc records the design decisions for T3a.

## Decisions

### D1 — T3a / T3b split

T3a builds and TDD-validates everything cluster-free (the medium deck, the convergence grader, the LEV
math) against the committed coarse run + synthetic fixtures, so the tooling and deck are reviewed **before**
the expensive run. T3b (separate change, after the operator run) commits `forces_medium.csv` + run metadata
and applies the grader. Mirrors T2a/T2b. *Rationale:* de-risk hours of A40 time; keep each PR reviewable.

### D2 — Report-only convergence, no pass/fail bar (scoping decision)

The grader **reports** the coarse→medium relative change + a GCI uncertainty band per body-frame
component; it does **not** grade a pass/fail and defines **no** loosenable tolerance constant. *Rationale:*
(a) with 2 grids there is no observed order to anchor a rigorous "converged" claim; (b) a fixed pass-bar
would be arbitrary; (c) the tier's value is the **quantified grid sensitivity** feeding T4/#40 — a
"not converged at coarse" reading is a valid, informative result, not a tier failure. The return dict
carries **no** `*_pass`/`*_match`/`converged` boolean; a test asserts that.

### D3 — 2-grid GCI as an order-dependent band (p = 1..2), not a single assumed p = 2

The sphere `grid_convergence_analysis(cd_coarse, cd_medium, cd_fine, r)` computes the **observed** order
from **three** grids. We have **two** (fine 256³ is out of scope → H100/grant), so the observed order is
not computable. Assuming a single `p = 2` (the interior scheme's formal order) would be an **over-claim**:
the **diffused-IB force extraction is expected to be lower than 2nd order near the boundary** — often ~1st
order — and the tangential `CF_chord` (the very #40 quantity) is a shear-dominated boundary force where
diffused IB is weakest. At the same `|eps|`, `p = 1` gives a GCI **3× larger** than `p = 2`. So the grader
reports the GCI as an **order-dependent band** across `p ∈ {1, 2}` (1st-order boundary to formal 2nd-order),
using the sphere's formula:

```
relative_change = (cf_medium - cf_coarse) / cf_medium              # sphere epsilon (÷ cf_medium)
gci(p)          = safety_factor * |relative_change| / (r**p - 1)   # p=1: 1.25|e|/1;  p=2: 1.25|e|/3
```

This is the sphere's `if`-branch GCI (the `observed_p`-finite `Fs·|eps|/(r^p−1)`, `analyze_sphere.py`
~L322) made explicit — the assumed band order `p` substituted for the unobservable `observed_p`;
**reuse of the formula, not a re-derivation** (the sphere's `else`-branch is instead the degenerate
`|eps|` fallback, no safety factor and no `r^p−1` denominator, which we deliberately do NOT use). It
returns `relative_change, gci_p1, gci_p2` (no single `assumed_p`). The docstring states the order is
**unobservable from 2 grids** and diffused-IB force is expected below 2nd order, and it does **not** cite the
sphere T1b's p = 2 as justification (the sphere Cd is a pressure-dominated *integral* quantity — not
transferable to the tangential wing CF). Known-answer (coarse 0.92 / medium 0.80): `relative_change = -0.15`,
`gci_p1 = 1.25·0.15/1 = 0.1875`, `gci_p2 = 1.25·0.15/3 = 0.0625`.

**No Richardson `cf_exact` is emitted** (dropped in review). A Richardson extrapolant
`cf_medium + (cf_medium−cf_coarse)/(r^p−1)` estimates the *grid-independent* force **only if the whole
coarse↔medium delta is order-p discretization error** — but D4 establishes that part of it is an
**IB-regularization model change**, which has no Richardson limit. Reporting a "grid-converged value" would
re-introduce the precise extrapolate-the-true-answer over-claim this report-only change exists to remove, and
`cf_exact` is anyway redundant with the GCI (`gci = Fs·|cf_exact − cf_med|/cf_med`). The **GCI band is the
discretization *uncertainty*, not a converged *value***. Relatedly, **`gci_p1` is the reported band edge, NOT
a rigorous upper bound**: `gci(p) → ∞` as `p → 0`, so if the near-boundary order is sub-1 (plausible for the
shear-dominated `CF_chord`), the true GCI **exceeds** `gci_p1` — the docstring/spec state this so `gci_p1` is
not read as a worst case.

**`relative_change` is normalized by `cf_medium`** (matching the sphere `epsilon`), NOT `cf_coarse` — so a
force field scaled by `k` (`cf_medium = k·cf_coarse`) gives `relative_change = (k-1)/k`, **not** `k-1`. A
near-zero `cf_medium` (the denominator) raises the module's `ValueError` (reusing `_DEGENERATE_CF_FLOOR`);
opposite-sign inputs return finite report values (honestly "not converged").

*Why not call the 3-grid function with `cd_fine = cd_medium`?* That gives `denom = 0 → observed_p = inf`
and a degenerate result with the GCI falling to the `abs(epsilon)` fallback — **wrong**. A
purpose-built 2-grid band function is the faithful reuse.

### D4 — dt held fixed at 5e-4 (isolate temporal error); the delta is spatial + IB-regularization, not "purely spatial"

The medium deck keeps `ns.fixed_dt = 5e-4` (the coarse value), changing **only** `amr.n_cell`. Holding dt
fixed makes the temporal discretization error **identical** in both runs, so the coarse↔medium difference is
**isolated from temporal error** (halving dt with Δx would confound spatial + temporal refinement).

It is **not** "purely spatial," however. The diffused-IB regularization is **grid-tied**: per this repo's
own findings (and confirmed in the IAMReX `DiffusedIB.cpp` source) the marker volume `dv = h·d_nn²` and the
regularized delta-kernel support (`2h`, a fixed index-space stencil × `h`) scale with the grid spacing `h`,
so refining the grid **also sharpens the IB regularization model** (narrower kernel, different `dv`). Holding
`particle_inputs.radius = 1.5` fixed does **not** pin the kernel — `radius` sets the signed-distance/indicator
field, a **separate** knob from the h-tied spreading kernel — so it is held constant while the kernel still
sharpens with `h`. The coarse↔medium
coefficient change therefore reflects **combined spatial discretization + IB-regularization refinement**,
and Richardson extrapolation does **not** model the IB-regularization part — a further, independent reason
the study is **report-only** (compounding D3: the order is both unobservable *and* the delta isn't a pure
discretization error). This caveat is stated in the proposal, the deck header, and the spec.

CFL at medium: using the same `u_max ≈ 28` (the peak wingtip speed `|u|≈28` from the flapping-wing stability
runs — not the single-slice figure range `[−9.98, +1.90]` printed in RESULTS) for both grids,
`CFL_medium ≈ 28·5e-4/0.0625 ≈ 0.22 < 0.3` (coarse `≈ 0.11` at `Δx = 0.125`; stable). If the medium run is
unstable the operator may
reduce dt — a documented run-time fallback recorded in T3b, **not** a deck change T3a bakes in (it would
reintroduce temporal confounding).

### D5 — LEV as pure vorticity/Q functions, plotfile wiring deferred to T3b

The LEV "resolved/present" oracle is a **reported diagnostic**, not a gate. T3a implements the *math* as
pure functions — `vorticity_magnitude(u, v, w, spacing)` (‖∇×**u**‖) and `q_criterion(u, v, w, spacing)`
(`Q = ½(‖Ω‖² − ‖S‖²)`, the **half-difference** convention — documented so a downstream Q-isosurface
threshold from a paper isn't applied with a 2× mismatch) — TDD'd on synthetic fields with **known analytic**
answers: solid-body rotation `(u,v,w) = Ω×r` gives uniform `|ω| = 2Ω` and `Q = Ω²` in the core. `spacing`
accepts a **scalar** (isotropic grid — the medium deck is `128 64 128` on `8 4 8` → `Δx = Δy = Δz = 0.0625`)
**or** a `(dx, dy, dz)` triple passed per-axis to `np.gradient`, so the T3b plotfile wiring cannot silently
mis-differentiate an anisotropic grid. The yt plotfile→field extraction (reusing `load_plotfile` /
`generate_all_figures.py`'s slice reader) and the actual "LEV present at medium, weak/absent at coarse"
call are **T3b** — no committed new-convention plotfile exists in-repo (the T2a plotfiles live on the Z:
drive). *Rationale:* the numerically load-bearing part (the curl/Q math) is cluster-free and testable now;
the field extraction is trivially wired once the medium plotfile exists.

### D6 — Deck-invariance baseline is `inputs.3d.validation` (sha-verified)

The invariance test compares the medium deck against `examples/flapping_wing/inputs.3d.validation` — the
**confirmed** canonical coarse deck (its sha256 `f9b69d98…` equals the `inputs.hash` in
`run_metadata_t2a.json`). The old-BC `inputs.3d.validation_v2` (`ns.lo/hi_bc = 2 0 4`, z-wall) and
`inputs.3d.production` — which is **old-BC `2 0 4`, a different operating point (f\* = 0.1, ν\* = 0.01, 3
wingbeats), AND already 128³** (the naive-but-wrong medium deck: it looks like the medium grid but is a
different physics case with the wrong BCs) — are explicitly **not** the baseline. The test parses both decks
into key→value maps (comments stripped, each value's internal whitespace normalized to avoid false diffs on
reformatting) and asserts the symmetric difference is exactly `{amr.n_cell}` (`amr.max_grid_size` held at 32),
**and** that `fixed_dt` and `particle_inputs.radius` are float-equal across decks (the fixed regularization
length held against the changing `h`).

### D7 — Reuse surface (no re-derivation)

- **Body-frame coefficients:** `reconstruct_wing_body_forces` → `body_frame_overall_match` give the peak
  `CF_chord`/`CF_normal` the grader consumes; the grader takes those peaks (or the CSVs) and never
  re-implements the rotation or `F_ref`.
- **GCI/Richardson:** the sphere formula (see D3).
- **Provenance (T3b):** `capture_run_metadata` (image digest, IAMReX commit `f93dc794`, inputs hash, git,
  hardware, timing); same `:fp64` pin (grid refinement needs no new solver features).
- **Reproducibility guard:** the T2b `tests/test_results_reproducibility.py` pattern (T3b recomputes the
  RESULTS convergence numbers from committed data).

## API sketch

```python
def wing_grid_convergence(
    cf_coarse: float, cf_medium: float, *, r: float = 2.0, safety_factor: float = 1.25,
) -> dict:
    """Report-only 2-grid GCI BAND (orders p=1..2) for one body-frame peak.

    Returns {cf_coarse, cf_medium, relative_change, gci_p1, gci_p2, r} — NO pass/fail, NO single
    assumed_p, NO Richardson cf_exact (a grid-independent value is not defensible; see D3/D4).
    gci_p1 is the reported band edge, not a rigorous upper bound. Raises ValueError on near-zero cf_medium.
    """

def vorticity_magnitude(u, v, w, spacing) -> NDArray: ...  # ‖∇×u‖; spacing scalar or (dx,dy,dz)
def q_criterion(u, v, w, spacing) -> NDArray: ...          # Q = ½(‖Ω‖² − ‖S‖²), half-difference
```

## Risks / mitigations

- **Reader treats a GCI number as a pass** → D2 (no verdict field) + docs state report-only + a test
  asserting no `*_pass` key.
- **"Reuse" quietly becomes a re-derivation** → D3/D7 name the exact reused pieces; a test pins the grader
  against the body-frame stack's peaks, and a known-answer test pins the GCI arithmetic.
- **Medium deck silently drifts from the coarse operating point** → D6 deck-invariance test (symmetric diff
  == `{amr.n_cell}` only; `fixed_dt`/`radius` float-equal asserted).
- **dt-fixed CFL surprise at medium** → D4 documents the CFL estimate (same `u_max` both grids) + the
  operator fallback (recorded in T3b if used).
- **Over-claiming grid convergence** (the two scientific over-claims flagged in review) → (a) the GCI is a
  `p=1..2` **band**, not a single p=2, with diffused-IB expected-lower-order stated (D3); (b) "purely
  spatial" is replaced by "spatial + IB-regularization refinement (isolated from temporal)" with the
  `dv = h·d_nn²` caveat (D4). Both compound to justify report-only.
- **Roadmap oracle laundering** → the T3 row's graded exit-criterion cell is **rewritten** (not just
  annotated) to report-only + T3a/T3b split, and a reconciliation-log entry records the oracle **relaxation**
  and defers the true observed-order (256³/grant) verdict — so T3 is not silently "done" on weaker evidence
  (task 4.1).
- **Auto-closing #40 or the new T3 issue** (a live bug in this repo) → task 6.2 forbids any closing keyword
  adjacent to `#40`/`#<T3>` **even negated**, suppresses the default `(closes #N)` title, and greps
  pre-merge; T3a is half the tier so it closes neither now.
