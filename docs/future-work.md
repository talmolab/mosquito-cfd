# Future work: open questions from the 2026-11-24 lab meeting

This page records the questions and suggestions raised at the 2026-11-24 lab meeting, why each
one matters, what we already know, and what result would answer it. It is meant to be quoted
when motivating future work (talks, proposals, the grant). Work on each item is scheduled in its
own GitHub issue; tracking issue [#222](https://github.com/talmolab/mosquito-cfd/issues/222)
lists them.

When an item is answered, replace its "What would answer it" with the answer and a link to the
evidence. Don't delete the question.

| § | Question | Issue | Status |
|---|---|---|---|
| 1 | What are the real mosquito flight numbers, and how do ours map onto them? | [#217](https://github.com/talmolab/mosquito-cfd/issues/217) | open |
| 2 | Where does the quasi-steady model fail, and where should the CFD fail? | [#218](https://github.com/talmolab/mosquito-cfd/issues/218) | open |
| 3 | Why does the chordwise force break down? | [#219](https://github.com/talmolab/mosquito-cfd/issues/219) | open |
| 4 | What do AMR and further grid-convergence work tell us? | [#220](https://github.com/talmolab/mosquito-cfd/issues/220) | open |
| 5 | What changes with a deformable wing with realistic stiffness? | [#221](https://github.com/talmolab/mosquito-cfd/issues/221) | open |

---

## 1. Real mosquito flight numbers

**Why it matters.** Every result we show is dimensionless. An audience needs to know what a
wingbeat, a chord and our Reynolds number correspond to in a real mosquito, and where our setup
deliberately or accidentally differs.

**What we know.**

| Quantity | Our simulation | Real mosquito | Source / status |
|---|---|---|---|
| Species | — | *Anopheles coluzzii* (target) | van Veen et al. 2022 use it as their malaria-mosquito reference ([#79](https://github.com/talmolab/mosquito-cfd/issues/79)) |
| Wingbeat frequency | f\* = 1.0 (sweep 0.85–1.15) | ~600 Hz for *A. coluzzii* (period ≈ 1.67 ms); 717 ± 59 Hz for *Culex quinquefasciatus* (period ≈ 1.39 ms) | van Veen 2022 via Muijres et al. 2017a; Bomphrey et al. 2017. The repo labels the Bomphrey numbers *Aedes*, which is wrong ([#201](https://github.com/talmolab/mosquito-cfd/issues/201)) |
| Wingbeat period | 1 time unit (2000 steps of dt = 5e-4, coarse grid) | see above | — |
| Stroke amplitude | 70° validation run; sweep 35/45/55° | 39 ± 4° (*Culex*) | Bomphrey 2017. *Anopheles* value: to source ([#217](https://github.com/talmolab/mosquito-cfd/issues/217)) |
| Chord | 1.0 (reference length) | to source | `CHORD` in `src/mosquito_cfd/force_surrogate/constants.py` |
| Span / wing length | 3.0 chords, synthetic ellipse | 3.0 mm cited to Bomphrey 2017 (not rechecked); *Anopheles* to source | `SPAN`; `wing.vertex` is not a real wing outline ([#79](https://github.com/talmolab/mosquito-cfd/issues/79)) |
| Reynolds number | ≈ 100 at the 70° validation stroke; 43–90 across the sweep (ν\* = 0.115) | to compute from the real numbers | [`force_surrogate/roadmap.md`](force_surrogate/roadmap.md) CC-7 |
| Kinematics | sinusoidal stroke, pitch and deviation | measured, non-sinusoidal | [#142](https://github.com/talmolab/mosquito-cfd/issues/142) |

**What would answer it.** One table of *Anopheles coluzzii* values (frequency, stroke and pitch
amplitude, wing length, mean chord, aspect ratio, area, second moment of area, body mass, and the
implied Re and reduced frequency), each with source and page, from Muijres et al. 2017a and van
Veen et al. 2022. Unknown values stay marked unknown rather than borrowed from another species.
This table then replaces the one above.

## 2. Where the quasi-steady model fails, and where the CFD should fail

**Why it matters.** This is the case for doing CFD at all. Where the quasi-steady (QS) model fails
and the CFD doesn't, CFD and surrogates trained on it earn their cost. Where both fail, CFD adds
little. Where the CFD itself should fail, no surrogate trained on it can be trusted.

**What we know.**
- The QS model (van Veen et al. 2022: translational + added mass + Wagner) has no pitch-rotation
  term, and its tangential force is weakly supported for a decelerating wing.
- On the 256³ grid, the CFD chord-force peak (0.41) is 3.8× the QS model's (0.107) on the same
  kinematics. The normal force agrees far better
  ([#165](https://github.com/talmolab/mosquito-cfd/issues/165),
  [#40](https://github.com/talmolab/mosquito-cfd/issues/40)).
- The CFD's own limits: diffused immersed boundary with kernel width tied to grid spacing; rigid
  wing; chord force not grid-converged (§3, §4); 2-wingbeat runs
  ([#192](https://github.com/talmolab/mosquito-cfd/issues/192)); small walled domain
  ([#204](https://github.com/talmolab/mosquito-cfd/issues/204)).

**Expected failure regimes (hypotheses to test).**

| Regime | QS model | CFD (current setup) |
|---|---|---|
| Steady mid-stroke translation | expected to hold | expected to hold (normal force converged) |
| Stroke reversal, rapid pitch rotation | expected to fail (no rotation term) | should capture it if the grid resolves it |
| Strong deceleration | weak tangential model | should capture it |
| Wing–wake interaction, later wingbeats | not modelled | should capture it, needs enough beats (#192) and a large enough domain (#204) |
| Thin boundary layer / skin friction | empirical | limited by IB smearing and grid (§3) |
| Wing flexibility | not modelled | not modelled (rigid wing, §5) |

**What would answer it.** [#194](https://github.com/talmolab/mosquito-cfd/issues/194): QS vs CFD
across the corpus, per component and per config, plus where in the stroke the residual
concentrates and how it varies with pitch amplitude and frequency. Run on the regenerated corpus.

## 3. Why the chordwise force breaks down

**Why it matters.** The chord force is the one coefficient that doesn't converge, and it's the
largest QS–CFD disagreement. Until we know whether that's the grid, the immersed boundary, the
analysis, or physics the QS model misses, neither the CFD's chord force nor the surrogates trained
on it can be quoted in absolute terms.

**What we know.** Peak body-frame `CF_chord`: 0.923 (64×32×64), 0.554 (128×64×128), 0.411
(256×128×256). Observed order 1.37, Richardson estimate 0.321, GCI 27.6 % (normal force 3.7 %).

**Candidate explanations.** (1) Under-resolved tangential boundary layer; (2) the IB force on a
zero-thickness wing can't separate pressure from shear, and normal force may leak into chord
during rotation; (3) physics missing from the QS model, not a CFD error; (4) a frame-projection
error moving part of the much larger normal force into chord.

**What would answer it.** The cheap diagnostics in
[#219](https://github.com/talmolab/mosquito-cfd/issues/219) (projection sensitivity, timing of the
peak in the stroke, cells across the boundary layer), then the 512³-equivalent run
([#165](https://github.com/talmolab/mosquito-cfd/issues/165), or via AMR, §4).

## 4. AMR and grid convergence

**Why it matters.** Every production run so far is a uniform grid (`amr.max_level = 0`). AMR could
reach finer spacing at the wing for a fraction of the cells, which could make the 512³ question
(§3) answerable without grant hardware and make a better-resolved corpus affordable.

**What we know.** Three uniform grids (64, 128, 256 in x). The 256³ run took about 8.8 h on an
A5000 and needed half the coarse dt, so the existing study mixes spatial and temporal refinement.

**What would answer it.** The experiments in
[#220](https://github.com/talmolab/mosquito-cfd/issues/220): AMR around the wing checked against
uniform 256³, fixed-dt refinement to isolate the spatial order, a 512³-equivalent AMR run, and a
larger domain. Output: a convergence table per component with cost, and the cheapest grid that
converges each force.

## 5. Deformable wing

**Why it matters.** Real mosquito wings bend and twist during the stroke. A rigid wing is a
modelling choice whose effect we haven't measured, and it is one of the places where both the QS
model and our CFD are expected to be wrong (§2).

**What we know.** The wing is 908 unconnected markers on a flat ellipse with prescribed rigid
motion. IAMReX's immersed boundary is set up for rigid particles; two-way elastic coupling needs
solver work.

**Steps.** (1) Prescribed deformation of the markers, no structural model; (2) markers connected
by a spring/beam network driven one-way by the CFD force; (3) full two-way FSI. Stiffness, mass
and damping come from the literature where published, and otherwise are tuned so simulated
deformation matches measured wing shapes from high-speed video. Every value records its source or
what it was tuned to. Details in [#221](https://github.com/talmolab/mosquito-cfd/issues/221).

## References

- Bomphrey, R. J. et al. 2017. Smart wing rotation and trailing-edge vortices enable high
  frequency mosquito flight. *Nature* 544:92–95. doi:10.1038/nature21727. (*Culex quinquefasciatus*.)
- Muijres, F. T. et al. 2017a. *J. Exp. Biol.* 220(20):3751–3762. (*Anopheles* kinematics and morphology used by van Veen 2022.)
- van Veen, W. G., van Leeuwen, J. L., van Oudheusden, B. W. & Muijres, F. T. 2022. *J. Fluid
  Mech.* 936:A3. doi:10.1017/jfm.2022.31.
