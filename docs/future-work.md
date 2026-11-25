# Future work: open questions from the 2026-11-24 lab meeting

This page records the questions and suggestions raised at the 2026-11-24 lab meeting, why each
one matters, what we already know, and what result would answer it. It is written to be quoted
when motivating future work in talks and grant proposals. Each item's work is scheduled in its own
GitHub issue; tracking issue [#222](https://github.com/talmolab/mosquito-cfd/issues/222) lists
them and gives a suggested order.

**Keeping it current.** Every section ends with "What would answer it". When an item is answered,
replace that paragraph with the answer and a link to the evidence (PR, figure or results file),
and keep the question. The issue links carry the status; this page doesn't duplicate it.

The CFD numbers quoted here are copies. Their source of truth is
[`examples/flapping_wing/RESULTS.md`](../examples/flapping_wing/RESULTS.md) (sections "T4
per-component decomposition" and "Grid convergence (T3c)"), where tests recompute them. If they
change there, update them here.

**Terms.** "Wing frame" means the frame attached to the wing (chord, span, normal axes), not the
insect's body. "Lab frame" means the fixed simulation axes. `CF_chord` and `CF_normal` are
wing-frame components; the force surrogates are trained on lab-frame `CF_x … CF_mz`, which equal
wing-frame components only at the rest pose ([#203](https://github.com/talmolab/mosquito-cfd/issues/203)).
"256³" is shorthand for the 256×128×256 grid, and "512³" for 512×256×512.

| § | Question | Issue |
|---|---|---|
| 1 | What are the real mosquito flight numbers, and how do ours map onto them? | [#217](https://github.com/talmolab/mosquito-cfd/issues/217) |
| 2 | Where does the quasi-steady model fail, and where should the CFD fail? | [#218](https://github.com/talmolab/mosquito-cfd/issues/218) |
| 3 | Why does the chordwise force break down? | [#219](https://github.com/talmolab/mosquito-cfd/issues/219) |
| 4 | What do AMR and further grid-convergence work tell us? | [#220](https://github.com/talmolab/mosquito-cfd/issues/220) |
| 5 | What changes with a deformable wing with realistic stiffness? | [#221](https://github.com/talmolab/mosquito-cfd/issues/221) |

---

## 1. Real mosquito flight numbers

**Why it matters.** Every result we show is dimensionless. An audience needs to know what a
wingbeat, a chord and our Reynolds number correspond to in a real mosquito, and where our setup
deliberately or accidentally differs.

**What we know.** Our target species is *Anopheles coluzzii*, the malaria mosquito of van Veen et
al. 2022 ([#79](https://github.com/talmolab/mosquito-cfd/issues/79)). The only measured kinematics
the repo cites are for male *Culex quinquefasciatus* (Bomphrey et al. 2017). The repo currently
labels those numbers *Aedes aegypti*; that is being corrected in
[#201](https://github.com/talmolab/mosquito-cfd/issues/201).

| Quantity | Our simulation | Real mosquito | Source / status |
|---|---|---|---|
| Wingbeat frequency | f\* = 1.0 (sweep 0.85–1.15), in wingbeats per simulation time unit | ~600 Hz hovering, *A. coluzzii* (period ≈ 1.67 ms); 717 ± 59 Hz, male *Culex* (period ≈ 1.39 ms) | van Veen 2022 (from Muijres et al. 2017; page to confirm in #217); Bomphrey 2017 p.2 |
| Wingbeat period | 1/f\* time units (1 at f\* = 1; 2000 steps of dt = 5e-4 on the coarse grid) | see above | Comparing f\* with Hz needs a chosen time scale. The meaningful comparison is reduced frequency and Re (below), not f\* = 1 ≈ some Hz. |
| Stroke amplitude | **half-amplitude** φ₀ in φ = φ₀ sin ωt: 70° in the validation run (140° total sweep); 35/45/55° in the corpus sweep (70/90/110° total) | 39 ± 4° **total** sweep between stroke reversals, male *Culex* | Bomphrey 2017 p.2. Our sweep is about 2–3× the mosquito's, and the validation stroke about 3.6×. *Anopheles* value: to source (#217). |
| Chord | 1.0 = the ellipse's maximum (root) chord; mean chord = π/4 ≈ 0.785 | to source | `CHORD` in `src/mosquito_cfd/force_surrogate/constants.py` |
| Span / wing length | 3.0 chords (nominal; markers span 2.95), synthetic ellipse | *Anopheles*: to source. The repo's 3.0 mm is an estimate from the APEX proposal; Bomphrey's text gives no wing length in mm | `SPAN`; [#201](https://github.com/talmolab/mosquito-cfd/issues/201); `wing.vertex` is not a real wing outline ([#79](https://github.com/talmolab/mosquito-cfd/issues/79)) |
| Reynolds number | Re = 2π f\* φ₀ r_mid / ν\* with r_mid = 1.5 and chord 1.0: ≈ 100 at the validation point, 43–90 across the sweep (ν\* = 0.115). On the mean chord it would be ≈ 79 at the validation point. | to compute from the real numbers, with the same definition | `compute_reynolds` in `force_surrogate/sweep.py`; [`force_surrogate/roadmap.md`](force_surrogate/roadmap.md) CC-7. Literature Re usually uses the mean chord and the speed at r₂ or the tip, so state the definition before comparing. |
| Kinematics | sinusoidal stroke and pitch; deviation amplitude 0 in every deck. Pitch is α₀ cos ωt, so the wing passes through horizontal at each reversal and the opposite edge leads on the return stroke. | measured, non-sinusoidal, insect-like rotation at reversal | [#142](https://github.com/talmolab/mosquito-cfd/issues/142) |

**What would answer it.** One table of *Anopheles coluzzii* values (frequency, stroke and pitch
amplitude with their conventions, wing length, mean chord, aspect ratio, area, second moment of
area, body mass, and the implied Re and reduced frequency), each with source and page, from
Muijres et al. 2017 and van Veen et al. 2022. Muijres et al. 2017 is a take-off study of blood-fed
females, so check which values describe hovering. Unknown values stay marked unknown rather than
borrowed from another species. That table then replaces the one above.

## 2. Where the quasi-steady model fails, and where the CFD should fail

**Why it matters.** This is the case for doing CFD at all. Where the quasi-steady (QS) model fails
and the CFD doesn't, CFD and surrogates trained on it earn their cost. Where both fail, CFD adds
little. Where the CFD itself should fail, no surrogate trained on it can be trusted.

**What we know.** From RESULTS.md, "T4 per-component decomposition" (the first wingbeat from an
impulsive start, window t ≥ 0.05, IB force on the wing, 256³ grid):
- The QS model is van Veen et al. 2022's translational + added-mass + Wagner model. It has no
  pitch-rotation term (the paper's §2.8), and our wing pitches continuously.
- Normal force: CFD peak 2.23 vs model 2.27, a 1.7 % gap (graded, within tolerance). Against the
  CFD's second normal peak (2.01) the gap is 12.9 %.
- Chord force: CFD peak 0.41 vs model 0.107, 3.8×. The curves have a similar shape and differ in
  size. This is not explained ([#40](https://github.com/talmolab/mosquito-cfd/issues/40)).
- The model's tangential force is weakly supported for a decelerating wing, but its chord peak
  falls in the accelerating part of the stroke, so that weakness doesn't explain the peak gap.
- The model's chord value depends on which of the paper's two coefficient sets is used (§3.1.2 vs
  §4.4); the planform moments are on mixed bases
  ([#155](https://github.com/talmolab/mosquito-cfd/issues/155)); and the recipe for a reversing
  wing is unverified ([#156](https://github.com/talmolab/mosquito-cfd/issues/156)).
- The model covers forces only; extending it to moments is
  [#111](https://github.com/talmolab/mosquito-cfd/issues/111).
- The CFD's own limits: a diffused immersed boundary whose kernel width scales with the grid
  spacing; a rigid wing; a chord force not converged at 256³ (§3, §4); corpus runs of 2 wingbeats
  ([#192](https://github.com/talmolab/mosquito-cfd/issues/192)); a small domain with walls
  ([#204](https://github.com/talmolab/mosquito-cfd/issues/204)); and non-insect-like rotation at
  reversal (§1, [#142](https://github.com/talmolab/mosquito-cfd/issues/142)).

**Expected failure regimes (hypotheses to test, not results).**

| Regime | QS model | CFD (current setup) |
|---|---|---|
| Steady mid-stroke translation | expected to hold | expected to hold (normal force GCI 3.7 %, first wingbeat) |
| Stroke reversal, rapid pitch rotation | expected to fail (no rotation term) | should capture it if the grid resolves it. Our reversal isn't insect-like (#142), so conclusions don't transfer directly to mosquitoes. |
| Strong deceleration | weak tangential model | should capture it |
| Wing–wake interaction, later wingbeats | not modelled | should capture it, given enough beats (#192) and a large enough domain (#204) |
| Low Re (the sweep spans 43–90) | coefficients fitted to the paper's simulations; whether they hold across 43–90 is to check | expected to hold; viscous layers are thicker and easier to resolve |
| Thin boundary layer / skin friction | no separate skin-friction term; folded into the empirical tangential coefficient | limited by IB smearing and grid (§3) |
| Wing flexibility | not modelled | not modelled (rigid wing, §5) |

**What would answer it.** [#218](https://github.com/talmolab/mosquito-cfd/issues/218), whose
measurement is [#194](https://github.com/talmolab/mosquito-cfd/issues/194): QS vs CFD across the
corpus, per component and per config, plus where in the stroke the residual concentrates and how
it varies with pitch amplitude and frequency. Run it on the regenerated corpus (#192).

## 3. Why the chordwise force breaks down

**Why it matters.** Of the two wing-frame components studied for grid convergence, the chord force
is the one not converged at 256³, and it carries the larger QS–CFD disagreement. Until we know
whether that is the grid, the immersed boundary, the choice of force, or physics the QS model
misses, the CFD's `CF_chord` can't be quoted in absolute terms. Whether the lab-frame `CF_x` the
surrogates are trained on converges hasn't been checked (#203).

**What we know.** From RESULTS.md, "Grid convergence (T3c)" (first wingbeat from rest): peak
`CF_chord` falls monotonically, 0.923 (64×32×64), 0.554 (128×64×128), 0.411 (256×128×256). Observed
order 1.37, GCI 27.6 % (normal force: 3.7 %). The Richardson extrapolant, 0.321, is illustrative
only: refinement here changes the grid spacing, the time step (the 256³ run used half the dt) and
the IB kernel width and marker volume together. Span force, moments and lab-frame components were
not grid-studied.

**Candidate explanations.**
1. **Under-resolved tangential boundary layer.** On a zero-thickness plate the chordwise force is
   viscous shear plus leading-edge suction, and with a leading-edge vortex at 45° pitch much of
   the suction is lost. So skin friction is plausibly a large part of the chord force. This is a
   hypothesis, and it needs the near-wall gradient, which the diffused IB smears over a few cells.
2. **Numerical chordwise force from the diffused IB.** On an ideal flat plate, pressure acts only
   along the normal. The IB returns only the total marker force and doesn't directly separate
   pressure from shear (that would need stress reconstruction from the field). Its marker force
   isn't constrained to the normal, and the kernel gives the wing an effective thickness of a few
   cells, which would add a spurious chordwise form drag that shrinks with the grid spacing. That
   is consistent with the monotone fall.
3. **Which CFD force is compared** ([#135](https://github.com/talmolab/mosquito-cfd/issues/135)).
   The numbers above use the IB force on the wing. The solver's 6-DOF force adds an internal-fluid
   term that is 84 % of the chord RMS on the coarse grid and moves the coarse chord peak from 0.923
   to 0.652 (RESULTS.md, "Added-mass-subtracted body-frame diagnostic"). For a zero-thickness wing
   that "internal" fluid is the kernel-smeared region, so it may scale with the grid too.
4. **Physics missing from the QS model**, not a CFD error: no pitch-rotation term (§2, #40).
5. **A frame-projection error.** Wing-frame forces are rotated with the analytic R(t), so only a
   time-stamp offset can move normal force into chord. A 2Δt offset (the size of the plotfile
   marker lag in [#166](https://github.com/talmolab/mosquito-cfd/issues/166)) gives about
   2Δt × peak pitch rate × `CF_normal` ≈ 5e-4 × 4.9 × 2.2 ≈ 0.006, about 1.5 % of 0.41. It can't
   explain a 3.8× gap unless the offset is much larger. Cheap to rule out.

**What would answer it.** The diagnostics in
[#219](https://github.com/talmolab/mosquito-cfd/issues/219) (the force choice in #135, the timing
of the chord peak in the stroke, cells across the boundary layer, the projection check), then a
512³-equivalent run ([#165](https://github.com/talmolab/mosquito-cfd/issues/165), or via AMR if
§4 shows AMR works with the moving IB).

## 4. AMR and grid convergence

**Why it matters.** Every committed deck uses a uniform grid (`amr.max_level = 0`). AMR could
reach finer spacing at the wing with far fewer cells. For uniform 512³ the binding constraint is
GPU memory: the 256³ pilot peaked at 7998 MiB of AMReX arena for 8.4 M cells (about 950 bytes per
cell), which extrapolates linearly to about 64 GB for 512³'s 67 M cells. That is beyond the A5000
(24 GB) and A40 (~46 GB) and only just fits an 80 GB H100.

**Caveats AMR has to clear first.**
- It has never been run with our moving diffused-IB wing. Whether markers work across level
  boundaries, and on which level the IB force is applied, is unverified. If it needs solver
  changes, it also needs a rebuilt image.
- With `amr.subcycling_mode = None`, every level advances at the finest level's dt. AMR saves
  cells and memory, not time steps, and each step pays for a regrid (`amr.regrid_int = 1`) and a
  multilevel solve. That per-step overhead is unmeasured
  ([#99](https://github.com/talmolab/mosquito-cfd/issues/99)).
- The field-surrogate reader rejects plotfiles with `max_level != 0`
  (`src/mosquito_cfd/field_surrogate/snapshot.py`), as does the stress-integral benchmark. An AMR
  corpus needs multi-level reader work.

**What we know.** Three uniform grids, 64×32×64 to 256×128×256. Two cost measurements exist and
differ by about 4× per step:
- The T3c validation run: one wingbeat, 4000 steps at dt = 2.5e-4 (dt = 5e-4 diverged), about
  8.8 h on a local RTX A5000 with a locally patched image (7.9 s/step).
- The fine-grid pilot: the production 256³ corpus decks on the cluster image, 2.01 s/step on an
  A40 ([`force_surrogate/fine-grid-pilot-report.md`](force_surrogate/fine-grid-pilot-report.md)).
  The corpus decks keep `ns.fixed_dt = 5e-4` as a ceiling with `ns.cfl = 0.6`, so their dt drops
  automatically where the CFL limit binds.

Either way, the existing convergence study mixes spatial and temporal refinement.

**What would answer it.** The experiments in
[#220](https://github.com/talmolab/mosquito-cfd/issues/220): first check that the IB works with
AMR, then AMR around the wing checked against uniform 256³ at the same finest spacing and dt,
fixed-dt refinement to isolate the spatial order, a 512³-equivalent AMR run, and a larger domain.
Output: a convergence table per force component and moment, with grid, dt, cell count, memory and
cost, and the cheapest grid that converges each.

## 5. Deformable wing

**Why it matters.** Real mosquito wings bend and twist during the stroke. A rigid wing is a
modelling choice whose effect we haven't measured, and it is one of the places where both the QS
model and our CFD are expected to be wrong (§2).

**What we know.** The wing is 908 unconnected markers on a flat ellipse (z = 0) with prescribed
rigid motion. IAMReX's immersed boundary is documented for rigid or prescribed-motion bodies, and
no elastic-structure coupling has been found in it. The field-surrogate roadmap records two-way
elastic FSI as out of scope for that roadmap
([`field_surrogate/roadmap.md`](field_surrogate/roadmap.md), open question 1), and notes that the
soft-body literature uses IBAMR. This section is the plan for picking it up later.

**Steps, smallest first.**
1. Prescribed deformation: move markers along a measured or assumed deformation (camber, twist,
   trailing-edge bending). No structural model and no solver change.
2. Markers connected by a spring/beam network, driven one-way by the CFD force. The structure can
   be sub-stepped inside each fluid step, so the fluid dt needn't shrink.
3. Full two-way FSI. This needs a substantial IAMReX extension or a different solver. With explicit
   coupling, stiff elastic forces add the classic IB stability limit on the fluid dt, set by the
   highest-frequency mode of the marker network.

Stiffness, mass and damping come from the literature where published, and otherwise are tuned so
the simulated deformation matches measured wing shapes from high-speed video. Every value records
its source or what it was tuned to.

**What would answer it.** For step 1, forces from a prescribed-deformation run compared with the
rigid run at the same kinematics, which bounds how much deformation matters before any structural
modelling. [#221](https://github.com/talmolab/mosquito-cfd/issues/221) starts with a design note,
then an OpenSpec proposal for step 1.

## References

- Bomphrey, R. J., Nakata, T., Phillips, N. & Walker, S. M. 2017. Smart wing rotation and
  trailing-edge vortices enable high frequency mosquito flight. *Nature* 544(7648):92–95.
  doi:10.1038/nature21727. (Male *Culex quinquefasciatus*.)
- Muijres, F. T., Chang, S. W., van Veen, W. G., Spitzen, J., Biemans, B. T., Koehl, M. A. R. &
  Dudley, R. 2017. Escaping blood-fed malaria mosquitoes minimize tactile detection without
  compromising on take-off speed. *J. Exp. Biol.* 220(20):3751–3762. doi:10.1242/jeb.163402.
  (Cited as 2017a by van Veen 2022; the source of their *Anopheles* kinematics and morphology.)
- van Veen, W. G., van Leeuwen, J. L., van Oudheusden, B. W. & Muijres, F. T. 2022. The unsteady
  aerodynamics of insect wings with rotational stroke accelerations, a systematic numerical
  study. *J. Fluid Mech.* 936:A3. doi:10.1017/jfm.2022.31. Erratum: *J. Fluid Mech.* 956:E1
  (2023).
