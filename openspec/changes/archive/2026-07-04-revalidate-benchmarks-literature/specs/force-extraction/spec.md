# force-extraction (delta) — Tier T2b

## ADDED Requirements

### Requirement: Confinement-corrected sphere Cd literature grade (H1′)

The benchmarks package SHALL grade the control-volume sphere Cd against the literature point
**Cd = 1.087** (Johnson & Patel 1999) by correcting for the **transverse-array confinement offset** whose
provenance (pitch 10 D, 5 D upstream; estimated **+3–6%** above the isolated value) is already stated by
the existing "Literature validation classifies the extraction-vs-field hypothesis" requirement — this
requirement **sharpens** that classification into a graded literature verdict and does **not** restate or
re-own the offset provenance. Given a confined control-volume Cd (a single grid or the
Richardson-extrapolated value) and the offset band, the grader SHALL compute the **isolated-equivalent**
Cd bracket by **dividing** the confined Cd by `(1 + offset)` — i.e. `cd_confined / (1 + [0.03, 0.06])` —
and classify the outcome **H1′** (extraction resolved; residual explained by confinement) when that
bracket lies within a **pinned tolerance** of 1.087 (**±5%**, i.e. `[1.033, 1.141]`). The tolerance and the
offset band SHALL be **named constants**, stated up front and **not** loosened or fitted to make the grade
pass (CC-V2). The grader SHALL be **cluster-free** — it takes Cd *values* as inputs and does **not**
re-derive the extractor (CC-V4) — while a `requires_plotfile`-marked companion recomputes the Cd with
`extract_sphere_cd(method="cv")` on the committed `plt10000` where the plotfile root is available.

#### Scenario: Richardson-extrapolated Cd grades as H1′ within tolerance

- **GIVEN** the committed T1b Richardson-extrapolated control-volume Cd `1.131` and the stated
  confinement offset band `+3–6%`
- **WHEN** the confinement-corrected literature grade is computed
- **THEN** the isolated-equivalent bracket is `cd/(1+[0.03,0.06]) = [1.067, 1.098]`, that bracket lies
  within `±5%` of 1.087, and the verdict is **H1′** — computed without reading any plotfile or cluster path

#### Scenario: Tolerance and offset band are pinned and not loosened

- **GIVEN** the literature target `1.087`, the pinned tolerance `±5%`, and the pinned offset band `+3–6%`
  as named constants
- **WHEN** a test inspects them
- **THEN** widening the tolerance or the offset band to admit an out-of-range confined Cd **fails** a
  not-loosened guard test, and a confined Cd whose isolated-equivalent bracket falls outside `[1.033, 1.141]`
  is graded **not H1′** (the grader can fail, not only pass)

#### Scenario: Tolerance-edge boundary case is decided deterministically

- **GIVEN** a confined Cd whose isolated-equivalent bracket lands **exactly at** a tolerance edge (e.g. an
  endpoint equal to `1.141` or `1.033`)
- **WHEN** the grade is computed
- **THEN** the inclusive/exclusive edge behaviour is deterministic and documented (the boundary is decided
  one way, not left to floating-point luck), so "within ±5%" has a single unambiguous meaning

#### Scenario: Companion re-grade verifies CV extraction traceability (verdict stays on Richardson)

- **GIVEN** the committed sphere `plt10000` (medium grid) and `MOSQUITO_CFD_PLOTFILE_ROOT` set
- **WHEN** the `requires_plotfile` companion recomputes the control-volume Cd
- **THEN** it calls `extract_sphere_cd(method="cv", x_inlet=2.0, x_outlet=8.0)` (**not** the default
  `method="marker"`, which returns the known-wrong ~0.45), and the returned `cd` matches
  `sphere_cv_drag_cd(...)["cd"]` (≈1.18) — confirming the extractor reproduces the pinned per-grid CV
  number (traceability; the marker/CV confusion is guarded)
- **AND** the H1′ **verdict** is graded on the **Richardson-extrapolated** value `1.131` (which requires
  **both** grids), **not** on the single medium value: the medium `1.18` alone yields
  `1.18/(1+[0.03,0.06]) = [1.113, 1.146]`, whose upper edge exceeds the tolerance `1.141` and so grades
  **not H1′** — the companion therefore verifies *extraction*, while the *literature verdict* rests on the
  Richardson value from the cluster-free grade (a single grid cannot reproduce a two-grid extrapolation)

#### Scenario: Off-cluster run auto-skips the plotfile companion but still grades the pinned numbers

- **GIVEN** no `MOSQUITO_CFD_PLOTFILE_ROOT` (CI / off-cluster)
- **WHEN** the sphere T2b tests run
- **THEN** the `requires_plotfile` companion **auto-skips**, while the cluster-free H1′ grade on the pinned
  Richardson value 1.131 still runs and passes — the literature verdict is CI-gradeable without cluster data
