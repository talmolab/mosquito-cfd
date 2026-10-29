## ADDED Requirements

### Requirement: Wing coefficients report the IB force and moment on the wing

The force and moment coefficients `CF_x/CF_y/CF_z/CF_mx/CF_my/CF_mz` SHALL be the immersed-boundary
(IB) force and moment **on the wing**: the Newton's-third-law reaction to IAMReX's
`kernel.ib_force` / `kernel.ib_moment` (the IB-particle CSV's `Fx..Mz`), which act **on the fluid**
(issue #109). No corpus coefficient includes the internal-fluid momentum term `ρ_f·SumU`, which the
solver's free-body 6-DOF balance would add. That balance runs only for freely moving bodies, never for
the prescribed-motion wing. For the zero-thickness vertex-file wing, the term is the momentum change of
fluid within about one grid cell of the sheet, so it depends on the grid. Its physical status is an
open follow-up question, not settled here.

Extraction SHALL shift the solver's moments to the hinge with the solver's own forces, exactly as
"Moment coefficients are referenced to the wing hinge" specifies. It SHALL then negate force and
shifted moment through the single-source helper `force_on_wing` in `force_surrogate/normalization.py`,
and only then normalize. Within the wing paths, no other site SHALL apply the sign. The wing paths
are dataset extraction, `benchmarks/flapping_wing.py`, and the figure functions `plot_f1_forces` and
`fig_v1_three_convention`, which compute coefficients directly. The raw `Fx..Mz` columns SHALL keep the solver's as-written values.

The convention SHALL be pinned by a **physics** regression guard, not only by an algebraic one.

- For a rigid wing rotating about a fixed hinge, `M_hinge · Ω = Σ F_i · U_wing(x_i)` is the power the IB
  forcing delivers to the fluid.
- With the diffused-IB forcing `F_i = (U_wing − u*)/dt · dv`, this power is the work done on the fluid
  plus a non-negative slip term.
- So the cumulative work from rest, `W(t) = ∫₀ᵗ M_hinge · Ω dt`, should not go negative. This rests on a
  stated physical assumption, not a theorem: the energy convected out through the open boundaries must
  not exceed what the wing put in. The guard is therefore an empirical check with measured margins.

`Ω` SHALL come from a canonical analytic `wing_kinematics.angular_velocity`, verified against a finite
difference of `rotation_matrix`.

#### Scenario: The sign is applied once, after the hinge shift, through the helper

- **Given** solver forces `F` and moments `M` about the particle origin, and an origin-to-hinge offset `d`
- **When** a configuration is extracted
- **Then** the emitted coefficients equal `force_on_wing(F)/f_ref` and `force_on_wing(M + d × F)/m_ref`, i.e. `−F/f_ref` and `−(M + d × F)/m_ref`
- **And** `force_on_wing` returns the elementwise negation of every array it is given (dtype and shape preserved; `−0.0`, NaN and infinity propagate; empty in, empty out)
- **And** `force_on_wing` is replaced at each use site by an identity spy. With the spy in place:
  - `build_dataset` emits exactly `+F/f_ref` and `+(M + d × F)/m_ref`;
  - every series that is the IB force itself equals the pre-change on-fluid series bitwise. These are `cf_*_ib`, the body-frame `CF_chord`/`CF_normal`, the T4 CFD series, `peak_cf_*_ib`, and the coefficients plotted by `plot_f1_forces` and `fig_v1_three_convention`;
  - every composite equals its formula evaluated on the spied output: `cf_hydro == cf_added + ρ_f·cf_ib_spied`, and `peak_cf_*_6dof` is the peak of `|CF(ρ_f·SumU + ρ_f·ib_spied)|`.
- **And** across all calls, the multiset of arrays passed to the spy equals the expected set of force (and moment) arrays, each passed exactly once (identity-compared, not counted per call). So no wing-path function applies the sign by other means.

#### Scenario: Raw columns satisfy the on-fluid work inequality

- **Given** these runs:
  - all 54 configurations of both committed corpora, with raw moments shifted to each committed deck's hinge;
  - `forces_t2a_newconv.csv`, `forces_medium.csv` and `forces_fine.csv`. Each is mapped to its deck by sha256: the deck's sha equals the `inputs.hash` recorded in `run_metadata_t2a.json`, `run_metadata_t3b.json` and `run_metadata_t3c.json` respectively, and the deck's hinge equals the literal `(4.0, 0.5, 4.0)`. The CSV's `X,Y,Z` matching the deck's `particle_inputs.{x,y,z}` is kept only as a sanity check; it cannot distinguish the decks, which all share `(4, 2, 4)`.
  - Duplicate `iStep` rows are kept last, as the extractor does.
- **When** `W(t) = ∫₀ᵗ M_hinge · Ω dt` is integrated (trapezoidal) from the first row
- **Then** `W(t) ≥ 0` at every row, with no tolerance, in every run
- **And** `W(t) > 0` at every row after the first, so the opposite sign would fail every run (measured margin `min W[1:] / max|W| = 0.0059`)
- **And** with `W₀` the value at the first row after the impulsive-start transient (`t ≥ 0.005`, per the comment on `STEADY_WINDOW_T0`), the increment `W(t) − W₀ ≥ 0` for every later row, so the verdict does not rest on the transient alone. Increments over arbitrary later windows are not asserted: the power dips below zero within a beat.
- **And** the check covers exactly 57 runs, each starting at `t = 0` (from rest) with strictly increasing time and a late window (`t ≥ 0.005`) of at least 0.9 wingbeats. A NaN anywhere in `W`, a zero-row run or a too-short run fails rather than passing.

#### Scenario: Raw force and moment share one convention

- **Given** the same 57 runs
- **When** the solver's **unshifted** (origin-referenced) moments are compared with its forces
- **Then** `corr(Mz, −Fx) > 0` and `corr(Mx, +Fz) > 0` in every run (measured minima +0.870 and +0.740)
- **And** a copy with only `Mx..Mz` negated, or only `Fx..Fz` negated, fails this check

#### Scenario: Coefficients satisfy the on-wing inequalities

- **Given** the 54 configurations of both committed corpora (the validation CSVs carry no committed moment coefficients)
- **When** `W_wing(t) = ∫₀ᵗ CF_m · Ω dt` is integrated and `CF_mz` is compared with `CF_x`
- **Then** `W_wing(t) ≤ 0` at every row and its late increment is `≤ 0`, so the fluid does net negative work on the wing
- **And** `corr(CF_mz, −CF_x) > 0` in every configuration, so a half-flip inside extraction (only the force or only the moment coefficients negated) fails
- **And** the sign predicates signal failure with a dedicated `CoefficientsOnFluid` error, so a corpus carrying on-fluid coefficients fails with exactly that error. The non-vacuity checks use plain assertions: every `CF_*` is finite and equals `|F|/f_ref` or `|M_hinge|/m_ref` in magnitude, so zeroed, NaN or rescaled coefficients fail even under the xfail.

### Requirement: Sign re-extraction and retrain pass pre-registered gates

The re-extraction that applies the sign SHALL be verified against the pre-change corpus by a
purpose-specific operator script, `scripts/verify_force_sign_reextraction.py --baseline-ref <ref>`,
where the ref is the PR branch's merge-base with `origin/main`, recorded in the PR. The retrain of
both surrogates SHALL pass a gate fixed before any GPU run. A gate failure SHALL halt the change for a
decision; no criterion SHALL be loosened to pass.

Retraining on negated targets is not seed-for-seed equivalent to the previous training. It equals
training on the original targets with the output layer's initial weights and bias negated. The gate
therefore:
- compares seed **ranges**, never single-seed metrics;
- does not gate config-resolved R², which is strongly seed-dependent;
- commits the pre-registered intervals and invariants as test literals before the GPU run, so the gate
  survives a depth-1 CI checkout.

Those tests SHALL name this change in their docstrings and MAY be retired by a later change's OpenSpec
proposal.

#### Scenario: Re-extraction changes only the sign of the coefficients

- **Given** a re-extracted corpus and the same corpus at the baseline ref
- **When** the verifier compares them
- **Then** the schema, the row order and every non-`CF_*` column are value-identical, and every `CF_*` column equals the negated baseline exactly, with identical NaN positions
- **And** the corpus `run_metadata.json` differs from the baseline only as follows:
  - `run_id`, `timestamp` and `git` may differ;
  - `hardware` is reported but not compared;
  - exactly one key is added, `force_sign_convention`, with its pinned value;
  - every other key is identical, including `inputs` (`file` and `hash`), `extraction_inputs` (every `csv_sha256`, `input_dir`), `moment_reference`, `docker_image` and `dropped_configs`;
  - `git.dirty` is `false`.
- **And** the sha256 of the baseline parquet equals the committed surrogate's `inputs.hash` and the pinned pre-change literal, so the parquet the verifier negated is exactly the one the stale surrogate was trained on
- **And** each of the following fails the verifier:
  - a changed raw or non-CF column, or a reordered row;
  - a missing, unflipped or off-by-one-ULP coefficient column, or a moved NaN;
  - a changed `csv_sha256`, `input_dir`, `inputs.hash`, `docker_image`, `moment_reference` offset or `dropped_configs`;
  - a wrong `force_sign_convention` value, a removed key, or a second added key;
  - `dirty: true`;
  - a baseline parquet whose sha256 does not match the surrogate's `inputs.hash`.
- **And** a changed `hardware` block is reported and does not fail it

#### Scenario: The trainer is sign-equivariant up to the output-layer initialization

- **Given** a small model and data on the CPU device, in the GPU-marked test tier (the trainer's dependencies are not installed in CI)
- **When** the trainer's own per-seed path (standardizer, training with a validation set, prediction, inverse transform) runs twice: once on `y`, and once on `−y` with only the final linear layer's initial weights and bias negated
- **Then** the second run's predictions satisfy `array_equal(p_neg, −p)`
- **And** each of these fails the check: an output activation appended to the model; the weights negated but not the bias; an asymmetric loss

#### Scenario: Retrained surrogates reproduce and stay within the prior seed ranges

- **Given** the 5-seed retrain of each corpus, run twice in separate processes from one clean committed tree into scratch directories outside the repository. `git status --porcelain` is empty in the training environment, and `git rev-parse HEAD` equals the recorded commit.
- **When** the gate is evaluated
- **Then** across the two runs:
  - `surrogate.pt` and `holdout_predictions.parquet` are byte-identical;
  - `metrics.json` is equal outside the `inference` wall-clock fields;
  - `run_metadata.json` is equal outside `run_id`;
  - both records name one 40-hex commit and `dirty: false`.
- **And** for each corpus and each of the six targets, the new `seed_sweep.range.<target>.skill` interval intersects the pre-change interval committed as a test literal
- **And** the same CI test asserts that the committed surrogate's `inputs.hash` equals the sha256 of the committed `dataset.parquet` and differs from the pinned pre-change sha. So it cannot pass on the pre-change surrogate comparing its intervals with themselves.

#### Scenario: Sign-invariant figure quantities are unchanged and the lift reference now agrees in sign

- **Given** the regenerated evidence-figure sidecars
- **When** they are compared with the pre-change values committed as test literals
- **Then** `overshoot_factor` is exactly equal: 1.3435407346470738 (coarse) and 1.4074274138248275 (fine)
- **And** `baseline_rmse_cf_z` equals its recomputation from the new committed predictions to relative `1e-12`, and `round(baseline_rmse_cf_z, 4)` equals 0.5175 (coarse) and 0.4782 (fine)

## MODIFIED Requirements

### Requirement: Tidy force-coefficient dataset extraction

The force-surrogate module SHALL build a tidy dataset that maps each sweep configuration's
kinematics (plus per-timestep phase) to normalized force and moment coefficients, reading forces
**only** from the IB-particle CSV. It SHALL read the CSV **name-based** against the documented 29-column
schema (never positional), join each configuration's kinematics, `reynolds`, and train/holdout
`split` from `sweep_manifest.json`, resolve each configuration's **deck** from the manifest's
`input_file` entry in order to read its hinge, compute the **per-configuration** `F_ref`/`M_ref` via the
single-source normalization helpers (with `f_star = frequency_fstar`, `phi_amp_deg = stroke_amp_deg`,
and the geometry's `r_gyr`/`span`/`chord`), and emit **one row per (configuration × timestep)**. Raw
force/moment columns SHALL be carried through unchanged; only the derived coefficient columns reflect
the convention — including the hinge moment reference point and the **sign**: coefficients are the
IB force and moment **on the wing**, the negation of the solver's on-fluid `ib_force`/`ib_moment` (see
"Wing coefficients report the IB force and moment on the wing"). The build SHALL return the
dataframe, the list of any configurations dropped
under `allow_missing`, and a per-configuration record of the moment origin, hinge and offset it
applied and the deck and CSV it consumed — `(frame, dropped, provenance)` — so the caller can record
the drop and the frame in run metadata (the dataframe alone provides no channel for either).

**BREAKING**: `build_dataset` returns three elements where it returned two.

**BREAKING** (`fix-wing-force-sign-convention`, #109): every `CF_*` value is the exact negation of
the value a corpus extracted before that change carries; raw `Fx..Mz` columns are unchanged.

**BREAKING**: because `ns.init_iter = N` causes the solver to write `1 + N` rows at `iStep = 0` — the
first with all-zero forces and the remainder being initial-pressure iterations — the extractor SHALL
deduplicate rows on `iStep`, retaining the **last** row for each step value. A field-capture corpus
extracted before this change therefore has `init_iter` more rows per configuration than one extracted
after it, and its `time` column is non-monotonic. Deduplication restores the one-row-per-timestep
contract and yields `len(df) == max_step` per configuration.

Deduplication SHALL retain the last row, never the first: the first `iStep = 0` row carries all-zero
forces and retaining it would place a non-physical zero-force sample at `phase = 0` in every
configuration.

Deduplication SHALL be a no-op for a corpus generated without `init_iter` (which writes exactly one
row per step), so a corpus extracted before this capability existed re-extracts with byte-identical raw columns
and an identical row set, and the frozen coarse corpus's raw columns are unaffected.

Apart from duplicate-step removal, every timestep SHALL be retained: there is no startup-transient
masking at the dataset layer.

#### Scenario: One row per configuration and timestep

- **Given** a manifest with `N` configurations, each mapped to an IB-particle CSV with `T` distinct `iStep` values
- **When** `build_dataset` is called
- **Then** the returned dataframe has exactly `N × T` rows, one per (configuration, timestep)

#### Scenario: Duplicate initialization rows are removed, keeping the converged row

- **Given** a configuration whose CSV was written with `ns.init_iter = 2`, so three rows carry `iStep = 0`, the first with all-zero forces
- **When** the configuration is extracted
- **Then** exactly one row with `iStep = 0` is retained, and it is the last of the three (non-zero forces), not the all-zero first row
- **And** the configuration's row count equals its manifest `max_step`

#### Scenario: Time is strictly increasing within every configuration

- **Given** an extracted dataset
- **When** each configuration's `time` column is inspected
- **Then** it is strictly increasing, with no duplicated timestamps

#### Scenario: Deduplication is a no-op without init_iter

- **Given** a corpus generated with no `init_iter` (one row per step)
- **When** it is extracted
- **Then** the resulting dataframe is identical to extraction without deduplication, and the committed coarse corpus's raw force columns are byte-unchanged

#### Scenario: Columns are the documented schema

- **Given** a built dataset
- **When** its columns are inspected
- **Then** they are exactly `config_name, index, time, phase, wingbeat, stroke_amp_deg, frequency_fstar, pitch_amp_deg, reynolds, split, Fx, Fy, Fz, Mx, My, Mz, CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz` — carrying all three force coefficients, all three moment coefficients, and the raw forces and moments

#### Scenario: Coefficients use the single-source per-config normalization

- **Given** the committed `synthetic_ib_particle.csv` mapped to a **synthetic single-config manifest** at the validated point (`stroke_amp_deg = 70.0`, `frequency_fstar = 1.0`, `pitch_amp_deg = 45.0`) — chosen because no committed-corpus config is at φ=70°, and so the per-config `f_ref` is the regression-locked `≈ 200.27`
- **When** `build_dataset` is called
- **Then** each `CF_x` equals `−Fx / compute_force_reference(f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO).f_ref` and each `CF_mx` equals `−(Mx + (r_origin − r_hinge) × F)_x / compute_moment_reference(...).m_ref` (and likewise for y/z) — **ratio** equality, not round literals (the validated `f_ref ≈ 200.27` is not round, so `CF_x = −50/200.27 ≈ −0.250`, etc.), confirming the extractor reuses the helpers rather than re-deriving a reference inline (CC-3)
- **And** for a fixture whose deck hinge coincides with the particle origin the shift is zero and the moment ratio reduces to `−Mx / m_ref`, so the pre-existing round-number relationship is preserved (up to the sign) for the degenerate case
- **And** `CF_x` is **not** `allclose` to `+Fx / f_ref`, so a build that omits the sign fails this scenario rather than passing it vacuously
- **And** a separate config whose reference is the round `f_ref = m_ref = 100` (e.g. via the helper unit tests) is where the fixture's round forces/moments give exact-decimal coefficients — the dataset path asserts the (negated) **ratio**, the helper path asserts the **exact decimals** of the sign-free normalization

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
- **Then** it skips that configuration with a logged warning, emits the rows for the present configurations, and **returns the dropped configuration name(s) as the second element of its `(frame, dropped, provenance)` return** so the truncation can be recorded in run metadata (no silent caps)

### Requirement: Per-configuration output layout matches the dataset driver contract

The runner SHALL write each configuration's IB-particle force CSV to
`<output-root>/<name>/<csv-name>` — the **exact** path that the merged dataset driver
(`scripts/extract_forces.py`) resolves from its `--input-dir <output-root>`. This guarantees the
PR4 extractor consumes the runner's output with no glue. The CSV filename SHALL default to the
IAMReX per-run name `IB_Particle_1.csv`, which is **verified** against real IAMReX output on the A40
corpus (PR #18, issue #19), and SHALL remain **operator-overridable** (a `csv_name` parameter /
`--csv-name` flag, mirroring `extract_forces.py`) as a defensive escape hatch in case a future solver
build writes forces under a different name. Live source comments SHALL NOT describe the name as
assumed or unverified.

#### Scenario: Runner output is the path the extractor reads

- **Given** an `output-root` and a config named `s45_f100_p45`
- **When** the runner completes that config
- **Then** its CSV is at `<output-root>/s45_f100_p45/IB_Particle_1.csv`
- **And** this equals the path `scripts/extract_forces.py` resolves for that config from `--input-dir <output-root>` (`<input-dir>/<name>/IB_Particle_1.csv`)

#### Scenario: The CSV name is operator-overridable

- **Given** a `csv_name` of `forces.csv` (the solver wrote forces under a different name than the default)
- **When** the runner completes a config named `a`
- **Then** it verifies and records `<output-root>/a/forces.csv` (not the default `IB_Particle_1.csv`), and the run metadata's `ib_particle_csv` is `a/forces.csv` — so a wrong default costs a flag, not a re-run of the corpus

#### Scenario: Live comments state the CSV name as verified

- **Given** `force_surrogate/runner.py`, `force_surrogate/run_one_config.py` and `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`
- **When** each whole file is read
- **Then** none contains `assum` or `not yet verified` anywhere (case-insensitive; these are the only hits today), and each file contains the phrase `verified against the A40 corpus (PR #18)`

### Requirement: Moment coefficients are referenced to the wing hinge

Extracted moment coefficients `CF_mx/CF_my/CF_mz` SHALL be taken about the **wing hinge**, not
about the immersed-boundary particle's own origin as written by IAMReX. Dataset extraction SHALL
apply the parallel-axis shift `M_hinge = M_origin + (r_origin − r_hinge) × F` before
normalization.

**BREAKING**: a corpus extracted before `fix-moment-reference-hinge` (#108) therefore carries different `CF_mx` and
`CF_mz` values; `CF_my` is unchanged wherever the origin-to-hinge offset is purely spanwise.

The reference point is defined canonically in `docs/coordinate-convention.md`
([Coordinate Convention](../coordinate-convention/spec.md)); this capability owns only the
extraction mechanism and SHALL cross-reference rather than restate the definition.

These are **lab-frame moment components taken about the hinge**. The shift relocates the
**origin** only; it does not rotate the axes. A body-frame (wing-frame) moment would additionally
require rotating by `R(t)ᵀ`, which is deferred and not currently tracked. Documentation SHALL NOT
claim the moments are in van Veen's wing frame.

The raw `Mx/My/Mz` columns SHALL retain the solver's as-written values about its own origin,
preserving the audit trail back to CFD output; only the derived `CF_m*` coefficients are referenced to the hinge (and carry the on-wing sign of
"Wing coefficients report the IB force and moment on the wing"; the shift itself is applied to the
solver's own on-fluid `M` and `F`, and the sign afterwards). The applied offset SHALL be recorded in the corpus's dataset-build
provenance so the correction is re-derivable from the committed parquet alone.

#### Scenario: Parallel-axis shift is applied at extraction

- **Given** a run whose CSV `X,Y,Z` columns are a constant `(4, 2, 4)` and whose deck declares `hinge = (4, 0.5, 4)`
- **When** the dataset is extracted
- **Then** the emitted `CF_mx/CF_my/CF_mz` correspond to moments about `(4, 0.5, 4)`, equal to the **negation** of the raw moments shifted by `(0, 1.5, 0) × F`, divided by `m_ref`
- **And** the emitted raw `Mx/My/Mz` columns are bitwise equal to the CSV's values

#### Scenario: A spanwise shift leaves the M_y component invariant

- **Given** a run whose origin-to-hinge offset is purely along the span axis `y`, with all-finite `Fx/Fy/Fz`
- **When** the parallel-axis shift is applied
- **Then** the resulting `CF_my` **compares equal** (`==`, accepting `-0.0 == 0.0`) to the unshifted `CF_my` for every row, because the y-term of `(0, a, 0) × F` is identically zero
- **And** `CF_mx` and `CF_mz` equal `−(Mx + a·Fz)/m_ref` and `−(Mz − a·Fx)/m_ref` exactly — this clause, **not** the `M_y` invariance, is what pins the cross-product **order**, since a reversed `F × d` would also leave the y-component zero
- **And** the y-term arises from evaluating the full three-component cross product, not from special-casing the `y` component

#### Scenario: A non-finite Fx or Fz breaks the M_y invariance

- **Given** a purely spanwise offset `(0, a, 0)` and a row whose `Fx` or `Fz` is NaN or infinite
- **When** the shift is applied
- **Then** that row's `CF_my` is NaN, because the zero-valued coefficient multiplies a non-finite force (`0.0 · NaN = NaN`), and the shift SHALL NOT special-case the term to preserve invariance
- **And** the invariance is conditional on `Fx` and `Fz` specifically, **not** on the forces generally: only those two enter `cross_y = d_z·F_x − d_x·F_z`, so a non-finite `F_y` leaves `CF_my` exactly invariant while contaminating `CF_mx` and `CF_mz`
- **And** no single non-finite force component contaminates all three outputs — each contaminates exactly two

#### Scenario: Committed corpora reconcile against their declared offset

- **Given** a committed `dataset.parquet` and, for each configuration, the origin-to-hinge offset `(0, a, 0)` derived from that configuration's **committed deck** (`particle_inputs.{x,y,z}` − `particle_inputs.hinge_{x,y,z}`) — **not** read back from the dataset-build provenance the same extraction wrote, which would make the check blind to a sign flip (an extractor computing `hinge − origin` records the negated offset and reconciles against it)
- **When** the derived coefficients are recomputed, **per configuration**, from the parquet's own raw `Fx..Mz` columns
- **Then** `CF_mx == −(Mx + a·Fz)/m_ref` and `CF_mz == −(Mz − a·Fx)/m_ref` to `rtol=1e-9`, and `CF_my == −My/m_ref`
- **And** `CF_mx` is **not** `allclose` to `−Mx/m_ref` (a dropped shift) nor to `+(Mx + a·Fz)/m_ref` (a dropped sign), so the check cannot be vacuously satisfied and either regression fails loudly

#### Scenario: Committed moments put the IB-part arm on the wing

- **Given** a committed `dataset.parquet` restricted to settled beats (`wingbeat ≥ 1`), and each configuration's hinge and tip taken from its deck and the wing's vertex file
- **When** the force-weighted spanwise arm is computed per row from the committed **coefficients** scaled back, `b = CF_mx·m_ref / (CF_z·f_ref)` — like-signed, so the sign cancels and a half-flip (only the force or only the moment coefficients negated) fails
- **Then** at least 90% of rows fall in `(0, tip − hinge]` (measured ~97% with the correct shift and under 1% with a sign-flipped **offset**)
- **And** the check is a **calibrated fraction**, not a bound on every row: `b` is a mixed-sign-weighted mean and omits the `−(z_i − z_h)·F_y` term, and `F`/`M` are the spread IB force and moment only, so `b` is the IB-part arm rather than the true centre of pressure

### Requirement: Re-normalization preserves surrogate skill (scale-invariance)

Re-deriving force/moment coefficients under a different per-configuration normalization-scale convention SHALL rescale the CFD targets and the surrogate predictions by the **same** constant,
leaving the held-out **R²** and the predicted-vs-CFD relationship invariant. The frozen corpus's raw
force/moment columns and IB-particle CSVs SHALL NOT be regenerated for a re-normalization convention
change; only derived coefficients change, and no surrogate retraining SHALL be required for that case.

A change of force/moment **sign** convention (`fix-wing-force-sign-convention`, #109) is this scale
case with `k = −1`: the raw columns stay frozen, every `CF_*` becomes exactly `CF_old/(−1)`, and the
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

- **Given** the committed `examples/prelim_sweep/surrogate/holdout_predictions.parquet` (`CF_x_true/pred`, `CF_z_true/pred`, …) whose `R²` matches `metrics.json`
- **When** both the `*_true` and `*_pred` columns are multiplied by the convention factor `k = f_ref_old / f_ref_new` (≈ 3.119)
- **Then** the recomputed per-target `R²` for `CF_x` and `CF_z` each equals the original within `1e-9`, confirming no retrain is needed
- **And** the `RMSE`/`MAE` rescale by exactly `k` (reported honestly), while the scatter shape is unchanged (axes relabeled)

#### Scenario: Raw corpus stays frozen under re-normalization; only derived coefficients move

- **Given** a re-normalization convention change (not a geometry-defect fix, and not a change that retrains by decision such as `fix-wing-force-sign-convention`) re-derives the corpus coefficients
- **When** `dataset.parquet` is regenerated
- **Then** its raw `Fx, Fy, Fz, Mx, My, Mz` column **values** are exactly equal (e.g. `pandas.testing.assert_frame_equal(..., check_exact=True)`) to the committed corpus, only the derived `CF_*` columns change (each new column equals the old divided by `k`), and the committed `metrics.json` per-target `R²` is reused unchanged (within `1e-9`)

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
- **Then** the raw `Fx..Mz` column values are exactly equal, and every `CF_*` column is the old one divided by `−1`, as verified by "Sign re-extraction and retrain pass pre-registered gates"
- **And** the frozen raw-force sha256 pins hold, so the change is not counted among the frozen-corpus exceptions

### Requirement: Dataset build provenance

The dataset build SHALL capture run provenance via the PR1 `capture_surrogate_run_metadata` helper,
requiring a pinned container **digest** (the dataset is downstream of the container CFD run) and a
**caller-supplied** timestamp, and SHALL record any configurations dropped under `allow_missing` so a
truncated corpus is auditable.

The provenance SHALL additionally record the **moment reference point** and the per-configuration
origin-to-hinge offset applied, so the frame travels with the corpus and the correction is
re-derivable from the committed parquet alone. This is provenance, not a unit declaration, and
SHALL NOT be added to `dataset.units.json`, whose closed vocabulary admits only unit strings.

The provenance SHALL likewise record the coefficients' **force sign convention**, under a third
top-level key `force_sign_convention` (see "Wing coefficients report the IB force and moment on the wing"). It is provenance, not a unit, and is likewise absent from `dataset.units.json`.

For a re-extraction that does **not** re-run the CFD, the recorded digest SHALL remain the digest of
the image that produced the underlying CFD data, not that of whatever host performed the
extraction — a corpus's provenance names what produced its measurements.

#### Scenario: Provenance records digest and caller timestamp

- **Given** a container image digest containing `sha256:` and a caller-supplied ISO-8601 timestamp
- **When** the dataset-build provenance is captured
- **Then** the metadata records the git commit, the supplied digest under `docker_image`, and the `timestamp` equal to the supplied value verbatim

#### Scenario: Dropped configurations are recorded under allow_missing

- **Given** a build run with `allow_missing=True` that skipped one or more configurations
- **When** the dropped names returned by `build_dataset` are passed to `capture_surrogate_run_metadata(..., extra={"dropped_configs": [...]})` and the metadata is written
- **Then** the dropped configuration names appear at the **top level** of the metadata under the `dropped_configs` key (because `capture_run_metadata` merges `extra` via `dict.update`, it is **not** nested under an `extra` sub-key), so the short corpus is never silent

#### Scenario: Mutable tag rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** the dataset-build provenance is captured
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording provenance without a pinned image

#### Scenario: Moment reference point travels with the corpus

- **Given** a corpus extracted from decks whose hinge is 1.5 span-units inboard of the particle origin
- **When** its dataset-build provenance is read
- **Then** it names the wing hinge as the reference point for `CF_mx/CF_my/CF_mz`, records the applied offset `(0, 1.5, 0)`, and states that the raw `Mx/My/Mz` columns remain about the solver's own origin
- **And** these live under two top-level keys of the corpus `run_metadata.json`, fixed here so writer and guard are not specified independently:
  - `moment_reference`: `point` (`"wing_hinge"`), `definition` (`"docs/coordinate-convention.md#moments"`), `axes` (`"lab"`), `offset` (`"r_origin - r_hinge"`), `applies_to` (`["CF_mx", "CF_my", "CF_mz"]`), `raw_moments_about` (`"particle_origin"`), and `configs.<name>` with `origin`, `hinge`, `offset` (3-lists), `deck` (the manifest `input_file`), `deck_sha256`, and `deck_sha256_verified_against` (the anchoring metadata file's path, in posix form and not resolved, or `null`)
  - `extraction_inputs`: `input_dir` (the `--input-dir` exactly as given, posix separators — **not** resolved, since resolving a mapped drive records a machine-specific network path; `csv_sha256` is the inputs' identity and the directory only a locator), `csv_name`, and `csv_sha256.<name>` — the sha256 of the exact bytes of each consumed IB-particle CSV
- **And** the per-configuration values are the ones extraction **applied**, returned by `build_dataset` alongside the frame, not re-derived by the driver
- **And** `dataset.units.json` is unchanged in shape — still a flat column-to-unit map over exactly the measured columns

#### Scenario: Re-extraction preserves the CFD digest

- **Given** a committed corpus whose provenance records the digest of the image its CFD ran under
- **When** the corpus is re-extracted from the same raw outputs without re-running the CFD
- **Then** the regenerated provenance records the **same** digest, not the digest of any image used to perform the re-extraction

#### Scenario: A failed write leaves the previous outputs in place

- **Given** an extraction whose dataset, units sidecar or provenance cannot be written
- **When** `extract_forces.py` runs
- **Then** every output is first written in full to a temporary beside its target, and nothing is moved into place until all writes succeeded, so a failure **while writing** leaves every previous output unchanged
- **And** the dataset parquet is moved into place **last**, after its units sidecar and provenance, because three renames cannot be atomic
- **And** a failure **while moving** raises an error naming the outputs already replaced, and keeps the temporaries not yet moved, rather than silently leaving a new parquet beside stale provenance
- **And** duplicate output paths and directory targets are rejected before anything is written

#### Scenario: Force sign convention travels with the corpus

- **Given** a corpus extracted after `fix-wing-force-sign-convention`
- **When** its `run_metadata.json` is read
- **Then** it carries `force_sign_convention` equal to `{"coefficients": "on_wing", "raw_columns": "on_fluid", "raw_source": "IAMReX kernel.ib_force / kernel.ib_moment", "applies_to": ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"], "definition": "docs/coordinate-convention.md#force-and-moment-sign"}`, written by the extraction driver and checked against **both committed corpora** by a CI test
- **And** each committed `dataset.units.json` equals its pinned key/value literal (the sign is not declared there)

### Requirement: Committed surrogate artifacts are tied to the dataset they were trained on

Training SHALL record, in the surrogate's `run_metadata.json`, the path and sha256 of the dataset
parquet it consumed (`inputs.file` / `inputs.hash`, via the existing `capture_run_metadata`
`inputs_file` channel), so that which corpus produced a committed `surrogate.pt` is auditable rather
than inferred.

A CI-runnable check SHALL reconcile each committed surrogate — the coarse `examples/prelim_sweep/` and the fine
`examples/prelim_sweep_fine/` — against its own corpus's committed dataset. Outside one pinned state the reconciliation is
unconditional: every `<target>_true` column of `holdout_predictions.parquet`, for all six targets,
equals the corresponding `dataset.parquet` column on `(config_name, time)`, the recorded `inputs.hash`
equals the sha256 of the committed `dataset.parquet`, and the committed phase-baseline skill
recomputes from the committed dataset.

The one pinned state is a surrogate trained before `fix-wing-force-sign-convention` (#109) negated the
coefficients, while its corpus README carries the staleness banner ("are stale against
`dataset.parquet`"). Then every `<target>_true` SHALL equal the **negated** dataset column (and SHALL
NOT be `allclose` to the dataset column, all-zero columns excepted and reported); `inputs.hash` SHALL
equal the pinned sha256 of that corpus's pre-change `dataset.parquet` and SHALL NOT equal the current
one; the phase-baseline skill SHALL recompute against the negated dataset; and the coarse
`seed_variation.json` `datasets.hinge_referenced.dataset_sha256` SHALL equal the same pinned
pre-change sha. The banner SHALL be present
exactly while this state holds, in both corpus READMEs, and SHALL tell a reader that the committed
surrogate predicts the force on the fluid, so its outputs must be negated. No other mismatch is
acceptable.

#### Scenario: Training metadata names the dataset

- **Given** a training run over a dataset parquet
- **When** `build_training_metadata` assembles the run's provenance
- **Then** the record's `inputs.file` names that parquet and `inputs.hash` is its sha256

#### Scenario: A surrogate trained on a different dataset fails CI

- **Given** a committed `holdout_predictions.parquet` whose `<target>_true` values for any of the six targets differ from the committed `dataset.parquet`, or a recorded `inputs.hash` that is not the committed parquet's sha256
- **When** the committed-artifact tests run
- **Then** they fail, naming the target or the hash mismatch

#### Scenario: A surrogate trained before the sign change is stale by exactly a sign flip

- **Given** a corpus whose README carries the staleness banner
- **When** the committed-artifact tests run
- **Then** every holdout `<target>_true` equals the negated dataset value for all six targets and the column is not `allclose` to the dataset value (all-zero columns excepted and reported), `inputs.hash` equals the pinned pre-change sha256, and the phase-baseline skill recomputes against the negated dataset
- **And** when the banner is absent the unconditional reconciliation applies, so the banner can be neither forgotten while stale nor left behind after the retrain

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

- **And** in the pinned stale-by-sign state of "Committed surrogate artifacts are tied to the dataset they were trained on", only the `<target>_true`, `inputs.hash` and `phase_baseline_skill` clauses above are replaced by that requirement's stale-by-sign clauses; every other clause still holds

#### Scenario: The fine figure is tied to the fine surrogate and regenerates from it

- **Given** the committed fine figure artifacts and the committed fine surrogate outputs
- **When** the committed-artifact tests run
- **Then** the figure's `run_metadata.json` hashes the fine `holdout_predictions.parquet` and `metrics.json` and records `grid == "fine"`, and regenerating the sidecar from the committed fine predictions and metrics with the `fine` profile and the recomputed fine CFD cost reproduces the committed `evidence_figure_metrics.json` (exact for copied values, relative 1e-12 for the two computed quasi-steady RMS values)

#### Scenario: Reruns that differ halt the change

- **Given** two full fine training runs from the same commit whose `surrogate.pt` or `holdout_predictions.parquet` bytes differ, whose `metrics.json` differ outside the `inference` wall-clock fields, whose `run_metadata.json` differ outside `run_id`, or either of which records `dirty: true`
- **When** the gate is evaluated
- **Then** no fine artifact is committed and the change stops for a decision with the user
