## ADDED Requirements

### Requirement: Phase-only baseline skill in metrics.json

The trainer SHALL report, per target, the surrogate's **skill over a phase-only baseline**,
`skill = 1 − SSE(surrogate) / SSE(phase-only baseline)` over the scored holdout rows, in a top-level
`metrics.json` block `phase_baseline_skill`, because pointwise R² alone is dominated by the wingbeat
waveform that a predictor knowing only the phase already captures (CC-4).

The phase-only baseline SHALL be built from the `split == "train"` configurations only (all of them,
independent of the seed's validation carve; never a holdout row), on the converged beat
(`wingbeat ≥ CONVERGED_MIN_WINGBEAT`): each converged beat, sorted by phase, is periodically
interpolated (`period = 1`) to the query phases; a configuration's curve is the mean of its beats'
curves; the baseline is the **equal-weight** mean of the configuration curves. The block SHALL record
the baseline's definition (`kind`, `reference_split`, `reference_configs`, `weighting`,
`converged_min_wingbeat`) under `phase_baseline` and, per target, `skill`, `phase_baseline_rmse` and
`phase_baseline_r2`. Skill SHALL NOT be clipped; if the baseline's SSE is at or below the
scale-relative `_VARIANCE_EPS · Σ t²` floor, skill SHALL be the NaN sentinel serialized as `null`.
The computation SHALL be pure numpy/pandas (torch-free, CI tier) and SHALL reject malformed input
with `ValueError` rather than emit a NaN.

#### Scenario: Baseline is the equal-weight mean of periodic per-config interpolants

- **Given** two reference configurations sampling known periodic curves at different rates (one with three times the rows of the other), with rows supplied out of phase order
- **When** the baseline is evaluated at query phases including one between a configuration's last sample and phase 1
- **Then** it equals the unweighted mean of the two configurations' periodic linear interpolants at each query phase (known answer), including the wrapped query, so the denser configuration does not dominate and row order does not matter

#### Scenario: Beats are averaged within a configuration and the startup beat is excluded

- **Given** a reference configuration with two converged beats and a startup beat (`wingbeat < CONVERGED_MIN_WINGBEAT`), and a second configuration with one converged beat
- **When** the baseline is built
- **Then** the first configuration contributes the mean of its two converged beats' curves, counted once against the second configuration, and the startup rows have no effect

#### Scenario: Holdout rows never enter the baseline

- **Given** a dataset whose holdout configurations carry extreme coefficients
- **When** the baseline is built
- **Then** it is bitwise identical to the baseline built with the holdout rows removed, and `reference_configs` lists exactly the sorted `split == "train"` configurations

#### Scenario: Skill known answers, sentinel and degenerate input

- **Given** true values, a phase-only baseline prediction and a surrogate prediction
- **When** skill is computed
- **Then** a surrogate equal to the truth scores 1, a surrogate equal to the baseline scores 0, a surrogate with twice the baseline's squared error scores −1 (unclipped), a baseline equal to the truth yields the `null` sentinel, and zero rows or mismatched array shapes raise `ValueError`

#### Scenario: Malformed reference or query data is rejected

- **Given** a reference set with no configurations, a beat with fewer than 2 rows, a duplicate phase within a beat, a non-finite value, or a reference or query phase that is non-finite or outside `[0, 1)`
- **When** the baseline is built
- **Then** it raises `ValueError` naming the problem rather than returning an interpolant

### Requirement: Multi-seed sweep reported by the trainer

The trainer SHALL accept a **primary seed** and zero or more **sweep seeds** (library default: none;
the training driver's default: 1235–1238 after primary 1234). Seeds SHALL be validated before the
dataset is read or the output directory is created. Provenance SHALL be captured before any artifact
is written.
The primary seed SHALL be trained first; only its checkpoint, holdout predictions and inference
timing SHALL be written; sweep seeds SHALL contribute metrics only. All four artifacts SHALL be
written only after every seed has finished, so a failure in any seed writes nothing. `metrics.json`
SHALL carry a top-level `seed_sweep` block with `primary_seed`, `seeds` (primary first), one `runs`
entry per seed (its `val_configs` and, per target, `skill`, `r2`, `rmse` and `config_mean_r2`), and a
per-target `range` holding the NaN-aware `min`/`max` of each of those statistics over **all** seeds,
computed by the trainer so the figure only reads it. The training `run_metadata.json` SHALL record
the seeds as `{"global": <primary>, "sweep": [<sweep seeds>]}`, with `sweep` an empty list when
there are none.

#### Scenario: Sweep seeds do not change the primary seed's outputs (torch tier)

- **Given** the `train` group installed, on each available torch device (CPU, and CUDA when present)
- **When** the trainer runs once with only the primary seed and once with the same primary seed plus sweep seeds
- **Then** the holdout predictions, the checkpoint tensors, and every `metrics.json` value except the wall-clock `inference` timings and the `seed_sweep` block are identical between the two runs, and the sweep run's `seed_sweep.runs[0]` equals the no-sweep run's `seed_sweep.runs[0]`

#### Scenario: A sweep seed in-process equals the same seed run alone (torch tier)

- **Given** the `train` group installed, on each available torch device
- **When** seed `b` is trained as the primary seed of its own run, and separately as a sweep seed after primary `a`
- **Then** each statistic of the sweep run's `runs` entry for `b` equals the corresponding value of the standalone run exactly

#### Scenario: The primary seed is trained before any sweep seed

- **Given** the per-seed fit replaced by a recorder (torch-free)
- **When** the trainer runs with sweep seeds
- **Then** the recorded order is the primary seed followed by the sweep seeds in the given order

#### Scenario: A failing sweep seed writes nothing

- **Given** a run whose second seed raises during training
- **When** the trainer runs into an empty output directory
- **Then** the error propagates and none of the four artifacts exists in the output directory

#### Scenario: Seed-sweep summary is computed from the per-seed runs

- **Given** per-seed metrics for several seeds, one of which carries a `null` statistic
- **When** the `seed_sweep` block is assembled
- **Then** each `range` entry is the min/max over the non-null values of all seeds including the primary, an all-`null` statistic has a `null` range, a single seed has `min == max`, and `seeds` lists the primary seed first

#### Scenario: Duplicate seeds are rejected before anything is read or written

- **Given** a sweep seed equal to the primary seed, or a repeated sweep seed
- **When** the trainer is invoked
- **Then** it raises `ValueError` without reading the dataset or creating any file in the output directory

#### Scenario: The committed sweep is internally consistent with the committed surrogate

- **Given** the committed coarse `metrics.json`, `run_metadata.json`, `holdout_predictions.parquet` and `dataset.parquet`
- **When** the committed-artifact tests run
- **Then** `seed_sweep.seeds` is the primary seed followed by the run_metadata's sweep seeds, each statistic of the primary run entry equals the corresponding top-level value (`per_target`, `config_resolved`, `phase_baseline_skill`), each run's `val_configs` equals the split recomputed from the dataset for that seed, and `phase_baseline_skill` recomputed from the committed dataset and predictions equals the committed values

## MODIFIED Requirements

### Requirement: Predicted-vs-CFD evidence figure on held-out configurations

The force surrogate SHALL provide a local, force-only figure generator that reads the committed
`examples/prelim_sweep/surrogate/holdout_predictions.parquet` and `metrics.json` and emits a
predicted-vs-CFD scatter figure with three panels — **CF_x**, **CF_z**, and **CF_my** — each plotting
CFD-true (x-axis) against surrogate-predicted (y-axis) coefficients over the 6 held-out
configurations (CC-4), with a 1:1 reference line, points distinguished by configuration, and a
per-panel annotation of the **skill over the phase-only baseline** (the plotted seed's value and its
range over the seed sweep), the pointwise R², and the RMSE. The figure SHALL be written to
`examples/prelim_sweep/figures/evidence_figure.png` at **≥200 dpi**. The generator SHALL **read**
the metrics the trainer already computed (phase-only baseline skill, seed-sweep ranges, pointwise R²,
per-target RMSE, inference timing) rather than re-deriving them. Skill and R² SHALL be displayed to
3 decimal places; either value that would display as `1.000` SHALL display as `>0.999`, a nonzero
value that would display as `±0.000` SHALL be displayed in scientific notation, and a range SHALL be
written "lo to hi".

#### Scenario: Figure has three predicted-vs-CFD panels for CF_x, CF_z, CF_my

- **Given** the committed holdout predictions parquet and metrics.json
- **When** the evidence figure is generated
- **Then** the figure contains exactly three scatter panels titled for `CF_x`, `CF_z`, and `CF_my`, each plotting `CF_*_true` on the x-axis against `CF_*_pred` on the y-axis with a 1:1 reference line, and the saved PNG exists at `examples/prelim_sweep/figures/evidence_figure.png` with a resolution of at least 200 dpi

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

### Requirement: Headline moment axis is CF_my, named as a component

The evidence figure SHALL designate **CF_my** as the single headline moment coefficient and SHALL
label its panel as an **"aerodynamic moment (M_y component)"** — it SHALL NOT label the panel
"pitch moment". The figure caption SHALL note that the moments are **lab-frame** components about the
hinge, not wing-frame (biomechanical) moments — that conversion is deferred and not currently
tracked — and therefore the panel reports the moment *component* rather than a biomechanical pitch
interpretation; the figure SHALL NOT apply an unverified sim→biomechanics axis relabeling.

The panel set SHALL be **fixed a priori** rather than re-derived per corpus, so the figure cannot
cherry-pick whichever moment axis scores best. The requirement SHALL NOT assert which moment
scores best: that ranking is corpus-dependent and has already inverted more than once. Instead the
caption SHALL disclose the actual off-panel `CF_mx`/`CF_mz` skill over the phase-only baseline at
call time, read from `metrics.json` and recorded in `evidence_figure_metrics.json`, so a reader can
see the ranking rather than be told it.

#### Scenario: Moment panel is CF_my labeled as a component, not "pitch moment"

- **Given** the evidence figure
- **When** the moment panel is rendered
- **Then** the panel uses the `CF_my` coefficient, its title/label contains "M_y" and the word "moment" but NOT the string "pitch moment", and the figure caption text states that the moment is a lab-frame component and that the wing-frame conversion is not currently tracked

#### Scenario: The off-panel moments are disclosed, not ranked in the spec

- **Given** the metrics.json `phase_baseline_skill` and `seed_sweep` blocks, whatever this corpus's moment ranking happens to be
- **When** the figure is built
- **Then** the headline moment coefficient is `CF_my`, and **no** axis plots a `CF_mx_*` or `CF_mz_*` column at all
- **And** the caption states the off-panel `CF_mx` and `CF_mz` skill values read from `metrics.json`, and `evidence_figure_metrics.json` records the same values, so a corpus in which an off-panel moment outscores the headline is visible to the reader rather than hidden by the frozen panel set

### Requirement: Honest evidence-figure caption and speedup annotation

The evidence figure's disclosures SHALL be **split** to stay both honest **and** legible (a caption
carrying a dozen disclosures fails an evidence figure as surely as a dishonest one): the on-figure
caption SHALL be **compact** — a positive headline (the plotted seed, the definition of skill over
the phase-only baseline and the number of seeds its ranges span, + the >1,000× batched speedup;
the per-axis numbers live on the panels and are not repeated), a single terse "Caveats:" line, a
single terse "Quasi-steady reference (not plotted):" line, and a pointer to
`examples/prelim_sweep/README.md` — and the **full** disclosure set SHALL ALSO live in that README
(task 10.2) and in `evidence_figure_metrics.json`, so honesty is preserved and test-enforced without
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
overlapping seed ranges do not support a ranking); that the result is **pipeline readiness on
coarse-grid forces** (64×32×64), **not** validated aerodynamics; and that the two off-axis moments
**CF_mx/CF_mz are excluded from the panels, with their actual skill (the plotted seed's value and
its seed range) read from `metrics.json` and stated** — the exclusion is stated with its numbers, not silent, and SHALL NOT assert a fixed reason
such as a particular within-beat waveform fraction,
because that ranking is corpus-dependent and has already inverted more than once. The figure SHALL
annotate the inference-vs-CFD speedup as a **batched GPU-throughput** speedup —
`inference.throughput_rows_per_s` ÷ the coarse-grid A40 CFD throughput (per-config converged-beat
rows ÷ the coarse per-wingbeat wall-clock) — which is the >1,000× claim. Because this factor equals
`latency_speedup × batch_size` (the surrogate is a pointwise map that batches; the CFD is an
**inherently sequential** time integration that cannot), the annotation SHALL disclose verbatim that
it is **batched GPU throughput at the stated batch size (N=12,535) versus a sequential coarse-grid
A40 CFD timestep rate** — not a per-evaluation speedup. The conservative per-evaluation **latency**
speedup (~310×, which is **not** >1,000×) SHALL be reported alongside as the like-for-like floor, and
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
- **Then** it names the plotted seed and the five-seed range, defines skill against the phase-only baseline, gives the phase-only baseline's pointwise R² for CF_x/CF_z/CF_my, states that skill also rewards amplitude and shape changes and points to the README for cycle-mean R², states the skill floor over all six targets, states that CF_mx/CF_mz are excluded from the panels **and gives their skill as read from metrics.json**, and frames the figure as coarse-grid pipeline readiness rather than validated aerodynamics — with every number read from metrics.json and no configuration-resolved R² value present

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

- **Given** the generated figure and the updated `examples/prelim_sweep/README.md`
- **When** both are inspected
- **Then** the on-figure caption leads with the positive headline (plotted seed, skill definition and seed count + the >1,000× batched speedup), carries a single terse "Caveats:" line and a single terse quasi-steady-reference line, and points to the README; **and** the README contains the full disclosure set (a skill table for all six targets — plotted seed, seed range, phase-only baseline pointwise R² — equal to `metrics.json`; the configuration-resolved (cycle-mean) R² discussion with its seed record; the statement that skill also rewards amplitude and shape changes; the lab-frame axis caveat, with the wing-frame conversion stated as not currently tracked; the CF_mx/CF_mz exclusion **with their skill**; the quasi-steady reference's omitted-terms / symmetric-rotation / stroke-plane-normal-vs-lab-z / uncalibrated nature and why it is not overlaid; the coarse-grid / not-validated framing; and the speedup batch-size + sequential-CFD decomposition) — so the full honesty content is present and test-enforced off the PNG

#### Scenario: The caption names the plotted seed and the seed count

- **Given** a `metrics.json` whose `seed_sweep.primary_seed` is `n` and whose `seed_sweep.seeds` has `k` entries
- **When** the caption is built
- **Then** it names seed `n` and a range over `k` seeds
- **And** with `k == 1` it states "single seed, no range", never an implied spread
- **And** a `metrics.json` with no `seed_sweep` block raises before any artifact is written

### Requirement: Committed evidence-figure artifacts with provenance

The figure generator SHALL produce three artifacts under `examples/prelim_sweep/figures/`: the
`evidence_figure.png`, an `evidence_figure_metrics.json` carrying the per-axis surrogate RMSE, the
quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), the plotted seed
(`primary_seed`) and seed count (`n_seeds`), for **all six** targets the skill over the phase-only
baseline (`skill.<c>` with `committed`, `min`, `max`), the surrogate's pointwise R²
(`pointwise_r2.<c>`) and the phase-only baseline's pointwise R² (`phase_baseline_pointwise_r2.<c>`),
the skill floor (`skill_floor` with its `value` and `targets_below_phase_baseline`), so that every
number the caption prints is recorded, and the speedup-derivation inputs (the batched throughput,
the per-config rows-per-wingbeat, the coarse CFD per-wingbeat cost, the single-row latency, and both
realized factors with their units); and a `run_metadata.json` emitted via
`capture_surrogate_run_metadata` requiring a pinned container **digest** and a **caller-supplied**
timestamp (CC-1), recording the hash of the consumed inputs (the predictions parquet and
metrics.json) and the seeds read from `metrics.json` `seed_sweep`. The sidecar SHALL NOT carry
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

### Requirement: Cluster-free evidence-figure tests

The figure generator SHALL be tested entirely **cluster-free** (CC-2) — no RunAI, no GPU, no
plotfiles, no `train` dependency-group. Tests SHALL use a tiny synthetic predictions parquet and a
tiny metrics dict, and SHALL assert the quasi-steady-reference formula on known arrays, the
config-name parsing, the CC-3 helper as the single normalization source, the per-panel annotation
values, the figure structure (three scatter axes; a shared config→color legend; **no**
Sane–Dickinson reference series and **no** phase-only baseline curve on any axis; caption/annotation
text present) via the Matplotlib object model (not pixels), the artifact schemas, and the provenance
digest guard.

#### Scenario: Tests run without cluster, GPU, or plotfiles

- **Given** a host with no RunAI access, no GPU, and no plotfiles
- **When** the evidence-figure test suite runs
- **Then** every test executes and passes using only the tiny synthetic parquet/metrics fixtures, with no RunAI call, no CUDA requirement, and no plotfile read

#### Scenario: Figure structure is asserted via the Matplotlib object model

- **Given** a generated figure object
- **When** its structure is inspected
- **Then** the test asserts three scatter axes, a shared config→color legend (one entry per held-out config) with **no** Sane–Dickinson reference series and **no** phase-only baseline curve on any axis (no line or scatter beyond the per-config points and the 1:1 line), and the presence of the caption and per-panel annotation text — without comparing rendered pixels
