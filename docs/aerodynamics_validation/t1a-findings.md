# T1a findings — diffused-IB force reconstruction & plotfile recoverability

**Tier:** T1a (diagnosis only) · **Tracking issue:** [#26](https://github.com/talmolab/mosquito-cfd/issues/26)
· **Roadmap:** [`roadmap.md`](roadmap.md) · **Bounds:** analysis-only, pre-June-30 OK (background track).

**Source of truth:** `talmolab/IAMReX @ 7ece065d` (`Source/DiffusedIB.{cpp,H}`), verified against the
committed sphere runs on `Z:\users\eberrigan\mosquito-cfd-benchmarks\{flow_past_sphere_coarse,flow_past_sphere_10k}`.

---

## TL;DR

- **Field mapping (numerically verified):** plotfile particle `real_comp0..8` =
  `U,V,W_Marker` (interpolated fluid velocity) · `Fx,Fy,Fz_Marker` (**dv-weighted** Lagrangian force) ·
  `Mx,My,Mz_Marker` (dv-weighted moment), in `P_ATTR` enum order.
- **RESULTS.md's hypothesis is wrong:** the deficit is **not** a missing kernel/`dv` weight. `dv` is
  *already* applied in-solver (`ForceSpreading_cic`, `fxP *= dv`), so the current "raw sum of comp3" is
  already a dv-weighted force. Confirmed by an exact identity (below).
- **Correct reconstruction** (IAMReX's own 6-DOF balance):
  `F_hydro = ρ_f · [ (ΣU_pvf,new − ΣU_pvf,old)/dt − F_ib ]`, where
  `F_ib = Σ_markers (dv·Fx_Marker)` **accumulated over all `loop_ns` sub-iterations**.
  For a **fixed sphere at steady state** the momentum term → 0, so `F_drag = −ρ_f·F_ib`.
- **Answer to the exit question — NO.** The corrected sphere Cd is **not** computable from the committed
  `plt10000` fields with no re-run. The plotfile persists only the **last** multidirect-forcing
  sub-iteration's force increment (markers are reset every sub-iteration); the accumulated `F_ib` and the
  solver's `IB_Particle_*.csv` ground truth are **not** persisted anywhere in the run dirs.
- **Consequence (per roadmap priority guard):** T1b needs a **solver-level fix + re-run** → **defers to
  post-submission, co-lands with T2a.**

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

## 2. Field mapping — verified by an exact numerical identity

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

The match is exact. This **confirms** comp3 = dv-weighted force (so the "missing dv" hypothesis is
false), confirms the comp0↔comp3 pairing, and confirms `Ml=515` ⇒ `rd=0`.

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

## 4. Why the corrected Cd is NOT recoverable from `plt10000` (the blocker)

1. **Multidirect accumulation is lost.** With `loop_ns=2`, `Σcomp3` = the **final** sub-iteration's
   increment only (markers reset each sub-iteration, `:377`). The physically intended IB force is the
   **accumulated** `kernel.ib_force` (`:392`), which is **not** in any plotfile field. So `Σcomp3 = 0.448`
   units is a single sub-iteration's residual forcing, not the solver's own total — using it as "the
   force" is methodologically wrong whenever `loop_ns>1`.
2. **Ground truth was not preserved.** `kernel.ib_force` and the momentum term are written only to
   `IB_Particle_<id>.csv`, emitted to the container's cwd (`/opt/cfd/IAMReX/Tutorials/FlowPastSphere`),
   **not** `/workspace`. A search of both run dirs finds **no** `IB_Particle*.csv` / no `*.csv` — they
   were discarded with the container.
3. **The added-mass term cannot supply the 2.4×.** It *is* in principle reconstructable from the
   persisted Eulerian velocity + the analytic sphere `pvf` across `plt09900`/`plt10000` (both committed),
   but at steady state it is ≈ 0 — it cannot explain a 2.43× deficit.
4. **Alternative reading is also solver-level.** Even if one treated `Σcomp3` as the solver's full IB
   force (i.e. if `loop_ns` effectively =1), the remaining ≈2.4× gap would be **intrinsic** to IAMReX's
   diffuse-IB force computation (`dv`/`rd`/regularization calibration, or the documented direct-forcing
   force underestimate). That too is fixable only in the solver + a re-run.

In every branch, the quantity needed to reach Cd=1.087 is **not present** in the committed plotfile
fields.

---

## 5. Field-availability check (per grid) — the issue #26 verification task

Read directly from the committed `plt10000/particles/Header`:

| Grid | `amr.n_cell` | real comps persisted | markers | comp0..8 present? | accumulated `F_ib` present? | `IB_Particle.csv` present? |
|---|---|---|---|---|---|---|
| Coarse | 128×64×64 | 9 (`real_comp0..8`) | 129 | ✅ yes | ❌ no | ❌ no |
| Medium | 256×128×128 | 9 (`real_comp0..8`) | 515 | ✅ yes | ❌ no | ❌ no |

The **persisted** fields are present and identical in structure on both grids. The fields the **correct
reconstruction requires** (accumulated multidirect `F_ib`; or the solver's `IB_Particle` force history)
are **absent** on both.

---

## 6. Reconstruction spec (for T1b)

**Steady fixed-body drag (target form):** `Cd = −ρ_f · F_ib,x / (½ ρ_f U² · A)`, `A = πr²`, with
`F_ib,x = Σ_markers dv · (U_b,x + (ω×r)_x − U_Marker,x) / dt` **summed over all `loop_ns`
sub-iterations**. The general (moving/unsteady) form adds the momentum term
`+ρ_f(ΣU_pvf,new − ΣU_pvf,old)/dt`.

Because the committed plotfiles cannot supply the accumulated `F_ib`, T1b must take a **solver-level**
path. Options to scope in T1b (pick during its `/new-feature` scoping):

- **(a)** Make IAMReX **emit** the per-marker *accumulated* dv-weighted force (don't reset, or write
  `kernel.ib_force` into a runtime real comp) so future plotfiles are self-sufficient; **or**
- **(b)** **persist `IB_Particle_<id>.csv`** to `/workspace` and read `Fx,Fy,Fz` directly (simplest;
  re-run only); **or**
- **(c)** re-run with **`LOOP_NS=1`** *and* validate that single-pass `Σcomp3` recovers Cd — only if a
  calibration check shows the single-pass force is physically complete (it likely is **not**; see §4.4).

All require a re-run ⇒ **post-submission, co-land with T2a** (roadmap priority guard + T1→T2 contingency).
Sphere **Cd = 1.087 ± tol** is T1b's TDD oracle.

---

## 7. Decision

> **Is the corrected sphere Cd computable from the committed `plt10000` fields, with no re-run?**
> **NO.**

**Path:** T1b is **not** analysis-only. It requires a solver fix + re-run and therefore **defers to
post-submission and co-lands with T2a** (roadmap §"Contingency", CC-V1). The diagnosis itself (this
document) lands pre-deadline, as the guard allows.

**Maintainer consult:** not required — the source path is unambiguous and the field mapping is confirmed
by an exact numerical identity (§2). Upstream issue
[`ruohai0925/IAMReX#59`](https://github.com/ruohai0925/IAMReX/issues/59) remains the contact point if
T1b's solver change needs upstream coordination (it concerns FP32/CUDA builds, not force extraction).

**Downstream (record, do not act here):** T1b will confirm the Track-B corpus is mis-scaled by ≈ the same
factor (re-caption, never regenerate — CC-V6) and supersede the "~60% low Cd / under investigation" claim
across `add-apex-benchmarking` + `benchmarks/METHODS.md` (CC-V5).
