## ADDED Requirements

### Requirement: Beat-to-beat settling metric

`mosquito_cfd.force_surrogate.settling` SHALL compute, for one run and each of the six targets
`CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`, how far each wingbeat is from the periodic state:

- Beat `b` (1-based) is the rows with `wingbeat == b - 1`. A beat is **complete** when it has at
  least 95% of `1 / (frequency_fstar * dt)` rows. `B` is the last complete beat. Incomplete beats
  SHALL be excluded and named in the result.
- Each complete beat is resampled onto 256 phases `k / 256` by periodic linear interpolation in
  `phase`, giving `w_b`.
- `P = max |w_B|` (the last complete beat's peak).
- Step change `s_b = rms(w_b - w_{b-1}) / P` for `b = 2..B`.
- Distance to the last beat `D_b = rms(w_b - w_B) / P`.
- Contraction ratio `rho = max(s_b / s_{b-1})` over `b = B-2, B-1, B`, dropping any ratio whose
  denominator is below `1e-4`.
- Tail bound `T = s_B * rho / (1 - rho)` when `rho < 1`; infinite, with `contracting = False`,
  when `rho >= 1`; `T = s_B` when no ratio remains.
- Estimated distance to the periodic state `E_b = D_b + T`.

The maximum absolute difference over phase SHALL be reported beside each RMS value. A run with
fewer than 3 complete beats, a missing column, a non-finite value or a zero peak SHALL raise
`ValueError` naming the configuration and the column.

#### Scenario: A geometric approach reproduces its closed form

- **Given** synthetic beats `w_b = w_inf + a * r^b * g(phase)` with `0 < r < 1`
- **When** the metric is computed
- **Then** every step change, the contraction ratio and the tail bound equal their closed forms to
  `rel = 1e-9`, and `E_b` is at least the true distance `rms(w_b - w_inf) / P` for every beat

#### Scenario: A run that is not contracting has no finite bound

- **Given** synthetic beats whose step changes grow from beat to beat
- **When** the metric is computed
- **Then** `contracting` is `False`, the tail bound is infinite and no beat is settled

#### Scenario: An incomplete final beat is not the reference

- **Given** a run whose last beat has 60% of its expected rows
- **When** the metric is computed
- **Then** that beat is listed as incomplete and the reference is the beat before it

### Requirement: The settled-beat criterion is pre-registered

A beat `b` SHALL be **settled** when `E_c <= 0.01` for every one of the six targets and every beat
`c = b..B`. The tolerance (`0.01`), the phase count (`256`), the completeness rule (95%) and the
noise floor (`1e-4`) SHALL be constants in `settling.py`, SHALL be stated in
`examples/settling_check/PREREGISTRATION.md`, and SHALL be pinned by a test that reads the file.
`PREREGISTRATION.md` SHALL be merged to `main` before any settling run is started. Every settling
report SHALL carry the constants it used, the SHA-256 of `PREREGISTRATION.md` and the git commit
it was computed at.

#### Scenario: The worst target decides

- **Given** a beat whose `E` is 0.004 for five targets and 0.012 for the sixth
- **When** the verdict is computed
- **Then** the beat is not settled, and the result names the sixth target

#### Scenario: A later failure unsettles earlier beats

- **Given** a run where beat 4 has `E <= 0.01` for all targets but beat 5 does not
- **When** the smallest settled beat is requested
- **Then** it is not 4

#### Scenario: The constants cannot drift from the pre-registration

- **Given** `PREREGISTRATION.md` as committed
- **When** the tolerance in `settling.py` is changed without changing the file
- **Then** the pinning test fails

### Requirement: Corpus beat count is chosen by the pre-registered settling rule

The beat count of a regenerated corpus SHALL be chosen by `decide_beat_count` from settling runs
of `s45_f100_p30` (8 beats), `s45_f100_p45` (6 beats) and `s55_f115_p30` (6 beats) on both the
64x32x64 and the 256x128x256 grid. With `N*_run` the smallest settled beat of a run and
`N* = max N*_run`:

- every run has a settled beat → both corpora use `n_wingbeats = N*`;
- a 6-beat run has no settled beat and the 8-beat run has one → that run is extended to 8 beats
  and the rule is applied again;
- the 8-beat run has no settled beat, or any run is not contracting → no regeneration; the result
  is reported and the user decides;
- `N* > 6` → regeneration needs the user's explicit approval of the cost.

No floor and no safety margin SHALL be applied to `N*`. Both corpora SHALL use the same beat
count. A departure from this rule SHALL be recorded as a deviation next to the original verdict,
not substituted for it. `examples/settling_check/DECISION.md` SHALL state the chosen count, and a
test SHALL recompute it from the committed settling datasets.

#### Scenario: The slowest run sets the count

- **Given** six runs whose smallest settled beats are 4, 4, 5, 5, 6 and 6
- **When** `decide_beat_count` is called
- **Then** the action is "regenerate", `N* = 6`, and the result names a run, beat and target that
  set it

#### Scenario: An unsettled long run stops the work

- **Given** an 8-beat run with no settled beat
- **When** `decide_beat_count` is called
- **Then** the action is "stop" and no beat count is returned

#### Scenario: The committed decision matches the committed data

- **Given** the committed settling datasets and `DECISION.md`
- **When** the decision is recomputed
- **Then** it equals the count written in `DECISION.md`

### Requirement: Settling-check decks differ minimally from the corpus decks

Each settling-check deck SHALL be generated from the committed corpus deck of the same
configuration and grid, and SHALL differ from it only in `max_step`, `stop_time`, an added
`amrex.the_arena_init_size`, and, for the coarse twins only, `amr.plot_int`. `ns.cfl`,
`ns.fixed_dt`, `ns.init_iter`, the geometry and the grid SHALL be equal. The settling manifest
SHALL record the SHA-256 of both the source and the generated deck.

#### Scenario: The diff is exactly the allowed key set

- **Given** a generated settling deck and its source corpus deck, both parsed into key/value pairs
- **When** they are compared
- **Then** the set of differing or added keys is a subset of the allowed keys, and `max_step` and
  `stop_time` equal `derive_run_duration` for the run's beat count

### Requirement: Settling runs are controlled against the committed corpus

Before a settling run is used for the decision, these controls SHALL each have a recorded result
in its run record, and the settling report SHALL be marked `controls_incomplete` if any is
missing:

- **C1** — 400 steps of the `s55_f115_p30` fine deck reproduce the committed cluster run: an
  identical time grid, and raw `Fx..Mz` equal to within `1e-10` of each column's peak.
- **C2** — the same 400 steps run as 200, a restart from checkpoint, and 200 agree with C1 to the
  same tolerance. Only then MAY a run be extended by restart.
- **C3** — the first two beats of each long run reproduce the committed 2-beat corpus dataset:
  within `1e-10` of peak on the fine grid (same image); on the coarse grid (different image) the
  difference is reported, and above `1e-6` of peak the work stops for a decision.
- **C4** — no step of a fine run is below the nominal `ns.fixed_dt`, over all beats.

Each run record SHALL also carry the digest-pinned image, the exact container command, the
hardware, the wall time and the seconds per step.

#### Scenario: A perturbed series fails the control

- **Given** two force series on the same time grid that differ by `1e-9` of peak in one column
- **When** they are compared at tolerance `1e-10`
- **Then** the comparison fails and names the column and the first failing step

#### Scenario: A missing control blocks the decision

- **Given** a run record with no C3 result
- **When** the settling report is built
- **Then** it is marked `controls_incomplete` and the driver exits non-zero

### Requirement: Field settling is reported alongside the force criterion

For the fine settling runs at `frequency_fstar = 1.00`, the report SHALL include, per beat, the
difference in speed between that beat and the last beat at matched plotfile phase inside the
near-wing box, divided by the reference wing speed: its median and the fraction of the box above
10%. These values SHALL NOT enter the settled verdict. The report SHALL say so.

#### Scenario: Identical fields give zero change

- **Given** two equal velocity arrays
- **When** the field statistic is computed
- **Then** the median is 0 and the fraction above 10% is 0

#### Scenario: A uniform offset is measured in units of the reference speed

- **Given** two velocity arrays differing everywhere by `0.1 * u_ref` in one component
- **When** the field statistic is computed
- **Then** the median equals 0.1 to `rel = 1e-12`

### Requirement: The training beat of a corpus is its final requested beat

`settling.training_wingbeat(manifest)` SHALL return `n_wingbeats - 1`. Any consumer that trains
on, scores or plots "the settled beat" of a corpus SHALL select `wingbeat == training_wingbeat`.
For a 2-beat corpus this is the selection `wingbeat >= 1` makes. The dataset extractor SHALL keep
writing every beat.

#### Scenario: The 2-beat corpora are unchanged

- **Given** either committed 2-beat corpus
- **When** rows are selected with `wingbeat == training_wingbeat(manifest)`
- **Then** they are exactly the rows `wingbeat >= 1` selects

#### Scenario: A 6-beat corpus selects one beat

- **Given** a manifest with `n_wingbeats = 6`
- **When** `training_wingbeat` is called
- **Then** it returns 5

### Requirement: Settled-beat guards use the final requested beat

The corpus guards and the acceptance gate SHALL compute the symmetry-ratio invariant
(`|mean CF_x| / max |CF_x|`) over the final requested beat
(`wingbeat == n_wingbeats - 1`, `time > 0`), not over every beat after the first, so that a
truncated final beat is not diluted by earlier complete beats. Its tolerance SHALL NOT be re-tuned
for a new corpus: the healthy maximum SHALL be measured and recorded, and a healthy value above
the tolerance SHALL stop the work.

#### Scenario: The 2-beat corpora give bit-identical ratios

- **Given** either committed 2-beat corpus
- **When** the ratios are computed with the final-beat definition
- **Then** every ratio equals the `wingbeat >= 1` value exactly

#### Scenario: A truncated last beat of a long run is caught

- **Given** a synthetic 6-beat run whose last beat stops at 60% of the cycle
- **When** the guard runs
- **Then** it fails for that configuration, whereas the ratio taken over `wingbeat >= 1` stays
  inside the tolerance

### Requirement: The acceptance gate checks settling of every regenerated configuration

For a corpus with at least 3 complete beats per run, the post-run acceptance gate SHALL compute
the settling metric for every configuration and SHALL fail if the final beat's tail bound exceeds
`0.01` for any target or the run is not contracting. It SHALL write the per-config values and the
result to `sweep_provenance.json` under `cluster_run.settling`. For a corpus with fewer than 3
beats it SHALL write `not_applicable` with the reason and SHALL NOT fail on this check.

#### Scenario: One unsettled configuration fails the corpus

- **Given** a 27-config corpus in which one configuration's final-beat tail bound is 0.013 in
  `CF_z`
- **When** the gate runs
- **Then** it fails, names the configuration and the target, and the recorded result is "failed"

#### Scenario: The 2-beat corpora still pass

- **Given** either committed 2-beat corpus
- **When** the gate runs
- **Then** `cluster_run.settling` is `not_applicable` and the gate's verdict is unchanged

### Requirement: Field capture at fixed frames per beat with beat-boundary checkpoints

`generate_sweep` SHALL accept `frames_per_beat` and `checkpoints_per_beat`. When given, each
config's `amr.plot_int` SHALL be `round(steps_per_beat / frames_per_beat)` and its `amr.check_int`
SHALL be `round(steps_per_beat / checkpoints_per_beat)`, with `steps_per_beat = 1 /
(frequency_fstar * dt)`, and both SHALL be recorded per config in the manifest. When both are
omitted the output SHALL be byte-identical to the current output. The regenerated corpora SHALL
use `frames_per_beat = 20` and `checkpoints_per_beat = 1` on both grids, so every beat of every
configuration has plotfiles at the same 20 phases and any beat can be re-run from its checkpoint.

#### Scenario: Plot and checkpoint intervals follow the frequency

- **Given** `frames_per_beat = 20`, `checkpoints_per_beat = 1`, `dt = 5e-4`
- **When** decks are generated for `frequency_fstar` 0.85, 1.00 and 1.15
- **Then** `amr.plot_int` is 118, 100 and 87 and `amr.check_int` is 2353, 2000 and 1739

#### Scenario: Defaults leave the committed corpora unchanged

- **Given** `generate_sweep` called without either argument
- **When** its output is compared with the committed 2-beat corpora
- **Then** it is byte-identical

### Requirement: Each regenerated corpus commits a storage manifest

Each regenerated corpus directory SHALL contain `storage_manifest.json`, written by a tested
function from the raw run tree, listing per configuration: the run directory, its size in bytes,
the plotfile steps present, the checkpoint steps present, and the SHA-256 of the force CSV and of
`run.log`. A check SHALL compare it with the steps the sweep manifest implies and report a missing
run directory, a missing step and an unexpected step.

#### Scenario: A missing plotfile is reported

- **Given** a run tree in which one expected plotfile step of one configuration is absent
- **When** the storage manifest is checked against the sweep manifest
- **Then** the check fails and names the configuration and the step

### Requirement: Supersession history has a tested writer

`append_supersession_entry(provenance_path, entry)` SHALL append an entry to
`sweep_provenance.json`'s `supersession_history`, creating the list when absent, leaving every
other key and every existing entry unchanged, rejecting an entry that lacks a required field, and
doing nothing when an identical entry is already present. The regeneration runbook SHALL call it
in place of a hand edit.

#### Scenario: Appending preserves what is there

- **Given** a provenance file with one supersession entry and a `cluster_run` block
- **When** a second entry is appended
- **Then** the list has both entries in order and `cluster_run` is byte-for-byte unchanged

#### Scenario: An incomplete entry is rejected

- **Given** an entry with no reason field
- **When** it is appended
- **Then** `ValueError` names the missing field and the file is not written

## MODIFIED Requirements

### Requirement: Run duration scaled to whole wingbeats

The module SHALL set each configuration's run duration to cover a fixed, configurable number of
**complete wingbeats** (library default 2; a corpus MAY request more, see "Corpus beat count is
chosen by the pre-registered settling rule") at the validated fixed timestep `dt = 5e-4`, via
`stop_time = n_wingbeats / f*` and `max_step = round(stop_time / dt)`. This guarantees every
configuration — including low-frequency ones where a fixed `stop_time = 1.0` would cover less than
one beat — captures whole periodic cycles. `dt` SHALL NOT be changed from the validated value.

This guarantee holds **only while `ns.fixed_dt` is the binding timestep constraint.** `ns.cfl` is an
independent limiter that can reduce the realized step below `ns.fixed_dt`; when it does, the run
exhausts `max_step` before reaching `stop_time` and terminates mid-wingbeat, silently. A corpus
SHALL therefore be generated with an `ns.cfl` value high enough that `ns.fixed_dt` binds for every
configuration at that corpus's grid resolution and kinematic range, and the resulting runs SHALL be
verified to have held their nominal timestep (see the run-metadata capability's observed-timestep
fields and the post-run acceptance gate below).

The corpus drivers (`examples/prelim_sweep/generate_sweep.py`,
`examples/prelim_sweep_fine/generate_full_corpus.py`) SHALL expose the beat count as
`--n-wingbeats` and record it in the manifest's `n_wingbeats`. A driver SHALL refuse to write into
an output directory whose existing `sweep_manifest.json` records a different `n_wingbeats`, so a
corpus of one length cannot be overwritten in place by another. Tests that regenerate a committed
corpus SHALL read `n_wingbeats` from that corpus's own manifest.

#### Scenario: Duration matches the per-frequency formula

- **Given** `frequency_fstar = 0.85`, `n_wingbeats = 2`, `dt = 5e-4`
- **When** `derive_run_duration` is called
- **Then** `stop_time ≈ 2.3529` (= 2 / 0.85) and `max_step = 4706` (= round(2.3529 / 5e-4))

#### Scenario: Every config covers at least the requested whole wingbeats

- **Given** the default 27-config sweep with `n_wingbeats = 2`
- **When** each generated input file is parsed
- **Then** for every config `stop_time * frequency_fstar ≥ 2` (at least two complete beats)
- **And** every config retains the validated `ns.fixed_dt = 0.0005`

#### Scenario: A longer corpus scales every configuration by the same beat count

- **Given** `n_wingbeats = 6` and `dt = 5e-4`
- **When** `derive_run_duration` is called for `frequency_fstar` 0.85, 1.00 and 1.15
- **Then** `max_step` is 14118, 12000 and 10435, and `stop_time * frequency_fstar = 6` for each

#### Scenario: A driver refuses to overwrite a corpus of a different length

- **Given** an output directory whose `sweep_manifest.json` has `n_wingbeats = 2`
- **When** a corpus driver is run on it with `--n-wingbeats 6`
- **Then** it exits non-zero with a message naming both beat counts, and no file in the directory
  is changed

#### Scenario: Omitting the flag reproduces the committed 2-beat corpora

- **Given** either corpus driver run without `--n-wingbeats`
- **When** its output is compared with the committed `examples/prelim_sweep` or
  `examples/prelim_sweep_fine` decks and manifest
- **Then** they are byte-identical

#### Scenario: The requested wingbeats are actually completed, not merely requested

- **Given** a completed corpus whose decks request `n_wingbeats = 2`
- **When** each configuration's observed run output is inspected
- **Then** every configuration's `cycles_completed` reaches `n_wingbeats` to within the writer's
  one-step-short convention, and no configuration terminated on `max_step` with a CFL-reduced
  interior timestep

### Requirement: An overridden parallelism without an explicit deadline auto-scales the deadline instead of silently reusing a stale default

`cluster/argo/scripts/submit_workflow.sh full` SHALL compute a replacement `activeDeadlineSeconds`
instead of leaving the committed value unpatched whenever `--parallelism` is overridden and
`--active-deadline-seconds` is **not** explicitly given. The computed value
SHALL be derived from the actual config count in the resolved `--corpus-dir`'s
`sweep_manifest.json` (not a hardcoded constant) and from each config's `max_step`, so that it
scales with run length:

`hours = ceil( sum(max_step) * s_mean / 3600 / parallelism + 2 * max(max_step) * s_max / 3600 )`

where `s_mean` and `s_max` are the measured mean and maximum wall-clock seconds per step for the
manifest's grid, and the second term covers two retries of the longest configuration. For the
256x128x256 grid the measured values SHALL be `s_mean = 2.311` and `s_max = 3.302` (the 27
committed `run_metadata_<config>.json` of `examples/prelim_sweep_fine`, run
`force-surrogate-sweep-vgn92`). For a grid with no measured values the script SHALL NOT fall back
to another grid's: it SHALL fail with a message asking for `SECONDS_PER_STEP_MEAN` and
`SECONDS_PER_STEP_MAX` or an explicit `--active-deadline-seconds`. A manifest with zero configs
SHALL be rejected, not given a zero deadline. An explicitly-supplied
`--active-deadline-seconds` SHALL always take precedence over the auto-computed value, and no
auto-scale computation SHALL be attempted when an explicit value is given.

#### Scenario: Overriding parallelism alone auto-scales the deadline

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` declares exactly 3 configs (the real
  `{"configs": [...]}` schema), and no `--active-deadline-seconds`
- **When** the command runs
- **Then** the sed-patched temporary copy's `activeDeadlineSeconds` equals
  `ceil(3 * 3600 * 2.311 / 3600 / 1 + 2 * 3600 * 3.302 / 3600) * 3600 = ceil(13.537) * 3600 =
  50400` seconds, for a manifest whose grid is `256 128 256` and whose three configs each have
  `max_step = 3600` — not the committed default, and not a value independent of the manifest's
  step counts

#### Scenario: Doubling the run length raises the deadline

- **Given** two manifests identical except that every `max_step` in the second is twice the
  first's
- **When** auto-scale runs on each at the same parallelism
- **Then** the second deadline is strictly larger than the first

#### Scenario: A grid with no measured rate is not sized from another grid's

- **Given** a manifest whose grid is `64 32 64`, `--parallelism 1`, no
  `--active-deadline-seconds`, and neither `SECONDS_PER_STEP_MEAN` nor `SECONDS_PER_STEP_MAX` set
- **When** the command runs
- **Then** it fails before `argo submit` with a message naming both environment variables and the
  `--active-deadline-seconds` alternative

#### Scenario: The fine-grid rates are the committed corpus's measured values

- **Given** the 27 committed `run_metadata_<config>.json` files of `examples/prelim_sweep_fine`
- **When** `wall_time_s / max_step` is computed per config
- **Then** the mean rounds to 2.311 and the maximum to 3.302, the two constants in the script

#### Scenario: An explicit deadline is never overridden by auto-scale

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1
  --active-deadline-seconds 999999 --no-provision` with a `--corpus-dir` whose manifest is
  missing or otherwise unreadable
- **When** the command runs
- **Then** the command succeeds with `activeDeadlineSeconds: 999999` in the patched copy — the
  auto-scale computation is never attempted, so an unreadable manifest under this combination of
  flags does not cause a failure

#### Scenario: Auto-scale falls back to a working Python interpreter

- **Given** a `full` invocation where auto-scale is eligible to fire, and `python3` resolves on
  `PATH` but is non-functional (e.g. a Windows App-Execution-Alias stub), while `python` on
  `PATH` is a genuinely working interpreter
- **When** the command runs
- **Then** auto-scale succeeds by falling back to `python` — the script probes each candidate
  by actually invoking it, not merely checking that `PATH` resolution succeeds, and the broken
  `python3` is never used for the real computation

#### Scenario: Auto-scale fails clearly when no working interpreter is found at all

- **Given** a `full` invocation where auto-scale is eligible to fire, and neither `python3` nor
  `python` on `PATH` is a genuinely working interpreter
- **When** the command runs
- **Then** it fails fast with a clear, `die`-style error message before invoking `argo submit`,
  not an uncaught interpreter error

#### Scenario: Auto-scale fails clearly, not with a raw crash, when the manifest is unreadable

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 2 --no-provision` with a
  `--corpus-dir` that exists but has no `sweep_manifest.json`, and no `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear, `die`-style error message before invoking `argo submit`,
  not an uncaught interpreter traceback

#### Scenario: Auto-scale fails clearly, not with a raw crash, when the manifest exists but is malformed

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 2 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` exists but is malformed (invalid JSON, missing the
  `"configs"` key, or `"configs"` present but not a list), and no `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear error message before invoking `argo submit`, not an
  uncaught interpreter traceback and not a silently wrong deadline computed from a misread value

#### Scenario: Auto-scale refuses to fire when `--corpus-dir` and `--workspace-hostpath` name different corpora

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` and `--workspace-hostpath` whose basenames do not match, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear error before invoking `argo submit` — `--no-provision`
  skips `provision()`'s own basename-match guard, so auto-scale (which reads `--corpus-dir`'s
  manifest independently of `--workspace-hostpath`) must not silently compute a deadline from
  the wrong corpus's config count

#### Scenario: An explicit deadline never triggers the basename-consistency check

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --active-deadline-
  seconds 999999 --no-provision` with a `--corpus-dir` and `--workspace-hostpath` whose
  basenames do not match
- **When** the command runs
- **Then** the command succeeds with `activeDeadlineSeconds: 999999` — the basename-consistency
  check is scoped to the auto-scale trigger path only, and an explicit `--active-deadline-
  seconds` never enters that path

#### Scenario: An invalid `--parallelism` is rejected before auto-scale is ever attempted

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (or `-1` or `abc`),
  no `--active-deadline-seconds`, and a `--corpus-dir` whose manifest exists and is readable
- **When** the command runs
- **Then** it fails fast with a clear "positive integer" error message and no interpreter
  traceback appears in its output — `--parallelism` is validated before it is ever passed to the
  auto-scale computation, not after

#### Scenario: A degenerate config count does not crash the formula

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` declares zero configs, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails before `argo submit` with a clear message that the manifest lists no configs
  — a zero-config manifest is an error, not a zero-hour deadline

#### Scenario: A very large parallelism does not overflow or underflow the formula

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1000000 --no-provision`
  with a `--corpus-dir` whose `sweep_manifest.json` declares 3 configs, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** for a `256 128 256` manifest whose three configs each have `max_step = 3600`, the
  computed `activeDeadlineSeconds` equals `25200` (`ceil(0.0000069 + 6.604) * 3600 = 7 * 3600`):
  the retry term remains and the result is a sane, correctly rounded value, not a tiny, negative
  or overflowed one

### Requirement: retryStrategy backoff can cover the full configured retry limit

`cluster/argo/workflow-templates/force-surrogate-single-config.yaml`'s `retryStrategy.backoff` SHALL
cap cumulative retry backoff (`maxDuration`) high enough that all `limit`-configured retries can
actually be attempted before Argo gives up, given the corpus's real per-attempt runtimes and
observed preemption frequency — not a value that exhausts itself partway through the configured
retry budget, as `maxDuration: "30m"` did for `duration: "2m"`/`factor: 2`.

`maxDuration` SHALL be documented and sized as **wall-clock measured from the first attempt's
start**, which includes each attempt's own runtime, not merely the sum of the backoff intervals. At a
per-attempt cost of hours, a value chosen against the backoff series alone silently permits far fewer
attempts than the configured `limit`.

Because a run's length now varies with the corpus's `n_wingbeats`, the per-attempt cost SHALL be
taken from the submitted manifest: `max(max_step) * s_max` for the manifest's grid (the same
`s_max` as the deadline auto-scale). `cluster/argo/scripts/submit_workflow.sh` SHALL set
`maxDuration` at submission to at least `(limit + 1)` such attempts plus the cumulative backoff
sequence. If Argo cannot take `maxDuration` from a parameter, the committed value SHALL be sized
for the longest corpus the repository commits, and a test SHALL fail when a committed manifest
needs more.

`retryPolicy` SHALL be `"Always"`. `"OnFailure"` sets `retryOnError = false` and cannot cover a pod
deleted by preemption, which Argo surfaces as node phase `Error` with message `pod deleted`.
`"OnError"` is unsuitable in the opposite direction: it sets `retryOnFailed = false`, abandoning
application-level failures, and preemption is not classified consistently as `Error` across
platforms. Only `"Always"` covers both.

#### Scenario: The full retry sequence fits within maxDuration

- **Given** the `force-surrogate-single-config` WorkflowTemplate's `retryStrategy`
- **When** its `backoff` block is inspected
- **Then** `limit: 5`, `duration: "2m"`, `factor: 2` are unchanged, and `maxDuration` accommodates
  `limit + 1` attempts at the per-attempt cost of the longest configuration of every committed
  corpus manifest (`max(max_step) * s_max`) plus the cumulative backoff sequence
  (`2m+4m+8m+16m+32m = 62m`), so a config that needs multiple preemption-driven retries is not cut
  off by `maxDuration` before its configured `limit` is exhausted

#### Scenario: A preempted pod is retried

- **Given** the committed single-config WorkflowTemplate
- **When** its `retryStrategy` is inspected
- **Then** `retryPolicy` is `"Always"`, so a pod deleted by preemption (node phase `Error`, message
  `pod deleted`) is retried rather than abandoned

