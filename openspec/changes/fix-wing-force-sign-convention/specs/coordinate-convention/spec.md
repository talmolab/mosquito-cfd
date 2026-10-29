## ADDED Requirements

### Requirement: The canonical convention page states the force and moment sign

`docs/coordinate-convention.md` SHALL carry exactly one `## Force and moment sign` section (anchor
`#force-and-moment-sign`), a sibling of `## Forces` and `## Moments`. It SHALL state:

- that IAMReX's `ib_force` / `ib_moment` (the IB-particle CSV's `Fx..Mz`) are the force and moment the
  wing exerts on the fluid;
- that every derived wing coefficient is the IB force or moment **on the wing**, their negation by
  Newton's third law. This covers the lab-frame `CF_x..CF_z`, the moment coefficients `CF_mx..CF_mz`
  about the hinge, the flapping-wing lab-frame series, the body-frame `CF_chord`/`CF_normal`, and the
  T4 CFD series;
- that no corpus coefficient includes the internal-fluid term `ρ_f·SumU`. The solver's free-body 6-DOF
  balance would add that term, but the solver never evaluates the balance for the prescribed-motion
  wing. For the zero-thickness wing the term is fluid momentum within about one grid cell of the sheet,
  so it depends on the grid, and its physical status is an open follow-up question;
- that the sphere and heaving-ellipsoid paths already report the force on the body;
- the name of the physics regression test that pins the convention.

It SHALL link the page's existing raw-vs-derived paragraph rather than repeat it. The section SHALL be
the only place that carries the **work-inequality evidence**, identified by the strings
`work from rest`, `work-from-rest` and `M_hinge · Ω`. The search set is every `*.md` under `docs/`,
`examples/` and the repository root, plus every docstring under `src/`. Exempt from the search:
`openspec/**`, `tests/**`, `docs/CHANGELOG.md` and the section itself.

A fixed list of documents SHALL link the section. Each link lands in the PR named, and the guard's list
grows in the same commit as the link:

| Document | PR |
|---|---|
| the `ForceCoefficients` / `MomentCoefficients` docstrings | PR1 |
| the `force_on_wing` docstring | PR1 |
| the `flapping_wing.py` module docstring | PR1 |
| `examples/flapping_wing/RESULTS.md` | PR2a |
| `examples/flapping_wing/figures/README.md` | PR2a |
| `docs/aerodynamics_validation/roadmap.md` | PR2a |
| both corpus READMEs | PR2b |
| `docs/force_surrogate/roadmap.md` | PR2b |
| `docs/field_surrogate/roadmap.md` | PR3 |

Docstrings SHALL NOT carry interim status. The section carries every pending phrase. Each phrase is the
exact literal below, occurs at most once, and is governed by a guard:

- **corpus phrase** — `Pending #109: the committed corpus coefficients still carry the solver's on-fluid sign.`
  Present iff the committed coarse `CF_x` is not `allclose` to `−Fx/f_ref` (tied to the data).
- **flapping-wing phrase** — `Pending #109: the flapping-wing series still carry the solver's on-fluid sign.`
  Present iff `reconstruct_wing_forces(forces_t2a_newconv.csv).cf_x_ib` is not `allclose` to
  `−Fx/f_ref`. This is tied to the **code path**, not the data: negating the CSV negates both sides.
- **surrogate phrase** — `Pending #109: the committed surrogates still predict the solver's on-fluid sign; negate their outputs.`
  Present iff both corpus READMEs carry the staleness banner.

#### Scenario: The section exists once and states the convention

- **Given** `docs/coordinate-convention.md`
- **When** its sections are read
- **Then** exactly one `## Force and moment sign` section exists, its slug is `force-and-moment-sign`, it names `ib_force`/`ib_moment` as on the fluid and the coefficients as the IB force on the wing, it notes the internal-fluid term, it names the oracle test, and it links the raw-vs-derived paragraph

#### Scenario: The listed documents link the section; the evidence lives only there

- **Given** the documents whose link has landed by the current PR, and the search set above
- **When** they are read
- **Then** each listed document contains `coordinate-convention.md#force-and-moment-sign`, and no file in the search set outside the section contains `work from rest`, `work-from-rest` or `M_hinge · Ω`

#### Scenario: Each pending phrase tracks its condition

- **Given** the committed coarse `dataset.parquet`, the committed `forces_t2a_newconv.csv`, both corpus READMEs and the canonical section
- **When** the guard evaluates each phrase's condition
- **Then** each pinned literal occurs exactly once if its condition holds and not at all otherwise. So the section can neither claim the on-wing sign for a path before that path carries it, nor keep a pending phrase after it does.
- **And** each direction is exercised by a test:
  - **corpus:** a parquet copy with only the `CF_*` columns negated;
  - **flapping-wing:** `force_on_wing` monkeypatched at the `flapping_wing` use site, identity against negation;
  - **surrogate:** README copies with and without the banner.
