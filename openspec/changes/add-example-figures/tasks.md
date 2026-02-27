# Tasks: add-example-figures

## Task 1: Create examples/heaving_ellipsoid/forces.csv
Extract force time series from plt_1k* plotfiles (or encode from verified RESULTS.md table).
Output: `examples/heaving_ellipsoid/forces.csv` with columns `time,Fx,Fy,Fz` (11 rows).

## Task 2: Create examples/flow_past_sphere/forces_coarse.csv and forces_medium.csv [parallel with Task 1]
Extract Cd-verified force data for both grid resolutions.
Output: `examples/flow_past_sphere/forces_coarse.csv` and `forces_medium.csv`.

## Task 3: Create examples/heaving_ellipsoid/generate_figures.py [depends on Task 1]
Two figure functions:
- `plot_geometry()`: elliptic cross-sections with annotated semi-axes
- `plot_forces()`: 2-panel Cd and CL vs time from forces.csv

## Task 4: Create examples/flow_past_sphere/generate_figures.py [depends on Task 2]
One figure function:
- `plot_forces_convergence()`: Cd vs time for both grids + Cd=1.087 reference line

## Task 5: Fix examples/flapping_wing/generate_all_figures.py [independent]
- Update `--forces-csv` default from stale Z: path to `Path(__file__).parent / "forces.csv"`
- Add PNG output alongside PDF in all four figure-saving calls (G1/K1/K2/F1)

## Task 6: Run all generate_figures.py and verify outputs [depends on Tasks 3, 4, 5]
```bash
uv run python examples/heaving_ellipsoid/generate_figures.py
uv run python examples/flow_past_sphere/generate_figures.py
uv run python examples/flapping_wing/generate_all_figures.py
```
Verify all figures/*.png and figures/*.pdf are non-zero size.

## Task 7: Update all three RESULTS.md files [depends on Task 6]
- Add Figures section with table linking generated images
- Add/update Reproducibility section with generate_figures.py command
- Update dates and notes for flapping_wing (second successful run, 146s)
