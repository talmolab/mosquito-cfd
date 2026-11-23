# Proposal: add-settled-beat-corpus

Advances #192 (tracked in #197). Also advances #101 and #103. Related: #204 (domain size), #205
(checkpoint restart), #206 (CC-F1 claim).

## Why

Both force-surrogate corpora are 2-wingbeat runs, and the surrogates train on the second beat.
That beat is still settling. In the exploration study E0b (three local 6-beat runs on the coarse
grid), beat 2 differs from beat 6 by 0.8–5.0% of peak at 30° pitch (RMS, phase ≥ 0.05). The force
surrogate's held-out error, measured the same way in exploration study E1, is 1.1–1.8% of peak. No
fine-grid run longer than 2 beats exists, so the fine grid's settling rate is unknown.

## What changes

This is one OpenSpec change delivered in four pull requests. Every run needs the user's explicit
go-ahead at launch.

| PR | contents | then |
|---|---|---|
| 1 | the settling metric and decision rule (`force_surrogate/settling.py`) and `examples/settling_check/` (`PREREGISTRATION.md`, long-run decks, force comparison, report and figure scripts) | settling runs on gh-04 (a second lab RTX A5000 machine) |
| 2 | regeneration tooling that does not depend on the beat count (details below) | written while the gh-04 runs go; **merged only if PR 3 decides to regenerate** |
| 3 | the settling results, `DECISION.md` with the chosen beat count N, and the new corpus decks | cluster sweeps |
| 4 | the two regenerated corpora: datasets, run metadata, acceptance records, storage manifests, READMEs | archive the change |

PR 2's tooling covers:
- `--n-wingbeats` for the corpus drivers;
- time-triggered field capture;
- final-beat guards and a settling acceptance check;
- a storage manifest;
- a supersession writer (#103);
- step-based cluster sizing (#101);
- a trainer refusal of multi-beat data.

### Stage 1: fine-grid settling check (PR 1, then gh-04)

**Metric.** For each wingbeat and each of the six force and moment coefficients, the metric gives:
- the RMS change from the previous beat, as a fraction of peak, compared sample by sample;
- a **tail bound**: how far the last beat still is from the periodic state, extrapolated from how
  fast the changes shrink;
- a noise floor set from the run's own sampling jitter.

**Rule.** A beat count N passes when the estimated distance to the periodic state is at most
**1% of peak for all six coefficients**, in two ways:
1. on the long run;
2. on the run cut off at N beats, which is the same test the regenerated corpus will face.

The corpus uses the largest N over all runs. The rule and its constants are merged before any
run starts. The exact definitions are in `design.md` D2–D3, and their durable home is
`PREREGISTRATION.md`.

**Runs.** 8 beats each, on both the 256³ fine grid and the 64³ coarse grid, using the
worst-settling corner from the 27-config beat-1→2 comparison (exploration study E0):

| configuration | why |
|---|---|
| `s35_f085_p30` | among the three worst on both grids; the only low-frequency case; slowest per step |
| `s45_f100_p30` | the slowest-settling run measured so far (E0b) |
| `s55_f115_p30` | high-frequency corner; also the configuration with the tightest timestep (CFL) margin |

**Images.** Each grid uses the image its 2-beat corpus ran, so the new runs extend the old ones
like for like.

**Controls** (`design.md` D4), each with a recorded result:
- **C1**: the first 400 steps reproduce the committed corpus run on each grid, to `1e-9` of each
  column's maximum, which is far above round-off.
- **C3**: the first two beats of every long run reproduce the committed corpus to the same
  tolerance.
- **C4**: the realized interior timestep never drops below nominal, over all 8 beats.
- There is no restart control, because checkpoint restarts are known not to be faithful (#205).

**Reported, not gated:**
- near-wing velocity settling for all three fine runs;
- mean-lift drift per beat. The domain's slip walls may hold the late beats in a confined state
  (#204).

### Stage 2: regenerate both corpora (PRs 2–4, cluster)

- **New directories.** The corpora go to `examples/settled_sweep` (coarse) and
  `examples/settled_sweep_fine`. The 2-beat corpora stay frozen, so each downstream consumer moves
  in its own later change.
- **Training beat.** The training beat is the final requested beat
  (`wingbeat == n_wingbeats − 1`). Until consumers are migrated, the trainer refuses a dataset
  with more than two beats instead of pooling them.
- **Field capture for later visualization.**
  - Every beat of every configuration, on both grids, gets 20 plotfiles at the same phases,
    triggered by time (`amr.plot_per`), with no build-up of phase error across beats.
  - One checkpoint per beat boundary (`amr.check_per`) is kept for when #205 is fixed.
  - Coarse plotfiles already carry velocity at the current `ns.init_iter = 0` (checked; #206).
- **Unchanged solver settings.** `ns.fixed_dt = 5e-4`; fine `ns.cfl = 0.6` and
  `ns.init_iter = 2`; coarse `ns.cfl = 0.3` and `ns.init_iter = 0`.
- **Unchanged checks.** The run-observed metadata, the acceptance gate and the corpus guards
  apply. The coarse corpus also gets per-config run metadata for the first time.
- **New checks.**
  - The acceptance gate checks settling on every configuration (54 runs), and the mid-sweep check
    applies the same test as configurations finish.
  - The cluster deadline is computed from each manifest's step counts and measured seconds per
    step.
  - A storage manifest records where the raw runs live and what they contain.

### Downstream reruns (list only; each is its own later change)

`design.md` D10 lists them: surrogates, both evidence figures, three coarse-vs-fine figures, V3,
bench PR 2, README tables, the field-reader corpus pointer, restart and resume (#205), and retiring
the 2-beat corpora.

## Cost

| item | where | estimate |
|---|---|---|
| Stage 1 fine runs (48,737 steps) | gh-04 | ≈101 h at 7.5 s/step (local A5000 probe, 2026-09); C1 remeasures this before the long runs |
| Stage 1 coarse runs (48,737 steps) | gh-04 | ≈25 h at 1.857 s/step (E0b, same image, A5000) |
| Stage 1 disk | gh-04 (1.7 TB free), then the share | ≈0.31 TB |
| Fine corpus at N = 6 / 7 / 8 | cluster A40, parallelism 3 | 212 / 247 / 283 GPU-h; 3.0 / 3.5 / 4.0 days without retries. The deadline allows for two retries (97 h at N = 6) |
| Coarse corpus | cluster A40 | measured by its smoke run |
| Disk, fine corpus at N = 6 / 8 | `Z:` share (≈36 TB free) | 2.05 / 2.73 TB, of which 0.37 / 0.50 TB is checkpoints |

**Expected outcome.** On the coarse 6-beat data, the rule finds no settled beat within 6 beats for
either configuration. The centre configuration misses by a hair (CF_my 1.007%); the 30° pitch one
misses by 25%. With 8 beats the likely results are N = 7–8, which needs cost approval, or `stop`.

## Impact

- **Specs** (`force-surrogate`):
  - PR 1 adds the settling metric, the decision rule, the pre-registration, the deck key set and
    the settling report.
  - PR 2 adds the training beat, settling acceptance, field capture, storage manifest,
    supersession writer and cluster sizing.
  - PR 2 also modifies nine requirements, named exactly in `stage2-spec-draft.md`.
  - `run-metadata`, `field-surrogate` and `visualization-tooling` need no delta: their
    requirements are field-level, the plotfile reader finds steps from disk, and the figure
    follows the existing sidecar convention.
- **BREAKING (cluster tooling):**
  - `submit_workflow.sh full` always computes the deadline from the manifest's step counts and
    `cluster_sizing.json`;
  - zero configs is an error;
  - `examples/prelim_sweep` needs `--active-deadline-seconds`;
  - the smoke `max-step` comes from the manifest;
  - the corpus drivers refuse to overwrite a corpus of a different length.
- **Code, new:** `force_surrogate/settling.py`, `force_surrogate/storage_manifest.py`,
  `force_surrogate/supersession.py`, `scripts/check_settling.py`,
  `scripts/make_settling_figure.py`, `scripts/write_storage_manifest.py`, `examples/settling_check/`.
- **Code, changed:** `sweep.py`, `corpus_guards.py`, `acceptance_gate.py`, `train.py` (refusal
  only), both corpus drivers, `cluster/argo/scripts/submit_workflow.sh`,
  `cluster/argo/workflows/*.yaml`, `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`,
  `.gitignore`, `.github/workflows/ci.yml` (ruff paths).
- **Not touched:** `src/mosquito_cfd/surrogate_bench/`, the `add-surrogate-comparison-bench`
  change, PR #198.
- **Docs:**
  - `docs/CHANGELOG.md`, `openspec/project.md`, `.claude/commands/submit-cluster-sweep.md`,
    `cluster/argo/README.md`;
  - both roadmaps;
  - "superseded by" notes in both 2-beat corpus READMEs (PR 4, after bench PR 2).
- **Hardware.** This workstation's GPU is not used.

## Decided with the user (2026-11-23)

- Two stages in one change.
- Three worst-case configurations, 8 beats each, on both grids.
- 1% of peak, RMS, on all six coefficients.
- Velocity fields measured and reported, not gated.
- Training on the final beat only.
- The domain question recorded, with mean-lift drift measured, and filed as #204.

## Open for approval

1. **New corpus directories** rather than regenerating in place (`design.md` D5).
2. **Coarse field capture** (≈41 GB at N = 8; `design.md` D7).
3. **Keep the per-beat checkpoints** (0.37–0.50 TB on `Z:`) even though they cannot be used until
   #205 is fixed. The alternative is to drop them and save that space.
4. **Long-term data home.** Raw runs stay on the `Z:` cluster share. Whether `Z:` is backed up,
   and whether to keep a second copy on `G:` (27 TB free), is your call; task 15.2 asks before the
   READMEs are written.
5. **The rule is strict.** With the rising-ratio safeguard the rule is conservative, and `stop` at
   8 beats is a real possibility. That outcome spends no cluster time and comes back to you.
