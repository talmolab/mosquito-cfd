# Surrogate-Data Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run seven exploratory experiments (E0–E6) on the post-#146 force datasets and the fine
field snapshots, each ending in a five-part report, by Sunday 2026-11-22.

**Architecture:** One `experiments/` tree in the worktree. Each experiment has a resumable `run.py`
that writes result files and a marimo `report.py` that only reads them. A small `common/` package
wraps the repo's library; nothing outside `experiments/` and `docs/superpowers/` is modified.

**Tech Stack:** Python via `uv`; numpy, pandas, matplotlib, yt (Windows, analysis and field reads);
PhysicsNeMo + CUDA torch in WSL2 (`--group train`) on the RTX A5000; marimo via `uv run --with marimo`.

**Spec:** `docs/superpowers/specs/2026-11-16-surrogate-exploration-design.md`

## Global Constraints

- Worktree: `C:\repos\mosquito-cfd\.claude\worktrees\explore-surrogate-experiments`, branch
  `explore-surrogate-experiments`. Verify `git branch --show-current` before any git command.
  No merge, no push. Local commits only if Elizabeth has said to commit; otherwise leave the tree
  uncommitted and skip every "Commit" step.
- No RunAI, no Argo, no `kubectl`. No new CFD of any kind unless Elizabeth approves the optional
  6-beat local run.
- Modify nothing under `src/`, `scripts/`, `tests/`, `examples/`, existing `docs/`, `pyproject.toml`
  or `uv.lock`. Never write to `Z:`. Never open `C:\vaults` beyond the files named in the request.
- Do not use any output of `mosquito_cfd.benchmarks.van_veen_model`.
- Suspected bug → `experiments/issue-drafts/<slug>.md` (what, where `file:line`, evidence, why it
  matters). No fix, no `gh issue create`.
- Track B comparisons report a range over ≥ 5 seeds (E2's leave-one-out: ≥ 3). Seeds start at 1234.
- Fit everything on training configs only: standardizer, phase-only baseline, POD basis, encoders.
  The 6 holdout configs (`sweep_manifest.json["holdout"]`) are never used for early stopping.
- Force data: `examples/prelim_sweep{,_fine}/dataset.parquet` at `80d653a`, second beat only
  (`wingbeat == 1`) unless the experiment is about beats.
- Field data: live `pltNNNNN` only, each passing the provenance check of Task 2.
- Every `run.py` writes `outputs/run_record.json`: git commit, dirty flag, seeds, input file
  sha256s, start/end time, and for field work the list of snapshots used.
- Every report has exactly five headed parts: Question, Method, Result, Caveats, Next step, and
  names the data it used.
- Stop and wait for Elizabeth if: Task 1's reproduction gate fails; any provenance check fails;
  free space on `C:` would fall below 60 GB; or a step needs a file outside the allowed tree.
- E6 ends Saturday 2026-11-21 23:59 in whatever state it is in.

Commands used throughout (run from the worktree root):

```bash
# Windows: analysis, field reads, tests, reports
uv run python experiments/<exp>/run.py
uv run pytest experiments/tests -q
uv run --with marimo marimo export html experiments/<exp>/report.py -o experiments/<exp>/report.html

# WSL2: anything that trains
wsl -e bash -lc "cd /mnt/c/repos/mosquito-cfd/.claude/worktrees/explore-surrogate-experiments && \
  UV_PROJECT_ENVIRONMENT=\$HOME/venvs/mosquito-explore uv run --frozen --group train \
  python experiments/<exp>/run.py --device cuda"
```

## Review Focus

1. **A stale `.old` plotfile or a `cfl = 0.3` snapshot enters the cache** → the cache must refuse
   it and stop. Test in Task 2 (`test_provenance_rejects_cfl_03`, `test_old_dirs_not_listed`).
2. **A read from `Z:` fails halfway through the cache** → rerun resumes, no half-written file is
   ever loaded, and reports list exactly which snapshots were used. Test in Task 2
   (`test_cache_is_atomic_and_resumable`).
3. **The three frequency groups have different rows per beat (2353 / 2000 / 1739)** → every
   cross-config or cross-grid comparison goes through one phase grid. Test in Task 1
   (`test_waveform_resamples_known_sinusoid`).
4. **Information leaks from holdout into a fit** (baseline, standardizer, POD basis, validation
   carve) → splits are asserted disjoint. Tests in Task 1 (`test_carve_never_touches_holdout`) and
   Task 7 (`test_basis_uses_training_snapshots_only`).
5. **A training or `Mesh_Reduced` run dies (OOM, missing dependency)** → the experiment writes its
   report with the failure as the result; later experiments still run. Each `run.py` wraps its
   per-item loop so one failed item is recorded in `outputs/failures.json` and skipped.

---

### Task 1: Scaffold, shared helpers, environment gate

**Files:**
- Create: `experiments/README.md`, `experiments/.gitignore` (ignores `_cache/`, `**/outputs/*.pt`),
  `experiments/common/{__init__,data,splits,fit,record}.py`, `experiments/tests/test_common.py`,
  `experiments/step0_environment/run.py`, `experiments/step0_environment/report.md`

**Interfaces (produced):**
- `data.TARGETS = ("CF_x","CF_y","CF_z","CF_mx","CF_my","CF_mz")`
- `data.load_dataset(grid: Literal["coarse","fine"]) -> pd.DataFrame`
- `data.holdout_configs() -> tuple[str, ...]` (from the fine manifest; assert equal to coarse's)
- `data.waveforms(df, *, wingbeat: int = 1, n_phase: int = 256) -> dict[str, np.ndarray]`:
  config → `(n_phase, 6)`, periodic linear interpolation onto `np.arange(n_phase)/n_phase`
- `splits.carve_validation(configs, *, seed: int, frac: float = 1/7, min_val: int = 1) -> tuple[list[str], list[str]]`
- `splits.nested_subsets(pool, sizes, *, seed: int) -> dict[int, list[str]]` (each a superset of the previous)
- `fit.FitResult(preds: np.ndarray, val_configs: list[str], best_epoch: int, seconds: float)`
- `fit.fit_predict(df, train_configs, val_configs, test_configs, *, seed, feature_fn=None, width=64, depth=3, epochs=2000, device="cuda") -> FitResult`:
  wraps the repo's `build_features` / `Standardizer` / `build_model` / `train_model` / `predict` in
  the call order of `train.py::_fit_one_seed` (read `train.py:1095-1169` first). `val_configs=[]`
  means fixed-epoch training with no early stopping.
- `fit.skill(df, train_configs, test_configs, preds) -> dict[str, float]`: wraps
  `build_phase_only_baseline` + `compute_baseline_skill`, baseline built from `train_configs` only.
- `record.write_run_record(out_dir: Path, **fields) -> None`

- [ ] **Step 1: Write failing tests** in `experiments/tests/test_common.py`:

```python
def test_waveform_resamples_known_sinusoid():
    # two fake configs with 1739 and 2353 rows/beat, CF_x = sin(2*pi*phase)
    w = waveforms(fake_df, n_phase=256)
    for cfg in w:
        assert np.allclose(w[cfg][:, 0], np.sin(2*np.pi*np.arange(256)/256), atol=1e-4)

def test_carve_never_touches_holdout():
    pool = [c for c in all_configs if c not in holdout_configs()]
    train, val = carve_validation(pool, seed=1234)
    assert not (set(train) | set(val)) & set(holdout_configs())
    assert not set(train) & set(val) and len(val) == 3   # round(21/7)

def test_carve_min_one_at_n3():
    train, val = carve_validation(["a", "b", "c"], seed=0)
    assert len(val) == 1 and len(train) == 2

def test_nested_subsets_are_nested():
    s = nested_subsets(pool, [3, 6, 9], seed=0)
    assert set(s[3]) < set(s[6]) < set(s[9])

def test_holdout_matches_committed_split_column():
    df = load_dataset("fine")
    assert set(df[df.split == "holdout"].config_name) == set(holdout_configs())
```

- [ ] **Step 2:** `uv run pytest experiments/tests -q` → fails on import.
- [ ] **Step 3:** Implement `common/` to the interfaces above.
- [ ] **Step 4:** `uv run pytest experiments/tests -q` → all pass.
- [ ] **Step 5: WSL2 environment.** Create the venv with the WSL command above running
  `python -c "import torch, physicsnemo; print(torch.cuda.is_available())"` → `True`.
- [ ] **Step 6: Reproduction gate.** `step0_environment/run.py --device cuda`: reproduce the
  committed fine surrogate's seed 1234 using the committed split and
  `examples/prelim_sweep_fine/surrogate/metrics.json` as the oracle. Pass = same `val_configs`
  (`s55_f100_p60`, `s55_f115_p30`, `s55_f115_p60`) and every target's held-out RMSE within 2% of
  the committed `seed_sweep.runs[0].per_target[*].rmse`. Record actual differences and the
  seconds per fit in `report.md`. **Fail → stop and wait.**
- [ ] **Step 7:** From the seconds per fit, write into `report.md` the seed and subset counts that
  E2–E4 will use so that all three finish inside 10 GPU-hours total (floors: E2 3 seeds, E3 3
  subset draws × 5 seeds, E4 5 seeds).
- [ ] **Step 8: Commit** (if authorised): `experiments: scaffold, shared helpers, environment gate`.

### Task 2: Field cache with provenance checks

**Files:**
- Create: `experiments/field/{__init__,provenance,cache}.py`, `experiments/tests/test_field.py`,
  `experiments/field/build_cache.py`

**Interfaces (produced):**
- `provenance.check_plotfile(plt: Path, step: int) -> None`: raises `ProvenanceError` unless
  `job_info` has `ns.cfl = 0.6`, `ns.fixed_dt = 0.0005`, `amr.n_cell = 256 128 256`, an IAMR hash
  containing `f93dc794`, and the Header time equals `step * 5e-4` to 1e-9.
- `cache.PATCH_LO = (1.0, 0.0, 2.5)`, `cache.PATCH_HI = (7.0, 4.0, 5.5)` → 192×128×96 cells
- `cache.cache_snapshot(corpus: FieldCorpus, config: str, step: int, root: Path) -> Path`:
  writes `root/<config>/<step:05d>.npz` with `patch_u` float32 `(192,128,96,3)`, `full4_u` and
  `full4_gradp` float32 `(64,32,64,3)` by 4×4×4 block mean, `time`, `phase`, `wingbeat`; writes to a
  `.tmp` name then renames.
- `cache.load(root, config, step) -> dict`; `cache.index(root) -> pd.DataFrame`
  (config, step, time, phase, wingbeat, path)
- `cache.wing_markers(config: str, time: float) -> np.ndarray (n_markers, 3)`: from
  the corpus's `wing.vertex` (at the `Z:` corpus root; read once and copied into `_cache/`), the
  config deck's scale and hinge (`examples/prelim_sweep_fine/inputs/inputs.3d.<config>`), and
  `benchmarks/wing_kinematics.py`.

- [ ] **Step 1: Failing tests** in `test_field.py` (all against fabricated directories in `tmp_path`,
  no `Z:`):

```python
def test_provenance_rejects_cfl_03(tmp_path):      # job_info with ns.cfl = 0.3 -> ProvenanceError
def test_provenance_rejects_wrong_time(tmp_path):  # Header time 0.83 for step 2000 -> ProvenanceError
def test_provenance_accepts_live(tmp_path):        # cfl 0.6, dt 5e-4, time 1.0, step 2000 -> no raise
def test_old_dirs_not_listed(tmp_path):            # plt00100 + plt00100.old.123 -> FieldCorpus.steps == [100]
def test_block_mean_downsample():                  # arange grid: 4x block mean equals analytic mean
def test_cache_is_atomic_and_resumable(tmp_path):  # a leftover .tmp is ignored by index(); rerun rewrites it
def test_markers_rotate_about_hinge():             # at t=0 markers equal the scaled rest geometry; hinge distance preserved at all t
```

- [ ] **Step 2:** run → fail. **Step 3:** implement. **Step 4:** run → pass.
- [ ] **Step 5:** Time three real reads from `Z:` (one per frequency group); record seconds and
  peak memory in `experiments/step0_environment/report.md`. Check free space on `C:` ≥ 100 GB.
- [ ] **Step 6:** On one mid-stroke snapshot of `s55_f115_p60` (largest sweep, fastest), compute
  vorticity magnitude over the full grid and report the fraction of enstrophy inside the patch.
  If < 90%, widen z downward in 0.5 steps until ≥ 90% or the patch would exceed 45 GB cached;
  record the final extents in `cache.py` and the report before bulk caching.
- [ ] **Step 7:** Try reading the plotfile `particles/` with `yt` on that snapshot; if it loads,
  compare against `wing_markers` (max distance < one cell, 0.03125). A mismatch → issue draft, and
  E5's wing-frame variant is dropped. If `yt` cannot read it, note that and move on.
- [ ] **Step 8:** Launch `build_cache.py` in the background over all 27 configs (resumable; logs
  per-snapshot failures to `_cache/failures.json`; stops if free space < 60 GB). Tasks 3–6 proceed
  while it runs.
- [ ] **Step 9: Commit** (if authorised): `experiments: field cache with provenance checks`.

### Task 3: E0 — beat 1 versus beat 2

**Files:** Create `experiments/e0_periodicity/{run.py,report.py}`; outputs `outputs/beat_diff.parquet`.

**Consumes:** `data.load_dataset`, `data.waveforms(df, wingbeat=0|1)`.

- [ ] **Step 1:** `run.py`: for each grid × config × target, `nrms = rms(w1 − w0) / rms(w1)` and the
  phase profile `|w1 − w0|` (256 points). Before trusting `wingbeat == 0`, check for duplicated
  `t = 0` rows per config and drop the impulsive-start rows `time < 0.005`; a duplicate found is an
  issue draft, since the extractor is meant to dedup.
- [ ] **Step 2: Check:** `beat_diff.parquet` has 2 × 27 × 6 = 324 rows, no NaN.
- [ ] **Step 3:** `report.py` (marimo): heatmap config × target of `nrms` per grid; phase profile of
  the difference averaged over configs; the five parts. Caveat text must state that two beats
  cannot show beat 2 is converged.
- [ ] **Step 4:** export HTML; add the line to `experiments/README.md`. **Commit** if authorised.

### Task 4: E1 — hover gate

**Files:** Create `experiments/e1_hover_gate/{run.py,report.py}`; outputs
`outputs/{predictions.parquet,gate_table.parquet}`.

**Consumes:** `fit.fit_predict`, `fit.skill`, `data.waveforms`, E0's `beat_diff.parquet`,
`mosquito_cfd.benchmarks.flapping_wing.body_frame_coefficients` (read its signature at
`flapping_wing.py:379` first).

- [ ] **Step 1:** Train seeds 1234–1238 on the committed split (repo convention: one seed sets
  validation carve and init, via `make_config_splits`); save holdout predictions for all seeds.
- [ ] **Step 2:** Per holdout config × target, on the 256-point phase grid:
  `err = rms(pred − cfd_fine) / peak|cfd_fine|` (median and range over seeds);
  `y2 = rms(cfd_coarse − cfd_fine) / peak|cfd_fine|`; `y3 = rms(beat1 − beat0) / peak|cfd_fine|`.
- [ ] **Step 3:** Body frame: rotate lab `CF_x, CF_y, CF_z` of CFD and prediction with
  `body_frame_coefficients`; `peak_err = | |pred|_peak − |cfd|_peak | / |cfd|_peak` for chord and
  normal; compare with 0.276 and 0.037.
- [ ] **Step 4: Checks:** seed-1234 skill per target equals Task 1's reproduction; `gate_table` has
  one row per (config, component, yardstick) with a boolean `inside`.
- [ ] **Step 5:** `report.py`: the per-component table (error beside each yardstick, verdict per
  cell, never a merged verdict); one figure of held-out waveforms with the coarse–fine band
  shaded. Caveats must list all four limits of the T3c band from the spec, including the
  `dt = 2.5e-4` confound. Export, index line, **commit** if authorised.

### Task 5: E2 — residual map

**Files:** Create `experiments/e2_residuals/{run.py,report.py}`, add `reversal_share` to
`experiments/common/stats.py`, test in `experiments/tests/test_stats.py`.

**Interfaces (produced):**
- `stats.reversal_share(sq_err: np.ndarray, phase: np.ndarray, *, half_width: float = 0.05) -> float`:
  share of summed squared error with phase within `half_width` of 0.25 or 0.75 (stroke reversals
  for φ = φ₀ sin 2πt/T; confirm against `wing_kinematics.py` before use). Uniform expectation is
  `4 * half_width`.

- [ ] **Step 1: Failing test:**

```python
def test_reversal_share_uniform_and_concentrated():
    ph = np.arange(1000) / 1000
    assert abs(reversal_share(np.ones(1000), ph) - 0.2) < 0.01
    e = np.zeros(1000); e[250] = 1.0
    assert reversal_share(e, ph) == 1.0
```

- [ ] **Step 2:** run → fail; implement; run → pass.
- [ ] **Step 3:** `run.py`: leave-one-config-out over 27 configs × the seed count from Task 1;
  validation carved from the remaining 26 by `carve_validation`. Save residuals on the phase grid:
  `outputs/loco_residuals.parquet` (config, seed, phase, target, resid, cfd).
- [ ] **Step 4:** `report.py`: residual-versus-phase per target (median over configs, seed band);
  `reversal_share` per target against 0.2; the same phase profile for `cfd_coarse − cfd_fine` and
  for seed-to-seed spread; normalized error versus φ, f*, α and by position class (corner 8,
  edge 12, face 6, centre 1). Export, index line, **commit** if authorised.

### Task 6: E3 and E4 — data efficiency and ablations

**Files:** Create `experiments/e3_data_efficiency/{run.py,report.py}`,
`experiments/e4_ablations/{run.py,report.py}`, `experiments/common/features.py`,
`experiments/common/ridge.py`, tests in `experiments/tests/test_features.py`.

**Interfaces (produced):**
- `features.make_feature_fn(*, drop: tuple[str, ...] = (), use_re: bool = False, harmonics: int = 1) -> Callable[[pd.DataFrame], tuple[np.ndarray, list[str]]]`:
  default reproduces the repo's `build_features` exactly.
- `ridge.fourier_poly_fit_predict(df, train_configs, test_configs, *, harmonics: int = 4, degree: int = 2, alpha: float = 1e-6) -> np.ndarray`

- [ ] **Step 1: Failing tests:**

```python
def test_default_feature_fn_matches_repo():
    X, names = make_feature_fn()(df); X0, names0 = build_features(df)
    assert names == names0 and np.array_equal(X, X0)

def test_harmonics_add_columns():
    assert make_feature_fn(harmonics=3)(df)[0].shape[1] == build_features(df)[0].shape[1] + 4

def test_ridge_recovers_separable_waveform():
    # synthetic CF = (1 + 0.5*stroke_z) * sin(2*pi*phase): held-out config RMSE < 1e-3
```

- [ ] **Step 2:** run → fail; implement; run → pass.
- [ ] **Step 3: E3 `run.py`.** Pool = 21 non-holdout configs. For n in {3, 6, 9, 12, 15, 18, 21}:
  `nested_subsets` draws (count from Task 1) × `carve_validation(seed=split_seed)` ×
  5 init seeds; evaluate skill on the 6 holdout with the baseline rebuilt from the n configs.
  Structured designs, fixed 2000 epochs and `val_configs=[]`: 8 corners + centre `s45_f100_p45`
  (9 runs); star = centre + the 6 face centres (7 runs). Row thinning at n = 21: keep every
  k-th row for k in {1, 10, 40, 100}. Output `outputs/curve.parquet`
  (n, design, subset_seed, split_seed, init_seed, target, skill, rmse).
- [ ] **Step 4: E4 `run.py`.** Seeds 1234–1238, committed split. Arms: baseline; drop φ / f* / α;
  `use_re`; harmonics 2, 3, 4; width {16, 64, 256} × depth {1, 3, 5}; ridge with harmonics
  {2, 4, 8} × degree {1, 2, 3}. Output `outputs/ablations.parquet` (arm, seed, target, skill, rmse,
  n_params).
- [ ] **Step 5: Checks:** E3's n = 21 random-design median skill and E4's baseline arm both fall
  inside the committed 5-seed range per target (`metrics.json` `seed_sweep`); if not, stop and
  find out why before writing either report.
- [ ] **Step 6:** Reports: E3 skill-versus-n with ranges per target, structured designs as marked
  points, and a variance split (subset / carve / init); E4 one table sorted by skill with ranges
  and parameter counts. Each caveat section names the mixed seed convention. Export, index lines,
  **commit** if authorised.

### Task 7: E5 — POD of the near-wing velocity

**Files:** Create `experiments/field/pod.py`, `experiments/e5_pod/{run.py,report.py}`, tests in
`experiments/tests/test_pod.py`.

**Interfaces (produced):**
- `pod.fit(X: np.ndarray) -> Pod` with `Pod(mean, modes, sing)`; `X` is `(n_snap, n_dof)` float32,
  method of snapshots (eigendecomposition of the `n_snap × n_snap` Gram matrix in float64).
- `pod.energy_fraction(p: Pod) -> np.ndarray` (cumulative)
- `pod.recon_error(p: Pod, X: np.ndarray, r: int) -> float`: relative Frobenius error of the
  mean-removed data projected on the first `r` modes.
- `pod.encode(p, X, r) -> np.ndarray (n_snap, r)`, `pod.decode(p, Z) -> np.ndarray`
- `e5_pod.run.snapshot_matrix(index_df, key: str) -> np.ndarray` (memory-mapped stack)

- [ ] **Step 1: Failing tests:**

```python
def test_pod_recovers_rank3():
    # X = mean + 3 orthogonal spatial modes x random coefficients: energy_fraction[2] > 1 - 1e-6,
    # recon_error(p, X, 3) < 1e-5
def test_recon_error_monotone_in_r():
def test_basis_uses_training_snapshots_only():
    # run.build_basis(index, holdout) raises if any holdout config is in its input
```

- [ ] **Step 2:** run → fail; implement; run → pass.
- [ ] **Step 3:** Wait for Task 2's cache; report its completeness (snapshots cached / expected
  1,116, failures) at the top of the E5 report. Use `wingbeat == 1` snapshots only.
- [ ] **Step 4:** `run.py`, each for `patch_u` and `full4_u`: per-config spectra; pooled spectrum
  over the 21 training configs; held-out `recon_error` for r in {1, 2, 4, 8, 16, 32, 64, 128, 256}
  on the 6 holdout configs; modes for 90% and 99% energy; ridge regression from the first r
  training coefficients to the six CF targets at each snapshot's time, scored on holdout.
- [ ] **Step 5 (only if Task 2 Step 7 passed and it is before Friday 18:00):** wing-frame variant:
  resample each patch into wing-fixed coordinates using the kinematics rotation, repeat Step 4.
- [ ] **Step 6:** `report.py`: spectrum, held-out error versus r, first six mode slices, force-probe
  skill versus r; caveats on the snapshot-count rank cap, the three unaligned phase samplings, and
  the lab-frame moving-body effect. Export, index line, **commit** if authorised.

### Task 8: E6 — `Mesh_Reduced` feasibility

**Files:** Create `experiments/e6_mesh_reduced/{probe.py,run.py,report.py}`.

**Consumes:** `cache.index/load`, `pod.fit/recon_error` (the comparator).

- [ ] **Step 1:** Read `physicsnemo/models/mesh_reduced/` and
  `examples/cfd/vortex_shedding_mesh_reduced/` in the installed package / upstream at the installed
  version; write the constructor arguments, the expected graph inputs and the latent shape into
  `report.py`'s Method section before writing any training code.
- [ ] **Step 2: `probe.py`:** import `Mesh_Reduced` in the WSL venv and run one forward/backward
  pass on a random 1,699-node 2-D graph. Missing graph dependencies are installed into
  `~/venvs/mosquito-explore` only (`uv pip install`, never `uv add`), and listed in the report.
  **Fail → write the report with the failure and stop the task.**
- [ ] **Step 3:** Build the graph once from the patch block-averaged to 48×32×24 = 36,864 nodes if
  it fits, else 48×32×12-equivalent ≈ 16k (6-neighbour grid edges; pivotal nodes on a regular
  sub-lattice). Record node, edge and pivotal counts, VRAM at batch size 1.
- [ ] **Step 4:** Train encode→decode on training-config second-beat snapshots, velocity only,
  per-channel standardized on training data; 3 seeds if one run takes < 2 h, else 1. Early stopping
  on 3 validation configs from `carve_validation(seed=1234)`.
- [ ] **Step 5:** Held-out relative reconstruction error on the 6 holdout configs against POD
  refit on the same downsampled patch, at r = the encoder's total latent size and at r = 8, 32.
  Record seconds per epoch, peak VRAM, encode latency (batch 1 and batch 64).
- [ ] **Step 6 (only if Step 5 finished before Saturday 12:00):** repeat Steps 3–5 at ~100k nodes,
  or the 3-D convolutional autoencoder comparator on the 48×32×24 patch; pick whichever Step 5's
  result makes more informative and say why in the report.
- [ ] **Step 7:** Report in whatever state the task reached by Saturday 23:59. Export, index line,
  **commit** if authorised.

### Task 9: Wrap-up (Sunday morning)

**Files:** Create `experiments/surrogate-recommendation.md`, `experiments/SUMMARY.md`; finalize
`experiments/README.md`.

- [ ] **Step 1:** `uv run pytest experiments/tests -q` passes; every `report.html` regenerates from
  its `outputs/` with no recomputation.
- [ ] **Step 2:** `surrogate-recommendation.md`: the spec's six-point draft, each point revised
  against the result that bears on it (E1/E4 → point 1; E2 → point 2; E5 → point 3; E6 → point 4),
  with unchanged points marked as untested.
- [ ] **Step 3:** `SUMMARY.md`, one page: per experiment the one-sentence result, the figure file,
  and a slide-ready yes/no with the reason; the list of issue drafts; what was dropped and why.
- [ ] **Step 4:** Confirm `git status` shows changes only under `experiments/` and
  `docs/superpowers/`, and `git diff main --stat -- src scripts tests examples pyproject.toml uv.lock`
  is empty. Report to Elizabeth; do not push.
