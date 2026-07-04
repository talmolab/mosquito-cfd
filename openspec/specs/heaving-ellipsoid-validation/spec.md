# heaving-ellipsoid-validation Specification

## Purpose
TBD - created by archiving change revalidate-benchmarks-literature. Update Purpose after archive.
## Requirements
### Requirement: Heaving-ellipsoid self-consistency over the steady window

The heaving-ellipsoid validation SHALL grade **self-consistency** (not a literature Cd point) from the
committed re-run IB-particle CSV: within a **pinned steady window `t ≥ 7`**, the relative change of the
**streamwise-drag force `Fx`** and the **heave-direction lift force `Fy`** (the heave is prescribed in
`+y`) SHALL be **below 1%** by a **named criterion** (the maximum consecutive-sample relative change over
the window, `SELF_CONSISTENCY_TOL = 0.01`). The **spanwise `Fz` is ~0 by symmetry** (identically `0.000`
in the committed coarse series) and SHALL **not** be graded (to avoid a degenerate `0/0` relative change) —
though a test SHALL confirm the re-run's `Fy` heave channel is **non-zero** so the lift-side gate is not
itself degenerate. The criterion SHALL be measured on the finer re-run series — **not** assumed from the
coarse committed `forces.csv` (whose 1.0-unit sampling shows a ~1.05% drift over `t=7→10` and cannot
resolve the gate). The window and threshold SHALL be named constants, not loosened to pass; the grader's
**numerics SHALL be exercised cluster-free** on a synthetic fixture so CI grades the logic before the
operator re-run lands.

#### Scenario: Steady-window force change is below the pinned threshold

- **Given** an IB force series (the committed re-run CSV, or a synthetic fixture) with fine-resolution
  samples over `t ≥ 7`
- **When** the maximum consecutive-sample relative change of the drag and lift force is computed over the
  steady window
- **Then** it is **< 1%** (`SELF_CONSISTENCY_TOL`), and the window `t ≥ 7` and threshold are pinned
  constants, not chosen post-hoc

#### Scenario: The gate fails above the threshold (can fail, not only pass)

- **Given** a synthetic fine-resolution series whose maximum consecutive relative change over `t ≥ 7` is
  e.g. `1.5%`
- **When** the self-consistency grade is computed
- **Then** it **fails** the `SELF_CONSISTENCY_TOL = 0.01` gate, and widening the threshold to pass fails a
  not-loosened guard — the self-consistency gate is load-bearing, symmetric with the band floor

#### Scenario: Coarse committed series is handled deterministically, not spoofed

- **Given** only the pre-existing 11-point `forces.csv` (1.0-unit sampling)
- **When** the self-consistency grader is asked to grade it
- **Then** it **declines with a clear error** (too few samples inside `t ≥ 7` to resolve a
  consecutive-sample change) — a single deterministic branch, not "either declines or reports" — so a
  coarse series can never be mistaken for a passing fine series

### Requirement: Heaving-ellipsoid added-mass-fraction sanity (reported, not matched)

The heaving-ellipsoid validation SHALL compute the immersed-boundary **added-mass** term from the re-run's
`SumU*` columns using the **same `WriteIBForceAndMoment` algebra as the wing** (`added_mass = ρ_f·SumU`,
reusing `added_mass_force`), and report its fraction of `ib_force`. Because the heave is **constant
velocity**, the grader SHALL assert the fraction is a **bounded, physical value** (`0 ≤ fraction < 1`) that
**decays after the impulsive start** toward the steady window (acceleration ≈ 0 ⇒ near-zero *steady* added
mass); this decay logic SHALL be exercised **cluster-free** on a synthetic fixture shaped to it. The
fraction SHALL be **reported against van Veen's 15% lift / 31% drag** ballpark as an **order-of-magnitude
sanity**, with that ballpark **cited to the roadmap oracle row (which cites van Veen 2022)** rather
than restated free-floating — it SHALL **NOT** be graded as a tight match (van Veen's numbers are for an
*accelerating* wing; the ellipsoid's steady share is expected *below* them, and asserting a match would
invent an oracle with no number, violating CC-V2).

#### Scenario: Added-mass fraction is bounded and decays after the impulsive start

- **Given** an IB series with `SumU*` columns (the committed re-run CSV, or a synthetic fixture shaped so
  the fraction is largest at `t≈0` and decays past `t=7`)
- **When** `added_mass = ρ_f·SumU` and its fraction of `ib_force` are computed over the run
- **Then** the fraction is bounded `0 ≤ fraction < 1`, is largest near the impulsive start, and **decays**
  toward the steady window — the physical signature of a constant-velocity heave (unsteady added mass is
  an acceleration effect) — and this is asserted cluster-free on the synthetic fixture

#### Scenario: Van Veen 15%/31% is a reported, cited sanity ballpark, not a graded match

- **Given** the computed ellipsoid added-mass fraction and van Veen's 15% lift / 31% drag wing values
- **When** the comparison is reported
- **Then** the ellipsoid fraction is presented **against** the van Veen ballpark (cited to its single
  source, not restated as a free number) as an order-of-magnitude sanity (expected at/below the wing
  values), and **no** test asserts a tight numeric match — the reference-area Cd/CL likewise remain
  *reported, not graded*

#### Scenario: Added-mass formula is locked to the IAMReX source, not tuned

- **Given** a known row of the committed re-run CSV (or the synthetic fixture)
- **When** the added-mass force is computed
- **Then** it equals `ρ_f·SumU` on that row (the `WriteIBForceAndMoment` definition, shared with the
  wing via `added_mass_force`), with the formula citation in the test — the expression is **not** selected
  to make any sanity bound pass

### Requirement: Ellipsoid re-run captures pinned, verifiable provenance (CC-V3)

The heaving-ellipsoid re-run SHALL capture a `run_metadata_t2b.json` via the force-surrogate provenance
helper `capture_surrogate_run_metadata`, requiring a pinned container **digest** (containing `sha256:`), a
**caller-supplied** ISO-8601 timestamp, the inputs hash of `inputs.3d.heaving_ellipsoid`, and the pinned
**IAMReX commit `f93dc794`** recorded via `extra={"iamrex_commit": ...}`. The re-run SHALL reuse the
committed deck **byte-unchanged** (the ellipsoid is a symmetric translating body, unaffected by the
`WingKinematics.H` motion refactor — like the sphere, it is convention-agnostic), and a test SHALL
**verify** that byte-invariance by asserting the recorded `inputs.hash` equals `hash_file` of the committed
deck (so a silently-edited deck is caught, not merely claimed).

#### Scenario: Provenance records the pinned digest, commit, inputs hash, and supplied timestamp

- **Given** the `:fp64` image digest (containing `sha256:`), a caller-supplied timestamp, and the
  committed `inputs.3d.heaving_ellipsoid`
- **When** `capture_surrogate_run_metadata` is called for the ellipsoid re-run
- **Then** `run_metadata_t2b.json` records the digest under `docker_image`, the timestamp verbatim, the
  inputs hash, and `iamrex_commit` (a **top-level** key, since `extra` is merged last) starting with
  `f93dc794`, and a mutable tag (no `sha256:`) raises `ValueError` via `validate_image_digest`

#### Scenario: Deck byte-invariance is verified against the recorded hash

- **Given** the committed `run_metadata_t2b.json` and `inputs.3d.heaving_ellipsoid`
- **When** the provenance test runs
- **Then** `run_metadata_t2b.json["inputs"]["hash"]` equals `hash_file("examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid")`
  — the "deck byte-unchanged" claim is verified, not assumed

#### Scenario: Grader tests skip on the committed-artifact predicate, without erroring, until the re-run lands

- **Given** no committed `forces_t2b_ib.csv` (the operator re-run has not yet landed)
- **When** the ellipsoid self-consistency / added-mass / provenance tests are collected and run
- **Then** the CSV-dependent tests **skip** via a `skipif(not Path(".../forces_t2b_ib.csv").exists())`
  guard (the committed-file predicate, **not** the `MOSQUITO_CFD_PLOTFILE_ROOT` env marker, which gates
  plotfile-root tests only), the CSV is loaded **inside** the guarded test body (never at module import, so
  collection does not error), and the cluster-free synthetic-fixture numerics still run — the tier's sphere,
  flapping, and METHODS workstreams proceed independently of the cluster run

