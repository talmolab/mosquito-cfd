## MODIFIED Requirements

### Requirement: Config-resolved (phase-honest) evaluation metrics

The surrogate evaluation SHALL additionally report **config-resolved** metrics in `metrics.json`,
because the pointwise aggregate R² is dominated by the within-beat force **waveform** — a smooth
periodic shape shared across all configurations and therefore largely "free" to learn — and on its
own **overstates** the surrogate's skill at the kinematics→force *map* (the genuinely held-out
config-to-config dependence) (CC-4 scientific honesty). The evaluation SHALL carry, per target, a
`config_resolved` block reporting (a) `config_mean_r2` — the R² computed on the per-configuration
**cycle-mean** coefficient (the phase-removed config-to-config score) — and (b)
`within_config_variance_fraction` — the fraction of total holdout variance that is
within-configuration (the waveform), which exposes how much of the aggregate R² is waveform-driven.
These SHALL be pure-numpy, computed on the inverse-transformed predictions grouped by `config_name`,
and reported **alongside** (never instead of) the aggregate.

`config_mean_r2` is a diagnostic, not the surrogate's headline skill. It divides by the spread of only
a few held-out configurations' cycle means, which is near zero for some targets, so it can swing from
strongly negative to positive between training seeds. Wherever a headline skill number is reported,
it SHALL be the skill over the phase-only baseline ("Phase-only baseline skill in metrics.json"), not
`config_mean_r2`.

#### Scenario: config_resolved block is present per target

- **Given** a completed holdout evaluation
- **When** `metrics.json` is written and re-read
- **Then** it contains a `config_resolved` block keyed by `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`, each carrying a `config_mean_r2` and a `within_config_variance_fraction` — distinct from, and reported in addition to, the pointwise `per_target`/`aggregate` blocks

#### Scenario: config_mean_r2 is reported but never headlined

- **Given** a `metrics.json` carrying both a `config_resolved` block and a `phase_baseline_skill` block
- **When** the evidence figure's caption and sidecar are built from it
- **Then** they report the skill over the phase-only baseline, contain no `config_mean_r2` value, and `config_mean_r2` stays in `metrics.json` and the corpus README

#### Scenario: config-resolved quantities match known-answer arrays

- **Given** two configurations whose true coefficients are `[1, 3]` (mean 2) and `[5, 7]` (mean 6), with predicted per-configuration cycle-means of `2` and `5`
- **When** the config-resolved metrics are computed
- **Then** `within_config_variance_fraction == 0.2` (within-config SS 4 / total SS 20) and `config_mean_r2 == 0.875` (`1 - 1/8`) — exact known answers, confirming the phase/config decomposition is correct and not a re-label of the inflated aggregate

#### Scenario: A constant per-configuration mean yields the R² sentinel, not garbage

- **Given** holdout configurations whose per-configuration cycle-means are (near-)identical (zero between-config variance)
- **When** `config_mean_r2` is computed
- **Then** it is the documented NaN sentinel (serialized as `null`) rather than an unhandled `0/0`, consistent with the pointwise R² sentinel (the **scale-relative** `_VARIANCE_EPS` floor, `SS_tot ≤ _VARIANCE_EPS · Σt²`, which fires on genuine constancy at any magnitude but does **not** null a tiny-but-real between-config spread — e.g. a near-zero-by-symmetry target keeps its honest, possibly negative, R²)

#### Scenario: Degenerate config-resolved inputs are handled

- **Given** either a **single** holdout configuration (no between-config variance) or a **zero-row** input
- **When** `compute_config_resolved` is called
- **Then** the single-configuration case yields the `config_mean_r2` sentinel (`null`) with `within_config_variance_fraction == 1.0` (all variance is within-config by definition), and a zero-row input raises `ValueError` (parity with `compute_metrics`) rather than emitting a NaN-with-`RuntimeWarning`

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
the corrected van Veen normalization the model's RMS ratio `rms(CF_trans)/rms(CFD-true CF_z)` is reported
as measured, with no bound and no direction asserted: whether the model's RMS is above or below the
CFD lift's is a property of the corpus, read from `evidence_figure_metrics.json`, and this
requirement states neither. The figure SHALL record
this RMS ratio (key `overshoot_factor`; the name is historical and asserts no direction) and the baseline RMSE in `evidence_figure_metrics.json`, and
the caption SHALL disclose the ratio neutrally (the model is ~X× the CFD lift in RMS, the lift
named for the figure's grid profile: "coarse-grid CFD lift" or "fine-grid CFD lift", in both
the caption and the sidecar `note`) and that the
uncalibrated translational model is therefore **not used as a quantitative baseline** — "at this resolution" on the coarse profile; the fine
profile omits that phrase and does not give the grid as the reason.

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

#### Scenario: The quasi-steady RMS ratio is recorded and disclosed, not presented as a baseline

- **Given** the computed Sane–Dickinson reference and the CFD-true CF_z
- **When** the sidecar and caption are built
- **Then** `evidence_figure_metrics.json` records the reference's `overshoot_factor` (the RMS ratio `rms(CF_trans)/rms(CFD-true CF_z)`, a positive finite number, reported as measured with no bound asserted for either profile) and `baseline_rmse_cf_z`, and the caption states neutrally that the uncalibrated translational quasi-steady model is ~X× the coarse-grid (or, for the fine profile, fine-grid) CFD lift in RMS and is **not used as a quantitative baseline** — "at this resolution" on the coarse profile; the fine profile omits that phrase (it is not framed as a comparison the surrogate "beats")

#### Scenario: No diffused-IB underestimate claim remains

- **Given** the evidence-figure module docstring, caption strings, `_baseline_reference` docstring, the `evidence_figure_metrics.json` `note`, and the `Sane–Dickinson` rationale text
- **When** they are inspected
- **Then** none contains a "~2.4× diffused-IB underestimate" (or equivalent CFD-is-biased-low) claim and no post-hoc correction factor — the quasi-steady reference's RMS ratio is described neutrally (translational-only model, a poor fit; the ratio is stated as measured, with no claim that the model over- or under-predicts the CFD lift)

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
configuration-resolved R² (which divides by the near-zero spread of the held-out configurations' cycle means for some targets
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
configuration's rows per wingbeat, labelled as a median per-step time) — which is the >1,000× claim. The surrogate
is a pointwise map that batches; the CFD is an **inherently sequential** time integration that
cannot. The parallelism factor is `throughput_speedup ÷ latency_speedup` by definition, and equals
`N · t_single / t_batch` for a batch of `N` rows: a ratio of two separately measured timings, which
can be larger or smaller than `N`. It SHALL NOT be stated or computed as the batch size. The
annotation SHALL disclose,
in the caption's words "N=<batch> parallel evals vs sequential <the profile's CFD label>", that
it is **batched GPU throughput at the stated batch size (`N` = the sidecar's `speedup.batch_size`)
versus a sequential A40 CFD timestep rate on the figure's grid** — not a per-evaluation speedup. The
conservative per-evaluation **latency** speedup SHALL be reported alongside as the like-for-like
floor, on both profiles, whether or not it exceeds 1,000× (it is not asserted to); it SHALL NOT be
conflated with the throughput claim or computed by dividing a per-wingbeat cost by a per-row
latency. All caption/annotation numbers SHALL be read from the committed artifacts, never
hard-coded. The caption SHALL name the seed of the plotted model (`metrics.json`
`seed_sweep.primary_seed`) and the number of seeds its skill ranges span; it SHALL NOT present one
draw as the corpus's skill, it SHALL state "single seed, no range" when the sweep has one seed, and a
`metrics.json` without `seed_sweep` SHALL be rejected rather than captioned with a default seed.

> Note: this requirement states no corpus result. The example numbers in its scenarios are the
> synthetic test fixture's known answers, labelled as such; the corpus's own speedups and batch size
> are read from `evidence_figure_metrics.json`.

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
- **Then** the annotated factor equals `throughput_rows_per_s / cfd_rows_per_s` (the synthetic test fixture — `throughput_rows_per_s = 5.17e7`, 2000 rows per wingbeat, a 12,535-row batch — pins the exact factor 5.17e7 ÷ (2000/144) ≈ 3.72e6; these are fixture values, not corpus results), the realized factor exceeds 1,000×, the annotation labels the denominator "coarse-grid A40 CFD" **and discloses the batch size and that the CFD rate is sequential**, and `evidence_figure_metrics.json` records both throughputs, the per-config rows-per-wingbeat, the batch size, and the parallelism factor (`throughput_speedup ÷ latency_speedup`, measured, not the batch size) so the headline is fully decomposable

#### Scenario: The single-row latency speedup is reported honestly and not conflated with the headline

- **Given** `metrics.json inference.latency_ms` (single-row latency, ms) and a config's per-row CFD cost `CFD_SECONDS_PER_WINGBEAT ÷ rows_per_wingbeat` (where `rows_per_wingbeat = 1/(f*·dt)` is **per-config**, not a constant)
- **When** the latency speedup is computed
- **Then** it equals `t_cfd_per_row / (latency_ms/1000)` with ms→s reconciled (the synthetic test fixture's `latency_ms = 0.232` at 2000 rows per wingbeat pins the known answer ≈310×; a fixture value, not a corpus result), it is **not** asserted to exceed 1,000×, and it is **never** computed by dividing a per-wingbeat cost by a per-row latency (the units-mismatch that would multiply the latency speedup by the rows per wingbeat)

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

### Requirement: Re-normalization preserves surrogate skill (scale-invariance)

Re-deriving force/moment coefficients under a different per-configuration normalization-scale convention SHALL rescale the CFD targets and the surrogate predictions by the **same** constant,
leaving the held-out **R²** and the predicted-vs-CFD relationship invariant. Throughout this
requirement the convention factor is `k = f_ref_old / f_ref_new`; because `CF = F / f_ref`, the
re-normalized coefficient is `CF_new = k · CF_old`, so going from the old convention to the new one
**multiplies** every coefficient by `k` and going back **divides** by it. The committed
`holdout_predictions.parquet` has held the new (van Veen) convention since #36, when every `CF_*`
column was multiplied by exactly `k` (`k = f_ref(R_TIP) / f_ref(R_GYRATION) = (R_TIP / R_GYRATION)²`,
≈ 3.120), so re-expressing it on the old (peak-tip, `F_ref(R_TIP)`) reference divides by `k`. That
re-expression changes the normalization only. It is not the corpus as it was before #36: the raw
columns were regenerated since, to fix a geometry defect rather than as a re-normalization
(`fix-force-surrogate-sweep-hinge`), and the moment reference point
and the sign changed (`fix-moment-reference-hinge`, `fix-wing-force-sign-convention`). The frozen corpus's raw
force/moment columns and IB-particle CSVs SHALL NOT be regenerated for a re-normalization convention
change; only derived coefficients change, and no surrogate retraining SHALL be required for that case.

A change of force/moment **sign** convention (`fix-wing-force-sign-convention`, #109) is this scale
case with `k = −1`: the raw columns stay frozen, every `CF_*` becomes exactly `−CF_old` (`k = −1` is
its own inverse, so multiplying and dividing by it agree), and the
held-out R² and phase-baseline skill are invariant, so no retrain is *required*. That change
nevertheless retrains both surrogates **by decision**, so that every committed surrogate is
reproducible by the trainer from its committed dataset; it is neither a raw-corpus regeneration nor an
exception to the frozen-corpus guarantee below.

This invariance is a property of **scale** conventions specifically. A change of moment **reference
point** is not a scale change: the parallel-axis shift `M_hinge = M_origin + (r_origin − r_hinge) × F`
is affine and row-dependent, so the corrected column is **not** the old one times a constant, the
held-out R² is **not** preserved, and retraining **is** required. Such a change SHALL be treated as a
documented exception on the same footing as a geometry-defect fix.

This frozen-corpus guarantee has exactly **two** documented exceptions.
`fix-force-surrogate-sweep-hinge` regenerated the raw corpus once to correct a wing-hinge geometry
defect present in every configuration since the corpus was first generated (the hinge was frozen from
a pre-refactor deck against a geometry file that had since moved to a new axis convention).
`fix-moment-reference-hinge` re-derived the moment coefficients about the wing hinge, leaving the raw
columns untouched but requiring a retrain. Neither is a
precedent for routine re-runs — any future raw-corpus regeneration, or any further reference-point
change, requires its own equally explicit, equally documented exception.

#### Scenario: R² is invariant under re-normalization

- **Given** the committed `examples/prelim_sweep/surrogate/holdout_predictions.parquet` (`CF_x_true/pred`, `CF_z_true/pred`, …), already in the new (van Veen) convention, whose `R²` matches `metrics.json`
- **When** both the `*_true` and `*_pred` columns are re-expressed on the old (peak-tip) reference by dividing them by the convention factor `k = f_ref_old / f_ref_new` (≈ 3.120)
- **Then** the recomputed per-target `R²` for `CF_x` and `CF_z` each equals the committed one within `1e-9`, confirming no retrain is needed
- **And** the `RMSE`/`MAE` on the old reference are the committed ones divided by `k`, within `1e-9` relative (reported honestly), while the scatter shape is unchanged (axes relabeled)

#### Scenario: Raw corpus stays frozen under re-normalization; only derived coefficients move

- **Given** a re-normalization convention change (not a geometry-defect fix, and not a change that retrains by decision such as `fix-wing-force-sign-convention`) re-derives the corpus coefficients
- **When** `dataset.parquet` is regenerated
- **Then** its raw `Fx, Fy, Fz, Mx, My, Mz` column **values** are exactly equal (e.g. `pandas.testing.assert_frame_equal(..., check_exact=True)`) to the committed corpus, only the derived `CF_*` columns change (each new column equals the old multiplied by `k`), and the committed `metrics.json` per-target `R²` is reused unchanged (within `1e-9`)

#### Scenario: Degenerate re-normalization is rejected

- **Given** a convention factor that is undefined — `f_ref_new = 0` (so `k` divides by zero) or a `holdout_predictions.parquet` missing a required `CF_*_true`/`CF_*_pred` column
- **When** the scale-invariance check is run
- **Then** it raises `ValueError` (or `KeyError` for the missing column) rather than emitting `inf`/`NaN` R² or silently skipping the target

#### Scenario: A documented geometry-defect fix is the sole exception to the frozen-corpus guarantee

- **Given** the corpus's raw force columns were generated from a deck with an incorrect wing-hinge placement (a geometric defect, not a normalization-convention choice)
- **When** the corpus is regenerated to fix that defect
- **Then** the regeneration is accompanied by an OpenSpec change (`fix-force-surrogate-sweep-hinge`) that names the defect, and this requirement's "SHALL NOT be regenerated" clause is understood to apply to normalization-convention changes, not to this documented correctness exception

#### Scenario: A reference-point change is not scale-invariant and does require a retrain

- **Given** the moment reference point moves from the particle origin to the wing hinge, so `CF_mx`/`CF_mz` are re-derived via a parallel-axis shift while the raw `Mx/My/Mz` columns stay frozen
- **When** the corrected corpus is compared with the committed one
- **Then** the new `CF_mx` column is **not** the old one times any constant (`CF_mx_new / CF_mx_old` is not constant across rows), so the R²-invariance argument does not apply and the committed `metrics.json` SHALL NOT be reused
- **And** the surrogate is retrained, because the model is a single shared-trunk multi-output network whose remaining targets' predictions also move
- **And** the raw `Fx..Mz` columns remain exactly equal to the committed corpus, so the frozen-raw-corpus guarantee itself is not breached

#### Scenario: A sign-convention change is the k = −1 scale case

- **Given** the corpus re-extracted by `fix-wing-force-sign-convention`
- **When** it is compared with the corpus committed before that change
- **Then** the raw `Fx..Mz` column values are exactly equal, and every `CF_*` column is the negation of the old one (`k = −1`), as verified by "Sign re-extraction and retrain pass pre-registered gates"
- **And** the frozen raw-force sha256 pins hold, so the change is not counted among the frozen-corpus exceptions

### Requirement: Post-run acceptance gate blocks dataset construction on an unverified corpus

A corpus SHALL pass an acceptance gate **after** run metadata is generated and **before** the tidy
dataset is built, so a truncated, duplicated or unverified run can never reach a committed
`dataset.parquet`.

The gate SHALL fail if, for any configuration: the run's observed interior timesteps fell below the
deck's declared `ns.fixed_dt`; the force CSV's deduplicated row count does not equal the manifest's
`max_step`; or `time` is not strictly increasing.

The gate's physical check SHALL be a **normalized** cycle-symmetry ratio — the magnitude of the
settled-beat mean lab-frame `CF_x` divided by that configuration's settled-beat peak `|CF_x|` —
rather than an absolute mean. It is a backstop behind the timestep and row-count checks above, which
are the gate's primary defences against truncation. The absolute settled-beat mean is not zero on a
healthy corpus: it grows with pitch amplitude, so a tolerance on it confounds pitch amplitude with
truncation. Dividing by the configuration's settled-beat peak reduces that dependence; it does not
remove it. The tolerance and the healthy and materially-truncated magnitudes it separates are
recorded beside `SYMMETRY_RATIO_TOLERANCE` and in `add-fine-corpus-run-verification` design D6; this
requirement states none of them and claims no separation factor.

The gate SHALL additionally fail if a mandatory pre-flight check has **no recorded result** for the
corpus. An absent result SHALL be treated as a failure, not a warning, because an unrecorded check is
indistinguishable from one that was never run.

The gate SHALL recompute at least one of its quantities directly from the raw run output rather than
reading every value back from the metadata file it is gating, so an error in the metadata generator
cannot certify its own corpus.

The gate SHALL be runnable offline against committed artifacts plus the run's output, with no cluster
or Argo access.

#### Scenario: A CFL-limited config fails the gate

- **Given** a corpus in which one configuration's observed interior timesteps fell below its
  declared `ns.fixed_dt` (a CFL-limited run)
- **When** the acceptance gate runs
- **Then** it fails, naming that configuration and its observed minimum timestep

#### Scenario: A corpus with duplicate timesteps fails the gate

- **Given** a corpus whose force CSV deduplicated row count does not equal its manifest `max_step`
- **When** the acceptance gate runs
- **Then** it fails, naming the configuration and both counts

#### Scenario: A sufficiently truncated config fails the normalized symmetry check

- **Given** a configuration whose settled wingbeat is covered only in part (a run that stopped early, or a CFL-limited run whose steps covered less simulated time), enough that its settled-beat mean is no longer near zero relative to its peak
- **When** the acceptance gate runs
- **Then** its normalized cycle-symmetry ratio exceeds the stated tolerance and the gate fails
- **And** the symmetry check is not claimed to catch every truncation: a milder one can stay within the tolerance, and is caught (if at all) by the observed-timestep or row-count check, so a configuration within the symmetry tolerance whose observed timesteps fell below its declared `ns.fixed_dt` still fails the gate

#### Scenario: A missing mandatory-check result fails the gate

- **Given** a field-capture corpus whose provenance records no CC-F1 result
- **When** the acceptance gate runs
- **Then** it fails, stating that the required check has no recorded outcome

#### Scenario: A healthy corpus passes

- **Given** a corpus where every configuration held its declared timestep, has deduplicated
  `rows == max_step`, strictly increasing `time`, a normalized symmetry ratio within tolerance, and a
  recorded CC-F1 result
- **When** the acceptance gate runs
- **Then** it passes

#### Scenario: The gate does not certify itself from the metadata it is gating

- **Given** a corpus whose metadata JSON has been hand-edited to claim a passing row count
  (`timing.timesteps` set to the manifest's `max_step`) while the underlying raw force CSV
  actually has fewer distinct timesteps
- **When** the acceptance gate runs
- **Then** it fails, because it recomputes the row count from the raw force CSV (via the same
  `build_dataset` code path used to build the real dataset) rather than trusting the metadata's
  claim

**Note:** `interior_dt_below_nominal` itself is the one value the gate takes on trust from
`run_metadata_<config>.json` — it cannot be recomputed offline without the run's `run.log`
(not committed to the corpus). The normalized symmetry check (scenario "A sufficiently truncated config fails the normalized symmetry check") is the gate's
defense-in-depth against exactly this metadata-generation risk, not a re-derivation of the
timestep check itself (`add-fine-corpus-run-verification` design D6).

### Requirement: Committed corpora are guarded by cluster-free reconciliation tests

Each committed corpus SHALL be guarded by tests that reconcile the committed artifacts against their
**manifest and physical invariants**, not merely against themselves, and that run offline with no
cluster, GPU or Argo access.

The guards SHALL be driven by an explicit registry of committed corpora rather than a directory glob,
so that a corpus which is expected to carry a `dataset.parquet` but does not is a loud failure rather
than a silently skipped test. A corpus that legitimately has no parquet yet SHALL be registered as
such, and the manifest- and deck-level guards SHALL still apply to it.

The guards SHALL assert, per registered corpus: the parquet's column set and order match the
documented schema; each configuration's row count equals its manifest `max_step`; `time` is strictly
increasing within each configuration; no NaN or Inf in any numeric column; the holdout set equals the
manifest's recorded holdout names; the units sidecar's keys match the parquet's measured columns;
each configuration's deck `max_step` equals its manifest `max_step`; and, for corpora that carry
per-config run metadata, that every parquet configuration has a corresponding metadata file.

The guards SHALL include at least one **physical** invariant that internal-consistency checks cannot
provide: the settled-wingbeat normalized cycle-symmetry ratio SHALL be within a stated tolerance,
with the tolerance recorded alongside the measured healthy maximum and materially-truncated minimum that bound
it.

#### Scenario: Row count is reconciled against the manifest, not the data

- **Given** a registered corpus
- **When** the guard runs
- **Then** each configuration's parquet row count is compared against that configuration's
  `max_step` read from `sweep_manifest.json`

#### Scenario: Deck and manifest max_step cannot silently diverge

- **Given** a registered corpus
- **When** the guard runs
- **Then** each configuration's generated deck `max_step` equals its manifest `max_step`

#### Scenario: A sufficiently truncated corpus is caught by the normalized symmetry invariant

- **Given** a corpus containing a configuration whose settled wingbeat is covered only in part, enough that its settled-beat mean `CF_x` is no longer near zero relative to its peak
- **When** the symmetry guard runs
- **Then** it fails, because that configuration's normalized cycle-symmetry ratio exceeds tolerance
- **And** a milder truncation that stays within the tolerance is not claimed to be caught by this guard; the row-count reconciliation against the manifest catches a run that stopped early, and the acceptance gate's timestep check catches a CFL-limited run (whose step count is complete)

#### Scenario: Units sidecar cannot silently drift from the parquet

- **Given** a registered corpus's parquet and its units sidecar
- **When** the guard runs
- **Then** the sidecar's key set equals the parquet's measured (non-categorical) column set

#### Scenario: No NaN or Inf in any numeric column

- **Given** a registered corpus's parquet
- **When** the guard runs
- **Then** no numeric column contains NaN or Inf

#### Scenario: Holdout set matches the manifest exactly

- **Given** a registered corpus's parquet and its `sweep_manifest.json`
- **When** the guard runs
- **Then** the parquet's `split == "holdout"` configuration names equal the manifest's recorded
  holdout names exactly

#### Scenario: The per-config-metadata guard is scoped to corpora that declare it

- **Given** the coarse corpus, which is registered `has_per_config_metadata: false` and carries only
  a dataset-build `run_metadata.json`, no per-config `run_metadata_<config>.json` files
- **When** the guard runs
- **Then** it does not fail on the coarse corpus's absence of per-config metadata files
- **And** it does fail on a corpus registered `has_per_config_metadata: true` that is missing one

#### Scenario: A corpus missing an expected parquet fails loudly

- **Given** a corpus registered as carrying a `dataset.parquet` whose parquet is absent
- **When** the guard runs
- **Then** it fails naming that corpus, rather than skipping

#### Scenario: Guards run without cluster access

- **Given** a checkout with no cluster credentials and no GPU
- **When** the guard tests run
- **Then** they execute and pass against the committed corpora, and the guard module imports no
  cluster, Argo or subprocess surface

## ADDED Requirements

### Requirement: Guards on specification text read the effective specification

A test that guards the text of an OpenSpec specification SHALL read its **effective** text: the
live `openspec/specs/<capability>/spec.md` with every active (unarchived) change's delta for that
capability applied. A `MODIFIED` requirement replaces the live block of the same name, a `REMOVED`
one drops it, and an `ADDED` one is appended; a `MODIFIED` or `REMOVED` name absent from the live
specification, or an `ADDED` name already present, SHALL raise. Reading the effective text makes the
guard hold on a proposal branch, where only the delta carries the new text, and after archiving,
where the live specification does.

When more than one active change modifies the same requirement, the effective text SHALL carry
every variant, so a whole-specification scan reads each of them. A requirement whose numbers are
checked individually (see "Data-dependent claims in the live specs are guarded against committed
data") SHALL make building that requirement's text for the per-number check raise, naming both
changes, rather than check one variant.

`RENAMED` sections SHALL raise as unsupported. A delta section other than `ADDED`, `MODIFIED` or
`REMOVED` (for example a cross-reference list) ends the preceding block and is not applied.

#### Scenario: A delta replaces, drops or appends a block

- **Given** a live specification and an active change whose delta has a `MODIFIED`, a `REMOVED` and an `ADDED` requirement
- **When** the effective text is built
- **Then** the modified block replaces the live one, the removed block is absent, the added block is present, and every other live block is unchanged

#### Scenario: Archived changes and other capabilities are ignored

- **Given** a change under `openspec/changes/archive/` and an active change whose deltas are for other capabilities only
- **When** the effective text of this capability is built
- **Then** neither contributes

#### Scenario: Inconsistent deltas raise

- **Given** a delta that modifies or removes a requirement absent from the live specification, adds one already present, or renames one
- **When** the effective text is built
- **Then** it raises, naming the change and the requirement

#### Scenario: Two changes modifying one requirement

- **Given** two active changes that both modify the same requirement
- **When** the effective text is built
- **Then** both variants are present for a whole-specification scan, and building the text of that requirement for a per-number check raises, naming both changes

### Requirement: Data-dependent claims in the live specs are guarded against committed data

A cluster-free test SHALL guard the force-surrogate and flapping-wing-validation specifications
against the failure of issue #115: a number measured from a committed corpus, frozen into a
requirement or scenario, that silently stops matching when the corpus is rebuilt. It SHALL read the
effective text ("Guards on specification text read the effective specification") and have two
parts.

- **Retired claims.** Each retired phrase is a pattern in the test module's `RETIRED` list,
  paired with the stale sentences it was written against (`RETIRED_EXAMPLES`). Every pattern
  SHALL match its stale sentence, SHALL match nothing in the effective text of either
  specification, and SHALL NOT match the corrective sentences that replaced it. Each specification
  SHALL also contain a fixed positive anchor, so the check cannot pass on an empty or wrong file.
  The same check SHALL cover the code docstrings that repeated a retired claim.
- **Enumerated numbers.** For every requirement named in the test module's `GUARDED` list,
  every number in the requirement's effective text SHALL
  be listed in a registry with the phrase that contains it, and each entry SHALL be one of:
  **recomputed** (recomputed from a committed artifact or a code constant, and equal to the printed
  number at its printed precision and notation), **fixture** (recomputed in the same way from the
  synthetic test fixture the scenario names), or **declared** (not a measured result, such as a
  tolerance, a grid size or a synthetic known-answer input, with its reason in the registry). A
  number in the text with no entry, an entry whose number or phrase is absent, or a recomputed or
  fixture value that no longer prints as written SHALL fail the guard, naming the requirement, the
  number and the phrase.

A number SHALL NOT stay in a guarded requirement unless it is recomputed, fixture or declared; a
corpus result whose specific value is not the point SHALL be deleted instead, and the behaviour it
illustrated stated without it.

#### Scenario: A retired claim fails the guard

- **Given** the effective text of either specification, or a guarded code docstring
- **When** a retired claim's stale sentence is inserted into it
- **Then** the guard fails, naming the pattern and the file

#### Scenario: Retired patterns accept the corrective text

- **Given** each corrective sentence recorded in the test module's `MUST_PASS` list
- **When** the retired patterns are applied to it
- **Then** none matches

#### Scenario: The pre-change text fails the guard

- **Given** the stale text of the guarded requirements as it stood before issue #115 was fixed, kept as committed test fixtures
- **When** the retired-claim and enumerated-number checks run on it
- **Then** they report every stale site recorded for those fixtures

#### Scenario: An unregistered, missing or stale number fails the guard

- **Given** a guarded requirement's effective text
- **When** it gains a number with no registry entry, loses a registered number or phrase, or a recomputed or fixture source changes so that its value no longer prints as written
- **Then** the guard fails, naming the requirement, the number and the phrase

#### Scenario: Each source of a recomputed number is load-bearing

- **Given** a recomputed or fixture registry entry
- **When** either the text's number or the source's value is drifted alone (the source through a monkeypatched module attribute read at call time)
- **Then** the guard fails, so the check cannot be re-pointed at a source that happens to agree
