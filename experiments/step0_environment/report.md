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
