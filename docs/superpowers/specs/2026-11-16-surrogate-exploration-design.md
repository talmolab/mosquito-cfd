# Surrogate-data exploration for the 2026-11-24 lab meeting: experiment plan

Status: **draft for approval** (2026-11-16). Nothing below has been run.

## Why

The lab meeting on Tuesday 2026-11-24 has an 18-minute block for surrogate theory and results. The
talk plan hoped for F3 arms A, B and C; none is started. This plan produces real, reportable results
by **Sunday 2026-11-22** from data that already exists, without new cluster runs.

The story the results should support has two parts:

1. **Hover gate (guaranteed result).** On the 27 hover configs, is the kinematics-only force
   surrogate (Track B) already as accurate as the CFD it was trained on? Where is it wrong, and how
   many CFD runs did it actually need?
2. **Flow compressibility (time-boxed stretch).** How many numbers does it take to describe the
   near-wing flow, and does a nonlinear encoder (`Mesh_Reduced`, arm B's encoder) beat a linear one
   (POD) at this data size?

Part 1 decides where field models have to earn their keep. Part 2 is the first measurement toward
the latent that April's slides sized at "between 64 and 256 dimensions".

## Goals, non-goals, anti-goals

**Goals**
- Seven short experiments (E0–E6 below), each ending in a report: question, method, result,
  caveats, next step.
- Every number traceable to a script and to named input data.
- A written recommendation on which surrogates suit this problem (draft below, revised by results).

**Non-goals**
- No production code. Nothing here is meant to merge as-is; a result worth keeping is promoted
  later through `/new-feature`.
- No new CFD on the cluster, no commanded-change configs, no arm C (DoMINO) attempt.
- No quasi-steady-model comparison or QS-plus-correction ablation. `van_veen_model.py` and the T4
  decomposition are being fixed in another session (#141, #133); no output of that model is used
  here. (`benchmarks/flapping_wing.py` imports it at module level, so E1's body-frame rotation
  loads the module, but the rotation never calls it.)

**Anti-goals** (would make this a failure even if it runs)
- A headline number that is one seed, one split or one config. Memory of this repo: config-level
  results are strongly seed-dependent, so every Track B comparison reports a range over at least
  5 seeds.
- A "within CFD uncertainty" claim that hides how weak the uncertainty estimate is.
- Silently fixing something that looks like a bug.

## Guardrails (from the request)

- All work in the worktree `.claude/worktrees/explore-surrogate-experiments`, branch
  `explore-surrogate-experiments`, cut from `main` at `80d653a`. No merging, no pushing to `main`.
  Commits stay local on this branch, and only once you say to commit.
- No RunAI jobs. If something needs an A40, it is written up as a next step.
- Anything that looks like a bug becomes a markdown issue draft under
  `experiments/issue-drafts/`. Drafts are not filed on GitHub and no fix is attempted.
- Two other worktrees are active (`add-real-comparison-figures`, `fix-van-veen-model-regrade-t4`).
  This work reads the same committed datasets and edits no file they would touch: nothing under
  `src/`, `scripts/`, `tests/`, `examples/` or existing `docs/` is modified.
- Vault: read-only, and only the files named in the request.

## Data used

| Data | Source | State |
|---|---|---|
| Fine force dataset | `examples/prelim_sweep_fine/dataset.parquet` at `80d653a` | Last re-extracted in #146 (`69d0000`); includes the #71 hinge fix and the #118 hinge-referenced moments. 27 configs, 109,656 rows, 2 wingbeats each. |
| Coarse force dataset | `examples/prelim_sweep/dataset.parquet` at `80d653a` | Same re-extraction history. |
| Committed fine surrogate | `examples/prelim_sweep_fine/surrogate/` | Retrained in #147 on the on-wing coefficients. |
| Fine field snapshots | `Z:\users\eberrigan\mosquito-cfd\examples\prelim_sweep_fine\runs\<config>\pltNNNNN` | About 41 live plotfiles per config, 513 MB each, 8 fields (velocity, density, tracer, ∇p) plus wing markers. |

Known data hazards, each checked in step 0 and restated in every report that depends on it:

- **Stale plotfiles.** Every run directory also holds `pltNNNNN.old.*` and `chk*.old.*`
  directories. `FieldCorpus` matches plotfile names with a full-match pattern, so they should be
  skipped (confirmed in `corpus.py`); step 0 asserts it. Step 0 also checks every plotfile it
  caches: `job_info` must show `ns.cfl = 0.6`, `ns.fixed_dt = 0.0005`, `amr.n_cell = 256 128 256`
  and IAMReX `f93dc794`, and the header time must equal step × 5e-4. I spot-checked one config
  while writing this: the live plotfile shows `ns.cfl = 0.6` and its `.old` twin shows 0.3, so the
  check does separate the two runs.
- **Wing markers.** Each plotfile has a `particles/` directory in AMReX's particle format, which
  no code in the repo reads. Wing position per snapshot is therefore rebuilt from `wing.vertex`
  and the prescribed kinematics (`benchmarks/wing_kinematics.py`), and cross-checked against the
  plotfile particles on one snapshot if `yt` can read them. *(My call.)*
- **Two beats only.** Each run is 2 wingbeats; the trainer already keeps only the second
  (`converged_min_wingbeat = 1`). The CFD notes say forces reach periodicity "within 2–3 WB".
- **Coarse in time.** A plotfile every 100 steps is about 17–24 snapshots per beat depending on
  frequency, and the three frequency groups do not sample the same phases.
- **Single-level grid.** The decks set `amr.max_level = 0`, so the field is one uniform
  256×128×256 grid (Δx = 0.03125) on an 8×4×8 domain with the hinge at (4, 0.5, 4).

## Approach

Considered:

1. **Exploratory scripts on one branch, analysis in marimo notebooks (chosen).** Fits six days;
   each number is reproducible from a script.
2. **One OpenSpec change per experiment.** The repo's normal process, but the review cycles would
   consume most of the time and the experiments are throwaway.
3. **Everything in notebooks.** Poor for unattended, resumable runs.

Chosen with Elizabeth on 2026-11-16, along with two design choices: the hover gate is reported
against three separate yardsticks, and `Mesh_Reduced` is judged against POD at equal latent size.

### Layout

```
experiments/
  README.md                 index: one line per experiment, status, link to report
  _cache/                   gitignored; local copies of field patches (tens of GB)
  common/                   small shared helpers (data loading, splits, plotting)
  e0_periodicity/           run.py, outputs/, report.py (marimo), report.html, figures/
  e1_hover_gate/            ...
  ...
  issue-drafts/             one markdown file per suspected bug
  surrogate-recommendation.md
```

- **`run.py`** does the heavy step and writes results to files (parquet, npz, json). It is
  resumable: finished pieces are skipped on rerun.
- **`report.py`** is a marimo notebook that only loads those files, draws the figures and holds the
  five-part report. It never recomputes anything expensive. It is exported headless to
  `report.html` and PNG figures so results are readable without opening marimo.
- Marimo runs through `uv run --with marimo`; `pyproject.toml` and `uv.lock` are not changed.
- Training runs in WSL2 with the existing `train` dependency group (PhysicsNeMo is Linux-only
  here), using a virtual environment in the WSL home directory so the worktree's Windows `.venv`
  is not clobbered. Analysis and field reading run natively on Windows.
- Experiments call the repo's library functions directly (`build_features`, `make_config_splits`,
  `train_model`, `compute_baseline_skill`, `build_phase_only_baseline`, `FieldCorpus`,
  `read_field_snapshot`). The provenance-strict `scripts/train_surrogate.py` CLI is not used,
  because it is built for committed artifacts; each `run.py` records commit, seed and inputs in
  its own small json instead.

### Step 0: setup and data checks (Tuesday morning)

- Confirm the WSL2 training environment reproduces the committed fine surrogate's seed 1234 on the
  A5000. The committed run was on CUDA, where the trainer promises determinism only as a warning
  (`metrics.json` records `"bitwise": "cpu_only"`), so the pass criterion is a tolerance, not
  equality: the same validation configs are drawn, and every target's held-out RMSE is within 2%
  of the committed value. The actual differences are reported. Outside that, stop and report
  before any ablation. *(My call.)*
- Time one Track B training run, to size the seed and subset counts in E2–E4.
- Run the stale-plotfile and `job_info` checks above.
- Time three full plotfile reads from `Z:`, then start the field cache as a background job:
  - **near-wing patch at full resolution:** x ∈ [1, 7], y ∈ [0, 4], z ∈ [2.5, 5.5]
    (192×128×96 cells), velocity only, float32, about 28 MB per snapshot and about 31 GB for all
    ~1,100 snapshots. The box covers the full stroke sweep (tip radius 3 at ±55°) with at least
    half a unit of margin in x; the z extent is my call and is checked against where the vorticity
    actually is before the cache is trusted.
  - **whole domain downsampled 4× (64×32×64):** velocity and ∇p, about 3 MB per snapshot.
  - plus the wing-marker positions per snapshot.
  The reader loads the full grid per plotfile regardless of the box, so the cost is about 570 GB of
  network reads once; nothing after the cache touches `Z:`.

### E0. Are two beats enough? (Tuesday)

- **Question:** how different are beat 1 and beat 2, per component and config?
- **Method:** phase-align the two beats of each fine and coarse run; report the normalized RMS
  difference per target, and where in the beat it sits.
- **Limit, stated up front:** two beats can show how large the beat-1-to-beat-2 change is; they
  cannot show that beat 2 is converged. See the optional item at the end for the run that could.

### E1. Hover gate (Tuesday–Wednesday)

- **Question:** is Track B's held-out error already inside the CFD's own uncertainty, per
  component?
- **Method:** held-out error from 5 seeds (the committed split, 6 holdout configs), expressed as a
  fraction of each config's peak coefficient, set beside three yardsticks without merging them:
  1. **T3c grid-convergence band** (3.7% normal, 27.6% chord). CFD-only and independent of #133
     and #141, but weak in four ways: it is the peak magnitude only; it is one 70°/45°, f* = 1
     point outside the sweep; it is in the body frame; and the T3c fine run used `dt = 2.5e-4`
     (`run_metadata_t3c.json`: `dt_reduced = true`) while coarse and medium used 5e-4, so the band
     mixes grid and timestep refinement. The corpus's fine runs are at 5e-4. The two percentages
     are applied as relative bands on each config's body-frame peak, which is a borrowing, and the
     report says so. To compare like with like, predictions and CFD are rotated into the body
     frame with the repo's own `body_frame_coefficients` and compared at the peak.
  2. **Coarse-versus-fine corpus difference**, per config, lab frame, whole waveform. Two grids
     only, so a sensitivity and not a GCI.
  3. **Beat-1-versus-beat-2 difference** from E0.
- **Output:** a per-component table of error against each yardstick and a one-line verdict per
  component and yardstick. Moments have no grid-convergence band; they get yardsticks 2 and 3 only.
- **Overlap note:** the `add-real-comparison-figures` worktree (#114) is building coarse-versus-fine
  figures. This experiment uses the coarse–fine difference only as a yardstick and makes no
  comparison figure of the two surrogates.

### E2. Where do the residuals cluster? (Wednesday)

- **Question:** are Track B's errors concentrated at stroke reversal, in particular components, or
  in particular corners of parameter space?
- **Why it is more than a fit diagnostic:** van Veen and Bomphrey place the history-dependent
  effects (wake capture, rotational mechanisms) at reversal, which instantaneous kinematics cannot
  see.
- **Method:** leave-one-config-out over all 27 configs, several seeds each (count set by step 0's
  timing, minimum 3), so every config, corners included, has out-of-sample residuals. Then:
  residual versus phase per component; share of squared error within a window around each
  reversal against the share expected if errors were uniform in phase; residual magnitude versus
  (φ, f*, α) and versus interior/edge/corner position; and the same phase profile for the
  coarse–fine difference and the seed-to-seed spread, so a reversal peak can be told apart from
  "that is just where the CFD is least certain".

### E3. Data-efficiency curve (Wednesday–Thursday)

- **Question:** how many CFD configs did the hover surrogate need?
- **Method:** fixed 6-config holdout; train on n ∈ {3, 6, 9, 12, 15, 18, 21} configs, several
  random nested subsets × 5 seeds each; skill over the phase-only baseline versus n, with ranges.
  Two structured designs alongside the random ones: the 8 corners plus centre, and a
  one-factor-at-a-time star. Separately, thin the rows per beat to see how coarse the force output
  could be.
- **What n counts:** every CFD run the model used, training and validation together. The repo's
  splitter always carves 3 validation configs and refuses n = 3, so E3 uses its own small splitter:
  validation is about one in seven of the n configs, at least one. The structured designs keep all
  their points for training and stop at a fixed epoch count instead. The subset draw, the
  validation carve and the model initialisation get separate seeds here, so the report can say how
  much of the spread is which. *(My call.)*
- **Caveat built in:** the phase-only baseline is rebuilt from each training subset, so skill stays
  comparable across n.
- **Seeds in E2 and E4:** these keep the repo's convention, where one seed sets both the
  validation carve and the initialisation, so their ranges are directly comparable with the
  committed 5-seed ranges. The ranges therefore mix the two sources of variation.

### E4. Track B ablations (Thursday)

- **Question:** which inputs and how much model does the hover force map need?
- **Method:** 5 seeds each, same holdout:
  - inputs: drop each of φ, f*, α in turn; replace f* with Re; phase as 1, 2, 3 or 4 harmonics;
  - model: width {16, 64, 256} × depth {1, 3, 5};
  - a non-neural comparator: ridge regression on Fourier harmonics in phase × low-order
    polynomials in (φ, f*, α). If this matches the MLP, the honest statement is that periodic hover
    is a small family of smooth waveforms.

### E5. POD spectrum of the near-wing velocity field (Thursday–Friday)

- **Question:** how many linear modes describe the flow, and does that number transfer to configs
  the basis has never seen?
- **Method:** method of snapshots on the cached patch (second beat only), mean removed:
  - energy spectrum and modes-for-90/99% per config, and pooled over the 21 training configs;
  - **the latent-sizing number:** reconstruction error on the 6 held-out configs versus number of
    modes, using a basis built from training configs only;
  - the same in the whole-domain downsampled cache, to see whether the near-wing patch is harder
    or easier than the wake;
  - a probe: linear regression from the leading mode coefficients to the six force coefficients.
- **Caveats built in:** the count of snapshots caps the rank (about 20 per config, about 430
  pooled), so "modes for 99%" is a lower bound on what a finer time sampling would need; a body
  moving through a fixed grid is the classic case where POD spectra decay slowly, so a slow decay
  here is evidence about the lab frame, not about the flow's true complexity. If time allows, the
  spectrum is repeated in the wing-fixed frame (patch resampled to follow the wing) to separate
  the two.

### E6. Can `Mesh_Reduced` encode the patch? (Friday–Saturday, most droppable)

- **Question:** does PhysicsNeMo's `Mesh_Reduced` train on a near-wing patch on the A5000, and
  does it reconstruct held-out configs better than POD at the same latent size?
- **Method, in order, stopping at the first failure and reporting it:**
  1. Import and run `Mesh_Reduced` in the WSL2 environment on the PhysicsNeMo vortex-shedding
     example's scale. Its graph dependencies may not be in the `train` group; if they need
     installing, that is done in the WSL-home environment only and recorded.
  2. Build a graph once from the patch downsampled to about 16k nodes (48×32×12 or similar), about
     ten times the example. Train the encoder–decoder on training-config snapshots, velocity only.
  3. Compare held-out reconstruction error against E5's POD at the same number of latent values,
     and report memory, time per step and encode latency.
  4. Only if 2–3 work: one larger patch (about 100k nodes) to see where it stops fitting.
- **Not attempted:** `Sequence_Model` rollout. At 17–24 snapshots per beat there is too little
  temporal data to say anything about latent dynamics.
- **Stretch comparator:** a small 3-D convolutional autoencoder on the same patch, since the grid
  is uniform. Dropped first if time is short.

### Wrap-up (Sunday morning)

`experiments/README.md` as the index, each report exported, `surrogate-recommendation.md` revised
against the results, and a one-page summary listing which numbers are slide-ready and which are
not.

## Unattended operation

- Experiments run in the order above. Each report is written when its experiment finishes, so a
  late failure never costs an earlier result.
- **Stop and wait for you** if: the seed-1234 reproduction fails; the plotfile provenance check
  fails; local disk would drop below 60 GB free; or anything would require touching files outside
  `experiments/` and this document.
- **Skip and continue** if a single experiment fails for its own reasons: the failure is written up
  as that experiment's report.
- The time box for E6 is fixed: it ends Saturday night whatever state it is in.

## Which surrogates suit this problem (draft, revised after the results)

This is my current view from the roadmaps, the papers and the PhysicsNeMo source reading already
recorded in the field roadmap. Your DoMINO and IAMReX notes are empty and there is no
`Mesh_Reduced` note, so none of this rests on the vault.

1. **Periodic hover forces: a kinematics-only model is the right tool, and it exists.** Track B's
   skill is about 0.98–0.99 over the phase-only baseline. E4 tests whether even the MLP is more
   than needed. Once #141 and #133 are fixed, a quasi-steady model plus a learned correction is the
   natural next variant, as April's slides proposed.
2. **Changing commands: test history dependence with kinematics history first.** A windowed MLP or
   a small recurrent model on the recent kinematics is cheap, needs no fields, is trivially fast
   in an RL loop, and directly answers whether a flow latent is needed. This is arm A on the
   commanded-change configs, which do not exist yet.
3. **If a flow latent is needed: start linear, then grid-based.** POD plus a small latent-dynamics
   model is the baseline any learned encoder must beat. Because the corpus is a single uniform
   grid, a convolutional autoencoder or a Fourier neural operator fits the data's structure
   directly; the closest published precedent (immersed-boundary swimmers under prescribed
   kinematics) used a grid-based FNO.
4. **`Mesh_Reduced`:** worth the feasibility probe because it is the one field-to-latent encoder
   PhysicsNeMo ships, but on a uniform grid its graph machinery buys nothing a convolution does
   not, and it is unproven above about 2k nodes. E6 measures this.
5. **DoMINO:** lowest priority for the RL goal. It maps geometry to fields, has no state to carry
   history, has no published result on continuously moving geometry, and the adapter is known
   incomplete (#112). It could serve as a pose-and-phase field predictor for periodic hover, which
   is the case that needs a surrogate least.
6. **Still not appropriate:** a PINN (no need to solve the PDE again) and MeshGraphNet stepping the
   full field (far too slow for an RL inner loop).

## Decisions I made that you can overrule

- The near-wing patch extents and the 16k-node starting size for `Mesh_Reduced`.
- Fields cached as float32 (the plotfiles are float64); POD and autoencoder errors are far above
  float32 precision.
- Velocity only for POD and `Mesh_Reduced`; ∇p is cached downsampled but not analysed unless time
  allows.
- Leave-one-config-out for the residual map, in addition to the committed 6-config holdout.
- Issue drafts live in the worktree, not in the vault's `github_issues` folder, because the request
  limits vault access to named files.
- The cache lives under the worktree in a gitignored folder on `C:` (158 GB free today).

## One optional item that needs your yes

**A longer coarse run on the local A5000.** E0 cannot show that beat 2 is converged, because no run
in either corpus is longer than 2 beats. One coarse 64×32×64 config run for 6 beats in the local
Docker image (not RunAI; the repo has a recipe, roughly half an hour) would measure beat-to-beat
convergence directly and tell you how much to trust every 2-beat result on the slides. It is new
CFD, so I will not run it unless you say so.
