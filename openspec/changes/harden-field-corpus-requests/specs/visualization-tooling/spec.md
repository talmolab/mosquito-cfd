## ADDED Requirements

### Requirement: `flow_video`'s near-field box margin is validated before any I/O

`build_flow_video` SHALL accept as `box_margin` any real number — an `int`, `float`,
`fractions.Fraction`, or numpy integer or floating scalar (`numbers.Real`), other than a `bool`,
`np.bool_` or `np.timedelta64` — that converts to a finite `float` strictly greater than zero, and
SHALL use that `float` as the margin. It SHALL reject every other value — including a `bool`, a
string, a `decimal.Decimal`, a `np.timedelta64` (a duration, not a length, although numpy registers
it as `numbers.Real`), `NaN`, `±inf`, zero, a negative number, an `int` too large to convert to a
`float`, and a `numbers.Real` whose conversion to `float` raises — with a `ValueError` naming
`box_margin` and its value (a numpy number or bool scalar shown as its plain Python value; a numpy
datetime or timedelta keeps numpy's repr), before any plotfile I/O or `Figure` creation, in every
field mode. A non-positive margin turns the `center ± box_margin` near-field request into an
inverted or zero-width region; without this check the caller would see the reader's `lo > hi` error,
naming values it never passed.

#### Scenario: an invalid box margin fails fast in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `-1`, `-1.0`, `0`, `0.0`, `nan`,
  `inf`, `-inf`, `np.float64(-1.0)`, `True`, `np.bool_(True)`, `"3"`, `Decimal("3")`, `10**400`,
  `-(10**400)`, `np.timedelta64(1, "s")`, `np.timedelta64(5, "ns")`, `np.datetime64("2020-01-01")`,
  or a registered `numbers.Real` whose `__float__` raises `TypeError` or `ValueError`, in each of the
  four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** it raises `ValueError` whose message is the `box_margin` validator's own and ends with the
  bad value, plotfile discovery was never reached, and no `Figure` was created

#### Scenario: a valid box margin passes validation in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `5e-324`, `1e-9`, `0.5`, `2`,
  `np.int64(2)`, `np.float32(0.5)` or `Fraction(1, 2)`, in each of the four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** validation passes and the call reaches plotfile discovery (the replacement's failure is
  raised, not a `ValueError`)

#### Scenario: the lev-3d near-field box is built from the validated float

- **GIVEN** a `lev-3d` call to `build_flow_video` with `box_margin` equal to `Fraction(5, 2)` or
  `np.float32(2.5)`, and the near-field box reader replaced by a recorder
- **WHEN** the function is invoked
- **THEN** every requested box has `lo == center - 2.5` and `hi == center + 2.5` exactly, as float64
  arrays
