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

