## MODIFIED Requirements

### Requirement: Force-surrogate comparison figures reproduce their source data exactly, not an approximation

`comparison_figure.build_coarse_vs_fine_comparison` SHALL compute per-config mean force values via
the same `groupby(...).mean()` aggregation the figure visualizes, and
`build_config_mean_collapse_diagnostic` SHALL report `config_resolved` R² values read verbatim from
the source `metrics.json`, never re-derived or approximated. This guards specifically against
conflating `metrics.json`'s `config_resolved` block (config-mean R²) with its separate `per_target`
block (RMSE) — a documented gotcha in the tooling this capability replaces (`evidence_figure.py`
formerly read config-mean R² and RMSE through separate `_config_mean_r2` and `_per_target_rmse`
accessors from two different blocks, before the evidence figure moved to skill over a phase-only
baseline; treating them as one view of the same number is a real, previously-made mistake this
requirement exists to prevent).

#### Scenario: per-config mean markers match a direct pandas groupby on the same data

- **GIVEN** a small synthetic `holdout_predictions.parquet` fixture with 2 configs, several rows each
- **WHEN** `build_coarse_vs_fine_comparison` computes the per-config mean marker positions
- **THEN** each position equals `df.groupby("config_name")[["CF_x_true", "CF_x_pred"]].mean()`
  computed directly on the same fixture, to floating-point equality

#### Scenario: the diagnostic's reported R² is not silently swapped for the RMSE block

- **GIVEN** a synthetic `metrics.json` fixture with distinct, known values in `config_resolved` and
  `per_target`
- **WHEN** `build_config_mean_collapse_diagnostic` reports its R² figure
- **THEN** the reported value matches the fixture's `config_resolved` block exactly, not any value
  from `per_target`

#### Scenario: a legitimate JSON `null` config-mean R² passes through unchanged, not as an error or a coerced number

- **GIVEN** a `metrics.json` fixture whose `config_resolved.<coefficient>.config_mean_r2` is JSON
  `null` (the value `train.py`'s `compute_config_resolved` legitimately writes when between-config
  variance is near-zero)
- **WHEN** `build_config_mean_collapse_diagnostic` reports that grid's R² value
- **THEN** the returned value is Python `None`, not `0.0`, `NaN`, or a raised exception
