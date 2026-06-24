# Design — add-sphere-stress-cd

## Context

T1a (`docs/aerodynamics_validation/t1a-findings.md`) closed "can the corrected force be read back from the
IB markers?" with **no**, and identified an IB-marker-free route to Cd from the persisted Eulerian fields.
This change builds that route. The oracle design below was hardened after an adversarial OpenSpec review
that showed a single slip-side wake oracle leaves the **pressure and viscous terms untested** — and at
Re=100 the **pressure/form drag dominates** sphere Cd, so that gap would ship an untested bug straight into
the decisive H1/H2 experiment.

## Goals / non-goals

- **Goal**: a correct, FP64, deterministic, cluster-free-testable drag extractor that yields a single Cd
  per plotfile from Eulerian fields, with **every term of the integrand independently validated**, and
  decides H1 vs H2 on the real sphere runs.
- **Non-goal**: fixing the solver (H2 remediation), the axis convention (T2a), generalising to
  ellipsoid/wing (T2b). Keep the core general enough to reuse later, but spec/test only the sphere now.

## Decision 1 — control-volume momentum balance, in two right-sized stages

We measure drag from the **resolved far field**, not on the body surface. Body-surface stress
`∮_S(−pI+μ(∇u+∇uᵀ))·n dA` samples exactly where the diffuse-IB kernel smears the field (~1–2 cells), so it
would reproduce the solver's own possibly-deficient near-wall field and **cannot** separate H1 from H2.
The control-volume momentum balance over a box with faces in the resolved far field can:
`F_drag = −∮_{∂CV}[ ρ u(u·n) + p n − μ(∇u+∇uᵀ)·n ] dA` (outward `n`; leading `−` applied **once globally**;
`F_drag` = force on the body).

**The H1/H2 question is a ~2.4× discrimination (1.087 vs 0.45), not a <1% measurement.** So the work is
staged, minimal-first (OpenSpec guardrail; pre-deadline priority guard):

- **Stage 1 — single-plane wake survey (the decisive test).** Place the CV side faces in the freestream so
  the 6-face box collapses to one downstream plane: `F_d = ρ ∬_plane u_x(U∞−u_x) dA + ∬_plane (p∞−p) dA`
  on a plane at x ≈ 7–8 (outside the Re=100 recirculation bubble). ~10 lines on top of the adapter; `p` is
  reconstructed *within the plane* from `gradp`. The far-wake viscous flux through the plane is
  `O(μ·small)` and negligible for a 2.4× call. This makes the H1/H2 verdict.
- **Stage 2 — full 6-face CV box (confirmation, only if needed).** Run only if Stage 1 lands band-edge
  ambiguous, or as the published-rigor artifact for the apex-benchmarks ±5% oracle. Adds the per-face
  viscous-transpose term, the volumetric curl-free pressure reconstruction, convergence-order fitting, and
  the CV-size plateau. Its <1%-grade KATs (Decision 4, Stage-2 group) are insurance against a precision
  claim the verdict does not need — so they do not gate the verdict.

The unsteady term `ρ d/dt ∫_CV u dV` (`plt09900`+`plt10000`) is a **load-bearing steadiness gate**
(Decision 6) in both stages, not silently assumed 0.

## Decision 2 — pressure from `gradp`, with a verified curl-free reconstruction

`p` is not persisted; only `gradpx/y/z`. **`gradp` semantics verified** against the IAMReX fork
(`Projection.cpp:305`, `u_new += gradp/rho`): it is the **true pressure gradient `∇p`, unscaled**
(force-per-volume; with `ρ=1` it equals `∇p`), **cell-centered** (same centering as velocity,
`NS_setup.cpp`), i.e. the standard IAMR `Gp` — exactly what the integral needs. **Caveat:** the persisted
`gradp` is the **old-time** `Gradp_Type` state (lagged half a step). Immaterial at the steady sphere state
(Cd flat from t=40), but flagged for T2b's unsteady-wing reuse. Stage-1 reconstructs `p` only within the
survey plane; Stage-2 recovers a scalar `p` field from one reference cell via a fixed path (integrate
`gradpx` along x, then `gradpy` along y, then `gradpz` along z). Two correctness conditions, each
test-backed:

- **Additive-constant cancellation.** The box term `∮_{∂CV} p n dA` is invariant to the unknown seed
  constant `C` because `C ∮ n dA = 0` over a closed surface (discretely too: the signed face areas sum to
  zero). Test: add an arbitrary constant to `p` → identical drag (`assert_allclose`, not `==`).
- **Path-consistency (curl-free).** The reconstruction is path-independent only if the persisted `∇p` is
  a true gradient (`∇×∇p = 0` discretely). Test: reconstruct `p` via two different integration orders and
  assert agreement up to a constant; on real data, assert the discrete curl of `(gradpx,gradpy,gradpz)` is
  within tolerance before trusting `∮pn`.

## Decision 3 — module split for a cluster-free oracle

```
stress_integral.py
  control_volume_drag(u, v, w, p, *, mu, rho, dx, face_slices) -> {Fx, Fy, Fz, per_face, per_term}  # pure numpy
  cd_from_drag(Fx, *, rho, U, D) -> float                                                            # pure numpy
  recover_pressure_from_grad(gpx, gpy, gpz, dx) -> p                                                  # pure numpy
  extract_eulerian_box(plotfile_path, bounds) -> dict[str, np.ndarray]  (yt covering_grid, FP64)     # yt adapter
```

The **pure-numpy core** (incl. `recover_pressure_from_grad`) is tested entirely with hand-built fields —
**no yt, no plotfile, no Z:**. `control_volume_drag` returns a **per-face / per-term breakdown** (6 faces ×
{momentum, pressure, viscous}) so each term is independently assertable and a dominant unphysical side
term is visible on real data. The **yt adapter** is the only cluster-touching code, exercised by a
`requires_plotfile`-marked local test that skips in CI.

## Decision 4 — per-term known-answer oracles (each integrand term validated separately)

A single oracle that zeroes most terms is insufficient. Each term gets its own analytic KAT, plus a
combined convergence test. **All use `ρ ≠ 1` at least once** so a latent `ν`-for-`μ` substitution cannot
hide (here physically `μ = ρν = 0.01`, and with `ρ=1` `μ=ν` — a trap).

**Staging (right-sized to the 2.4× decision).** **Stage-1 KATs** (gate the verdict): KAT-momentum
(wake-survey closed form), KAT-pressure, null-field, sign, pressure-constant invariance — these validate
exactly the single-plane survey. **Stage-2 KATs** (only when the full 6-face box is built): KAT-viscous
(transpose + Poiseuille), convergence-order, anisotropic/off-center box, CV-size plateau — these are <1%
insurance for the full box and do **not** gate H1/H2.

- **KAT-momentum (divergence-free wake, side faces in the freestream).** A **divergence-free** velocity
  field: uniform freestream `U∞ x̂` plus a transverse-compact streamwise wake deficit that is x-uniform
  through the outlet, with `v,w` supplying the continuity closure so `div u = 0` pointwise (the test
  asserts `‖div u‖ ≈ 0` before trusting the oracle). **The CV side faces are placed in the freestream
  (`u = U∞` there)** — this is the condition under which the wake-survey identity holds (an adversarial
  numerical check confirmed the closed form requires the side flux to leave at streamwise velocity `U∞`;
  it is *not* a property of an arbitrary div-free field). Closed form: wake-survey drag
  `F_d = ρ ∬_outlet u_x(U∞ − u_x) dA`, which for a planar Gaussian deficit `A·exp(−r²/2σ²)` evaluates to
  `ρ π σ² A (2U∞ − A)` (using `∬exp(−r²/2σ²)dA = 2πσ²`, `∬exp(−r²/σ²)dA = πσ²`); the box spans ≥5σ
  transversely (tail < 0.1% ≪ 1% tol) **or** the test compares against the truncated analytic integral
  over the actual box. This **replaces** the earlier non-divergence-free slip-side Gaussian (a net mass
  sink) and **validates the side faces** carrying nonzero throughflow at `U∞`. The wake-survey integrand
  is independent of the box-sum discretization the core performs, so the test is non-circular.
- **KAT-pressure.** Uniform velocity (no momentum-flux variation, no viscous term) + a **linear pressure**
  `p = p0 + G·x`. Then drag = `−∮ p n_x dA = −G·L_x·A_x` (known); `∇p = (G,0,0)` is recovered exactly. This
  isolates the **pressure term and the `∇p` reconstruction** — the term that dominates real sphere Cd and
  was previously untested. (The field need not be a Navier–Stokes solution; this is a quadrature KAT.)
  *Verified exactly* by the round-2 numerical check (all four sub-claims).
- **KAT-viscous (two checks — a linear `u_x=Sy` is insufficient).** A single linear shear gives **zero
  net** box viscous force (any linear `u` ⇒ constant strain ⇒ `∇·τ = 0`) **and** does not exercise `∇uᵀ`
  (its transpose partner `∂v/∂x = 0`). So:
  - *(a) per-face / transpose check.* `u = (b·y, c·x, 0)`, `p=0`, `ρ≠1`: the `+y`-face streamwise traction
    is `μ(b+c)·A_face` — **wrong if the transpose term `c` is dropped**. Assert the per-face viscous
    contributions (each known and nonzero), not the net (which cancels).
  - *(b) nonzero-net check.* Plane Poiseuille `u_x = U0 + (g/2μ) y(H−y)`, `p=0`: `∇·τ = μ u_x'' = −g`, so
    the net streamwise viscous force is `−g·H·L_x·L_z` (known, nonzero). Run with `ρ≠1` (`μ=ρν`) so a
    `μ`-for-`ν` swap is caught.
- **KAT-combined + convergence.** Superpose the div-free wake + linear pressure with a known total drag;
  refine `dx` and assert the **fitted convergence order** `p ≈ 1–2` (slope of `log‖err‖` vs `log dx`),
  not merely "error decreases" — guarding against a constant-offset false pass. The **CV face planes are
  held fixed** as `dx` refines (do not snap faces to moving cell centers, or face-placement error injects
  a spurious `O(dx)`).
- **Structural KATs.** Null field → 0 (tol `≤ 1e-12·ρU∞²D²`); `cd_from_drag` known answer
  `Fx/(½ρU²·πD²/4)`; **anisotropic `dx`** (distinct dx,dy,dz) still matches; **off-center / asymmetric
  box**; **NaN in the CV raises** a clear error (never a silent NaN Cd); **sign invariant** (inlet face
  contributes the `+ρU∞²` inflow term with the correct sign).
- **Plateau-on-oracle.** Sweep CV face offsets on the **compact-deficit wake field** (uniform freestream
  outside a transverse-compact, x-uniform wake — so moving faces in the freestream / along the x-uniform
  wake does not change the integral) and assert `Fx` is flat (spread < 1%). A periodic field (e.g.
  Taylor–Green) has no plateau region and must **not** be used here. This pins the plateau property
  **cluster-free**, so a real-data non-plateau is attributable to physics (→ evidence toward H2), not a
  quadrature bug.

## Decision 5 — tolerances, fixed up front (CC-V2, never loosened)

- Each analytic KAT: relative error **< 1%** at the test resolution; convergence order fitted `≈ 1–2`.
- Literature validation: **±5%** of 1.087 → band **[1.033, 1.141]** (matches apex-benchmarks 1.087–1.10).
  H2's ≈0.45 is −59%, ~12× outside the band — a robust discriminator no plausible CV error bridges
  (blockage ≈0.79% ⇒ <2% correction; viscous-term omission would be wrong, so it is *kept*). The band is
  **fixed here and never widened** to force a pass.

## Decision 5b — the setup is a confined periodic array, not an isolated sphere (hypothesis H1′)

The literature oracle Cd=1.087 is for an **unbounded isolated** sphere. The committed run has **periodic
y,z** (sphere D=1 at pitch 10 D — an infinite square array) with only **5 D upstream** to the inflow. The
co-directional (all positive) setup biases relative to the isolated value:

- **Solid + wake blockage**, frontal area fraction `β = (π/4)/100 = 0.79%`, inertial (linear-in-β) regime
  at Re=100 → `+1.6%…+4%` (`1+kβ`, `k≈2–4`). **Note:** the Stokes array law `1+k·φ^{1/3}` (which would be
  ~tens of %) does **not** apply — at Re=100 the disturbance decays as `1/r²` (inertial), not `1/r`
  (Stokeslet).
- **Tight 5 D upstream** inflow → a further `+1%…+2%`.
- **Net expected offset ≈ +3%…+6%** → true Cd of *this* setup ≈ **1.12–1.15**.

**This does not confound H1 vs H2** (a +4% offset cannot masquerade as a −59% deficit; H2≈0.45 is ~12×
outside any target in 1.05–1.20). But it adds a third interpretation:

> **H1′ (setup-target offset):** extraction correct **and** field correct, but the true Cd of the
> confined/periodic run is ~1.12–1.15, not 1.087.

Handling (no pass-forcing loosening; CC-V2 intact):
- **1.087 ± 5% stays the H2 gate** (its only load-bearing job; H2 fails any reasonable target).
- For the **H1 interpretation**, also compare against the **confinement-corrected target**
  `1.087·(1+kβ) ≈ 1.10–1.15`, and report the **isolated-equivalent** Cd (divide out `1+kβ`). A field Cd in
  ~1.09–1.15 with isolated-equivalent ≈ 1.087±5% is **H1/H1′ (solver correct, offset explained)**, not
  "exact literature agreement."
- The **upper** H1-acceptance edge is widened to ~+8% (≈1.17) **with this β-based justification only** (so
  a correct confined result on the high tail is not mislabeled a failure); the **lower edge and the entire
  H2 logic are untouched**. The offset is documented in `t1a-findings.md §8` / `RESULTS.md`.

## Decision 6 — steadiness gate (reject the "third answer")

The unsteady term `ρ(∫_CV u dV|_{plt10000} − |_{plt09900})/dt` is computed from the two committed
plotfiles and **must be `< 5%` of |drag|** for the verdict to stand. At Re=100 the sphere wake is steady
and axisymmetric (below the ~Re 210 shedding onset), so this should hold; if it does not, the steady
assumption fails and the H1/H2 verdict is **void** (not silently reported). This makes the momentum-term
check load-bearing rather than a side note.

## Decision 7 — H1/H2 is recorded, not CI-asserted

The literature comparison **classifies** the outcome (within ±5% of 1.087 → H1; reproduces ≈0.45 → H2)
and **records** it as an analysis artifact. It is a `requires_plotfile`-marked local test that **skips in
CI**. On the H2 path the test is `xfail`/relaxed in the result commit so it is never a permanent local
red. This matches the decisive-experiment framing: the test's job is to *report* the verdict, not to fail
the build when reality is H2.

## Decision 8 — yt adapter: FP64, field-name, halo, and alignment contract

Feasibility is fine (a CV sub-region of a 4.2M-cell single-level dataset is ≲270 MB; the cost is the CIFS
read from Z:, seconds–minutes — no streaming needed). The adapter contract, with the gotchas the review
surfaced:

- **Field names are tuples.** AMReX/boxlib fields are `('boxlib','x_velocity')`, `('boxlib','gradpx')`,
  … — `gradpx/y/z`/`tracer` have **no bare-string alias**. Read via the `('boxlib',name)` tuple and
  **assert all six required fields are present** (fail loud if names drift between IAMReX versions).
- **Halo for face-normal derivatives.** The viscous term needs `∂u/∂n` **on** the CV faces → a difference
  straddling each face. The adapter **reads a box padded ≥1 cell (≥2 for centered 2nd-order) beyond the
  integration faces**, and the core's `face_slices` select the integration planes inside that padded read.
  (This is the most likely source of a wrong viscous term; it is a first-class requirement, not implicit.)
- **Edge alignment.** `covering_grid(level=0)` over a sub-region requires `left_edge`/`dims` on the
  integer cell lattice; the adapter computes them from `ds.domain_left_edge` + integer offsets and
  **returns the real cell-center coordinate arrays** so the core integrates over actual centers.
- **Unwrap units + FP64.** yt returns a `YTArray` in code units; the adapter calls `.to_ndarray()` (bare
  numpy) and **explicitly casts/asserts `float64`** (yt may return float32). Everything is dimensionless
  code units end-to-end (`μ=0.01`, `ρ=1`), so no unit conversion — but the YTArray must be unwrapped.
- **Single level.** Asserts `ds.index.max_level == 0` (covering grid exact, no interpolation) and that the
  run is an fp64 build.

The numpy core is FP64 throughout; all near-zero comparisons use `assert_allclose(atol=…)`, never `==`.

## Decision 9 — keep the magnitude tool from becoming a labeling trap (CC-V4, forward-looking)

`cd_from_drag(Fx, …)` and "drag = streamwise = x-projection" are a **sphere-stage convenience that assumes
freestream = +x**. Correct here (the sphere run is +x freestream, axisymmetric, so the axis convention —
issue #1 — cannot be exercised and Cd is convention-independent). But the core is **general** and will be
reused for the ellipsoid/wing in T2b, where the **post-T2a convention changes which axis is streamwise**.
To prevent this magnitude tool from re-introducing a #1-style *mislabeling* in the analysis layer (CC-V4
keeps the two defects separate), the core `control_volume_drag` returns the **full `(Fx,Fy,Fz)` vector**,
and the spec/docstring state that **T2b reuse MUST pass the freestream/streamwise axis explicitly — never
assume component 0**. This is a contract note only; no change to the sphere path.

## Risks

- **CV placement.** Too close → kernel smearing; too far → outflow/inflow BC contamination; the
  **downstream face must sit outside the Re=100 recirculation bubble** (~1–2 D behind the sphere, so
  x ≳ 7–8) where the field is smooth. The real-data sweep reports Cd **and per-face/per-term breakdown**
  vs CV size; the chosen bounds are documented. No plateau ⇒ evidence toward H2 (only trustworthy because
  the plateau test already passes on the analytic oracle).
- **Periodic y/z + finite width.** Side faces carry real transverse flux/shear (validated by KAT-momentum
  + KAT-viscous, which have nonzero side terms). Confirm the wake has not wrapped at the box width (it
  should not at Re=100 over a width of ~8–10).
- **`covering_grid` on AMR.** Sphere runs are `amr.max_level=0`; the adapter asserts this so the covering
  grid is exact (no interpolation).
