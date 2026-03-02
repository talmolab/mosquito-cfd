# Proposal: add-velocity-figures

**Change ID**: add-velocity-figures
**Status**: In Progress
**Date**: 2026-02-27

## Problem

All three CFD examples have committed force/geometry figures (from `add-example-figures`)
but no velocity field visualizations. The "fluid flow pictures" — showing wakes,
boundary layers, and induced flow — are essential for the APEX proposal and for
validating that the simulations produce physically correct flow fields.

## Solution

Add a `plot_velocity_field()` (or `plot_validation()` for ellipsoid) function to each
example's `generate_figures.py`, using the publication-quality matplotlib FRB technique
developed for the existing proposal figure:

    C:\vaults\physics surrogate models\ellipsoid-validation-figure\generate_ellipsoid_figure.py

This approach uses `ds.slice().to_frb()` to extract a fixed-resolution buffer and
renders it with matplotlib `imshow`, avoiding yt's default CGS unit labeling artifacts.

All scripts accept an optional `--plotfile` argument and skip gracefully if not provided,
so `generate_figures.py` still runs cleanly from repo root without cluster access.

## Timepoints

| Example | Plotfile | Time | Rationale |
|---------|----------|------|-----------|
| heaving_ellipsoid | `plt_1k00500` | t=5.0 | Body at y=7.5, clear of y-periodic boundary ([0,10]) |
| flow_past_sphere | `plt10000` | t=100.0 | Confirmed steady state |
| flapping_wing | `plt00500` | t=0.25 | Mid-forward-stroke, phi=70°; z-periodic not a concern |

## Figures Produced

| Example | Figure | Description |
|---------|--------|-------------|
| heaving_ellipsoid | `fig_validation.{png,pdf}` | 2-panel: x-velocity field (t=5.0) + force history; matches proposal Figure 2 |
| flow_past_sphere | `fig_velocity.{png,pdf}` | x-velocity field z-slice at steady state |
| flapping_wing | `fig_velocity.{png,pdf}` | x-velocity field z-slice at mid-stroke (phi=70°) |

## Acceptance Criteria

- `uv run python examples/heaving_ellipsoid/generate_figures.py` (no args) still runs cleanly
- `uv run python ... --plotfile <path>` generates the velocity figure
- All velocity figures show physically plausible flow (wake behind body, reasonable velocity range)
- PNGs committed and linked from RESULTS.md
