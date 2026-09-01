# force-surrogate Specification

## Purpose
TBD - created by archiving change add-force-surrogate-foundation. Update Purpose after archive.
## Requirements
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
blank lines, ordering, and unrelated keys. `amr.plot_int` SHALL default to **-1** (force-only: no
field plotfiles) but SHALL be overridable via an explicit caller-supplied parameter, for corpora
that intentionally enable field-capture output. `ns.init_iter` SHALL be an additional, optional
targeted key: when the caller does not supply a value, it is left untouched (pass-through from the
base deck, matching every other non-targeted key's behavior) — it is never rewritten by default,
distinct from `amr.plot_int`'s "rewritten to a default" behavior. Neither `amr.plot_int` nor
`ns.init_iter` overrides are bounds-validated by this requirement (e.g. `0` or a negative value
other than `-1` are accepted and written verbatim) — validating the physical sense of a supplied
value is out of scope; a targeted key absent from the base SHALL raise rather than be silently
skipped, generated files SHALL use **LF (`\n`) line endings** regardless of host platform, and
numeric values SHALL be written with a **deterministic, platform-independent formatter** so the
corpus is byte-reproducible.

#### Scenario: Generated file differs from base only in the swept and derived keys

- **Given** a generated input file (no field-capture override) and the base `inputs.3d.validation`
- **When** both are parsed into key→value maps
- **Then** the keys whose values differ are exactly `{particle_inputs.kinematics_stroke_amp, particle_inputs.kinematics_frequency, particle_inputs.kinematics_pitch_amp, max_step, stop_time, amr.plot_int}`
- **And** all other keys (e.g. `geometry_type`, `geometry_file`, `hinge_*`, `ns.vel_visc_coef`, `ns.init_iter`, projection tolerances) are unchanged
- **And** `particle_inputs.kinematics_deviation_amp` (a prefix-sibling of the swept stroke/pitch keys, present in the base) is byte-unchanged — the rewrite matches full keys, not the `kinematics_` prefix

#### Scenario: Plot output disabled by default

- **Given** the default 27-config sweep is generated with no field-capture override
- **When** each generated input file is parsed
- **Then** every file has `amr.plot_int = -1`

#### Scenario: Plot output enabled via an explicit override, independent of `init_iter`

- **Given** the sweep is generated with an explicit `plot_int` override (e.g. `100`) and `init_iter`
  left at its default (omitted)
- **When** each generated input file is parsed
- **Then** every file has `amr.plot_int` equal to the supplied override value, and `ns.init_iter` is
  unchanged from the base — overriding one parameter does not implicitly affect the other

#### Scenario: `init_iter` enabled via an explicit override, independent of `plot_int`

- **Given** the sweep is generated with an explicit `init_iter` override (e.g. `2`) and `plot_int`
  left at its default (omitted)
- **When** each generated input file is parsed
- **Then** every file has `ns.init_iter` equal to the supplied override value, and `amr.plot_int`
  is unchanged from its own default (`-1`) — overriding one parameter does not implicitly affect
  the other

#### Scenario: Omitting the field-capture override preserves today's exact behavior

- **Given** the sweep is generated with `plot_int`/`init_iter` both omitted (or explicitly `None`
  for `init_iter`)
- **When** the output is compared against a generation from before this change existed
- **Then** the output is byte-identical — this change is purely additive for every caller that
  doesn't opt in, including the coarse corpus's own generation

#### Scenario: Missing target key is rejected

- **Given** a base inputs text that lacks one of the targeted keys (e.g. `amr.plot_int`, or
  `ns.init_iter` when an `init_iter` override is actually supplied)
- **When** `render_inputs` is called
- **Then** it raises `ValueError` naming the missing key rather than producing a file without the
  requested value

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
kinematic parameters, `nu_star`, `reynolds`, derived `max_step`/`stop_time`, `plot_int`, an optional
`init_iter` field, the train/holdout `split`, and the input-file path; plus top-level grid levels,
the resolved Reynolds policy, and the holdout seed. `init_iter` SHALL be present with the caller's
supplied value when a field-capture `init_iter` override was requested, and SHALL be omitted
entirely (not recorded as `null`) when the caller left it at its default pass-through — mirroring
`ns.init_iter`'s own pass-through-by-default behavior in the generated deck. It SHALL emit a
`sweep_manifest.units.json` via the PR1 `write_units_sidecar` helper declaring the unit of each
measured column. It SHALL emit a separate `sweep_provenance.json` carrying environmental
provenance — git commit, base-inputs SHA256, and a **caller-supplied** timestamp, and **no** Docker
image digest (PR2 runs no container). When the caller requests a field-capture override (a
non-default `plot_int` and/or `init_iter`), `sweep_provenance.json` SHALL additionally carry a
top-level `field_capture` block recording the resolved policy (`plot_int`, a one-line rationale, a
pointer to CC-F1/CC-F3, and `init_iter` when it was itself overridden — omitted, not recorded as
`null`, when only `plot_int` was overridden, mirroring the manifest's own omit-not-null convention
for `init_iter` rather than introducing a second, differently-encoded "not requested" representation);
when no override is requested at all, no `field_capture` block is present. Provenance is kept out
of the manifest so the manifest stays byte-reproducible: the
`git_commit` is inherently non-reproducible across checkouts, so it must not contaminate the
byte-identity guarantee. Regenerating the sweep with the recorded seed and timestamp SHALL produce
byte-identical input files and a byte-identical manifest + units sidecar, for either the force-only
default or an explicit field-capture override.

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

#### Scenario: Field-capture override is recorded in the manifest and provenance, force-only omits both

- **Given** a sweep generated with an explicit `init_iter` override
- **When** `sweep_manifest.json` is read
- **Then** every config's record includes `"init_iter"` set to the supplied value
- **And** `sweep_provenance.json` includes a top-level `field_capture` block recording `plot_int`/`init_iter` and a rationale pointer to CC-F1/CC-F3

#### Scenario: Default (force-only) generation omits the field-capture fields entirely

- **Given** a sweep generated with `plot_int`/`init_iter` both left at their defaults
- **When** `sweep_manifest.json` and `sweep_provenance.json` are read
- **Then** no config record has an `"init_iter"` key at all (not `null`), and `sweep_provenance.json` has no `field_capture` block — this change is purely additive for every caller that doesn't opt in

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
cluster client (those live only in the thin driver's real executor). This runner (the local/dev
`runai exec` fallback path, `examples/prelim_sweep/sweep_manifest.json`-scoped) SHALL operate
**force-only** (CC-6): it launches only the force-only decks (`amr.plot_int = -1`) and reads/writes
only the IB-particle CSV — it neither accepts nor requires any plotfile or velocity/pressure-field
path. This scope is specific to this runner module and the coarse corpus it is documented against;
it does not constrain what deck content the separate cluster-side Argo orchestration (a different
requirement, below) submits for a different corpus.

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
The workflow itself SHALL be agnostic to whatever `amr.plot_int`/`ns.init_iter` values the configs'
decks actually contain — it neither inspects nor constrains those values, since its own steps
(`validate`, the fan-out, `verify-complete`) only ever read/write the IB-particle CSV, regardless
of whether the submitted corpus is force-only or field-capture-enabled.

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
- **Then** it produces the per-config IB-particle CSV corpus and gates completeness, but contains **no** dataset-build step (no `extract_forces`/`dataset.parquet`) and **no** plotfile/field-reading step (PR4's `extract_forces.py` remains the downstream local step, and never reads plotfiles regardless of whether the submitted corpus is force-only or field-capture-enabled)

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

### Requirement: Committed evidence-figure artifacts with provenance

The figure generator SHALL produce three artifacts under `examples/prelim_sweep/figures/`: the
`evidence_figure.png`, an `evidence_figure_metrics.json` carrying the per-axis surrogate RMSE, the
quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), the configuration-resolved
R² the figure annotates, and the speedup-derivation inputs (the batched throughput, the per-config
rows-per-wingbeat, the coarse CFD per-wingbeat cost, the single-row latency, and both realized factors
with their units); and a
`run_metadata.json` emitted via `capture_surrogate_run_metadata` requiring a pinned container
**digest** and a **caller-supplied** timestamp (CC-1), recording the hash of the consumed inputs (the
predictions parquet and metrics.json). The JSON sidecars SHALL be written **LF-newline UTF-8** (as
`write_units_sidecar` does) so the committed artifacts do not churn between Windows authoring and
Linux CI.

#### Scenario: All three artifacts write and re-load with the documented content

- **Given** a figure-generation run into a temporary output directory
- **When** the run completes
- **Then** `evidence_figure.png`, `evidence_figure_metrics.json`, and `run_metadata.json` all exist and re-load, and `evidence_figure_metrics.json` carries the per-axis surrogate RMSE, the quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), the annotated config-resolved R², and the speedup inputs — equal to what the figure displays

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
tiny metrics dict, and SHALL assert the quasi-steady-reference formula on known arrays, the
config-name parsing, the CC-3 helper as the single normalization source, the per-panel annotation
values, the figure structure (three scatter axes; a shared config→color legend; **no** baseline
series on any axis; caption/annotation text present) via the Matplotlib object model (not pixels),
the artifact schemas, and the provenance digest guard.

#### Scenario: Tests run without cluster, GPU, or plotfiles

- **Given** a host with no RunAI access, no GPU, and no plotfiles
- **When** the evidence-figure test suite runs
- **Then** every test executes and passes using only the tiny synthetic parquet/metrics fixtures, with no RunAI call, no CUDA requirement, and no plotfile read

#### Scenario: Figure structure is asserted via the Matplotlib object model

- **Given** a generated figure object
- **When** its structure is inspected
- **Then** the test asserts three scatter axes, a shared config→color legend (one entry per held-out config) with **no** Sane–Dickinson/baseline series on any axis, and the presence of the caption and per-panel annotation text — without comparing rendered pixels

### Requirement: Force-only evidence-figure scope guard

The figure generator SHALL consume **only** the committed `holdout_predictions.parquet` and
`metrics.json` (plus the validated geometry module constants) and SHALL NOT read AMReX
plotfiles/velocity/pressure fields, build a DoMINO/latent-dynamics encoder, or integrate any RL loop
(CC-6).

#### Scenario: Generator requires only the committed surrogate artifacts

- **Given** the figure-generation inputs
- **When** the generator runs
- **Then** it requires only the predictions parquet and metrics.json (and module geometry constants) — it neither accepts nor requires a plotfile/field path — and it produces only the figure and its sidecar artifacts, with no field reconstruction, latent state, or RL interaction

### Requirement: Re-normalization preserves surrogate skill (scale-invariance)

Re-deriving force/moment coefficients under a different per-configuration convention SHALL rescale
the CFD targets and the surrogate predictions by the **same** constant, leaving the held-out **R²**
and the predicted-vs-CFD relationship invariant. The frozen corpus's raw force/moment columns and
IB-particle CSVs SHALL NOT be regenerated for a re-normalization convention change; only derived
coefficients change, and no surrogate retraining SHALL be required for that case. This
frozen-corpus guarantee has exactly **one** documented exception: `fix-force-surrogate-sweep-hinge`
regenerated the raw corpus once to correct a wing-hinge geometry defect present in every
configuration since the corpus was first generated (the hinge was frozen from a pre-refactor deck
against a geometry file that had since moved to a new axis convention). That regeneration is not a
precedent for routine re-runs — any future raw-corpus regeneration requires its own equally
explicit, equally documented exception.

#### Scenario: R² is invariant under re-normalization

- **Given** the committed `examples/prelim_sweep/surrogate/holdout_predictions.parquet` (`CF_x_true/pred`, `CF_z_true/pred`, …) whose `R²` matches `metrics.json`
- **When** both the `*_true` and `*_pred` columns are multiplied by the convention factor `k = f_ref_old / f_ref_new` (≈ 3.119)
- **Then** the recomputed per-target `R²` for `CF_x` and `CF_z` each equals the original within `1e-9`, confirming no retrain is needed
- **And** the `RMSE`/`MAE` rescale by exactly `k` (reported honestly), while the scatter shape is unchanged (axes relabeled)

#### Scenario: Raw corpus stays frozen under re-normalization; only derived coefficients move

- **Given** a re-normalization convention change (not a geometry-defect fix) re-derives the corpus coefficients
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

### Requirement: Fine-grid pilot base deck is deck-invariant except grid resolution

`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` SHALL be an exact copy of the frozen
`examples/prelim_sweep/base_inputs.3d.validation` (the sweep's coarse base deck), changing
**only** `amr.n_cell` (`64 32 64` → `256 128 256`). `ns.fixed_dt`, `particle_inputs.radius`,
and every other key SHALL be identical, so the coarse↔fine difference is isolated to spatial
refinement (the fallback to `ns.fixed_dt = 2.5e-4`, if a config's run diverges, happens as a
per-config runtime override — not a change baked into this shared base deck).

#### Scenario: Fine base deck matches the frozen coarse base deck except n_cell

- **Given** `examples/prelim_sweep/base_inputs.3d.validation` (the frozen coarse base) and
  `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`
- **When** both decks are parsed into `{key: value}` maps (comments stripped, whitespace
  normalized)
- **Then** the symmetric difference of keys is empty, and the only differing value is
  `amr.n_cell` (`"64 32 64"` in the coarse base, `"256 128 256"` in the fine base)

### Requirement: Fine-grid pilot decks are reproducibly generated via the unmodified sweep generator

The 3 pilot decks SHALL be produced by calling the existing, unmodified
`mosquito_cfd.force_surrogate.sweep.generate_sweep()` against the fine base deck and a
pilot-specific output directory — no changes to `sweep.py` itself, and no hand-edited decks.

#### Scenario: Pilot decks are byte-reproducible from the fine base deck and the 3 pilot configs

- **Given** `base_inputs.3d.fine`, the 3 pilot configs (`s55_f115_p45`, `s45_f100_p45`,
  `s35_f085_p45`, each with `pitch_amp_deg=45`), `n_wingbeats=2`, and `dt=5e-4`
- **When** `generate_sweep()` is called twice with identical arguments (aside from the
  caller-supplied timestamp)
- **Then** the two runs produce byte-identical `inputs/inputs.3d.<name>` deck files and an
  identical `sweep_manifest.json` (mirroring the existing byte-reproducibility guarantee
  already proven for the coarse 27-config corpus)

#### Scenario: Pilot max_step matches the existing run-duration formula

- **Given** the 3 pilot configs' `frequency_fstar` values (1.15, 1.00, 0.85), `n_wingbeats=2`,
  and `dt=5e-4`
- **When** `derive_run_duration` computes each config's `max_step`
- **Then** the values are exactly 3478, 4000, and 4706 respectively (`round(n_wingbeats / f* /
  dt)`, the existing, unmodified formula)

### Requirement: Fine-grid pilot artifacts are isolated from the frozen coarse corpus

Nothing generated or submitted for this pilot SHALL write into, modify, or otherwise touch
`examples/prelim_sweep/` (the frozen, byte-identical 27-config coarse corpus) — the same
frozen-artifact guarantee already established elsewhere in this spec for the corpus's raw force
columns (see "Re-normalization preserves surrogate skill (scale-invariance)"), extended here to
a sibling pilot process rather than a re-normalization trigger. All pilot artifacts (base deck,
generated decks, manifests, force CSVs, run metadata, report) SHALL live under a separate
`examples/prelim_sweep_fine_pilot/` directory, and cluster submission SHALL target a
pilot-specific `WORKSPACE_HOSTPATH`, never the coarse corpus's path.

#### Scenario: Pilot output directory and workspace path are statically distinct from the coarse corpus's

- **Given** the pilot generation script's output-directory constant and the pilot's configured
  `WORKSPACE_HOSTPATH`
- **When** each is compared against `examples/prelim_sweep/` and the coarse corpus's own NFS
  hostpath, respectively — as a static check, not one that requires actually running generation
  or submitting a workflow
- **Then** both are confirmed distinct strings/paths before any generation or submission happens

#### Scenario: Coarse corpus is unperturbed by the pilot

- **Given** the frozen `examples/prelim_sweep/` directory's committed contents (decks,
  `sweep_manifest.json`, `dataset.parquet`, `run_metadata.json`) before the pilot is run
- **When** the fine-grid pilot is generated and submitted
- **Then** every file under `examples/prelim_sweep/` is byte-identical to its pre-pilot state
  (checked via `sha256`, mirroring the existing frozen-corpus reproducibility tests) — this is a
  passive, one-time confirmation of the static guarantee above, not a repeatable automated test
  that re-executes generation against the real corpus path on every run

### Requirement: Fine-grid pilot per-config run metadata is committed with provenance

Each attempted pilot config's provenance SHALL be committed once its cluster run completes (or
is abandoned as unstable): `run_metadata_<config-name>.json` with the same schema as
`run_metadata_t3c.json` (git/docker/hardware/timing), committed incrementally per config as it
finishes rather than held until all 3 configs are done.

#### Scenario: Per-config run metadata is committed once its run completes (Session B)

- **Given** a pilot config's cluster run has completed (stable, with or without the fallback)
- **When** `examples/prelim_sweep_fine_pilot/run_metadata_<config-name>.json` is read
- **Then** it has the same required fields as `run_metadata_t3c.json` (`git`, `docker_image`,
  `image_digest`, `timing.wall_time_s`, `timing.timesteps`, `timing.s_per_step`, `fixed_dt`,
  `dt_reduced`) — this scenario is checked (and skipped if not yet true) **per config
  independently**, matching the `add-wing-fine-grid-convergence` Session A/Session B pattern, so
  a partially-complete pilot (e.g. 1 of 3 configs done) still reports 1 pass + 2 skips rather
  than one all-or-nothing result

### Requirement: Fine-grid pilot report documents per-config stability and a cost/go-no-go verdict

A pilot report SHALL document, per attempted config, whether it was stable at `dt=5e-4`, needed
the `2.5e-4` fallback, or was unstable even with the fallback — plus a real (measured, not
merely estimated) cost projection for the full 27-config regeneration and an explicit go/no-go
recommendation. An unstable-even-with-fallback config SHALL be recorded as a genuine finding,
not silently omitted or retried indefinitely, and any partial force-CSV/log artifacts from an
aborted run SHALL be committed as evidence alongside that finding rather than discarded.

#### Scenario: Pilot report is present and covers all attempted configs

- **Given** the pilot has been run (fully or partially, including a config that never
  completes or is found unstable)
- **When** the pilot report is read
- **Then** it lists a stability outcome (`stable_at_5e-4` / `stable_at_2.5e-4_fallback` /
  `unstable`) and a measured wall-time / `s_per_step` for every config that was attempted, and
  a full 27-config cost projection derived from those measurements

### Requirement: Full fine-grid corpus decks reuse the unmodified sweep generator with default grid and holdout

The 27 full-corpus decks SHALL be produced by calling the existing, unmodified
`mosquito_cfd.force_surrogate.sweep.generate_sweep()` against the pilot's already-committed fine
base deck (`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`) with **no** `configs=` or
`n_holdout=` override — `configs` SHALL default to `build_kinematic_grid()`'s full 27-point
Aedes grid and `n_holdout` SHALL default to `N_HOLDOUT` (6), unlike the pilot's forced
`n_holdout=0` (which was required only because 3 configs cannot support a 6-config holdout). No
new base deck and no changes to `sweep.py` itself.

#### Scenario: Full corpus generation uses the default 27-config grid and a non-degenerate holdout

- **Given** the fine base deck and no `configs=`/`n_holdout=` arguments supplied
- **When** `generate_sweep()` runs
- **Then** the resulting `sweep_manifest.json` has exactly 27 configs matching
  `build_kinematic_grid()`'s own `stroke_amp_deg`/`frequency_fstar`/`pitch_amp_deg` axes, and
  `manifest["holdout"]["n_holdout"] == 6` with a non-empty `config_names` list

#### Scenario: Full corpus decks are byte-reproducible

- **Given** the fine base deck and the default 27-config grid
- **When** `generate_sweep()` is called twice with identical arguments (aside from the
  caller-supplied timestamp)
- **Then** the two runs produce byte-identical `inputs/inputs.3d.<name>` deck files and an
  identical `sweep_manifest.json`

### Requirement: Full fine-grid corpus artifacts are isolated from the frozen coarse corpus and the pilot

Nothing generated for the full corpus SHALL write into, modify, or otherwise touch
`examples/prelim_sweep/` (the frozen coarse corpus) or `examples/prelim_sweep_fine_pilot/` (the
already-committed pilot). All full-corpus artifacts (generated decks, manifests, and — once the
future cluster run completes — force CSVs and run metadata) SHALL live under a separate
`examples/prelim_sweep_fine/` directory, and cluster submission SHALL target a full-corpus-
specific `WORKSPACE_HOSTPATH`, distinct from both the coarse corpus's and the pilot's.

#### Scenario: Full corpus output directory and workspace path are statically distinct from both the coarse corpus's and the pilot's

- **Given** the full-corpus generation script's output-directory constant and its configured
  `WORKSPACE_HOSTPATH`
- **When** each is compared against `examples/prelim_sweep/` and
  `examples/prelim_sweep_fine_pilot/` and their respective NFS hostpaths — as a static check, not
  one that requires actually running generation
- **Then** all four comparisons are confirmed distinct strings/paths before any generation happens

#### Scenario: The output directory guard rejects both frozen paths

- **Given** the full-corpus generation script's `_validate_output_dir` guard
- **When** it is called with `examples/prelim_sweep/` or `examples/prelim_sweep_fine_pilot/` as
  the requested `--output`
- **Then** it raises `ValueError` for both, and does not raise for the script's own real
  `OUTPUT_DIR`

#### Scenario: The CLI rejects a frozen-path `--output` without generating anything

- **Given** the full-corpus script's `main()` invoked with `--output` pointed at a decoy standing
  in for a frozen path (via a monkeypatched constant, never the real coarse-corpus or pilot
  directory)
- **When** `main()` runs
- **Then** it raises `SystemExit` before calling `generate_sweep()` — the guard's `ValueError` is
  converted to a `parser.error()` at the CLI boundary, exactly as the pilot's own
  `generate_pilot.py` does

### Requirement: Argo sweep-submission parallelism is overridable without mutating the committed workflow

`cluster/argo/scripts/submit_workflow.sh`'s `full` command SHALL accept an optional `--parallelism`
flag that overrides the submitted workflow's concurrency without editing the checked-in workflow
file — since Argo's `spec.parallelism` is a hardcoded `int` field with no `{{...}}`
parameter-templating support (see this capability's base spec, "Concurrency and total runtime are
bounded," which this requirement is additive to, not a replacement for) and `argo submit` provides
no CLI override for it. When the flag is supplied, the script SHALL apply the override by submitting an anchored,
self-verifying `sed`-patched temporary copy of the workflow file, leaving the committed file
unchanged on disk. When the flag is **omitted**, the script SHALL submit the committed workflow
file unpatched — there is no separate hardcoded default that could drift from the committed
file's actual value. This requirement is a sibling of, and independent of, "Argo sweep-submission
provisions the NFS workspace before submitting" (below) — the two flags compose freely and neither
implies the other.

#### Scenario: `--parallelism` overrides concurrency without touching the committed file

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1`
- **When** the command runs
- **Then** the sed-patched temporary copy of the workflow that would be passed to `argo submit`
  has `parallelism: 1`, and `cluster/argo/workflows/force-surrogate-sweep.yaml` on disk is
  byte-identical (same `sha256`) before and after the command runs — this is verified cluster-free
  (a stub `argo` executable capturing what it was invoked with), not against a live cluster

#### Scenario: Omitting `--parallelism` is a true no-op, not a re-patch with a hardcoded default

- **Given** `cluster/argo/scripts/submit_workflow.sh full` invoked with no `--parallelism` flag
- **When** the command runs
- **Then** the committed `force-surrogate-sweep.yaml` is passed to `argo submit` **unpatched** —
  no temporary file is created at all — so its `parallelism: 3` is whatever the committed file
  actually says, not a second, independently-hardcoded "3" in the shell script that could silently
  diverge if the committed value is ever changed

#### Scenario: An invalid `--parallelism` value is rejected before any file is touched

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (or a negative or
  non-integer value, e.g. `-1` or `abc`)
- **When** the command runs
- **Then** it fails fast with a clear error before creating any temporary file or invoking `argo
  submit`, and the committed workflow file is untouched

#### Scenario: A failed substitution is never silently submitted

- **Given** the workflow file's top-level `parallelism: <N>` line is missing or does not match
  the expected anchored pattern (e.g. the line was reformatted)
- **When** `--parallelism` is supplied
- **Then** the script fails with a clear error rather than submitting an unpatched temporary copy
  that would silently run at the wrong concurrency

#### Scenario: `--parallelism` and provisioning compose without interfering with each other

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (an invalid value) with a valid, current corpus-dir/workspace-hostpath pair
- **When** the command runs
- **Then** it still fails fast on the invalid `--parallelism` value before invoking the stub `argo`, and provisioning's copy step (if it already ran) has no bearing on that rejection — an invalid `--parallelism` is not masked or bypassed by provisioning having succeeded first

### Requirement: Sweep base deck hinge is geometrically consistent with the wing geometry

Every hand-authored sweep base deck SHALL place `particle_inputs.hinge_{x,y,z}` at the wing's own
**root** along the geometry's actual span axis — this applies to
`examples/prelim_sweep/base_inputs.3d.validation` and
`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` — derived from the referenced
`particle_inputs.geometry_file` marker extent — **not** merely matched by byte-identity to another
committed file. Along the span axis, the hinge-to-centre arm SHALL equal the geometry's own
half-span (from its marker extent) within a documented tolerance; along the two non-span axes, the
hinge SHALL exactly equal the wing centre (`particle_inputs.{x,y,z}`) — no spurious offset. This
guard is independent of, and in addition to, any byte-identity/deck-invariance guard elsewhere in
this spec, precisely because byte-identity alone cannot detect a value that is self-consistently
wrong.

#### Scenario: Coarse and fine base decks place the hinge at the span root

- **Given** `examples/prelim_sweep/base_inputs.3d.validation`, `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`, and the committed `examples/flapping_wing/wing.vertex`
- **When** each deck's hinge is checked against the vertex file's marker extent along the span axis (y)
- **Then** each deck's `hinge_y` arm from `particle_inputs.y` equals the vertex file's own half-span within tolerance, and `hinge_x`/`hinge_z` exactly equal `particle_inputs.x`/`particle_inputs.z`

#### Scenario: The live validation deck already satisfies the guard (calibration baseline)

- **Given** `examples/flapping_wing/inputs.3d.validation` (never affected by the bug this guard targets)
- **When** the same geometric-consistency check is applied to it
- **Then** it passes, confirming the guard's tolerance is calibrated against a known-correct deck and not merely tuned to accept the corrected sweep decks

#### Scenario: A midspan-pivot hinge is rejected

- **Given** a synthetic deck whose hinge equals the wing centre along the span axis (zero arm — the pre-fix defect's exact shape)
- **When** the geometric-consistency check is applied
- **Then** it raises / reports failure, naming the expected vs actual span arm

#### Scenario: A spurious non-span-axis offset is rejected

- **Given** a synthetic deck whose span-axis hinge arm correctly equals the geometry's half-span, but whose non-span-axis hinge coordinate (e.g. `hinge_z` when the span axis is y) differs from the wing centre (`particle_inputs.z`) by a nonzero offset — the second, independently wrong half of the original defect's exact shape (`hinge_z = 2.5` against a wing centre `z = 4.0`)
- **When** the geometric-consistency check is applied
- **Then** it raises / reports failure, naming the offending non-span axis and the expected-vs-actual coordinate — a deck can fail this scenario while passing the span-arm scenario above, and both checks are required independently

### Requirement: Cluster-free wing-phase geometric diagnostic

The force-surrogate module SHALL provide a reusable, parameterized function that renders a sweep
configuration's wing-marker positions at four phases of one wingbeat (t = 0, T/4, T/2, 3T/4) in the
stroke plane, computed from the configuration's kinematics, hinge, and `wing.vertex` alone — no CFD
run, plotfile, or force CSV required. It SHALL use the canonical
`mosquito_cfd.benchmarks.wing_kinematics` rotation functions (not a re-derived rotation), and SHALL
emit the same three-artifact provenance convention as the evidence figure: `<name>.png`,
`<name>_metrics.json` (the numeric span-arm/hinge values the figure displays, matching the
geometric-consistency guard's own computation), and a `run_metadata.json` via
`capture_surrogate_run_metadata`. A thin CLI driver SHALL default to a documented representative
sample of configurations (not all 54, since the kinematics amplitude/frequency doesn't affect
hinge correctness) with an explicit `--config all` override, and the sampling choice SHALL be
documented in the figures README (no silent caps).

#### Scenario: Diagnostic figure matches the geometric-consistency guard's own numbers

- **Given** a sweep configuration and the committed `wing.vertex`
- **When** the wing-phase diagnostic is built for that configuration
- **Then** its `<name>_metrics.json` span-arm and hinge values are numerically identical to what the geometric-consistency guard (this spec) computes for the same deck — the figure and the automated check are provably checking the same underlying geometry, not two independently-tunable numbers

#### Scenario: Runs without any CFD output present

- **Given** a sweep configuration's input deck and `wing.vertex`, with no force CSV, plotfile, or cluster access available
- **When** the wing-phase diagnostic is built
- **Then** it succeeds, using only the deck's kinematics/hinge parameters and the geometry file

#### Scenario: Default sample is documented, not silent

- **Given** the CLI driver invoked with no `--config` argument
- **Then** it renders a documented, named subset of configurations (not all 54) and states in its own `--help` text and the figures README which configurations are included and why

### Requirement: Argo sweep-submission provisions the NFS workspace before submitting

`cluster/argo/scripts/submit_workflow.sh`'s `full` and `smoke` commands SHALL provision the
`--workspace-hostpath` from the local, git-committed corpus directory (its `inputs/` and the
canonical `examples/flapping_wing/wing.vertex`; `sweep_manifest*.json` additionally for `full`,
which reads it, but not for `smoke`, which runs a single named deck and never reads the manifest)
**before** calling `argo submit`, translating the cluster-hostPath convention
(`/hpi/hpi_dev/...`) to the WSL-visible mount point (`/mnt/hpi_dev/...`, per
`openspec/project.md`'s path table) before any filesystem operation — `submit_workflow.sh` runs
inside WSL, so operating on the unstranslated cluster-path string would silently no-op or write to
the wrong location while still reporting success. Provisioning SHALL replace (not merge into) any
prior `inputs/` content at the destination, SHALL verify the copy of `wing.vertex` specifically by
content hash (the one artifact with a documented history of silently drifting; `inputs/` and the
manifest rely on the replace-not-merge behavior plus `cp`'s own failure under `set -euo pipefail`),
and SHALL reject a `--corpus-dir`/`--workspace-hostpath` pair whose basenames don't match
(preventing one corpus's decks from being silently provisioned onto a different corpus's
workspace). Provisioning SHALL additionally reject a `--corpus-dir`/`--workspace-hostpath` pair
whose real (canonicalized) paths are **equal to, or nested inside, one another** — whether via an
identical literal path, two differently-spelled paths (relative vs. absolute, a trailing slash, a
symlink) naming the same real directory, or one path's real location being a descendant of the
other's (e.g. a coincidentally-matching basename deep inside the other's `inputs/` tree, even
though the two real paths are not byte-identical) — checked **before** the destructive
replace-not-merge step: an identity-only check is not enough, since `rm -rf
"$local_workspace/inputs"` destroys anything nested beneath it regardless of whether the nested
path is byte-identical to `$local_workspace` itself, and a basename-only comparison cannot
distinguish either hazard from two genuinely distinct corpora. Provisioning SHALL apply the
identical equal-to-or-nested-inside rejection to `WING_VERTEX_SOURCE` against the resolved
`--workspace-hostpath`: without it, a `WING_VERTEX_SOURCE` located at or under the workspace
(e.g. inside the `inputs/` tree the replace-not-merge step wipes, or exactly at the destination
`wing.vertex` path) can be deleted or corrupted by the same replace-not-merge step before the
final copy reads from it. It fails fast and loudly rather
than causing the submitted
workflow's pods to retry a mount for hours (issue #62) or, worse, silently run against stale or
mismatched geometry. Provisioning SHALL default to on and SHALL be skippable via an explicit
`--no-provision` flag for an operator who has already verified the workspace is current. This is
additive to, and independent of, the existing `--parallelism` override — sibling requirements, not
a replacement for either (cross-referenced from both requirements' descriptions, not a one-way
pointer).

#### Scenario: A stale or missing NFS workspace is provisioned before submission

- **Given** a `--corpus-dir` containing `inputs/` + `sweep_manifest.json` whose basename matches `--workspace-hostpath`'s basename, and a `--workspace-hostpath` (resolved to its local mount point) that is empty or contains stale content
- **When** `submit_workflow.sh full` runs (verified cluster-free via a stub `argo` executable and a `tmp_path`-rooted `--workspace-hostpath`/`CLUSTER_NFS_PREFIX`/`LOCAL_NFS_PREFIX`, per the existing `--parallelism` test convention — never a live cluster or real NFS mount)
- **Then** the resolved local workspace directory contains a byte-identical copy of `inputs/` and `sweep_manifest*.json` (verified by content equality at the test level, mirroring the existing `--parallelism` test's hashlib convention) and a copy of `wing.vertex` whose content hash the script **itself** verifies against the canonical source before proceeding — `wing.vertex` gets script-internal verification because it is the one artifact with a documented history of silently drifting; `inputs/`/the manifest rely on the replace-not-merge behavior (below) plus `cp`'s own failure under `set -euo pipefail` — and this provisioning completes before the stub `argo` is ever invoked

#### Scenario: A dropped config does not survive provisioning (replace, not merge)

- **Given** a `--workspace-hostpath` whose `inputs/` already contains a deck for a config that no longer exists in the current `--corpus-dir` (e.g. a config dropped when the corpus grid changed)
- **When** provisioning runs
- **Then** that stale deck is gone from the resulting `inputs/` afterward — provisioning replaces the destination's `inputs/` wholesale rather than only adding/overwriting matching filenames, so a shrunk or changed corpus can never leave an orphaned, silently-stale deck behind (the same failure class as a stale `wing.vertex`, just for `inputs/`)

#### Scenario: `smoke` provisions without requiring a manifest

- **Given** a `--corpus-dir` containing `inputs/` but no `sweep_manifest.json` (a lone deck being smoke-tested ad hoc, before any manifest exists)
- **When** `submit_workflow.sh smoke` runs
- **Then** provisioning succeeds (copying `inputs/` and `wing.vertex` only) and the stub `argo` is invoked — `smoke` never requires the manifest, unlike `full`

#### Scenario: The default cluster-to-local path translation is exactly right

- **Given** `CLUSTER_NFS_PREFIX`/`LOCAL_NFS_PREFIX` left at their real-world defaults (not overridden by a test — the script is sourced directly so the translation function is called with production defaults, not a test-substituted prefix pair)
- **When** the path-translation function is applied to `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep`
- **Then** it returns `/mnt/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep` exactly — a pure string-substitution check requiring no real filesystem or mount, since the real mount can't be exercised in CI

#### Scenario: A sibling cluster export sharing the prefix string is not mistranslated

- **Given** a hostpath under a *different* cluster export that happens to share `CLUSTER_NFS_PREFIX` as a string prefix but not as a path component (e.g. `/hpi/hpi_dev_archive/...` against the default `/hpi/hpi_dev` prefix)
- **When** the path-translation function is applied
- **Then** it returns the input unchanged (no translation applied) rather than silently rewriting it under `LOCAL_NFS_PREFIX`'s tree, which has no relationship to that sibling export — the prefix match is anchored on a path-component boundary (exact match or followed by `/`), not a bare string prefix

#### Scenario: A missing corpus-dir, a corpus-dir that is a file, or a corpus-dir missing inputs/, fails before any cluster action

- **Given**, separately: a `--corpus-dir` that does not exist at all; a `--corpus-dir` path that exists but is a file, not a directory; and a `--corpus-dir` that exists but whose `inputs/` subdirectory does not
- **When** `submit_workflow.sh full` runs for each
- **Then** each fails with a clear, **distinguishable** error (naming which condition applies — nonexistent vs. not-a-directory vs. missing `inputs/`), and the stub `argo` is never invoked for any of them (mirrors the existing `--parallelism` "fails before touching anything" convention)

#### Scenario: `full` additionally requires a manifest and its units sidecar; `smoke` does not

- **Given**, separately, a `--corpus-dir` containing `inputs/` but no `sweep_manifest.json`, and one containing `sweep_manifest.json` but no `sweep_manifest.units.json`
- **When** `submit_workflow.sh full` runs for each
- **Then** each fails with a clear error naming the specific missing file, before any copy or the stub `argo` is invoked — distinct from the `smoke` scenario above, where the identical corpus-dir provisions successfully because `smoke` never requires either manifest file

#### Scenario: A missing canonical `wing.vertex` source fails clearly

- **Given** `WING_VERTEX_SOURCE` resolving to a path that does not exist
- **When** provisioning runs
- **Then** it fails with a clear error naming the missing source, before the stub `argo` is invoked — not a bare `cp: cannot stat` message

#### Scenario: A corpus-dir/workspace-hostpath basename mismatch is rejected

- **Given** `--corpus-dir examples/prelim_sweep` (the coarse corpus) together with `--workspace-hostpath .../examples/prelim_sweep_fine` (the fine corpus's path) — the exact mistake of overriding one flag without the other
- **When** `submit_workflow.sh full` runs
- **Then** it fails with a clear error naming both mismatched paths, before any copy or the stub `argo` is invoked

#### Scenario: `--no-provision` skips the copy but still submits

- **Given** `submit_workflow.sh full --no-provision`, with a `--workspace-hostpath` that already contains different content than the local corpus-dir
- **When** the command runs
- **Then** the workspace-hostpath's existing content is left unchanged (no copy attempted), and the stub `argo` is still invoked with the submission proceeding normally

#### Scenario: Provisioned `wing.vertex` always matches the canonical file, independent of which corpus-dir is used

- **Given** at least two different `--corpus-dir`/`--workspace-hostpath` pairs (coarse and fine), neither of which carries its own committed `wing.vertex`
- **When** provisioning runs for each independently
- **Then** each resolved workspace's `wing.vertex` is byte-identical to the single canonical `examples/flapping_wing/wing.vertex`, never a different or stale copy, **for every corpus-dir tested** — this is the specific defect this requirement exists to prevent (this session found the live coarse corpus's NFS `wing.vertex` did not match any git-committed version)

#### Scenario: The script's own hardcoded defaults name the same corpus

- **Given** `submit_workflow.sh`'s built-in `CORPUS_DIR` and `WORKSPACE_HOSTPATH` defaults, with neither overridden
- **When** their basenames are compared
- **Then** they match — a static guard so a future edit to only one default (exactly the failure class this requirement fixes) is caught before it ever reaches the runtime basename-mismatch check on a real submission

#### Scenario: `--help` documents the new flags

- **Given** `submit_workflow.sh help`
- **When** the command runs
- **Then** its output names both `--corpus-dir` and `--no-provision`

#### Scenario: A `--corpus-dir`/`--workspace-hostpath` pair resolving to the same real path is rejected before any deletion

- **Given** a `--corpus-dir` and a `--workspace-hostpath` that either are the identical literal
  path, or are two differently-spelled paths (e.g. one with a trailing slash, or a `./`-relative
  spelling, or one reached via a symlink) that resolve to the same real directory
- **When** `submit_workflow.sh full` (or `smoke`) runs
- **Then** it fails fast with a clear, `die`-style error message before any filesystem mutation
  — in particular, before the `rm -rf` that would otherwise delete the corpus's own `inputs/`
  before the subsequent `cp -r` could read from it — and the corpus directory's `inputs/`
  contents are verified to still exist on disk afterward, not just that the command exited
  non-zero

#### Scenario: A `--corpus-dir` nested inside `--workspace-hostpath`'s own tree is rejected, not just an exact path match

- **Given** a `--corpus-dir` whose real path is a descendant of `--workspace-hostpath`'s real
  path (or vice versa) — e.g. a coincidentally-matching basename deep inside the other's
  `inputs/` tree — even though the two real paths are not byte-identical
- **When** `submit_workflow.sh full` (or `smoke`) runs
- **Then** it fails fast with a clear error before any filesystem mutation, the same as the
  exact-match case — an identity-only check is insufficient, since `rm -rf
  "$local_workspace/inputs"` destroys anything nested beneath it regardless of whether the
  nested path is byte-identical to `$local_workspace` itself

#### Scenario: A `WING_VERTEX_SOURCE` at or inside `--workspace-hostpath` is rejected before any deletion

- **Given** `WING_VERTEX_SOURCE` resolving to a real path that is equal to, or a descendant of,
  the resolved `--workspace-hostpath` (e.g. somewhere inside the `inputs/` tree the
  replace-not-merge step wipes, or exactly at the destination `wing.vertex` path)
- **When** `submit_workflow.sh full` (or `smoke`) runs
- **Then** it fails fast with a clear, `die`-style error message before any filesystem mutation
  — the identical hazard class as the `--corpus-dir`/`--workspace-hostpath` check above, just
  for the canonical wing.vertex source

#### Scenario: A `--corpus-dir`/`--workspace-hostpath` pair sharing a long path prefix but naming genuinely distinct siblings is not falsely rejected

- **Given** a `--corpus-dir` and a `--workspace-hostpath` with matching basenames whose parent
  directories share a long string prefix (e.g. `.../staging` and `.../staging_other`) but are
  genuinely distinct, non-nested sibling directories
- **When** `submit_workflow.sh full` (or `smoke`) runs
- **Then** provisioning succeeds normally — the same-path/nesting check is boundary-aware (a
  trailing path separator before comparing), so a shared string prefix alone never triggers a
  false rejection

### Requirement: Corpus-generation CLI drivers require an explicit timestamp

Both corpus-generation CLI drivers SHALL require `--timestamp` as an explicit, ISO-8601-validated
CLI argument with **no default value** — this applies to `examples/prelim_sweep/generate_sweep.py`
and `examples/prelim_sweep_fine/generate_full_corpus.py`. A real regeneration run must supply a
fresh, caller-chosen, well-formed timestamp — never silently reuse a literal from the script's
original authoring session (which would misleadingly stamp a corrected corpus's provenance as if
generated on the original, pre-fix date), and never accept an empty or malformed value that
`required=True` alone would not catch.

#### Scenario: Omitting `--timestamp` is rejected

- **Given** either driver invoked with no `--timestamp` argument
- **When** `main()` parses arguments
- **Then** it exits non-zero via argparse's own "required argument" error, before any file is read or written

#### Scenario: An empty or malformed `--timestamp` value is rejected

- **Given** either driver invoked with `--timestamp ""` or a non-ISO-8601 string (e.g. `"not-a-timestamp"`)
- **When** `main()` parses arguments
- **Then** it exits non-zero before any file is read or written — presence of the flag alone is not sufficient; the value must parse as ISO-8601

#### Scenario: A frozen-path rejection is not masked by the timestamp requirement

- **Given** a CLI invocation with `--output` pointed at a frozen/protected path (e.g. the committed pilot directory) **and** an explicit, valid `--timestamp` supplied
- **When** `main()` runs
- **Then** it exits via the frozen-path guard's own `SystemExit` (naming the protected path), not via a missing-`--timestamp` argparse error — the two guards are independently reachable, and supplying `--timestamp` is what makes that possible to observe

### Requirement: Argo sweep-submission deadline is overridable without mutating the committed workflow

`cluster/argo/scripts/submit_workflow.sh`'s `full` command SHALL accept an optional
`--active-deadline-seconds` flag that overrides the submitted workflow's `activeDeadlineSeconds`
without editing the checked-in workflow file — mirroring the existing `--parallelism` requirement
("Argo sweep-submission parallelism is overridable without mutating the committed workflow"),
which this requirement is additive to and independent of. Since the committed
`activeDeadlineSeconds: 86400` (24h) was implicitly sized for the committed default
`parallelism: 3`, overriding `--parallelism` alone without a matching deadline change can silently
doom a submission to a deadline-kill before completion (the failure mode observed in
`force-surrogate-sweep-7wrk7`, 0/27 configs completed at `parallelism=1`). When the flag is
supplied, the script SHALL apply the override by submitting an anchored, self-verifying
`sed`-patched temporary copy of the workflow file — the same mechanism as `--parallelism`, and
when both flags are supplied together, both patches SHALL land on the same temporary copy. When
the flag is **omitted** and `--parallelism` is also omitted, the script SHALL submit the
committed workflow file unpatched.

#### Scenario: `--active-deadline-seconds` overrides the deadline without touching the committed file

- **Given** `cluster/argo/scripts/submit_workflow.sh full --active-deadline-seconds 172800` (no
  `--parallelism`)
- **When** the command runs
- **Then** the sed-patched temporary copy passed to `argo submit` has
  `activeDeadlineSeconds: 172800` and an unchanged `parallelism:` line (the committed default),
  and `cluster/argo/workflows/force-surrogate-sweep.yaml` on disk is byte-identical (same
  `sha256`) before and after the command runs

#### Scenario: `--parallelism` and `--active-deadline-seconds` compose onto one temporary copy

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1
  --active-deadline-seconds 200000`
- **When** the command runs
- **Then** the single sed-patched temporary copy passed to `argo submit` has **both**
  `parallelism: 1` and `activeDeadlineSeconds: 200000` set correctly, and the committed workflow
  file is unchanged on disk

#### Scenario: Omitting both flags remains a true no-op

- **Given** `cluster/argo/scripts/submit_workflow.sh full` invoked with neither `--parallelism`
  nor `--active-deadline-seconds`
- **When** the command runs
- **Then** the committed `force-surrogate-sweep.yaml` is passed to `argo submit` unpatched — no
  temporary file is created at all

#### Scenario: An invalid `--active-deadline-seconds` value is rejected before any file is touched

- **Given** `cluster/argo/scripts/submit_workflow.sh full --active-deadline-seconds 0` (or a
  negative or non-integer value)
- **When** the command runs
- **Then** it fails fast with a clear error before creating any temporary file or invoking `argo
  submit`, and the committed workflow file is untouched

#### Scenario: A failed deadline substitution is never silently submitted

- **Given** the workflow file's top-level `activeDeadlineSeconds: <N>` line is missing or does not
  match the expected anchored pattern
- **When** `--active-deadline-seconds` is supplied
- **Then** the script fails with a clear error rather than submitting an unpatched or
  partially-patched temporary copy

#### Scenario: Help text documents the flag and the coupling risk

- **Given** `cluster/argo/scripts/submit_workflow.sh help`
- **When** the command runs
- **Then** its output documents `--active-deadline-seconds`, and separately documents the
  coupling risk that overriding `--parallelism` without a matching deadline change can silently
  doom a submission to a deadline-kill — not just the flag's existence in isolation

### Requirement: An overridden parallelism without an explicit deadline auto-scales the deadline instead of silently reusing a stale default

`cluster/argo/scripts/submit_workflow.sh full` SHALL compute a replacement `activeDeadlineSeconds`
instead of leaving the committed 24h value unpatched whenever `--parallelism` is overridden and
`--active-deadline-seconds` is **not** explicitly given. The computed value
SHALL be derived from the actual config count in the resolved `--corpus-dir`'s
`sweep_manifest.json` (not a hardcoded constant), a documented per-config-hours estimate, the
given parallelism, and a fixed retry margin, rounded up to a whole hour. An explicitly-supplied
`--active-deadline-seconds` SHALL always take precedence over the auto-computed value, and no
auto-scale computation SHALL be attempted when an explicit value is given.

#### Scenario: Overriding parallelism alone auto-scales the deadline

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` declares exactly 3 configs (the real
  `{"configs": [...]}` schema), and no `--active-deadline-seconds`
- **When** the command runs
- **Then** the sed-patched temporary copy's `activeDeadlineSeconds` equals
  `ceil(3 * 2.4 / 1 + 4) * 3600 = 43200` seconds — not the committed default, and not a value
  independent of the actual manifest's config count. More generally, for any config count and
  parallelism, the computed value equals `ceil(config_count * 2.4 / parallelism + 4) * 3600`

#### Scenario: An explicit deadline is never overridden by auto-scale

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1
  --active-deadline-seconds 999999 --no-provision` with a `--corpus-dir` whose manifest is
  missing or otherwise unreadable
- **When** the command runs
- **Then** the command succeeds with `activeDeadlineSeconds: 999999` in the patched copy — the
  auto-scale computation is never attempted, so an unreadable manifest under this combination of
  flags does not cause a failure

#### Scenario: Auto-scale falls back to a working Python interpreter

- **Given** a `full` invocation where auto-scale is eligible to fire, and `python3` resolves on
  `PATH` but is non-functional (e.g. a Windows App-Execution-Alias stub), while `python` on
  `PATH` is a genuinely working interpreter
- **When** the command runs
- **Then** auto-scale succeeds by falling back to `python` — the script probes each candidate
  by actually invoking it, not merely checking that `PATH` resolution succeeds, and the broken
  `python3` is never used for the real computation

#### Scenario: Auto-scale fails clearly when no working interpreter is found at all

- **Given** a `full` invocation where auto-scale is eligible to fire, and neither `python3` nor
  `python` on `PATH` is a genuinely working interpreter
- **When** the command runs
- **Then** it fails fast with a clear, `die`-style error message before invoking `argo submit`,
  not an uncaught interpreter error

#### Scenario: Auto-scale fails clearly, not with a raw crash, when the manifest is unreadable

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 2 --no-provision` with a
  `--corpus-dir` that exists but has no `sweep_manifest.json`, and no `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear, `die`-style error message before invoking `argo submit`,
  not an uncaught interpreter traceback

#### Scenario: Auto-scale fails clearly, not with a raw crash, when the manifest exists but is malformed

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 2 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` exists but is malformed (invalid JSON, missing the
  `"configs"` key, or `"configs"` present but not a list), and no `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear error message before invoking `argo submit`, not an
  uncaught interpreter traceback and not a silently wrong deadline computed from a misread value

#### Scenario: Auto-scale refuses to fire when `--corpus-dir` and `--workspace-hostpath` name different corpora

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` and `--workspace-hostpath` whose basenames do not match, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear error before invoking `argo submit` — `--no-provision`
  skips `provision()`'s own basename-match guard, so auto-scale (which reads `--corpus-dir`'s
  manifest independently of `--workspace-hostpath`) must not silently compute a deadline from
  the wrong corpus's config count

#### Scenario: An explicit deadline never triggers the basename-consistency check

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --active-deadline-
  seconds 999999 --no-provision` with a `--corpus-dir` and `--workspace-hostpath` whose
  basenames do not match
- **When** the command runs
- **Then** the command succeeds with `activeDeadlineSeconds: 999999` — the basename-consistency
  check is scoped to the auto-scale trigger path only, and an explicit `--active-deadline-
  seconds` never enters that path

#### Scenario: An invalid `--parallelism` is rejected before auto-scale is ever attempted

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (or `-1` or `abc`),
  no `--active-deadline-seconds`, and a `--corpus-dir` whose manifest exists and is readable
- **When** the command runs
- **Then** it fails fast with a clear "positive integer" error message and no interpreter
  traceback appears in its output — `--parallelism` is validated before it is ever passed to the
  auto-scale computation, not after

#### Scenario: A degenerate config count does not crash the formula

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` declares zero configs, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** the computed `activeDeadlineSeconds` equals `14400` (just the 4-hour retry margin,
  `ceil(0 * 2.4 / 1 + 4) * 3600`) — the formula degrades gracefully rather than erroring or
  producing a nonsensical value

#### Scenario: A very large parallelism does not overflow or underflow the formula

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1000000 --no-provision`
  with a `--corpus-dir` whose `sweep_manifest.json` declares 3 configs, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** the computed `activeDeadlineSeconds` equals `18000` (`ceil(3 * 2.4 / 1000000 + 4) *
  3600 = ceil(4.0000072) * 3600 = 5 * 3600` — the config-count term contributes only `0.0000072`,
  but `ceil` still rounds up past that nonzero remainder to `5`, not `4`) — the formula produces
  a sane, correctly-rounded floor rather than a nonsensical tiny, negative, or overflowed value

### Requirement: retryStrategy backoff can cover the full configured retry limit

`cluster/argo/workflow-templates/force-surrogate-single-config.yaml`'s `retryStrategy.backoff` SHALL
cap cumulative retry backoff (`maxDuration`) high enough that all `limit`-configured retries can
actually be attempted before Argo gives up, given the corpus's real per-attempt runtimes and
observed preemption frequency — not a value that exhausts itself partway through the configured
retry budget, as `maxDuration: "30m"` did for `duration: "2m"`/`factor: 2` (exhausted after 3 of 5
configured retries).

#### Scenario: The full retry sequence fits within maxDuration

- **Given** the `force-surrogate-single-config` WorkflowTemplate's `retryStrategy`
- **When** its `backoff` block is inspected
- **Then** `limit: 5`, `duration: "2m"`, `factor: 2` are unchanged, and `maxDuration` is `"4h"` —
  the cumulative backoff sequence for all 5 configured retries (`2m+4m+8m+16m+32m = 62m`) fits
  well within the cap, so a config that needs multiple preemption-driven retries is not cut off
  by `maxDuration` before its configured `limit` is exhausted

### Requirement: Field-capture plotfile velocity verification (CC-F1)

The module SHALL provide a reusable, standalone check that a given AMReX plotfile's `x_velocity`
field is not silently zero before that plotfile is trusted as training data for any downstream
field-surrogate work. This guards against a known, previously-hit defect: with `ns.init_iter = 0`,
IAMReX computes the induced velocity field internally but never persists it to the plotfile — every
`x_velocity` value in an affected plotfile reads as exactly zero, with no other symptom. The check
is scoped to `x_velocity` specifically (the documented defect signature), not to every velocity
component being non-zero — a physically valid field can have a legitimately-zero component (e.g. a
purely 2D flow's out-of-plane velocity), and a check that rejected any zero component would produce
false positives on real, correct data. Independently, the module SHALL also reject a
NaN- or Inf-contaminated field — but this second check is scoped across ALL THREE velocity
components (`x_velocity`, `y_velocity`, `z_velocity`), not `x_velocity` alone: unlike zero, there is
no physically valid scenario where a converged solve legitimately produces NaN or Inf in any
velocity component, so the reasoning that narrows the zero-check to `x_velocity` does not extend to
NaN/Inf. The check SHALL be built on the existing
`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` reader rather than a new plotfile
reader.

#### Scenario: A plotfile with a real, non-zero `x_velocity` field passes

- **Given** a plotfile whose velocity field was captured with `ns.init_iter = 2` (or otherwise
  contains genuinely non-zero `x_velocity` values) — including a plotfile with a legitimately-zero
  other component (e.g. `z_velocity = 0` for a 2D flow), which SHALL NOT cause a false rejection
- **When** the check is run against it
- **Then** it reports the field as valid (non-zero), without raising

#### Scenario: A plotfile with an all-zero `x_velocity` field is rejected

- **Given** a plotfile whose `x_velocity` field is entirely zero (the `ns.init_iter = 0` defect
  signature)
- **When** the check is run against it
- **Then** it raises a clear, actionable error naming the defect (not a generic assertion failure),
  so an operator sees immediately that the deck's `ns.init_iter` setting is the likely cause

#### Scenario: A NaN- or Inf-contaminated field is rejected regardless of which component carries it

- **Given** a plotfile whose `x_velocity`, `y_velocity`, or `z_velocity` field contains NaN or Inf
  in at least one cell — including the case where `x_velocity` itself is clean and genuinely
  non-zero but a different component is contaminated
- **When** the check is run against it
- **Then** it raises, naming the contamination (not the `ns.init_iter=0` defect, a different
  failure mode) — a corrupted/diverged field must never be reported as a passing result solely
  because `x_velocity` happens to look clean

#### Scenario: The check runs cluster-free in CI

- **Given** the committed synthetic AMReX plotfile fixture (already used by the existing
  `extract_eulerian_box` tests, per issue #33)
- **When** the check's own test suite runs
- **Then** it requires no live cluster, GPU, or real plotfile — only the committed fixture

