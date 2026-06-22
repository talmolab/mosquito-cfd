# force-surrogate Specification

## Purpose
TBD - created by archiving change add-force-surrogate-foundation. Update Purpose after archive.
## Requirements
### Requirement: Single-source force normalization

The force-surrogate module SHALL be the single, parameterized source for aerodynamic force
normalization and force-coefficient computation. The reference normalization SHALL be a pure
function of its kinematic and geometric inputs (no hardcoded amplitude/frequency, no I/O) and
SHALL reproduce the validated reference values. No other module SHALL re-derive `F_ref` inline.

#### Scenario: Reference normalization at the validated point

- **Given** `f_star = 1.0`, `phi_amp_deg = 70.0`, `r_tip = 3.0`, `span = 3.0`, `chord = 1.0`, `rho = 1.0`
- **When** `compute_force_reference` is called
- **Then** it returns `u_tip_max ≈ 23.029`, `q_tip ≈ 265.17`, `area ≈ 2.3562`, `f_ref ≈ 624.79` (each within 0.1%; these are recomputed from the formula and consistent with the rounded values in `examples/flapping_wing/RESULTS.md`)

#### Scenario: Parameterization, not hardcoded

- **Given** the validated inputs with `phi_amp_deg` reduced from 70° to 35°
- **When** `compute_force_reference` is called
- **Then** both `u_tip_max` and `f_ref` are strictly smaller than at 70°
- **And** doubling `f_star` doubles `u_tip_max`

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
- **Then** it calls `compute_force_reference` from this module rather than re-deriving `F_ref` inline, and still reports `f_ref ≈ 624.79`

### Requirement: Dimensionless units sidecar

The force-surrogate module SHALL emit and parse a `units.json` sidecar declaring the unit of every
data column, validated **on both write and read** against a documented dimensionless units
vocabulary (dimensionless coefficients/forces, angles in degrees, dimensionless frequency/time).
The pipeline is dimensionless by design; `openspec/project.md` is silent on a units convention, so
this establishes one for surrogate data (a physical SI mapping, if ever needed, is a downstream
concern).

#### Scenario: Units sidecar round-trip

- **Given** a units mapping over surrogate columns (e.g. `{"cf_x": "dimensionless", "stroke_amp": "deg", "frequency": "dimensionless (f*)"}`)
- **When** it is written with `write_units_sidecar` and read back with `read_units_sidecar`
- **Then** the parsed mapping equals the original, and the file is UTF-8 JSON

#### Scenario: Unknown unit rejected on write

- **Given** a units mapping with a column unit not in the vocabulary (e.g. `{"force": "newtons"}`)
- **When** `write_units_sidecar` is called
- **Then** it raises `ValueError` naming the offending column and unit

#### Scenario: Non-string column or unit rejected

- **Given** a units mapping whose column key or unit value is not a string (e.g. `{1: "dimensionless"}` or `{"cf_x": 2.0}`)
- **When** `write_units_sidecar` is called
- **Then** it raises `ValueError` (non-string keys would be silently coerced by JSON and not round-trip)

#### Scenario: Invalid sidecar rejected on read

- **Given** a `units.json` on disk that is malformed (not a JSON object) or carries a unit outside the vocabulary
- **When** `read_units_sidecar` is called
- **Then** it raises `ValueError` (read enforces the same vocabulary as write)

### Requirement: Run provenance with caller-supplied timestamp and container digest

The force-surrogate module SHALL capture run provenance by reusing the existing benchmarks metadata
capture, and SHALL (a) require the Docker image **digest** (not merely a tag) and (b) accept a
**caller-supplied timestamp** so artifacts are reproducible rather than stamped with wall-clock
time at runtime (CC-1).

#### Scenario: Run provenance includes container digest

- **Given** a Docker image digest, an existing inputs file, and a caller-supplied ISO timestamp
- **When** `capture_surrogate_run_metadata` is called
- **Then** the returned metadata records the git commit, the supplied image digest (under `docker_image`), and the inputs hash

#### Scenario: Caller-supplied timestamp recorded

- **Given** a caller-supplied ISO-8601 timestamp string
- **When** `capture_surrogate_run_metadata` is called
- **Then** the returned metadata's `timestamp` equals the supplied value verbatim (an ISO-8601 string), not the runtime wall clock

#### Scenario: Missing digest rejected

- **Given** an empty or missing Docker image digest
- **When** `capture_surrogate_run_metadata` is called
- **Then** it raises `ValueError` rather than recording provenance without a pinned image

#### Scenario: Mutable tag rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** `capture_surrogate_run_metadata` is called
- **Then** it raises `ValueError` — only a content-addressable digest (containing `sha256:`) is accepted, and surrounding whitespace is stripped before recording

### Requirement: Cluster-free test fixtures

The repository SHALL provide committed synthetic fixtures that allow force-surrogate tests to run
without the RunAI cluster, a GPU, or AMReX plotfiles.

#### Scenario: Synthetic fixture is usable cluster-free

- **Given** the committed `tests/fixtures/synthetic_ib_particle.csv`
- **When** it is loaded in a test with no cluster/GPU available
- **Then** it parses (name-based, not positional), mirrors the real IB-particle schema in column order (`iStep,time,X,Y,Z,Vx,Vy,Vz,Rx,Ry,Rz,Fx,Fy,Fz,Mx,My,Mz,Fcp{x,y,z},Tcp{x,y,z},SumU{x,y,z},SumT{x,y,z}` — `Fx,Fy,Fz` at their real positions), and its forces yield the exact known coefficients when normalized by the fixture's round reference `F_ref`

### Requirement: Aedes-anchored kinematic sweep grid

The force-surrogate module SHALL build the biologically-anchored kinematic sweep grid as a pure
function of its level inputs, defaulting to the *Aedes aegypti* levels (stroke amplitude φ ∈
{35, 45, 55}°, dimensionless frequency f\* ∈ {0.85, 1.0, 1.15}, pitch amplitude α ∈ {30, 45, 60}°;
27 configurations). Each configuration SHALL carry the documented schema keys
`stroke_amp_deg`, `frequency_fstar`, `pitch_amp_deg` — the same keys as the committed
`tests/fixtures/micro_sweep.json` fixture, so the generator is testable cluster-free against it.
The default levels SHALL be defined as named, source-attributed constants (Bomphrey 2017).

#### Scenario: Default grid cardinality and levels

- **Given** `build_kinematic_grid` is called with no arguments
- **Then** it returns 27 configurations whose `stroke_amp_deg` values are drawn from {35, 45, 55}, `frequency_fstar` from {0.85, 1.0, 1.15}, and `pitch_amp_deg` from {30, 45, 60}
- **And** every (stroke, frequency, pitch) combination appears exactly once

#### Scenario: Config schema matches the micro-sweep fixture

- **Given** the committed `tests/fixtures/micro_sweep.json` (2 configs with keys `stroke_amp_deg, frequency_fstar, pitch_amp_deg`)
- **When** it is loaded and passed to the generator as the config list
- **Then** the generator accepts it without a schema error and produces exactly 2 input files (cluster-free, no RunAI/GPU/plotfiles)

#### Scenario: Malformed or empty config rejected

- **Given** a config list that is empty, or a config dict missing a required key (e.g. no `pitch_amp_deg`) or carrying an unknown key
- **When** it is passed to the generator
- **Then** it raises `ValueError` naming the offending config/key rather than emitting an underspecified or zero-file sweep

### Requirement: Reynolds policy holds ν\* fixed across the sweep

The module SHALL hold the dimensionless viscosity ν\* (`ns.vel_visc_coef`) **fixed** at the
validated `0.115` for every generated configuration, so that the Reynolds number varies as a
deterministic function of the swept stroke amplitude and frequency. `compute_reynolds` SHALL use
the **midspan arm `r_mid = 1.5`** (the viscous-scaling arm), NOT the force-normalization tip arm
`R_TIP = 3.0`, computing `Re = 2π · f* · radians(φ) · r_mid / ν*`. The per-configuration Reynolds
number SHALL be recorded in the sweep manifest.

#### Scenario: Reynolds reproduces the validated point

- **Given** `stroke_amp_deg = 70.0`, `frequency_fstar = 1.0`, `nu_star = 0.115`
- **When** `compute_reynolds` is called
- **Then** it returns approximately 100 (within 1%), matching the `inputs.3d.validation` header (`V_tip* ≈ 11.5`, `ν* = 11.5 / 100`)

#### Scenario: Reynolds uses the midspan arm, not the tip arm

- **Given** identical kinematics and ν\*
- **When** `compute_reynolds` (which uses `r_mid = 1.5`) is compared against the same formula evaluated with `R_TIP = 3.0`
- **Then** the two differ by the factor `R_TIP / r_mid = 2`, confirming the midspan arm is used

#### Scenario: ν\* identical across all generated files

- **Given** the default 27-config sweep is generated
- **When** each generated input file is parsed
- **Then** every file has `ns.vel_visc_coef = 0.115` (the viscosity is not perturbed per config)
- **And** the manifest records each config's `nu_star = 0.115` and a `reynolds` value equal to `compute_reynolds` for that config's kinematics

#### Scenario: Non-positive viscosity rejected

- **Given** `nu_star <= 0` (a degenerate or non-physical viscosity)
- **When** `compute_reynolds` is called
- **Then** it raises `ValueError` rather than returning `inf`/`NaN` or a sign-flipped Reynolds number (parity with the PR1 `compute_force_coefficients` non-positive-reference guard)

### Requirement: Run duration scaled to whole wingbeats

The module SHALL set each configuration's run duration to cover a fixed, configurable number of
**complete wingbeats** (default 2) at the validated fixed timestep `dt = 5e-4`, via
`stop_time = n_wingbeats / f*` and `max_step = round(stop_time / dt)`. This guarantees every
configuration — including low-frequency ones where a fixed `stop_time = 1.0` would cover less than
one beat — captures whole periodic cycles. `dt` SHALL NOT be changed from the validated value.

#### Scenario: Duration matches the per-frequency formula

- **Given** `frequency_fstar = 0.85`, `n_wingbeats = 2`, `dt = 5e-4`
- **When** `derive_run_duration` is called
- **Then** `stop_time ≈ 2.3529` (= 2 / 0.85) and `max_step = 4706` (= round(2.3529 / 5e-4))

#### Scenario: Every config covers at least the requested whole wingbeats

- **Given** the default 27-config sweep with `n_wingbeats = 2`
- **When** each generated input file is parsed
- **Then** for every config `stop_time * frequency_fstar ≥ 2` (at least two complete beats)
- **And** every config retains the validated `ns.fixed_dt = 0.0005`

### Requirement: Force-only input generation with minimal diff

The module SHALL generate each IAMReX input file from the validated base file
(`examples/flapping_wing/inputs.3d.validation`) by rewriting **only** the swept kinematic keys
(`particle_inputs.kinematics_stroke_amp`, `particle_inputs.kinematics_frequency`,
`particle_inputs.kinematics_pitch_amp`) and the derived run-control keys (`max_step`, `stop_time`,
`amr.plot_int`), matching each key on its **full name** (not a prefix), preserving all comments,
blank lines, ordering, and unrelated keys. `amr.plot_int` SHALL be forced to **-1** (force-only: no
field plotfiles), a targeted key absent from the base SHALL raise rather than be silently skipped,
generated files SHALL use **LF (`\n`) line endings** regardless of host platform, and numeric values
SHALL be written with a **deterministic, platform-independent formatter** so the corpus is byte-reproducible.

#### Scenario: Generated file differs from base only in the swept and derived keys

- **Given** a generated input file and the base `inputs.3d.validation`
- **When** both are parsed into key→value maps
- **Then** the keys whose values differ are exactly `{particle_inputs.kinematics_stroke_amp, particle_inputs.kinematics_frequency, particle_inputs.kinematics_pitch_amp, max_step, stop_time, amr.plot_int}`
- **And** all other keys (e.g. `geometry_type`, `geometry_file`, `hinge_*`, `ns.vel_visc_coef`, projection tolerances) are unchanged
- **And** `particle_inputs.kinematics_deviation_amp` (a prefix-sibling of the swept stroke/pitch keys, present in the base) is byte-unchanged — the rewrite matches full keys, not the `kinematics_` prefix

#### Scenario: Plot output disabled in every config

- **Given** the default 27-config sweep is generated
- **When** each generated input file is parsed
- **Then** every file has `amr.plot_int = -1`

#### Scenario: Missing target key is rejected

- **Given** a base inputs text that lacks one of the targeted keys (e.g. `amr.plot_int`)
- **When** `render_inputs` is called
- **Then** it raises `ValueError` naming the missing key rather than producing a file without the forced value

#### Scenario: LF newlines and deterministic numeric formatting

- **Given** a sweep is generated to disk (and, separately, `render_inputs` is called on a base text)
- **When** a written input file is read back as raw bytes and a representative config's rendered text is inspected
- **Then** the file on disk contains no `\r` byte (LF-only, regardless of host platform — the write uses `newline=""`), and the config renders the exact, platform-independent value strings (e.g. `particle_inputs.kinematics_frequency = 0.85`, `max_step = 4706` as a bare integer) so two regenerations on different platforms are byte-identical

### Requirement: Held-out configuration split is seeded, non-corner, and label-only

The module SHALL designate a fixed, configurable number of **held-out configurations** (default 6)
for the eventual predicted-vs-CFD figure, selected deterministically from a seed
(`numpy.random.default_rng`) and drawn only from grid **non-corner** configurations (a corner has
all three parameters at an extreme level). The held-out designation SHALL be a training-exclusion
**label only**: all configurations (held-out included) are still generated and recorded, since the
held-out set is the CFD ground truth. The seed and the resulting split SHALL be recorded in the
manifest.

#### Scenario: Six non-corner held-out configs, deterministic by seed

- **Given** the default 27-config grid and a fixed seed
- **When** `select_holdout` is called
- **Then** it returns exactly 6 configuration indices, none of which is a grid corner (a corner has all three parameters at an extreme level: 8 corners, 19 eligible non-corners)
- **And** calling it again with the same seed returns the identical set (selection samples a deterministically ordered eligible list, not a hash-ordered set)

#### Scenario: Holdout larger than the eligible set is rejected

- **Given** a config list whose non-corner eligible count is smaller than the requested `n_holdout` (e.g. the 2-config micro-sweep with `n_holdout = 6`)
- **When** `select_holdout` is called
- **Then** it raises `ValueError` rather than sampling with replacement or looping indefinitely

#### Scenario: All configs generated regardless of split

- **Given** the default sweep with 6 held-out configs
- **When** the sweep is generated
- **Then** 27 input files are written (held-out configs are generated too)
- **And** the manifest marks exactly 6 configs `split = "holdout"` and 21 `split = "train"`

### Requirement: Reproducible sweep manifest with units sidecar

The module SHALL emit a **deterministic** `sweep_manifest.json` recording, per configuration, the
kinematic parameters, `nu_star`, `reynolds`, derived `max_step`/`stop_time`, `plot_int`, the
train/holdout `split`, and the input-file path; plus top-level grid levels, the resolved Reynolds
policy, and the holdout seed. It SHALL emit a `sweep_manifest.units.json` via the PR1
`write_units_sidecar` helper declaring the unit of each measured column. It SHALL emit a separate
`sweep_provenance.json` carrying environmental provenance — git commit, base-inputs SHA256, and a
**caller-supplied** timestamp, and **no** Docker image digest (PR2 runs no container). Provenance is
kept out of the manifest so the manifest stays byte-reproducible: the `git_commit` is inherently
non-reproducible across checkouts, so it must not contaminate the byte-identity guarantee.
Regenerating the sweep with the recorded seed and timestamp SHALL produce byte-identical input files
and a byte-identical manifest + units sidecar.

#### Scenario: Manifest records the resolved Reynolds policy and per-config Re

- **Given** a generated sweep
- **When** `sweep_manifest.json` is read
- **Then** it records `reynolds_policy = "nu_star_fixed"`, `nu_star = 0.115`, and for each config a `reynolds` value exactly equal (round-trip) to `compute_reynolds` for that config's kinematics, serialized with canonical (non-truncated) float formatting

#### Scenario: Configs recorded in a canonical, stable order

- **Given** a generated sweep
- **When** the `configs[]` list and the input-file names are inspected
- **Then** the configs appear in a single documented, stable order (stroke × frequency × pitch nested enumeration), each config's `index` equals its position, and the input-file naming sorts consistently with that order — so a downstream consumer that globs filenames and one that reads `configs[]` see the same configuration sequence

#### Scenario: Provenance records git + base hash + caller timestamp, and no digest

- **Given** a generated sweep with a caller-supplied ISO-8601 timestamp
- **When** the `sweep_provenance.json` sidecar is read
- **Then** it records the git commit, the base-inputs SHA256 (equal to `hash_file(inputs.3d.validation)`), and `generated_at` equal to the supplied timestamp verbatim
- **And** it contains no Docker image digest field (the pinned-digest run metadata is emitted by the cluster-run stage, not config generation), and `git_commit` lives here rather than in `sweep_manifest.json` so the manifest stays byte-reproducible

#### Scenario: Units sidecar validates against the dimensionless vocabulary

- **Given** the emitted `sweep_manifest.units.json`
- **When** it is read with `read_units_sidecar`
- **Then** it parses without error and maps `stroke_amp_deg → "deg"`, `pitch_amp_deg → "deg"`, `frequency_fstar → "dimensionless (f*)"`, and `nu_star`/`reynolds`/`stop_time → "dimensionless"`

#### Scenario: Byte-identical regeneration

- **Given** the committed sweep artifacts and the seed + timestamp recorded in their manifest
- **When** the sweep is regenerated into a clean directory with that seed and timestamp
- **Then** each regenerated input file is byte-identical to its committed counterpart
- **And** the regenerated `sweep_manifest.json` and `sweep_manifest.units.json` are byte-identical to their committed counterparts (deterministic key order, float formatting, and config list order)

### Requirement: Single-source moment normalization

The force-surrogate module SHALL be the single, parameterized source for aerodynamic **moment**
normalization and moment-coefficient computation, sibling to the published force normalization. The
reference moment SHALL be `M_ref = q_tip · area · L` with the moment length scale **`L = chord`**,
where `q_tip` and `area` are computed by the **same formulas** as the force reference (no second
copy). It SHALL be a pure function of its kinematic and geometric inputs (no hardcoded
amplitude/frequency, no I/O), SHALL reproduce the validated reference value, and SHALL NOT be
re-derived inline by any other module.

#### Scenario: Moment reference at the validated point

- **Given** `f_star = 1.0`, `phi_amp_deg = 70.0`, `r_tip = 3.0`, `span = 3.0`, `chord = 1.0`, `rho = 1.0`
- **When** `compute_moment_reference` is called
- **Then** it returns `m_ref ≈ 624.79` (within 0.1%, i.e. `rtol=1e-3`), equal to `q_tip · area · chord` and — because `chord = 1.0` — numerically equal to the force reference `f_ref` at the same point, while remaining a distinct, chord-parameterized quantity
- **And** the returned `length` field equals the supplied `chord`

#### Scenario: Moment reference scales with the chord length scale and reuses the force reference

- **Given** the validated inputs evaluated once with `chord = 1.0` and once with `chord = 2.0`
- **When** `compute_moment_reference` is called for each
- **Then** the second `m_ref` is exactly **four** times the first — because `chord` enters `m_ref` **twice**, once through the area (`S = π/4·span·chord`) and once through the explicit moment length scale `L = chord`, so `m_ref` scales **quadratically** with chord — confirming the helper is genuinely parameterized on chord rather than hardcoding `L = 1.0`
- **And** at a **non-unit** chord (e.g. `chord = 2.0`) `m_ref` equals `compute_force_reference(same kinematics/geometry).f_ref · chord` exactly — proving the moment helper reuses the force reference's `q_tip`/`area` (CC-3, single source) rather than carrying a divergent second copy of the formula (an equality that would hold trivially at `chord = 1.0` and hide a copy)

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
single-source normalization helpers (with `f_star = frequency_fstar`, `phi_amp_deg = stroke_amp_deg`),
and emit **one row per (configuration × timestep)**. The build SHALL return both the dataframe and
the list of any configurations dropped under `allow_missing`, so the caller can record the drop in
run metadata (the dataframe alone provides no channel for the dropped names).

#### Scenario: One row per configuration and timestep

- **Given** a manifest with `N` configurations, each mapped to an IB-particle CSV with `T` timesteps
- **When** `build_dataset` is called
- **Then** the returned dataframe has exactly `N × T` rows, one per (configuration, timestep)

#### Scenario: Columns are the documented schema

- **Given** a built dataset
- **When** its columns are inspected
- **Then** they are exactly `config_name, index, time, phase, wingbeat, stroke_amp_deg, frequency_fstar, pitch_amp_deg, reynolds, split, Fx, Fy, Fz, Mx, My, Mz, CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz` — carrying all three force coefficients, all three moment coefficients, and the raw forces and moments

#### Scenario: Coefficients use the single-source per-config normalization

- **Given** the committed `synthetic_ib_particle.csv` mapped to a **synthetic single-config manifest** at the validated point (`stroke_amp_deg = 70.0`, `frequency_fstar = 1.0`, `pitch_amp_deg = 45.0`) — chosen because no committed-corpus config is at φ=70°, and so the per-config `f_ref` is the regression-locked `≈ 624.79`
- **When** `build_dataset` is called
- **Then** each `CF_x` equals `Fx / compute_force_reference(f_star=1.0, phi_amp_deg=70.0, r_tip=R_TIP, span=SPAN, chord=CHORD, rho=RHO).f_ref` and each `CF_mx` equals `Mx / compute_moment_reference(...).m_ref` (and likewise for y/z) — **ratio** equality, not round literals (the validated `f_ref ≈ 624.79` is not round, so `CF_x = 50/624.79 ≈ 0.080`, etc.), confirming the extractor reuses the PR1/PR4 helpers rather than re-deriving a reference inline (CC-3)
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

### Requirement: Dataset units sidecar

The force-surrogate module SHALL emit a `dataset.units.json` sidecar for the extracted dataset via
the PR1 `write_units_sidecar` helper, declaring the unit of every **measured** column against the
existing dimensionless units vocabulary, and SHALL NOT introduce a new unit (every dataset quantity
is already expressible as `dimensionless`, `deg`, or `dimensionless (f*)`).

#### Scenario: Units sidecar validates against the dimensionless vocabulary

- **Given** an emitted `dataset.units.json`
- **When** it is read with `read_units_sidecar`
- **Then** it parses without error and maps `CF_x/CF_y/CF_z/CF_mx/CF_my/CF_mz`, `phase`, `time`, the raw forces/moments `Fx..Mz`, and `reynolds` → `"dimensionless"`; `stroke_amp_deg`/`pitch_amp_deg` → `"deg"`; `frequency_fstar` → `"dimensionless (f*)"`

#### Scenario: Non-measured columns are omitted

- **Given** an emitted `dataset.units.json`
- **When** its keys are inspected
- **Then** the string columns `config_name`/`split` and the bookkeeping counts `index`/`wingbeat` are absent (only measured columns are declared, mirroring the sweep-manifest units convention)

### Requirement: Dataset build provenance

The dataset build SHALL capture run provenance via the PR1 `capture_surrogate_run_metadata` helper,
requiring a pinned container **digest** (the dataset is downstream of the container CFD run) and a
**caller-supplied** timestamp, and SHALL record any configurations dropped under `allow_missing` so a
truncated corpus is auditable.

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

### Requirement: Force-only dataset scope guard

The dataset extractor SHALL derive all forces and moments from the IB-particle CSV alone and SHALL
NOT read AMReX plotfiles or velocity/pressure fields (CC-6). The force-only path keeps the dataset
build cluster-free and sidesteps the velocity-field-in-plotfiles issue entirely.

#### Scenario: Extraction consumes only the CSV and manifest

- **Given** the dataset-build inputs
- **When** `build_dataset` is called
- **Then** it requires only the IB-particle CSV(s) and `sweep_manifest.json` — it neither accepts nor requires a plotfile/field path — and runs with no cluster, GPU, or AMReX plotfile present

### Requirement: Per-configuration cluster run command construction

The force-surrogate module SHALL build, as a **pure function** of a sweep configuration, the
RunAI `workspace exec` command that runs one configuration's force-only CFD through the pinned
container. The command SHALL wrap the validated IAMReX launch
(`mpirun --allow-run-as-root -np 1 <iamrex_binary> <deck>`) with the per-configuration container
run directory `<container_workspace>/<runs_subdir>/<name>` as the working directory (so IAMReX
writes its IB-particle CSV there), SHALL stage `wing.vertex` into that working directory (the
deck's `particle_inputs.geometry_file = wing.vertex` is resolved relative to the working
directory), and SHALL reference the deck by its `input_file` path under the container workspace.
Command construction SHALL perform no I/O and SHALL NOT import `subprocess` or any cluster client.

#### Scenario: Command targets the per-config run directory and deck

- **Given** a config `{name: "s35_f085_p30", input_file: "inputs/inputs.3d.s35_f085_p30", max_step: 4706}` and `workspace = "sweep-runner"`
- **When** `build_run_command` is called with the default container workspace `/workspace`
- **Then** it returns `["runai", "workspace", "exec", "sweep-runner", "--", "sh", "-c", <inner>]`
- **And** `<inner>` sets the working directory to `/workspace/runs/s35_f085_p30`, copies the staged `wing.vertex` into that directory, and runs `mpirun --allow-run-as-root -np 1 <iamrex_binary> /workspace/inputs/inputs.3d.s35_f085_p30`

#### Scenario: Every corpus configuration yields a distinct, correctly-targeted command

- **Given** the committed `examples/prelim_sweep/sweep_manifest.json` (27 configs)
- **When** `build_run_command` is called for each config
- **Then** it produces 27 commands, each whose run directory ends in that config's `name` and whose deck path ends in that config's `input_file`, with no two commands sharing a run directory

#### Scenario: Command construction is pure (no cluster, no I/O)

- **Given** a single config dict
- **When** `build_run_command` is called with no cluster, GPU, or container present
- **Then** it returns the command list without reading or writing any file and without invoking RunAI

### Requirement: Per-configuration output layout matches the dataset driver contract

The runner SHALL write each configuration's IB-particle force CSV to
`<output-root>/<name>/<csv-name>` — the **exact** path that the merged dataset driver
(`scripts/extract_forces.py`) resolves from its `--input-dir <output-root>`. This guarantees the
PR4 extractor consumes the runner's output with no glue. The CSV filename SHALL default to the
assumed IAMReX per-run name `IB_Particle_1.csv` and SHALL be **operator-overridable** (a `csv_name`
parameter / `--csv-name` flag, mirroring `extract_forces.py`), because that name is inherited from
PR4's contract and is not yet verified against a real IAMReX run.

#### Scenario: Runner output is the path the extractor reads

- **Given** an `output-root` and a config named `s45_f100_p45`
- **When** the runner completes that config
- **Then** its CSV is at `<output-root>/s45_f100_p45/IB_Particle_1.csv`
- **And** this equals the path `scripts/extract_forces.py` resolves for that config from `--input-dir <output-root>` (`<input-dir>/<name>/IB_Particle_1.csv`)

#### Scenario: The CSV name is operator-overridable

- **Given** a `csv_name` of `forces.csv` (the solver wrote forces under a different name than the default)
- **When** the runner completes a config named `a`
- **Then** it verifies and records `<output-root>/a/forces.csv` (not the default `IB_Particle_1.csv`), and the run metadata's `ib_particle_csv` is `a/forces.csv` — so a wrong default costs a flag, not a re-run of the corpus

### Requirement: Per-run cluster provenance with pinned digest

Each completed configuration run SHALL emit a `run_metadata.json` via the force-surrogate
provenance helper `capture_surrogate_run_metadata`, requiring a pinned container **digest**
(containing `sha256:`) and a **caller-supplied** timestamp (CC-1). The metadata SHALL record the
digest, the timestamp verbatim, and portable provenance (the configuration name, the deck's
manifest-relative path — its `input_file`, the same portable identifier PR4 uses — and its SHA256,
and the exact logical command), and SHALL NOT record absolute host mount paths. A missing or mutable-tag digest SHALL be rejected **before** any
container run is launched.

#### Scenario: Provenance records the pinned digest and caller timestamp

- **Given** a container image reference containing `sha256:` and a caller-supplied ISO-8601 timestamp
- **When** a configuration run completes
- **Then** its `<output-root>/<name>/run_metadata.json` records the digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, the config name, and the deck's SHA256

#### Scenario: Mutable tag rejected up front

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** `run_sweep` is called
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) before any configuration's run command is issued to the executor

#### Scenario: Recorded provenance is portable

- **Given** a completed run's `run_metadata.json`
- **When** every nested string value is inspected
- **Then** no value is an absolute host mount path (none matches a `^[A-Za-z]:\\` drive-letter path nor starts with `/hpi/`); the **deck** is identified by its manifest-relative path (`deck`, the config's `input_file`) plus its SHA256 (`deck_sha256`), while the recorded **command** embeds portable container (`/workspace/...`) paths — two intentionally different fields
- **And** the metadata has no `inputs.file` key (the deck id is supplied via `extra=`, not via `inputs_file=`, because the base capture records an absolute `inputs.file` path when given `inputs_file=`)

### Requirement: Run completion verification

The runner SHALL verify each configuration's IB-particle CSV is complete: the file SHALL exist,
its header SHALL equal the documented 29-column IB-particle schema (`IB_PARTICLE_COLUMNS`, reused
from the dataset module — not re-listed), and its data-row count SHALL be at least
`max_step · threshold` (default threshold 0.99, configurable). A missing, empty (header-only), or
short CSV SHALL be flagged incomplete with a distinguishing reason; a full-length CSV SHALL pass.

#### Scenario: Full-length CSV passes

- **Given** an IB-particle CSV with the correct 29-column header and `max_step` data rows
- **When** `check_completion` is called with that config's `max_step`
- **Then** it reports complete with `rows == max_step` and `reason == "ok"`

#### Scenario: Empty and short CSVs are flagged incomplete

- **Given** a header-only CSV (zero data rows), and separately a CSV with fewer than `max_step · threshold` data rows
- **When** `check_completion` is called
- **Then** the header-only CSV is incomplete with `reason == "empty"` and the short CSV is incomplete with `reason == "short"`

#### Scenario: Missing CSV and wrong header are distinguished

- **Given** a config whose CSV **path does not exist**, and separately a CSV whose first line is not the 29-column schema
- **When** `check_completion` is called
- **Then** the missing path is incomplete with `reason == "missing"` (not an error — this is the resume signal) and the mis-headed CSV is incomplete with `reason == "bad_header"`

#### Scenario: Row-count threshold boundary is exact

- **Given** a `max_step` and `threshold` whose product is non-integer (e.g. `max_step = 4706`, `threshold = 0.99` → `ceil(max_step · threshold) = 4659`)
- **When** `check_completion` is called on a CSV with exactly `ceil(max_step · threshold)` data rows, and separately on one with exactly one fewer
- **Then** the first is complete (`reason == "ok"`) and the second is incomplete (`reason == "short"`) — the boundary is `rows >= ceil(max_step · threshold)`, pinning the off-by-one
- **And** the data-row count is correct whether or not the CSV ends in a trailing newline, and whether its line ending is `\n` or `\r\n` (a trailing newline is not counted as an extra data row)

### Requirement: Idempotent resume of a partial corpus

The runner SHALL skip any configuration whose IB-particle CSV already passes the completion check,
so that re-running over a partially-completed corpus resumes rather than recomputes (the A40
allocation is preemptible). The skip SHALL be logged and reported, never silent, and SHALL pair
with the dataset extractor's `allow_missing` so a still-incomplete corpus is auditable downstream.
Resume SHALL be enabled by default and disable-able by the caller.

#### Scenario: Already-complete configuration is skipped, the rest run

- **Given** an `output-root` in which one config's `IB_Particle_1.csv` already passes the completion check and the others are absent, with `resume=True`
- **When** `run_sweep` is called
- **Then** the already-complete config has `status == "skipped"` and **no** run command is issued to the executor for it
- **And** every other config has a run command issued and (on a successful executor) `status == "completed"`

#### Scenario: Resume can be disabled

- **Given** the same already-complete config with resume disabled
- **When** `run_sweep` is called
- **Then** a run command **is** issued for that config (it is re-run, not skipped)

#### Scenario: A partial (short) CSV is re-run, not skipped

- **Given** an `output-root` where one config's `IB_Particle_1.csv` exists but has fewer than `max_step · threshold` rows (a preempted run), with `resume=True`
- **When** `run_sweep` is called
- **Then** that config is **re-run** (a command is issued, `status != "skipped"`) — resume skips only configs that pass the completion check, never configs whose CSV is merely present, so a preempted partial run is correctly resumed rather than mistaken for complete

### Requirement: Cluster-free injected executor seam (force-only)

The runner SHALL take the container launch as an **injected executor** so all of its logic is
testable without RunAI, a GPU, or a container (CC-2). The executor SHALL be a callable
`executor(command, *, cwd) -> ExecResult`; the tested library SHALL NOT import `subprocess` or a
cluster client (those live only in the thin driver's real executor). The runner SHALL operate
**force-only** (CC-6): it launches only the force-only decks (`amr.plot_int = -1`) and reads/writes
only the IB-particle CSV — it neither accepts nor requires any plotfile or velocity/pressure-field
path.

#### Scenario: Full sweep runs against an injected fake executor

- **Given** a fake executor that records each command and writes a synthetic full-length `IB_Particle_1.csv` into the per-config directory
- **When** `run_sweep` is called over a manifest with no cluster, GPU, or container present
- **Then** it completes, the recorded commands match `build_run_command` for each config, and each config's CSV + `run_metadata.json` are written under `<output-root>/<name>/`

#### Scenario: No plotfile or field path is consumed or produced

- **Given** the runner inputs
- **When** `run_sweep` is called
- **Then** it requires only the manifest, the output root, and the executor — it neither accepts nor requires a plotfile/field path — and the constructed commands reference only the force-only deck and the IB-particle CSV (no plotfile output)

### Requirement: Sweep input validation is fail-fast

The runner SHALL validate the sweep before launching any container run, so a malformed corpus
never wastes A40 time or surfaces a bare `KeyError` deep in the loop. `run_sweep` SHALL return one
`RunOutcome` per configuration, SHALL reject a configuration missing the keys it consumes
(`input_file`, `max_step`) with a clear `ValueError` naming the configuration and the missing key
(the published manifest validator does not require these keys), SHALL reject a **non-positive
`max_step`** (which could never satisfy the completion check), SHALL reject duplicate configuration
names (which would collide on the same `<output-root>/<name>/` directory), and SHALL handle an empty
manifest without error. All such validation SHALL occur **before** any run command is issued to the
executor.

#### Scenario: One outcome per configuration

- **Given** a manifest with `N` configurations and a successful executor
- **When** `run_sweep` is called
- **Then** it returns exactly `N` `RunOutcome`s, one per configuration in manifest order

#### Scenario: Configuration missing a consumed key is rejected before any run

- **Given** a manifest configuration lacking `input_file` (or lacking `max_step`)
- **When** `run_sweep` is called
- **Then** it raises `ValueError` naming the configuration and the missing key, and **no** run command is issued to the executor (a bare `KeyError` is never surfaced, because the published `load_manifest_configs` validator does not require `input_file`/`max_step`)

#### Scenario: Non-positive max_step is rejected before any run

- **Given** a manifest configuration with `max_step <= 0`
- **When** `run_sweep` is called
- **Then** it raises `ValueError` naming the configuration before any run command is issued (a non-positive `max_step` can never satisfy `rows >= ceil(max_step · threshold)` and would burn an A40 slot that can never be marked complete)

#### Scenario: Duplicate configuration names are rejected before any run

- **Given** a manifest with two configurations sharing a `name`
- **When** `run_sweep` is called
- **Then** it raises `ValueError` (inherited from `load_manifest_configs`) before any run command is issued — two configs with the same name would otherwise collide on `<output-root>/<name>/`

#### Scenario: Empty manifest yields no outcomes

- **Given** a manifest whose `configs` list is empty
- **When** `run_sweep` is called
- **Then** it returns `[]` without error and issues no run command

### Requirement: Failed runs are isolated and surfaced

The runner SHALL record a configuration whose run does not produce a complete CSV — the executor
returns a nonzero `returncode`, **the executor raises an exception**, or the executor returns zero
but the post-run completion check still reports incomplete (short/empty CSV) — with
`status == "failed"`. It SHALL log every failure (never silent) and SHALL NOT abort the remaining
configurations (so one bad config — including a transient cluster/WSL error that raises — does not
lose the 65-minute corpus; resume retries it on a later run). The post-run completion check SHALL be
authoritative over the executor return code. The thin driver SHALL exit non-zero if any
configuration's outcome is `failed`.

#### Scenario: Nonzero executor return is recorded as failed and the sweep continues

- **Given** a fake executor that returns `ExecResult(returncode=1)` for one configuration and succeeds for the rest
- **When** `run_sweep` is called
- **Then** that configuration's outcome is `status == "failed"`, the failure is logged, every other configuration still runs, and `run_sweep` returns one outcome per configuration

#### Scenario: A run that completes but leaves a short CSV is failed

- **Given** a fake executor that returns `ExecResult(returncode=0)` but writes a header-only (or short) `IB_Particle_1.csv`
- **When** `run_sweep` is called
- **Then** that configuration's outcome is `status == "failed"` — the post-run completion re-check is authoritative, not the return code — and its failure is logged

#### Scenario: An executor that raises is isolated as failed

- **Given** a fake executor that **raises** an exception (e.g. an `OSError`, as the real WSL/`subprocess` executor would on a transient cluster error or missing `wsl`) for one configuration and succeeds for the rest
- **When** `run_sweep` is called
- **Then** that configuration's outcome is `status == "failed"` (the exception is caught, logged, and recorded), every other configuration still runs, and the corpus is not aborted

#### Scenario: Driver exits non-zero when any configuration failed

- **Given** a run in which at least one configuration's outcome is `failed`
- **When** the thin driver `scripts/run_sweep.py` `main()` returns
- **Then** its exit code is non-zero, so an operator's unattended corpus run surfaces the incomplete corpus rather than reporting success

### Requirement: Per-run solver output is captured to a log

Each configuration whose run is launched (i.e. not skipped by resume) SHALL have the executor's
captured stdout and stderr written to a per-run log file `<output-root>/<name>/run.log`, so a
failed or anomalous run on an unattended corpus is diagnosable from the solver's own output rather
than from `status` alone. The log SHALL be written for both completed and failed runs — including a
run whose executor **raised**, whose exception is recorded in the log — and the per-run
`run_metadata.json` SHALL reference the log by its relative path.

#### Scenario: Completed run writes the solver output to run.log

- **Given** a fake executor that returns stdout `"…max.abs.u …"` (and possibly stderr)
- **When** `run_sweep` completes a configuration
- **Then** `<output-root>/<name>/run.log` exists and contains the captured stdout (and stderr), and the run metadata's `log` field is `<name>/run.log`

#### Scenario: A failed run's diagnostics are captured

- **Given** a configuration whose executor fails — a nonzero return carrying stderr (e.g. `"IAMReX error: …"`), or an executor that raises (whose exception is recorded as the run's stderr)
- **When** `run_sweep` is called
- **Then** that configuration's `run.log` contains the failure diagnostics (the stderr text, or the raised exception's representation), so the failure is debuggable without re-running — while the corpus still continues

#### Scenario: A skipped run does not overwrite its log

- **Given** a configuration already complete (resume skips it)
- **When** `run_sweep` is called with `resume=True`
- **Then** no executor runs for it and no new `run.log` is written for it (its prior run artifacts are untouched, parity with its metadata)

### Requirement: Per-run provenance records the compute node's hardware

The per-run provenance SHALL record the hardware that actually ran the CFD — the **compute node
inside the container** (the cluster GPU) — and SHALL NOT present the **driver host** (the machine
that orchestrates the run) as the simulation hardware. Because the runner executes locally and
launches the simulation remotely via the injected executor, the base metadata capture's *local*
hardware probe is misleading. The runner SHALL capture the compute node's GPU via the executor (an
`nvidia-smi` query in the container) and record it under `hardware`. If the probe fails — a nonzero
return or a raised exception — the runner SHALL record an explicit *unavailable* marker rather than
the driver host's hardware, and SHALL NOT abort the sweep. The probe SHALL be **lazy**: it runs only
when a configuration is about to run, so a fully-resumed (already-complete) corpus issues no probe.

#### Scenario: Recorded hardware is the compute node, not the driver host

- **Given** an executor whose in-container `nvidia-smi` probe reports a cluster GPU (e.g. `NVIDIA A40`)
- **When** `run_sweep` completes a configuration
- **Then** that run's `run_metadata.json` `hardware` records the **compute** GPU (its `gpus` list carries the A40's model/memory/driver, and a `source` of `"container"`), and does **not** present the driver host's GPU as the simulation hardware

#### Scenario: A failed hardware probe is recorded honestly, not as the driver host

- **Given** an executor whose `nvidia-smi` probe fails (returns nonzero, or raises)
- **When** `run_sweep` runs a configuration
- **Then** the run's `hardware` records an explicit `"unavailable"` marker naming the workspace, the driver host's GPU is **not** recorded as the compute hardware, and the sweep still completes the configuration (the probe failure is logged, never silent, and never fatal)

#### Scenario: The hardware probe is lazy

- **Given** a corpus in which every configuration already passes the completion check (resume skips all)
- **When** `run_sweep` is called with `resume=True`
- **Then** **no** executor command is issued at all — including no hardware probe — so a fully-complete corpus remains a no-op (the probe is captured only on the first configuration that actually runs)

#### Scenario: The probe command is pure and force-only

- **Given** a workspace name
- **When** `build_probe_command` is called
- **Then** it returns a `runai workspace exec … nvidia-smi --query-gpu=… --format=csv,noheader,nounits` command without performing any I/O, and the command reads only GPU metadata — no plotfile, field, or simulation side effect

### Requirement: Single-configuration pod run

The force-surrogate module SHALL provide a per-configuration run entrypoint suitable for a
container whose **main process is the CFD run itself** (so the orchestrator manages its lifecycle,
with no remote exec stream to drop and no orphaned GPU process). For one sweep configuration it SHALL
stage `wing.vertex` into the run directory, invoke `mpirun` through an **injected runner seam** (so
the logic is unit-tested cluster-free, CC-2), write the run's captured output to `run.log`, verify
completion via the published `check_completion` (29-column header + rows ≥ `ceil(max_step · threshold)`),
and write a per-run `run_metadata.json` via `capture_surrogate_run_metadata` recording the pinned
container **digest**, the deck's manifest-relative path and SHA256, a **caller-supplied** timestamp,
and the orchestrator provenance (workflow uid, pod, node, retry attempt). The entrypoint SHALL signal
**non-zero on an incomplete run** so the orchestrator retries, and the per-run output path SHALL match
PR4's `<output-root>/<name>/IB_Particle_1.csv` driver contract. For this pod transport the hardware
provenance is captured **natively** (the base local probe), **superseding** the PR3 laptop driver's
exec-probe `source: "container"` path (the pod runs *on* the compute GPU, so no probe is needed).

#### Scenario: Completed run writes the checked output and provenance

- **Given** a config and an injected runner that writes a full-length `IB_Particle_1.csv` into the run directory
- **When** `run_config` is called
- **Then** the run's status is `"completed"`, `<output-root>/<name>/IB_Particle_1.csv` passes `check_completion`, `run.log` holds the runner's output, and `<output-root>/<name>/run_metadata.json` records the `sha256:` digest under `docker_image`, the deck SHA256, the timestamp verbatim, the `mpirun` command, and the supplied orchestrator provenance (workflow uid / pod / node / retry)

#### Scenario: Wing geometry is staged into the run directory

- **Given** a config and an injected runner that writes a full-length `IB_Particle_1.csv`
- **When** `run_config` is called
- **Then** the wing geometry (`wing.vertex`) is present in the run directory (`<output-root>/<name>/wing.vertex`) and byte-identical to the source vertex file — the CFD deck resolves its geometry relative to the run directory, so an unstaged geometry would be a silent solver failure rather than a `check_completion` failure

#### Scenario: Incomplete run signals retry

- **Given** an injected runner that returns success but writes a short (or empty) CSV, or returns non-zero
- **When** `run_config` is called and then the `main()` entrypoint returns
- **Then** the run's status is `"failed"`, a `run_metadata.json` is still written (the attempt is auditable, `status = "failed"`), and `main()` returns a **non-zero** exit code so the orchestrator retries the configuration on a fresh pod

#### Scenario: Native compute hardware is recorded (no exec probe)

- **Given** `run_config` running inside the pod that executes the CFD on the GPU
- **When** the run metadata is captured
- **Then** the `hardware` block is the base local capture (`get_hardware_info`: `hostname` present; the override-only keys `source`/`workspace` **absent**), since the pod runs on the compute node itself — it does **not** use an in-container exec probe (which the laptop driver needed) and does not record a different host. This is provable **cluster-free, with no GPU**: the entrypoint does **not** import `capture_compute_hardware`/`build_probe_command` and `run_config` takes no `hardware`/`compute_hardware`/`executor` parameter (asserted structurally via AST + signature), and the output-shape assertion never requires `gpus` to be non-empty (CI has no GPU)

#### Scenario: Mutable tag rejected

- **Given** a mutable image tag (no `sha256:` digest)
- **When** `run_config` writes its provenance
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording an unpinned image

#### Scenario: Malformed configuration fails fast (no wasted A40 retries)

- **Given** a non-positive `max_step` (or an empty `input_file`/`name`) passed to `run_config`, or a missing/non-integer `--max-step` on the `main()` CLI
- **When** `run_config` / `main()` is invoked
- **Then** `run_config` raises a clear `ValueError` naming the configuration and the offending field, and `main()`'s argparse rejects a missing/non-integer flag with a non-zero exit — the published `load_manifest_configs` validator does **not** require `input_file`/`max_step`, so a hopeless config is rejected **once**, not retried five times on the A40

#### Scenario: A raised runner is a clean failure, not a crash

- **Given** an injected `mpi_runner` that **raises** (e.g. the real subprocess hitting a missing binary or a transient `OSError`)
- **When** `run_config` is called
- **Then** it records `status == "failed"` with the exception captured in `run.log`, still writes the `run_metadata.json` (`status="failed"`), and `main()` returns a non-zero exit code — a **clean** pod failure the orchestrator retries, not an uncaught traceback

#### Scenario: Provenance is portable

- **Given** a completed run's `run_metadata.json`
- **When** every nested string is inspected
- **Then** no value is an absolute host mount path (no `^[A-Za-z]:\\` drive-letter path, none starting with `/hpi/`); the deck is identified by its manifest-relative path plus SHA256, and the recorded command uses container (`/workspace/...`) paths

### Requirement: Cluster-side Argo orchestration of the corpus

The repository SHALL provide Argo Workflows artifacts that run the committed 27-config corpus
robustly on the cluster as the production path, **superseding** the laptop `runai exec` driver (which
is retained as a documented local/dev fallback). Each configuration SHALL run as its own pod whose
main process is the CFD run, with a full-GPU request, run-as-root for `mpirun`, and automatic retries;
the workflow SHALL fan out over the configurations declared in `sweep_manifest.json` under a bounded
concurrency, and SHALL gate overall success on every configuration's CSV passing the completion check.

#### Scenario: Each config gets a dedicated GPU, runs as root, and is retried

- **Given** the `force-surrogate-single-config` WorkflowTemplate
- **When** a configuration runs under it
- **Then** each config gets a **dedicated full A40** (the template declares `resources.limits` `nvidia.com/gpu: 1` — no fractional sharing, so IAMReX's ~34 GB never collides), runs **as root** for `mpirun` (`securityContext` `runAsUser: 0`), and a dropped/preempted run is **retried on a fresh pod** (`retryStrategy` with a limit + backoff); it is annotated `runai/preemptible: "true"`, sets `serviceAccountName: default` in namespace `runai-talmo-lab`, and invokes `mosquito_cfd.force_surrogate.run_one_config`. These load-bearing fields are verified **cluster-free** by asserting them in the manifest (each in its correct block — `nvidia.com/gpu: 1` under `limits:`, `runAsUser: 0` under `securityContext`); **`argo lint` is the authoritative structural validator**.

#### Scenario: Workflow fans out over the manifest configs (not a hardcoded list)

- **Given** the `force-surrogate-sweep` Workflow
- **When** a sweep runs
- **Then** its per-config tasks are **derived from `sweep_manifest.json`** (an `extract-configs` step using `load_manifest_configs` feeds a `withParam` fan-out — there is no hardcoded list of the 27 `s*_f*_p*` config names), under a bounded `parallelism` parameter (default 3), with the container image pinned by an `@sha256:` parameter at submit time, the prelim_sweep workspace mounted, and `serviceAccountName: default`

#### Scenario: Concurrency and total runtime are bounded

- **Given** the `force-surrogate-sweep` Workflow
- **When** it is submitted
- **Then** concurrent GPU pods are capped by the workflow's spec-level `parallelism` (default 3 — the limited A40 quota, not an unbounded 27-way burst; a literal, since Argo's `parallelism` is an `int` field that takes no `{{...}}` parameter) and the run is bounded by `activeDeadlineSeconds` (24 h), so a wedged run is killed rather than holding the quota indefinitely; per-pod `retryStrategy` backoff (not the deadline) handles transient failures

#### Scenario: A stale or mismatched image is caught before any GPU pod

- **Given** the workflow's `validate` step, which runs the pinned image **before** the fan-out
- **When** the pinned image does not contain `run_one_config` (a digest pinned before the module shipped), or the recorded `docker-digest` is a mutable tag, or `image != docker-digest` (a half-override that would record a digest the container was not built from), or `sweep_manifest.json`/`wing.vertex` is unmounted, or a config lacks `input_file`/`max_step`
- **Then** `validate` **fails the workflow immediately** — before any GPU pod is scheduled — so the mistake costs seconds, not 27 configs × 5 retries of A40 time (it imports the module, runs `validate_image_digest(docker-digest)`, asserts `image == docker-digest`, and preflights the mounted manifest, geometry, and per-config keys)

#### Scenario: Completion is gated by check_completion, not assumed

- **Given** the workflow's final `verify-complete` step
- **When** the fan-out finishes
- **Then** that step runs **`check_completion`** over **every** configuration's `IB_Particle_1.csv` and **fails the workflow** if any configuration is incomplete — overall success means a complete corpus, not merely that pods exited

#### Scenario: Dataset extraction is not in scope of the workflow

- **Given** the sweep workflow
- **When** its steps are inspected
- **Then** it produces the per-config IB-particle CSV corpus and gates completeness, but contains **no** dataset-build step (no `extract_forces`/`dataset.parquet`) and **no** plotfile/field token (PR4's `extract_forces.py` remains the downstream local step; force-only is preserved — `amr.plot_int = -1`, no plotfile/field reader)

### Requirement: Held-out-configuration train/validation/test split

The force-surrogate trainer SHALL evaluate on **held-out configurations**, not held-out timesteps
within a run (CC-4). The 6 configurations labelled `split == "holdout"` in the dataset (carried
verbatim from `sweep_manifest.json`) SHALL be the **test** set and SHALL NOT be used for training or
model selection. A **configuration-level validation** set SHALL be carved from the 21 training
configurations by a seeded selection for early-stopping / model selection. The three configuration
sets (train, validation, test) SHALL be mutually disjoint, and the assignment SHALL be reproducible
from the seed. (This is the **model-side** split that *consumes* the `split` label; it is distinct
from the sweep-generation requirement *Held-out configuration split is seeded, non-corner, and
label-only*, which *assigns* that label at sweep-generation time.) A dataset missing the `split`
column, with no `holdout` configurations, or whose seeded validation carve would be empty SHALL
raise a clear `ValueError` rather than silently producing an empty test or validation set.

#### Scenario: Holdout configs are exactly the dataset holdout label

- **Given** the committed dataset whose 6 `split == "holdout"` configurations are `s35_f085_p45, s45_f085_p60, s45_f100_p60, s45_f115_p60, s55_f085_p45, s55_f115_p45`
- **When** `make_config_splits` is called
- **Then** the **test** configuration set equals exactly those 6 names, taken from the `split` column (never re-derived), and no holdout configuration appears in the train or validation sets

#### Scenario: Validation is carved at the configuration level from the training configs

- **Given** the 21 `split == "train"` configurations
- **When** `make_config_splits` is called with a fixed seed
- **Then** a non-empty validation set of **whole configurations** is selected from those 21 (every row of a validation configuration is a validation row — no configuration is split across train and validation), the train and validation configuration sets are disjoint and together cover all 21 training configurations, and neither contains any holdout configuration

#### Scenario: Split is seed-reproducible and seed-sensitive

- **Given** the same dataset
- **When** `make_config_splits` is called twice with the same seed, then once with a different seed
- **Then** the two same-seed calls produce identical train/validation/test configuration sets, and the different-seed call leaves the **test** set unchanged (it is always the 6 holdout configs) while it MAY change which training configs are held for validation — proving the holdout set is fixed by the label and only the validation carve is seeded
- **And** the seeded validation carve selects configurations from the **sorted** unique config-name list (`sorted(unique(config_name))`) before sampling, so the selection is reproducible across pandas versions (not dependent on groupby/unique row order)

#### Scenario: Malformed split raises rather than silently emptying a set

- **Given** a dataset that is missing the `split` column, has zero `split == "holdout"` configurations, or is so small that the seeded validation carve would select zero configurations
- **When** `make_config_splits` is called
- **Then** it raises a clear `ValueError` naming the problem (no `split` column / no holdout configs / empty validation carve) rather than returning an empty test or validation set that would silently train on a malformed corpus

### Requirement: Surrogate input and target construction

The trainer SHALL build inputs and targets from the dataset without re-deriving any coefficient math
(CC-3 — it consumes the dataset's already-normalized `CF_*` columns). Inputs SHALL be
`[stroke_amp_deg, frequency_fstar, pitch_amp_deg, sin(2π·phase), cos(2π·phase)]` (cyclic phase
encoding; **Reynolds is excluded** because it is a deterministic function of `(φ, f*)` under the
ν\*-fixed policy and carries no independent information). Targets SHALL be the six coefficients
`CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`. The trainer SHALL filter to the **converged beat**
(`wingbeat ≥ 1`) before training and evaluation. Feature and target standardization statistics SHALL
be fit on **training rows only** (no validation/holdout leakage).

#### Scenario: Feature columns are the kinematics knobs plus cyclic phase

- **Given** a dataset slice
- **When** `build_features` is called
- **Then** the returned feature matrix has exactly five columns named `stroke_amp_deg, frequency_fstar, pitch_amp_deg, phase_sin, phase_cos`, where `phase_sin = sin(2π·phase)` and `phase_cos = cos(2π·phase)`, and **no** `reynolds` column is present

#### Scenario: Cyclic phase encoding is continuous across the wrap

- **Given** two rows with `phase = 0.999` and `phase = 0.001` (adjacent in the cycle)
- **When** their `(phase_sin, phase_cos)` features are computed
- **Then** the two feature pairs are numerically close (Euclidean distance small), whereas their raw `phase` scalars differ by ≈ 0.998 — confirming the encoding removes the 0/1 boundary discontinuity

#### Scenario: Only the converged beat is used

- **Given** the dataset with `wingbeat ∈ {0, 1}`
- **When** `filter_converged_beat` is applied
- **Then** every retained row has `wingbeat ≥ 1`, no `wingbeat == 0` (startup-transient) row remains, and the drop is explicit (the count of retained rows equals the count of `wingbeat == 1` rows) — not a silent mask

#### Scenario: Standardization is fit on training rows only

- **Given** train, validation, and holdout row partitions
- **When** the `Standardizer` is fit
- **Then** the feature/target means and standard deviations are computed from the **training rows only**; recomputing them from the full dataset yields different values (proving no validation/holdout rows entered the fit), and transforming the training features yields per-column mean ≈ 0 and std ≈ 1

#### Scenario: Targets round-trip through standardization

- **Given** the six target columns and a `Standardizer` fit on the training targets
- **When** targets are standardized and then inverse-transformed
- **Then** the inverse-transformed values equal the originals within floating tolerance, so metrics computed after inverse-transform are in physical coefficient units

### Requirement: PhysicsNeMo force-coefficient regressor

The trainer SHALL learn the kinematics(+phase) → six-coefficient map with a **PhysicsNeMo** model
(its fully-connected/MLP architecture) and SHALL NOT ship a second (e.g. plain-PyTorch) model as a
fallback. Model construction and the training loop SHALL be seeded. The model and training functions
SHALL import `torch`/`physicsnemo` lazily so the surrounding module imports without the optional
`train` dependency-group installed.

#### Scenario: Module imports without the training dependency-group

- **Given** an environment where `torch`/`nvidia-physicsnemo` are **not** installed (the CI runner)
- **When** `mosquito_cfd.force_surrogate.train` is imported and its pure helpers (`build_features`, `filter_converged_beat`, `make_config_splits`, `Standardizer`, `compute_metrics`) are called
- **Then** the import succeeds and the helpers run — no `torch`/`physicsnemo` import is triggered until a model/training function is invoked

#### Scenario: Model constructs with the right shape (GPU tier)

- **Given** the optional `train` group installed and a CUDA device available
- **When** `build_model(n_in=5, n_out=6, seed=...)` is called and a batch of 5-feature inputs is passed through it
- **Then** a PhysicsNeMo model is constructed and the forward pass returns a 6-wide output per input row

#### Scenario: Seeded training reduces loss (GPU/torch tier)

- **Given** the model and a small standardized training batch
- **When** `train_model` runs for a handful of seeded steps
- **Then** the final training loss is strictly less than the initial loss (the loop learns) — the CPU-device determinism of this loop is asserted separately under the reproducibility requirement, not here

### Requirement: Held-out evaluation metrics

The trainer SHALL evaluate the trained model on the **holdout configurations** (converged beat) and
emit a `metrics.json` reporting, for each of the six coefficients, the RMSE, MAE, and R²; an
aggregate across targets; a **per-configuration** breakdown over the 6 holdout configs; and an
inference latency/throughput measurement (for the downstream >1,000× inference-vs-CFD speedup
annotation). Metric computation SHALL be pure **numpy** (no scipy/sklearn — they are not project
dependencies and would break the CPU CI tier) and SHALL operate on inverse-transformed
(physical-coefficient) predictions. For a target with (near-)zero variance, R² SHALL be a documented
sentinel (NaN, serialized as `null`) rather than an unhandled `0/0`, and the `aggregate` block SHALL
be NaN-aware (it skips a sentinel R² rather than propagating it, so one constant target does not
poison the aggregate).

#### Scenario: Metrics math is correct on known arrays

- **Given** target and prediction arrays with an analytically known RMSE, MAE, and R²
- **When** `compute_metrics` is called
- **Then** the returned RMSE, MAE, and R² equal the known values within floating tolerance, for each target independently

#### Scenario: Constant-target R² is a defined sentinel, not an unhandled divide-by-zero

- **Given** a target column whose true values have (near-)zero variance — as `CF_y` and the off-axis moments may be by symmetry (design D4)
- **When** `compute_metrics` is called
- **Then** that target's R² is the documented sentinel (NaN, serialized as `null` in `metrics.json`) rather than an unhandled `0/0`, while its RMSE and MAE remain finite — so `metrics.json` serializes without a crash, and the `aggregate` R² skips the sentinel (NaN-aware) so it is not silently NaN-poisoned

#### Scenario: metrics.json carries per-target, aggregate, per-config, and inference keys

- **Given** a completed evaluation on the holdout configs
- **When** `metrics.json` is written and re-read
- **Then** it contains a `per_target` block keyed by `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz` (each with `rmse`, `mae`, `r2`), an `aggregate` block, a `per_config` block keyed by the 6 holdout configuration names, an `inference` block with a `latency_ms` field (single-row forward-pass latency in milliseconds) and a `throughput_rows_per_s` field (batched rows per second) each carrying the timing basis so the downstream >1,000× speedup annotation is auditable, and a `reproducibility` block recording the seeds, the feature list, and the `bitwise` scope key (`"cpu_only"`) — these are CPU-computable, so the CI tier asserts the block's presence even when the model timing is a placeholder

#### Scenario: Evaluation uses only holdout configurations

- **Given** the split assignment
- **When** the holdout metrics are computed
- **Then** every row scored is from a `split == "holdout"` configuration on the converged beat, and no training or validation row contributes to the reported holdout metrics (CC-4)

### Requirement: Config-resolved (phase-honest) evaluation metrics

The surrogate evaluation SHALL additionally report **config-resolved** metrics in `metrics.json`,
because the pointwise aggregate R² is dominated by the within-beat force **waveform** — a smooth
periodic shape shared across all configurations and therefore largely "free" to learn — and on its
own **overstates** the surrogate's skill at the kinematics→force *map* (the genuinely held-out
config-to-config dependence) (CC-4 scientific honesty). The evaluation SHALL carry, per target, a
`config_resolved` block reporting (a) `config_mean_r2` — the R² computed on the per-configuration
**cycle-mean** coefficient (the phase-removed config-to-config skill, the physically-central
cycle-averaged force) — and (b) `within_config_variance_fraction` — the fraction of total holdout
variance that is within-configuration (the waveform), which exposes how much of the aggregate R² is
waveform-driven. These SHALL be pure-numpy, computed on the inverse-transformed predictions grouped
by `config_name`, and reported **alongside** (never instead of) the aggregate.

#### Scenario: config_resolved block is present per target

- **Given** a completed holdout evaluation
- **When** `metrics.json` is written and re-read
- **Then** it contains a `config_resolved` block keyed by `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`, each carrying a `config_mean_r2` and a `within_config_variance_fraction` — distinct from, and reported in addition to, the pointwise `per_target`/`aggregate` blocks

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

### Requirement: Training reproducibility and provenance

The training run SHALL be seeded (python/numpy/torch) with `torch.use_deterministic_algorithms`
enabled, and SHALL emit a `run_metadata.json` via `capture_surrogate_run_metadata` requiring a pinned
container **digest** and a **caller-supplied** timestamp (CC-1). The metadata SHALL record the seeds,
and — on the training host where the `train` group is installed — the resolved `torch`/`physicsnemo`
versions. Bitwise reproducibility SHALL be claimed only for the CPU path; the GPU run SHALL be
documented as seeded-but-not-bitwise. `wandb` logging SHALL default to **disabled** (a no-op,
without importing `wandb`) and SHALL be opt-in to online; an online wandb failure SHALL NOT block or
truncate the committed `metrics.json`.

#### Scenario: Provenance records digest, timestamp, and seeds (CI tier, no train group)

- **Given** a container image digest containing `sha256:`, a caller-supplied ISO-8601 timestamp, and the run seeds
- **When** the training provenance is captured **without** the `train` group installed
- **Then** the metadata records the git commit, the supplied digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, and the seeds (the `torch`/`physicsnemo` version fields are absent/`null`, not asserted on this tier)

#### Scenario: Resolved library versions recorded on the training host (torch tier)

- **Given** the `train` group installed (the A5000/WSL2 training host)
- **When** the training provenance is captured
- **Then** it additionally records the resolved `torch` and `physicsnemo` version strings, so the GPU run's environment is auditable from metadata even though it is not bitwise-reproducible

#### Scenario: Mutable image tag rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** the training provenance is captured
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording provenance without a pinned image

#### Scenario: Torch-free CPU helpers are bitwise-reproducible (CI tier)

- **Given** the torch-free CPU code paths only (feature build, standardization, config split, metrics) — no `torch` import
- **When** they are run twice with the same seed
- **Then** their outputs are bitwise-identical — this is the CI-gating determinism check, runnable without the `train` group

#### Scenario: Seeded training step is deterministic on the CPU torch device (torch tier)

- **Given** the `train` group installed and the model placed on the CPU torch device
- **When** a seeded `train_model` step is run twice with the same seed
- **Then** the two loss trajectories are identical, and `metrics.json` records `reproducibility.bitwise == "cpu_only"` to scope the claim honestly (the CUDA/GPU run is seeded but not asserted bitwise — cuDNN/TF32 nondeterminism)

#### Scenario: wandb is disabled by default without importing wandb

- **Given** the trainer invoked in the default `disabled` mode (the CI/rerun default) with the `wandb` import barred
- **When** training runs
- **Then** the wandb-gating path is a no-op that does **not** import `wandb` (no `ImportError` on a host without it), and the run completes and writes `metrics.json` with no wandb network call

#### Scenario: wandb online failure does not block metrics.json

- **Given** `--wandb online` selected but no reachable/authenticated wandb backend
- **When** training runs
- **Then** `metrics.json` is still written in full from local state (no missing or partial fields) — the committed artifact never depends on the wandb call succeeding

### Requirement: Committed training artifacts

The training run SHALL produce four artifacts under `examples/prelim_sweep/`: a `metrics.json`, a
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

### Requirement: Two-tier cluster-free and GPU-gated tests

The trainer SHALL be tested in two tiers. The **CPU tier** SHALL be cluster-free (CC-2) — no RunAI,
no GPU, no plotfiles, no `train` dependency-group — and SHALL gate CI, covering feature/target
construction, the converged-beat filter, the configuration split, standardization-leakage,
metric math, the artifact schemas, and the provenance digest guard. The **GPU tier** SHALL be marked
with a registered `gpu` pytest marker that **auto-skips** when CUDA is unavailable or `physicsnemo`
is not importable, and CI SHALL additionally deselect it (`-m "not gpu"`), so no GPU-bound test can
block CI.

#### Scenario: GPU tests skip on a CPU-only host

- **Given** a host with no CUDA device or without `physicsnemo` installed (the CI runner)
- **When** the test suite runs
- **Then** every `@pytest.mark.gpu` test is skipped (not failed, not errored), and the CPU-tier tests run and pass

#### Scenario: CI deselects the GPU marker explicitly

- **Given** the CI pytest invocation
- **When** it is configured
- **Then** it passes `-m "not gpu"` so GPU tests are deselected regardless of the runner's hardware, and the `gpu` marker is registered in `[tool.pytest.ini_options]` (no unknown-marker warning)

### Requirement: Force-only training scope guard

The trainer SHALL consume **only** the tidy `dataset.parquet` (kinematics + phase + coefficients) and
SHALL NOT read AMReX plotfiles or velocity/pressure fields, build a DoMINO/latent-dynamics encoder,
or integrate any RL loop (CC-6). It is the instantaneous kinematics(+phase) → force-coefficient
regressor only.

#### Scenario: Training consumes only the dataset parquet

- **Given** the training inputs
- **When** the trainer runs
- **Then** it requires only `examples/prelim_sweep/dataset.parquet` (and its units sidecar) — it neither accepts nor requires a plotfile/field path — and it produces force-coefficient predictions only, with no field reconstruction, no latent-dynamics state, and no RL interaction

