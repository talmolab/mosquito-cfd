# Design: add-settled-beat-corpus

Conventions:
- **Beat `b`** is 1-based and is the rows with `wingbeat == b − 1` (the extractor's 0-based
  column).
- **N** is a beat count.
- **Peak** is per target, per run.
- Percentages are RMS, in percent of peak, unless stated otherwise.
- **E0** and **E0b** are exploration studies on branch `explore-surrogate-experiments` (`b99c7b2`,
  never merged). E0 compares beats 1 and 2 of all 27 committed configurations on both grids. E0b is
  three local 6-beat coarse runs.

## Context

These facts were measured or read from the code; sources are in parentheses.

- **Steps per beat** are `1 / (f*·dt)`: 2352.94 (`f085`), 2000 (`f100`) and 1739.13 (`f115`).
- **The beat count is a parameter.** `N_WINGBEATS = 2` is threaded through `derive_run_duration`
  and `generate_sweep`. Neither driver exposes it.
- **No consumer selects "beat 2"; they all use `wingbeat >= 1`.** This applies to the trainer
  (`filter_converged_beat`, `build_phase_only_baseline`), both figure modules and the corpus
  guards. On an N-beat corpus that would pool beats 2..N. Both committed corpora contain only
  beats 0 and 1.
- **Fine corpus cost on A40s: 70.70 GPU-h.**
  - Mean 2.311 s/step (unweighted), 2.321 (step-weighted).
  - Maximum 3.302 s/step (`s35_f085_p30`, gpu-node8).
  - 23 h 51 min at parallelism 3.
  - Source: 27 committed `run_metadata_<config>.json`.
- **Storage per file.** Fine: plotfile ≈513 MB, checkpoint ≈2.3 GB. Coarse (E0b, measured):
  plotfile 8.2 MB, checkpoint 25 MB.
- **Images.** The fine corpus used `sha256:92817878…a47`; the coarse corpus and E0b used
  `sha256:07625ce4…24d3`. E0b's local rerun matched the committed coarse corpus in 3999 of 4000
  rows; row 1 differed at round-off (Fy 5.7e-13, My 1.7e-12).
- **Time-triggered output.** AMReX `amr.plot_per` / `amr.check_per` fire at the first step whose
  end time reaches the next multiple. They do not change `dt`; only `stop_time` clamps the final
  step. IAMReX does not override either hook.
  - Sources: `AMReX_Amr.cpp:2360–2445` in the pinned image; `NavierStokesBase.cpp:1161–1170`.
  - The force CSV's `time` is the step's start time; a plotfile's time is `(iStep + 1)·dt`.
- **Restart is not faithful (#205).**
  - `Particles::Restart` truncates the force CSV by line count, so the two extra `iStep == 0`
    rows that `init_iter = 2` writes shift it.
  - It also re-initialises the wing with zero marker velocity before the first forcing step
    (`DiffusedIB.cpp:1373–1450`).
- **`ns.init_iter = 0` plotfiles carry velocity.** E0b's coarse plotfiles were written at
  `init_iter = 0`, and the project's CC-F1 check passes on `plt12000` (x_velocity −21.1 to 4.2 in
  the near-wing box). The live CC-F1 requirement says the opposite; that discrepancy is #206.
- **E0b, coarse, `s45_f100_p30`.**
  - CF_z step ratios at beats 4–6: 0.64, 0.65, 0.58.
  - Mean CF_z still falls 1.4% per beat at beat 6.
- **E0 ranking.** Stroke 35° with pitch 30° is worst on both grids; `s45_f100_p30` ranks 5th.

**Lessons that constrain this design** (`openspec/project.md` Verification Principles; #92):
- validate the worst case;
- a pilot's result applies only to the physics it ran under;
- a check needs an external reference;
- a mandatory check must record its result.

## D1. Four PRs, one change, a staged delta

- **Stage 1 delta.** PR 1's spec delta carries only the Stage 1 requirements.
- **Stage 2 delta.** PR 2 adds the Stage 2 requirements (drafted in `stage2-spec-draft.md`) in the
  same commits as their code.
- **Order.** PR 2 may be written and reviewed while the gh-04 runs go, but it **merges only after
  PR 3's decision is `regenerate`** (task 13.2).
  - On `stop`, the PR 2 branch is closed unmerged, PR 3 still lands the results, and the change
    is archived after PR 3 with the Stage 1 delta only.
  - Either way the effective spec (live specs plus active deltas) is never ahead of `main`.
- **Branches.** PR 1 uses the existing branch. PRs 2–4 each start on a fresh branch from
  `origin/main`.

## D2. The settling metric

**Constants**, pinned in code, in `PREREGISTRATION.md` and in the spec:

| constant | value | meaning |
|---|---|---|
| `SETTLED_TOLERANCE` | 0.01 | 1% of peak, RMS |
| `COMPLETE_FRACTION` | 0.95 | a beat with fewer rows than this fraction of `1/(f*·dt)` is incomplete |
| `MIN_BEATS` | 5 | fewest complete beats the metric accepts |
| `FIRST_RATIO_BEAT` | 4 | ratios never use the start-up steps `s_2`, `s_3` |
| `NOISE_FACTOR` | 3 | a step is noise when it is at most `NOISE_FACTOR · J` |
| `MAX_NOISE` | 0.002 | if `NOISE_FACTOR · J` exceeds this, the measurement is too noisy to judge; the noisiest committed final beat has `3J = 8.1e-4` |

For one run, target `j` (one of `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`) and timestep `dt` (the
manifest's `fixed_dt`, passed in):

1. **Beats.**
   - Beats come from the extractor's `wingbeat` and `phase`, never recomputed.
   - A beat is complete when it has at least `COMPLETE_FRACTION / (f*·dt)` rows. `B` is the last
     complete beat.
   - An incomplete beat before `B`, or a duplicate or non-increasing `phase` within a beat, raises.
     So does `B < MIN_BEATS`.
2. **Comparison at sample resolution.**
   - `dist(a, c)` is the RMS over beat `a`'s own samples of `w_a(φ_i) − L_c(φ_i)`, divided by `P`.
     `L_c` is periodic linear interpolation of beat `c` in `phase`, and `P = max |w_B|` over beat
     `B`'s samples.
   - There is no 256-point grid. A coarse grid hits or misses the one-sample force spikes at stroke
     reversal, which put up to 1e-3 of noise into a beat difference, even at `f100` where beats
     share sample phases.
3. **Steps and distances.** `s_b = dist(b, b − 1)` for `b = 2..B`, and `D_b = dist(b, B)`.
4. **Jitter.**
   - `J = rms(w_B[i−1] − 2·w_B[i] + w_B[i+1]) / (8·P)`, over the interior samples of beat `B`
     (no wrap).
   - `Δ²/8` is the maximum error of linear interpolation at half a sample spacing for a locally
     quadratic signal. So `J` bounds the error that off-integer steps per beat add to `s_b`.
   - Measured: at most 2.7e-4 on the final beats of both committed corpora (f085 worst; f100 and
     f115 below 6.4e-5), and about 2e-5 on E0b's beat 6.
5. **Ratios** for `b = max(FIRST_RATIO_BEAT, B − 2) .. B`, with noise floor `ν = NOISE_FACTOR · J`:
   - both `s_{b−1}` and `s_b` at most `ν`: the ratio is skipped (noise);
   - only `s_{b−1}` at most `ν`: the run is growing, so it is **not contracting**;
   - otherwise `r_b = s_b / s_{b−1}`.
6. **Contraction.** `ρ = max r_b + max(0, r_last − r_first)`, over the kept ratios in beat order.
   The second term widens the bound when the ratios are rising, as E0b's `s45_f100_p45` CF_my does
   (0.40 → 0.64). `ρ ≥ 1` means not contracting.
7. **Tail bound** (how far beat `B` still is from the periodic state):
   - not contracting: `T = ∞`;
   - every ratio skipped: `T = 2 · max s_b` over the ratio beats, which assumes `ρ ≤ 2/3`;
   - otherwise `T = s_B · ρ / (1 − ρ)`.

   The geometric bound holds while later steps shrink by at most `ρ`. RMS is a norm, so the
   triangle inequality gives `‖w_B − w_∞‖ ≤ Σ_{k>B} s_k`.
8. **Estimated distance to the periodic state:** `E_b = D_b + T`.

**What is reported alongside.** The maximum absolute difference over samples is reported beside
each RMS value and does not gate. A 256-point resampling is kept only for figures and for
reproducing E0b's published tables.

**Stress tests** (synthetic, `ν = 6e-5`):

| case | result | true distance |
|---|---|---|
| ratios rising 0.53 → 0.71 | `T = 1.44%`, fails | 1.35% |
| a slow mode (ratio 0.96) just below 1e-3 | `T = 1.73%`, fails | 1.33% |
| growth by ×10 per beat starting at 1e-6 | not contracting | — |

**On the E0b coarse runs:**
- `s45_f100_p30`: CF_z `T = 1.168%`; no settled beat within 6.
- `s45_f100_p45`: CF_my `ρ = 0.812` (rising ratios), `T = 1.007%`; no settled beat within 6, by a
  hair.

`surrogate_bench/gate.py` has a related `late_beat` yardstick. This change does not import or
edit bench code; consolidation is a follow-up (D10).

## D3. Pre-registered decision rule

For a run with `B` complete beats and a candidate `N` with `MIN_BEATS ≤ N ≤ B`, **pass(N)**
requires, for every target:

- **(a) Truncated:** the metric on the run's first `N` beats alone is contracting with
  `T ≤ SETTLED_TOLERANCE`. This is the test the regenerated corpus faces (D6).
- **(b) Full:** on the full run, `E_N ≤ SETTLED_TOLERANCE` and the run is contracting.

`N*_run` is the smallest `N` for which pass(N′) holds for every `N′` from `N` to `B`.
`N* = max N*_run` over the six runs (three configurations × two grids).

Both corpora use `N*`:
- the coarse-versus-fine comparisons need the same beat on both grids;
- one count keeps the manifests comparable.

The cost is that the slower grid sets the count for both, for example about 71 GPU-h more on the
fine grid if the coarse grid needs 8 and the fine 6.

| outcome | action |
|---|---|
| any run has no `N*_run`, is not contracting on its full length, or has `NOISE_FACTOR · J > MAX_NOISE` for a target | `stop`: no regeneration; report to the user |
| every run has `N*_run` and `N* > 6` | `regenerate_needs_cost_approval` |
| otherwise | `regenerate` |

**Precedence:** `stop`, then `regenerate_needs_cost_approval`, then `regenerate`. No margin is
added to `N*`. Changing the tolerance after the data exist is recorded as a deviation next to the
original verdict, never substituted for it.

**Expected outcome, honestly.** On the coarse 6-beat data, even the centre configuration misses at
6 beats under this rule (CF_my 1.007%), and the 30° configuration misses by 25%. With 8 beats the
likely outcomes are `regenerate_needs_cost_approval` with `N*` of 7–8, or `stop`.

**Precedence proof.** It is squash-safe and attested, not proven by CI.

- **The constants block.** `PREREGISTRATION.md` holds the constants in an anchored block.
- **What each run records.** Each gh-04 run starts from a clean checkout of a `main` SHA that is
  an ancestor of `origin/main`. The run record stores that SHA and the SHA-256 of
  `PREREGISTRATION.md`, `settling.py` and `generate_decks.py`.
- **What CI checks** (from PR 1 on):
  - the committed `PREREGISTRATION.md` and `generate_decks.py` hash to the recorded values, or a
    `deviations.json` entry `{file, old_sha256, new_sha256, reason, pr}` explains the difference;
  - once `DECISION.md` or `settling_report.json` exists, the number of run records equals the
    number of runs declared in the settling manifest and is greater than zero.

  No test reads git history; CI checkouts are shallow.
- **What it does not prove.** The criterion predates the **fine-grid** and 8-beat data. It was
  tuned with the E0b coarse 6-beat data in view, and that data is also a test fixture.
  `PREREGISTRATION.md` says so.
- **Recomputation.** `check_settling.py` recomputes everything from the committed datasets with
  the current code, and reports whether `settling.py` differs from the hash recorded at run time.

## D4. Stage 1 runs and controls

**Decks.** `examples/settling_check/generate_decks.py` starts from each committed corpus deck,
parsed with `metadata_capture.parse_deck`. The declared differences are:
- `max_step` and `stop_time` from `derive_run_duration(f*, 8)`;
- `amrex.the_arena_init_size = 12884901888` (the A5000's 24 GB cannot take AMReX's default
  arena);
- `amr.plot_int = -1`, `amr.check_int = -1`, `amr.plot_per = 1/(20·f*)` and
  `amr.check_per = 1/f*`.

The set of differing keys must equal this set. `ns.cfl`, `ns.init_iter`, `ns.fixed_dt`, geometry
and grid are untouched; coarse keeps `ns.init_iter = 0`. Stage 2 decks are tested against these
decks (task 13.4), so the settling result transfers.

**Images.** Each grid uses the image its 2-beat corpus ran:
- fine: `ghcr.io/talmolab/mosquito-cfd@sha256:92817878…a47`;
- coarse: `…@sha256:07625ce4…24d3`.

Both are pulled by digest, and each image's `com.mosquito-cfd.iamrex-commit` label is recorded.
The new corpora use the same images, so each extends its predecessor like for like.

**Controls.** Each result goes into the run record. The settling manifest declares which controls
apply to which run, and the report is `controls_incomplete` while any declared control is missing.

| id | applies to | check | pass |
|---|---|---|---|
| C1 | once per grid, `s55_f115_p30` | the first 400 steps against the committed corpus force CSV (its SHA-256 recorded) | every value within `1e-9 · max |column|` |
| C3 | every long run | its first two beats against the committed 2-beat corpus | the same tolerance |
| C4 | every long run | the realized interior timestep, from `run.log` | no interior step below nominal `ns.fixed_dt`; the final step is clamped by `stop_time` and excluded |

- **Tolerance.** `1e-9 · max |column|` sits about four orders of magnitude above the round-off E0b
  saw and well below any physical difference.
- **Rate check.** C1 also measures seconds per step on gh-04. The long runs start only after the
  user has seen that rate and the projected wall time.
- **Why C1 and C3 matter.** They are external checks: each run must reproduce the corpus it will
  replace.
- **No restart control.** Restart equivalence is not tested. It is known to fail (#205), and no
  Stage 1 run restarts.

**Known answers on real data.** The E0b coarse 6-beat datasets are committed as test fixtures,
needed columns only:
- `s45_f100_p45`: `experiments/e0b_long_run/outputs/long_run.parquet`, blob `f232bca`;
- `s45_f100_p30`: `outputs_s45_f100_p30_fields/long_run.parquet`, blob `ef8f74a`.

Their run records say `git_dirty: true`, which the fixture README notes. The tests:
- **Reproduce E0b's own tables.** With E0b's 256-point resampling, the `phase ≥ 0.05` mask on the
  differences and the peak over all 256 points, the step changes match E0b's beat-to-previous
  tables to `5e-5`.
- **Apply the pre-registered rule.** `s45_f100_p30` gives CF_z `T = 0.01168 ± 1e-4` and no settled
  beat. `s45_f100_p45` gives CF_my `T = 0.01007 ± 1e-4` and no settled beat.

**Reported, not gated.**
- **Near-wing field change**, for all three fine runs. With time-triggered plotfiles every beat has
  frames at the same phases, to within one step.
  - The report gives the median, and the fraction above 0.1, of `|u_b − u_B| / u_ref` (vector
    difference norm) for each beat and frame.
  - The region is the near-wing box `(1, 0, 2.5)–(7, 4, 5.5)`, a constant in `settling.py`.
  - `u_ref` comes from `compute_force_reference(...).u_ref`.
  - Plotfiles are read with the existing `field_surrogate` reader.
- **Mean CF_z per beat** and its drift per beat (D11).

**Outputs** (committed in PR 3, `examples/settling_check/`):
- the decks and `settling_manifest.json`;
- one `dataset.parquet` per grid;
- `records/<grid>_<config>.json` (outside the ignored `runs/`);
- `settling_report.json`;
- `settling_figure.png` with its sidecar;
- `DECISION.md`.

## D5. New corpus directories

The new corpora go in `examples/settled_sweep` and `examples/settled_sweep_fine`.

- **Why not regenerate in place.** That would break, all in one PR:
  - the frozen raw-force hashes in `test_force_surrogate_scale_invariance.py` ("a HALT, not a
    re-pin");
  - the surrogate provenance tests;
  - both evidence figures, the three comparison figures and V3;
  - the bench pins.
- **What new directories give.** `main` stays green, each consumer moves in its own change, and
  beat 2 of the old corpus can be compared directly with the settled beat.
- **Overwrite guard.** The drivers refuse to write into a directory whose manifest has a different
  `n_wingbeats`. `N_WINGBEATS = 2` stays the library default, so the old corpora regenerate
  byte-identically.
- **Registry.** Each new corpus is registered with `has_parquet=False` in the commit that adds its
  decks (PR 3). It flips to `True` in PR 4, in the same commit as the guard tests' new values.
- **The 2-beat corpora are frozen.** They are not resubmitted. `prelim_sweep_fine` gets a
  `cluster_sizing.json` from its own metadata. `prelim_sweep` has no measured cluster rate, so it
  needs `--active-deadline-seconds`.

## D6. Training beat, guards and acceptance

- **Training beat.** `settling.training_wingbeat(manifest)` returns `n_wingbeats − 1`.
- **Trainer refusal.** Until consumers are migrated, `train.filter_converged_beat` and
  `train.build_phase_only_baseline` raise `ValueError` for a frame whose `wingbeat` exceeds 1,
  naming the follow-up issue.
  - The bench imports both, so bench code on a settled corpus is refused on purpose.
  - Both committed corpora have only beats 0 and 1, so nothing existing breaks.
- **Symmetry ratio.** It is computed over the final requested beat (`wingbeat == n_wingbeats − 1`,
  `time > 0`).
  - It is bit-identical for the 2-beat corpora.
  - For a 6-beat run with its last beat truncated at 95%, the old pooled ratio is ≈0.008 (inside
    0.012) and the new one ≈0.048.
  - The tolerance is not re-tuned. A healthy value above it stops the work.
- **Settling acceptance.** The D3 (a) test is applied to every configuration.
  - It is `not_applicable` only when the manifest's `n_wingbeats < MIN_BEATS`, decided from the
    manifest.
  - A run whose complete-beat count differs from `n_wingbeats` fails.
  - Results are written to `sweep_provenance.json` under `cluster_run.settling`.
  - The mid-sweep check runs the same function on configurations as they complete.
- **Field capture and CC-F1.** Provenance `field_capture` records `frames_per_beat` and
  `checkpoints_per_beat`. The gate keys CC-F1 on `frames_per_beat > 0`, and the rationale text no
  longer says no field output is produced.
- **Unchanged checks:** row count equals `max_step`; the realized-timestep check; the
  `wingbeat > 0` tripwire.

## D7. Field capture for later visualization

| later use | provision |
|---|---|
| beat-to-beat difference maps, phase averages, wing-frame POD, side-by-side movies across configurations | `amr.plot_per = 1/(20·f*)`: 20 frames per beat, each within one step of phase `k/20`, with no build-up across beats |
| start-up-to-settled movies of any configuration | plotfiles in every beat |
| coarse-versus-fine field comparisons | field capture on the coarse corpus too (velocity is written at `init_iter = 0`) |
| force traces of all beats | the extractor keeps every beat |
| a denser re-run of one beat later | `amr.check_per = 1/f*`: one checkpoint per beat boundary. **Not usable until #205 is fixed.** Kept because the fluid checkpoint is sound and a fix to the particle restart would make these files usable; open question 4 |

- `generate_sweep` gains `frames_per_beat` and `checkpoints_per_beat`, default `None`, which
  reproduces today's output byte-identically.
- The manifest records `plot_per` and `check_per` per config.
- The storage-manifest check derives the expected plotfile and checkpoint steps from each run's
  own time column, using AMReX's crossing rule on step end times `(iStep + 1)·dt`.

**Storage.**
- Fine: `27 × (20N + 1) × 0.513 GB` of plotfiles plus `27 × N × 2.3 GB` of checkpoints. The `+1`
  is the plotfile AMReX writes at `max_step`.
- Coarse: 8.2 MB per plotfile and 25 MB per checkpoint (E0b).

| N | fine plotfiles | fine checkpoints | fine total | coarse total |
|---|---|---|---|---|
| 6 | 1.68 TB | 0.37 TB | 2.05 TB | ≈31 GB |
| 7 | 1.96 TB | 0.43 TB | 2.39 TB | ≈36 GB |
| 8 | 2.23 TB | 0.50 TB | 2.73 TB | ≈41 GB |

## D8. Where the data lives

| data | home |
|---|---|
| decks, manifests, parquet (≈38 MB per corpus at N = 6, ≈50 MB at N = 8), run metadata, reports, figures, storage manifests, `cluster_sizing.json` | git |
| raw runs of the new corpora | `Z:\users\eberrigan\mosquito-cfd\examples\settled_sweep{,_fine}\runs\` (the cluster workspace) |
| Stage 1 raw runs | written on gh-04; copied with `scp` straight to `Z:\…\examples\settling_check_2026-11\`; verified by file count and CSV hash; never staged on `C:` |
| 2-beat raw runs | left in place; deletion is the user's decision when the 2-beat corpora are retired |

- **Ignore rules.** `.gitignore` gains `examples/settling_check/**/runs/` (PR 1) and
  `examples/settled_sweep*/runs/` (PR 2). `git check-ignore` tests confirm these are ignored and
  that the committed artifact names are not.
- **Durable homes.** This file is archived. Data locations and backup status therefore go in:
  - the corpus READMEs and `openspec/project.md` (Cluster Path Mappings);
  - `examples/settling_check/README.md` for Stage 1.
- **Backup.** The user is asked before task 15.2 is written.

## D9. Cluster sizing from step counts (#101)

- **Rates.** Each corpus that can be submitted carries `cluster_sizing.json`, with
  `{seconds_per_step_mean, seconds_per_step_max, source}`. A test recomputes it from the files its
  `source` names.
  - **Fine** (`prelim_sweep_fine` and `settled_sweep_fine`): 2.321 step-weighted and 3.302, from
    the 27 committed run metadata files. After the fine smoke run, `s_max` becomes the larger of
    3.302 and the smoke rate scaled by `3.302 / 2.137`, where 2.137 (7432 s / 3478 steps) is the committed rate of the
    smoke configuration. This accounts for plotfile I/O.
  - **Coarse** (`settled_sweep`): from the coarse smoke run. The mean is the smoke rate times
    `2.321 / 2.137`, and the max is the smoke rate times `3.302 / 2.137`. This is the fine grid's
    measured spread, stated as an assumption. The file is committed in PR 4 with the smoke run
    metadata.
- **Deadline.** `submit_workflow.sh full` always computes the deadline unless
  `--active-deadline-seconds` is given, using the effective parallelism (the committed 3 unless
  overridden):

  `ceil( Σ max_step · s_mean / 3600 / p  +  2 · max(max_step) · s_max / 3600 )` hours

  - This is the list-scheduling bound plus two retries of the longest configuration. It is a
    sizing choice, not a guarantee; further preemptions are handled by the runbook's
    trimmed-manifest resume.
  - A missing `cluster_sizing.json` is an error naming the explicit-deadline alternative. So is a
    manifest with zero configs.
  - Fine, N = 6, `p = 3`: 70.7 + 25.9 → 97 h.
- **Retry budget.** `maxDuration` lives in the WorkflowTemplate and cannot be patched per
  submission. It is committed as `"105h"`, covering 6 attempts of N = 8 fine
  `s35_f085_p30` (6 × 18824 × 3.302 s = 103.6 h) plus 62 min of backoff. A test fails when any
  committed manifest with a `cluster_sizing.json` needs more.
- **Smoke run.** `SMOKE_MAX_STEP` is read from the manifest. An environment value that disagrees
  with it is an error.
- **Stale values.** The 86400 s / 24 h and 3478 literals are replaced in the runbook,
  `submit_workflow.sh` (lines 20, 84, 95, 333), `force-surrogate-smoke.yaml:37`,
  `cluster/argo/README.md` and the spec. The YAML `98280` stays as the fallback for a direct
  `argo submit` and is documented as such.
- **Risk.** A preempted fine pod at N = 8 restarts from zero and loses up to ≈17 h. Resume needs
  #205.

## D10. Downstream reruns (list only)

This list also goes into row 19 of `docs/force_surrogate/roadmap.md` and into `DECISION.md`.

| rerun | code it needs first |
|---|---|
| force surrogates, coarse and fine, 5 seeds | `train.py` selects `training_wingbeat` (lifts the D6 refusal) |
| evidence figures | `evidence_figure.py`: `rows_per_wingbeat` assumes one scored beat per config |
| three coarse-vs-fine figures | `comparison_figure.py`: guard 8, coverage, `beat_sentence` |
| V3 figure and summary | repoint to the new coarse predictions |
| bench PR 2 results | bench scope strings, corpus pins, and its own `wingbeat >= 1` uses (owned by the bench session) |
| README tables | regenerated numbers |
| field-surrogate reader and roadmap | corpus pointer; plotfile counts |
| consolidate `settling.py` with the bench's `late_beat` | after the bench change is archived |
| checkpoint restart and resume-on-retry | #205 |
| retire the 2-beat corpora | frozen-hash policy; deleting 0.84 TB of raw runs is the user's call |

## D11. Domain caveat (#204)

- **Geometry.** The z boundaries are slip walls 4 units below the hinge. The x outflow is 1.5 units
  past the tip's reach, and the span is periodic.
- **Why it matters.** The downwash reaches the wall within 2.5–3 time units, and mean CF_z is
  still drifting at beat 6. "Settled" may therefore mean settled into a confined, wall-affected
  state.
- **What this change does.** It keeps the existing domain, reports mean-lift drift per beat, and
  states the caveat in `PREREGISTRATION.md`, `DECISION.md` and the corpus READMEs. The study is
  #204.

## Risks

| risk | mitigation |
|---|---|
| no settled beat within 8 | D3 `stop`; nothing is spent on the cluster; PR 2 is not merged |
| an unsampled configuration settles more slowly | the worst corner is sampled from E0; the mid-sweep settling check stops the sweep early; the gate checks all 54 runs |
| ratio noise | rising ratios widen the bound; the truncated test (a) equals the gate, so a corpus at `N*` passes for the sampled runs by construction |
| gh-04 slower than 7.5 s/step | C1 measures it before the long runs are approved |
| the CFL limiter binds in later beats | C4 on both grids over 8 beats, including the CFL-worst configuration |
| a preempted pod loses ≈17 h | the deadline covers two retries; resume needs #205 |
