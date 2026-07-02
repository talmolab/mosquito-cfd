# force-extraction (delta)

## ADDED Requirements

### Requirement: Axis-general control-volume force vector with an explicit freestream axis

The control-volume force core SHALL accept the streamwise/freestream axis **explicitly** and return the
full `(Fx, Fy, Fz)` momentum-flux force vector, rather than assuming the streamwise axis is `+x`. The
existing sphere entry point (`sphere_cv_drag_cd` / `cd_from_drag`) SHALL retain its current `+x`-default
behavior and keys (backward compatible), delegating to the generalized core. This exists so the wing
under the new convention — whose relevant force axis differs from the sphere's, and which has no single
freestream — can be analyzed without re-introducing a #1-style axis mislabel in the analysis layer.

#### Scenario: Explicit axis reproduces the x-only answer

- **GIVEN** a synthetic Eulerian box and the generalized core invoked with streamwise axis `= +x`
- **WHEN** the control-volume force is computed
- **THEN** the returned `Fx` equals the current `sphere_cv_drag_cd` drag for that box to round-off, and
  the full `(Fx,Fy,Fz)` vector is returned (backward-compatible for the sphere entry point)

#### Scenario: A non-x streamwise axis is honored

- **GIVEN** the same synthetic box but the streamwise axis supplied as `+y` (or `+z`)
- **WHEN** the control-volume force is computed
- **THEN** the momentum balance is taken across planes normal to the supplied axis and the returned
  force vector equals a hand-rolled balance across planes normal to that axis — the analysis never
  hard-codes `+x`

#### Scenario: A malformed streamwise axis raises

- **GIVEN** a streamwise axis that is a zero vector, a non-unit vector, or not a 3-vector
- **WHEN** the generalized core is invoked
- **THEN** a clear error is raised (matching the existing "Non-finite field raises" robustness bar),
  rather than a silently mis-projected or NaN force vector

### Requirement: Rotation-equivariance invariance guard (orientation/labeling only)

The field-based force extractor SHALL be **rotation-equivariant**: for a rotation `Q` that
rotates/permutes the grid axes, the extracted force satisfies `F(Q·field) = Q·F(field)` to
floating-point round-off. This property SHALL be proven as a **cluster-free** test on synthetic fields
(and, where a plotfile is available, on the committed field rotated in memory) — the pure-rotation
control pair. It is the invariance instrument for the axis-convention change (**CC-V4: orientation and
labeling only**): it validates that the relabel/extraction is correct **without** comparing forces
across two physically different runs (never new-extractor-new-geom vs old-extractor-old-geom), and it
does **not** touch force-magnitude reconstruction (T1b/#36).

#### Scenario: Extractor is equivariant under a grid rotation

- **GIVEN** a synthetic Eulerian field whose force vector has **all three components non-zero** and an
  **off-diagonal** rotation `Q` (e.g. `(x,y,z)→(y,−x,z)`, not a pure axis-relabel that could cancel a
  latent sign error)
- **WHEN** the force is extracted from the field and, separately, from `Q·field` with the axis mapping rotated by `Q`
- **THEN** `F(Q·field)` equals `Q·F(field)` to round-off, confirming the extractor is a correct
  relabeling under rotation (a dropped or swapped component would be detectable)

#### Scenario: The guard does not compare across geometries

- **GIVEN** the invariance test
- **WHEN** it is run
- **THEN** both sides use the **same** extractor on the **same** physical field (one rotated), never a
  different extractor on a different geometry — so the guard measures labeling correctness only, kept
  strictly separate from the magnitude fixes (CC-V4)
