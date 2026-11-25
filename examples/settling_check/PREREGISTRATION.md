# Settling check: pre-registration

**Status: fixed before any run of this check.** This file is merged to `main` before the first
settling run starts. Every run record stores its SHA-256 (see "Precedence"). Any later edit is
recorded as a deviation in `deviations.json`; it never replaces the original.

OpenSpec change `add-settled-beat-corpus` (issue #192). This file is the single narrative home of
the settling criterion. The implementation is `src/mosquito_cfd/force_surrogate/settling.py`, and
the normative requirements are in the `force-surrogate` spec.

## Question

The force-surrogate corpora were 2-wingbeat runs, and the surrogates trained on the second beat.
How many wingbeats must a run have before its last beat is periodic to within 1% of peak, on the
fine grid (256×128×256) and the coarse grid (64×32×64)?

## Runs

There are three configurations, each run for 8 wingbeats on both grids. That is six runs on the
lab RTX A5000 machine gh-04.

| configuration | why |
|---|---|
| `s35_f085_p30` | One of the three slowest to settle on both grids in the 27-config beat 1→2 comparison (exploration study E0). It is the only low-frequency case, and the slowest per step. |
| `s45_f100_p30` | The slowest-settling run measured so far (E0b, coarse, 6 beats). |
| `s55_f115_p30` | The high-frequency corner, and the configuration with the tightest timestep (CFL) margin. |

**Decks.** Each deck is the committed corpus deck for that configuration and grid, changed in only
these keys:
- `max_step` and `stop_time`, for 8 beats;
- `amrex.the_arena_init_size = 12884901888`;
- `amr.plot_int = -1` (already −1 in the coarse decks, so not a change there) and
  `amr.plot_per = 1/(20·f*)`, giving 20 plotfiles per beat at fixed phases;
- `amr.check_int = -1` and `amr.check_per = 1/f*`, giving one checkpoint per beat. Checkpoints are
  not used for restarts (#205).

`ns.cfl`, `ns.init_iter`, `ns.fixed_dt`, the geometry and the grid are unchanged.

**Images.** Each grid uses the image its 2-beat corpus ran:
- fine: `ghcr.io/talmolab/mosquito-cfd@sha256:92817878fead23f9c6b8219706a2ebcec7cccf2158db8016e867e0227ca68a47`;
- coarse: `ghcr.io/talmolab/mosquito-cfd@sha256:07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3`.

## Metric

For one run, and each coefficient `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`:

1. **Clamped steps.** Rows whose step would end past `stop_time` (`time + dt > stop_time + CLAMP_SLACK`, 1e-9)
   are dropped. At `f* = 0.85` the solver shortens its final step to land on `stop_time`, and that
   row carries a force spike of about 10% of peak (up to 10.4% in the committed corpora).
2. **Beats.** Beat `b` (1-based) is the rows with `wingbeat == b − 1`, using the extractor's
   `wingbeat` and `phase` as given.
   - A beat is complete when it has at least `COMPLETE_FRACTION / (f*·dt)` rows.
   - `B` is the last complete beat. It must be at least `MIN_BEATS`.
3. **Distance.** `dist(a, c)` is the RMS, over beat `a`'s own samples, of beat `a` minus beat `c`
   interpolated (periodic, linear in `phase`) at those samples. It is divided by `P`, the largest
   magnitude in beat `B`.
   - Beats are compared at their own sample resolution, not on a coarse phase grid. A 256-point
     grid aliases the one-sample force features at stroke reversal and adds up to 1e-3 to a beat
     difference.
4. **Step change and distance to the last beat.** `s_b = dist(b, b − 1)` and `D_b = dist(b, B)`.
5. **Jitter and noise floor.**
   - `J = rms(w[i−1] − 2·w[i] + w[i+1]) / (8·P)` over beat `B`'s interior samples. This is the
     largest error of linear interpolation at half a sample spacing, for a locally quadratic
     signal.
   - The noise floor is `ν = NOISE_FACTOR · J`.
   - On the committed 2-beat corpora's final beats, `J` is below 6.5e-5. On exactly periodic
     signals rebuilt from those beats on the true step grids, `s_b` stays below `ν`.
6. **Ratios**, for `b = max(FIRST_RATIO_BEAT, B − 2) .. B`:
   - if `s_{b−1} ≤ ν` and `s_b ≤ 2ν`, the ratio is skipped (noise);
   - if `s_{b−1} ≤ ν` and `s_b > 2ν`, the run is growing: **not contracting**;
   - otherwise `r_b = s_b / s_{b−1}`.

   The window starts at `r_4 = s_4 / s_3`, so the start-up ratio `s_3 / s_2` never enters.
7. **Contraction.** `ρ = max r_b + max(0, r_last − r_first)`. The second term widens the bound
   when the ratios are rising, as when a fast decay hands over to a slower one. `ρ ≥ 1` is not
   contracting.
8. **Tail bound** `T`, which estimates how far beat `B` still is from the periodic state:
   - `T = s_B · ρ / (1 − ρ)` in general. This is the sum of the remaining steps if they keep
     shrinking by `ρ`. RMS is a norm, so `‖w_B − w_∞‖ ≤ Σ_{k>B} s_k`.
   - `T` is infinite when the run is not contracting.
   - When every ratio was skipped, `T = AT_FLOOR_FACTOR · max s_b` over the ratio beats.
     `AT_FLOOR_FACTOR = 24` is `ρ/(1 − ρ)` at `ρ = 0.96`.
9. **Estimate.** `E_b = D_b + T`.

The largest absolute difference over samples is reported beside every RMS value, but it does not
enter the verdict.

## Criterion and decision

For a run with `B` complete beats and a candidate count `N` (`MIN_BEATS ≤ N ≤ B`), **pass(N)**
holds when, for every coefficient, both of these are true:
- **(a)** the metric on the run cut at its first `N` beats (rows with `wingbeat < N`, and
  `stop_time = N/f*` for the clamp rule) is contracting, with
  `T ≤ SETTLED_TOLERANCE`. This is the test every regenerated corpus run will face.
- **(b)** on the full run, `E_N ≤ SETTLED_TOLERANCE` and the run is contracting.

`N*_run` is the smallest `N` such that pass(N′) holds for every `N′` from `N` to `B`. The corpus
beat count is `N* = max N*_run` over the six runs, used for both grids, with no margin added.

| outcome | action |
|---|---|
| any run has no `N*_run`, is not contracting on its full length, or has `ν > MAX_NOISE` (or a non-finite `ν`) for a coefficient | `stop`: no regeneration; the result goes to the user |
| otherwise, `N* > COST_APPROVAL_ABOVE` (6) | `regenerate_needs_cost_approval` |
| otherwise | `regenerate` |

`stop` takes precedence, then cost approval.

## Controls

Each control records its result in the run's record. A report with a declared control missing is
`controls_incomplete`.

| id | runs | check |
|---|---|---|
| C1 | `s55_f115_p30`, once per grid | The corpus deck with only `max_step = 400` and the arena size changed runs exactly 400 steps, and they reproduce that configuration's rows of the committed `dataset.parquet`. |
| C3 | every long run | Its first two beats reproduce the committed `dataset.parquet` rows. The reference's own clamped final row is excluded. |
| C4 | every long run | No interior step falls below the nominal `ns.fixed_dt`, over all 8 beats. Clamped final steps are excluded. |

**Coverage rule for C1 and C3.**
- The run's force rows first go through the extractor's de-duplication. That removes the extra
  `iStep == 0` rows written by `ns.init_iter = 2`; any other duplicate is a failure.
- Rows whose step ends past each side's `stop_time` are dropped. The remaining rows are matched
  by step index `round(time / dt)`.
- The comparison covers steps `0 .. n − 1`:
  - for C1, `n` is the control deck's `max_step` (400);
  - for C3, `n` is the number of reference rows left after the reference's clamped row is dropped.
- Each of those steps must appear exactly once in both the run and the reference. Rows of a long
  run after step `n − 1` are not compared.

**Tolerance for C1 and C3.** Every value must be finite and agree to within
`max(COMPARE_RELATIVE_TO_COLUMN · max |column|, COMPARE_PRINT_UNITS · one unit in the 6th
significant figure of the reference value)`, that is `max(1e-9 · max |column|, 1.5 units)`.
- The CSV prints 6 significant figures, so this means "bit-identical output, allowing a flip of
  the last printed digit".
- The extra half unit absorbs floating-point error in the subtraction.
- For an exact zero the second term is 0.
- A NaN or inf on either side fails.

**Run length.** Every run must reach its deck's end: its de-duplicated force CSV has exactly
`max_step` rows (C1 included), and the long runs' datasets have `n_wingbeats` complete beats.

A failed control stops the work and is reported to the user.

There is no restart control. Restarts are known not to be faithful (#205), and no settling run
restarts.

## Reported, not part of the decision

- **Near-wing field change.** For the fine runs, for each beat `b` and each of the 20 frames: the
  median, and the fraction above `FIELD_CHANGE_THRESHOLD` (0.1), of `|u_b − u_B| / u_ref`.
  - `|·|` is the norm of the vector difference.
  - The region is the box from `(1, 0, 2.5)` to `(7, 4, 5.5)`.
  - `u_ref` is the reference speed `2π f*·φ_amp·r_gyr` used for the force coefficients.
  - Matched frames of two beats can be up to one step apart in phase (about 0.3% of `u_ref` in
    the change), which is negligible against the threshold.
  - The values are reported together with the SHA-256 of each plotfile's `Header`.
- **Mean CF_z per beat**, and its drift per beat.

## Known limitations

- **The rule is calibrated against coarse data only.** It was designed with the E0b coarse 6-beat
  runs in view, and those runs are also its test fixtures. It therefore predates only the
  **fine-grid and 8-beat** data. On the E0b data it finds no settled beat within 6 beats:
  `s45_f100_p30` reaches CF_my `T = 1.245%`, and `s45_f100_p45` reaches CF_my `T = 1.007%`.
- **Two decay modes can defeat a three-ratio window.** For example, a fast mode (ratio 0.5) plus a
  slow one (ratio 0.97, starting at 4e-4) can pass with `T = 0.21%` against a true tail of about
  1.24%. The reported mean-CF_z drift is the cross-check.
- **pass(5) is harder by design.** At `N = 5` only `r_4` and `r_5` enter, and the start-up
  transient often depresses `r_4`, so the rising-ratio term makes pass(5) harder.
- **The noise floor is not a white-noise floor.** `ν = 3J` bounds the interpolation error of
  smooth signals. The real data's second differences are correlated (curvature), not white.
- **The domain may confine the late beats.** The z boundaries are slip walls 4 units below the
  hinge. "Settled" may therefore mean settled into a wall-affected state (#204). Mean-lift drift
  is reported for that reason.

## Precedence

Each run starts from a clean checkout of a `main` commit that is an ancestor of `origin/main`.
This is derived from git, not typed in by the operator:
- just before the container starts, `scripts/record_settling_run.py launch` writes the
  checkout's HEAD and `git status --porcelain` into the run directory. It refuses if the
  checkout is dirty, HEAD is not on `origin/main`, or the run directory is inside the checkout
  without being ignored by git. A launch state without its git status counts as neither clean
  nor dirty, and the record is refused;
- when the record is written, the script checks four things:
  - HEAD is still that commit;
  - the commit is an ancestor of `origin/main` (no other upstream is accepted);
  - the checkout was and is clean: only new, untracked `*.json` files directly in `records/`
    are exempt, and files hidden from `git status` (skip-worktree, assume-unchanged) count as
    dirty;
  - each gated file equals its bytes at that commit.

The record stores the commit and the SHA-256 (at that commit, from `git show`) of the gated
files:
- this file;
- `examples/settling_check/generate_decks.py`;
- `src/mosquito_cfd/force_surrogate/settling.py`.

`settling.py` is gated because the verdict is recomputed with the current code: changing the
analysis after seeing the data is a deviation, like changing the criterion.

A CI test fails if any gated file differs from the recorded hash, unless a `deviations.json`
entry (`file`, `old_sha256`, `new_sha256`, `reason`, `pr`) explains the change. The record also
stores three things observed at run time:
- the hash of the deck in the run directory, which must be the committed deck;
- the exact container command, which must name the pinned image;
- the image's IAMReX label, from `docker image inspect`.

This attests that the criterion and the analysis were fixed before the fine-grid data existed.
It is not a cryptographic proof.

## Constants

<!-- settling-constants:start -->
```
SETTLED_TOLERANCE = 0.01
COMPLETE_FRACTION = 0.95
MIN_BEATS = 5
FIRST_RATIO_BEAT = 4
NOISE_FACTOR = 3
MAX_NOISE = 0.0006
AT_FLOOR_FACTOR = 24
CLAMP_SLACK = 1e-9
COST_APPROVAL_ABOVE = 6
COMPARE_RELATIVE_TO_COLUMN = 1e-9
COMPARE_PRINT_UNITS = 1.5
FIELD_CHANGE_THRESHOLD = 0.1
```
<!-- settling-constants:end -->
