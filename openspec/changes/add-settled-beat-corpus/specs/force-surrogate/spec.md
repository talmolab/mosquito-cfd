## ADDED Requirements

### Requirement: Beat-to-beat settling metric

`mosquito_cfd.force_surrogate.settling` SHALL measure, for one run and each of the six targets
`CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`, how far each wingbeat is from the periodic state. Beat `b`
is 1-based and is the rows with `wingbeat == b − 1`; the extractor's `wingbeat` and `phase` columns
SHALL be used as given, never recomputed. The constants `SETTLED_TOLERANCE = 0.01`,
`N_PHASE = 256`, `COMPLETE_FRACTION = 0.95`, `STEP_FLOOR = 0.001`, `MIN_BEATS = 5` and
`FIRST_RATIO_BEAT = 4` SHALL be module constants.

- A beat is complete when it has at least `COMPLETE_FRACTION / (frequency_fstar · dt)` rows. `B`
  is the number of the last complete beat. An incomplete beat before `B`, a duplicate or
  non-increasing `phase` within a beat, a missing column, a non-finite value or a zero peak SHALL
  raise `ValueError` naming the configuration and the column. `B < MIN_BEATS` SHALL raise
  `ValueError`.
- Each complete beat is resampled onto phases `k / N_PHASE` by periodic linear interpolation,
  giving `w_b`. `P = max |w_B|`.
- Step change `s_b = rms(w_b − w_{b−1}) / P` (`b = 2..B`); distance to the last beat
  `D_b = rms(w_b − w_B) / P`.
- For `b = max(FIRST_RATIO_BEAT, B − 2) .. B`: when `s_{b−1}` and `s_b` are both at most
  `STEP_FLOOR` the ratio is skipped; when only `s_b` exceeds `STEP_FLOOR` the run is not
  contracting; otherwise `r_b = s_b / s_{b−1}`. `ρ = max r_b`; `ρ ≥ 1` means not contracting.
- Tail bound `T`: infinite when not contracting; `2 · max s_b` over the ratio beats when every
  ratio was skipped; otherwise `s_B · ρ / (1 − ρ)`. `E_b = D_b + T`.
- Jitter `J = rms(L_even(w_B) − L_odd(w_B)) / P`, where `L_even` and `L_odd` resample beat `B`
  from its even- and odd-indexed samples, SHALL be reported per target.
- The maximum absolute difference over phase SHALL be reported beside every RMS value and SHALL
  NOT enter any verdict.

#### Scenario: A geometric approach reproduces its closed form

- **Given** synthetic beats `w_b = w_∞ + a · r^b · g(phase)` with `r = 0.6`, `B = 8`, and `a` large
  enough that every `s_b` exceeds `STEP_FLOOR`
- **When** the metric is computed
- **Then** every `s_b`, `ρ` and `T` equal their closed forms to `rel = 1e-9`, and `E_b` is at least
  `rms(w_b − w_∞) / P` for every beat

#### Scenario: Growth from the floor is not contracting

- **Given** step changes `s_4..s_7` of `1e-5, 1e-5, 1e-5, 5e-3`
- **When** the metric is computed with `B = 7`
- **Then** the run is not contracting and `T` is infinite

#### Scenario: A run that has reached the floor is bounded, not stopped

- **Given** step changes `5e-4, 4e-4, 3e-4, 4e-4` at beats `B − 3 .. B`
- **When** the metric is computed
- **Then** every ratio is skipped, the run counts as contracting, and `T = 8e-4`

#### Scenario: Too few beats are rejected

- **Given** a run with 4 complete beats
- **When** the metric is computed
- **Then** `ValueError` names the configuration and the number of complete beats

#### Scenario: An incomplete final beat is not the reference

- **Given** an 8-beat run whose eighth beat has 60% of its expected rows
- **When** the metric is computed
- **Then** `B = 7` and beat 8 is listed as incomplete

#### Scenario: Off-integer steps per beat stay below the floor

- **Given** an exactly periodic signal with a one-step spike at stroke reversal, sampled at
  `dt = 5e-4` for `frequency_fstar` 0.85 and 1.15 over 8 beats
- **When** the metric is computed
- **Then** every `s_b` for `b ≥ 2` and every `J` are below `STEP_FLOOR`

#### Scenario: Known answer on the exploration coarse run

- **Given** the committed test fixture of the coarse 6-beat `s45_f100_p30` run
- **When** the metric is computed
- **Then** the CF_z tail bound is `0.0118 ± 1e-4`, and with E0b's `phase ≥ 0.05` mask applied the
  step changes reproduce E0b's beat-to-previous table to `5e-5`

### Requirement: Pre-registered settled-beat decision rule

`settling.decide_beat_count(runs)` SHALL apply the following rule, for runs that each have more
complete beats than the candidate. For a run with `B` complete beats and a candidate
`N` (`MIN_BEATS ≤ N ≤ B`), `pass(N)` SHALL hold only when, for every target:

- **(a)** the metric computed on that run's first `N` beats alone is contracting with
  `T ≤ SETTLED_TOLERANCE`; and
- **(b)** on the full run, `E_N ≤ SETTLED_TOLERANCE` and the run is contracting.

`N*_run` SHALL be the smallest `N` for which `pass(N′)` holds for every `N′` from `N` to `B`, and
`N* = max N*_run`. The action SHALL be one of three values, in this order of precedence:

- `stop`, when any run has no `N*_run`, any run is not contracting on its full length, or any
  target's jitter `J` exceeds `STEP_FLOOR`;
- `regenerate_needs_cost_approval`, when `N* > 6`;
- otherwise `regenerate`.

The result SHALL name the run, beat and target that set `N*` or caused `stop`. No margin SHALL be
added to `N*`.

#### Scenario: The slowest run sets the count

- **Given** runs whose `N*_run` are 5, 6 and 6
- **When** `decide_beat_count` is called
- **Then** the action is `regenerate`, `N* = 6`, and a run, beat and target that set it are named

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

### Requirement: The settling criterion is pre-registered and its precedence is provable

`examples/settling_check/PREREGISTRATION.md` SHALL state the settling constants in an anchored,
machine-readable block. A test SHALL fail when any constant in `settling.py` differs from that
block, and when the block is missing. The file SHALL be merged to `main` before any settling run
starts.

Every settling run record SHALL carry:
- the `main` commit the run was started from, which SHALL be an ancestor of `origin/main` with a
  clean working tree;
- the SHA-256 of `PREREGISTRATION.md`, `settling.py` and the deck generator at that commit.

Once run records are committed, a test SHALL fail unless the committed `PREREGISTRATION.md` hashes
to the recorded value, or a committed `deviations.json` entry
(`old_sha256`, `new_sha256`, `reason`, `pr`) accounts for the change. No such test SHALL read git
history.

#### Scenario: A changed tolerance fails the pinning test

- **Given** the committed `PREREGISTRATION.md`
- **When** `SETTLED_TOLERANCE` in `settling.py` is changed to `0.02`
- **Then** the pinning test fails and names the constant

#### Scenario: An unrecorded edit after the runs fails

- **Given** committed run records carrying the pre-registration hash
- **When** `PREREGISTRATION.md` is edited without a `deviations.json` entry
- **Then** the precedence test fails

### Requirement: Settling-check decks differ from the corpus decks by a declared key set

A settling-check deck SHALL be generated from the committed corpus deck of the same configuration
and grid. Parsed key by key, the set of keys that differ or are added SHALL equal the key set
declared for that grid in the settling manifest. `ns.cfl`, `ns.fixed_dt`, the geometry and the grid
SHALL be equal to the source deck's. `max_step` and `stop_time` SHALL equal `derive_run_duration`
for the declared beat count. The settling manifest SHALL record the SHA-256 of both decks.

#### Scenario: A missing declared key fails

- **Given** a generated deck without `amrex.the_arena_init_size`
- **When** it is compared with its source deck
- **Then** the check fails and names the missing key

#### Scenario: An undeclared change fails

- **Given** a generated deck whose `ns.cfl` differs from the source deck
- **When** it is compared with its source deck
- **Then** the check fails and names `ns.cfl`

### Requirement: A settling report records its controls and its inputs

`scripts/check_settling.py` SHALL write `settling_report.json` with:
- the constants used, the pre-registration hash and the git commit;
- each run's metrics per beat and target, plus each run's jitter, mean CF_z per beat, and the
  near-wing field change at matched phase;
- the result of every control the settling manifest declares for that run, and the decision.

The report SHALL be marked `controls_incomplete`, and the script SHALL exit non-zero, when any
declared control has no recorded result. The field change and mean-lift drift SHALL be reported
and SHALL NOT enter the decision. The field change is the median, and the fraction above 0.1, of
`|u_b − u_B| / u_ref` over the near-wing box, with `u_ref` from `compute_force_reference`.

#### Scenario: A missing control blocks the report

- **Given** a run record with no result for a declared control
- **When** the report is built
- **Then** it is marked `controls_incomplete` and the script exits non-zero

#### Scenario: A uniform field offset is measured in units of the reference speed

- **Given** two velocity arrays differing everywhere by `0.12 · u_ref` in one component
- **When** the field change is computed
- **Then** the median is `0.12` to `rel = 1e-12` and the fraction above 0.1 is 1
