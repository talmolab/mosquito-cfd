# Tasks: add-velocity-figures

## Task 1: Add plot_validation() to examples/heaving_ellipsoid/generate_figures.py
2-panel figure matching proposal Figure 2.
Reuse render_velocity_axes/render_force_axes logic from vaults/generate_ellipsoid_figure.py.
Add --plotfile optional CLI arg; skip with message if not provided.

## Task 2: Add plot_velocity_field() to examples/flow_past_sphere/generate_figures.py [parallel with Task 1]
Single-panel x-velocity field at steady state.
Add --plotfile optional CLI arg.

## Task 3: Add plot_velocity_field() to examples/flapping_wing/generate_all_figures.py [parallel with Tasks 1,2]
Single-panel x-velocity field at mid-stroke (t=0.25, phi=70°).
Add --plotfile optional CLI arg.

## Task 4: Run all three scripts with plotfile args and verify figures [depends on Tasks 1, 2, 3]
```bash
uv run python examples/heaving_ellipsoid/generate_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k00500
uv run python examples/flow_past_sphere/generate_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k/plt10000
uv run python examples/flapping_wing/generate_all_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/plt00500
```

## Task 5: Update all three RESULTS.md files [depends on Task 4]
Add velocity/validation figure to Figures table in each RESULTS.md.

## Task 6: Commit [depends on Task 5]
