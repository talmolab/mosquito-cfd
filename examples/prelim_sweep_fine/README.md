# Force-surrogate fine-grid kinematic sweep (`prelim_sweep_fine`)

The **256×128×256** counterpart of [`examples/prelim_sweep`](../prelim_sweep/README.md) (which
this file assumes as background — differences are called out, not re-derived). Same 27-config
*Aedes aegypti*-anchored kinematic grid (φ ∈ {35,45,55}°, f\* ∈ {0.85,1.0,1.15}, α ∈ {30,45,60}°),
same holdout split and Reynolds policy, but at fine grid resolution and with **field capture
enabled** — this corpus produces AMReX plotfiles, not just force CSVs.

## What's here

| File | Contents |
|---|---|
| `inputs/inputs.3d.s{φ}_f{f*×100}_p{α}` | 27 decks (same naming as the coarse corpus). |
| `sweep_manifest.json` / `sweep_manifest.units.json` | Per-config kinematics, `reynolds`, `max_step`/`stop_time`, `plot_int`, `init_iter`, **`cfl`**, train/holdout `split`. |
| `sweep_provenance.json` | git commit, base-inputs SHA256, `field_capture` policy, `timestep_policy` (this corpus's `ns.cfl`), `supersession_history` (superseded prior cluster runs — see below), and `cluster_run` (recorded post-run checks, e.g. CC-F1). |
| `run_metadata_<config>.json` | Per-config run-observed metadata (27 files) — see "Run-observed metadata" below. |
| `dataset.parquet` / `dataset.units.json` / `run_metadata.json` | The extracted force dataset and its build provenance — same schema and conventions as the coarse corpus's (see its README's "Dataset" section). |
| `generate_full_corpus.py` | Thin driver over `mosquito_cfd.force_surrogate.sweep.generate_sweep()`. |
| `surrogate/` | The force surrogate trained on this corpus (#110): `surrogate.pt` (seed 1234), `holdout_predictions.parquet`, `metrics.json` (with `phase_baseline_skill` and the 5-seed `seed_sweep`), `run_metadata.json`. Same trainer, flags and file layout as the coarse corpus's `surrogate/`. |
| `figures/` | The evidence figure: `evidence_figure.png`, `evidence_figure_metrics.json` (every number on the figure), `run_metadata.json` (provenance, including the grid profile and the CFD cost per step). There is no separate `figures/README.md`; this file covers it. |

The surrogate and its figure are described in [Surrogate and evidence figure](#surrogate-and-evidence-figure)
below.

## Surrogate and evidence figure

The surrogate is the coarse corpus's, retrained here with no functional change: the same trainer
(`scripts/train_surrogate.py`), the same flags (2000 epochs, primary seed 1234, sweep seeds
1235–1238, 3 validation configurations) and the same holdout split; only the dataset differs. The
figure comes from the same generator with its `fine` grid profile. Background that is the same for
both corpora is in the coarse README's
[honest reading of the figure](../prelim_sweep/README.md#honest-reading-of-the-figure-cc-4) and is
not repeated here.

### What the figure reports: skill over the phase-only baseline

Each panel leads with **skill = 1 − MSE/MSE₀**, where MSE₀ is the holdout error of the
**phase-only baseline**: the mean waveform of this corpus's 21 non-holdout configurations (the
`train` split, including the 3 the trainer sets aside for validation), which knows the phase but
ignores stroke amplitude, frequency and pitch. 0 is no better than the
baseline, 1 is perfect, below 0 is worse. Pooled over every holdout row, skill also credits
predicting how the waveform's amplitude and shape change with the kinematics, not only the
cycle-mean force. The baseline alone already scores a high pointwise R² (last column), which is how
much of the surrogate's pointwise R² the shared waveform explains. From `surrogate/metrics.json`
(the five seeds are trained in one run; only seed 1234 is committed as a model):

| target | skill, seed 1234 | skill, 5 seeds | phase-only baseline R² |
|---|---|---|---|
| `CF_x` | 0.990 | 0.990 to 0.996 | 0.933 |
| `CF_y` | 0.980 | 0.980 to 0.994 | 0.942 |
| `CF_z` | 0.977 | 0.977 to 0.991 | 0.907 |
| `CF_mx` | 0.968 | 0.968 to 0.993 | 0.925 |
| `CF_my` | 0.985 | 0.975 to 0.986 | 0.944 |
| `CF_mz` | 0.987 | 0.987 to 0.995 | 0.940 |

Every target beats the phase-only baseline at every seed. Five seeds give the spread observed, not
a confidence interval. The plotted seed 1234 is the lowest of the five for every target except
`CF_my`, so the panels show the low end of each range. The panels plot `CF_x`, `CF_z` and `CF_my`;
`CF_mx` and `CF_mz` are left off the panels by design (the panel set is fixed, not chosen per
corpus) and their skill is given in the table above and in the caption. Moments are **lab-frame**
components about the hinge, so `CF_my` is labelled the M_y component, not a wing-frame moment; the
wing-frame conversion is deferred, not currently tracked
([`docs/coordinate-convention.md`](../../docs/coordinate-convention.md#moments)).

### Config-resolved (cycle-mean) R², 5 seeds

R² over the six holdout configurations' cycle means, the phase-removed config-to-config measure. It
is off the figure for the reason given in the coarse README: for several targets it divides by a
near-zero spread of six cycle means and swings with the seed. It stays in `metrics.json`
(`config_resolved`, and `seed_sweep.range.<c>.config_mean_r2`):

| target | cycle-mean R², 5 seeds |
|---|---|
| `CF_x` | −7.21 to 0.80 |
| `CF_y` | 0.97 to 0.99 |
| `CF_z` | 0.97 to 1.00 |
| `CF_mx` | 0.94 to 1.00 |
| `CF_my` | −0.20 to 0.86 |
| `CF_mz` | −20.75 to 0.80 |

On this corpus `CF_y`, `CF_z` and `CF_mx` are robust to the seed and `CF_x`, `CF_my` and `CF_mz` are
not; only for the first three does the record support saying the surrogate resolves the per-config
average force.

### Coarse vs fine

The same 5-seed skill ranges for both corpora, each read from its own committed `metrics.json`:

| target | skill, 5 seeds, coarse | skill, 5 seeds, fine | ranges overlap |
|---|---|---|---|
| `CF_x` | 0.988 to 0.992 | 0.990 to 0.996 | yes |
| `CF_y` | 0.974 to 0.984 | 0.980 to 0.994 | yes |
| `CF_z` | 0.984 to 0.990 | 0.977 to 0.991 | yes |
| `CF_mx` | 0.973 to 0.990 | 0.968 to 0.993 | yes |
| `CF_my` | 0.970 to 0.984 | 0.975 to 0.986 | yes |
| `CF_mz` | 0.983 to 0.991 | 0.987 to 0.995 | yes |

Both corpora use the same six holdout and the same three validation configurations. The rule was
fixed before the fine run, in the `add-fine-corpus-surrogate` OpenSpec change (design D5 and the
spec): a target counts as moved only if its two 5-seed ranges are disjoint (computed on the
unrounded values; touching ranges count as overlapping). Every pair
overlaps, so for all six targets: no shift detected. Five seeds a side cannot rule out a difference
as large as the seed spread. Each grid is scored against its own corpus's phase-only baseline, so a
difference would reflect the CFD data as well as the surrogate; this table is not a measurement of
the effect of grid resolution on its own.

### Quasi-steady reference

The caption gives the ratio of an uncalibrated, translational-only Sane–Dickinson quasi-steady
model to the fine-grid CFD lift: ~1.4× in RMS (`quasi_steady_reference.overshoot_factor` in
`figures/evidence_figure_metrics.json`). The model omits rotational, added-mass and LEV lift, uses a
symmetric-rotation angle of attack, and defines lift stroke-plane-normal while the CFD `CF_z` is the
lab-z force, so it is reported as a reference number and not overlaid on the figure. The ratio is
above 1 even though the omitted terms would add lift, so the omissions do not explain the gap; why
the uncalibrated model over-predicts this grid's lift was not investigated here. The model itself is
described in the coarse README.

### Validation status of the fine CFD

The caption says the figure shows agreement with CFD, not with experiment. The surrogate is scored
against this corpus's CFD; nothing here compares the CFD with measured forces. What has been checked
about the fine-grid CFD, all in [`examples/flapping_wing/RESULTS.md`](../flapping_wing/RESULTS.md):

- **Grid convergence was checked at one wing motion, outside this sweep:** the 70° validation
  stroke (this sweep's stroke amplitudes are 35–55°), on the A5000 at `dt` 2.5e-4 rather than this
  corpus's 5e-4, and on peak body-frame forces only. The three-grid study (T3c, PR #52) gives
  GCI_fine 3.7 % for `CF_normal` and 27.6 % for `CF_chord`. No moment and no lab-frame time series
  was grid-checked.
- **Comparison with a model, not a measurement** (T4): `CF_normal 2.23 vs model 2.48` and
  `CF_chord 0.41 vs model 0.43` against van Veen's quasi-steady force model at that same point.
- **This sweep's 27 runs** passed only the acceptance gate's internal checks (CFL, row counts, CC-F1,
  beat symmetry; see below), not a comparison with any reference.

### Speedup

The headline (≈1.1×10⁸×) is batched GPU throughput (`inference.throughput_rows_per_s`, the
surrogate timed on the local RTX A5000) divided by the **sequential** fine-grid CFD rate (run on the
cluster's A40s), so the two sides are on different GPUs. It equals the latency speedup times the
parallelism factor (~7,510× this run; the batch is the whole holdout set, N=12,535 rows, evaluated in parallel,
which a CFD time integration cannot do). The like-for-like per-evaluation latency speedup is
~14,893×. Both are single wall-clock timing samples, in `figures/evidence_figure_metrics.json`.

The CFD cost is per step: each dataset row is one CFD timestep, so the figure divides by the CFD's
wall-clock time per step, the median over this corpus's 27 runs, 2.14 s per step
(`scripts/cfd_seconds_per_step.py`). A wingbeat takes `1/(f*·dt)` steps, so a per-wingbeat time
scales with the frequency by construction; the per-step time is not expected to depend much on the
kinematics (the fine pilot measured 2.00–2.02 s/step across its three configs), but over these 27
runs it spans 2.10–3.30 s per step, with the slowest runs on two of the six cluster nodes, so this
corpus does not separate a node effect from a kinematic one. The median is used because it is
robust to that slow tail. That wall time includes plotfile output (field capture every 100 steps)
and solver start-up; the force-only rate measured in the fine pilot is in
[`docs/force_surrogate/fine-grid-pilot-report.md`](../../docs/force_surrogate/fine-grid-pilot-report.md)
(~2.01 s/step, on the pre-hinge-fix geometry). The sidecar's `cfd_seconds_per_wingbeat` is this
per-step cost times the 2,000 rows of the figure's representative configuration (the f* = 1.00
holdout config); it is not a cost for every configuration's wingbeat. The coarse figure's denominator is not like-for-like
with this one: it is a fixed 144 s per wingbeat, the rounded 2.4 min (146 seconds) of a single A40
run of the 70° validation deck, which also wrote plotfiles (`examples/flapping_wing/RESULTS.md`,
Performance), whereas this one is the median per-step time over the sweep's own runs.

The `docker_image` recorded in `surrogate/run_metadata.json` and `figures/run_metadata.json` is the
image that produced this corpus's CFD data (the same digest as `run_metadata.json`); training ran
in a uv environment under WSL2 on a local RTX A5000, and the figure was generated natively on the
Windows host of the same machine, neither in that container.

### Regenerating

```bash
# 1. Train (WSL2, local A5000; from a clean, committed tree; see scripts/train_surrogate.py)
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/mosquito-cfd-train"
uv sync --frozen --group train
uv run --frozen --group train python scripts/train_surrogate.py \
    --dataset examples/prelim_sweep_fine/dataset.parquet \
    --out-dir <scratch>/surrogate \
    --docker-digest "$(python -c 'import json;print(json.load(open("examples/prelim_sweep_fine/run_metadata.json"))["docker_image"])')" \
    --timestamp <iso-8601-utc> \
    --seed 1234 --sweep-seeds 1235 1236 1237 1238 \
    --epochs 2000 --n-val-configs 3 --device cuda --wandb disabled

# 2. The CFD cost per step
uv run --frozen python scripts/cfd_seconds_per_step.py --metadata-dir examples/prelim_sweep_fine

# 3. The figure (from a clean tree, after copying the surrogate in)
uv run --frozen --group viz python scripts/make_evidence_figure.py \
    --predictions examples/prelim_sweep_fine/surrogate/holdout_predictions.parquet \
    --metrics examples/prelim_sweep_fine/surrogate/metrics.json \
    --grid fine --cfd-seconds-per-step <printed by step 2> \
    --docker-digest <same digest as step 1> --timestamp <iso-8601-utc> \
    --out-dir examples/prelim_sweep_fine/figures
```

The committed surrogate was trained twice from the same commit before it was committed: the
checkpoint and predictions were byte-identical and `metrics.json` differed only in its wall-clock
inference timing (an observed outcome on that host, not a bitwise-reproducibility claim;
`reproducibility.bitwise` stays `cpu_only`).

## Field capture (CC-F1)

`ns.init_iter = 2` and `amr.plot_int = 100` are set on every deck (`field_capture` in
`sweep_provenance.json`), so this corpus writes AMReX plotfiles every 100 steps in addition to the
force CSV — the input side of the Stage-2 field-surrogate work
([`docs/field_surrogate/roadmap.md`](../../docs/field_surrogate/roadmap.md)). `ns.init_iter = 0`
is a known defect that silently zeroes the plotfile velocity field with no other symptom (forces
are unaffected, since they come from the IB-particle marker velocity, not the plotfile); every
committed deck here sets `init_iter = 2` specifically to avoid it, and the post-run acceptance
gate below requires a passing CC-F1 velocity check on a field-capture corpus before it will pass.

## The CFL fix (`ns.cfl = 0.6`)

`ns.fixed_dt = 0.0005` is a **ceiling**, not the realized timestep — `ns.cfl` is an independent
limiter that can push the actual step below it, and at this grid's resolution it does (see
`estTimeStep()`/`predict_velocity`/`computeNewDt` in IAMReX, cited in
[`openspec/project.md`](../../openspec/project.md)'s Conventions → Running Simulations, and
`design.md` D1 of the `add-fine-corpus-run-verification` OpenSpec change). A first cluster run at
`ns.cfl = 0.3` (superseded, see below) was CFL-limited on 15 of 27 configs, truncating them mid-
wingbeat. This corpus is generated with **`ns.cfl = 0.6`** — the smallest value clearing every
config's measured CFL requirement (worst case `s55_f115_p30` needs `cfl ≥ 0.490`; `design.md` D2)
with a 22% margin — so the realized step equals the validated `dt = 5e-4` everywhere. Every
config's `run_metadata_<config>.json` confirms this: `interior_dt_below_nominal: false` and
`cycles_completed ≈ 2.0` for all 27.

## Run-observed metadata (six new fields)

Every `run_metadata_<config>.json` reports what the run **did**, not just what it was asked to do
— a metadata field computable from the deck alone (e.g. the deck's declared `fixed_dt`) is not
evidence about how the run actually behaved:

| Field | Meaning |
|---|---|
| `cfl` | This config's `ns.cfl` (per-config, since it's an opt-in override — see `sweep_manifest.json`). |
| `stop_time` | This config's target simulation end time (deck-declared, needed to judge `reached_stop_time`). |
| `realized_dt` | `{min, mean, max, frac_below_nominal}` of the **interior** (non-final) per-step `DT` actually taken, parsed from `run.log`. |
| `interior_dt_below_nominal` | `true` iff any interior step's realized `dt` fell below the deck's nominal `fixed_dt` — the hard, exact CFL-limiting signal (excludes only the final, deliberately clamped step that lands on `stop_time`). |
| `cycles_completed` | Wingbeats actually completed (`final_time × frequency_fstar`), vs. the intended `n_wingbeats = 2`. |
| `reached_stop_time` | Whether the run's final CSV time is within a loose (`2×fixed_dt`) sanity tolerance of `stop_time` — a diagnostic, not itself gating. |

`stability` is derived from **both** the deck's declared intent and these observed fields (never
just an echo of `fixed_dt`) — a value of `stable_at_5e-4` means the run was confirmed stable at
that step, not merely configured to attempt it.

## Superseded prior runs

`sweep_provenance.json`'s `supersession_history` records two prior cluster runs whose raw NFS
output predates fixes in this corpus's current decks and is no longer valid:

1. `force-surrogate-sweep-vb8t5` / `force-surrogate-retry-failed-trz9k` — predated the
   `fix-force-surrogate-sweep-hinge` geometry fix.
2. `force-surrogate-sweep-pzdhl` / `force-surrogate-sweep-zpkvt` — ran at `ns.cfl = 0.3` (15/27
   configs CFL-limited, see above); landed as PR #91, since corrected by this corpus's
   `ns.cfl = 0.6` regeneration.

## Regenerating the decks

```bash
uv run python examples/prelim_sweep_fine/generate_full_corpus.py \
    --cfl 0.6 --plot-int 100 --init-iter 2 --timestamp <iso-8601>
```

All three flags are required to reproduce the committed decks exactly — the script's own bare
defaults are force-only (`plot_int=-1`, `init_iter=None`) and would silently drop field capture if
omitted. Given the same flags/timestamp, regeneration is byte-identical to the committed corpus
(`test_committed_fine_corpus_matches_regeneration`).

## Running the sweep and rebuilding the dataset

Use the [`/submit-cluster-sweep`](../../.claude/commands/submit-cluster-sweep.md) runbook — it
covers the smoke-then-full submission sequence, the mid-sweep health check, and the mandatory
post-run steps below. In short, after every config finishes:

```bash
# 1. Per-config metadata (run once per config; see generate_run_metadata.py --help)
uv run python scripts/generate_run_metadata.py --config-name <name> \
    --pod-metadata <runs>/<name>/run_metadata.json --csv <runs>/<name>/IB_Particle_1.csv \
    --run-log <runs>/<name>/run.log --manifest sweep_manifest.json \
    --deck inputs/inputs.3d.<name> --tier fine-grid-corpus-full \
    --workflow-name <argo-workflow> --output run_metadata_<name>.json

# 2. Mandatory acceptance gate over the FULL 27-config corpus -- must pass before building the parquet
uv run python scripts/check_corpus_acceptance.py \
    --manifest examples/prelim_sweep_fine/sweep_manifest.json \
    --provenance examples/prelim_sweep_fine/sweep_provenance.json \
    --csv-dir <runs-dir> --metadata-dir examples/prelim_sweep_fine

# 3. Rebuild dataset.parquet (one row per config × timestep; expect 109,656 rows total)
uv run python scripts/extract_forces.py \
    --manifest examples/prelim_sweep_fine/sweep_manifest.json --input-dir <runs-dir> \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> --timestamp <iso-8601> \
    --out examples/prelim_sweep_fine/dataset.parquet \
    --units examples/prelim_sweep_fine/dataset.units.json \
    --metadata examples/prelim_sweep_fine/run_metadata.json
```

The acceptance gate (`mosquito_cfd.force_surrogate.acceptance_gate.run_acceptance_gate`) checks,
per config: no CFL limiting (`interior_dt_below_nominal`), deduplicated row count matches the
manifest's `max_step`, a passing CC-F1 velocity result is on record, and the settled-beat force
symmetry ratio is within tolerance (catches truncation even when the other checks miss it) — plus
row-count/units/NaN checks on the parquet itself. It re-derives at least one quantity (row count)
from raw run output rather than trusting every value in the metadata it gates.
