## MODIFIED Requirements

### Requirement: Math and Physics Review Checklist

Subagent 6's prompt template SHALL name `openspec/specs/coordinate-convention/spec.md` and
`openspec/specs/force-surrogate/spec.md` as the normative authority (including the definition
`ω_peak = 2π·f_star·radians(phi_amp_deg)` for F_ref) and `docs/coordinate-convention.md` as
narrative only (without describing the page as using `ω` for two quantities); SHALL tell the reviewer to confirm the code implements what those pages say, and to
flag, not resolve, disagreement between the proposal, the pages, the code and the source paper. It
SHALL tell the reviewer to recompute every constant, reference point, sign, timestep or seed count
the proposal relies on from its source and report each as `VERIFIED / CONTRADICTED / UNVERIFIABLE`,
and SHALL receive the current specs being modified. Within the prompt template, a list starting
with `**Failure classes:**` SHALL name: sign and frame conventions (there is no insect-body frame;
the flapping-wing body-frame family (`CF_chord`/`CF_normal` and the diagnostics built on them) is
wing-frame; the corpus and surrogate `CF_x..CF_z`, the flapping-wing lab-frame series and the
moments are lab-frame components), reference points and
normalization, units (deg vs rad), CFL-limited timestep (the realized dt), domain size and boundary
conditions, time window and sampling, worst case rather than first case validation, variance across
at least 5 seeds, known-answer tests, and like-for-like comparisons.

#### Scenario: Authority and method are stated

- **WHEN** Subagent 6's prompt template (its `> ` lines) is read
- **THEN** it contains `openspec/specs/coordinate-convention/spec.md`,
  `openspec/specs/force-surrogate/spec.md`, `radians(phi_amp_deg)`,
  `docs/coordinate-convention.md`, `narrative only`, `confirm the code implements`, `flag, do not resolve`,
  `recompute every constant`, `VERIFIED / CONTRADICTED / UNVERIFIABLE`, `{DESIGN_MD}` and
  `{CURRENT_SPECS}`
- **AND** it does not contain `uses ω for two quantities`

#### Scenario: Failure-class list covers each past failure class

- **WHEN** the `**Failure classes:**` list in Subagent 6's prompt template is read
- **THEN** it contains `sign and frame`, `no insect-body frame`, `CF_chord`, `CF_x..CF_z`,
  `flapping-wing lab-frame series`, `lab-frame components`, `reference point` (stem),
  `normaliz` (stem), `units`, `deg vs rad`, `CFL`, `realized dt`, `boundary conditions`,
  `time window`, `worst case`, `5 seeds`, `known-answer` and `like-for-like`
- **AND** deleting any one list item fails the test even though the authority sentence also
  mentions reference point, sign and normalization
- **AND** it contains none of `forces are in the wing frame`, `forces in the wing frame` and
  `By design, forces`
