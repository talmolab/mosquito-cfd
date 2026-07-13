# Design — per-component van Veen force decomposition (T4)

## Context

We have the CFD **total** body-frame coefficients `CF_chord(t)`, `CF_normal(t)` (from
`reconstruct_wing_body_forces`, T2a) and the logged added-mass `ρ_f·SumU` (T2a/#36). The CFD gives only
the **total** force; the per-component split is never independently observed. T4 builds **van Veen's own
quasi-steady model** (translational + added-mass + Wagner) from its published coefficients, applies it to
**our** kinematics, and compares the model total (and components) to the CFD total. Reference model,
coefficients, and figures were extracted verbatim from van Veen 2022 (JFM 936 A3); see project memory
`van-veen-force-model-t4`. Citations at the end.

### What T4 can and cannot claim (honest framing — reconciles review C4)

Because both sides share the **same** kinematics and the **same** `F_ref`, the graded comparison tests
whether **van Veen's quasi-steady model reproduces our CFD total force** — a *consistency / plausibility*
result against the literature-standard model, **not** an independent validation of the per-component split
(which the CFD cannot provide). T4 therefore claims: our CFD wing force is **consistent with / validated
against van Veen's quasi-steady model at matched kinematics — in peak magnitude** (the CFD's phase *lead*
over the QS model is **reported** as the expected quasi-steady-vs-unsteady discrepancy, §D5) — and the #40
chord PARTIAL is **explained** (apples-to-oranges resolved) by van Veen's own tangential added-mass. It does
**not** claim to have independently measured the translational/AM/Wagner decomposition. The docs use
"validated against van Veen's quasi-steady model", not a bare "validated". The magnitude agreement is
moreover **grid-dominated** (the grid GCI is ~95 % of the tolerance budget, and the model↔CFD gap 0.13 is
smaller than the grid GCI 0.15 alone — round-3) — a legitimate *consistency* check, honestly hedged, not a
tight independent validation.

## D1 — The model (van Veen 2022, eqs 1.1–2.10 / 3.9–3.15; α in radians, body frame)

Van Veen's coefficients are defined **directly in the wing body frame** (x = chord/tangential,
z = normal), so the model needs **no rotation** — it is compared to our CFD body-frame `CF` directly. Each
component has its **own** reference scaling:

| component | normal (z) | tangential/chord (x) |
|---|---|---|
| translational | `½ρω²S_yy · 3.13·sinα` | `½ρω²S_yy · (A·α²+B·α+C)`, A=8.5e-5, B=−1.2e-2, C=0.41 |
| added-mass | `ρω̇S_cy · 0.96·sinα` | `ρω̇S_cy · 0.104·cosα` |
| Wagner | `½ρω·sign(ω̇)·√\|ω̇\|·S_WE · (−1.02)·sinα` | `0` |

`ω(t) = φ̇(t)`, `ω̇(t) = φ̈(t)`, `α(t)` from the analytic `wing_kinematics` mirror at our operating point.

**Added-mass moment is S_cy (fitted revised model), not S_τy (analytic).** The paper's *original*
potential-flow added mass (eqs 1.4–1.8) used the **thickness**-based `S_τy = ∫τ(y)y²dy` for the tangential
term. The paper's **revised, fitted** model (eqs 2.2/2.9, 3.7/3.13) deliberately re-bases the tangential
added mass on the **chord**-based `S_cy` and makes it **viscous** — this is the paper's stated novelty
("tangential added-mass scales with chord and is viscous, not thickness-based"). T4 uses the fitted model,
so **both** AM components use `S_cy` with the fitted coefficients (0.96 normal, 0.104 tangential). A code
comment records this so a future reader does not "correct" it back to S_τy. (Reconciles review B3/C1.)

## D2 — Normalization: the model is directly comparable to our CFD `CF` (same `F_ref`)

Our CFD `CF = F / F_ref` with `F_ref = ½ρω_ref²S_yy = 200.27` from `compute_force_reference`, where the
**reference** rate `ω_ref = 2π·f*·φ_amp_rad` is the *peak* stroke angular velocity (constant, = peak of
φ̇). Van Veen's translational normal uses the **instantaneous** `ω(t)²`. Dividing:

```
CF_transl,normal(t) = F_z,transl(t)/F_ref = (ω(t)/ω_ref)² · 3.13 · sinα(t)
```

For `φ(t)=φ_amp·sin(2πf*t)`: `ω(t)=φ̇=ω_ref·cos(2πf*t)`, so `ω(t)/ω_ref = cos(2πf*t)` (verified to machine
precision in review) and `CF_transl,normal(t) = cos²(2πf*t)·3.13·sinα(t)`. The AM and Wagner components
carry their **own** scalings (`ρω̇S_cy`, `½ρω√|ω̇|S_WE`); each is reconstructed as a **force** with its own
scaling, the three are summed, and the total (and each component) is divided by the **shared** `F_ref`.
Dimensional check (review PASS): `ρω̇S_cy/(½ρω_ref²S_yy)` and `½ρω√|ω̇|S_WE/(½ρω_ref²S_yy)` are both
dimensionless. **Decision:** reconstruct-force-then-divide (not coefficient-mixing); one normalization
convention; reuse `compute_force_reference` (CC-3), no inline `F_ref`.

## D3 — Area-moment integration convention (pinned — reconciles review B3)

All moments use **y measured from the stroke rotation (hinge) axis**, `∫₀^R … dy` over the wing span (van
Veen's convention: y from the axis). The wing root sits at a hinge offset `d ≈ 1.5` from the wing's
geometric centre, so `r_gyr ≈ 1.6985` **about the hinge** (matching the committed `R_GYRATION`). Using y
from the wing **centre** instead gives the *wrong* `r_gyr ≈ 0.74` / `S_yy ≈ 1.20` (the review's finding) —
the origin must be the hinge. Contract:

- **`S_yy = R_GYRATION²·area = 6.797`** — defined via the committed `R_GYRATION` (the *same* single source
  `compute_force_reference` uses for `F_ref`), **not** re-derived as a marker `∫c·y²dy` quadrature. (A raw
  chord-integral over the discrete markers gives ≈6.24 because the marker planform area ≠ the analytic
  elliptic area by ~7 %; we do **not** claim `S_yy` equals that quadrature — round-2 B3.) Documented "≈6.80".
- **`S_cy == S_yy`** — van Veen's `S_cy` has the *identical* integrand as `S_yy` (both `∫c·y²dy`), so it
  takes the same value `6.797`.
- **`S_WE = ∫√(c³y³)dy ≈ 3.98`**, **new**, computed by a hinge-origin marker quadrature over the committed
  planform (`y > 0` throughout, so the `√` is real) and **cross-checked against a genuinely independent
  analytic elliptic-planform quadrature** (`c(y) = c_max·√(1−((y−yc)/a)²)`, integrated on a fine 20k-point
  grid — a different integrator, not a re-binning): they agree to **~0.1 %** (both ≈3.978). This
  independent-quadrature claim applies to **`S_WE`, not `S_yy`**. A too-fine `nbins` (bins with ≤1 marker,
  which cannot resolve the chord) **raises** rather than silently under-estimating `S_WE`.
- `compute_wing_area_moments` is a **single shared** function; the existing inline `S_yy = r_gyr²·area`
  sites (`generate_validation_figures.py`, `test_force_surrogate_normalization.py`) are refactored to call
  it (CC-V4 — one moment code path, not two).

**`S_WE` is well-determined (round-3 correction):** the marker quadrature (3.978) and the independent
analytic elliptic quadrature (3.9785) agree to **~0.1 %**, so `S_WE` carries **no meaningful convention
uncertainty** (the round-2 "~9.6 %" estimate was not reproducible — it conflated `S_WE` with the *S_yy*
area convention). Its residual uncertainty (~0.1 % ⇒ ~0.001 on the normal peak — §D6) is negligible; the
tolerance budget is **grid-dominated**. `S_WE` is a **fixed geometric constant** of the pinned planform,
**not** a tunable knob (the `nbins` guard prevents silent drift — reconciles the review B2 reverse-fit
hazard). The distinct **S_yy** area choice (analytic-area 6.797 for `F_ref` consistency, vs a marker
quadrature ~6.24) is a documented convention, not an uncertainty — `S_yy` is fixed.

## D4 — Sign convention (the `ω̇`/half-stroke subtlety)

Fixed by van Veen's definitions + our `R(t)`, derived **analytically**, **never** by matching CFD:
- Translational ∝ `ω²·sinα`: `ω²` is sign-blind; stroke-direction reversal is carried by the body-frame
  `R(t)` (shared with the CFD `CF`) and by `sinα(t)`. Structurally airtight for the normal (review PASS).
- Added-mass ∝ `ω̇`: keeps its sign. Wagner ∝ `sign(ω̇)·√|ω̇|` (van Veen eq 3.15/4.1), finite for ω̇<0.

A **kinematic** test (tasks §1) pins it: at mid-downstroke and mid-upstroke (opposite φ̇, opposite α) the
model normal-component sign equals the hand-computed `sign(sinα(t))`/`R(t)`-frame expectation and reverses
between half-strokes — asserted against **hand-computed literals**, never the CFD series.

**Modeling caveat (review C3):** van Veen fitted on *revolving* wings (ω ≈ const, one sign); applying the
fit quasi-steadily through stroke reversal (where ω→0 and AM/Wagner dominate) is an approximation. Stated
as a caveat in the docs, not presented as exact. It is not a hidden reverse-fit knob (the reduction is
exact algebra; the sign is pinned kinematically).

## D5 — Graded vs reported (reconciles review B1, B2, C4 + the round-2 phase finding)

T3b established: **normal grid-settled** (coarse↔medium −11.7 %, GCI 0.05–0.15); **chord grid-unconverged**
(−66.5 %, GCI 0.28–0.83, → #50). Measured on the committed data (round-2 review): the QS model reproduces
the CFD normal peak **magnitude** (model 2.48 vs CFD 2.61, within the grid+model band) but the CFD peak
**leads** the model in **phase** by ~0.058 cycle. This dictates what is *gated* vs *reported*:

- **Gated — "consistent with van Veen's QS model in peak magnitude":**
  - **G1 — normal peak MAGNITUDE** (the robust lever): model-total peak `|CF_normal|` ≈ CFD peak
    `|CF_normal|` within `T4_NORMAL_MAG_TOL`. This is `S_WE`-**insensitive** (the `S_WE` uncertainty moves
    the normal peak by only ~0.001, since the marker and analytic `S_WE` agree to ~0.1 % — round-3), so it is
    not a tuned quantity, and the normal is grid-settled, so a genuine agreement is expected and
    load-bearing. **This is the primary graded lever.**
  - **G3 — decomposition closure**: `model_total ≡ transl + AM + Wagner` (chord & normal) to float tol.
  - The existing lab-frame `VAN_VEEN_BAND` floor stays graded (unchanged).
- **Reported (not gated):**
  - **Normal peak PHASE**: the CFD peak **leads** the QS model by ~0.058 cycle — reported as the **expected
    quasi-steady-vs-unsteady phase discrepancy** (the QS model omits the Wagner wake-memory / added-mass
    circulatory *history* that shifts the CFD peak), and **triply confounded** by grid non-convergence + the
    single-wingbeat impulsive-start transient (a coarse, non-limit-cycle window). A physics-honest phase
    tolerance would be ~0.02, which the confounded gap exceeds; **widening a phase gate to fit the measured
    ~0.06 would be reverse-fitting** (CC-V2). So the measured phase gap is **reported with its confounds**,
    not gated. A one-line roadmap reconciliation-log note records this scoped exception (a
    confounded-measurement honesty call, **not** a loosened tolerance).
  - **Normal curve RMSE**: reported (inflated by the phase offset above), not gated.
  - **G2 — translational-chord self-consistency (known-answer, NOT an identity to 0.30):** the model
    translational-tangential **peak** equals the value **computed from the pinned polynomial** at our α
    (`½ρω²S_yy·(A·α²+B·α+C)` ⇒ CF peak ≈ **0.42** at α=−45°, |ω|=ω_ref — pinned as a known-answer literal),
    which is **O(0.4) ≪ the CFD total 0.92** — the apples-to-oranges resolution. Van Veen's *reported* ~0.3
    (a Fig-4b eyeball at his mosquito operating point) is the same order; the 0.42-vs-0.3 difference is the
    operating-point/α-range, **reported, not graded**. **We do NOT assert the peak equals 0.30 within a
    tolerance** (that both fails numerically and is circular — review B1). `VAN_VEEN_CF_TARGETS` is **not**
    reused as a G2 gate.
  - **R1 — chord total curve:** model-total `CF_chord(t)` (≈0.43 peak) vs CFD `CF_chord(t)`, reported
    **with the coarse↔medium chord GCI band** `T4_CHORD_GCI_BAND`; reports that the CFD chord **converges
    toward the model** under refinement (0.92 coarse → 0.554 medium → model ≈0.43, monotone — round-2
    confirmed) — the real chord resolution; the tight verdict is deferred to **#50**.
  - **R2 — per-component shares** of chord and normal.

## D6 — Tolerances: pinned up front from sourced quantities, and the sourcing is TESTED (reconciles review B2 + TDD CC-V2)

Only **one** graded magnitude tolerance survives (phase and RMSE are *reported*, §D5). It is a **named
constant** with a not-loosened guard, derived from independent sources **before** the committed-run result,
AND a test (`test_tolerances_derive_from_sourced_quantities`) recomputes it from its inputs and asserts the
pinned value sits just above the derived floor — so the sourcing is enforceable, not aspirational.

| constant | value | source (quadrature of independent errors, all recomputed in the test) |
|---|---|---|
| `T4_NORMAL_MAG_TOL` | 0.16 | normal grid GCI (T3b `gci_p1 = 0.146`, the **dominant** term, >90 % of the budget) ⊕ normal coefficient-CI band (recomputed ≈0.006) ⊕ **`S_WE` geometric uncertainty** (marker-vs-analytic `S_WE` agree to ~0.1 % ⇒ ~0.001 on the peak — negligible) → √(0.146²+0.006²+0.001²) ≈ **0.147** → rounded up to **0.16**. The relative gap (model 2.48 vs CFD 2.61 ⇒ ~0.05) passes with margin; a test asserts the floor is **grid-dominated** (`grid_rel > 0.9·floor`). |
| `T4_CHORD_GCI_BAND` | `(chord gci_p2, gci_p1)` | **reported only**; asserted **equal** to the committed T3b chord GCI via the reused `wing_grid_convergence_from_body_forces` (not a re-typed literal) |

### Why `T4_NORMAL_MAG_TOL` is a RELATIVE tolerance (implementation deviation — reconcile step)

Discovered during implementation: the grid-GCI term (the *dominant* budget term) is a **relative**
(fractional) uncertainty — `gci_p1 = safety·|Δ|/(rᵖ−1)` is normalized by the medium value. To combine it in
quadrature with the coefficient-CI and `S_WE` terms (also relative), and to *be* a single meaningful
number, `T4_NORMAL_MAG_TOL` is therefore a **relative peak tolerance**: the grade is
`|model_peak − cfd_peak| / cfd_peak ≤ T4_NORMAL_MAG_TOL`. So the committed-run "gap 0.13" (absolute CF, model
2.48 vs CFD 2.61) is a **relative gap of ~0.05** (0.13/2.61) — comfortably inside `0.16`. The sourcing test
recomputes the floor `√(gci_p1² + coeff_ci² + swe²) ≈ 0.147` (all relative) and asserts
`floor ≤ 0.16 ≤ floor + 0.03`. (An *absolute* tolerance would have had to convert the relative grid GCI by
×peak ≈ 0.38 and could not be `0.16`; relative is the units-consistent choice.) The recomputed coeff/swe
terms (~0.006/~0.001) are negligible against the grid term (0.146), so the floor is `≈0.147`
(grid-dominated, a test asserts `grid_rel > 0.9·floor`) and `0.16` sits just above it — honest, not
reverse-fit.

The reported (non-gated) diagnostics — normal peak **phase** gap, curve **RMSE**, translational-chord
known-answer (≈0.42), chord total + grid band — carry **no** pass/fail tolerance (a reported number cannot
be reverse-fit). `S_WE` itself is **not** a tolerance — it is a pinned geometric constant cross-checked
against an independent quadrature (§D3); its residual uncertainty is the small `~0.001` term above,
**recomputed** in the sourcing test from the marker-vs-analytic `S_WE` difference (not a typed literal —
TDD round-2). **Discipline:** the magnitude grader is proven on synthetic fixtures to *pass within and fail
outside* `T4_NORMAL_MAG_TOL` (both directions); a widened tolerance flips a not-loosened test.

## D7 — Reuse map (CC-V4, no re-derivation)

| need | reused symbol | module |
|---|---|---|
| CFD body-frame `CF_chord/CF_normal(t)` | `reconstruct_wing_body_forces`, `body_frame_coefficients` | `benchmarks/flapping_wing.py` |
| shared `F_ref = 200.27` | `compute_force_reference` | `force_surrogate/normalization.py` |
| kinematics `φ(t), α(t)` | `euler_angles` | `benchmarks/wing_kinematics.py` |
| coarse↔medium chord GCI (for `T4_CHORD_GCI_BAND` + R1) | `wing_grid_convergence_from_body_forces` | `benchmarks/wing_convergence.py` |
| added-mass magnitude `ρ_f·SumU` (cross-check) | `added_mass_force` | `benchmarks/flapping_wing.py` |
| steady window | `STEADY_WINDOW_T0`, `_steady_mask` | `benchmarks/flapping_wing.py` |
| constants (SPAN, CHORD, RHO, R_GYRATION, VALIDATED_*) | — | `force_surrogate/constants.py` |

New code: van Veen's three-component model, the shared `compute_wing_area_moments` (incl. `S_WE`), the
`stroke_rate` derivatives, and the decomposition grader/figure. (`VAN_VEEN_CF_TARGETS` is not reused as a
G2 gate — §D5.)

## D8 — Figure and the mislabelled-figures correction

`fig_force_decomposition` overlays, for chord and normal separately, the model translational / added-mass /
Wagner / total curves against the CFD total over the steady window — **van Veen's model replotted at our
operating point** (cluster-free). The docs correct the "Fig 3–4" label everywhere it appears (roadmap
lines 74 & 97, `RESULTS.md`, `figures/README.md`, `docs/coordinate-convention.md`,
`flapping_wing.py` docstring/comment): van Veen **Fig 3** = fruit-fly force vs stroke-acceleration;
**Fig 4** = fruit-fly coefficient-vs-α polars (the fits we build the model from — RESULTS' existing "Fig 4"
translational-target cites are **correct and kept**); the time-resolved **mosquito** component curves are
**Fig 13(c,d,…)**. We do **not** overlay Fig 13 (its measured low-amplitude Anopheles kinematics ≠ our
analytic φ=70° stroke). Roadmap line 74's "**digitized curve**" is also corrected — we replot van Veen's
**model**, no digitization.

## D9 — Erratum (load-bearing coefficient check — reconciles review C1)

The paper's Data-availability DOI is malformed in print (`10.1017/jfm.2019`); the erratum **JFM 956 E1
(2023)** is characterised as a "publisher-introduced" (production) correction — most likely that DOI, not
the fitted coefficients. Because the graded G1 magnitude / the AM coefficient 0.96 (fitted, vs analytic
π/4=0.785) are load-bearing, the erratum check is **blocking-if-unresolved**, not a formality: task §9 confirms the pinned
coefficients against JFM 956 E1 and records the verdict as a **testable provenance literal**
(`ERRATUM_CHECKED = "JFM 956 E1 (2023): no coefficient change"`), asserted in a test. If the erratum *does*
touch a coefficient, the pinned constant + CI are updated and the deviation recorded here.

## References

- van Veen, van Leeuwen, van Oudheusden & Muijres (2022), "The unsteady aerodynamics of insect wings with
  rotational stroke accelerations, a systematic numerical study," *J. Fluid Mech.* **936**, A3, DOI
  10.1017/jfm.2022.31 (CC BY; OA mirror edepot.wur.nl/566000). Erratum: *J. Fluid Mech.* **956**, E1 (2023).
- Muijres et al. (2017a), *J. Exp. Biol.* **220**, 3751 — the measured Anopheles kinematics van Veen's
  mosquito case uses (context for the kinematics caveat; not a data input here).
