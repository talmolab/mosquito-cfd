# force-surrogate (delta) — van Veen normalization convention

> **BREAKING.** This delta changes the regression-locked reference values
> (`f_ref`/`m_ref` 624.79 → ≈ 200.27, dataset `CF_x = 50/f_ref` 0.080 → 0.250) and renames the
> `ForceReference` fields `u_tip_max → u_ref`, `q_tip → q_ref`. Every MODIFIED requirement below
> reproduces the **full** current requirement text and applies only the convention edits — no
> existing scenario (including error-path guards) is removed.

## MODIFIED Requirements

### Requirement: Single-source force normalization

The force-surrogate module SHALL be the single, parameterized source for aerodynamic force
normalization and force-coefficient computation, using the **van Veen (2022) convention**: the
reference force SHALL be `F_ref = ½·ρ·ω_peak²·S_yy` (van Veen eq 1.1), where
`ω_peak = 2π·f_star·radians(phi_amp_deg)` is the peak stroke rate and `S_yy = ∫c(y)·y² dy` is the
spanwise **second moment of area**. Equivalently `F_ref = ½·ρ·u_ref²·area` with
`u_ref = ω_peak·r_gyr`, the speed at the **radius of gyration** `r_gyr = sqrt(S_yy/area)`, and
`area = π/4·span·chord`. The reference normalization SHALL be a pure function of its kinematic and
geometric inputs (no hardcoded amplitude/frequency, no I/O) and SHALL reproduce the validated
reference values. No other module SHALL re-derive `F_ref` inline, and **no post-hoc correction
factor** (e.g. "~2.4×"/"~2.64×") SHALL be applied to coefficients.

#### Scenario: Reference normalization at the validated point

- **Given** `f_star = 1.0`, `phi_amp_deg = 70.0`, `r_gyr = R_GYRATION` (≈ 1.6985), `span = 3.0`, `chord = 1.0`, `rho = 1.0`
- **When** `compute_force_reference` is called
- **Then** it returns `u_ref ≈ 13.04`, `q_ref ≈ 85.0`, `area ≈ 2.3562`, `f_ref ≈ 200.27` (each within 0.1%, `rtol=1e-3`)
- **And** `f_ref` equals `½·rho·ω_peak²·S_yy` with `S_yy = r_gyr²·area ≈ 6.797`

#### Scenario: Radius of gyration is traced to the committed wing geometry

- **Given** the committed `examples/flapping_wing/wing.vertex` markers
- **When** the radius of gyration is re-derived as `sqrt(mean(r²))` over the markers (`r` = hinge-distance along the span, using the documented hinge offset `r = z_local + (R_TIP − max z_local)`)
- **Then** it equals `R_GYRATION ≈ 1.6985` within `rtol=1e-3`, confirming the normalization arm is the wing's radius of gyration (van Veen `S_yy`), not a magic constant
- **And** it is strictly less than the tip arm `r_tip = 3.0` (the load is tip-weighted, so `r_gyr` sits outboard of the geometric midspan `1.5`)

#### Scenario: Parameterization, not hardcoded

- **Given** the validated inputs with `phi_amp_deg` reduced from 70° to 35°
- **When** `compute_force_reference` is called
- **Then** both `u_ref` and `f_ref` are strictly smaller than at 70°
- **And** doubling `f_star` doubles `u_ref`

#### Scenario: Force coefficients

- **Given** force component arrays `Fx, Fy, Fz` and a nonzero reference `F_ref`
- **When** `compute_force_coefficients` is called
- **Then** it returns `cf_x = Fx / F_ref`, `cf_y = Fy / F_ref`, `cf_z = Fz / F_ref` element-wise, preserving input shape (scalar input → scalar output)

#### Scenario: Non-positive reference rejected

- **Given** `F_ref <= 0` (zero — reachable when `f_star = 0` or `phi_amp_deg = 0`; or negative — e.g. a non-physical `rho < 0`)
- **When** `compute_force_coefficients` is called
- **Then** it raises `ValueError` rather than returning inf/NaN or sign-flipped coefficients

#### Scenario: Mismatched force shapes rejected

- **Given** `fx`, `fy`, `fz` that do not all share the same shape (e.g. a truncated column)
- **When** `compute_force_coefficients` is called
- **Then** it raises `ValueError` rather than silently returning misaligned coefficient vectors

#### Scenario: Empty and NaN forces

- **Given** an empty force array, or a force array containing NaN, with a nonzero `F_ref`
- **When** `compute_force_coefficients` is called
- **Then** an empty input yields empty outputs without error, and a NaN force propagates to a NaN coefficient (no exception)

#### Scenario: Inline normalization is replaced by the shared helper

- **Given** the flapping-wing figure script `examples/flapping_wing/generate_all_figures.py`
- **When** it computes the force reference
- **Then** it calls `compute_force_reference` from this module rather than re-deriving `F_ref` inline, and reports `f_ref ≈ 200.27`

### Requirement: Single-source moment normalization

The force-surrogate module SHALL be the single, parameterized source for aerodynamic **moment**
normalization and moment-coefficient computation, sibling to the published force normalization. The
reference moment SHALL be `M_ref = q_ref · area · L` with the moment length scale **`L = chord`**,
where `q_ref` and `area` are computed by the **same formulas** as the force reference (no second
copy; `q_ref = ½·ρ·u_ref²` at the radius of gyration). It SHALL be a pure function of its kinematic and
geometric inputs (no hardcoded amplitude/frequency, no I/O), SHALL reproduce the validated reference
value, and SHALL NOT be re-derived inline by any other module.

#### Scenario: Moment reference at the validated point

- **Given** `f_star = 1.0`, `phi_amp_deg = 70.0`, `r_gyr = R_GYRATION` (≈ 1.6985), `span = 3.0`, `chord = 1.0`, `rho = 1.0`
- **When** `compute_moment_reference` is called
- **Then** it returns `m_ref ≈ 200.27` (within 0.1%, i.e. `rtol=1e-3`), equal to `q_ref · area · chord` and — because `chord = 1.0` — numerically equal to the force reference `f_ref` at the same point, while remaining a distinct, chord-parameterized quantity
- **And** the returned `length` field equals the supplied `chord`

#### Scenario: Moment reference scales with the chord length scale and reuses the force reference

- **Given** the validated inputs evaluated once with `chord = 1.0` and once with `chord = 2.0`
- **When** `compute_moment_reference` is called for each
- **Then** the second `m_ref` is exactly **four** times the first — because `chord` enters `m_ref` **twice**, once through the area (`S = π/4·span·chord`) and once through the explicit moment length scale `L = chord`, so `m_ref` scales **quadratically** with chord — confirming the helper is genuinely parameterized on chord rather than hardcoding `L = 1.0`
- **And** at a **non-unit** chord (e.g. `chord = 2.0`) `m_ref` equals `compute_force_reference(same kinematics/geometry).f_ref · chord` exactly — proving the moment helper reuses the force reference's `q_ref`/`area` (CC-3, single source) rather than carrying a divergent second copy of the formula (an equality that would hold trivially at `chord = 1.0` and hide a copy)

#### Scenario: Moment coefficients

- **Given** moment component arrays `Mx, My, Mz` and a nonzero reference `M_ref`
- **When** `compute_moment_coefficient` is called
- **Then** it returns `cf_mx = Mx / M_ref`, `cf_my = My / M_ref`, `cf_mz = Mz / M_ref` element-wise, preserving input shape (scalar input → scalar output)

#### Scenario: Non-positive moment reference rejected

- **Given** `M_ref <= 0` (degenerate or non-physical)
- **When** `compute_moment_coefficient` is called
- **Then** it raises `ValueError` rather than returning inf/NaN or sign-flipped coefficients (parity with `compute_force_coefficients`)

#### Scenario: Mismatched moment shapes rejected

- **Given** `mx`, `my`, `mz` that do not all share the same shape
- **When** `compute_moment_coefficient` is called
- **Then** it raises `ValueError` rather than silently returning misaligned coefficient vectors

#### Scenario: Empty and NaN moments

- **Given** an empty moment array, or a moment array containing NaN, with a nonzero `M_ref`
- **When** `compute_moment_coefficient` is called
- **Then** an empty input yields empty outputs without error, and a NaN moment propagates to a NaN coefficient (no exception)

### Requirement: Tidy force-coefficient dataset extraction

The force-surrogate module SHALL build a tidy dataset that maps each sweep configuration's
kinematics (plus per-timestep phase) to normalized force and moment coefficients, reading forces
**only** from the IB-particle CSV. It SHALL read the CSV **name-based** against the documented 29-column
schema (never positional), join each configuration's kinematics, `reynolds`, and train/holdout
`split` from `sweep_manifest.json`, compute the **per-configuration** `F_ref`/`M_ref` via the
single-source normalization helpers (with `f_star = frequency_fstar`, `phi_amp_deg = stroke_amp_deg`,
and the geometry's `r_gyr`/`span`/`chord`), and emit **one row per (configuration × timestep)**. Raw
force/moment columns SHALL be carried through unchanged; only the derived coefficient columns reflect
the convention. The build SHALL return both the dataframe and the list of any configurations dropped
under `allow_missing`, so the caller can record the drop in run metadata (the dataframe alone provides
no channel for the dropped names).

#### Scenario: One row per configuration and timestep

- **Given** a manifest with `N` configurations, each mapped to an IB-particle CSV with `T` timesteps
- **When** `build_dataset` is called
- **Then** the returned dataframe has exactly `N × T` rows, one per (configuration, timestep)

#### Scenario: Columns are the documented schema

- **Given** a built dataset
- **When** its columns are inspected
- **Then** they are exactly `config_name, index, time, phase, wingbeat, stroke_amp_deg, frequency_fstar, pitch_amp_deg, reynolds, split, Fx, Fy, Fz, Mx, My, Mz, CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz` — carrying all three force coefficients, all three moment coefficients, and the raw forces and moments

#### Scenario: Coefficients use the single-source per-config normalization

- **Given** the committed `synthetic_ib_particle.csv` mapped to a **synthetic single-config manifest** at the validated point (`stroke_amp_deg = 70.0`, `frequency_fstar = 1.0`, `pitch_amp_deg = 45.0`) — chosen because no committed-corpus config is at φ=70°, and so the per-config `f_ref` is the regression-locked `≈ 200.27`
- **When** `build_dataset` is called
- **Then** each `CF_x` equals `Fx / compute_force_reference(f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO).f_ref` and each `CF_mx` equals `Mx / compute_moment_reference(...).m_ref` (and likewise for y/z) — **ratio** equality, not round literals (the validated `f_ref ≈ 200.27` is not round, so `CF_x = 50/200.27 ≈ 0.250`, etc.), confirming the extractor reuses the helpers rather than re-deriving a reference inline (CC-3)
- **And** a separate config whose reference is the round `f_ref = m_ref = 100` (e.g. via the helper unit tests) is where the fixture's round forces/moments give exact-decimal coefficients — the dataset path asserts the **ratio**, the helper path asserts the **exact decimals**

#### Scenario: Phase and wingbeat tag every timestep, no rows dropped

- **Given** a configuration with `frequency_fstar = 1.0` mapped to the committed fixture (whose `time` column is `0, 0.25, 0.5, 0.75, 1.0`), so `time · f*` reaches exactly `1.0` at the last row and crosses into the second wingbeat
- **When** `build_dataset` is called
- **Then** every timestep is retained (no startup-transient masking), each row's `phase` equals `(time · f*) mod 1` and lies in the half-open interval `[0, 1)`, and each row's `wingbeat` equals `floor(time · f*)` (integer cycle index, 0 for the first beat) — for this config `phase = [0, 0.25, 0.5, 0.75, 0.0]` and `wingbeat = [0, 0, 0, 0, 1]`
- **And** at the cycle boundary where `time · f* = 1.0` exactly, `phase = 0.0` (the boundary opens the next cycle; `phase` is never `1.0`) and `wingbeat = 1` — pinning the half-open-interval edge that an off-by-one would hide. (`frequency_fstar = 1.0` is required for the fixture's `time = 1.0` row to land on the boundary; at e.g. `f* = 0.85` no row would.)

#### Scenario: Empty force CSV yields no rows for that configuration

- **Given** a configuration whose IB-particle CSV has the header but **zero** data rows
- **When** `build_dataset` is called
- **Then** that configuration contributes zero rows (no error, no fabricated row), and the dataset comprises the rows of the remaining configurations — an empty contribution is explicit, not silently treated as a missing CSV

#### Scenario: Name-based parse is robust to column order

- **Given** an IB-particle CSV whose columns are present but reordered from the canonical schema
- **When** `build_dataset` is called
- **Then** it reads each column by name and produces the same coefficients as the canonically-ordered CSV (never positional)

#### Scenario: Held-out configuration split is carried through

- **Given** a manifest in which some configurations are labelled `split = "holdout"`
- **When** `build_dataset` is called
- **Then** every row carries its configuration's `split` value verbatim from the manifest (CC-4: the held-out **configuration** label is propagated, not re-derived)

#### Scenario: Complete build reports no drops

- **Given** a manifest in which every configuration has a present, non-empty CSV
- **When** `build_dataset` is called (default `allow_missing=False`)
- **Then** the returned `dropped` list is empty (`[]`) — the second tuple element's baseline is normative, not incidental

#### Scenario: Missing configuration CSV is rejected by default

- **Given** a manifest configuration whose IB-particle CSV **path does not exist on disk** (distinct from a present-but-header-only CSV, which yields zero rows per the prior scenario — the two are distinguished by **path existence**, not row count)
- **When** `build_dataset` is called with the default `allow_missing=False`
- **Then** it raises `ValueError` naming the missing configuration rather than silently emitting a short dataset

#### Scenario: Opt-in allow_missing skips and records the drop

- **Given** the same missing-CSV configuration
- **When** `build_dataset` is called with `allow_missing=True`
- **Then** it skips that configuration with a logged warning, emits the rows for the present configurations, and **returns the dropped configuration name(s) as the second element of its `(dataframe, dropped)` return** so the truncation can be recorded in run metadata (no silent caps)

### Requirement: Sane–Dickinson quasi-steady reference (computed, not overlaid)

The evidence figure SHALL **compute** a **translational-only** Sane–Dickinson quasi-steady CF_z
reference through the **single-source** `compute_force_reference` helper (CC-3) — the reference
force/reference speed SHALL NOT be re-derived inline — as
`CF_trans(t) = F_trans(t)/F_ref = (U(t)/u_ref)²·C_L(α_eff(t))`, with `U(t)/u_ref = cos(2π·phase)` from
the parquet `phase` column, `C_L(α)` the Dickinson–Lehmann–Sane (1999) empirical fit, and the
per-configuration `(φ, f*, α)` parsed from `config_name`.

It SHALL **NOT** overlay this reference on the scatter panels. **Why reference-only instead of an
overlay (CC-4 deviation; reference-only decision recorded in the proposal):** the uncalibrated
**translational-only** quasi-steady model is a poor fit to the coarse 64×32×64 CFD lift — it omits
rotational, added-mass, and LEV lift — so a scatter overlay would mostly re-display the model's
analytic loops rather than demonstrate surrogate skill. The earlier "~2.4× diffused-IB underestimate"
framing was a normalization-convention artifact and is removed (the CFD `ib_force` is correct). Under
the corrected van Veen normalization the model's RMS ratio `rms(CF_trans)/rms(CFD-true CF_z)` is **< 1**
(it **under-predicts** the now-in-band CFD lift, ≈ 0.7 on the committed corpus — the opposite of the
old > 1 "overshoot," because the CFD lift is no longer mis-normalized small). The figure SHALL record
this RMS ratio (key `overshoot_factor`) and the baseline RMSE in `evidence_figure_metrics.json`, and
the caption SHALL disclose the ratio neutrally (the model is ~N× the CFD lift in RMS) and that the
uncalibrated translational model is therefore **not used as a quantitative baseline at this
resolution**.

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
- **Then** `evidence_figure_metrics.json` records the reference's `overshoot_factor` (the RMS ratio `rms(CF_trans)/rms(CFD-true CF_z)`, a positive finite number — **< 1** under the van Veen convention) and `baseline_rmse_cf_z`, and the caption states neutrally that the uncalibrated translational quasi-steady model is ~N× the coarse-grid CFD lift in RMS and is **not used as a quantitative baseline** at this resolution (it is not framed as a comparison the surrogate "beats")

#### Scenario: No diffused-IB underestimate claim remains

- **Given** the evidence-figure module docstring, caption strings, `_baseline_reference` docstring, the `evidence_figure_metrics.json` `note`, and the `Sane–Dickinson` rationale text
- **When** they are inspected
- **Then** none contains a "~2.4× diffused-IB underestimate" (or equivalent CFD-is-biased-low) claim and no post-hoc correction factor — the quasi-steady reference's RMS ratio is described neutrally (translational-only model, a poor fit that under-predicts the in-band CFD lift)

### Requirement: Honest evidence-figure caption and speedup annotation

The evidence figure's disclosures SHALL be **split** to stay both honest **and** legible (a caption
carrying a dozen disclosures fails an evidence figure as surely as a dishonest one): the on-figure
caption SHALL be **compact** — a positive headline (the three panels' config-resolved R²/RMSE + the >1,000× batched
speedup), a single terse "Caveats:" line, a single terse "Quasi-steady reference (not plotted):" line,
and a pointer to `examples/prelim_sweep/README.md` — and the **full** disclosure set SHALL ALSO live in that README
(task 10.2) and in `evidence_figure_metrics.json`, so honesty is preserved and test-enforced without
overloading the PNG. The positive config-resolved results (CF_x, CF_my) SHALL read as dominant; the
off-panel CF_y −3.61 SHALL be subordinate (an honesty flag, not a co-headline). Within that compact
caption, the figure SHALL report the **configuration-resolved** R² (read from
`metrics.json config_resolved.<coefficient>.config_mean_r2`) for the three figure axes and state that the
pointwise aggregate R²≈0.98 is dominated by the shared within-beat phase waveform and **overstates**
the kinematics→force skill (naming CF_y's negative config-resolved R² as the concrete tell), that the
result is **pipeline readiness on coarse-grid forces** (64×32×64),
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
- **Then** the on-figure caption leads with the positive headline (per-axis config-resolved R²/RMSE + the >1,000× batched speedup), carries a single terse "Caveats:" line and a single terse quasi-steady-reference line, and points to the README; **and** the README contains the full disclosure set (the issue-#1 axis caveat, the CF_mx/CF_mz exclusion reason, the quasi-steady reference's omitted-terms / symmetric-rotation / stroke-plane-normal-vs-lab-z / uncalibrated nature and why it is not overlaid, the coarse-grid / not-validated framing, and the speedup batch-size + sequential-CFD decomposition) — so the full honesty content is present and test-enforced off the PNG

## ADDED Requirements

### Requirement: Re-normalization preserves surrogate skill (scale-invariance)

Re-deriving force/moment coefficients under a different per-configuration convention SHALL rescale the CFD targets and the surrogate predictions by the **same** constant, leaving the held-out **R²** and the predicted-vs-CFD relationship invariant. The frozen corpus's raw force/moment columns and IB-particle CSVs SHALL NOT be regenerated; only derived coefficients change, and no surrogate retraining SHALL be required.

#### Scenario: R² is invariant under re-normalization

- **Given** the committed `examples/prelim_sweep/surrogate/holdout_predictions.parquet` (`CF_x_true/pred`, `CF_z_true/pred`, …) whose `R²` matches `metrics.json`
- **When** both the `*_true` and `*_pred` columns are multiplied by the convention factor `k = f_ref_old / f_ref_new` (≈ 3.119)
- **Then** the recomputed per-target `R²` for `CF_x` and `CF_z` each equals the original within `1e-9`, confirming no retrain is needed
- **And** the `RMSE`/`MAE` rescale by exactly `k` (reported honestly), while the scatter shape is unchanged (axes relabeled)

#### Scenario: Raw corpus stays frozen; only derived coefficients move

- **Given** the convention change re-derives the corpus coefficients
- **When** `dataset.parquet` is regenerated
- **Then** its raw `Fx, Fy, Fz, Mx, My, Mz` column **values** are exactly equal (e.g. `pandas.testing.assert_frame_equal(..., check_exact=True)`) to the committed corpus, only the derived `CF_*` columns change (each new column equals the old divided by `k`), and the committed `metrics.json` per-target `R²` is reused unchanged (within `1e-9`)

#### Scenario: Degenerate re-normalization is rejected

- **Given** a convention factor that is undefined — `f_ref_new = 0` (so `k` divides by zero) or a `holdout_predictions.parquet` missing a required `CF_*_true`/`CF_*_pred` column
- **When** the scale-invariance check is run
- **Then** it raises `ValueError` (or `KeyError` for the missing column) rather than emitting `inf`/`NaN` R² or silently skipping the target
