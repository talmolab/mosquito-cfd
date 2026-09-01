## MODIFIED Requirements

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

## ADDED Requirements

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
