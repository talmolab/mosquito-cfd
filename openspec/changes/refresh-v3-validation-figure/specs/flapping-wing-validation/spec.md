## ADDED Requirements

### Requirement: Committed V1–V5 validation-figure summary matches its committed sources

`examples/flapping_wing/figures/validation_figures_summary.json` SHALL equal the summary that
`examples/flapping_wing/generate_validation_figures.py` `main()` produces from the committed data:
the same keys at every nesting level, each number within `1e-12` relative to the committed value, or
within `1e-12` absolute where the committed value's magnitude is below `1e-12`, and a non-finite
number on either side counting as a mismatch. The summary's `v3.<coef>.r2_van_veen` SHALL also equal,
within the same tolerance, both the R² recomputed from the committed
`examples/prelim_sweep/surrogate/holdout_predictions.parquet` with the R² function the force-surrogate
trainer uses, and the committed `surrogate/metrics.json` `per_target.<coef>.r2`, for `CF_x` and
`CF_z`. Each mismatch SHALL be reported with its dotted key path.

A retrain, rescale or sign flip of the predictions that is not followed by a regeneration therefore
fails CI. See also [force-surrogate](../force-surrogate/spec.md), "Re-normalization preserves
surrogate skill (scale-invariance)", for the invariance itself.

#### Scenario: The committed summary equals a fresh regeneration

- **Given** the committed `validation_figures_summary.json` and the committed inputs of the generator
- **When** `main(out_dir=tmp_path)` is run and its summary compared with the committed one
- **Then** there is no mismatch

#### Scenario: The committed V3 R² equals R² recomputed from the committed predictions

- **Given** the committed `holdout_predictions.parquet` and `metrics.json`
- **When** R² of `CF_*_true` against `CF_*_pred` is computed for `CF_x` and `CF_z`
- **Then** the summary's `v3.<coef>.r2_van_veen` equals it, and equals `metrics.json`
  `per_target.<coef>.r2`, within `1e-12` relative

#### Scenario: Stale values under the correct keys are rejected

- **Given** a summary in which `v3.CF_x.r2_van_veen` and `v3.CF_z.r2_van_veen` are present and
  hold values that differ from the R² recomputed from the committed predictions by more than the
  tolerance (the values committed before this change, 0.9931809360713737 and 0.9854005163288705, are
  such a pair)
- **When** it is compared with a fresh regeneration and with R² recomputed from the parquet
- **Then** both comparisons report a value mismatch (committed against fresh or recomputed value),
  not a key mismatch, at `v3.CF_x.r2_van_veen` and at `v3.CF_z.r2_van_veen`

#### Scenario: The comparison rejects each kind of drift and accepts rounding

- **Given** synthetic committed and fresh summaries
- **When** they differ, at a nested path three levels deep, by a key missing from fresh, a key
  present only in fresh, a block present only in fresh, a dict against a number, a non-zero number
  off by `1e-9` relative, a number `1e-11` against `1.05e-11`, `0.5` against `0.5 + 8e-13`, a
  committed `0.0` against `2e-12`, a NaN on either side, or a differing string
- **Then** each case yields a mismatch of its kind naming its key path
- **And** identical summaries, a non-zero number off by `1e-13` relative, and a committed `0.0`
  against `5e-13` yield none

### Requirement: Validation-figure summary is written with LF line endings

`main()` SHALL write `validation_figures_summary.json` with LF line endings on every platform.

#### Scenario: The summary has no carriage returns even where the platform default is CRLF

- **Given** `Path.write_text` patched so that its default line ending is CRLF
- **When** `main(out_dir=tmp_path)` runs
- **Then** the written `validation_figures_summary.json` contains no `\r` byte

### Requirement: V3 shows the van Veen and the peak-tip normalization of the committed predictions

The V3 figure (`V3_scale_invariance.png`) SHALL show, for `CF_x` and `CF_z`, the committed
coarse-surrogate predictions against the CFD targets twice: as stored in
`holdout_predictions.parquet` (the van Veen normalization), and divided by
`k = F_ref(R_TIP) / F_ref(R_GYRATION)` (the same coefficients on the peak-tip reference), both
references from `compute_force_reference`. Each panel's title SHALL name its normalization and state
its R²; its axes SHALL name the CFD coefficient as lab-frame and on the wing, and the surrogate
prediction; no title or suptitle SHALL contain "BEFORE" or "AFTER". The summary SHALL record, per
coefficient, `r2_van_veen`, `r2_peak_tip`, their absolute difference `delta` (below `1e-9`), and the
mean and RMS of the stored target and prediction (`true_mean`, `true_rms`, `pred_mean`, `pred_rms`).

#### Scenario: The van Veen panel plots the stored coefficients unscaled

- **Given** the committed `holdout_predictions.parquet`
- **When** V3 is rendered
- **Then** for each of `CF_x` and `CF_z`, the van Veen panel's scatter offsets equal
  `(CF_*_true, CF_*_pred)` exactly, and the peak-tip panel's equal `(CF_*_true / k, CF_*_pred / k)`

#### Scenario: The peak-tip panel matches raw forces on the tip reference

- **Given** the holdout rows joined one-to-one with `examples/prelim_sweep/dataset.parquet` on
  (`config_name`, `time`)
- **When** each row's `−Fx` and `−Fz` are divided by `compute_force_reference(frequency_fstar,
  stroke_amp_deg, R_TIP, SPAN, CHORD, RHO).f_ref`
- **Then** the result equals the peak-tip panels' x offsets for `CF_x` and `CF_z` within `1e-12`
  relative

#### Scenario: Titles and axis labels describe what is plotted

- **Given** V3 rendered from the committed data
- **When** its titles, suptitle and axis labels are read
- **Then** each van Veen panel's title contains "van Veen" and `r2_van_veen` to six decimals, each
  peak-tip panel's title contains "peak-tip" and `r2_peak_tip` to six decimals
- **And** no title or suptitle contains "BEFORE" or "AFTER"
- **And** every x label contains the coefficient, "lab frame" and "on wing", and every y label
  contains "surrogate" and the coefficient

#### Scenario: Re-normalization leaves R² unchanged

- **Given** V3 rendered from the committed data
- **When** the summary's `v3` block is read
- **Then** `delta < 1e-9` for `CF_x` and `CF_z`
