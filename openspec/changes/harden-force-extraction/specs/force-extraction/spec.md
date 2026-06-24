# Force Extraction Specification (delta)

## ADDED Requirements

### Requirement: Robust input validation for the control-volume tools

The control-volume tools SHALL validate their inputs and fail loud rather than emit non-finite or
sign-flipped results. The unsteady-momentum term SHALL reject a non-positive time step, and the
field-based sphere Cd entry point SHALL not require IB-marker fields when run in control-volume mode.

#### Scenario: Non-positive time step raises

- **GIVEN** the unsteady-momentum term with `dt <= 0`
- **WHEN** it is evaluated
- **THEN** a clear error is raised, rather than dividing to `inf`/`nan`

#### Scenario: CV mode tolerates a field-only plotfile

- **GIVEN** a plotfile with no IB-marker particle fields and `extract_sphere_cd(method="cv")`
- **WHEN** the drag coefficient is extracted
- **THEN** the control-volume `cd` is returned, the legacy marker diagnostic `cd_marker_lastpass` is
  `None` (computed best-effort), and no error is raised
- **AND** with `method="marker"` (the default) a missing-particle plotfile still raises, because the
  marker sum *is* that method

### Requirement: Cluster-free verifiability of the plotfile-to-drag wiring

The sphere control-volume drag entry point SHALL compose the Eulerian-field adapter and the numeric
core deterministically, so that — given a known gridded Eulerian box — the resulting drag coefficient
is a known closed-form value. This makes the adapter→core wiring (plane selection, the pressure-gradient
slice, the cell area/thickness weighting, and the Cd conversion) verifiable without cluster data, by
substituting a synthetic box for the plotfile read.

#### Scenario: Known synthetic box yields the closed-form Cd

- **GIVEN** a synthetic Eulerian box (uniform inlet plane, uniformly slowed outlet plane, constant
  pressure gradient) substituted for the plotfile read
- **WHEN** `sphere_cv_drag_cd` is invoked for inlet/outlet planes within that box
- **THEN** the returned `cd` equals the closed-form periodic-duct drag coefficient for that box to
  round-off, confirming the wiring selects the correct planes, slices `gradpx` between them, and applies
  the correct `dy*dz` and `dx` weights — all without reading a plotfile
