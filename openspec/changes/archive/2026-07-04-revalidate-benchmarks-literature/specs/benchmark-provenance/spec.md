# benchmark-provenance (delta) — Tier T2b

## ADDED Requirements

### Requirement: METHODS.md IAMReX pin is consistent with the built image

The benchmark methodology document `benchmarks/METHODS.md` SHALL pin the **same IAMReX repository and
commit** as the image it describes: the **`talmolab/IAMReX` fork** at the commit recorded in
`docker/build-args.env` (currently `f93dc794`). A **cluster-free** test SHALL assert that the IAMReX commit
stated in METHODS.md is a **prefix of (or equal to)** the full 40-hex `IAMREX_COMMIT` in
`docker/build-args.env` — i.e. `build_pin.startswith(methods_pin)` with `len(methods_pin) >= 7` — so the
repo's conventional abbreviation (`f93dc794`) is accepted while a **different** commit fails. The METHODS
extractor SHALL match a 7-to-40-hex commit token in the software-stack row (independent of the existing
`test_iamrex_pin_consistent` 40-hex regex), so on the **current** stale document it extracts `c5f8e2a` and
the assertion fails with a genuine **mismatch** (`build_pin` does not start with `c5f8e2a`), not an
extraction error — a valid test-first red. The test is complementary to `test_iamrex_pin_consistent`
(which checks `build-args.env` ↔ `Dockerfile.fp64`), not a duplicate, and SHALL be written and passing
**before** METHODS.md is edited.

#### Scenario: METHODS.md commit is a prefix of the build-args pin

- **GIVEN** `benchmarks/METHODS.md` and `docker/build-args.env`
- **WHEN** the pin-consistency test extracts the IAMReX commit token from each
- **THEN** the `build-args.env` full 40-hex `IAMREX_COMMIT` **starts with** the METHODS.md commit token
  (`len >= 7`), a mismatch fails with a message naming both sources and both hash forms, and on the current
  stale document (`c5f8e2a`) the assertion produces a mismatch failure (not a collection/extraction error)

#### Scenario: The repository is the fork, not upstream, in the software-stack row

- **GIVEN** the METHODS.md software-stack row for IAMReX (the row that pins the built solver)
- **WHEN** it is read after reconciliation
- **THEN** that row names `https://github.com/talmolab/IAMReX` (the fork), **not** the upstream
  `ruohai0925/IAMReX`, and the stale `c5f8e2a` commit no longer appears anywhere in METHODS.md — both the
  **repo divergence** and the **hash skew** are reconciled (the separate upstream FP32 tracking link,
  `ruohai0925/IAMReX#59`, is a legitimate reference to an upstream *issue* and is retained with a note that
  the *fork* is what is built — it is not the solver-source pin)

#### Scenario: Stale build/Docker/extraction references are corrected alongside the pin

- **GIVEN** the METHODS.md provenance references — the non-existent `Dockerfile.iamrex` path, the sphere
  analysis example that calls `extract_sphere_cd` with the **default** (known-wrong) `method="marker"`, the
  ellipsoid run-command block, and the illustrative `run_metadata.json` example
- **WHEN** the pin reconciliation lands
- **THEN** the Dockerfile reference points to the real `docker/Dockerfile.fp64`; the analysis example
  **positively contains** `extract_sphere_cd(method="cv")` (the T1b-corrected path — the guard is a
  positive assertion, because the current bare-default `extract_sphere_cd('…')` call carries **no** literal
  `method="marker"` string, so a negative "marker absent" check would be vacuous); the ellipsoid
  run-command block matches the actual T2b re-run (consistent with `run_metadata_t2b.json`); the
  illustrative `run_metadata.json` block includes an `iamrex_commit` field and does not label a git commit
  as a `sha256`; the stale "discrepancy investigation" pointer (which the H1′ grade supersedes) is
  refreshed; and no METHODS.md provenance line contradicts the pinned `talmolab/IAMReX @ f93dc794` image —
  the content test asserts `c5f8e2a` and `Dockerfile.iamrex` are **absent** and the sphere example
  **positively contains** `method="cv"`
