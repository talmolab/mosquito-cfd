# T1a findings — diffused-IB force reconstruction & plotfile recoverability

**Tier:** T1a (diagnosis only) · **Tracking issue:** [#26](https://github.com/talmolab/mosquito-cfd/issues/26)
· **Roadmap:** [`roadmap.md`](roadmap.md) · **Bounds:** analysis-only, pre-June-30 OK (background track).

**Source of truth:** `talmolab/IAMReX @ 7ece065d` (`Source/DiffusedIB.{cpp,H}`), verified against the
committed sphere runs on `Z:\users\eberrigan\mosquito-cfd-benchmarks\{flow_past_sphere_coarse,flow_past_sphere_10k}`
(`flow_past_sphere_coarse` = **coarse** 128×64×64; `flow_past_sphere_10k` = **medium** 256×128×128).

---

## TL;DR

- **Field mapping (numerically verified):** plotfile particle `real_comp0..8` =
  `U,V,W_Marker` (interpolated fluid velocity) · `Fx,Fy,Fz_Marker` (**dv-weighted** Lagrangian force) ·
  `Mx,My,Mz_Marker` (dv-weighted moment), in `P_ATTR` enum order.
- **RESULTS.md's hypothesis is wrong:** the deficit is **not** a missing kernel/`dv` weight. `dv` is
  *already* applied in-solver (`ForceSpreading_cic`, `fxP *= dv`), so the current "raw sum of comp3" is
  already a dv-weighted force. Confirmed by a numerical identity (§2).
- **Correct reconstruction** (IAMReX's own 6-DOF balance):
  `F_hydro = ρ_f · [ (ΣU_pvf,new − ΣU_pvf,old)/dt − F_ib ]`, where
  `F_ib = Σ_markers (dv·Fx_Marker)` **accumulated over all `loop_ns` sub-iterations**.
  For a **fixed sphere at steady state** the momentum term → 0, so `F_drag = −ρ_f·F_ib`.
- **Answer to the exit question — split by route (net: lean NO, but with a re-run-free test outstanding):**
  - **Diffused-IB force route (issue #26's literal framing) — NO.** The plotfile persists only the
    **last** multidirect-forcing sub-iteration's force increment (markers are reset every sub-iteration);
    the accumulated `F_ib` and the solver's `IB_Particle_*.csv` ground truth are **not** persisted
    anywhere in the run dirs. The corrected force *as IAMReX computes it* cannot be reconstructed.
  - **Independent field route (control-volume momentum / surface-stress integral) — computable from
    committed fields with NO re-run, in principle, but not yet executed.** Cd is a physical quantity and
    can be obtained from the persisted Eulerian `x/y/z_velocity` + `gradpx/y/z` (with known `μ=0.01`,
    `ρ=1`) **without touching the IB markers**. This route is the **decisive H1-vs-H2 test** (force-
    extraction bug vs. flow-field deficit, §4.b–c) and **must be T1b's first action** because it is cheap
    and re-run-free.
- **Consequence (per roadmap priority guard):** the binary that sets T1b's path resolves only **after**
  the re-run-free CV cross-check (§4.b–c). If it recovers Cd≈1.087, T1b stays **analysis-only / pre-deadline
  eligible**; if it reproduces ≈0.45, the deficit is in the solver's flow field → **solver-level fix +
  re-run → defers post-submission, co-lands with T2a.** Plan for the re-run branch but do not commit to it
  until the cross-check is run.

---

## 1. How the diffused-IB force is built (call path)

Per IB-coupled timestep, `mParticle::InteractWithEuler` (`DiffusedIB.cpp:350`) runs a multidirect
(iterative) forcing loop `loop_ns` times. Each sub-iteration, **per marker**:

1. `ResetLargrangianPoints` (`:912`) — zeroes `U..W_Marker`, `Fx..Fz_Marker`, `Mx..Mz_Marker`.
2. `VelocityInterpolation` (`:729`) — `U_Marker ← ` fluid velocity at the marker (from the *current,
   already-corrected* Euler field).
3. `ComputeLagrangianForce` (`:1179`) — `Fx_Marker = (Ub + (ω×r)_x − U_Marker)/dt` (units: accel; **no
   `dv` yet**). For the fixed sphere `Ub = ω = 0` ⇒ `Fx_Marker = −U_Marker/dt`.
4. `ForceSpreading` → `ForceSpreading_cic` (`:769`) — **`fxP *= dv`** in place (`:795`), recomputes the
   moment from the dv-weighted force, then spreads to the Euler grid via the regularized delta.
5. Reduction (`:860`) sums the now-dv-weighted `Fx_Marker` → `kernel.ib_force`; this is
   **accumulated across sub-iterations** (`kernel.ib_force += ib_force`, `:392`).
6. `VelocityCorrection` (`:1216`) applies the spread force to the Euler field before the next
   sub-iteration re-interpolates.

**Two facts that drive everything below:**

- After the loop, the **stored** `Fx_Marker` (→ plotfile `comp3`) holds **only the final
  sub-iteration's** dv-weighted increment — every sub-iteration `Reset`s it. The accumulated total lives
  **only** in the scalar `kernel.ib_force`.
- `kernel.ib_force` (and the momentum term) are written **only** to `IB_Particle_<id>.csv`
  (`WriteIBForceAndMoment`, `:1234`) — never into the plotfile particle stream.

### The complete hydrodynamic force

The full force IAMReX uses is its 6-DOF balance (`UpdateParticles`, `:1077`, non-Uhlmann):

```
m·dv/dt = ρ_f·(ΣU_pvf,new − ΣU_pvf,old)/dt  −  ρ_f·F_ib  + buoyancy + collision
          └─ internal-momentum (added-mass) term ─┘   └ spread IB force ┘
```

⇒ hydrodynamic force on the body `F_hydro = ρ_f·[ (ΣU_pvf,new − ΣU_pvf,old)/dt − F_ib ]`.
`ΣU_pvf` is the volume-fraction-weighted fluid velocity integrated over the particle
(`CalculateSumU_cir`). For a **fixed sphere at steady state** the momentum term is ≈ 0 (Cd is flat from
t=40, `flow_past_sphere/RESULTS.md`), so `F_drag = −ρ_f·F_ib`.

---

## 2. Field mapping — verified by a numerical identity

`plt10000/particles/Header` (both grids) lists **9** double real components, `real_comp0..8`, in
`P_ATTR` order (`DiffusedIB.H:37`):

| comp | `P_ATTR` | meaning | dv applied? |
|---|---|---|---|
| 0,1,2 | `U,V,W_Marker` | interpolated fluid velocity at marker (final sub-iter) | n/a |
| 3,4,5 | `Fx,Fy,Fz_Marker` | Lagrangian force/marker, **last sub-iter only** | **yes** (`:795`) |
| 6,7,8 | `Mx,My,Mz_Marker` | moment of the dv-weighted force | yes |

**Cross-check (medium grid, from RESULTS.md dumps):** for the fixed sphere
`Σcomp3 = −(dv/dt)·Σcomp0`. With `r=0.5`, `h = 20/256 = 0.078125`, `Ml = 515`:

```
dv = [(r+0.5h)³ − (r−0.5h)³]·4π/(3·Ml) = 4.78e-4
Σcomp3_pred = −(dv/dt)·Σcomp0 = −(4.78e-4/0.01)·3.69 = −0.176   (RESULTS dump: −0.176 ✓)
Cd = −Σcomp3 / (½ρU²·πr²) = 0.176 / 0.3927 = 0.448             (RESULTS: 0.448 ✓)
```

The prediction matches the RESULTS.md dumps to the reported 3-figure precision. This **confirms** comp3 =
dv-weighted force (so the "missing dv" hypothesis is false), confirms the comp0↔comp3 pairing, and
confirms `Ml=515` ⇒ `rd=0`.

---

## 3. Run configuration (from committed `job_info` + the deck)

`ns.do_diffused_ib=1`, `ns.fluid_rho=1.0`, `ns.fixed_dt=0.01`, `ns.init_iter=0`;
`particle_inputs`: `radius=0.5`, `rho=1.0`, `velocity=0`, `omega=0`, `TL=RL=0` (**fixed**, no 6-DOF
motion). `RD` and `LOOP_NS` are **not** set in the deck or `job_info` ⇒ C++ defaults
**`rd=0.0`, `loop_ns=2`** (`DiffusedIB.cpp:48,55`). So **multidirect forcing with 2 sub-iterations is
active.**

> Note: `ns.init_iter=0` is the same flag implicated in the flapping-wing `x_velocity=0` plotfile
> defect. Here it did **not** zero the sphere's Eulerian velocity (the velocity figure renders), but it
> is flagged for T1b/T2b awareness.

---

## 4. Recoverability — by route

### 4.a Why the *diffused-IB force* (IAMReX's own number) is NOT recoverable from `plt10000`

1. **Multidirect accumulation is lost.** With `loop_ns=2`, `Σcomp3` = the **final** sub-iteration's
   increment only (markers reset each sub-iteration, `:377`). The physically intended IB force is the
   **accumulated** `kernel.ib_force` (`:392`), which is **not** in any plotfile field. So `Σcomp3 = 0.448`
   units is a single sub-iteration's residual forcing, not the solver's own total — using it as "the
   force" is methodologically wrong whenever `loop_ns>1`.
2. **Ground truth was not preserved.** `kernel.ib_force` and the momentum term are written only to
   `IB_Particle_<id>.csv` (`WriteIBForceAndMoment`, a *relative* filename → lands in the solver's cwd,
   `/opt/cfd/IAMReX/Tutorials/FlowPastSphere` per the RESULTS.md run commands, **not** `/workspace`). A
   search of both run dirs finds **no** `IB_Particle*.csv` / no `*.csv` — the CSV ground truth was not
   preserved (discarded with the container).
3. **The added-mass term cannot supply the 2.4×.** It *is* in principle reconstructable from the
   persisted Eulerian velocity + the analytic sphere `pvf` across `plt09900`/`plt10000` (both committed),
   but at steady state it is ≈ 0 — it cannot explain a 2.43× deficit.
4. **Alternative reading is also solver-level.** Even if one treated `Σcomp3` as the solver's full IB
   force (i.e. if `loop_ns` effectively =1), the remaining ≈2.4× gap would be **intrinsic** to IAMReX's
   diffuse-IB force computation (`dv`/`rd`/regularization calibration, or the documented direct-forcing
   force underestimate). That too is fixable only in the solver + a re-run.

So the IB-marker route to IAMReX's *own* corrected force number is blocked: the accumulated `F_ib` is not
persisted, and the CSV that held it is gone.

### 4.b Independent route that IS re-run-free: control-volume momentum / surface-stress integral

`Cd` is a physical quantity, not IAMReX's bookkeeping. There is a classical, **IB-marker-free** route to
it that uses only persisted Eulerian fields and **needs no re-run**:

- A **control-volume momentum balance** over a box enclosing the sphere:
  `F_drag = −∮_∂CV [ ρ u(u·n) + p n − μ(∇u+∇uᵀ)·n ] dA`, using committed
  `x/y/z_velocity` (momentum flux + viscous stress) and `gradpx/y/z` for the pressure term. Pressure `p`
  is recoverable from `∇p` up to an additive constant that **cancels** in the closed-surface integral
  `∮ p n dA`, so `p` itself need not be persisted. `μ = ns.vel_visc_coef = 0.01`, `ρ = 1` (both in
  `job_info`). The unsteady term needs `plt09900` + `plt10000` (both committed) and is ≈ 0 at steady
  state. Placing `∂CV` several cells outside the regularization support avoids the smeared near-boundary
  field.

This route is computable **in principle from the committed fields with no re-run**. It was **not executed
here** (it is new quadrature code, deferred to T1b per the priority guard), but it is the decisive next
experiment — see §4.c.

### 4.c The two hypotheses, and the one cheap test that separates them

The 2.4× deficit is one of:

- **H1 — force-extraction bug.** The resolved flow field is essentially correct; only IAMReX's IB-force
  *bookkeeping* (multidirect accumulation lost to the plotfile) under-reports. ⇒ A CV/stress integral on
  the committed fields would give **≈ 1.087** ⇒ corrected Cd **is** recoverable with no re-run ⇒ T1b
  analysis-only.
- **H2 — flow-field deficit.** The diffuse-IB no-slip enforcement is too weak / over-smeared, so the
  *velocity field itself* under-produces drag. ⇒ The CV integral would also give **≈ 0.45** ⇒ a
  **solver-level fix + re-run** is required ⇒ T1b defers post-submission, co-lands with T2a.

Both H1 and H2 are consistent with everything observed so far (incl. the away-from-literature grid trend,
which fits an unconverged diffuse boundary layer **or** a resolution-dependent multidirect split). **The
§4.b CV integral is the single re-run-free computation that distinguishes them**, and it is therefore
T1b's mandatory first step before any re-run is scheduled.

---

## 5. Field-availability check (per grid) — the issue #26 verification task

Read directly from the committed `plt10000/particles/Header`:

| Grid | `amr.n_cell` | real comps persisted | markers | comp0..8 present? | accumulated `F_ib` present? | `IB_Particle.csv` present? |
|---|---|---|---|---|---|---|
| Coarse | 128×64×64 | 9 (`real_comp0..8`) | 129 | ✅ yes | ❌ no | ❌ no |
| Medium | 256×128×128 | 9 (`real_comp0..8`) | 515 | ✅ yes | ❌ no | ❌ no |

The **persisted** fields are present and identical in structure on both grids. The fields the
**IB-marker reconstruction requires** (accumulated multidirect `F_ib`; or the solver's `IB_Particle`
force history) are **absent** on both. The fields the **independent CV/stress route requires** (§4.b —
`x/y/z_velocity`, `gradpx/y/z`; plus `plt09900` for the unsteady term) **are present** on both grids —
which is why that route, not the IB-marker route, is the re-run-free path worth testing.

---

## 6. Reconstruction spec (for T1b)

**Steady fixed-body drag (target form):** `Cd = −ρ_f · F_ib,x / (½ ρ_f U² · A)`, `A = πr²`, with
`F_ib,x = Σ_markers dv · (U_b,x + (ω×r)_x − U_Marker,x) / dt` **summed over all `loop_ns`
sub-iterations**. The general (moving/unsteady) form adds the momentum term
`+ρ_f(ΣU_pvf,new − ΣU_pvf,old)/dt`.

**T1b's first step is the re-run-free CV cross-check, not a re-run.** Only if it reproduces ≈0.45 (H2)
does T1b need a solver path. Options to scope during T1b's `/new-feature`:

- **(0) — re-run-free, do this first.** Implement the **§4.b control-volume momentum / surface-stress
  integral** in `mosquito_cfd.benchmarks`, reading committed `plt10000` (+ `plt09900`) Eulerian fields.
  Outcome decides everything: ≈1.087 ⇒ **H1, analysis-only, pre-deadline eligible, done**; ≈0.45 ⇒ **H2**,
  proceed to a solver option below.
- **(a)** Make IAMReX **emit** the per-marker *accumulated* dv-weighted force (don't reset, or write
  `kernel.ib_force` into a runtime real comp) so future plotfiles are self-sufficient; **or**
- **(b)** **persist `IB_Particle_<id>.csv`** to `/workspace` and read `Fx,Fy,Fz` directly (simplest;
  re-run only); **or**
- **(c)** re-run with **`LOOP_NS=1`** *and* validate that single-pass `Σcomp3` recovers Cd — only if a
  calibration check shows the single-pass force is physically complete (it likely is **not**; see §4.a item 4).

Options (a)–(c) require a re-run ⇒ **post-submission, co-land with T2a** (roadmap priority guard + T1→T2
contingency). Option (0) is analysis-only. Sphere **Cd = 1.087 ± tol** is T1b's TDD oracle throughout.

---

## 7. Decision

> **Is the corrected sphere Cd computable from the committed `plt10000` fields, with no re-run?**
> **Split by route — net: not via the IB markers, but a re-run-free path remains untested.**
> - **Diffused-IB force reconstruction (issue #26's literal subject): NO** — the accumulated `F_ib` is not
>   persisted (only the last multidirect increment is) and the `IB_Particle` CSV was discarded.
> - **Independent CV/surface-stress integral: YES in principle, from committed fields, with no re-run** —
>   but **not yet executed**, and its *result* (≈1.087 vs ≈0.45) is what actually fixes T1b's path.

**Path:** T1b's **first action is the re-run-free CV cross-check (§4.b, option 0)** — analysis-only and
pre-deadline-eligible. It is the single computation that distinguishes a force-extraction bug (H1 → T1b
stays analysis-only) from a flow-field deficit (H2 → solver fix + re-run, **defers post-submission,
co-lands with T2a**, roadmap §"Contingency"/CC-V1). **Do not schedule a re-run until that cross-check has
been run.** The diagnosis itself (this document) lands pre-deadline, as the guard allows.

> Earlier framing note: the IB-marker route alone would have read as a flat "NO → re-run". The CV route
> (surfaced in adversarial review) is the correction — the honest answer is conditional on a cheap test
> that is itself within the pre-deadline analysis-only budget.

**Maintainer consult:** not required — the source path is unambiguous and the field mapping is confirmed
by a numerical identity to the reported precision (§2). Upstream issue
[`ruohai0925/IAMReX#59`](https://github.com/ruohai0925/IAMReX/issues/59) remains the contact point if
T1b's solver change needs upstream coordination (it concerns FP32/CUDA builds, not force extraction).

**Downstream (record, do not act here):** T1b will confirm the Track-B corpus is mis-scaled by ≈ the same
factor (re-caption, never regenerate — CC-V6) and supersede the "~60% low Cd / under investigation" claim
across `add-apex-benchmarking` + `benchmarks/METHODS.md` (CC-V5).

---

## 8. Stage-1 result (T1b) — H1 confirmed, no re-run

The re-run-free cross-check (§4.b) was implemented (OpenSpec `add-sphere-stress-cd`,
`src/mosquito_cfd/benchmarks/stress_integral.py`) and run on the committed `plt10000`. **One correction
to §4.b:** the single-plane wake survey is invalid here because the run is **periodic in y,z** — with
blockage the bypass flow accelerates above `U∞`, so the "side faces in the freestream" premise fails
(it gave negative, non-plateau Cd). The correct measure is a **two-plane periodic-duct momentum balance**:
the periodic lateral faces cancel exactly, leaving
`F_drag = ρ(∫_{x1}u_x²dA − ∫_{x2}u_x²dA) − ∫_V (∂p/∂x)dV` — read directly from `u_x` on an inlet/outlet
plane and `gradpx` between them (no pressure reconstruction; the constant cancels). `gradp` is confirmed
the true unscaled `∇p` (IAMReX `Projection.cpp:305`). The streamwise **viscous** flux on the two planes is
neglected — estimated **~1–5% of the drag** at Re=100, so the absolute Cd carries an error bar of that
order; this is far below the 2.4× H1/H2 gap but means the trailing digits below are *indicative*, not
measured to <1%.

**Result (x_inlet=2, x_outlet=8; plane-insensitive plateau):**

| Grid | CV Cd | vs literature 1.087 |
|---|---|---|
| Coarse 128×64×64 | **1.342** | +23% |
| Medium 256×128×128 | **1.183** | +8.9% |
| Richardson extrap. (order unmeasured: p=1 → 1.025, p=2 → 1.131) | **≈1.03–1.13** | **−6% … +4%** |

Only two grids exist, so the convergence order `p` is *assumed*, not fitted — the extrapolation is a
**range** `1.03–1.13` that brackets literature within ~±6%. Dividing out the confinement offset
(`1+kβ`, β=0.79%, k≈2–4) shifts the isolated-equivalent down by ~2–3%, i.e. into `≈1.00–1.11`.

**Steadiness gate (design Decision 6, implemented).** `|unsteady momentum term| / |drag|` between
`plt09900` and `plt10000` is **≈ 0.00** (the flow is fully steady at Re=100, below the ~Re 210 shedding
onset), so the steady balance is valid and the verdict stands (not merely assumed).

**Verdict — H1 (with an H1′ confinement offset).** The resolved flow field carries Cd ≈ 1.1 (grid-
converged ± a few %, confinement-corrected toward ~1.0–1.1) — **not** the broken ≈0.45. The marker
extractor under-reported by **2.64×** (`1.183/0.448`), confirming the deficit was a **force-extraction
bug**, not a flow-field deficit (H2 is decisively excluded by a ~12× margin no error budget bridges). The
grid pair **converges toward literature** (1.342 → 1.183, from above); the residual is the confined-array
setup offset (the run is a transversely-periodic array at pitch 10 D) plus incomplete grid convergence.

> **Answer to issue #26's question, now settled by execution:** the corrected sphere Cd **is** computable
> from the committed plotfile fields **with no re-run** — via the field-based CV balance, not the IB
> markers. T1b is **analysis-only** (the "Yes" branch); no solver re-run is needed.

**Carried to T2b (not blocking):** to land the literal `1.087 ± 5%` on a single grid, T2b should refine
the grid and/or apply the confinement correction (or re-run with non-periodic far-field BCs).

**Follow-up (CC-V5/V6 supersession).** The ~2.4×→**2.64×** factor is resolved. This change updated the two
benchmark-local docs (`flow_past_sphere/RESULTS.md`, `METHODS.md` Known-Limitation #1). The remaining live
copies of the "~60% low / under investigation" (CC-V5) and "~2.4×" (CC-V6) claims — in
`add-apex-benchmarking` (proposal/tasks/spec), `examples/heaving_ellipsoid/RESULTS.md`,
`examples/prelim_sweep/README.md`, `force_surrogate/evidence_figure.py`,
`examples/flapping_wing/RESULTS.md`, `docs/force_surrogate/roadmap.md` — are **deferred to a dedicated
follow-up** (keeps this PR focused; avoids entangling the frozen/submitted Track-B corpus and another
in-flight change). The already-submitted APEX PDF is immutable and intentionally retains the original note;
`F_ref≈624.8` (pure kinematics) is unaffected.
