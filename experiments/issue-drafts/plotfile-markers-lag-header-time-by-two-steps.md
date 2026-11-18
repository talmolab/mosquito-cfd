# Draft issue: wing markers stored in a plotfile lag the plotfile's time by exactly 2Δt

**Status:** filed 2026-11-17 as #166. Found during the surrogate exploration (2026-11-16); no fix attempted.

## What

The IB marker positions written into a fine-corpus plotfile's `particles/` data are the prescribed
wing pose at `t − 2Δt`, where `t` is the plotfile header time, not the pose at `t`.

## Evidence

Config `s55_f115_p60`, `plt02600` (header time 1.3, `Δt = 5e-4`), 908 markers read with `yt`.
Markers rebuilt from `wing.vertex`, the deck's centre (4, 2, 4) and hinge (4, 0.5, 4), and
`benchmarks/wing_kinematics.py` (`x = h + R(t)(X₀ − h)`), compared by nearest-marker distance:

| kinematics evaluated at | max distance to a stored marker |
|---|---|
| t | 2.06e-02 |
| t − Δt | 1.03e-02 |
| **t − 2Δt** | **5.1e-14** |
| t − 3Δt | 1.03e-02 |
| t + Δt | 3.10e-02 |

So the agreement at `t − 2Δt` is to round-off, and the offset is exactly two steps. One snapshot of
one config was checked.

## Where

Consistent with the lead already in the math inventory ("Markers lag by about 2Δt:
`UpdateParticles` runs at the end of the step with time tⁿ", `NavierStokes.cpp:2745` in the IAMReX
fork). This is the first measurement of it from corpus data.

## Why it matters

- At this wing speed the offset is 0.02 length units, under one cell (0.03125), so it is small.
- It is a known, exact phase offset between any quantity labelled with plotfile time (fields, and
  possibly the `IB_Particle` force rows) and the wing pose that produced it: 0.1% of a beat at
  f* = 1. Whether the force rows carry the same lag has not been checked.
- Anything that overlays markers on a field snapshot, or resamples fields into the wing frame,
  should use the stored markers or `t − 2Δt`.

## Suggested next step

Confirm on a second config and step; check whether `IB_Particle_1.csv` time stamps share the lag;
decide whether to document the offset in `docs/coordinate-convention.md` or correct it in the fork.
