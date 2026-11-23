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
- `amr.plot_int = -1` and `amr.plot_per = 1/(20·f*)`, giving 20 plotfiles per beat at fixed
  phases;
- `amr.check_int = -1` and `amr.check_per = 1/f*`, giving one checkpoint per beat. Checkpoints are
  not used for restarts (#205).

`ns.cfl`, `ns.init_iter`, `ns.fixed_dt`, the geometry and the grid are unchanged.

**Images.** Each grid uses the image its 2-beat corpus ran:
- fine: `ghcr.io/talmolab/mosquito-cfd@sha256:92817878fead23f9c6b8219706a2ebcec7cccf2158db8016e867e0227ca68a47`;
- coarse: `ghcr.io/talmolab/mosquito-cfd@sha256:07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3`.

## Metric

For one run, and each coefficient `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`:

1. **Clamped steps.** Rows whose step would end past `stop_time` (`time + dt > stop_time + 1e-9`)
   are dropped. At `f* = 0.85` the solver shortens its final step to land on `stop_time`, and that
   row carries a force spike of up to 10% of peak.
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
   - When every ratio was skipped, `T = 24 · max s_b` over the ratio beats. That is `ρ/(1 − ρ)` at
     `ρ = 0.96`.
9. **Estimate.** `E_b = D_b + T`.

The largest absolute difference over samples is reported beside every RMS value, but it does not
enter the verdict.

## Criterion and decision

For a run with `B` complete beats and a candidate count `N` (`MIN_BEATS ≤ N ≤ B`), **pass(N)**
holds when, for every coefficient, both of these are true:
- **(a)** the metric on the run cut at its first `N` beats is contracting, with
  `T ≤ SETTLED_TOLERANCE`. This is the test every regenerated corpus run will face.
- **(b)** on the full run, `E_N ≤ SETTLED_TOLERANCE` and the run is contracting.

`N*_run` is the smallest `N` such that pass(N′) holds for every `N′` from `N` to `B`. The corpus
beat count is `N* = max N*_run` over the six runs, used for both grids, with no margin added.

| outcome | action |
|---|---|
| any run has no `N*_run`, is not contracting on its full length, or has `ν > MAX_NOISE` for a coefficient | `stop`: no regeneration; the result goes to the user |
| otherwise, `N* > 6` | `regenerate_needs_cost_approval` |
| otherwise | `regenerate` |

`stop` takes precedence, then cost approval.

## Controls

Each control records its result in the run's record. A report with a declared control missing is
`controls_incomplete`.

| id | runs | check |
|---|---|---|
| C1 | `s55_f115_p30`, once per grid | The first 400 steps of the unmodified corpus deck reproduce that configuration's rows of the committed `dataset.parquet`. |
| C3 | every long run | Its first two beats reproduce the committed `dataset.parquet` rows. The reference's own clamped final row is excluded. |
| C4 | every long run | No interior step falls below the nominal `ns.fixed_dt`, over all 8 beats. Clamped final steps are excluded. |

**Coverage rule for C1 and C3.**
- The run's force rows first go through the extractor's de-duplication. That removes the extra
  `iStep == 0` rows written by `ns.init_iter = 2`; any other duplicate is a failure.
- Rows are then matched by time. Every run row must match exactly one reference row, every
  reference row up to the run's last time must be matched, and the run must reach its declared
  step count.

**Tolerance for C1 and C3.** Each value must agree to within
`max(1e-9 · max |column|, 1.5 units in the 6th significant figure of the reference value)`. The
CSV prints 6 significant figures, so this means "bit-identical output, allowing a flip of the last
printed digit". For an exact zero the second term is 0.

A failed control stops the work and is reported to the user.

There is no restart control. Restarts are known not to be faithful (#205), and no settling run
restarts.

## Reported, not part of the decision

- **Near-wing field change.** For the fine runs, for each beat `b` and each of the 20 frames: the
  median, and the fraction above 0.1, of `|u_b − u_B| / u_ref`.
  - `|·|` is the norm of the vector difference.
  - The region is the box from `(1, 0, 2.5)` to `(7, 4, 5.5)`.
  - `u_ref` is the reference speed `2π f*·φ_amp·r_gyr` used for the force coefficients.
  - The values are reported together with the plotfile hashes.
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

Each run starts from a clean checkout of a `main` commit that is an ancestor of `origin/main`. Its
record stores that commit and the SHA-256 of:
- this file;
- `src/mosquito_cfd/force_surrogate/settling.py`;
- `examples/settling_check/generate_decks.py`.

A CI test fails if this file or the deck generator differs from the recorded hash, unless a
`deviations.json` entry (`file`, `old_sha256`, `new_sha256`, `reason`, `pr`) explains the change.

This attests that the criterion was fixed before the fine-grid data existed. It is not a
cryptographic proof.

## Constants

<!-- settling-constants:start -->
```
SETTLED_TOLERANCE = 0.01
COMPLETE_FRACTION = 0.95
MIN_BEATS = 5
FIRST_RATIO_BEAT = 4
NOISE_FACTOR = 3
MAX_NOISE = 0.0006
```
<!-- settling-constants:end -->
