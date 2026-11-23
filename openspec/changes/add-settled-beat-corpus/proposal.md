# Proposal: add-settled-beat-corpus

Advances #192 (tracked in #197). Also advances #101 and #103.

## Why

Both force-surrogate corpora are 2-wingbeat runs, and the surrogates train on the second beat. That
beat is still settling: on the coarse grid the 30° pitch configuration is 0.8–5.0% of peak from
beat 6. The surrogate's held-out error is 1.1–1.8% of peak by the same measure. The fine grid's
settling rate has never been measured.

## What changes

One OpenSpec change in four pull requests. Every run needs the user's explicit go-ahead at
launch.

| PR | contents | then |
|---|---|---|
| 1 | settling metric and decision rule (`force_surrogate/settling.py`); `examples/settling_check/` with `PREREGISTRATION.md`, the long-run decks, control comparisons, report and figure scripts | settling runs on gh-04 |
| 2 | regeneration tooling that does not depend on the beat count: `--n-wingbeats`, time-based field capture, final-beat guards, the settling acceptance check, storage manifest, supersession writer (#103), step-based cluster sizing (#101), trainer refusal of multi-beat data | can be written while the gh-04 runs go |
| 3 | settling results, `DECISION.md` with the chosen beat count N, and the new corpus decks | cluster sweeps |
| 4 | the two regenerated corpora (datasets, run metadata, acceptance records, storage manifests, READMEs) | archive the change |

### Stage 1: fine-grid settling check (PR 1, then gh-04)

- **Metric and rule.** Settling is measured per wingbeat and per force/moment coefficient, as the
  RMS change from beat to beat in percent of peak.
  - A beat counts as settled when its estimated distance to the periodic state is at most **1% of
    peak, RMS, for all six coefficients**.
  - The 1% threshold must hold two ways, both computed by one function: on the long run, and on
    the run cut off at that beat (the same test the regenerated corpus will face).
  - The corpus beat count is the largest settled beat over all runs.
  - The rule and its constants are committed and merged before any run starts. The exact
    definitions are in `design.md` D2–D3, and their durable home is `PREREGISTRATION.md`.
- **Runs.** Each run is 8 beats, on the 256³ (fine) grid and also on the 64³ (coarse) grid. The
  configurations are the worst-settling corner found in the 27-config beat 1→2 comparison
  (exploration study E0), not the centre of the grid:

  | configuration | why |
  |---|---|
  | `s35_f085_p30` | top 3 on both grids for beat 1→2 change; the only low-frequency case; slowest per step |
  | `s45_f100_p30` | slowest-settling run measured so far (coarse, 6 beats) |
  | `s55_f115_p30` | high-frequency corner; also the configuration with the tightest timestep (CFL) margin |

- **Controls.** Four checks, each with a recorded result (`design.md` D4):
  - the same answer as the committed cluster run, bit for bit;
  - a run stopped and restarted from a checkpoint matches an uninterrupted run;
  - the first two beats of each long run equal the committed corpus;
  - the realized timestep never drops below nominal, on both grids, over all beats.
- **Reported but not gated.** Near-wing velocity settling for all three fine runs, and drift in
  mean lift per beat. The domain's slip walls may hold the late beats in a confined state; a
  separate issue covers the domain-size question.

### Stage 2: regenerate both corpora (PRs 2–4, cluster)

- **New directories.** The corpora go to `examples/settled_sweep` (coarse) and
  `examples/settled_sweep_fine`. The 2-beat corpora stay frozen, so every downstream consumer can
  be moved in its own later change.
- **Training beat.** It is the final requested beat (`wingbeat == n_wingbeats − 1`). Until each
  consumer is migrated, the trainer refuses a dataset with more than two beats instead of pooling
  them.
- **Field capture for later visualization.** Every beat of every configuration on both grids gets
  20 plotfiles at the same phases, triggered by time (`amr.plot_per`), plus one checkpoint per beat
  boundary (`amr.check_per`).
  - Phases are matched to within one timestep, with no build-up across beats.
  - The coarse corpus moves to `ns.init_iter = 2`, so that its plotfiles carry velocity.
- **Unchanged solver settings.** `ns.fixed_dt = 5e-4`; fine `ns.cfl = 0.6`; coarse `ns.cfl = 0.3`.
  The run-observed metadata, the acceptance gate and the corpus guards apply. The coarse corpus
  gets per-config run metadata for the first time.
- **Acceptance and verification.**
  - The acceptance gate checks settling on every configuration (all 54 runs), and the mid-sweep
    check applies the same test to configurations as they finish.
  - The deadline and retry budget are computed from each manifest's step counts and measured
    seconds per step.
  - A storage manifest records where the raw runs live and what they contain.

### Downstream reruns (list only; each is its own later change)

`design.md` D10 lists them: surrogates, both evidence figures, three coarse-vs-fine figures, V3,
bench PR 2, the README tables, the field-reader corpus pointer, and retiring the 2-beat corpora.

## Cost

| item | where | estimate |
|---|---|---|
| Stage 1 fine runs, 48,737 steps | gh-04 RTX A5000 | ≈101 h at 7.5 s/step (local probe, 2026-09); remeasured by control C1 before the long runs |
| Stage 1 coarse runs, 48,737 steps | gh-04 | ≈25 h at 1.857 s/step (E0b's measured coarse rate on the A5000) |
| Stage 1 disk | gh-04 (1.7 TB free), then the share | ≈0.31 TB |
| Fine corpus at N = 6 / 7 / 8 | cluster A40, 3 in parallel | 212 / 247 / 283 GPU-h; 3.0 / 3.5 / 4.0 days |
| Coarse corpus | cluster A40 | measured by its smoke run; no committed coarse rate exists |
| Disk, fine corpus at N = 6 / 8 | `Z:` share (≈36 TB free) | 2.05 / 2.73 TB |

Expected outcome, from the coarse data only: N is likely 6–8. Applied to the coarse 6-beat
`s45_f100_p30` run, the rule finds no settled beat within 6 beats (CF_z tail bound 1.18%).

## Impact

- **Specs.** `force-surrogate`.
  - PR 1 adds the settling metric, the pre-registration and the decision rule.
  - PR 2 adds the training beat, final-beat guards, settling acceptance, field capture, storage
    manifest and supersession writer.
  - PR 2 modifies run duration, the deadline auto-scale, the deadline override, the retry budget
    and the trainer's converged-beat filter. The PR 2 text is drafted in `stage2-spec-draft.md`.
  - `run-metadata`, `field-surrogate` and `visualization-tooling` need no delta. Their
    requirements are field-level, the plotfile reader finds steps from disk, and the settling
    figure follows the existing figure-sidecar convention.
- **BREAKING (cluster tooling).**
  - `submit_workflow.sh full` now always computes the deadline from the manifest; it no longer
    submits the committed value unpatched.
  - A manifest with zero configs is now an error.
  - The smoke `max-step` comes from the manifest.
  - Corpus drivers refuse to overwrite a corpus of a different length.
- **Code.**
  - New: `force_surrogate/settling.py`, `force_surrogate/storage_manifest.py`,
    `force_surrogate/supersession.py`, `scripts/check_settling.py`,
    `scripts/make_settling_figure.py`, `scripts/write_storage_manifest.py`,
    `examples/settling_check/`.
  - Changed: `sweep.py`, `corpus_guards.py`, `acceptance_gate.py`, `train.py` (refusal only), both
    corpus drivers, `cluster/argo/scripts/submit_workflow.sh`, `cluster/argo/workflows/*.yaml`,
    `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`, `.gitignore`,
    `.github/workflows/ci.yml` (ruff paths).
  - **Not touched:** `src/mosquito_cfd/surrogate_bench/`, the `add-surrogate-comparison-bench`
    change, PR #198.
- **Docs.**
  - `docs/CHANGELOG.md`; `openspec/project.md` (directory tree, cluster path mappings, settling
    principle); `.claude/commands/submit-cluster-sweep.md`; `cluster/argo/README.md`.
  - `docs/field_surrogate/roadmap.md` and `docs/force_surrogate/roadmap.md` (row 19).
  - Both 2-beat corpus READMEs get a "superseded by" note (PR 4, after bench PR 2).
- **Hardware.** This workstation's GPU is not used.

## Decided with the user (2026-11-23)

- Two stages in one change.
- Settling runs: three worst-case configurations, 8 beats each, on both grids.
- Tolerance: 1% of peak, RMS, all six coefficients.
- Velocity fields are measured and reported, not gated.
- Training data is the final beat only.
- The domain-confinement question gets its own issue; this change records it and measures
  mean-lift drift.

## Open for approval

1. **New directories instead of in-place regeneration** (`design.md` D5).
2. **Coarse field capture** with `ns.init_iter = 2`, about 43 GB at N = 8 (`design.md` D7). This
   changes the coarse start-up procedure relative to the old coarse corpus.
3. **Long-term data home.** Raw runs stay on the `Z:` cluster share. Whether `Z:` is backed up,
   and whether to keep a second copy on `G:` (27 TB free), is your call. The corpus READMEs will
   record the answer.
4. **Resume-on-retry is left out.** A preempted fine pod restarts from zero and can lose about 17 h
   at N = 8. If the restart control passes, a follow-up issue proposes resuming from checkpoints.
