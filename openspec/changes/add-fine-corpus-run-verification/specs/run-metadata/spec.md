# run-metadata

## MODIFIED Requirements

### Requirement: final_time and timesteps are derived from the committed force CSV, never the deck's stop_time

The metadata generator SHALL read the committed force CSV's actual last data row and use its
`time` value for `timing.final_time`, and its **distinct-timestep count** for `timing.timesteps`. It
SHALL NOT use the deck's `stop_time`/`ns.stop_time` value for `final_time` under any circumstance,
since IB-particle CSVs systematically end exactly one `dt` short of `stop_time` (a pre-existing
writer convention, not a divergence signal).

**BREAKING**: `timing.timesteps` previously recorded the raw data-row count. When `ns.init_iter > 0`
the solver writes `1 + init_iter` rows at `iStep = 0`, so the raw row count exceeds the timestep
count and the field no longer means what its name says. It SHALL now be the count of distinct
`iStep` values. For a corpus generated without `init_iter` the two are identical, so previously
committed force-only metadata is unaffected. The raw row count SHALL remain available internally for
the pod-side cross-check (see "pod-reported row count is cross-validated against the CSV").

#### Scenario: CSV ends one dt short of stop_time

- **GIVEN** a config's committed force CSV whose last row has `iStep=4705, time=2.3525` and a
  deck with `stop_time=2.352941176`
- **WHEN** the generator assembles `run_metadata_<config>.json`
- **THEN** `timing.final_time` is `2.3525` (the CSV's last row) and `timing.timesteps` is `4706`
  (the distinct-timestep count), and neither value equals the deck's `stop_time`

#### Scenario: Initialization rows do not inflate the timestep count

- **GIVEN** a force CSV written with `ns.init_iter = 2`, carrying 4708 data rows of which three
  share `iStep = 0`
- **WHEN** the generator assembles metadata for that config
- **THEN** `timing.timesteps` is `4706`, the number of distinct `iStep` values
- **AND** it equals the configuration's manifest `max_step`

### Requirement: run context is structured, not free-text narrative, except for one optional notes field

The metadata generator SHALL derive `stability`, `arena_max_mib`, `node`, and `gpu_model` as
independent structured fields rather than composing a free-text narrative paragraph. An optional
`notes` field MAY be present for exceptional human commentary but SHALL NOT be required for a normal
run, and the generator SHALL produce a complete, valid metadata file when `notes` is omitted.

`stability` SHALL reflect the timestep behaviour the run **actually exhibited**, derived from the
run's observed timestep series compared against both the deck's declared `ns.fixed_dt` and the
sweep's nominal `fixed_dt`. It SHALL NOT be derived from the deck's declared value alone.

**BREAKING**: `stability` previously had exactly two forms, `stable_at_5e-4` and
`stable_at_<dt>_fallback`, and was a pure function of the deck's `fixed_dt`. Because `ns.cfl` can
limit the realized timestep below `ns.fixed_dt`, a deck-derived value cannot report a CFL-limited run
and will assert stability for a run that did not have it. Two values are therefore ADDED —
`cfl_limited_at_5e-4` and `cfl_limited_at_<dt>_fallback` — for runs in which any interior step fell
below the deck's declared `ns.fixed_dt`. The two existing values keep their exact current meaning for
runs that held their declared timestep. The new values deliberately do **not** begin with
`stable_at_`, so any consumer matching that prefix fails closed rather than silently accepting a
CFL-limited run; every such consumer SHALL be updated in the same change.

The observed timestep series SHALL be read from the run's `run.log` per-step `DT` output at full
precision, not by differencing the force CSV's `time` column. The CSV writes `time` at six
significant figures, which at `t ≈ 2` quantizes a differenced timestep to roughly ±2% of nominal and
can yield values above the `ns.fixed_dt` ceiling that the solver cannot have taken.

The final step SHALL be excluded from the comparison: the solver clamps its last step to land exactly
on `stop_time`, so a short final step is expected on a healthy run and is not evidence of
instability.

#### Scenario: Arena max parsed from run.log

- **GIVEN** a `run.log` containing an AMReX end-of-run report with a "The Arena" max-used line
  reporting `7998 MiB`
- **WHEN** the generator assembles the committed metadata file
- **THEN** `arena_max_mib` is `7998`, and no free-text field is required to convey this figure

#### Scenario: stability reflects a run that held its declared timestep

- **GIVEN** a config whose deck declares `ns.fixed_dt = 5e-4` and whose observed interior timesteps
  are all `5e-4`, and a second config whose deck declares the `2.5e-4` documented fallback and whose
  observed interior timesteps are all `2.5e-4`
- **WHEN** the generator assembles metadata for each
- **THEN** the first config's `stability` is `"stable_at_5e-4"` and the second's is
  `"stable_at_2.5e-4_fallback"`, with no separate hand-set flag read or required

#### Scenario: A CFL-limited run is not reported as stable

- **GIVEN** a config whose deck declares `ns.fixed_dt = 5e-4` but whose observed interior timesteps
  fall as low as `3.06e-4`
- **WHEN** the generator assembles metadata for that config
- **THEN** `stability` is `"cfl_limited_at_5e-4"`, not `"stable_at_5e-4"`
- **AND** the value does not begin with `stable_at_`, so a prefix-matching consumer fails closed

#### Scenario: A clamped final step is not mistaken for instability

- **GIVEN** a run whose interior timesteps are all `5e-4` and whose final step is `4.41e-4` because
  it was clamped to land on `stop_time`
- **WHEN** the generator assembles metadata for that config
- **THEN** `stability` is `"stable_at_5e-4"`

#### Scenario: notes omitted on a normal run

- **GIVEN** a run with no exceptional circumstances to document
- **WHEN** the generator assembles the committed metadata file without a `--notes` argument
- **THEN** the output is complete and valid with no `notes` key present (not an empty string)

### Requirement: kinematics, grid, fixed_dt, and max_step are sourced from the sweep manifest or deck

The metadata generator SHALL read `stroke_amp_deg`, `frequency_fstar`, `pitch_amp_deg`,
`reynolds`, grid resolution, `fixed_dt`, `cfl`, and `max_step` from the committed
`sweep_manifest.json` or the generated deck file for the given config, rather than accepting them as
freeform CLI input or requiring a human to re-type them. These fields describe what the run was
**asked** to do.

Fields describing what the run **did** SHALL be derived from the run's own output and recorded
alongside them, so intent and outcome are both present and comparable. The output SHALL therefore
also carry, per run:

- `realized_dt`: the observed timestep series summarized as `min`, `mean`, `max`, and
  `frac_below_nominal` over interior steps
- `interior_dt_below_nominal`: whether any interior step fell below the deck's declared `ns.fixed_dt`
- `cycles_completed`: `final_time * frequency_fstar`, the whole wingbeats actually covered
- `reached_stop_time`: whether the run terminated on `stop_time` rather than on `max_step`

`realized_dt` SHALL NOT be summarized by its median. The median is provably blind to this failure
mode: on the affected corpus every config — including one whose timesteps fell to 3.06e-4 for 40.7%
of its steps — has a median interior timestep of exactly the nominal value, because the majority of
steps still sit at the `ns.fixed_dt` ceiling. `min` and `frac_below_nominal` are the discriminating
statistics.

The field is named `interior_dt_below_nominal` rather than `dt_reduced` because `dt_reduced` already
exists in the pilot metadata schema with different semantics — a deck-level fallback marker asserting
`fixed_dt == 2.5e-4` — and reusing the name would silently collide with it.

#### Scenario: kinematics, grid, and timestep fields match the manifest entry

- **GIVEN** a config present in `sweep_manifest.json` with a specific `stroke_amp_deg`,
  `frequency_fstar`, `pitch_amp_deg`, `reynolds`, grid resolution, `fixed_dt`, `cfl`, and `max_step`
- **WHEN** the generator assembles metadata for that config
- **THEN** the output's `kinematics` block, `grid`, `fixed_dt`, `cfl`, and `max_step` fields all match
  the manifest entry's values exactly, with no CLI flag available to override any of them

#### Scenario: Observed fields are recorded alongside intent

- **GIVEN** a completed run's `run.log` and force CSV
- **WHEN** the generator assembles metadata for that config
- **THEN** the output records `realized_dt`, `interior_dt_below_nominal`, `cycles_completed`, and
  `reached_stop_time`

#### Scenario: A truncated run is machine-readable as truncated

- **GIVEN** a run that exhausted `max_step` at `final_time = 1.5904` with `frequency_fstar = 1.15`
- **WHEN** the generator assembles metadata for that config
- **THEN** `cycles_completed` is approximately `1.829` and `reached_stop_time` is false
- **AND** `realized_dt.min` is below the deck's `ns.fixed_dt` while `realized_dt.mean` is between
  them, so the shortfall is legible without recomputing it from the `time` column

#### Scenario: No hand-set stability or observation input is accepted

- **GIVEN** the metadata generator's command-line interface
- **WHEN** its available options are inspected
- **THEN** none of `stability`, `realized_dt`, `interior_dt_below_nominal`, `cycles_completed`, or
  `reached_stop_time` can be supplied or overridden by a flag

### Requirement: pod-reported row count is cross-validated against the CSV

The metadata generator SHALL compare the pod-side `run_metadata.json`'s own reported row/step
count against the force CSV's independently-derived **raw data-row count**, and SHALL raise a clear
error naming both values when they disagree, rather than silently preferring one or producing a
valid-looking output with an unresolved discrepancy.

The comparison SHALL be made against the raw row count, since that is what the pod records. It SHALL
NOT be made against `timing.timesteps`, which is the distinct-timestep count and legitimately differs
from the raw count by `init_iter` when initialization rows are present.

#### Scenario: pod-reported row count disagrees with the CSV

- **GIVEN** a pod-side `run_metadata.json` reporting `rows=4700` and a force CSV containing 4706
  data rows
- **WHEN** the generator attempts to assemble metadata for that config
- **THEN** it raises a clear error naming both the pod-reported and CSV-derived counts, rather than
  producing output that silently picks one

#### Scenario: Initialization rows do not trigger a false mismatch

- **GIVEN** a pod-side `run_metadata.json` reporting `rows=4708` and a force CSV containing 4708
  data rows spanning 4706 distinct `iStep` values
- **WHEN** the generator assembles metadata for that config
- **THEN** the cross-check passes
- **AND** `timing.timesteps` is recorded as `4706`
