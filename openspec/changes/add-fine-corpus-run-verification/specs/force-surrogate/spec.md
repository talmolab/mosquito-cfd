# force-surrogate

## MODIFIED Requirements

### Requirement: Run duration scaled to whole wingbeats

The module SHALL set each configuration's run duration to cover a fixed, configurable number of
**complete wingbeats** (default 2) at the validated fixed timestep `dt = 5e-4`, via
`stop_time = n_wingbeats / f*` and `max_step = round(stop_time / dt)`. This guarantees every
configuration — including low-frequency ones where a fixed `stop_time = 1.0` would cover less than
one beat — captures whole periodic cycles. `dt` SHALL NOT be changed from the validated value.

This guarantee holds **only while `ns.fixed_dt` is the binding timestep constraint.** `ns.cfl` is an
independent limiter that can reduce the realized step below `ns.fixed_dt`; when it does, the run
exhausts `max_step` before reaching `stop_time` and terminates mid-wingbeat, silently. A corpus
SHALL therefore be generated with an `ns.cfl` value high enough that `ns.fixed_dt` binds for every
configuration at that corpus's grid resolution and kinematic range, and the resulting runs SHALL be
verified to have held their nominal timestep (see the run-metadata capability's observed-timestep
fields and the post-run acceptance gate below).

#### Scenario: Duration matches the per-frequency formula

- **Given** `frequency_fstar = 0.85`, `n_wingbeats = 2`, `dt = 5e-4`
- **When** `derive_run_duration` is called
- **Then** `stop_time ≈ 2.3529` (= 2 / 0.85) and `max_step = 4706` (= round(2.3529 / 5e-4))

#### Scenario: Every config covers at least the requested whole wingbeats

- **Given** the default 27-config sweep with `n_wingbeats = 2`
- **When** each generated input file is parsed
- **Then** for every config `stop_time * frequency_fstar ≥ 2` (at least two complete beats)
- **And** every config retains the validated `ns.fixed_dt = 0.0005`

#### Scenario: The requested wingbeats are actually completed, not merely requested

- **Given** a completed corpus whose decks request `n_wingbeats = 2`
- **When** each configuration's observed run output is inspected
- **Then** every configuration's `cycles_completed` reaches `n_wingbeats` to within the writer's
  one-step-short convention, and no configuration terminated on `max_step` with a CFL-reduced
  interior timestep

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
distinct from `amr.plot_int`'s "rewritten to a default" behavior.

`ns.cfl` SHALL be a further additional, optional targeted key with exactly the same pass-through
semantics as `ns.init_iter`: untouched unless the caller supplies a value. It is threaded through the
generator rather than edited in a base deck so that the fine corpus's base deck remains an exact copy
of the frozen coarse base deck except for `amr.n_cell`, preserving the deck-invariance guarantee.

Neither `amr.plot_int`, `ns.init_iter`, nor `ns.cfl` overrides are bounds-validated by this
requirement (e.g. `0` or a negative value other than `-1` are accepted and written verbatim) —
validating the physical sense of a supplied value is out of scope; a targeted key absent from the
base SHALL raise rather than be silently skipped, generated files SHALL use **LF (`\n`) line
endings** regardless of host platform, and numeric values SHALL be written with a **deterministic,
platform-independent formatter** so the corpus is byte-reproducible.

#### Scenario: Generated file differs from base only in the swept and derived keys

- **Given** a generated input file (no field-capture override) and the base `inputs.3d.validation`
- **When** both are parsed into key→value maps
- **Then** the keys whose values differ are exactly `{particle_inputs.kinematics_stroke_amp, particle_inputs.kinematics_frequency, particle_inputs.kinematics_pitch_amp, max_step, stop_time, amr.plot_int}`
- **And** all other keys (e.g. `geometry_type`, `geometry_file`, `hinge_*`, `ns.vel_visc_coef`, `ns.init_iter`, `ns.cfl`, projection tolerances) are unchanged
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

#### Scenario: `cfl` set via an explicit override, independent of the other overrides

- **Given** the sweep is generated with an explicit `cfl` override (e.g. `0.6`) and `plot_int` /
  `init_iter` left at their defaults
- **When** each generated input file is parsed
- **Then** every file has `ns.cfl` equal to the supplied override value, `amr.plot_int` is unchanged
  from its own default (`-1`), and `ns.init_iter` is unchanged from the base

#### Scenario: Omitting the field-capture override preserves today's exact behavior

- **Given** the sweep is generated with `plot_int`/`init_iter`/`cfl` all omitted (or explicitly
  `None`)
- **When** the output is compared against a generation from before this change existed
- **Then** the output is byte-identical — this change is purely additive for every caller that
  doesn't opt in, including the coarse corpus's own generation

#### Scenario: Missing target key is rejected

- **Given** a base inputs text that lacks one of the targeted keys (e.g. `amr.plot_int`, or
  `ns.init_iter`/`ns.cfl` when that override is actually supplied)
- **When** `render_inputs` is called
- **Then** it raises `ValueError` naming the missing key rather than producing a file without the
  requested value

#### Scenario: LF newlines and deterministic numeric formatting

- **Given** a sweep is generated to disk (and, separately, `render_inputs` is called on a base text)
- **When** a written input file is read back as raw bytes and a representative config's rendered text is inspected
- **Then** the file on disk contains no `\r` byte (LF-only, regardless of host platform — the write uses `newline=""`), and the config renders the exact, platform-independent value strings (e.g. `particle_inputs.kinematics_frequency = 0.85`, `max_step = 4706` as a bare integer) so two regenerations on different platforms are byte-identical

### Requirement: Reproducible sweep manifest with units sidecar

The module SHALL emit a **deterministic** `sweep_manifest.json` recording, per configuration, the
kinematic parameters, `nu_star`, `reynolds`, derived `max_step`/`stop_time`, `plot_int`, an optional
`init_iter` field, an optional `cfl` field, the train/holdout `split`, and the input-file path; plus
top-level grid levels, the resolved Reynolds policy, and the holdout seed. `init_iter` SHALL be
present with the caller's supplied value when a field-capture `init_iter` override was requested, and
SHALL be omitted entirely (not recorded as `null`) when the caller left it at its default
pass-through — mirroring `ns.init_iter`'s own pass-through-by-default behavior in the generated deck.
`cfl` SHALL follow exactly the same omit-not-null convention. It SHALL emit a
`sweep_manifest.units.json` via the PR1 `write_units_sidecar` helper declaring the unit of each
measured column. It SHALL emit a separate `sweep_provenance.json` carrying environmental
provenance — git commit, base-inputs SHA256, and a **caller-supplied** timestamp, and **no** Docker
image digest (PR2 runs no container). When the caller requests a field-capture override (a
non-default `plot_int` and/or `init_iter`), `sweep_provenance.json` SHALL additionally carry a
top-level `field_capture` block recording the resolved policy (`plot_int`, a one-line rationale, a
pointer to CC-F1/CC-F3, and `init_iter` when it was itself overridden — omitted, not recorded as
`null`, when only `plot_int` was overridden, mirroring the manifest's own omit-not-null convention
for `init_iter` rather than introducing a second, differently-encoded "not requested" representation);
when no override is requested at all, no `field_capture` block is present. When a `cfl` override is
requested, `sweep_provenance.json` SHALL carry a top-level `timestep_policy` block recording the
resolved `cfl`, the nominal `fixed_dt` it is chosen to protect, and a one-line rationale; when no
`cfl` override is requested, no `timestep_policy` block is present. Provenance is kept out
of the manifest so the manifest stays byte-reproducible: the
`git_commit` is inherently non-reproducible across checkouts, so it must not contaminate the
byte-identity guarantee. Regenerating the sweep with the recorded seed and timestamp SHALL produce
byte-identical input files and a byte-identical manifest + units sidecar, for the force-only
default, an explicit field-capture override, or an explicit `cfl` override.

`sweep_provenance.json`'s record of superseded cluster runs SHALL be a **list-valued supersession
history**, each entry naming the superseded workflow(s) and the reason, so a corpus that is
superseded more than once does not require rewriting or discarding the earlier record.

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

#### Scenario: A cfl override is recorded in the manifest and provenance, default omits both

- **Given** a sweep generated with an explicit `cfl` override
- **When** `sweep_manifest.json` and `sweep_provenance.json` are read
- **Then** every config's record includes `"cfl"` set to the supplied value, and provenance includes
  a top-level `timestep_policy` block recording the resolved `cfl`, the nominal `fixed_dt`, and a
  rationale
- **And** a sweep generated without a `cfl` override has no `"cfl"` key on any config record (not
  `null`) and no `timestep_policy` block

#### Scenario: Supersession history accumulates rather than being overwritten

- **Given** a corpus whose provenance already records one superseded cluster run
- **When** a second, later run supersedes it
- **Then** the supersession history contains both entries in chronological order, each naming its
  workflow(s) and reason, and the earlier entry is unmodified

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
row per step), so a corpus extracted before this capability existed re-extracts byte-identically and
the frozen coarse corpus is unaffected.

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

### Requirement: Cluster-side Argo orchestration of the corpus

The repository SHALL provide Argo Workflows artifacts that run the committed 27-config corpus
robustly on the cluster as the production path, **superseding** the laptop `runai exec` driver (which
is retained as a documented local/dev fallback). Each configuration SHALL run as its own pod whose
main process is the CFD run, with a full-GPU request, run-as-root for `mpirun`, and automatic retries;
the workflow SHALL fan out over the configurations declared in `sweep_manifest.json` under a bounded
concurrency, and SHALL gate overall success on every configuration's CSV passing the completion check.
The workflow itself SHALL be agnostic to whatever `amr.plot_int`/`ns.init_iter`/`ns.cfl` values the
configs' decks actually contain — it neither inspects nor constrains those values, since its own steps
(`validate`, the fan-out, `verify-complete`) only ever read/write the IB-particle CSV, regardless
of whether the submitted corpus is force-only or field-capture-enabled.

The committed default `activeDeadlineSeconds` SHALL be at least the value the submission script's own
auto-scale formula computes for the full corpus at the committed `parallelism`, and SHALL additionally
accommodate the retry headroom that the configured `retryPolicy` makes reachable, so that submitting
with committed defaults cannot under-provision the deadline. The same default SHALL be applied to
every committed workflow that carries one, including the smoke workflow, whose value no command-line
flag can patch.

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
- **Then** concurrent GPU pods are capped by the workflow's spec-level `parallelism` (default 3 — the limited A40 quota, not an unbounded 27-way burst; a literal, since Argo's `parallelism` is an `int` field that takes no `{{...}}` parameter) and the run is bounded by `activeDeadlineSeconds`, so a wedged run is killed rather than holding the quota indefinitely; per-pod `retryStrategy` backoff (not the deadline) handles transient failures

#### Scenario: The committed deadline is not below the script's own formula

- **Given** the committed `parallelism` and the full corpus's configuration count
- **When** the submission script's auto-scale formula is evaluated for them
- **Then** the committed `activeDeadlineSeconds` is greater than or equal to the computed value
- **And** it additionally accommodates at least two preemption retries of the longest configuration at
  the documented per-config cost

#### Scenario: The smoke workflow carries the same committed deadline

- **Given** the committed smoke workflow
- **When** its `activeDeadlineSeconds` is inspected
- **Then** it equals the same committed default as the sweep workflow, not a smaller,
  workflow-specific value
- **And** no `--parallelism` or `--active-deadline-seconds` flag passed to a smoke submission can
  override it

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

### Requirement: retryStrategy backoff can cover the full configured retry limit

`cluster/argo/workflow-templates/force-surrogate-single-config.yaml`'s `retryStrategy.backoff` SHALL
cap cumulative retry backoff (`maxDuration`) high enough that all `limit`-configured retries can
actually be attempted before Argo gives up, given the corpus's real per-attempt runtimes and
observed preemption frequency — not a value that exhausts itself partway through the configured
retry budget, as `maxDuration: "30m"` did for `duration: "2m"`/`factor: 2`.

`maxDuration` SHALL be documented and sized as **wall-clock measured from the first attempt's
start**, which includes each attempt's own runtime, not merely the sum of the backoff intervals. At a
per-attempt cost of hours, a value chosen against the backoff series alone silently permits far fewer
attempts than the configured `limit`.

`retryPolicy` SHALL be `"Always"`. `"OnFailure"` sets `retryOnError = false` and cannot cover a pod
deleted by preemption, which Argo surfaces as node phase `Error` with message `pod deleted`.
`"OnError"` is unsuitable in the opposite direction: it sets `retryOnFailed = false`, abandoning
application-level failures, and preemption is not classified consistently as `Error` across
platforms. Only `"Always"` covers both.

#### Scenario: The full retry sequence fits within maxDuration

- **Given** the `force-surrogate-single-config` WorkflowTemplate's `retryStrategy`
- **When** its `backoff` block is inspected
- **Then** `limit: 5`, `duration: "2m"`, `factor: 2` are unchanged, and `maxDuration` accommodates
  `limit + 1` attempts at the documented per-attempt cost plus the cumulative backoff sequence
  (`2m+4m+8m+16m+32m = 62m`), so a config that needs multiple preemption-driven retries is not cut
  off by `maxDuration` before its configured `limit` is exhausted

#### Scenario: A preempted pod is retried

- **Given** the committed single-config WorkflowTemplate
- **When** its `retryStrategy` is inspected
- **Then** `retryPolicy` is `"Always"`, so a pod deleted by preemption (node phase `Error`, message
  `pod deleted`) is retried rather than abandoned

## ADDED Requirements

### Requirement: Post-run acceptance gate blocks dataset construction on an unverified corpus

A corpus SHALL pass an acceptance gate **after** run metadata is generated and **before** the tidy
dataset is built, so a truncated, duplicated or unverified run can never reach a committed
`dataset.parquet`.

The gate SHALL fail if, for any configuration: the run's observed interior timesteps fell below the
deck's declared `ns.fixed_dt`; the force CSV's deduplicated row count does not equal the manifest's
`max_step`; or `time` is not strictly increasing.

The gate's primary physical check SHALL be a **normalized** cycle-symmetry ratio — the settled-beat
mean chordwise coefficient divided by that configuration's settled-beat peak chordwise coefficient —
rather than an absolute mean. The absolute settled-beat mean is not zero: it scales with pitch
amplitude and reaches 2.9% of `F_ref` on a healthy corpus, leaving a usable tolerance window of only
about 1.3×, whereas the normalized ratio separates healthy from truncated configurations by roughly
two orders of magnitude.

The gate SHALL additionally fail if a mandatory pre-flight check has **no recorded result** for the
corpus. An absent result SHALL be treated as a failure, not a warning, because an unrecorded check is
indistinguishable from one that was never run.

The gate SHALL recompute at least one of its quantities directly from the raw run output rather than
reading every value back from the metadata file it is gating, so an error in the metadata generator
cannot certify its own corpus.

The gate SHALL be runnable offline against committed artifacts plus the run's output, with no cluster
or Argo access.

#### Scenario: A CFL-limited config fails the gate

- **Given** a corpus in which one configuration's observed interior timesteps fell to `3.06e-4`
  against a declared `ns.fixed_dt` of `5e-4`
- **When** the acceptance gate runs
- **Then** it fails, naming that configuration and its observed minimum timestep

#### Scenario: A corpus with duplicate timesteps fails the gate

- **Given** a corpus whose force CSV deduplicated row count does not equal its manifest `max_step`
- **When** the acceptance gate runs
- **Then** it fails, naming the configuration and both counts

#### Scenario: A truncated config fails the normalized symmetry check

- **Given** a configuration that covered only 83% of its settled wingbeat
- **When** the acceptance gate runs
- **Then** its normalized cycle-symmetry ratio exceeds the stated tolerance and the gate fails

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

- **Given** a corpus whose metadata JSON has been hand-edited to claim a passing
  `interior_dt_below_nominal = false` while the underlying run output shows CFL-reduced interior
  timesteps
- **When** the acceptance gate runs
- **Then** it fails, because it recomputes the timestep check from the raw run output rather than
  trusting the metadata's claim

### Requirement: Mandatory pre-flight check results are recorded in corpus provenance

Every mandatory pre-flight or mid-sweep gate defined by the submission runbook SHALL persist its
outcome into the corpus's `sweep_provenance.json` under `cluster_run`, recording at minimum the check
name, the artifact it was run against, the observed value it gated on, and a pass/fail verdict.

The `cluster_run` block SHALL also record the submitted `parallelism` and the effective
`activeDeadlineSeconds`, so a deadline-related claim about a completed run is auditable from the
committed artifacts alone.

A mid-sweep gate evaluated against a partial corpus SHALL record that it was partial, and SHALL NOT
be treated as satisfying the post-run acceptance gate: mid-sweep, configurations that have not yet
finished legitimately report as incomplete, whereas post-run the same signal is a defect.

#### Scenario: CC-F1 is recorded with the value it observed

- **Given** a field-capture corpus whose CC-F1 plotfile-velocity check has been run
- **When** `sweep_provenance.json` is read
- **Then** `cluster_run` records the check name, the plotfile path, the observed `x_velocity` range,
  and a pass verdict

#### Scenario: Deadline provenance is recorded

- **Given** a completed cluster run
- **When** `cluster_run` is read
- **Then** it records the submitted `parallelism` and the effective `activeDeadlineSeconds`

#### Scenario: A partial mid-sweep result does not satisfy the post-run gate

- **Given** a `cluster_run` record whose only completion evidence is a mid-sweep partial check
- **When** the post-run acceptance gate runs
- **Then** it does not treat the partial record as a passing post-run result

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
with the tolerance recorded alongside the measured healthy maximum and truncated minimum that bound
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

#### Scenario: A truncated corpus is caught by the normalized symmetry invariant

- **Given** a corpus containing a configuration that covered only 83% of its settled wingbeat
- **When** the symmetry guard runs
- **Then** it fails, because that configuration's normalized cycle-symmetry ratio exceeds tolerance

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
