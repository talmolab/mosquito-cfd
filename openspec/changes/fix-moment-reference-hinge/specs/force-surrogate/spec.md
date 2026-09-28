# force-surrogate — moment reference point

## ADDED Requirements

### Requirement: Moment coefficients are referenced to the wing hinge

Extracted moment coefficients `CF_mx/CF_my/CF_mz` SHALL be taken about the **wing hinge**, not
about the immersed-boundary particle's own origin as written by IAMReX. Dataset extraction SHALL
apply the parallel-axis shift `M_hinge = M_origin + (r_origin − r_hinge) × F` before
normalization.

**BREAKING**: a corpus extracted before this change therefore carries different `CF_mx` and
`CF_mz` values; `CF_my` is unchanged wherever the origin-to-hinge offset is purely spanwise.

The reference point is defined canonically in `docs/coordinate-convention.md`
([Coordinate Convention](../coordinate-convention/spec.md)); this capability owns only the
extraction mechanism and SHALL cross-reference rather than restate the definition.

These are **lab-frame moment components taken about the hinge**. The shift relocates the
**origin** only; it does not rotate the axes. A body-frame (wing-frame) moment would additionally
require rotating by `R(t)ᵀ`, which is out of scope (GitHub issue #1). Documentation SHALL NOT
claim the moments are in van Veen's wing frame.

The raw `Mx/My/Mz` columns SHALL retain the solver's as-written values about its own origin,
preserving the audit trail back to CFD output; only the derived `CF_m*` coefficients are
referenced to the hinge. The applied offset SHALL be recorded in the corpus's dataset-build
provenance so the correction is re-derivable from the committed parquet alone.

#### Scenario: Parallel-axis shift is applied at extraction

- **Given** a run whose CSV `X,Y,Z` columns are a constant `(4, 2, 4)` and whose deck declares `hinge = (4, 0.5, 4)`
- **When** the dataset is extracted
- **Then** the emitted `CF_mx/CF_my/CF_mz` correspond to moments about `(4, 0.5, 4)`, equal to the raw moments shifted by `(0, 1.5, 0) × F`, divided by `m_ref`
- **And** the emitted raw `Mx/My/Mz` columns are bitwise equal to the CSV's values

#### Scenario: A spanwise shift leaves the M_y component invariant

- **Given** a run whose origin-to-hinge offset is purely along the span axis `y`, with all-finite `Fx/Fy/Fz`
- **When** the parallel-axis shift is applied
- **Then** the resulting `CF_my` **compares equal** (`==`, accepting `-0.0 == 0.0`) to the unshifted `CF_my` for every row, because the y-term of `(0, a, 0) × F` is identically zero
- **And** `CF_mx` and `CF_mz` equal `(Mx + a·Fz)/m_ref` and `(Mz − a·Fx)/m_ref` exactly — this clause, **not** the `M_y` invariance, is what pins the cross-product **order**, since a reversed `F × d` would also leave the y-component zero
- **And** the y-term arises from evaluating the full three-component cross product, not from special-casing the `y` component

#### Scenario: A non-finite Fx or Fz breaks the M_y invariance

- **Given** a purely spanwise offset `(0, a, 0)` and a row whose `Fx` or `Fz` is NaN or infinite
- **When** the shift is applied
- **Then** that row's `CF_my` is NaN, because the zero-valued coefficient multiplies a non-finite force (`0.0 · NaN = NaN`), and the shift SHALL NOT special-case the term to preserve invariance
- **And** the invariance is conditional on `Fx` and `Fz` specifically, **not** on the forces generally: only those two enter `cross_y = d_z·F_x − d_x·F_z`, so a non-finite `F_y` leaves `CF_my` exactly invariant while contaminating `CF_mx` and `CF_mz`
- **And** no single non-finite force component contaminates all three outputs — each contaminates exactly two

#### Scenario: Committed corpora reconcile against their declared offset

- **Given** a committed `dataset.parquet` and the origin-to-hinge offset `(0, a, 0)` recorded in its dataset-build provenance
- **When** the derived coefficients are recomputed from the parquet's own raw `Fx..Mz` columns
- **Then** `CF_mx == (Mx + a·Fz)/m_ref` and `CF_mz == (Mz − a·Fx)/m_ref` to `rtol=1e-9`, and `CF_my == My/m_ref`
- **And** `CF_mx` is **not** `allclose` to `Mx/m_ref`, so the check cannot be vacuously satisfied by a zero offset and a re-extraction that dropped the shift fails loudly

### Requirement: The moment origin offset is derived per configuration and validated

The origin-to-hinge offset SHALL be **derived per configuration** — `r_origin` from the run's own
`X,Y,Z` CSV columns (IAMReX writes `kernel.location` there, which is the origin its moments are
taken about) and `r_hinge` from the configuration's deck (`particle_inputs.hinge_{x,y,z}`) — and
SHALL NOT be hardcoded, so a deck whose particle origin and hinge differ from the committed
corpora is handled correctly rather than silently mis-shifted.

`X`, `Y` and `Z` SHALL become required IB-particle CSV columns. The deck SHALL be located via the
configuration's existing manifest `input_file` entry, resolved relative to the manifest's own
directory; the hinge SHALL be read with the existing ParmParse-aware deck reader rather than a
second parser.

#### Scenario: Offset is derived, not hardcoded

- **Given** a configuration whose particle origin and hinge differ by an offset other than `(0, 1.5, 0)` — for example a deck with `hinge_z` displaced as well
- **When** the dataset is extracted
- **Then** the shift applied is that configuration's own `r_origin − r_hinge`, not the value that happens to hold for the committed corpora

#### Scenario: The offset is derived independently for each configuration

- **Given** a two-configuration manifest whose decks declare **different** hinges, mapped to identical CSVs
- **When** the dataset is extracted
- **Then** the two configurations emit correspondingly different `CF_mx`, proving the offset is derived per configuration rather than derived once and reused

#### Scenario: A moving moment origin is rejected rather than shifted

- **Given** a run whose `X,Y,Z` columns are **not** constant across timesteps under exact equality (the immersed-boundary particle moved, so a single constant offset cannot describe the run)
- **When** the dataset is extracted
- **Then** extraction raises `ValueError` naming the configuration, rather than applying a constant shift that would be silently wrong for every row
- **And** any variation is rejected, however small — the guard is exact equality, not a tolerance

#### Scenario: A NaN moment origin is rejected

- **Given** a run whose `X,Y,Z` columns are NaN
- **When** the dataset is extracted
- **Then** extraction raises `ValueError` naming the configuration, rather than deriving a NaN offset that would silently NaN every moment coefficient

#### Scenario: A CSV lacking the origin columns is rejected

- **Given** an IB-particle CSV with no `X`, `Y` or `Z` column
- **When** the dataset is extracted
- **Then** it raises `ValueError` naming the configuration and the absent columns, via the existing required-column check

#### Scenario: A header-only CSV contributes no rows without tripping the origin guard

- **Given** a configuration whose IB-particle CSV has the header but **zero** data rows
- **When** the dataset is extracted
- **Then** that configuration contributes zero rows without the constant-origin guard raising on the empty array

#### Scenario: A deck without a declared hinge is rejected

- **Given** a deck that declares no `particle_inputs.hinge_{x,y,z}`, or a non-finite hinge value
- **When** the dataset is extracted
- **Then** extraction raises `ValueError` naming **both** the configuration and the deck path, rather than falling back to the particle origin, which would silently reinstate mid-span moments

#### Scenario: A configuration with no locatable deck is rejected

- **Given** a manifest configuration with no `input_file` entry, or whose declared deck path does not exist on disk
- **When** the dataset is extracted
- **Then** it raises `ValueError` naming the configuration and the resolved path — never a bare `TypeError` from a missing argument, and never a silent emission of particle-origin moments

### Requirement: Parallel-axis shift helper

The force-surrogate module SHALL expose a pure `shift_moment_reference` helper that applies a
parallel-axis shift to moment components given the corresponding forces and a displacement. It
SHALL be a pure array function (no I/O, no hardcoded geometry), so the reference-frame change is
unit-testable independently of extraction.

#### Scenario: Known-answer parallel-axis shift

- **Given** hand-computed moments `M`, forces `F` and a displacement `d` with a known analytic result
- **When** `shift_moment_reference` is called
- **Then** it returns `M + d × F` exactly, pinning both the cross-product order and the sign convention

#### Scenario: Degenerate shift inputs

- **Given** an empty moment/force array, mismatched `M`/`F` shapes, or a zero displacement
- **When** `shift_moment_reference` is called
- **Then** an empty input yields empty outputs without error; mismatched shapes raise `ValueError`; and a zero displacement leaves all-finite inputs comparing equal (`==`, accepting `-0.0 == 0.0`)
- **And** the shape check SHALL reject a mismatch **within** the moment triple or **within** the force triple, not merely between the two groups — an intra-group mismatch is the broadcasting hazard that would pair a force with the wrong moment row

#### Scenario: Non-finite moments propagate unmasked

- **Given** a moment component that is NaN or infinite, with finite forces and a finite offset
- **When** `shift_moment_reference` is called
- **Then** that component's output is non-finite — the helper SHALL NOT mask, zero or `nan_to_num` its inputs, so a corrupt upstream value stays visible rather than being silently repaired

#### Scenario: A malformed offset is rejected

- **Given** an `offset` that is not exactly three components — including a `(3,1)` or `(1,3)` array, a two- or four-element sequence, or a scalar — or one containing NaN or infinity
- **When** `shift_moment_reference` is called
- **Then** it raises `ValueError` naming the problem, rather than broadcasting a wrongly-shaped displacement or silently producing all-NaN moments
- **And** the check is on the **shape**, not merely the element count, so a `(3,1)` array is rejected rather than reshaped

## MODIFIED Requirements

### Requirement: Single-source moment normalization

The force-surrogate module SHALL be the single, parameterized source for aerodynamic **moment**
normalization and moment-coefficient computation, sibling to the published force normalization. The
reference moment SHALL be `M_ref = q_ref · area · L` with the moment length scale **`L = chord`**,
where `q_ref` and `area` are computed by the **same formulas** as the force reference (no second
copy; `q_ref = ½·ρ·u_ref²` at the radius of gyration). It SHALL be a pure function of its kinematic and
geometric inputs (no hardcoded amplitude/frequency, no I/O), SHALL reproduce the validated reference
value, and SHALL NOT be re-derived inline by any other module.

The module SHALL name the **reference point** its moments are taken about — the wing hinge — by
cross-referencing the canonical definition in `docs/coordinate-convention.md` rather than
restating its justification or citation. It SHALL NOT describe the reference point as "the body
center", and SHALL NOT claim the moments are in van Veen's wing frame: they are lab-frame
components about the hinge origin.

Reference-frame changes SHALL be applied to the raw moments **before** normalization; the
coefficient helpers normalize a moment that is already in the intended frame. (This constrains
the pipeline order, not the module a shift helper lives in.)

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

#### Scenario: Reference point is named, not implied

- **Given** the `MomentCoefficients` documentation
- **When** it is read
- **Then** it names the wing hinge as the reference point, points at `docs/coordinate-convention.md` for the definition, and does not describe the moments as "about the body center"
- **And** it states that the axes remain lab axes, so a reader cannot conclude the moments are van Veen wing-frame moments

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
the convention — including the hinge moment reference point. The build SHALL return both the
dataframe and the list of any configurations dropped
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
- **Then** each `CF_x` equals `Fx / compute_force_reference(f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO).f_ref` and each `CF_mx` equals `(Mx + (r_origin − r_hinge) × F)_x / compute_moment_reference(...).m_ref` (and likewise for y/z) — **ratio** equality, not round literals (the validated `f_ref ≈ 200.27` is not round, so `CF_x = 50/200.27 ≈ 0.250`, etc.), confirming the extractor reuses the helpers rather than re-deriving a reference inline (CC-3)
- **And** for a fixture whose deck hinge coincides with the particle origin the shift is zero and the moment ratio reduces to `Mx / m_ref`, so the pre-existing round-number relationship is preserved for the degenerate case
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

### Requirement: Dataset build provenance

The dataset build SHALL capture run provenance via the PR1 `capture_surrogate_run_metadata` helper,
requiring a pinned container **digest** (the dataset is downstream of the container CFD run) and a
**caller-supplied** timestamp, and SHALL record any configurations dropped under `allow_missing` so a
truncated corpus is auditable.

The provenance SHALL additionally record the **moment reference point** and the per-configuration
origin-to-hinge offset applied, so the frame travels with the corpus and the correction is
re-derivable from the committed parquet alone. This is provenance, not a unit declaration, and
SHALL NOT be added to `dataset.units.json`, whose closed vocabulary admits only unit strings.

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
- **And** `dataset.units.json` is unchanged in shape — still a flat column-to-unit map over exactly the measured columns

#### Scenario: Re-extraction preserves the CFD digest

- **Given** a committed corpus whose provenance records the digest of the image its CFD ran under
- **When** the corpus is re-extracted from the same raw outputs without re-running the CFD
- **Then** the regenerated provenance records the **same** digest, not the digest of any image used to perform the re-extraction

### Requirement: Headline moment axis is CF_my, named as a component

The evidence figure SHALL designate **CF_my** as the single headline moment coefficient and SHALL
label its panel as an **"aerodynamic moment (M_y component)"** — it SHALL NOT label the panel
"pitch moment". The figure caption SHALL note that the repository's axis convention differs from the
biomechanics standard (GitHub issue #1) and therefore the panel reports the moment *component* rather
than a biomechanical pitch interpretation; the figure SHALL NOT apply an unverified
sim→biomechanics axis relabeling.

The panel set SHALL be **fixed a priori** rather than re-derived per corpus, so the figure cannot
cherry-pick whichever moment axis scores best. The requirement SHALL NOT assert which moment
carries the most between-configuration signal: that ranking is corpus-dependent and has already
inverted more than once. Instead the caption SHALL disclose the actual off-panel `CF_mx`/`CF_mz`
config-resolved R² at call time, so a reader can see the ranking rather than be told it.

#### Scenario: Moment panel is CF_my labeled as a component, not "pitch moment"

- **Given** the evidence figure
- **When** the moment panel is rendered
- **Then** the panel uses the `CF_my` coefficient, its title/label contains "M_y" and the word "moment" but NOT the string "pitch moment", and the figure caption text references the issue-#1 axis-convention caveat

#### Scenario: The off-panel moments are disclosed, not ranked in the spec

- **Given** the metrics.json config-resolved block, whatever this corpus's moment ranking happens to be
- **When** the figure is built
- **Then** the headline moment coefficient is `CF_my`, and **no** axis plots a `CF_mx_*` or `CF_mz_*` column at all
- **And** the caption states the off-panel `CF_mx` and `CF_mz` config-resolved R² values read from `metrics.json`, so a corpus in which an off-panel moment outscores the headline is visible to the reader rather than hidden by the frozen panel set

### Requirement: Force-only dataset scope guard

The dataset extractor SHALL derive all forces and moments from the IB-particle CSV alone and SHALL
NOT read AMReX plotfiles or velocity/pressure fields (CC-6). The force-only path keeps the dataset
build cluster-free and sidesteps the velocity-field-in-plotfiles issue entirely.

The per-configuration **deck** named by the manifest's `input_file` entry is an additional
permitted input, read solely for its declared moment reference point (`particle_inputs.hinge_*`
and `particle_inputs.{x,y,z}`). Decks are committed text files, so this preserves the cluster-free
property; it does not relax the plotfile/field prohibition.

#### Scenario: Extraction consumes only the CSV, manifest and decks

- **Given** the dataset-build inputs
- **When** `build_dataset` is called
- **Then** it requires only the IB-particle CSV(s), `sweep_manifest.json`, and the per-configuration decks that manifest's `input_file` entries name — it neither accepts nor requires a plotfile/field path — and runs with no cluster, GPU, or AMReX plotfile present

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
**not** validated aerodynamics, and that the two off-axis moments **CF_mx/CF_mz are excluded from the
panels, with their actual config-resolved R² read from `metrics.json` and stated** — the exclusion is
stated with its numbers, not silent, and SHALL NOT assert a fixed reason such as a particular
within-beat waveform fraction, because that ranking is corpus-dependent and has already inverted
more than once. The figure SHALL annotate the inference-vs-CFD speedup as a **batched
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

> Note: the result numbers embedded above (CF_y −3.61, R²≈0.98, ~310×, N=12,535) are stale against
> the current committed artifacts and are tracked separately in issue #115. They are reproduced here
> verbatim because this change modifies only the `CF_mx`/`CF_mz` exclusion clause; refreshing them is
> deliberately out of scope.

#### Scenario: Caption reports config-resolved skill and flags the inflated aggregate

- **Given** a metrics.json with `config_resolved.<c>.config_mean_r2` (CF_x 0.94, CF_z 0.83, CF_my 0.99, CF_y −3.61) and an aggregate R²≈0.98
- **When** the caption is built
- **Then** it contains the per-axis config-resolved R² for CF_x/CF_z/CF_my (each read from `config_resolved.<c>.config_mean_r2`), explicitly states the aggregate overstates skill because it is dominated by the shared phase waveform, names the negative CF_y config-resolved R², states that CF_mx/CF_mz are excluded from the panels **and gives their config-resolved R² as read from metrics.json**, and frames the figure as coarse-grid pipeline readiness rather than validated aerodynamics — with every number read from metrics.json

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
- **Then** the on-figure caption leads with the positive headline (per-axis config-resolved R²/RMSE + the >1,000× batched speedup), carries a single terse "Caveats:" line and a single terse quasi-steady-reference line, and points to the README; **and** the README contains the full disclosure set (the issue-#1 axis caveat, the CF_mx/CF_mz exclusion **with their config-resolved R²**, the quasi-steady reference's omitted-terms / symmetric-rotation / stroke-plane-normal-vs-lab-z / uncalibrated nature and why it is not overlaid, the coarse-grid / not-validated framing, and the speedup batch-size + sequential-CFD decomposition) — so the full honesty content is present and test-enforced off the PNG

### Requirement: Re-normalization preserves surrogate skill (scale-invariance)

Re-deriving force/moment coefficients under a different per-configuration normalization-scale convention SHALL rescale the CFD targets and the surrogate predictions by the **same** constant,
leaving the held-out **R²** and the predicted-vs-CFD relationship invariant. The frozen corpus's raw
force/moment columns and IB-particle CSVs SHALL NOT be regenerated for a re-normalization convention
change; only derived coefficients change, and no surrogate retraining SHALL be required for that case.

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

#### Scenario: A reference-point change is not scale-invariant and does require a retrain

- **Given** the moment reference point moves from the particle origin to the wing hinge, so `CF_mx`/`CF_mz` are re-derived via a parallel-axis shift while the raw `Mx/My/Mz` columns stay frozen
- **When** the corrected corpus is compared with the committed one
- **Then** the new `CF_mx` column is **not** the old one times any constant (`CF_mx_new / CF_mx_old` is not constant across rows), so the R²-invariance argument does not apply and the committed `metrics.json` SHALL NOT be reused
- **And** the surrogate is retrained, because the model is a single shared-trunk multi-output network whose remaining targets' predictions also move
- **And** the raw `Fx..Mz` columns remain exactly equal to the committed corpus, so the frozen-raw-corpus guarantee itself is not breached
