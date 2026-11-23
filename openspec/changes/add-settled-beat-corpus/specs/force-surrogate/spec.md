## ADDED Requirements

### Requirement: Beat-to-beat settling metric

`mosquito_cfd.force_surrogate.settling` SHALL measure how far each wingbeat of one run is from the
periodic state, for each of the six targets `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`.

- **Beats.** Beat `b` is 1-based and is the rows with `wingbeat == b − 1`. The extractor's
  `wingbeat` and `phase` columns SHALL be used as given, never recomputed. The timestep `dt` and
  `stop_time` SHALL be passed in, taken from the manifest.
- **Clamped steps.** Rows with `time + dt > stop_time + CLAMP_SLACK` SHALL be dropped before beats are
  formed. Those are steps the solver shortened to land on `stop_time`.
- **Constants.** These SHALL be module constants: `SETTLED_TOLERANCE = 0.01`,
  `COMPLETE_FRACTION = 0.95`, `MIN_BEATS = 5`, `FIRST_RATIO_BEAT = 4`, `NOISE_FACTOR = 3` and
  `MAX_NOISE = 0.0006`, together with the decision and control constants
  `AT_FLOOR_FACTOR = 24`, `CLAMP_SLACK = 1e-9`, `COST_APPROVAL_ABOVE = 6`,
  `COMPARE_RELATIVE_TO_COLUMN = 1e-9`, `COMPARE_PRINT_UNITS = 1.5` and
  `FIELD_CHANGE_THRESHOLD = 0.1`.
- **Complete beats.** A beat is complete when it has at least
  `COMPLETE_FRACTION / (frequency_fstar · dt)` rows. `B` is the number of the last complete beat.
- **Errors.** Each of these SHALL raise `ValueError` naming the configuration and the cause:
  - an incomplete first beat, or a `wingbeat` value that is not a finite integer;
  - an incomplete beat before `B`;
  - a duplicate or non-increasing `phase` within a beat;
  - a missing column, a non-finite value or a zero peak;
  - `B < MIN_BEATS`.
- **Distance.** `dist(a, c)` SHALL be the RMS, over beat `a`'s own samples, of
  `w_a(φ_i) − L_c(φ_i)`, divided by `P = max |w_B|`. `L_c` is periodic linear interpolation of
  beat `c` in `phase`.
- **Steps and distances.** Step change `s_b = dist(b, b − 1)` for `b = 2..B`. Distance to the last
  beat `D_b = dist(b, B)`.
- **Jitter.** `J = rms(w_B[i−1] − 2·w_B[i] + w_B[i+1]) / (8 · P)` over the interior samples of
  beat `B`. The noise floor is `ν = NOISE_FACTOR · J`.
- **Ratios**, for the ratio beats `b = max(FIRST_RATIO_BEAT, B − 2) .. B`:
  - when `s_{b−1} ≤ ν` and `s_b ≤ 2ν`, the ratio is skipped;
  - when `s_{b−1} ≤ ν` and `s_b > 2ν`, the run is not contracting;
  - otherwise `r_b = s_b / s_{b−1}`.
- **Contraction.** `ρ = max r_b + max(0, r_last − r_first)` over the kept ratios in beat order.
  `ρ ≥ 1` means not contracting.
- **Tail bound `T`.**
  - `T` is infinite when the run is not contracting.
  - When every ratio was skipped, `T = AT_FLOOR_FACTOR · max s_b` over the ratio beats.
  - Otherwise `T = s_B · ρ / (1 − ρ)`.
- **Estimated distance.** `E_b = D_b + T`.
- **Reporting.** The maximum absolute difference over samples SHALL be reported beside every RMS
  value and SHALL NOT enter any verdict.

#### Scenario: A geometric approach reproduces its closed form

- **Given** synthetic beats `w_b = w_∞ + a · r^b · g(phase)` with `r = 0.6` and `B = 8`, sampled on
  identical phases in every beat, with `a` large enough that every `s_b` exceeds `ν`
- **When** the metric is computed
- **Then** every `s_b`, `ρ` and `T` equal their closed forms to `rel = 1e-9`
- **And** `E_b` is at least `dist` between beat `b` and `w_∞` for every beat, to `rel = 1e-9`

#### Scenario: Rising ratios widen the bound

- **Given** step changes `s_5..s_8` of `0.0125, 0.0080, 0.0050, 0.0036` and `ν = 6e-5`
- **When** the tail bound is computed with `B = 8`
- **Then** `ρ = 0.72 + (0.72 − 0.64) = 0.80` to `rel = 1e-6`, and `T = 0.0144 > SETTLED_TOLERANCE`

#### Scenario: A slow mode below one percent is not mistaken for noise

- **Given** step changes `s_5..s_8` of `8.1e-4, 7.7e-4, 7.4e-4, 7.0e-4` and `ν = 6e-5`
- **When** the tail bound is computed with `B = 8`
- **Then** no ratio is skipped and `T > SETTLED_TOLERANCE`

#### Scenario: Growth from the noise floor is not contracting

- **Given** step changes `s_5..s_8` of `1e-6, 1e-5, 1e-4, 9e-4` and `ν = 6e-5`
- **When** the tail bound is computed with `B = 8`
- **Then** the run is not contracting and `T` is infinite

#### Scenario: A run at the noise floor is bounded, not stopped

- **Given** step changes `s_4..s_7` of `5e-5, 4e-5, 3e-5, 4e-5` and `ν = 6e-5`
- **When** the tail bound is computed with `B = 7`
- **Then** every ratio is skipped, the run counts as contracting, and
  `T = 24 · 4e-5 = 9.6e-4`

#### Scenario: Two noise-level steps straddling the floor are not growth

- **Given** step changes `s_4..s_7` of `5e-5, 4e-5, 5e-5, 7e-5` and `ν = 6e-5`
- **When** the tail bound is computed with `B = 7`
- **Then** the run counts as contracting (`7e-5 ≤ 2ν`) and `T` is finite

#### Scenario: Too few beats are rejected

- **Given** a run with 4 complete beats
- **When** the metric is computed
- **Then** `ValueError` names the configuration and the number of complete beats

#### Scenario: An incomplete final beat is not the reference

- **Given** an 8-beat run whose eighth beat has 60% of its expected rows
- **When** the metric is computed
- **Then** `B = 7` and beat 8 is listed as incomplete

#### Scenario: Off-integer steps per beat add less than the noise floor

- **Given** an exactly periodic 8-beat signal built by periodic linear interpolation of a committed
  final beat, on the true `step · dt` grid, for each committed `f085` and `f115` configuration
- **When** the metric is computed
- **Then** every `s_b` for `b ≥ 2` is at most `ν` for every target, and `ν ≤ MAX_NOISE`

#### Scenario: A clamped final step is dropped

- **Given** an 8-beat run at `frequency_fstar = 0.85` whose last row is a short final step carrying
  a force spike of `0.1 · P`
- **When** the metric is computed with the manifest's `stop_time`
- **Then** that row is excluded, and every result equals the result for the run without it

### Requirement: Pre-registered settled-beat decision rule

`settling.decide_beat_count(runs)` SHALL apply the following rule.

For a run with `B` complete beats and a candidate `N` with `MIN_BEATS ≤ N ≤ B`, `pass(N)` SHALL
hold only when, for every target:
- **(a)** the metric computed on that run's first `N` beats alone is contracting with
  `T ≤ SETTLED_TOLERANCE`; and
- **(b)** on the full run, `E_N ≤ SETTLED_TOLERANCE` and the run is contracting.

`N*_run` SHALL be the smallest `N` for which `pass(N′)` holds for every `N′` from `N` to `B`, and
`N* = max N*_run`.

The action SHALL be one of these, in this order of precedence:
- `stop`, when any run has no `N*_run`, any run is not contracting on its full length, or any
  target has a `ν` that is not at most `MAX_NOISE` (a NaN stops);
- `regenerate_needs_cost_approval`, when `N* > COST_APPROVAL_ABOVE`;
- otherwise `regenerate`.

The result SHALL name the run, beat and target that set `N*` or caused `stop`; for `N*`, the beat is the one below `N*` that failed and the target is the worst there. No margin SHALL be
added to `N*`.

#### Scenario: The slowest run sets the count

- **Given** runs whose `N*_run` are 5, 6 and 6
- **When** `decide_beat_count` is called
- **Then** the action is `regenerate` and `N* = 6`
- **And** a run, beat and target that set it are named

#### Scenario: The truncated test can fail when the full-run test passes

- **Given** an 8-beat run where `E_6 ≤ 0.01` on the full run but the metric on its first 6 beats
  gives `T = 0.0118` for CF_z
- **When** `pass(6)` is evaluated
- **Then** it is false

#### Scenario: Stop takes precedence

- **Given** one run with no settled beat and another whose `N*_run = 8`
- **When** `decide_beat_count` is called
- **Then** the action is `stop` and no beat count is returned

#### Scenario: A long count needs cost approval

- **Given** runs whose `N*_run` are 6, 7 and 7
- **When** `decide_beat_count` is called
- **Then** the action is `regenerate_needs_cost_approval` with `N* = 7`

#### Scenario: Too much noise stops the decision

- **Given** a run whose CF_y has `ν = 9e-4`
- **When** `decide_beat_count` is called
- **Then** the action is `stop`, naming the run and CF_y

### Requirement: The settling criterion is pre-registered and its precedence is attested

`examples/settling_check/PREREGISTRATION.md` SHALL state the settling constants in a
machine-readable block between `<!-- settling-constants:start -->` and
`<!-- settling-constants:end -->`. A test SHALL fail when any constant in `settling.py` differs
from that block, or when the block is missing. The file SHALL be merged to `main` before any
settling run starts, and SHALL state that the criterion predates the fine-grid and 8-beat data
only.

The gated files are `PREREGISTRATION.md`, the deck generator and `settling.py`.

Every settling run record SHALL carry git provenance derived by `settling.git_provenance`, never
typed in by the operator:
- the launch commit and `git status --porcelain`, written to the run directory just before the
  run starts;
- HEAD at record time;
- whether the launch commit is an ancestor of `origin/main`;
- whether the checkout was dirty at launch and is dirty at record time, ignoring Stage 1
  records under `examples/settling_check/records/`;
- the SHA-256 of each gated file at the launch commit (from `git show`), and whether the
  working tree still matches it.

A record SHALL be refused unless HEAD equals the launch commit, the launch commit is an
ancestor of `origin/main`, the checkout was and is clean, and every gated file matches the
launch commit.

For every committed run record, a test SHALL fail unless every gated file hashes to the recorded
value, or an entry in a committed `deviations.json` (`file`, `old_sha256`, `new_sha256`,
`reason`, `pr`) accounts for the difference. Malformed JSON SHALL be a named failure, not an
exception.

When a decision or settling report is committed, a test SHALL fail unless the set of run
records equals the set of runs and controls the settling manifest declares, with none missing
and none stray.

No such test SHALL read git history.

#### Scenario: A changed tolerance fails the pinning test

- **Given** the committed `PREREGISTRATION.md`
- **When** `SETTLED_TOLERANCE` in `settling.py` is changed to `0.02`
- **Then** the pinning test fails and names the constant

#### Scenario: An unrecorded edit after the runs fails

- **Given** a run record carrying the pre-registration hash
- **When** `PREREGISTRATION.md` is edited without a `deviations.json` entry
- **Then** the precedence check fails, and with a matching entry it passes

#### Scenario: A decision without run records fails

- **Given** a committed `DECISION.md` and no run records
- **When** the precedence check runs
- **Then** it fails, naming each run and control that has no record

#### Scenario: Control records count, and stray records fail

- **Given** a manifest with long runs and C1 controls, and a record for each
- **When** the precedence check runs
- **Then** it passes
- **And** with one control record removed and a record for an undeclared name added, it fails
  naming both

#### Scenario: A gated file edited after launch blocks the record

- **Given** a run launched from a clean commit
- **When** a gated file is edited before the record is written
- **Then** `git_provenance` reports the working tree no longer matches the launch commit, and
  the record is refused

### Requirement: Settling-check decks differ from the corpus decks by a declared key set

A settling-check deck SHALL be generated from the committed corpus deck of the same configuration
and grid, parsed with `metadata_capture.parse_deck`.
- The set of keys that differ or are added SHALL equal the key set the settling manifest declares
  for that deck.
- `ns.cfl`, `ns.fixed_dt`, `ns.init_iter`, the geometry and the grid SHALL equal the source deck's.
- `max_step` and `stop_time` SHALL equal `derive_run_duration` for the declared beat count.
- The settling manifest SHALL record the SHA-256 of both decks.

#### Scenario: A missing declared key fails

- **Given** a generated deck without `amrex.the_arena_init_size`
- **When** it is compared with its source deck
- **Then** the check fails and names the missing key

#### Scenario: An undeclared change fails

- **Given** a generated deck whose `ns.cfl` differs from the source deck
- **When** it is compared with its source deck
- **Then** the check fails and names `ns.cfl`

### Requirement: A settling report records its controls and its inputs

`scripts/check_settling.py` SHALL write `settling_report.json` containing:
- the constants used, the pre-registration hash, and the git commit;
- each run's metrics per beat and target, its jitter, its mean CF_z per beat, and its near-wing
  field change at matched phase;
- the result of every control the settling manifest declares for that run;
- the decision.

Every record SHALL be checked with `settling.validate_run_record`, which requires:
- clean provenance (see the pre-registration requirement);
- the manifest's digest-pinned image, named in the recorded container command;
- the SHA-256 of the deck in the run directory equal to the committed settling deck;
- a step count equal to the deck's `max_step`, so a run that stopped early fails;
- non-empty hardware and IAMReX label, positive timing, and a boolean result for every
  declared control.

A control counts as passed only when its result is the boolean `true`.

The report's `status` SHALL be one of:
- `controls_incomplete`, when a declared record or control result is missing;
- otherwise `control_failed`, when a record is invalid or a control did not pass;
- otherwise `precedence_failed`, when the precedence check fails;
- otherwise `data_incomplete`, when a run has no dataset rows, fewer complete beats than the
  manifest declares, or a dataset whose extraction metadata does not name the CSV its record
  hashes;
- otherwise `complete`.

The script SHALL exit non-zero unless the status is `complete`.

The force comparison control SHALL:
- de-duplicate the run's force rows with the extractor's validated rule;
- drop rows whose step ends past the reference's or the run's `stop_time`;
- match the remaining rows to the configuration's rows of the committed `dataset.parquet` by
  step index `round(time / dt)`.

The comparison covers steps `0 .. n − 1`:
- for C1, `n` is the control deck's declared `max_step`;
- for C3, `n` is the number of reference rows left after the reference's clamped row is dropped.

Each of those steps SHALL appear exactly once in both the run and the reference. A missing or
duplicate step on either side fails, so a gapped or truncated run cannot pass. Run rows after
step `n − 1` (a long run continuing past its 2-beat reference) are not compared.

It SHALL pass only when every raw `Fx..Mz` value is finite on both sides and within
`max(COMPARE_RELATIVE_TO_COLUMN · max |column|, COMPARE_PRINT_UNITS units in the 6th
significant figure of the reference value)`. The column maximum is taken over the matched
reference rows. For a reference value of exactly 0 the second term is 0. A NaN or inf on either
side fails, and a missing column is a failure, not an exception.

The field change is the median, and the fraction above `FIELD_CHANGE_THRESHOLD`, of
`|u_b − u_B| / u_ref` (the vector
difference norm) over the near-wing box, with `u_ref` from `compute_force_reference`. The field
change and the mean-lift drift SHALL be reported and SHALL NOT enter the decision.

#### Scenario: A missing control blocks the report

- **Given** a run record with no result for a declared control
- **When** the report is built
- **Then** it is marked `controls_incomplete` and the script exits non-zero

#### Scenario: Round-off passes the force comparison and a real difference fails

- **Given** a reference force series and a copy perturbed by `5e-13` in one row of `Fy`
- **When** they are compared
- **Then** the comparison passes
- **And** with a perturbation of `1e-4 · max |Fy|` in a row near the peak it fails, naming `Fy` and
  the `time`

#### Scenario: A truncated run fails the comparison

- **Given** a 400-step run whose rows stop at step 380
- **When** it is compared with the reference rows for a declared step count of 400
- **Then** the comparison fails, naming the first missing step

#### Scenario: A non-finite force fails the comparison

- **Given** a run CSV with `nan`, `-nan` or `inf` in one row of `Fz`, otherwise identical
- **When** it is compared with the committed rows
- **Then** the comparison fails and names `Fz`

#### Scenario: A run that stopped early is not a valid record

- **Given** a long run whose force CSV ends after 5 of its declared 8 beats
- **When** its record is validated
- **Then** validation fails, naming `steps` and the declared `max_step`

#### Scenario: Init-iteration duplicates do not fail the comparison

- **Given** a run CSV with the two extra `iStep == 0` rows that `ns.init_iter = 2` writes, and
  otherwise identical values
- **When** it is compared with the committed rows
- **Then** the comparison passes, and a duplicate at any other `iStep` fails

#### Scenario: A uniform field offset is measured in units of the reference speed

- **Given** two velocity arrays differing everywhere by `0.12 · u_ref` in one component
- **When** the field change is computed
- **Then** the median is `0.12` to `rel = 1e-12` and the fraction above 0.1 is 1
