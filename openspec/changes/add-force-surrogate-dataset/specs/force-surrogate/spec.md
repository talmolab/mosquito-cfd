## ADDED Requirements

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
