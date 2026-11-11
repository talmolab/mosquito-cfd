## ADDED Requirements

### Requirement: `flow_video`'s near-field box margin is validated before any I/O

`build_flow_video` SHALL accept as `box_margin` any real number — an `int`, `float`,
`fractions.Fraction`, or numpy integer or floating scalar (`numbers.Real`), other than a `bool` or
`np.bool_` — that converts to a finite `float` strictly greater than zero, and SHALL use that `float`
as the margin. It SHALL reject every other value — including a `bool`, a string, a `decimal.Decimal`,
`NaN`, `±inf`, zero, a negative number, and an `int` too large to convert to a `float` — with a
`ValueError` naming `box_margin` and its value (a numpy scalar shown as its plain Python value),
before any plotfile I/O or `Figure` creation, in every field mode. A non-positive margin turns the
`center ± box_margin` near-field request into an inverted or zero-width region; without this check the
caller would see the reader's `lo > hi` error, naming values it never passed.

#### Scenario: an invalid box margin fails fast in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `-1.0`, `0`, `0.0`, `nan`, `inf`,
  `-inf`, `np.float64(-1.0)`, `True`, `np.bool_(True)`, `"3"`, `Decimal("3")`, `10**400` or
  `-(10**400)`, in each of the four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** it raises `ValueError` whose message is the `box_margin` validator's own and ends with the
  bad value, plotfile discovery was never reached, and no `Figure` was created

#### Scenario: a valid box margin passes validation in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `1e-9`, `0.5`, `2`, `np.int64(2)`,
  `np.float32(0.5)` or `Fraction(1, 2)`, in each of the four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** validation passes and the call reaches plotfile discovery (the replacement's failure is
  raised, not a `ValueError`)
