## MODIFIED Requirements

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


#### Scenario: An inlet that is not strictly upstream is rejected before any plotfile is read

- **GIVEN** `sphere_cv_drag_cd` or `sphere_cv_steadiness_fraction` called with `x_inlet` equal to
  `x_outlet`, greater than it, or `NaN` in either
- **WHEN** the function is invoked with the Eulerian-box reader replaced by a function that fails the
  test if called
- **THEN** it raises `ValueError` saying `x_inlet` must be strictly upstream of `x_outlet` and showing
  both values, and the reader was never called; the guard is the test `not (x_inlet < x_outlet)`, so a
  `NaN`, which compares false both ways, cannot pass it
