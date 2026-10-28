## ADDED Requirements

### Requirement: Fine-corpus surrogate and evidence figure are committed with a reproducibility gate

The fine corpus `examples/prelim_sweep_fine/` SHALL carry a trained force surrogate in
`surrogate/` (`surrogate.pt`, `holdout_predictions.parquet`, `metrics.json`, `run_metadata.json`)
and an evidence figure in `figures/` (`evidence_figure.png`, `evidence_figure_metrics.json`,
`run_metadata.json`), mirroring the coarse corpus's layout. The surrogate SHALL be trained by the
trainer with no functional change (docstrings only), with the coarse run's hyperparameters and
seeds (2000 epochs, primary seed 1234, sweep seeds 1235–1238, 3 validation configurations),
differing only in the dataset, the output directory and the container digest, which SHALL be the
fine corpus's own (`examples/prelim_sweep_fine/run_metadata.json` `docker_image`, the image that
produced the data, as for the coarse surrogate). The figure SHALL be generated with the `fine` grid
profile.

Before any fine binary is committed, the full 5-seed training SHALL be run twice from the same
clean, committed tree into two scratch directories outside the repository, and SHALL pass this
gate: `surrogate.pt` and `holdout_predictions.parquet` byte-identical; `metrics.json` equal as
parsed JSON apart from the wall-clock fields of the top-level `inference` block (its `basis` SHALL
also be equal); `run_metadata.json` equal apart from `run_id`; and both records naming the same
40-hex commit with `dirty: false`. A failure SHALL halt the change for a decision; the gate SHALL
NOT be loosened to pass. Passing it is an observed outcome for this run on this host, **not** a
bitwise-reproducibility claim: `reproducibility.bitwise` stays `cpu_only` and the "Training
reproducibility and provenance" requirement is unchanged.

#### Scenario: The fine surrogate is the committed fine dataset's, trained with the coarse run's settings

- **Given** the committed `examples/prelim_sweep_fine/surrogate/` artifacts, `dataset.parquet` and `run_metadata.json`
- **When** the committed-artifact tests run
- **Then** every holdout `<target>_true` equals the fine dataset on `(config_name, time)` for all six targets, `inputs.hash` is the fine dataset's sha256, the surrogate's `docker_image` equals the fine corpus's, `seed_sweep.seeds == [1234, 1235, 1236, 1237, 1238]`, the recorded epochs are 2000, each run has 3 `val_configs` equal to the split recomputed from the fine dataset, `reproducibility.bitwise == "cpu_only"`, and `phase_baseline_skill` recomputes from the committed predictions and fine dataset

#### Scenario: The fine figure is tied to the fine surrogate and regenerates from it

- **Given** the committed fine figure artifacts and the committed fine surrogate outputs
- **When** the committed-artifact tests run
- **Then** the figure's `run_metadata.json` hashes the fine `holdout_predictions.parquet` and `metrics.json` and records `grid == "fine"`, and regenerating the sidecar from the committed fine predictions and metrics with the `fine` profile and the recomputed fine CFD cost reproduces the committed `evidence_figure_metrics.json` (exact for copied values, relative 1e-12 for the two computed quasi-steady RMS values)

#### Scenario: Reruns that differ halt the change

- **Given** two full fine training runs from the same commit whose `surrogate.pt` or `holdout_predictions.parquet` bytes differ, whose `metrics.json` differ outside the `inference` wall-clock fields, whose `run_metadata.json` differ outside `run_id`, or either of which records `dirty: true`
- **When** the gate is evaluated
- **Then** no fine artifact is committed and the change stops for a decision with the user

### Requirement: Fine-grid CFD cost is derived from committed run metadata

A torch-free helper `median_cfd_seconds_per_step(paths)` SHALL reduce per-configuration run metadata
files to the median of `timing.wall_time_s / timing.timesteps`, returning that median with the
configuration count, the single GPU model, and the minimum and maximum. The cost is per timestep, not
per wingbeat, because a wingbeat takes `1/(f*·dt)` steps, so per-wingbeat time scales with the
kinematics while the per-step rate does not. It SHALL raise `ValueError`, naming the offending file,
for an empty input, a missing `config` or `gpu_model`, a `wall_time_s` that is missing, `null`,
boolean, a string, non-finite or non-positive, a `timesteps` that is not a positive integer, a
duplicate configuration, or more than one GPU model. A script SHALL print the median for a metadata
directory (reading only `run_metadata_<config>.json`, ignoring a corpus-level `run_metadata.json`) in
a form that `float()` reads back exactly.

The fine evidence figure SHALL take that median over the 27 committed fine
`run_metadata_<config>.json` files as its CFD cost per step, so the speedup's per-row CFD cost is the
per-step cost; the sidecar's `speedup.cfd_seconds_per_wingbeat` SHALL be that cost times the
representative configuration's `rows_per_wingbeat`, and the figure's `run_metadata.json` SHALL record
the per-step cost as `cfd_seconds_per_step`. CI tests SHALL recompute the median and compare it
exactly with both. The fine README SHALL state the fine cost per step and disclose that the coarse and
fine denominators are not like-for-like: the coarse 144 s per wingbeat is 2.4 min, the rounded wall
time (146 s) of a single A40 run of the 70° validation deck (`examples/flapping_wing/RESULTS.md`,
Performance), while the fine value is the median per-step time over the sweep's own runs; both
include plotfile output and solver start-up. The README SHALL NOT state a ratio between the two
denominators.

#### Scenario: Known-answer median per step

- **Given** metadata files with (wall time, timesteps) of (300, 200), (400, 200), (1000, 200) on one GPU model
- **When** the helper runs
- **Then** it returns `seconds_per_step == 2.0`, `n_configs == 3`, `min == 1.5`, `max == 5.0`, independent of input order, and an even count returns the mean of the middle two

#### Scenario: The per-step cost does not depend on the step count

- **Given** two configurations with the same per-step rate but 4706 and 3478 timesteps (f* 0.85 and 1.15)
- **When** the helper runs
- **Then** both give the same per-step cost, so `min == max`

#### Scenario: Malformed or empty metadata is rejected

- **Given** no files, or a file with a missing `config` or `gpu_model`, a `wall_time_s` that is missing, `null`, boolean, a string, zero, negative, NaN or infinite, a `timesteps` that is missing, `null`, boolean, a string, zero, negative or fractional, a duplicated configuration, or a second GPU model
- **When** the helper runs
- **Then** it raises `ValueError` naming the file (or, for no files, saying none were given)

#### Scenario: The script reads only per-configuration files

- **Given** a directory holding per-configuration `run_metadata_<config>.json` files and a corpus-level `run_metadata.json`
- **When** the script runs
- **Then** its printed value, parsed with `float()`, equals the helper's median over the per-configuration files only

#### Scenario: The committed fine denominator is the recomputed median

- **Given** the committed fine run metadata, the committed fine `evidence_figure_metrics.json` and the fine figure's `run_metadata.json`
- **When** the committed-artifact tests run
- **Then** `median_cfd_seconds_per_step` over the 27 files reports 27 configurations on the A40, `speedup.cfd_seconds_per_wingbeat` equals that median times `speedup.rows_per_wingbeat` exactly, and the figure's `cfd_seconds_per_step` equals the median exactly

### Requirement: Fine README compares coarse and fine skill under a pre-registered overlap rule

The fine README (`examples/prelim_sweep_fine/README.md`) SHALL replace its "Not yet built" statement
with: a one-line definition of skill over the phase-only baseline and a skill table in the coarse
README's format, equal to the fine `metrics.json`; a table of the configuration-resolved (cycle-mean)
R² range over the five seeds, read from `seed_sweep.range.<c>.config_mean_r2`; a coarse-vs-fine table
giving, per target, each corpus's five-seed skill range read from its committed `metrics.json` and
whether the two ranges overlap; the quasi-steady reference's fine-grid ratio and why it is not a
baseline, and the CF_mx/CF_mz panel exclusion with their skill; and the validation status of the fine
CFD — grid convergence checked only at the 70° validation stroke (outside this sweep's 35–55°), on peak
body-frame force components, with the GCI values (written as in the source, "3.7 %" `CF_normal`, "27.6 %" `CF_chord`) and the
quasi-steady-model comparison (per component) cited to `examples/flapping_wing/RESULTS.md`, and no
comparison with measured forces.

Overlap SHALL be computed on the raw `metrics.json` values, with touching ranges counting as
overlapping; a `null` range SHALL make the cell `n/a`. Under the rule stated here, a target whose
ranges overlap SHALL be described, if at all, only as "no shift detected"; only a target whose ranges
are disjoint MAY be described, in the form "`CF_c` … higher on fine across 5 seeds" or "… lower on fine
across 5 seeds". The README SHALL state that each grid is scored against its own corpus's phase-only
baseline, so a difference reflects the data as well as the surrogate, and SHALL NOT attribute a
difference to grid resolution alone. No skill, pointwise R² or cycle-mean R² value SHALL appear as
`CF_c ≈v` / `CF_c = v` prose. Every table SHALL be guarded by a CI test against the committed JSON.

#### Scenario: The comparison table is the two metrics files

- **Given** the committed coarse and fine `metrics.json` and the fine README
- **When** the README tests run
- **Then** each comparison row's two ranges equal the corpora's `seed_sweep.range.<c>.skill` at 3 dp, and the overlap cell equals `yes` exactly when `max(lo_coarse, lo_fine) <= min(hi_coarse, hi_fine)` on the raw values, and `n/a` when either range is `null` (a `null` range cell itself renders `n/a`)

#### Scenario: The cycle-mean and skill tables are the fine metrics file

- **Given** the committed fine `metrics.json` and the fine README
- **When** the README tests run
- **Then** each skill-table row equals the fine `phase_baseline_skill` and `seed_sweep.range.<c>.skill` (3 dp) and each cycle-mean row equals `seed_sweep.range.<c>.config_mean_r2` (2 dp), for all six targets

#### Scenario: Only disjoint ranges are described as a difference

- **Given** the fine README's coarse-vs-fine section
- **When** its prose is checked
- **Then** every "higher on fine" / "lower on fine" sentence has the stated form, appears only in that section, names exactly the targets whose overlap cell is `no`, and states the direction the ranges show; and the section contains no other comparative wording ("shift" other than "no shift detected", "improve", "better", "worse", "increase", "decrease", "drop", "greater", "less", "exceed", "outperform", "rise", "fall", "gain")

#### Scenario: The fine README states what "not validated" means

- **Given** the fine README
- **When** its disclosures are checked
- **Then** it says the figure shows agreement with CFD, not with experiment; that grid convergence was checked only at one wing motion outside this sweep; gives "3.7 %" and "27.6 %" citing `examples/flapping_wing/RESULTS.md`; discloses what the CFD wall-time denominators contain, citing `docs/force_surrogate/fine-grid-pilot-report.md` for the force-only rate; gives the CF_mx/CF_mz skill; and describes moments as lab-frame components about the hinge with the wing-frame conversion not currently tracked

#### Scenario: The fine README discloses the quasi-steady reference

- **Given** the fine README and the committed fine `evidence_figure_metrics.json`
- **When** its quasi-steady disclosures are checked
- **Then** it states the fine-grid RMS ratio equal to the sidecar's `overshoot_factor` at the caption's precision, and that the model is uncalibrated and translational-only, omits rotational/added-mass/LEV lift, assumes symmetric-rotation, is a stroke-plane-normal force compared with the lab-z CFD component, and is not overlaid on the figure; and it states the fine CFD cost as "<x.xx> s per step", where x.xx is the sidecar's `cfd_seconds_per_wingbeat / rows_per_wingbeat` at 2 dp, with no ratio between the coarse and fine denominators

## MODIFIED Requirements

### Requirement: Predicted-vs-CFD evidence figure on held-out configurations

The force surrogate SHALL provide a local, force-only figure generator that reads a corpus's committed
`<corpus>/surrogate/holdout_predictions.parquet` and `metrics.json` (`<corpus>` is
`examples/prelim_sweep` for the coarse corpus or `examples/prelim_sweep_fine` for the fine corpus) and emits a
predicted-vs-CFD scatter figure with three panels — **CF_x**, **CF_z**, and **CF_my** — each plotting
CFD-true (x-axis) against surrogate-predicted (y-axis) coefficients over the 6 held-out
configurations (CC-4), with a 1:1 reference line, points distinguished by configuration, and a
per-panel annotation of the **skill over the phase-only baseline** (the plotted seed's value and its
range over the seed sweep), the pointwise R², and the RMSE. The figure SHALL be written to
`<corpus>/figures/evidence_figure.png` at **≥200 dpi**. The generator SHALL **read**
the metrics the trainer already computed (phase-only baseline skill, seed-sweep ranges, pointwise R²,
per-target RMSE, inference timing) rather than re-deriving them. Skill and R² SHALL be displayed to
3 decimal places; either value that would display as `1.000` SHALL display as `>0.999`, a nonzero
value that would display as `±0.000` SHALL be displayed in scientific notation, and a range SHALL be
written "lo to hi".

#### Scenario: Figure has three predicted-vs-CFD panels for CF_x, CF_z, CF_my

- **Given** the committed holdout predictions parquet and metrics.json
- **When** the evidence figure is generated
- **Then** the figure contains exactly three scatter panels titled for `CF_x`, `CF_z`, and `CF_my`, each plotting `CF_*_true` on the x-axis against `CF_*_pred` on the y-axis with a 1:1 reference line, and the saved PNG exists at `<corpus>/figures/evidence_figure.png` (for the corpus whose predictions were read) with a resolution of at least 200 dpi

#### Scenario: Only held-out configurations are plotted

- **Given** the predictions parquet (which by construction contains only the held-out configurations — it has **no** `split` column; holdout-ness is the parquet's identity, not a column)
- **When** the scatter points are built
- **Then** every plotted point's `config_name` is one of the held-out configuration names, and the per-panel point count equals the parquet row count for that coefficient (no train/validation rows are introduced)

#### Scenario: Per-panel annotation reports skill, seed range, pointwise R² and RMSE read from metrics.json

- **Given** a metrics.json carrying, for each panel coefficient `<c>`, `phase_baseline_skill.per_target.<c>.skill`, `seed_sweep.range.<c>.skill.{min,max}`, `per_target.<c>.r2` and `per_target.<c>.rmse`
- **When** the panels are annotated
- **Then** each panel's annotation text contains that skill, its seed range with the number of seeds, the pointwise R² and the RMSE, each equal (within display rounding) to the value read from metrics.json — not hard-coded literals — and changing any one of them in metrics.json changes the annotation

#### Scenario: Null, near-perfect, near-zero and negative values render honestly

- **Given** a metrics.json in which a panel coefficient's skill is `null`, another's pointwise R² is 0.9996 and skill 0.9997, and a range runs from −0.150 to 0.992, and a skill is −0.0004
- **When** the annotations are built
- **Then** the `null` skill renders as `n/a` without raising, the R² and skill render as `>0.999` (never `1.000`), the range renders "−0.150 to 0.992", and −0.0004 renders in scientific notation rather than `−0.000`

#### Scenario: A required metrics key or panel coefficient is missing

- **Given** a metrics.json missing a key the figure reads (`phase_baseline_skill`, `seed_sweep`, `per_target`, `inference`, or a panel coefficient's entry in any of them), or a predictions parquet missing a panel `CF_*` column
- **When** the figure generation is invoked
- **Then** it raises a clear `KeyError`/`ValueError` naming the missing key or column **before** any artifact is written, rather than emitting a partial or mislabeled figure

#### Scenario: Degenerate prediction sets are rejected, not silently mis-plotted

- **Given** a predictions parquet with **fewer than two** configurations or **zero** rows
- **When** the figure generation is invoked
- **Then** it raises a clear error (a held-out comparison across configurations is undefined with <2 configs) rather than writing a misleading single-point or empty figure

### Requirement: Sane–Dickinson quasi-steady reference (computed, not overlaid)

The evidence figure SHALL **compute** a **translational-only** Sane–Dickinson quasi-steady CF_z
reference through the **single-source** `compute_force_reference` helper (CC-3) — the reference
force/reference speed SHALL NOT be re-derived inline — as
`CF_trans(t) = F_trans(t)/F_ref = (U(t)/u_ref)²·C_L(α_eff(t))`, with `U(t)/u_ref = cos(2π·phase)` from
the parquet `phase` column, `C_L(α)` the Dickinson–Lehmann–Sane (1999) empirical fit, and the
per-configuration `(φ, f*, α)` parsed from `config_name`.

It SHALL **NOT** overlay this reference on the scatter panels. **Why reference-only instead of an
overlay (CC-4 deviation; reference-only decision recorded in the proposal):** the uncalibrated
**translational-only** quasi-steady model is a poor fit to the CFD lift (first established on the coarse 64×32×64 grid) — it omits
rotational, added-mass, and LEV lift — so a scatter overlay would mostly re-display the model's
analytic loops rather than demonstrate surrogate skill. The earlier "~2.4× diffused-IB underestimate"
framing was a normalization-convention artifact and is removed (the CFD `ib_force` is correct). Under
the corrected van Veen normalization the model's RMS ratio `rms(CF_trans)/rms(CFD-true CF_z)` is **< 1** on the coarse
corpus (it **under-predicts** the now-in-band CFD lift, ≈ 0.7 on the committed coarse corpus — the opposite of the
old > 1 "overshoot," because the CFD lift is no longer mis-normalized small). The figure SHALL record
this RMS ratio (key `overshoot_factor`) and the baseline RMSE in `evidence_figure_metrics.json`, and
the caption SHALL disclose the ratio neutrally (the model is ~N× the CFD lift in RMS, the lift
named for the figure's grid profile: "coarse-grid CFD lift" or "fine-grid CFD lift", in both
the caption and the sidecar `note`) and that the
uncalibrated translational model is therefore **not used as a quantitative baseline** — "at this resolution" on the coarse profile; the fine
profile omits that phrase, since there the reason is the omitted terms, not the grid. On the fine
profile no bound on the RMS ratio is asserted; it is reported as measured.

#### Scenario: Baseline coefficient matches the documented formula on known inputs

- **Given** a configuration with known `(φ, f*, α)` and a `phase` array, with `C_L(α)` the Dickinson-1999 fit
- **When** the Sane–Dickinson baseline coefficient is computed
- **Then** it equals `(cos(2π·phase))² · C_L(α_amp·|cos(2π·phase)|)` within floating tolerance, evaluated at the documented angle-of-attack mapping

#### Scenario: Baseline normalizes through the CC-3 single-source helper

- **Given** the baseline computation for a configuration
- **When** the reference force `F_ref` and reference speed `u_ref` are obtained
- **Then** they come from `compute_force_reference(f_star, phi_amp_deg, r_gyr, span, chord)` (the single source — CC-3), and the baseline force is divided by that `F_ref` explicitly rather than using an inline-re-derived reference

#### Scenario: config_name parses to kinematic parameters

- **Given** a configuration name such as `s45_f115_p60`
- **When** it is parsed
- **Then** it yields `phi_amp_deg == 45`, `f_star == 1.15`, and `pitch_amp_deg == 60`

#### Scenario: The quasi-steady reference is not drawn on any panel

- **Given** the generated figure
- **When** every panel's series are inspected
- **Then** **no** axis carries a Sane–Dickinson / baseline point series (the reference is computed, not plotted), and the panels show only the surrogate predictions colored by held-out configuration

#### Scenario: The quasi-steady overshoot is recorded and disclosed, not presented as a baseline

- **Given** the computed Sane–Dickinson reference and the CFD-true CF_z
- **When** the sidecar and caption are built
- **Then** `evidence_figure_metrics.json` records the reference's `overshoot_factor` (the RMS ratio `rms(CF_trans)/rms(CFD-true CF_z)`, a positive finite number — **< 1** under the van Veen convention on the coarse corpus as stated above; no bound is asserted for the fine profile, whose value is reported as measured) and `baseline_rmse_cf_z`, and the caption states neutrally that the uncalibrated translational quasi-steady model is ~N× the coarse-grid (or, for the fine profile, fine-grid) CFD lift in RMS and is **not used as a quantitative baseline** — "at this resolution" on the coarse profile; the fine profile omits that phrase, since there the reason is the omitted terms, not the grid (it is not framed as a comparison the surrogate "beats")

#### Scenario: No diffused-IB underestimate claim remains

- **Given** the evidence-figure module docstring, caption strings, `_baseline_reference` docstring, the `evidence_figure_metrics.json` `note`, and the `Sane–Dickinson` rationale text
- **When** they are inspected
- **Then** none contains a "~2.4× diffused-IB underestimate" (or equivalent CFD-is-biased-low) claim and no post-hoc correction factor — the quasi-steady reference's RMS ratio is described neutrally (translational-only model, a poor fit that under-predicts the in-band CFD lift)

### Requirement: Honest evidence-figure caption and speedup annotation

The evidence figure's disclosures SHALL be **split** to stay both honest **and** legible (a caption
carrying a dozen disclosures fails an evidence figure as surely as a dishonest one): the on-figure
caption SHALL be **compact** — a positive headline (the plotted seed, the definition of skill over
the phase-only baseline and the number of seeds its ranges span, + the >1,000× batched speedup;
the per-axis numbers live on the panels and are not repeated), a single terse "Caveats:" line, a
single terse "Quasi-steady reference (not plotted):" line, and a pointer to the
corpus's README (`examples/prelim_sweep/README.md` or
`examples/prelim_sweep_fine/README.md`) — and the **full** disclosure set SHALL ALSO live in that README
and in `evidence_figure_metrics.json`, so honesty is preserved and test-enforced without
overloading the PNG. Skill SHALL read as dominant; a skill below the phase-only baseline (negative),
on or off the panels, SHALL be subordinate (an honesty flag, not a co-headline). The figure SHALL
report the **skill over the phase-only baseline** (read from `metrics.json
phase_baseline_skill.per_target.<coefficient>.skill`, with its range over the seed sweep from
`seed_sweep.range`), always naming the reference "phase-only baseline", and SHALL NOT report
configuration-resolved R² (which divides by the near-zero spread of six cycle means for some targets
and is strongly seed-dependent; it remains in `metrics.json` and the README). The caveats SHALL state
that pointwise R² mostly reflects the shared within-beat waveform, giving the phase-only baseline's
own pointwise R² (`phase_baseline_skill.per_target.<c>.phase_baseline_r2`) for the three axes as the
concrete evidence; that skill also rewards predicting how the waveform's amplitude and shape change
with the kinematics, not only the cycle-mean force, with configuration-resolved (cycle-mean) R²
pointed to in the README; the **skill floor** — the minimum over the six targets of each target's
seed-sweep minimum skill — or, if that floor is negative, each target whose minimum is below zero,
named as below the phase-only baseline (a single "weakest" target SHALL NOT be named, because
overlapping seed ranges do not support a ranking); the caveat of the figure's grid profile — for the coarse grid, that the result is **pipeline
readiness on coarse-grid forces** (64×32×64), **not** validated aerodynamics; for the fine grid
(256×128×256), that it shows agreement with CFD, **not** with experiment, grid convergence having
been checked only at one wing motion outside the sweep; and that the two off-axis moments
**CF_mx/CF_mz are excluded from the panels, with their actual skill (the plotted seed's value and
its seed range) read from `metrics.json` and stated** — the exclusion is stated with its numbers, not silent, and SHALL NOT assert a fixed reason
such as a particular within-beat waveform fraction,
because that ranking is corpus-dependent and has already inverted more than once. The figure SHALL
annotate the inference-vs-CFD speedup as a **batched GPU-throughput** speedup —
`inference.throughput_rows_per_s` ÷ the A40 CFD throughput on the figure's grid (per-config
converged-beat rows ÷ that grid's per-wingbeat wall-clock: 144 s on the coarse grid; on the fine grid
the median per-step wall time over the committed per-configuration run metadata times the representative
configuration's rows per wingbeat, labelled as a median per-step time) — which is the >1,000× claim. Because this factor equals
`latency_speedup × batch_size` (the surrogate is a pointwise map that batches; the CFD is an
**inherently sequential** time integration that cannot), the annotation SHALL disclose, in the caption's words "N=<batch> parallel evals vs sequential
<the profile's CFD label>", that
it is **batched GPU throughput at the stated batch size (N=12,535) versus a sequential A40 CFD
timestep rate on the figure's grid** — not a per-evaluation speedup. The conservative per-evaluation **latency**
speedup (~310× on the coarse grid, which is **not** >1,000×; on the fine grid the floor may
itself exceed 1,000× and is still reported separately) SHALL be reported alongside as the like-for-like floor, and
SHALL NOT be conflated with the throughput claim or computed by dividing a per-wingbeat cost by a
per-row latency. All caption/annotation numbers SHALL be read from the committed artifacts, never
hard-coded. The caption SHALL name the seed of the plotted model (`metrics.json`
`seed_sweep.primary_seed`) and the number of seeds its skill ranges span; it SHALL NOT present one
draw as the corpus's skill, it SHALL state "single seed, no range" when the sweep has one seed, and a
`metrics.json` without `seed_sweep` SHALL be rejected rather than captioned with a default seed.

> Note: the result numbers still embedded above and in the scenarios (~310×, N=12,535, ≈12,009×,
> 3.7×10⁶×) are stale against the committed artifacts and are tracked separately in issue #115;
> refreshing them is deliberately out of scope. The `fix-moment-reference-hinge` change rewrote the
> `CF_mx`/`CF_mz` exclusion clause and the clauses that named specific targets as dominant and as the
> negative-R² tell; the `replace-config-r2-with-baseline-skill` change replaced
> configuration-resolved R² with skill over the phase-only baseline throughout this requirement
> (issue #127).

#### Scenario: Caption defines skill and shows why pointwise R² overstates it

- **Given** a metrics.json with `phase_baseline_skill.per_target.<c>.skill` and `phase_baseline_r2` for all six targets, `per_target.<c>.r2`, and a `seed_sweep` block over five seeds whose ranges are all positive
- **When** the caption is built
- **Then** it names the plotted seed and the five-seed range, defines skill against the phase-only baseline, gives the phase-only baseline's pointwise R² for CF_x/CF_z/CF_my, states that skill also rewards amplitude and shape changes and points to the README for cycle-mean R², states the skill floor over all six targets, states that CF_mx/CF_mz are excluded from the panels **and gives their skill as read from metrics.json**, and states its grid profile's caveat (coarse: pipeline readiness rather than validated aerodynamics; fine: agreement with CFD, not with experiment, grid convergence checked only at one wing motion outside this sweep) — with every number read from metrics.json and no configuration-resolved R² value present

#### Scenario: A target below the phase-only baseline is flagged, subordinate

- **Given** a metrics.json in which one or more targets' seed-sweep minimum skill is negative (and another's is exactly 0)
- **When** the caption is built
- **Then** the caveats name each negative target and its minimum as below the phase-only baseline, do not call the zero-minimum target below it, and do not move that flag into the headline

#### Scenario: Null skills in the caption render without crashing

- **Given** a metrics.json in which an off-panel skill, a phase-only baseline R² and one target's seed-sweep skill range are `null`
- **When** the caption is built
- **Then** each `null` renders as `n/a`, a negative value renders verbatim, neither raising nor being silently dropped, the skill floor is computed over the non-null minima, and if every minimum is `null` the caption says skill is undefined for every target rather than raising

#### Scenario: The >1,000× headline is the batched-throughput speedup, computed not hard-coded

- **Given** `metrics.json inference.throughput_rows_per_s` (batched GPU throughput) and the coarse-grid A40 CFD throughput (a config's converged-beat row count ÷ the coarse per-wingbeat wall-clock `CFD_SECONDS_PER_WINGBEAT`)
- **When** the headline speedup annotation is built
- **Then** the annotated factor equals `throughput_rows_per_s / cfd_rows_per_s` (a known-answer case pins the exact factor, e.g. 5.17e7 ÷ (2000/144) ≈ 3.7×10⁶×), the realized factor exceeds 1,000×, the annotation labels the denominator "coarse-grid A40 CFD" **and discloses the batch size (N=12,535) and that the CFD rate is sequential**, and `evidence_figure_metrics.json` records both throughputs, the per-config rows-per-wingbeat, the batch size, and the implied parallelism factor (≈12,009×, = throughput_speedup ÷ latency_speedup) so the headline is fully decomposable

#### Scenario: The single-row latency speedup is reported honestly and not conflated with the headline

- **Given** `metrics.json inference.latency_ms` (single-row latency, ms) and a config's per-row CFD cost `CFD_SECONDS_PER_WINGBEAT ÷ rows_per_wingbeat` (where `rows_per_wingbeat = 1/(f*·dt)` is **per-config**, not a constant)
- **When** the latency speedup is computed
- **Then** it equals `t_cfd_per_row / (latency_ms/1000)` with ms→s reconciled (a known-answer case pins ≈310×), it is **not** asserted to exceed 1,000×, and it is **never** computed by dividing a per-wingbeat cost by a per-row latency (the units-mismatch that would fabricate a ~10⁶× number)

#### Scenario: On-figure caption is compact; full disclosures live in the README

- **Given** the generated figure and its corpus's README
- **When** both are inspected
- **Then** the on-figure caption leads with the positive headline (plotted seed, skill definition and seed count + the >1,000× batched speedup), carries a single terse "Caveats:" line and a single terse quasi-steady-reference line, and points to the README; **and** the README contains the full disclosure set (a skill table for all six targets — plotted seed, seed range, phase-only baseline pointwise R² — equal to `metrics.json`; the configuration-resolved (cycle-mean) R² discussion with its seed record; the statement that skill also rewards amplitude and shape changes; the lab-frame axis caveat, with the wing-frame conversion stated as not currently tracked; the CF_mx/CF_mz exclusion **with their skill**; the quasi-steady reference's omitted-terms / symmetric-rotation / stroke-plane-normal-vs-lab-z / uncalibrated nature and why it is not overlaid; the grid's validation framing; and the speedup batch-size + sequential-CFD decomposition) — so the full honesty content is present and test-enforced off the PNG

#### Scenario: The caption names the plotted seed and the seed count

- **Given** a `metrics.json` whose `seed_sweep.primary_seed` is `n` and whose `seed_sweep.seeds` has `k` entries
- **When** the caption is built
- **Then** it names seed `n` and a range over `k` seeds
- **And** with `k == 1` it states "single seed, no range", never an implied spread
- **And** a `metrics.json` with no `seed_sweep` block raises before any artifact is written

#### Scenario: The fine profile labels the fine grid and its median CFD cost

- **Given** a metrics.json and predictions, the `fine` grid profile and a CFD cost per step `s`
- **When** the caption and speedup are built
- **Then** the throughput factor equals `throughput_rows_per_s × s`, the sidecar's `cfd_seconds_per_wingbeat` equals `s × rows_per_wingbeat`, the caption labels the denominator "fine-grid A40 CFD at its median per-step wall time", states "Fine 256x128x256 grid: agreement with CFD, not with experiment; grid convergence checked only at one wing motion outside this sweep (README).", omits "at this resolution" from the quasi-steady line, points to `examples/prelim_sweep_fine/README.md`, and contains no "coarse", "64x32x64" or "pipeline readiness"

#### Scenario: The default profile reproduces the coarse figure byte for byte

- **Given** the committed coarse predictions and metrics.json, the same digest and timestamp
- **When** the figure is generated with no grid argument by this change's code and by the code before it, in one environment
- **Then** the two `evidence_figure.png` files and the two `evidence_figure_metrics.json` files are byte-identical

### Requirement: Committed evidence-figure artifacts with provenance

The figure generator SHALL produce three artifacts under the corpus's `figures/` directory (`examples/prelim_sweep/figures/` or
`examples/prelim_sweep_fine/figures/`): the
`evidence_figure.png`, an `evidence_figure_metrics.json` carrying the per-axis surrogate RMSE, the
quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), the plotted seed
(`primary_seed`) and seed count (`n_seeds`), for **all six** targets the skill over the phase-only
baseline (`skill.<c>` with `committed`, `min`, `max`), the surrogate's pointwise R²
(`pointwise_r2.<c>`) and the phase-only baseline's pointwise R² (`phase_baseline_pointwise_r2.<c>`),
the skill floor (`skill_floor` with its `value` and `targets_below_phase_baseline`), so that every
number the caption prints is recorded, and the speedup-derivation inputs (the batched throughput,
the per-config rows-per-wingbeat, the CFD per-wingbeat cost used (`cfd_seconds_per_wingbeat`), the single-row latency, and both
realized factors with their units); and a `run_metadata.json` emitted via
`capture_surrogate_run_metadata` requiring a pinned container **digest** and a **caller-supplied**
timestamp (CC-1), recording the hash of the consumed inputs (the predictions parquet and
metrics.json) and the seeds read from `metrics.json` `seed_sweep`, plus the grid profile name (`grid`), the CFD
cost per step supplied (`cfd_seconds_per_step`, `null` for a fixed-cost profile) and the CFD
per-wingbeat cost used (`cfd_seconds_per_wingbeat`); a record without those keys (the committed
coarse figure's, which predates them) SHALL be read as `coarse` / 144 s. The `fine` profile requires
a CFD cost per step and has no default; the `coarse` profile's cost is fixed at 144 s per wingbeat
and it takes no per-step cost. Generation with a missing fine per-step cost, a non-finite or
non-positive one, a per-step cost for the coarse profile, or an unknown profile name SHALL raise
`ValueError` before any artifact is written. The caption builder SHALL likewise reject a speedup
whose per-wingbeat cost does not fit its profile (the coarse label over a cost other than 144 s,
or the fine label over 144 s). The sidecar key set SHALL be the same for both profiles. The sidecar SHALL NOT carry
configuration-resolved R², which the figure no longer displays. The JSON sidecars SHALL be written
**LF-newline UTF-8** (as `write_units_sidecar` does) so the committed artifacts do not churn between
Windows authoring and Linux CI.

#### Scenario: All three artifacts write and re-load with the documented content

- **Given** a figure-generation run into a temporary output directory
- **When** the run completes
- **Then** `evidence_figure.png`, `evidence_figure_metrics.json`, and `run_metadata.json` all exist and re-load, and `evidence_figure_metrics.json` carries the per-axis surrogate RMSE, the quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), `primary_seed`, `n_seeds`, the six targets' `skill`, `pointwise_r2` and `phase_baseline_pointwise_r2`, the `skill_floor`, and the speedup inputs — equal to what the figure displays and to `metrics.json` — and carries no `config_mean_r2` key

#### Scenario: Every number in the caption is in the sidecar

- **Given** a generated figure
- **When** the caption's plotted seed, seed count, phase-only baseline R² values, skill floor and off-panel `CF_mx`/`CF_mz` skill are compared with `evidence_figure_metrics.json`
- **Then** each equals (within display rounding) the sidecar's recorded value

#### Scenario: Provenance records a pinned digest, caller timestamp and the metrics' seeds

- **Given** a container image digest containing `sha256:`, a caller-supplied ISO-8601 timestamp, and a metrics.json with a `seed_sweep` block
- **When** the figure provenance is captured
- **Then** `run_metadata.json` records the git commit, the supplied digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, a hash of the consumed predictions parquet + metrics.json, and seeds equal to `{"global": seed_sweep.primary_seed, "sweep": seed_sweep.seeds[1:]}`

#### Scenario: JSON sidecars are written LF-newline UTF-8

- **Given** the figure-generation run on any host (including Windows)
- **When** `evidence_figure_metrics.json` and `run_metadata.json` are written
- **Then** they use LF line endings and UTF-8 encoding (no CRLF), so the committed artifacts are byte-stable across the Windows authoring host and the Linux CI runner

#### Scenario: Mutable image tag is rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** the figure provenance is captured
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording provenance without a pinned image

#### Scenario: A fine figure without a CFD cost writes nothing

- **Given** the `fine` grid profile and no CFD cost per step (or 0, a negative value, NaN or inf), the `coarse` profile given a per-step cost, or an unknown profile name
- **When** figure generation is invoked
- **Then** it raises `ValueError` and the output directory contains no artifact

### Requirement: Committed surrogate artifacts are tied to the dataset they were trained on

Training SHALL record, in the surrogate's `run_metadata.json`, the path and sha256 of the dataset
parquet it consumed (`inputs.file` / `inputs.hash`, via the existing `capture_run_metadata`
`inputs_file` channel), so that which corpus produced a committed `surrogate.pt` is auditable rather
than inferred.

A CI-runnable check SHALL reconcile each committed surrogate — the coarse `examples/prelim_sweep/` and the fine
`examples/prelim_sweep_fine/` — against its own corpus's committed dataset **unconditionally**: every `<target>_true` column of `holdout_predictions.parquet`, for all
six targets, equals the corresponding `dataset.parquet` column on `(config_name, time)`, and the
recorded `inputs.hash` equals the sha256 of the committed `dataset.parquet`. Unlike a staleness
banner, this check has no state in which a mismatch is acceptable.

#### Scenario: Training metadata names the dataset

- **Given** a training run over a dataset parquet
- **When** `build_training_metadata` assembles the run's provenance
- **Then** the record's `inputs.file` names that parquet and `inputs.hash` is its sha256

#### Scenario: A surrogate trained on a different dataset fails CI

- **Given** a committed `holdout_predictions.parquet` whose `<target>_true` values for any of the six targets differ from the committed `dataset.parquet`, or a recorded `inputs.hash` that is not the committed parquet's sha256
- **When** the committed-artifact tests run
- **Then** they fail, naming the target or the hash mismatch

### Requirement: Committed training artifacts

The training run SHALL produce four artifacts under the corpus's `surrogate/` directory (`examples/prelim_sweep/surrogate/` or
`examples/prelim_sweep_fine/surrogate/`): a `metrics.json`, a
holdout-**predictions** parquet, a trained **model checkpoint**, and a `run_metadata.json`. The
predictions parquet SHALL carry the holdout identifiers and both true and predicted coefficients so
the downstream figure consumes a versioned prediction file rather than re-running inference.

#### Scenario: Predictions parquet schema

- **Given** a completed holdout evaluation
- **When** the predictions parquet is written and re-read
- **Then** it has columns `config_name, time, phase, wingbeat` plus, for each of the six coefficients, a `CF_*_true` and a `CF_*_pred` column, with one row per scored holdout (config × timestep) on the converged beat
- **And** every `config_name` in the predictions parquet is one of the 6 holdout configuration names (no train/validation row leaks into the predictions file)

#### Scenario: All four artifacts are written

- **Given** a full training driver run into a temporary output directory
- **When** the run completes
- **Then** `metrics.json`, the holdout-predictions parquet, the model checkpoint, and `run_metadata.json` all exist and re-load, and the parquet's true coefficients match the dataset's holdout `CF_*` values for the same (config, timestep) rows

### Requirement: Force-only training scope guard

The trainer SHALL consume **only** the tidy `dataset.parquet` (kinematics + phase + coefficients) and
SHALL NOT read AMReX plotfiles or velocity/pressure fields, build a DoMINO/latent-dynamics encoder,
or integrate any RL loop (CC-6). It is the instantaneous kinematics(+phase) → force-coefficient
regressor only.

#### Scenario: Training consumes only the dataset parquet

- **Given** the training inputs
- **When** the trainer runs
- **Then** it requires only the corpus's `dataset.parquet` (`examples/prelim_sweep/` or `examples/prelim_sweep_fine/`, and its units sidecar) — it neither accepts nor requires a plotfile/field path — and it produces force-coefficient predictions only, with no field reconstruction, no latent-dynamics state, and no RL interaction
