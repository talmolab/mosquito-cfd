## ADDED Requirements

### Requirement: Predicted-vs-CFD evidence figure on held-out configurations

The force surrogate SHALL provide a local, force-only figure generator that reads the committed
`examples/prelim_sweep/surrogate/holdout_predictions.parquet` and `metrics.json` and emits a
predicted-vs-CFD scatter figure with three panels — **CF_x**, **CF_z**, and **CF_my** — each plotting
CFD-true (x-axis) against surrogate-predicted (y-axis) coefficients over the 6 held-out
configurations (CC-4), with a 1:1 reference line, points distinguished by configuration, and a
per-panel annotation of the configuration-resolved R² and the RMSE. The figure SHALL be written to
`examples/prelim_sweep/figures/evidence_figure.png` at **≥200 dpi**. The generator SHALL **read**
the metrics the trainer already computed (config-resolved R², per-target RMSE, inference timing)
rather than re-deriving them.

#### Scenario: Figure has three predicted-vs-CFD panels for CF_x, CF_z, CF_my

- **Given** the committed holdout predictions parquet and metrics.json
- **When** the evidence figure is generated
- **Then** the figure contains exactly three scatter panels titled for `CF_x`, `CF_z`, and `CF_my`, each plotting `CF_*_true` on the x-axis against `CF_*_pred` on the y-axis with a 1:1 reference line, and the saved PNG exists at `examples/prelim_sweep/figures/evidence_figure.png` with a resolution of at least 200 dpi

#### Scenario: Only held-out configurations are plotted

- **Given** the predictions parquet (which by construction contains only the held-out configurations — it has **no** `split` column; holdout-ness is the parquet's identity, not a column)
- **When** the scatter points are built
- **Then** every plotted point's `config_name` is one of the held-out configuration names, and the per-panel point count equals the parquet row count for that coefficient (no train/validation rows are introduced)

#### Scenario: Per-panel annotation reports config-resolved R² and RMSE read from metrics.json

- **Given** a metrics.json carrying, for each panel coefficient `<c>`, a `config_resolved.<c>.config_mean_r2` and a `per_target.<c>.rmse`
- **When** the panels are annotated
- **Then** each panel's annotation text contains the configuration-resolved R² (from `config_resolved.<c>.config_mean_r2`) and the RMSE (from `per_target.<c>.rmse`) for that coefficient, equal (within display rounding) to the values read from metrics.json — not hard-coded literals

#### Scenario: A required metrics key or panel coefficient is missing

- **Given** a metrics.json missing a key the figure reads (`config_resolved`, `inference`, or a panel coefficient's `per_target`/`config_resolved` entry), or a predictions parquet missing a panel `CF_*` column
- **When** the figure generation is invoked
- **Then** it raises a clear `KeyError`/`ValueError` naming the missing key or column **before** any artifact is written, rather than emitting a partial or mislabeled figure

#### Scenario: Degenerate prediction sets are rejected, not silently mis-plotted

- **Given** a predictions parquet with **fewer than two** configurations or **zero** rows
- **When** the figure generation is invoked
- **Then** it raises a clear error (the config-resolved scatter and `config_mean_r2` are undefined with <2 configs) rather than writing a misleading single-point or empty figure

### Requirement: Headline moment axis is CF_my, named as a component

The evidence figure SHALL designate **CF_my** as the single headline moment coefficient and SHALL
label its panel as an **"aerodynamic moment (M_y component)"** — it SHALL NOT label the panel
"pitch moment". The figure caption SHALL note that the repository's axis convention differs from the
biomechanics standard (GitHub issue #1) and therefore the panel reports the moment *component* rather
than a biomechanical pitch interpretation. The pick is justified by CF_my being the only moment with
genuine configuration-to-configuration signal (design D1); the figure SHALL NOT apply an unverified
sim→biomechanics axis relabeling.

#### Scenario: Moment panel is CF_my labeled as a component, not "pitch moment"

- **Given** the evidence figure
- **When** the moment panel is rendered
- **Then** the panel uses the `CF_my` coefficient, its title/label contains "M_y" and the word "moment" but NOT the string "pitch moment", and the figure caption text references the issue-#1 axis-convention caveat

#### Scenario: The off-axis (waveform-dominated) moments are not the headline

- **Given** the metrics.json config-resolved block (CF_mx and CF_mz are ~99.9% within-configuration waveform)
- **When** the figure is built
- **Then** the headline moment coefficient is `CF_my`, and **no** axis plots a `CF_mx_*` or `CF_mz_*` column at all — so the headline panel shows a moment with genuine between-configuration variation and the waveform-dominated moments are excluded entirely

### Requirement: Sane–Dickinson quasi-steady baseline overlay

The evidence figure SHALL overlay a **translational-only** Sane–Dickinson quasi-steady baseline on
the **CF_z (lift)** panel and SHALL annotate the baseline's RMSE against CFD-true CF_z alongside the
surrogate's RMSE, so the figure shows the surrogate is at least as good as the analytic model (CC-4).
The baseline SHALL be computed through the **single-source** `compute_force_reference` helper (CC-3)
— the reference force/tip-speed SHALL NOT be re-derived inline — as
`CF_trans(t) = F_trans(t)/F_ref = (U(t)/U_tip)²·C_L(α_eff(t))`, with `U(t)/U_tip = cos(2π·phase)` from
the parquet `phase` column, `C_L(α)` the Dickinson–Lehmann–Sane (1999) empirical fit, and the
per-configuration `(φ, f*, α)` parsed from `config_name`. The baseline SHALL NOT be overlaid on the
moment panel (a translational force model does not predict a moment), and the figure SHALL scope the
baseline to hovering (Sane & Dickinson 2002) and disclose, in the caption, that: the rotational and
added-mass terms are omitted; the AoA uses the **symmetric-rotation** quasi-steady profile fixed by
the prescribed kinematics; the QS lift is defined **stroke-plane-normal** while CFD `CF_z` is the
**lab-z** force (the projections coincide only near mid-stroke); and the baseline is a **zero-parameter
analytic model** present to **bound** the surrogate, **not** a fair-fit competitor (the surrogate is
*fit* to sibling configs of this corpus, so a lower surrogate RMSE shows within-range interpolation,
**not** that ML is more accurate than quasi-steady theory in general).

#### Scenario: Baseline coefficient matches the documented formula on known inputs

- **Given** a configuration with known `(φ, f*, α)` and a `phase` array, with `C_L(α)` the Dickinson-1999 fit
- **When** the Sane–Dickinson baseline coefficient is computed
- **Then** it equals `(cos(2π·phase))² · C_L(α_amp·|cos(2π·phase)|)` within floating tolerance, evaluated at the documented angle-of-attack mapping

#### Scenario: Baseline normalizes through the CC-3 single-source helper

- **Given** the baseline computation for a configuration
- **When** the reference force `F_ref` and tip speed `U_tip` are obtained
- **Then** they come from `compute_force_reference(f_star, phi_amp_deg, r_tip, span, chord)` (the single source — CC-3), and the baseline force is divided by that `F_ref` explicitly rather than using an inline-re-derived reference

#### Scenario: config_name parses to kinematic parameters

- **Given** a configuration name such as `s45_f115_p60`
- **When** it is parsed
- **Then** it yields `phi_amp_deg == 45`, `f_star == 1.15`, and `pitch_amp_deg == 60`

#### Scenario: Baseline is overlaid only on the lift panel with both RMSEs annotated

- **Given** the generated figure
- **When** the CF_z panel and the CF_my panel are inspected
- **Then** the CF_z panel carries two labeled point series (surrogate and Sane–Dickinson baseline) versus CFD-true CF_z with both RMSEs annotated, while the CF_my moment panel carries no baseline series, and the caption discloses the baseline is translational-only, hovering-scoped, symmetric-rotation, stroke-plane-normal vs lab-z, and a zero-parameter model that bounds (does not fairly compete with) the fitted surrogate

#### Scenario: Caption discloses the baseline is unfitted and the comparison is not "ML beats theory"

- **Given** the figure overlays the fitted surrogate and the zero-parameter Sane–Dickinson baseline on CF_z, with the surrogate's RMSE lower
- **When** the caption is built
- **Then** it states the surrogate is fit to sibling configurations of this corpus while the baseline is a zero-parameter analytic model with no fit to any CFD data, and that the lower surrogate RMSE demonstrates within-range interpolation rather than ML being more accurate than quasi-steady theory in general

### Requirement: Honest evidence-figure caption and speedup annotation

The evidence figure's disclosures SHALL be **split** to stay both honest **and** legible (a caption
carrying a dozen disclosures fails an evidence figure as surely as a dishonest one): the on-figure
caption SHALL be **compact** — a positive headline (the three panels' config-resolved R²/RMSE + the >1,000× batched
speedup), a single terse "Caveats:" line, a single terse "Baseline:" line, and a pointer to
`examples/prelim_sweep/README.md` — and the **full** disclosure set SHALL ALSO live in that README
(task 10.2) and in `evidence_figure_metrics.json`, so honesty is preserved and test-enforced without
overloading the PNG. The positive config-resolved results (CF_x, CF_my) SHALL read as dominant; the
off-panel CF_y −3.61 SHALL be subordinate (an honesty flag, not a co-headline). Within that compact
caption, the figure SHALL report the **configuration-resolved** R² (read from
`metrics.json config_resolved.<coefficient>.config_mean_r2`) for the three figure axes and state that the
pointwise aggregate R²≈0.98 is dominated by the shared within-beat phase waveform and **overstates**
the kinematics→force skill (naming CF_y's negative config-resolved R² as the concrete tell), that the
result is **pipeline readiness on coarse-grid forces** (64×32×64; ~2.4× diffused-IB underestimate),
**not** validated aerodynamics, and that the two off-axis moments **CF_mx/CF_mz are excluded because
they are ≈99.9% the shared within-beat waveform** (no between-config signal) — the exclusion is stated
with its reason, not silent. The figure SHALL annotate the inference-vs-CFD speedup as a **batched
GPU-throughput** speedup — `inference.throughput_rows_per_s` ÷ the coarse-grid A40 CFD throughput
(per-config converged-beat rows ÷ the coarse per-wingbeat wall-clock) — which is the >1,000× claim.
Because this factor equals `latency_speedup × batch_size` (the surrogate is a pointwise map that
batches; the CFD is an **inherently sequential** time integration that cannot), the annotation SHALL
disclose verbatim that it is **batched GPU throughput at the stated batch size (N=12,535) versus a
sequential coarse-grid A40 CFD timestep rate** — not a per-evaluation speedup. The conservative
per-evaluation **latency** speedup (~310×, which is **not** >1,000×) SHALL be reported alongside as
the like-for-like floor, and SHALL NOT be conflated with the throughput claim or computed by dividing
a per-wingbeat cost by a per-row latency. All caption/annotation numbers SHALL be read from the
committed artifacts, never hard-coded.

#### Scenario: Caption reports config-resolved skill and flags the inflated aggregate

- **Given** a metrics.json with `config_resolved.<c>.config_mean_r2` (CF_x 0.94, CF_z 0.83, CF_my 0.99, CF_y −3.61) and an aggregate R²≈0.98
- **When** the caption is built
- **Then** it contains the per-axis config-resolved R² for CF_x/CF_z/CF_my (each read from `config_resolved.<c>.config_mean_r2`), explicitly states the aggregate overstates skill because it is dominated by the shared phase waveform, names the negative CF_y config-resolved R², states that CF_mx/CF_mz are excluded because they are ≈99.9% the shared waveform, and frames the figure as coarse-grid pipeline readiness rather than validated aerodynamics — with every number read from metrics.json

#### Scenario: A NaN-sentinel (null) config-resolved R² renders without crashing

- **Given** a metrics.json in which a coefficient's `config_resolved.<c>.config_mean_r2` is `null` (the documented NaN sentinel for near-zero between-config variance) and another is negative (CF_y −3.61)
- **When** the caption/annotation are built
- **Then** the `null` value renders as an explicit token (e.g. "n/a") and the negative value renders verbatim, neither raising nor being silently dropped

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
- **Then** the on-figure caption leads with the positive headline (per-axis config-resolved R²/RMSE + the >1,000× batched speedup), carries a single terse "Caveats:" line and a single terse "Baseline:" line, and points to the README; **and** the README contains the full disclosure set (the issue-#1 axis caveat, the CF_mx/CF_mz exclusion reason, the baseline's omitted-terms / symmetric-rotation / stroke-plane-normal-vs-lab-z / zero-parameter-unfitted caveats, the coarse-grid / ~2.4× / not-validated framing, and the speedup batch-size + sequential-CFD decomposition) — so the full honesty content is present and test-enforced off the PNG

### Requirement: Committed evidence-figure artifacts with provenance

The figure generator SHALL produce three artifacts under `examples/prelim_sweep/figures/`: the
`evidence_figure.png`, an `evidence_figure_metrics.json` carrying the per-axis surrogate RMSE, the
Sane–Dickinson baseline RMSE on CF_z, the configuration-resolved R² the figure annotates, and the
speedup-derivation inputs (the batched throughput, the per-config rows-per-wingbeat, the coarse CFD
per-wingbeat cost, the single-row latency, and both realized factors with their units); and a
`run_metadata.json` emitted via `capture_surrogate_run_metadata` requiring a pinned container
**digest** and a **caller-supplied** timestamp (CC-1), recording the hash of the consumed inputs (the
predictions parquet and metrics.json). The JSON sidecars SHALL be written **LF-newline UTF-8** (as
`write_units_sidecar` does) so the committed artifacts do not churn between Windows authoring and
Linux CI.

#### Scenario: All three artifacts write and re-load with the documented content

- **Given** a figure-generation run into a temporary output directory
- **When** the run completes
- **Then** `evidence_figure.png`, `evidence_figure_metrics.json`, and `run_metadata.json` all exist and re-load, and `evidence_figure_metrics.json` carries the per-axis surrogate RMSE, the CF_z Sane–Dickinson baseline RMSE, the annotated config-resolved R², and the speedup inputs — equal to what the figure displays

#### Scenario: Provenance records a pinned digest and caller timestamp

- **Given** a container image digest containing `sha256:`, a caller-supplied ISO-8601 timestamp, and the run seeds
- **When** the figure provenance is captured
- **Then** `run_metadata.json` records the git commit, the supplied digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, and a hash of the consumed predictions parquet + metrics.json

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
tiny metrics dict, and SHALL assert the baseline formula on known arrays, the config-name parsing,
the CC-3 helper as the single normalization source, the per-panel annotation values, the figure
structure (three axes; the CF_z panel carries two labeled series; caption/annotation text present)
via the Matplotlib object model (not pixels), the artifact schemas, and the provenance digest guard.

#### Scenario: Tests run without cluster, GPU, or plotfiles

- **Given** a host with no RunAI access, no GPU, and no plotfiles
- **When** the evidence-figure test suite runs
- **Then** every test executes and passes using only the tiny synthetic parquet/metrics fixtures, with no RunAI call, no CUDA requirement, and no plotfile read

#### Scenario: Figure structure is asserted via the Matplotlib object model

- **Given** a generated figure object
- **When** its structure is inspected
- **Then** the test asserts three scatter axes, the CF_z axis carrying two labeled point series (surrogate + baseline), and the presence of the caption and per-panel annotation text — without comparing rendered pixels

### Requirement: Force-only evidence-figure scope guard

The figure generator SHALL consume **only** the committed `holdout_predictions.parquet` and
`metrics.json` (plus the validated geometry module constants) and SHALL NOT read AMReX
plotfiles/velocity/pressure fields, build a DoMINO/latent-dynamics encoder, or integrate any RL loop
(CC-6).

#### Scenario: Generator requires only the committed surrogate artifacts

- **Given** the figure-generation inputs
- **When** the generator runs
- **Then** it requires only the predictions parquet and metrics.json (and module geometry constants) — it neither accepts nor requires a plotfile/field path — and it produces only the figure and its sidecar artifacts, with no field reconstruction, latent state, or RL interaction
