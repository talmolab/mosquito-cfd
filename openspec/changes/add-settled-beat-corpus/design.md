# Design: add-settled-beat-corpus

## Context

Measured facts this design rests on (sources in parentheses):

- Steps per beat are `1 / (f* · dt)`: 2352.9 (`f085`), 2000 (`f100`), 1739.1 (`f115`). A 2-beat
  corpus is 109,656 steps (`sweep_manifest.json`).
- The beat count is already a parameter: `N_WINGBEATS = 2` in `constants.py`, passed through
  `derive_run_duration` and `generate_sweep(n_wingbeats=...)`. Neither driver exposes it.
- The fine corpus cost 70.70 GPU-h on A40s: mean 2.311 s/step, maximum 3.302 s/step
  (`s35_f085_p30`, 4.32 h) (27 committed `run_metadata_<config>.json`).
- The fine corpus writes about 513 MB per plotfile and about 2.3 GB per checkpoint
  (`docs/field_surrogate/roadmap.md`).
- The fine corpus ran image `sha256:92817878…a47`; the coarse corpus ran `sha256:07625ce4…24d3`.
  gh-04 already holds `92817878…`.
- Nothing downstream selects "beat 2". The trainer, both figure modules and the corpus guards use
  `wingbeat >= 1`; the bench picks the largest common beat. In an N-beat corpus `wingbeat >= 1`
  would pool beats 2..N.
- Free space on 2026-11-23: `Z:` (cluster share `hpi_dev`) about 36 TB; `G:` about 27 TB; gh-04
  1.7 TB; this workstation's `C:` 156 GB.

Lessons that constrain the design (`openspec/project.md`, Verification Principles; issue #92):
validate the worst case; a pilot's result is scoped to the physics it ran under; a check needs an
external reference; a mandatory check must record its result.

## D1. Three pull requests, with the criterion merged before any run

| PR | contents | then |
|---|---|---|
| 1 | settling metric, pre-registration, long-run deck generator, control checks, spec deltas for Stage 1 | user go-ahead → gh-04 controls → user go-ahead → long runs |
| 2 | Stage 1 results and decision record; regeneration tooling parametrized by the chosen N | user go-ahead → cluster smoke → user go-ahead → full sweeps |
| 3 | the two regenerated corpora, acceptance records, storage manifests | archive the change |

The run records cite the merge commit of PR 1 and the SHA-256 of `PREREGISTRATION.md`, so the
criterion is provably older than the data it judges.

## D2. The settling metric

For one run and one target `j` of `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`:

1. **Beats.** Beat `b` (1-based) is the rows with `wingbeat == b - 1`. A beat is complete when it
   has at least 95% of `1 / (f* · dt)` rows. `B` is the last complete beat. Incomplete beats are
   ignored and named in the report.
2. **Resampling.** Each beat is resampled onto 256 phases `k/256` by periodic linear
   interpolation in the extractor's `phase` column, giving `w_b,j`. This is E0b's resampling. The
   whole cycle is used; E0b's `phase >= 0.05` mask was for the start-up beat and is not applied.
3. **Scale.** `P_j = max |w_B,j|`, the last complete beat's peak.
4. **Step change.** `s_b,j = rms(w_b,j − w_{b−1},j) / P_j` for `b = 2..B`.
5. **Distance to the last beat.** `D_b,j = rms(w_b,j − w_B,j) / P_j`.
6. **Tail bound.** The last beat is not the periodic state. With contraction ratio
   `ρ_j = max(s_b,j / s_{b−1},j)` over `b = B−2, B−1, B`, the last beat is at most
   `T_j = s_B,j · ρ_j / (1 − ρ_j)` from the limit, provided later steps keep shrinking at least
   that fast. If `ρ_j >= 1` the run is **not contracting** and `T_j` is infinite. A ratio whose
   denominator is below `1e-4` is dropped as noise; if none remain, `T_j = s_B,j`.
7. **Estimated distance to the periodic state.** `E_b,j = D_b,j + T_j`.
8. **Verdict.** Beat `b` is settled when `E_c,j <= 0.01` for every target `j` and every beat
   `c = b..B`. `N*_run` is the smallest settled beat, or undefined.

The maximum absolute difference over phase is reported beside each RMS value but does not gate.
RMS is the gate because the surrogate error it is compared with (1.1–1.8% of peak) is an RMS
figure, and so E0b's coarse tables stay comparable.

**Why a tail bound and not "distance to the last beat".** On the coarse grid `s45_f100_p30` moved
0.60% per beat at beat 6 with steps shrinking by about 0.59 per beat, so beat 6 was about 0.9%
from the limit while its "distance to beat 6" was zero. The bound makes the reference's own error
part of the number. Its assumption (geometric decay continues) is stated in every report.

`surrogate_bench/gate.py` already computes a `late_beat` yardstick. This change does not import or
edit bench code (another session owns it). Consolidating the two is a follow-up once the bench
change is archived.

## D3. Pre-registered decision rule

Runs: three configurations × two grids. `N* = max N*_run` over the six runs.

| outcome | action |
|---|---|
| every run has a settled beat | both corpora are generated with `n_wingbeats = N*` |
| a 6-beat run has no settled beat but the 8-beat run does | extend that run to 8 beats, then re-apply the rule |
| the 8-beat run has no settled beat, or any run is not contracting | **stop**. No regeneration. Report to the user, who decides between longer runs and a different tolerance. A changed tolerance is recorded as a deviation, with the original verdict kept |
| `N* > 6` | proceed only with the user's explicit approval of the higher cost (283 GPU-h at 8) |
| `N* < 5` | use `N*`; no floor is applied. The issue title's "5+" was an expectation, not a rule |

There is no safety margin for the 24 configurations not sampled. The protection is D6: all 54
regenerated runs are checked with the same function, and the corpus is not accepted if any fails.

Both corpora use the same N, because the comparison figure requires equal beat counts.

## D4. Stage 1 runs and controls

**Decks.** `examples/settling_check/generate_decks.py` takes each committed corpus deck and
changes only `max_step` and `stop_time` (through `derive_run_duration`) and adds
`amrex.the_arena_init_size = 12884901888` (the A5000's 24 GB cannot take AMReX's default arena).
For the coarse twins it also sets `amr.plot_int` to 20 frames per beat (D7). A test asserts the
diff against the corpus deck is exactly this key set. `ns.cfl`, `ns.init_iter`, `ns.fixed_dt`,
geometry and grid are untouched, so the result transfers to the regeneration.

**Image.** `ghcr.io/talmolab/mosquito-cfd@sha256:92817878…a47`, pulled by digest, with its
`com.mosquito-cfd.iamrex-commit` label checked against `docker/build-args.env`. The coarse twins
use the same image, which is the image both new corpora will use.

**Runner.** The existing local runner (`force_surrogate/runner.py`, `scripts/run_sweep.py`
patterns) so that the exact container command is recorded in each run record. E0b's command was
never saved.

**Controls, in order, each with a recorded result:**

| id | check | pass condition |
|---|---|---|
| C1 | 400 steps of the `s55_f115_p30` fine deck against the committed cluster run | identical time grid; raw `Fx..Mz` agree to `1e-10` of each column's peak |
| C2 | the same 400 steps as 200 + restart from checkpoint + 200 | agrees with C1 to the same tolerance → restarts are **admissible** for extending a run |
| C3 | after each long run: its first two beats against the committed corpus dataset | fine: `1e-10` of peak. Coarse (different image): reported; above `1e-6` of peak → stop and ask |
| C4 | realized timestep over all beats (`metadata_capture.realized_dt`) | fine: no step below nominal. A later beat that triggers the CFL limiter blocks regeneration |

C1 also measures seconds per step on gh-04. The long runs start only after the user has seen that
number and the projected wall time.

If C2 fails, a run that needs more beats is re-run from zero.

**Field settling (reported, not gated).** For the two `f* = 1.00` fine runs (2000 steps per beat,
so plotfiles fall on identical phases): the speed difference between beat `b` and the last beat
in the near-wing box, over the reference wing speed `u_ref`, as a median and as the fraction of
the box above 10%, per beat. The arithmetic is a pure, tested function; plotfiles are read with
the existing `field_surrogate` reader. `s55_f115_p30` is excluded because its beats are not a
whole number of plot intervals in a deck that must stay identical to the corpus deck.

**Outputs committed in PR 2** (`examples/settling_check/`): decks, `settling_manifest.json`, one
extracted `dataset.parquet` per grid, a run record per run (image, hardware, command, wall time,
seconds per step, realized timestep, control results), `settling_report.json`,
`settling_figure.png` with its metadata sidecar, and `DECISION.md` (the rule applied to the
numbers, and the chosen N).

## D5. New corpus directories, not in-place regeneration

`examples/settled_sweep` and `examples/settled_sweep_fine`. The 2-beat corpora become frozen
references.

- In-place regeneration would break, in one commit, the frozen raw-force hashes
  (`test_force_surrogate_scale_invariance.py`, whose comment calls a trip "a HALT, not a re-pin"),
  the surrogate provenance tests, both evidence figures, the three comparison figures, V3 and the
  bench's corpus pins. All of those reruns would have to land in the same pull request.
- With new directories `main` stays green, and each rerun is a small change that repoints one
  consumer.
- The old and new corpora can be compared directly (beat 2 against the settled beat, per
  configuration), which is itself a result worth a figure.

Cost: two more example directories until the 2-beat corpora are retired (D10, last row).

Guard against accidents: both drivers refuse to write into a directory whose existing
`sweep_manifest.json` records a different `n_wingbeats`.

`N_WINGBEATS = 2` stays the library default, so the byte-identity tests on the old corpora are
untouched. Regeneration tests are parametrized over the corpus registry and read `n_wingbeats`
from each manifest.

## D6. Guards and the training beat

- **Training beat.** `settling.training_wingbeat(manifest)` returns `n_wingbeats − 1`. For the
  2-beat corpora this is 1, which is what `wingbeat >= 1` selects today.
- **Symmetry ratio.** `settled_beat_symmetry_ratios` currently averages `wingbeat >= 1`. Over N
  beats a truncated final beat would be diluted and the guard would weaken. It becomes "the final
  requested beat". For N = 2 the result is bit-identical. The tolerance (0.012) is **not**
  re-tuned: the healthy maximum on the new corpora is measured and recorded, and a healthy value
  above 0.012 stops the work for investigation.
- **Settling acceptance.** `acceptance_gate` computes D2 for every configuration and requires
  `T_j <= 0.01` for the final beat, for all targets. The per-config values and the pass/fail
  result are written into `sweep_provenance.json` under `cluster_run.settling`.
- Row count equals `max_step`, the realized-timestep check, CC-F1 and the `wingbeat > 0` tripwire
  are unchanged.

## D7. Field capture for later visualization

What later figures and movies need, and what the corpus therefore writes:

| need | provision |
|---|---|
| the same phases in every beat and every configuration (beat-to-beat difference maps, phase-averaged fields, wing-frame POD, side-by-side movies across configurations) | **20 plotfiles per beat**: per-config `plot_int = round(steps_per_beat / 20)`, i.e. 118 / 100 / 87. Phase drift is at most 7 steps per beat (0.3% of a beat) |
| settling movies and "start-up to settled" figures for any configuration | plotfiles for **every** beat, not only the last |
| a smooth or zoomed movie of one configuration later, without paying for N beats again | **one checkpoint per beat boundary** (`check_int = round(steps_per_beat)`); the last beat can be re-run from its checkpoint at any cadence, provided C2 passed |
| coarse-versus-fine field comparisons | field capture on the **coarse** corpus too (about 8 MB per plotfile, about 26 GB in total at N = 6) |
| force traces for all beats | already kept: the extractor writes every beat to the parquet |

Today `plot_int = 100` gives 23.5 / 20 / 17.4 frames per beat at phases that differ between beats
for two of the three frequencies. `generate_sweep` gains `frames_per_beat` and
`checkpoints_per_beat` keyword arguments (default `None` = today's behaviour, so the old corpora
regenerate byte-identically). The manifest already records `plot_int` per config; `check_int` is
recorded when overridden, following the `init_iter` / `cfl` precedent.

Storage at N beats, fine grid: `27 × (20N + 1) × 0.513 GB` of plotfiles plus `27 × N × 2.3 GB` of
checkpoints.

| N | plotfiles | checkpoints | total |
|---|---|---|---|
| 5 | 1.40 TB | 0.31 TB | 1.71 TB |
| 6 | 1.68 TB | 0.37 TB | 2.05 TB |
| 8 | 2.23 TB | 0.50 TB | 2.73 TB |

The plotfile variable set is unchanged (the decks do not set `amr.plot_vars`).

## D8. Where the data lives

| data | home | why |
|---|---|---|
| decks, manifests, extracted parquet, per-config run metadata, reports, figures, storage manifest | git | small, reviewed, hash-checked by tests |
| raw runs (force CSV, `run.log`, plotfiles, checkpoints) of the new corpora | `Z:\users\eberrigan\mosquito-cfd\examples\settled_sweep{,_fine}\runs\` | it is the cluster workspace, so nothing is copied; about 36 TB free |
| Stage 1 raw runs | written on gh-04, then copied straight to `Z:\…\examples\settling_check_2026-11\` (`scp` from gh-04 to the share; never staged on `C:`) | gh-04 has no mount of the share |
| the 2-beat raw runs already on `Z:` | left in place | deleting them is a user decision, taken when the 2-beat corpora are retired |

`storage_manifest.json` in each new corpus directory lists, per configuration: the run directory,
its byte size, the plotfile steps present, the checkpoint steps present, and SHA-256 of the force
CSV and `run.log`. A later figure can then verify it reads the intended run, and missing data is
detectable from a checkout. It is written by a tested function from a directory listing and
verified against the manifest's expected plotfile and checkpoint steps.

Not decided here (open question 4): whether `Z:` is backed up and whether a second copy is wanted.

## D9. Cluster sizing from step counts (#101)

- **Deadline.** `ceil(Σ max_step · s_mean / 3600 / parallelism + 2 · max(max_step) · s_max / 3600)`
  hours: the mean cost of the whole manifest plus two retries of its longest configuration at the
  worst measured rate. For 256×128×256, `s_mean = 2.311` and `s_max = 3.302` (measured on run
  `vgn92`, which is what #101 asks for). For any other grid the script refuses to guess: it needs
  `SECONDS_PER_STEP_MEAN` / `SECONDS_PER_STEP_MAX` or an explicit `--active-deadline-seconds`.
  The coarse values come from the coarse smoke run.
- **Retry budget.** `maxDuration` must cover `limit + 1` attempts of the longest configuration:
  about 78 h at N = 6, against today's fixed 20 h. It becomes a workflow parameter computed by the
  submit script. If Argo does not substitute parameters in `backoff.maxDuration` (to be verified
  with `argo lint` and the smoke run), the fallback is a static value sized for N = 8.
- **Smoke.** `SMOKE_MAX_STEP` is read from the manifest for `SMOKE_CONFIG_NAME`; the literal 3478
  goes away. The smoke run stays a full-length run of the CFL-worst configuration and is kept as
  that configuration's corpus member, as before.
- **Stale 24 h figures** in the runbook, `cluster/argo/README.md` and the spec are corrected.
- **Risk kept open.** A preempted fine pod restarts from zero and can lose up to 13 h at N = 6.
  The last full sweep had no preemptions in 24 h. Resume-on-retry is not in this change; if C2
  passes, a follow-up issue proposes it.

## D10. Downstream reruns (list only)

| rerun | code it needs first |
|---|---|
| force surrogates, coarse and fine (5 seeds each) | `train.py`: select `settling.training_wingbeat`, not `wingbeat >= 1` |
| evidence figures, both corpora | `evidence_figure.py`: `rows_per_wingbeat` assumes one scored beat per config |
| three coarse-vs-fine figures | `comparison_figure.py`: guard 8, prediction coverage, `beat_sentence` |
| V3 scale-invariance figure and summary | repoint to the new coarse predictions |
| bench PR 2 results | bench scope and gate strings ("second-beat data from 2-beat runs"); owned by the bench session |
| README tables in both corpus READMEs | regenerated numbers |
| field-surrogate reader and roadmap | corpus pointer; plotfile counts change from 441/369/324 |
| retire the 2-beat corpora | frozen-hash test policy; deleting 0.84 TB of raw runs is the user's call |

## Risks

| risk | mitigation |
|---|---|
| the fine grid settles more slowly than the coarse grid and 8 beats are not enough | D3 stops instead of guessing; C2 allows extension by restart |
| geometric decay does not hold (slow wake mode) | `ρ >= 1` is a stop condition; the all-config check in D6 catches a configuration that behaves differently |
| gh-04 is much slower than 7.5 s/step | C1 measures it before the long runs are approved |
| a later beat triggers the CFL limiter | C4 on the CFL-worst configuration, on the fine grid, over 6 beats |
| a 3-day sweep is hit by preemption | deadline and retry budget re-derived (D9); partial sweeps resume with a trimmed manifest (existing runbook step 5) |
| three configurations do not represent 27 | D6 checks all 54 runs after regeneration |
