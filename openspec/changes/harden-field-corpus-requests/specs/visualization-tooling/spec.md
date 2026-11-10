## ADDED Requirements

### Requirement: `flow_video`'s near-field box margin is validated before any I/O

`build_flow_video` SHALL reject a `box_margin` that is not a finite real number strictly greater than
zero — including a `bool`, a string, `NaN` and `±inf` — with a `ValueError` naming `box_margin` and
its value, before any plotfile I/O or `Figure` creation, in every field mode. A non-positive margin
turns the `center ± box_margin` near-field request into an inverted or zero-width region; without this
check the caller would see the reader's `lo > hi` error, naming values it never passed.

#### Scenario: an invalid box margin fails fast in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `-1.0`, `0`, `0.0`, `nan`, `inf`,
  `-inf`, `np.float64(-1.0)`, `True` or `"3"`, in each of the four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** it raises `ValueError` whose message is the `box_margin` validator's own and contains the
  bad value, plotfile discovery was never reached, and no `Figure` was created
