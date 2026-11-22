## MODIFIED Requirements

### Requirement: Every generated video or figure writes the CC-1 run-metadata sidecar

Every artifact-producing function in `visualization/` and `force_surrogate/comparison_figure.py` SHALL call `validate_image_digest` before any computation or file write, and SHALL write a `<name>_run_metadata.json` sidecar afterward via `capture_surrogate_run_metadata`, following the same provenance triple convention as `wing_phase_diagnostic.build_wing_phase_figure`.

#### Scenario: a mutable docker tag is rejected before any rendering work happens

- **GIVEN** a call to any `visualization/` or `comparison_figure.py` builder function with
  `docker_image_digest=":latest"`
- **WHEN** the function is invoked
- **THEN** it raises `ValueError` immediately, before reading any plotfile, extracting any field, or
  opening any matplotlib figure

#### Scenario: a rendered video has a matching run-metadata sidecar

- **GIVEN** a successful `flow_video` call that writes `<name>.mp4`
- **WHEN** the call returns
- **THEN** `<name>_run_metadata.json` also exists in the same output directory, containing the
  caller-supplied docker digest and ISO-8601 timestamp (never a wall-clock-derived value)

#### Scenario: a builder with more than one input file independently hashes every input, not just the primary one

- **GIVEN** any `comparison_figure.py` figure builder, which reads eight input files under the roles
  `coarse_dataset`, `coarse_predictions`, `coarse_metrics`, `coarse_surrogate_run_metadata`,
  `fine_dataset`, `fine_predictions`, `fine_metrics` and `fine_surrogate_run_metadata`
- **WHEN** the run-metadata sidecar is written
- **THEN** each role in `input_files` records that file's own path and SHA256 — the generic
  `capture_surrogate_run_metadata` helper's single `inputs.hash` field records only the one file
  passed as its primary `inputs_file`, so each additional input must be hashed and recorded
  separately for full provenance

### Requirement: Generated video files are excluded from version control by filename convention; figure scripts ship one committed reference PNG

`.gitignore` SHALL exclude generated video output by **filename convention**
(`*_flow_*.mp4`, `*_kinematics_preview.mp4`), not by directory, since `--out-dir` is caller-supplied
and arbitrary. Each figure that `scripts/make_coarse_vs_fine_figures.py` renders (`skill_ranges`,
`error_histograms`, `cycle_mean_r2_diagnostic`) SHALL have exactly one committed reference PNG,
rendered from the committed coarse and fine force-surrogate artifacts (real corpus data, not a
synthetic fixture) and committed with its `<name>_metrics.json` and `<name>_run_metadata.json`
under `examples/prelim_sweep_fine/figures/coarse_vs_fine/`. No synthetic-fixture render of these
figures SHALL be committed: the unit tests build their own synthetic inputs in a temporary
directory, and a rendered toy fixture is not documentation.

#### Scenario: a freshly rendered video does not appear in `git status` regardless of output directory

- **GIVEN** a clean working tree
- **WHEN** `make_flow_video.py --out-dir <any-caller-chosen-directory>` writes
  `s45_f115_p60_flow_wake-slice.mp4`
- **THEN** `git status` does not list that file as untracked, because its filename matches the
  `*_flow_*.mp4` `.gitignore` pattern independent of which directory it was written to

#### Scenario: each coarse-vs-fine figure has one committed real-data reference output

- **GIVEN** the repository at HEAD
- **WHEN** `examples/prelim_sweep_fine/figures/coarse_vs_fine/` is inspected
- **THEN** for each of `skill_ranges`, `error_histograms` and `cycle_mean_r2_diagnostic`, the PNG,
  `<name>_metrics.json` and `<name>_run_metadata.json` each pass `git ls-files --error-unmatch`,
  the PNG begins with the PNG file signature, and `tests/fixtures/comparison_figure/` does not exist

### Requirement: Force-surrogate comparison figures reproduce their source data exactly, not an approximation

Every quantity a `comparison_figure.py` figure plots that `metrics.json` also records SHALL either be
read verbatim from `metrics.json` or be recomputed from the committed predictions and dataset and
required to equal the recorded value before anything is written; the remaining quantities (waveform
RMS, cycle-mean spread, histogram counts) SHALL be computed from the committed predictions and
dataset by the formulas stated in this capability. The builder SHALL raise `ValueError` naming the
corpus, target and quantity when a check fails, and SHALL write no file in that case.

**Tolerance form T.** Wherever this capability compares a recomputed `a` with a recorded `b` "in
form T", it SHALL require `|a − b| ≤ 1e-12·max(1, |b|)`.

The specific checks are:

- `skill_ranges` SHALL read each seed's skill verbatim from `seed_sweep.runs[i].per_target.<c>.skill`.
- `error_histograms` SHALL rebuild the phase-only baseline with `train.build_phase_only_baseline`.
  - The returned definition SHALL equal `phase_baseline_skill.phase_baseline`, with lists compared
    as lists.
  - The recomputed baseline RMSE SHALL equal `phase_baseline_rmse` to `rel=1e-9, abs=0`.
  - The recomputed `1 − skill` SHALL equal `1 − phase_baseline_skill.per_target.<c>.skill` to
    `rel=1e-9, abs=0`.
- `cycle_mean_r2_diagnostic` SHALL recompute the primary seed's cycle-mean R² with the arithmetic of
  `train.compute_config_resolved`. It is recomputed, not read, and required to equal the recorded
  value. The recomputed `1 − R²` SHALL equal the recorded `1 − R²` in form T, both for
  `config_resolved.<c>.config_mean_r2` and for `seed_sweep.runs[0].per_target.<c>.config_mean_r2`.

This guards against conflating `metrics.json` blocks (`config_resolved`, `per_target`,
`phase_baseline_skill`, `seed_sweep`) — a documented, previously made mistake in the tooling this
capability replaces — and against a dataset or baseline definition that no longer matches the
surrogate it is drawn with.

#### Scenario: the skill-range values are the seed sweep, verbatim

- **GIVEN** synthetic coarse and fine corpora whose `metrics.json` is assembled exactly as the
  trainer assembles it, with five distinct per-seed skills per target
- **WHEN** `skill_ranges` is built
- **THEN** its sidecar's per-seed values equal `seed_sweep.runs[i].per_target.<c>.skill` in seed
  order; none equals any `r2`, `rmse`, `config_mean_r2`, `phase_baseline_r2` or
  `phase_baseline_rmse` value; and the primary seed's value equals
  `phase_baseline_skill.per_target.<c>.skill`

#### Scenario: a baseline that does not reproduce metrics.json is refused

- **GIVEN** a synthetic corpus whose `metrics.json` `phase_baseline_rmse` for `CF_x` is multiplied by
  `1 + 1e-8`, and separately one multiplied by `1 + 1e-11`
- **WHEN** `error_histograms` is built
- **THEN** the first raises `ValueError` naming the corpus, `CF_x` and "phase-only baseline" and
  writes no file; the second succeeds

#### Scenario: a recorded skill that does not reproduce is refused

- **GIVEN** a synthetic corpus whose recorded `CF_x` skill is set to `1 − (1 − skill)·(1 + 1e-8)`,
  and separately to `1 − (1 − skill)·(1 + 1e-11)`, in `runs[0]` (before `summarize_seed_sweep`, so
  `range` stays consistent) and in `phase_baseline_skill` together
- **WHEN** `error_histograms` is built
- **THEN** the first raises `ValueError` naming the corpus, `CF_x` and `skill`; the second succeeds

#### Scenario: a baseline definition that differs is refused

- **GIVEN** a synthetic corpus whose `phase_baseline.reference_configs` lists the same
  configurations in a different order
- **WHEN** `error_histograms` is built
- **THEN** it raises `ValueError` naming the corpus and `reference_configs`, and no file is written

#### Scenario: the diagnostic's R² is recomputed, matches, and is not swapped for another block

- **GIVEN** a synthetic corpus whose six holdout configurations each have an even number of rows and
  constant true values 1, 2, 3, 4, 5, 6, with primary-seed predictions offset per configuration by
  +1, −1, +1, −1, +1, −1 plus a ±0.5 alternation within each configuration
- **WHEN** `cycle_mean_r2_diagnostic` is built
- **THEN** the recorded primary-seed `config_mean_r2` equals the fixture's `config_resolved` value
  and `23/35` in form T (on `1 − R²`); the recorded σ equals `sqrt(35/12)` and ε equals `1` to
  `rel=1e-12, abs=0`; and the recorded value equals no `per_target` or `phase_baseline_skill` value

#### Scenario: a recorded R² that disagrees with the recomputation is refused

- **GIVEN** the previous fixture (R² = 23/35) with `config_resolved.CF_x.config_mean_r2` multiplied
  by `1 + 1e-10`, and separately by `1 + 1e-14`
- **WHEN** `cycle_mean_r2_diagnostic` is built
- **THEN** the first raises `ValueError` naming the corpus, `CF_x` and `config_mean_r2` and writes
  no file; the second succeeds

#### Scenario: a null config-mean R² passes through as null, never as a number

- **GIVEN** a synthetic corpus whose six holdout configurations have true values alternating
  `0.5 ± 1` with an even number of rows each (so the cycle means are bitwise equal, `_r2` returns its
  sentinel, and `config_resolved` and every seed's `config_mean_r2` are JSON `null`), and whose
  training configurations' values differ from that alternation (so the skill stays finite)
- **WHEN** `cycle_mean_r2_diagnostic` is built
- **THEN** the recorded R² and every derived error for that target are JSON `null` (not `0`, not
  `NaN`); σ is recorded as computed, here exactly `0.0`; the sidecar's drawn state labels the target
  `n/a`; and no exception or warning is raised

## ADDED Requirements

### Requirement: Comparison figures validate their inputs before writing anything

Each `comparison_figure.py` builder SHALL take the repository root as `root: Path` (the driver
passes `Path.cwd()`) and SHALL resolve the eight inputs as `root / <corpus dir> / ...`.

Before anything is written, it SHALL apply the guards below **in this order**. On the first that
fails it SHALL raise `ValueError` naming the corpus, the role and the defect, with no file written
and no matplotlib figure left open. A test of a defect SHALL assert the message of the first guard
the defect trips.

1. The digest is validated, before any file is touched.
2. Each of the eight files exists.
3. Each JSON input is a JSON object without a `NaN` or `Infinity` literal.
4. The required columns are present: `config_name`, `time`, `phase`, `wingbeat`, `CF_c_true` and
   `CF_c_pred` in the predictions; `config_name`, `time`, `phase`, `wingbeat`, `split` and each
   target in the dataset.
5. The dataset sha256 equals the surrogate's `inputs.hash`.
6. The predictions are non-empty and have at least two configurations. Neither frame repeats a
   `(config_name, time)` key.
7. Every coefficient is finite.
8. **Beat structure.** Every dataset configuration has wingbeats exactly `0..N−1`, with the same N
   for all configurations. The prediction rows have wingbeats exactly
   `CONVERGED_MIN_WINGBEAT..N−1`, where `CONVERGED_MIN_WINGBEAT` equals
   `phase_baseline.converged_min_wingbeat`.
9. The predictions' `CF_c_true` equal the dataset's `split == "holdout"` rows with
   `wingbeat >= CONVERGED_MIN_WINGBEAT`, matched on `(config_name, time)` exactly.
10. **Seed sweep.**
    - Each `seed_sweep.range.<c>.<stat>` equals the NaN-aware min and max of its runs.
    - `runs[0].seed` equals `primary_seed`.
    - `runs[0].per_target.<c>.skill` equals `phase_baseline_skill.per_target.<c>.skill`, with a null
      equal only to a null.
    - A null `skill` or `config_mean_r2` is either null for every seed of that corpus and target, or
      for none of them.
    - No `config_mean_r2` exceeds 1.
11. **Pairing.** The coarse and fine corpora have equal configuration sets, equal seed lists, equal
    per-seed `val_configs` and equal N.

#### Scenario: each defect is refused before any output

- **GIVEN** a valid synthetic corpus pair and, one at a time, each of these defects:
  - each of the eight input files removed, in turn;
  - a JSON input that is a list;
  - `metrics.json` containing a `NaN` literal;
  - each required column dropped;
  - an empty predictions frame;
  - one configuration only;
  - a repeated `(config_name, time)` key;
  - `+inf`, `−inf` and `NaN` in a `_true` and in a `_pred` column;
  - the coarse and the fine dataset sha256 each changed;
  - a dataset whose wingbeats are `{0, 2}`, and one configuration with an extra beat, both built
    before the dataset is hashed, so its hash still matches;
  - `phase_baseline.converged_min_wingbeat` set to `0`;
  - a prediction row with `wingbeat == 0`;
  - a `CF_x_true` changed by one ulp;
  - the fine predictions copied into the coarse directory;
  - a `range` off by one ulp at `min` and at `max`;
  - `runs[0].seed` differing from `primary_seed`;
  - `phase_baseline_skill.per_target.CF_x.skill` changed by one ulp, with `runs` and `range`
    unchanged;
  - one non-primary seed's skill set to `null` while the others are finite, placed before
    `summarize_seed_sweep`;
  - a non-primary `config_mean_r2` of `1.5`, and separately of `nextafter(1, 2)`, both placed
    before `summarize_seed_sweep`;
  - differing configuration sets, seed lists or `val_configs`;
  - a coarse corpus with wingbeats `{0, 1}` beside a fine one with `{0, 1, 2}`
- **WHEN** each of the three builders is called
- **THEN** each raises `ValueError` whose message names the corpus and the first guard tripped (the
  file or role, the column, the hash pair, the quantity and seed), the output directory has no new
  file, and `matplotlib.pyplot.get_fignums()` is unchanged

#### Scenario: the digest is checked before any file

- **GIVEN** a mutable digest and corpus directories that do not exist
- **WHEN** each builder is called
- **THEN** the raised `ValueError` is the digest error, not a missing-file error

### Requirement: The coarse-vs-fine skill-range figure follows the pre-registered overlap rule

`comparison_figure.py` SHALL build `skill_ranges`. For each of the six targets it draws a coarse row
and a fine row on one shared skill axis. Each row shows:

- every per-seed skill over that corpus's phase-only baseline as a marker, the primary seed's
  marker distinct;
- the min–max of the per-seed skills as a bar.

A row whose skills are null (all of them, by the all-or-none guard) SHALL be labelled `n/a` with no
bar.

The metrics sidecar SHALL record:

- per target and corpus: the seeds and per-seed values, the min and max, the overlap cell from
  `ranges_overlap`, the number of markers drawn, the bar `[lo, hi]` or `null`, and the `n/a` label;
- the notes (`{target: text}`);
- the caption string.

`ranges_overlap` SHALL return `yes` exactly when `max(lo_coarse, lo_fine) <= min(hi_coarse, hi_fine)`
on the raw values, `no` otherwise, and `n/a` when either range is null.

A target whose cell is `no` SHALL carry the in-axes note
`ranges disjoint at <n> seeds each; see README before reading this as a grid effect`, with `<n>`
read from the data. No note or caption SHALL match `_readme_guards._COMPARATIVE`,
`_readme_guards._FINE_COMPARATIVE` or `_readme_guards._BANNED`.

#### Scenario: overlap agrees with the README guard

- **GIVEN** the committed coarse and fine `metrics.json`, and the hand-written pairs
  `[0.97, 0.98]`/`[0.98, 0.99]` (touching), `[0.97, 0.98]`/`[nextafter(0.98, 1), 0.99]` (one ulp
  apart), an overlapping pair, and a pair with a null range
- **WHEN** `ranges_overlap` and `_readme_guards.overlap_cell` are each applied
- **THEN** they return the same cell for every pair: `yes`, `no`, `yes` and `n/a` respectively, and
  on the committed data `no` for `CF_y` only

#### Scenario: only disjoint targets are annotated, without direction

- **GIVEN** synthetic metrics in which exactly `CF_y` has disjoint ranges, and separately metrics in
  which every range overlaps
- **WHEN** `skill_ranges` is built
- **THEN** the first sidecar's notes hold exactly one entry, for `CF_y`, and the second holds none;
  no note or caption matches `_COMPARATIVE`, `_FINE_COMPARATIVE` or `_BANNED`

#### Scenario: a target whose skills are all null

- **GIVEN** a synthetic corpus in which one target has the same constant value in every
  configuration, holdout included, so the baseline equals the truth, its SSE is zero and every seed's
  skill is `null` by construction
- **WHEN** `skill_ranges` is built
- **THEN** that target records one `null` per seed, a `null` range, overlap `n/a`, zero markers, a `null`
  bar and the `n/a` label, and carries no note

### Requirement: The error-histogram figure compares the surrogate with the phase-only baseline within each grid

`comparison_figure.py` SHALL build `error_histograms`, with one row per corpus and one column per
target. Each panel SHALL show, on the same holdout rows:

- the primary seed's surrogate error (`pred − true`);
- the phase-only baseline's error.

Each is divided by that corpus's **recomputed** baseline RMSE (`z`), and drawn as a log-scale
density on the fixed edges `numpy.linspace(-3, 3, 601)`, with
`density = counts / (n_rows · numpy.diff(edges))`. Here `n_rows` includes out-of-range rows.

Values with `z < −3` or `z > 3` SHALL be counted as below or above range. A value exactly at ±3
falls in the end bin, as `numpy.histogram` places it. Non-zero out-of-range counts SHALL be printed
in the axes as `outside ±3: <below> / <above>`.

Each panel SHALL be annotated `seed <primary> skill <x> (<n> seeds: <lo> to <hi>)`, with `<x>` from
`seed_sweep.runs[0].per_target.<c>.skill` and the range from `seed_sweep.range.<c>.skill`, read
verbatim. A target whose recorded skill is null SHALL be refused, naming the target.

The sidecar SHALL record:

- per corpus and target:
  - the recomputed `rmse0` and `rmse_surrogate`, and `skill = 1 − (rmse_surrogate / rmse0)²`;
  - `skill_recorded` and its range, read verbatim;
  - both count arrays and both below/above counts;
  - `n_rows`;
- the edges, once;
- the caption string.

#### Scenario: the counts follow the bin convention

- **GIVEN** a pure `_bin_counts(z, edges)` helper and `z` values `[-3.5, -3.0, 0.0, 3.0, 3.5]`
- **WHEN** it is applied with `numpy.linspace(-3, 3, 601)`
- **THEN** below is 1, above is 1, `-3.0` is in the first bin, `3.0` is in the last bin, and the
  counts plus below plus above equal 5

#### Scenario: the histogram counts are the normalised errors

- **GIVEN** a synthetic corpus with known errors, including values outside ±3 baseline RMSEs
- **WHEN** `error_histograms` is built
- **THEN** each recorded count array equals `numpy.histogram` of the normalised errors on the
  recorded edges, below/above equal the out-of-range counts, and counts plus below plus above equal
  `n_rows`

#### Scenario: the recomputed skill is consistent with its two RMSEs

- **GIVEN** any corpus the builder accepts
- **WHEN** `error_histograms` is built
- **THEN** for every target `(rmse_surrogate / rmse0)²` equals the recorded recomputed `1 − skill`
  to `rel=1e-12, abs=0`, and `skill_recorded` equals `runs[0].per_target.<c>.skill` exactly

### Requirement: The cycle-mean R² diagnostic shows why the metric is ill-conditioned, across all seeds

`comparison_figure.py` SHALL build `cycle_mean_r2_diagnostic` with two panels per corpus.

**Definitions.** Cycle means SHALL be computed as `train.compute_config_resolved` computes them:
numpy boolean-mask means in `numpy.unique` order. σ is the population standard deviation
(`ddof=0`) of the true cycle means.

**Scales panel** (log axis), per target, showing:

- the waveform RMS (RMS of `CF_c_true` about its holdout mean);
- σ;
- each seed's cycle-mean RMS error `ε_s = σ·sqrt(1 − R²_s)`, from that seed's committed
  `config_mean_r2`.

A zero or null scale value SHALL be drawn as a marker at the axis floor labelled `0` or `n/a`, never
as data on the log axis.

**Seeds panel** (symlog axis, linear within ±1): each seed's `config_mean_r2`, with 0 and 1 marked.

**Check.** When the recorded primary R² is non-null, the builder SHALL require the measured
primary-seed `ε²/σ²` to equal the recorded `1 − R²_primary` in form T.

**Sidecar.** It SHALL record every plotted value with its seed, the per-target drawn state (floor
markers and `n/a` labels) and the caption string. The figure SHALL NOT show one seed's value without
the others.

#### Scenario: every seed is plotted and the derived errors are exact

- **GIVEN** the 23/35 fixture with five seeds whose per-configuration offsets are 1, 3, 2, 0.5 and
  1.5 (so the second seed's R² is `−73/35`)
- **WHEN** the diagnostic is built
- **THEN** the sidecar holds five `ε_s`, each equal to `σ·sqrt(1 − R²_s)` to `rel=1e-12, abs=0`;
  the `−73/35` seed's `ε_s` equals 3 and is greater than σ; and the primary seed's measured `ε²/σ²`
  equals `1 − R²` in form T

#### Scenario: boundary values of R²

- **GIVEN** non-primary seeds whose `config_mean_r2` is `0.0`, `1.0` and `−1e6`, placed before
  `summarize_seed_sweep` so `range` stays consistent
- **WHEN** the diagnostic is built
- **THEN** `0.0` gives `ε_s == σ` exactly; `1.0` gives `ε_s == 0.0`, recorded as a floor marker
  labelled `0`; and `−1e6` is recorded and drawn, with no warning

#### Scenario: the scales are the stated statistics

- **GIVEN** a target whose true values alternate `+1`, `−1` within every configuration, each with an
  even number of rows
- **WHEN** the diagnostic is built
- **THEN** the recorded waveform RMS is `1.0` and σ is `0.0`

### Requirement: Comparison-figure captions and labels state the scope and never compare the grids

Each figure's caption SHALL be built by a pure `build_<figure>_caption` function.

**Every caption SHALL state:**

- `shipped surrogate (surrogate/)`;
- `lab-frame components of the IB force and moment on the wing; moments about the hinge`;
- the beat label:
  - `second wingbeat of 2-beat runs` when N = 2, otherwise `wingbeats 2–N of N-beat runs`;
  - `the corpus is to be regenerated with longer runs` exactly when N = 2.

**`skill_ranges` and `error_histograms` SHALL also state** `OWN_BASELINE_PHRASE`
(`each grid is scored against its own corpus's phase-only baseline`).

**`cycle_mean_r2_diagnostic` SHALL state instead**
`cycle-mean R² is computed on each grid's own <k> holdout configurations`, with `<k>` read from the
data.

**Figure-specific content:**

- **`skill_ranges` and `cycle_mean_r2_diagnostic`:** `<n> seeds`, and
  `observed spread, not a confidence interval`.
- **`skill_ranges`:**
  - `RULE_SENTENCE.format(n=<n>)`, where `RULE_SENTENCE` is
    `a target counts as moved only if its two {n}-seed ranges are disjoint (computed on the
    unrounded values; touching ranges count as overlapping)`;
  - `not a measurement of the effect of grid resolution on its own`.
- **`error_histograms`:**
  - `seed <primary>`;
  - `skill = 1 − (RMSE / RMSE₀)²`;
  - `not compared across the two rows`;
  - `consecutive timesteps of <k> configurations, not independent samples`.
- **`cycle_mean_r2_diagnostic`:** `a diagnostic of the metric, not a comparison of the grids`.

`<n>`, `<k>` and `<primary>` SHALL be read from the data, never hard-coded.

**Target labels:**

| target | label |
|---|---|
| `CF_x` | `CF_x (lab x force)` |
| `CF_y` | `CF_y (lab y force)` |
| `CF_z` | `CF_z (lab vertical force)` |
| `CF_mx` | `CF_mx (lab M_x about the hinge)` |
| `CF_my` | `CF_my (lab M_y about the hinge)` |
| `CF_mz` | `CF_mz (lab M_z about the hinge)` |

**Forbidden.** No caption, note or label SHALL match
`(?i)\b(?:(?:chord|span|drag|pitch|roll)\w*|normal)\b`, `_readme_guards._COMPARATIVE` or
`_readme_guards._FINE_COMPARATIVE`.

#### Scenario: the beat label follows the data

- **GIVEN** synthetic corpora with dataset wingbeats `{0, 1}` and prediction wingbeats `{1}`, and
  separately `{0, 1, 2, 3}` and `{1, 2, 3}`
- **WHEN** each figure's caption is built
- **THEN** the first contains `second wingbeat of 2-beat runs` and `the corpus is to be regenerated
  with longer runs`; the second contains `wingbeats 2–4 of 4-beat runs` and no regeneration phrase

#### Scenario: required and forbidden wording

- **GIVEN** each figure built on a synthetic corpus pair with a primary seed of 42, three seeds and
  six holdout configurations
- **WHEN** its caption, notes and labels are inspected
- **THEN** every required phrase is present with `seed 42`, `3 seeds` and `6` where the data supply
  them (never a hard-coded `1234` or `5`); the diagnostic caption does not contain
  `OWN_BASELINE_PHRASE`; and nothing matches a forbidden pattern

#### Scenario: the forbidden-word pattern matches whole framings only

- **GIVEN** the strings `normalised`, `timespan`, `wing-normal`, `spanwise`, `chordwise`, `spans` and
  `rolling`
- **WHEN** the forbidden-word pattern is applied
- **THEN** `normalised` and `timespan` do not match, and every other string matches

#### Scenario: the README carries the shared constants

- **GIVEN** the fine README's "Coarse vs fine" section with whitespace runs collapsed to one space
- **WHEN** it is searched case-insensitively
- **THEN** it contains `OWN_BASELINE_PHRASE` and `RULE_SENTENCE.format(n=5)`, where 5 is the
  committed seed count

### Requirement: Committed comparison figures stay current with their inputs and renderer

**Run-metadata contents.** Each `*_run_metadata.json` from `comparison_figure.py` SHALL record:

- `input_files`: role → `{path, sha256}`, for the eight roles;
- `inputs.file` and `inputs.hash` for `coarse_metrics`;
- `corpus_docker_images`: `{coarse, fine}`, from the two `surrogate/run_metadata.json`;
- `library_versions`: python, numpy, pandas, pyarrow and matplotlib;
- `renderer_sources`: the sha256 of the LF-normalised bytes of `comparison_figure.py` and
  `scripts/make_coarse_vs_fine_figures.py`, read from those files' own locations (not from `root`)
  and keyed by those fixed names;
- `figure`.

**Portable paths.** Every recorded path SHALL be relative to `root`, written with forward slashes,
with no drive letter, no leading `/` and no `..`. A pure `_portable_path(path, root)` SHALL produce
it, resolving a relative path against `root` first, and SHALL refuse a path outside `root`.

**The checker.** A pure test helper `check_committed_figure(root, figure)` SHALL check the input
hashes before any recomputation. It SHALL re-raise any `ValueError` from the library as
`AssertionError` naming the figure and the role, and SHALL raise `AssertionError` naming the figure
and the failing field or role. It SHALL require:

- every `input_files` path to resolve under `root` to a file whose sha256 equals the recorded one,
  and `inputs.hash` to equal the `coarse_metrics` hash;
- the committed `<figure>_metrics.json` to equal the library's `compute_<figure>_metrics` on the
  committed inputs, at these tolerances:
  - exactly: values read verbatim, counts, edges, captions, notes and drawn states;
  - `rel=1e-12, abs=0`: every other float (σ, `ε_s`, waveform RMS, `rmse0`, `rmse_surrogate`, the
    recomputed `skill`), with exact zeros compared exactly;
- `renderer_sources` to equal the current files;
- `corpus_docker_images` to equal the two surrogate records;
- `docker_image` to equal `examples/prelim_sweep_fine/run_metadata.json`'s;
- the five `library_versions` keys to be non-null strings (not compared with the running
  environment);
- `git.commit` to be 40 hex characters and `git.dirty` to be false;
- `figure` to equal the name.

**The CI test.** A CI test SHALL apply the checker to each committed figure, and SHALL require one
`timestamp` across the three. It SHALL also check independent anchors computed in the test itself:

- histogram counts, via `numpy.histogram` with the baseline from `train.build_phase_only_baseline`;
- the per-seed values, against `metrics.json`;
- σ.

**Re-rendering.** A render or re-render SHALL be done into a scratch directory outside the
repository, with the nine files then
copied into place, so that `git diff HEAD` stays empty during every render and `git.dirty` stays
false.

#### Scenario: the check fails for each kind of staleness

- **GIVEN** a synthetic repository layout in a temporary directory, rendered by the real builder with
  injected git metadata, and copies of it with, one at a time:
  - the last digit of the fine `metrics.json`'s first `skill` value changed;
  - `git.dirty` set to true;
  - a backslash path;
  - an absolute path;
  - a per-seed `skill` in `skill_ranges_metrics.json` moved by `1e-10` relative;
  - an `ε_s` in `cycle_mean_r2_diagnostic_metrics.json` moved by `1e-10` relative;
  - the recorded hash of `comparison_figure.py` changed
- **WHEN** `check_committed_figure` runs on each copy
- **THEN** the unmodified layout passes, and each copy fails with `AssertionError` naming the
  figure and the role or field (`fine_metrics`, `git.dirty`, `path`, the sidecar key,
  `renderer_sources`)

#### Scenario: recorded paths are portable on every OS

- **GIVEN** `PureWindowsPath("C:/repo/examples/prelim_sweep/dataset.parquet")` with root
  `PureWindowsPath("C:/repo")`, the same as a `PurePosixPath`, the relative path
  `examples/prelim_sweep` with an absolute root, and a path outside the root
- **WHEN** `_portable_path` is applied
- **THEN** the first three give `examples/prelim_sweep/...` paths with forward slashes and the
  fourth is refused

#### Scenario: a dataset that is not the surrogate's training data is refused

- **GIVEN** a corpus directory whose `dataset.parquet` sha256 differs from its
  `surrogate/run_metadata.json` `inputs.hash`
- **WHEN** any figure is built
- **THEN** it raises `ValueError` naming the corpus and both hashes, and no file is written

### Requirement: Coarse-vs-fine figures are rendered one per invocation by a single driver

`scripts/make_coarse_vs_fine_figures.py` SHALL take these flags, all required:

- `--figure`, which accepts exactly `skill_ranges`, `error_histograms` or `cycle_mean_r2_diagnostic`;
- `--coarse-dir`;
- `--fine-dir`;
- `--out-dir`;
- `--docker-digest`;
- `--timestamp`.

It SHALL render exactly the named figure, passing `root=Path.cwd()`, and SHALL be a thin wrapper
over the library builder.

#### Scenario: one figure per invocation

- **GIVEN** synthetic corpus directories and an empty output directory
- **WHEN** the driver runs with `--figure error_histograms`
- **THEN** the output directory holds exactly `error_histograms.png`,
  `error_histograms_metrics.json` and `error_histograms_run_metadata.json`

#### Scenario: a missing or unknown flag value is a usage error

- **GIVEN** the driver
- **WHEN** it runs with `--figure coarse_vs_fine_comparison`, or without any one of the six flags
- **THEN** argparse exits with status 2 and no file is written
