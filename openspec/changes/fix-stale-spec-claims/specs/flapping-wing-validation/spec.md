## MODIFIED Requirements

### Requirement: Stroke motion reproduces van Veen's translational sweep

The change SHALL verify — at the **kinematic** level, cluster-free — that the refactored wing kinematics
produce a **stroke that sweeps the span**. The new convention puts the span along body `y`, so the
stroke rotation `Rz(φ)` swings the span-tip through the stroke plane. The old convention put the
span along body `z`, so, with zero pitch, the same stroke rotation turned the wing about its own
span and left the span-tip where it was. The two conventions are compared on a span-tip marker at radius `r` **at
stroke reversal**. With `φ = φ_amp sin ωt` and `α = α_amp cos ωt`, stroke reversal is `t = T/4` or
`3T/4`, where `φ = ±φ_amp`, `φ̇ = 0` and the pitch is zero. Mid-stroke is `t = 0` or `T/2`, where
`φ = 0` and `|α| = α_amp`. The deviation `θ ∝ sin 2ωt` is zero at all four instants, so it does
not enter the comparison.

At reversal the new span-tip's lab `x` coordinate (in the stroke plane, perpendicular to the
mid-stroke span direction) has magnitude `r·sin φ_amp`, while the old span-tip's distance from its stroke
axis is `r·|sin α|`, which is zero there. The comparison is made at reversal because the pitch is
zero there, so the old span-tip's distance from its axis is `≈0` and the new span-tip's
`|x| = r·sin φ_amp` isolates the stroke sweep. At mid-stroke the pitch tilts the old span-tip off its
axis (distance `r·sin α_amp`) while the new span-tip, pitched about its own span, stays at
`(0, r, 0)`, so mid-stroke does not isolate the sweep. This encodes that the refactor is a **motion
correction** reproducing van Veen's translational sweep, not merely an axis relabel.

#### Scenario: New stroke sweeps the span-tip; old one does not

- **Given** the new and old conventions evaluated on a span-tip marker at stroke reversal (`t = T/4`: `φ = φ_amp`, zero pitch)
- **When** the new span-tip's lab `x` coordinate and the old span-tip's distance from its stroke axis are measured
- **Then** the **new** `|x|` equals `r·sin φ_amp`, consistent with a `±φ_amp` stroke arc,
  the **old** distance is `≈0` (`r·|sin α|` with zero pitch), and the test asserts the new stroke
  sweeps the span while the old one does not

#### Scenario: At mid-stroke the old span-tip is tilted off its axis

- **Given** the old composition at mid-stroke (`φ = 0`, `α = α_amp`) applied to the old span-tip `(0, 0, r)`, and the new composition applied to the new span-tip `(0, r, 0)`
- **When** both span-tip positions are computed
- **Then** the old one is exactly `(0, −r·sin α_amp, r·cos α_amp)`, at distance `r·sin α_amp` from its axis, and the new one is `(0, r, 0)`
- **And** the test asserts the full vectors, with the mid-stroke angles taken from the kinematics and a pitch amplitude at which `sin α_amp ≠ cos α_amp`: swapping the old and new rotation compositions leaves both scalar measures unchanged (new-tip `|x| = 0`, old-tip axis distance `r·sin α_amp`), so only the vectors detect the swap

#### Scenario: The kinematics tests name the instant they measure

- **Given** the kinematics tests that evaluate the Euler angles or the span-tip position at `t = T/4`
- **When** their names and docstrings are read
- **Then** they call that instant stroke reversal (or the stroke extreme), not mid-stroke, and the renamed Euler-angle test exists

## ADDED Requirements

### Requirement: Retired kinematics and T4 claims stay out of this specification

This specification's effective text SHALL be covered by the force-surrogate requirement
"Data-dependent claims in the live specs are guarded against committed data". The test module's
`RETIRED` list SHALL include the stroke-reversal instant described as mid-stroke, and, as
forward-only regression guards on text PR #168 already removed, the coarse CFD normal peak given as
T4's graded comparison value and the superseded T4 peak-phase gap. Coarse T2a values quoted in an
explicitly coarse context are not retired. The kinematics tests' names and docstrings SHALL likewise
not describe stroke reversal as mid-stroke.

#### Scenario: Stroke reversal is not called mid-stroke

- **Given** the effective text of this specification and the docstrings and test names of `tests/test_wing_kinematics.py`
- **When** the retired-claim guard runs
- **Then** it reports nothing, and inserting any of this specification's retired stale sentences into either makes it fail

#### Scenario: Coarse T2a values in a coarse context are not flagged

- **Given** the scenarios in this specification that quote coarse T2a peaks and name the coarse CSV as their input
- **When** the retired-claim guard runs
- **Then** those quotes are not reported, because the retired pattern is the T4 comparison phrase, not a bare number
