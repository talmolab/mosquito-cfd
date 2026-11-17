# Step 0: environment and sizing

**Data used:** `examples/prelim_sweep_fine/dataset.parquet` at `80d653a`
(sha256 `e248f331…`, the same hash the committed surrogate's `run_metadata.json` records), second beat only.

## Reproduction gate: PASS

Seed 1234, committed split, RTX A5000 under WSL2, existing environment
`~/.venvs/mosquito-cfd-train` (torch 2.12.1+cu126, PhysicsNeMo 2.1.1).

- Validation configs drawn: `s55_f100_p60`, `s55_f115_p30`, `s55_f115_p60` — identical to the committed run.
- Held-out RMSE and skill on all six targets equal the committed `metrics.json` values to every
  printed digit (relative difference 0.0). The gate's tolerance was 2%.

So on this machine the CUDA run reproduced exactly, although the trainer only promises that on CPU.

## Sizing

One fit (18 training configs, 2000 epochs, full batch) takes **30 s**.

| Experiment | Fits | Seeds / draws chosen |
|---|---|---|
| E2 leave-one-config-out | 27 × 5 = 135 | 5 seeds (floor was 3) |
| E3 data efficiency | about 205 | 5 subset draws × 5 init seeds per n, plus structured designs and row thinning |
| E4 ablations | about 85 | 5 seeds per arm |

About 3.5 GPU-hours in total, inside the 10-hour budget.

## Note

`run_record.json` cannot read the git commit from inside WSL (the known Windows-worktree problem,
#78), so WSL launches pass the commit in through `EXP_GIT_COMMIT`.

## Field data checks (2026-11-16)

**Data used:** live plotfiles under `Z:\users\eberrigan\mosquito-cfd\examples\prelim_sweep_fine\runs\`.

- **Stale directories:** `FieldCorpus.steps()` lists none of the `.old.*` directories on the three
  configs probed (36, 49 and 41 live steps). Every snapshot is also checked before caching:
  `ns.cfl = 0.6`, `ns.fixed_dt = 0.0005`, `amr.n_cell = 256 128 256`, IAMReX `f93dc794`, and header
  time = step x 5e-4. A failure stops the cache.
- **Read cost:** 30-47 s and about 0.8 GB peak per full plotfile read from `Z:`. The cache therefore
  runs as three parallel workers, second-beat snapshots first.
- **Patch coverage:** share of the full-domain enstrophy inside the patch (x 1-7, y 0-4, z 2.5-5.5)
  at mid-stroke of the second beat:

  | config | z from 2.5 (chosen) | z from 2.0 | z from 1.5 |
  |---|---|---|---|
  | `s55_f115_p60` (largest, fastest) | 0.913 | 0.959 | 0.985 |
  | `s45_f100_p45` | 0.965 | 0.989 | 0.999 |
  | `s35_f085_p30` | 0.998 | 1.000 | 1.000 |

  All are above the 90% rule, so the extents stand. The patch misses up to 9% of the enstrophy in
  the wake below z = 2.5 for the most energetic config; the whole-domain 4x-downsampled cache covers
  that region at lower resolution.
- **Wing markers:** `yt` reads the 908 markers from the plotfile. Markers rebuilt from
  `wing.vertex` and the kinematics match them to round-off at `t - 2 dt` and to 0.02 length units
  (under one cell) at `t`. The wing-frame POD variant is therefore possible. The exact two-step lag
  is written up in `experiments/issue-drafts/plotfile-markers-lag-header-time-by-two-steps.md`.

## Field cache: final state (2026-11-16)

- **558 snapshots cached, all 27 configs, second beat only** (24, 20 and 18 per config for
  f* = 0.85, 1.0 and 1.15). Every one passed the provenance check. About 16 GB locally.
- **Each run's final plotfile is excluded.** For the f* = 0.85 group it sits at the deck's
  `stop_time`, not at step x 5e-4 (the solver shortens its last step), so the time test refused it
  and stopped the cache. The test was left as strict as it was and the final plotfile (start of a
  third beat) is simply not cached.
- **The manifest copy on `Z:` lists 26 configs**; `s55_f115_p30` is missing from it although its run
  directory is complete. The cache uses the committed 27-config manifest. Written up in
  `experiments/issue-drafts/cluster-manifest-copy-lists-26-configs.md`.
- The first beat is not cached.
