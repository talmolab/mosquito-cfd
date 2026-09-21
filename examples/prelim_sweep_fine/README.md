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

**Not yet built:** unlike the coarse corpus, this corpus has no `surrogate/` or `figures/` yet —
training the force surrogate on the fine-grid data and producing an evidence figure is future work.

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
