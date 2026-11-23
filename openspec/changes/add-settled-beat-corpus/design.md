# Design: add-settled-beat-corpus

Conventions: **beat `b`** is 1-based and is the rows with `wingbeat == b − 1` (the extractor's
0-based column). **N** is a beat count. "Peak" is per target, per run. All percentages are RMS over
phase unless stated.

## Context

These facts were measured or read from the code; sources are in parentheses.

- **Steps per beat** are `1 / (f*·dt)`: 2352.94 (`f085`), 2000 (`f100`) and 1739.13 (`f115`).
  Only `f100` has a whole number of steps per beat.
- **The beat count is already a parameter.** It is `N_WINGBEATS = 2` in `constants.py`, passed
  through `derive_run_duration` and `generate_sweep(n_wingbeats=...)`. Neither driver exposes it.
- **No consumer selects "beat 2".** The trainer, both figure modules and the corpus guards use
  `wingbeat >= 1`. The bench uses the largest common beat. In an N-beat corpus `wingbeat >= 1`
  would pool beats 2..N.
- **Fine corpus cost: 70.70 GPU-h on A40s.**
  - The mean is 2.311 s/step per config, unweighted; 2.321 weighted by steps.
  - The maximum is 3.302 s/step (`s35_f085_p30` on gpu-node8, 4.32 h). That node also has the next
    two slowest configs.
  - The run took 23 h 51 min at parallelism 3 (27 committed `run_metadata_<config>.json`).
- **Storage.** A fine plotfile is ≈513 MB and a fine checkpoint ≈2.3 GB
  (`docs/field_surrogate/roadmap.md`). A coarse plotfile is ≈8 MB.
- **Images.** The fine corpus ran image `sha256:92817878…a47` and the coarse corpus
  `sha256:07625ce4…24d3`. gh-04 holds `92817878…`.
- **The force CSV is opened in append mode** (`DiffusedIB*.cpp`, `std::ios::app`). A restarted run
  appends rows.
- **AMReX's `amr.plot_per` / `amr.check_per`** write at the first step whose time reaches the next
  multiple of the period. They do not change `dt`; only `stop_time` clamps the last step.
  (`AMReX_Amr.cpp:2360–2445` in the pinned image; `NavierStokesBase.cpp:1168`.)
- **Exploration study E0b**, coarse grid, 6 beats, unmasked RMS over beat-6 peak:
  - At `s45_f100_p30` the step ratios for CF_z at beats 4–6 are 0.64, 0.65 and 0.58. The CF_z
    tail bound at beat 6 with the max-of-three rule is 1.18%.
  - The ratios are not constant: beat 3/2 is about 0.03 (start-up), then they rise and fall.
  - Mean CF_z still falls 1.4% per beat at beat 6.
- **Exploration study E0**, beat 1→2 change, worst target, 27 configurations: stroke 35° with
  pitch 30° is worst on both grids, and `s45_f100_p30` ranks 5th.

**Lessons that constrain this design** (`openspec/project.md` Verification Principles; issue #92):
validate the worst case; a pilot's result applies only to the physics it ran under; a check needs
an external reference; a mandatory check must record its result.

## D1. Four PRs, one change, a staged delta

- PR 1's spec delta carries only the Stage 1 requirements.
- PR 2 adds the Stage 2 requirements, drafted now in `stage2-spec-draft.md`, in the same commits
  as their code. Each PR then leaves the effective spec (live specs plus active deltas) true of
  `main`.
- Each PR starts on a fresh branch cut from `origin/main` after the previous squash merge.
- The change is archived after PR 4.
- If Stage 1 ends in **stop**, PRs 2–4 are not opened. The change is archived with the Stage 1
  delta only, and a new change takes up the follow-up.

## D2. The settling metric

Constants are pinned in code, in `PREREGISTRATION.md` and in the spec:

| constant | value |
|---|---|
| `SETTLED_TOLERANCE` | 0.01 |
| `N_PHASE` | 256 |
| `COMPLETE_FRACTION` | 0.95 |
| `STEP_FLOOR` | 0.001 (0.1 × tolerance) |
| `MIN_BEATS` | 5 |
| `FIRST_RATIO_BEAT` | 4 |

For one run and target `j` (one of `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`):

1. **Beats** come from the extractor's `wingbeat` and `phase` columns, which are never
   recomputed. A beat is complete when it has at least `COMPLETE_FRACTION / (f*·dt)` rows. `B` is
   the number of the last complete beat. Every beat before it must also be complete, or the input
   is rejected. Duplicate or non-increasing `phase` within a beat is rejected.
2. **Resampling.** Each beat is resampled onto `k / 256` by periodic linear interpolation, giving
   `w_b`.
3. **Peak.** `P = max |w_B|`.
4. **Step change.** `s_b = rms(w_b − w_{b−1}) / P` for `b = 2..B`.
5. **Distance to the last beat.** `D_b = rms(w_b − w_B) / P`.
6. **Ratios** are taken for `b = max(FIRST_RATIO_BEAT, B − 2) .. B`. This excludes the start-up
   steps `s_2` and `s_3` and needs `B ≥ MIN_BEATS`; fewer complete beats is a `ValueError`.
   - If `s_{b−1} ≤ STEP_FLOOR` and `s_b ≤ STEP_FLOOR`: the ratio is skipped (at the floor).
   - If `s_{b−1} ≤ STEP_FLOOR < s_b`: the run is growing, so it is **not contracting**.
   - Otherwise `r_b = s_b / s_{b−1}`.
   - `ρ = max r_b`. If `ρ ≥ 1`, the run is not contracting.
7. **Tail bound** (how far beat `B` still is from the periodic state):
   - not contracting: `T = ∞`;
   - every ratio skipped: `T = 2 · max s_b` over the ratio beats (assumes `ρ ≤ 2/3`, stated in the
     report);
   - otherwise `T = s_B · ρ / (1 − ρ)`. This is a geometric-tail bound, valid if later steps shrink
     at least by `ρ`. RMS is a norm, so the triangle inequality gives
     `rms(w_B − w_∞) ≤ Σ_{k>B} s_k`.
8. **Estimated distance to the periodic state** `E_b = D_b + T`.
9. **Jitter.** `J = rms(L_even(w_B) − L_odd(w_B)) / P`, where `L_even` and `L_odd` resample beat
   `B` from its even- and odd-indexed samples. It overestimates the interpolation error that
   off-integer steps per beat add to `s_b` (about 1e-4 to 5e-4 measured on the committed data). It
   is reported. If `J > STEP_FLOOR` for any target, the floor is invalid and the rule returns
   **stop**.

The maximum absolute difference over phase is reported beside each RMS value but does not gate.
It is 2–3× the RMS, and at off-integer frequencies it is dominated by stroke-reversal spikes.

`surrogate_bench/gate.py` has a related `late_beat` yardstick. This change does not import or
edit bench code; consolidating them is a follow-up.

## D3. Pre-registered decision rule

For a run with `B` complete beats and a candidate `N` (`MIN_BEATS ≤ N ≤ B`), **pass(N)** requires
both of the following for every target:

- **(a) Truncated:** the metric on the run's first `N` beats alone is contracting (or at the
  floor) with `T ≤ SETTLED_TOLERANCE`. This is exactly the test the regenerated corpus faces in
  D6.
- **(b) Full:** on the full run, `E_N ≤ SETTLED_TOLERANCE` and the run is contracting (or at the
  floor).

`N*_run` is the smallest `N` such that pass(N′) holds for every `N′` from `N` to `B`.
`N* = max N*_run` over the six runs (three configurations × two grids). Both corpora use `N*`.

| outcome | action |
|---|---|
| any run has no `N*_run`, is not contracting on the full run, or fails the jitter check | `stop`: no regeneration; report to the user |
| every run has `N*_run` and `N* > 6` | `regenerate_needs_cost_approval` |
| every run has `N*_run` and `N* ≤ 6` | `regenerate` |

Precedence is stop, then needs approval, then regenerate. No floor or margin is added to `N*`.
Changing the tolerance after the data exist is a recorded deviation next to the original verdict,
never a substitute for it.

**Expected.** With 8 beats, the coarse 30° data suggests `N*_run` of 6–7 if its ratios fall to
about 0.58 and stay there. If they stay near 0.65, (a) can fail until beat 8, and the outcome is
`stop`. That outcome is a real possibility.

**Precedence proof** (squash-safe):

- `PREREGISTRATION.md` holds the constants in an anchored machine-readable block.
- Each gh-04 run starts from a clean checkout of `main` at a recorded SHA. The SHA must be an
  ancestor of `origin/main` and `git status --porcelain` must be empty.
- The run record stores that SHA and the SHA-256 of `PREREGISTRATION.md`, `settling.py` and
  `generate_decks.py`.
- In PR 3, a CI test asserts that the committed `PREREGISTRATION.md` hashes to the value in every
  run record, or that a committed `deviations.json` entry `{old_sha256, new_sha256, reason, pr}`
  explains the change.
- `check_settling.py` recomputes every number from the committed datasets with the current code,
  and states whether `settling.py` differs from the run-time hash. The runs themselves do not
  depend on `settling.py`.
- No CI test reads git history; CI checkouts are shallow.

## D4. Stage 1 runs and controls

**Decks.** `examples/settling_check/generate_decks.py` starts from each committed corpus deck. The
allowed differences are:

- `max_step` and `stop_time` (from `derive_run_duration(f*, 8)`);
- `amrex.the_arena_init_size = 12884901888` (the A5000's 24 GB cannot take AMReX's default arena);
- `amr.plot_int = -1`, `amr.check_int = -1`, `amr.plot_per = 1/(20·f*)`, `amr.check_per = 1/f*`;
- coarse only: `ns.init_iter = 2`.

These are the Stage 2 corpus settings, so the result transfers. The set of differing keys must
**equal** the allowed set. `ns.cfl`, `ns.fixed_dt`, geometry and grid are untouched.

**Image.** Fine and coarse runs use `ghcr.io/talmolab/mosquito-cfd@sha256:92817878…a47`, pulled by
digest. Its `com.mosquito-cfd.iamrex-commit` label must match `docker/build-args.env`. The runs are
driven through the existing local runner, so the container command is recorded.

**Controls.** Each control writes its result to the run record, and the report is
`controls_incomplete` while any applicable one is missing.

| id | applies to | check | pass |
|---|---|---|---|
| C1 | once, fine `s55_f115_p30` | 400 steps of the unmodified corpus deck against the committed cluster force CSV (SHA-256 recorded) | the 400 CSV rows are byte-identical (the CSV prints 6 significant figures, so this is exact equality) |
| C2 | once, fine `s55_f115_p30` | the corpus deck run 1000 steps, then restarted from `chk01000` to 2000 | rows 1–2000 are byte-identical to the committed CSV, with no duplicate or missing `iStep` at the restart |
| C3 | every long run | its first two beats against the committed 2-beat corpus | fine: CSV rows byte-identical; coarse: the RMS difference per target is **reported only** (image and `init_iter` differ by design) |
| C4 | every long run | realized timestep over all beats, from `run.log` | no step below nominal `ns.fixed_dt` |

- C1 also measures seconds per step. The long runs start only after the user has seen that rate
  and the projected wall time.
- If C2 fails, checkpoints are not used for restarts or later re-runs, and D7's "re-run a beat
  from its checkpoint" no longer holds.
- C3 on the fine grid is an external check: the runs are compared with the corpus they will
  replace.

**Known-answer test** on real data: the E0b coarse 6-beat datasets are committed as small test
fixtures (needed columns only).

- With E0b's `phase ≥ 0.05` mask, the step changes reproduce E0b's published beat-to-previous
  tables to `5e-5`.
- With the pre-registered rule, the `s45_f100_p30` CF_z tail bound is `0.0118 ± 1e-4` and the run
  has no settled beat.

**Reported, not gated.**

- **Near-wing field change.** With time-triggered plotfiles every beat has frames at the same
  phases (within one step), so all three fine runs are measured. For each beat `b` and frame `k`
  the report gives the median, and the fraction above 0.1, of `|u_b − u_B| / u_ref`. This is the
  vector-difference norm over E0b's near-wing box `(1,0,2.5)–(7,4,5.5)`. `u_ref` is
  `compute_force_reference(...).u_ref`. The #166 marker lag cancels at matched phase.
- **Mean CF_z per beat** and its drift per beat, for the domain caveat (D11).

**Outputs** (committed in PR 3, `examples/settling_check/`): the decks, `settling_manifest.json`,
one `dataset.parquet` per grid, a run record per run (SHA, file hashes, image, label, hardware,
command, wall time, seconds per step, realized timestep, controls), `settling_report.json`,
`settling_figure.png` with its sidecar, and `DECISION.md`.

## D5. New corpus directories

The new corpora are `examples/settled_sweep` and `examples/settled_sweep_fine`.

- **Why not regenerate in place.** That would break the frozen raw-force hashes
  (`test_force_surrogate_scale_invariance.py`: "a HALT, not a re-pin"), the surrogate provenance
  tests, two evidence figures, three comparison figures, V3 and the bench pins, all in one PR.
- **What new directories give.** `main` stays green, each consumer moves in its own change, and
  beat 2 of the old corpus can be compared directly with the settled beat.
- **Overwrite guard.** The drivers refuse to write into a directory whose manifest has a
  different `n_wingbeats`. The library default stays `N_WINGBEATS = 2`, so the old corpora
  regenerate byte-identically.
- **Registry.** Each new corpus is registered with `has_parquet=False` in the same commit that adds
  its decks (PR 3). It flips to `True` in PR 4, in the same commit as the guard tests' new
  expected values.

## D6. Training beat, guards and acceptance

- **Training beat.** `settling.training_wingbeat(manifest)` returns `n_wingbeats − 1`. Until a
  consumer is migrated, `train.py` raises `ValueError` for a dataset whose `wingbeat` exceeds 1,
  naming the follow-up issue. Downstream figures consume trainer output, so they are blocked too.
  The bench is out of scope and is noted in D10.
- **Symmetry ratio.** It is computed over the final requested beat (`wingbeat == n_wingbeats − 1`,
  `time > 0`).
  - For the 2-beat corpora this is bit-identical to today, because their maximum `wingbeat` is 1.
  - In a 6-beat run whose last beat is truncated at 95%, the old pooled ratio stays inside 0.012,
    at about 0.008, while the new ratio is about 0.048.
  - The tolerance is not re-tuned. A healthy value above it stops the work.
- **Settling acceptance** applies the D3 (a) test to every configuration.
  - It is `not_applicable` only when the manifest's `n_wingbeats < MIN_BEATS`, decided from the
    manifest, never from the observed beats.
  - A run whose complete-beat count differs from `n_wingbeats` fails.
  - Results go to `sweep_provenance.json` under `cluster_run.settling`.
- **Mid-sweep check.** It runs the same function on each configuration as it completes.
- **Unchanged checks.** Row count equals `max_step`, the realized-timestep check and the
  `wingbeat > 0` tripwire stay as they are.
- **CC-F1 on the coarse corpus.** CC-F1 now applies to the coarse corpus. The gate treats
  `plot_per > 0` as field capture (it keys on `plot_int > 0` today).

## D7. Field capture for later visualization

| later use | provision |
|---|---|
| beat-to-beat difference maps, phase averages, wing-frame POD, side-by-side movies across configurations | `amr.plot_per = 1/(20·f*)`: 20 frames per beat, each within one step of phase `k/20`, with no build-up across beats |
| start-up-to-settled movies of any configuration | plotfiles in every beat, not only the last |
| a denser or zoomed movie later without paying for N beats again | `amr.check_per = 1/f*`: one checkpoint per beat boundary (usable once C2 passes) |
| coarse-versus-fine field comparisons | field capture on the coarse corpus too, with `ns.init_iter = 2` so velocity is written |
| force traces of all beats | the extractor already keeps every beat |

- **Generator arguments.** `generate_sweep` gains `frames_per_beat` and `checkpoints_per_beat`,
  default `None` (today's output, byte-identical). When given, they write `plot_per`/`check_per`
  and set `plot_int`/`check_int` to −1, and the manifest records `plot_per` and `check_per` per
  config.
- **Where provenance records it.** `field_capture` in the provenance records `plot_per`.
- **Storage check.** The storage-manifest check derives each config's expected plotfile and
  checkpoint steps from that run's own time column, using the same crossing rule as AMReX.

**Storage, fine grid.** Plotfiles take `27 × (20N + 1) × 0.513 GB`; the `+1` is the final
plotfile AMReX writes at `max_step`. Checkpoints take `27 × N × 2.3 GB`.

| N | plotfiles | checkpoints | total | coarse total |
|---|---|---|---|---|
| 6 | 1.68 TB | 0.37 TB | 2.05 TB | ≈32 GB |
| 7 | 1.96 TB | 0.43 TB | 2.39 TB | ≈37 GB |
| 8 | 2.23 TB | 0.50 TB | 2.73 TB | ≈43 GB |

The coarse totals use 8 MB per plotfile and 2.3 GB / 64 ≈ 36 MB per checkpoint. Both coarse sizes
are scaled from the fine grid, not measured; the coarse smoke run measures them.

## D8. Where the data lives

| data | home |
|---|---|
| decks, manifests, extracted parquet (≈38 MB per corpus at N = 6, ≈50 MB at N = 8), run metadata, reports, figures, storage manifests | git |
| raw runs of the new corpora (CSV, `run.log`, plotfiles, checkpoints) | `Z:\users\eberrigan\mosquito-cfd\examples\settled_sweep{,_fine}\runs\` (the cluster workspace) |
| Stage 1 raw runs | written on gh-04, copied with `scp` straight to `Z:\…\examples\settling_check_2026-11\`, and verified by file count and CSV hash; never staged on `C:` |
| 2-beat raw runs | left in place; deleting them is the user's decision when the 2-beat corpora are retired |

- `.gitignore` gains `examples/settling_check/**/runs/` (PR 1) and `examples/settled_sweep*/runs/`
  (PR 2).
- A test asserts with `git check-ignore` that these are ignored and that the committed artefact
  names are not.
- **Durable homes.** This file is archived, so the data locations and backup status go in the
  corpus READMEs and `openspec/project.md` (Cluster Path Mappings). Stage 1 locations go in
  `examples/settling_check/README.md`.

## D9. Cluster sizing from step counts (#101)

- **Rates.** Each new corpus directory carries `cluster_sizing.json`:
  `{seconds_per_step_mean, seconds_per_step_max, source}`.
  - The fine values come from the committed 2-beat run metadata: 2.321 (step-weighted) and 3.302.
    A test recomputes them.
  - The coarse values are written from the coarse smoke run before the full submission.
- **Deadline.** `submit_workflow.sh full` always computes the deadline, unless
  `--active-deadline-seconds` is given, using the effective parallelism (the committed 3 unless
  overridden):

  `ceil( Σ max_step · s_mean / 3600 / p  +  2 · max(max_step) · s_max / 3600 )` hours

  - This is the list-scheduling bound plus two retries of the longest configuration. It is a
    sizing choice, not a guarantee. More preemptions than that are handled by the runbook's
    trimmed-manifest resume.
  - A missing `cluster_sizing.json` is an error that names the explicit-deadline alternative.
  - A manifest with zero configs is an error.
  - Fine, N = 6, parallelism 3: 70.7 + 25.9 → 97 h.
- **Retry budget.** `maxDuration` is set at submission to `(limit + 1) · max(max_step) · s_max`
  plus 62 min of backoff.
  - If `argo lint --offline` or the smoke run shows Argo will not template `backoff.maxDuration`,
    the committed value becomes `"105h"` (N = 8 fine: 6 × 18824 × 3.302 s + 62 min = 104.6 h).
  - In that case a test fails when any committed manifest needs more.
- **Smoke run.** `SMOKE_MAX_STEP` is read from the manifest. An environment override that
  disagrees with the manifest is an error.
- **Stale figures.** The 86400 s / 24 h figures in the runbook, `submit_workflow.sh:20`,
  `cluster/argo/README.md` and the spec are corrected. The committed YAML `98280` stays as the
  fallback for direct `argo submit` and is documented as such.
- **Risk.** A preempted fine pod at N = 8 can lose ≈17 h. The resume follow-up depends on C2.

## D10. Downstream reruns (list only)

| rerun | code it needs first |
|---|---|
| force surrogates, coarse and fine, 5 seeds | `train.py` selects `training_wingbeat` (lifts the D6 refusal) |
| evidence figures | `evidence_figure.py`: `rows_per_wingbeat` assumes one scored beat per config |
| three coarse-vs-fine figures | `comparison_figure.py`: guard 8, coverage, `beat_sentence` |
| V3 figure and summary | repoint to the new coarse predictions |
| bench PR 2 results | bench scope strings and corpus pins (owned by the bench session) |
| README tables | regenerated numbers |
| field-surrogate reader and roadmap | corpus pointer; plotfile counts |
| consolidate `settling.py` with the bench's `late_beat` | after the bench change is archived |
| retire the 2-beat corpora | frozen-hash policy; deleting 0.84 TB of raw runs is the user's call |

## D11. Domain caveat

- The z boundaries are slip walls 4 units below the hinge. The x outflow is 1.5 units beyond the
  tip's reach, and the span is periodic.
- A momentum-theory estimate puts the downwash at the wall within 2.5–3 time units, and mean
  CF_z is still drifting at beat 6. "Settled" may therefore mean settled into a confined,
  wall-affected state.
- This change keeps the existing domain (all existing data use it), reports mean-lift drift per
  beat, and states the caveat in `DECISION.md` and the corpus READMEs.
- A separate issue covers a domain-size study.

## Risks

| risk | mitigation |
|---|---|
| no settled beat within 8 | D3 `stop`; nothing is spent on the cluster |
| an unsampled configuration settles more slowly | worst corner sampled from E0; the mid-sweep settling check stops the sweep early; the gate checks all 54 |
| ratio noise (three ratios, ±0.1) | the truncated test (a) is identical to the gate, so a corpus at `N*` passes for the sampled runs by construction |
| gh-04 slower than 7.5 s/step | C1 measures it before the long runs are approved |
| CFL limiter in later beats | C4 on both grids over 8 beats, including the CFL-worst configuration |
| the restart duplicates rows (CSV append) | C2 checks `iStep` continuity |
