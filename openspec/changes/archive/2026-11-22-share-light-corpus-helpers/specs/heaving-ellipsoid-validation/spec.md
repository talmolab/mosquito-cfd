## MODIFIED Requirements

### Requirement: Ellipsoid re-run captures pinned, verifiable provenance (CC-V3)

The heaving-ellipsoid re-run SHALL capture a `run_metadata_t2b.json` via the force-surrogate provenance
helper `capture_surrogate_run_metadata`, requiring a digest-pinned container **reference**
(`<repo>@sha256:<64 hex>`, as accepted by `validate_image_digest`; a bare `sha256:` digest is refused), a
**caller-supplied** ISO-8601 timestamp, the inputs hash of `inputs.3d.heaving_ellipsoid`, and the pinned
**IAMReX commit `f93dc794`** recorded via `extra={"iamrex_commit": ...}`. The re-run SHALL reuse the
committed deck **byte-unchanged** (the ellipsoid is a symmetric translating body, unaffected by the
`WingKinematics.H` motion refactor — like the sphere, it is convention-agnostic), and a test SHALL
**verify** that byte-invariance by asserting the recorded `inputs.hash` equals `hash_file` of the committed
deck (so a silently-edited deck is caught, not merely claimed).

#### Scenario: Provenance records the pinned digest, commit, inputs hash, and supplied timestamp

- **Given** the `:fp64` image's digest-pinned reference (`ghcr.io/talmolab/mosquito-cfd@sha256:<64 hex>`), a caller-supplied timestamp, and the
  committed `inputs.3d.heaving_ellipsoid`
- **When** `capture_surrogate_run_metadata` is called for the ellipsoid re-run
- **Then** `run_metadata_t2b.json` records the digest under `docker_image`, the timestamp verbatim, the
  inputs hash, and `iamrex_commit` (a **top-level** key, since `extra` is merged last) starting with
  `f93dc794`, and a mutable tag (no `sha256:`) or a bare `sha256:<64 hex>` digest raises `ValueError`
  via `validate_image_digest`

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

