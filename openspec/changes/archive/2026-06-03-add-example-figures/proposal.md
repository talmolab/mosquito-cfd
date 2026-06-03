# Proposal: add-example-figures

**Change ID**: add-example-figures
**Status**: In Progress
**Date**: 2026-02-27

## Problem

Only `flapping_wing` has committed force CSV data and reproducible figure generation.
The other two examples (`heaving_ellipsoid`, `flow_past_sphere`) require Z: drive
access to reproduce any results, and neither has committed figures or a standalone
`generate_figures.py` script. This makes the repo incomplete for external reviewers
and the ALCF proposal.

Additionally, all figures are currently saved only as PDF, which is incompatible with
`xhtml2pdf` (used by the proposal PDF generator) — PNG format is required.

## Solution

1. **Commit force CSVs** extracted from AMReX plotfiles on the NFS share:
   - `examples/heaving_ellipsoid/forces.csv` (11 data points, t=0–10)
   - `examples/flow_past_sphere/forces_coarse.csv` (coarse 128×64×64 run)
   - `examples/flow_past_sphere/forces_medium.csv` (medium 256×128×128 run)

2. **Add `generate_figures.py` scripts** that run entirely from repo data (no cluster
   access required after the one-time CSV extraction):
   - `examples/heaving_ellipsoid/generate_figures.py` — geometry + force history
   - `examples/flow_past_sphere/generate_figures.py` — grid convergence figure

3. **Fix `flapping_wing/generate_all_figures.py`**:
   - Update stale `--forces-csv` default path to `examples/flapping_wing/forces.csv`
   - Add PNG output alongside PDF for xhtml2pdf compatibility

4. **Generate and commit figures** for all three examples

5. **Update RESULTS.md** with figure tables and reproducibility commands

## Figures Produced

| Example | Figure | Description |
|---------|--------|-------------|
| heaving_ellipsoid | `fig_geometry.{png,pdf}` | Elliptic cross-sections with semi-axes |
| heaving_ellipsoid | `fig_forces.{png,pdf}` | Cd and CL vs time |
| flow_past_sphere | `fig_forces_convergence.{png,pdf}` | Coarse + medium Cd vs time + literature |
| flapping_wing | `fig_planform.{png,pdf}` | Wing planform marker scatter (now also PNG) |
| flapping_wing | `fig_kinematics.{png,pdf}` | Euler angle time series (now also PNG) |
| flapping_wing | `fig_wing_phases.{png,pdf}` | Wing at 4 key phases (now also PNG) |
| flapping_wing | `fig_forces.{png,pdf}` | Force coefficient time series (now also PNG) |

## Acceptance Criteria

- `uv run python examples/heaving_ellipsoid/generate_figures.py` runs with no args
- `uv run python examples/flow_past_sphere/generate_figures.py` runs with no args
- `uv run python examples/flapping_wing/generate_all_figures.py` runs with no args
- All `figures/*.png` and `figures/*.pdf` are non-zero size
- RESULTS.md for each example links the figures and documents the reproducibility command
