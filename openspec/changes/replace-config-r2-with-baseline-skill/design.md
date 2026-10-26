# Design

## Context

- `train.py` writes `metrics.json` with `per_target`, `aggregate`, `per_config`,
  `config_resolved`, `inference`, `reproducibility`. Tests pin the key sets **inside**
  `per_target`, `per_config` and `config_resolved` exactly; the top-level key set is not pinned.
  New data therefore goes into **new top-level blocks**.
- A seed controls both the initial weights and the 3-of-21 validation carve
  (`make_config_splits`, `np.random.default_rng(seed)`). `set_seeds` runs inside both `build_model`
  and `train_model`; training is full-batch Adam with no dropout or shuffling.
- At a fixed seed, training on the A5000 reproduced the committed checkpoint and predictions bitwise
  (#126, archived design D9). Each run takes ~20 s.
- `seed_variation.json` was assembled by hand from **separate-process** runs; it holds
  `config_mean_r2` only.
- `evidence_figure.py` reads only `holdout_predictions.parquet` and `metrics.json` (scope guard) and
  must keep reading, never re-deriving (CC-4).
- Holdout configs have 1738, 2000 or 2353 rows per beat (`1/(f*·dt)`).
- **"Baseline" already names the Sane–Dickinson reference** in the caption ("not used as a
  quantitative baseline", pinned by its requirement) and in the sidecar
  (`quasi_steady_reference.baseline_rmse_cf_z`). Every new name and every new sentence therefore says
  **phase-only baseline** / `phase_baseline_*`, never bare "baseline".
- **"Skill" is used loosely for config-R²** in the README today ("config-to-config skill"). After
  this change "skill" means only `1 − MSE/MSE₀`; config-R² is called "config-resolved (cycle-mean) R²".

A CPU check on the committed seed-1234 predictions (scratch, no training) gives, with the D2
baseline, skill 0.973–0.988 and phase-only-baseline R² 0.897–0.973, within 0.001 of #125's 200-bin
version on every target; every reference beat has strictly increasing phases in `[0, 1)`.

## Decisions

### D1. Skill is `1 − SSE(surrogate)/SSE(phase-only baseline)`, pooled over holdout rows, per target

Computed on the inverse-transformed holdout predictions, on the same rows as `per_target`, so it is
the MSE ratio. Pooling over rows weights the f*=0.85 configs ~35% more than f*=1.15 ones; that is
deliberate, to match the pointwise `rmse`/`r2` printed beside it and the #125 measurement (D2 makes
the opposite choice for the baseline's *construction*, where the question is "the typical
configuration's waveform"). Skill is **not clipped**: negative means worse than the phase-only
baseline. If `SSE(baseline) ≤ _VARIANCE_EPS · Σ t²`, skill is the NaN sentinel, serialized `null`.
Zero rows or mismatched shapes raise `ValueError` (parity with `compute_metrics`).

### D2. Phase-only baseline: equal-weight mean of per-config periodic interpolants, all train-split configs

```
for each reference config c (split == "train", wingbeat >= CONVERGED_MIN_WINGBEAT):
    for each converged beat b of c:
        curve_cb(φ) = np.interp(φ, phase_cb, target_cb, period=1.0)   # rows sorted by phase
    curve_c(φ) = mean_b curve_cb(φ)
baseline(φ) = mean_c curve_c(φ)                                       # equal weight per config
```

- **Interpolation, not bins**: no bin-count parameter. **Periodic**, so a query past the last sample
  wraps to phase 0.
- **Equal weight per configuration, per beat within a configuration**: each configuration counts
  once whatever its row count or number of converged beats (the fine corpus, #110, may have more
  than one).
- **All `split == "train"` configs (21 here), not the seed's 18**: the baseline depends only on the
  dataset, so the seed range reflects the surrogate alone. It sees the 3 configs the surrogate used
  only for model selection, which makes skill conservative. Holdout rows are never used.
- **Validation** (`ValueError`, naming the problem): no reference config; a beat with < 2 rows; a
  duplicate phase within a beat; a reference **or query** phase outside `[0, 1)` or non-finite; a
  non-finite reference value. Input row order does not matter.

### D3. The trainer computes it; the figure reads it (CC-4)

`build_phase_only_baseline(df, query_phase, target_names) -> (predictions, definition)` and
`compute_baseline_skill(y_true, y_pred, y_baseline, target_names)` are torch-free.
`run_training` computes the baseline once and passes it to `build_metrics(..., phase_baseline=...)`
(keyword-only, default `None` → block omitted, so existing callers are unchanged):

```json
"phase_baseline_skill": {
  "phase_baseline": {
    "kind": "phase_only_periodic_interpolation", "reference_split": "train",
    "reference_configs": ["...21 names..."], "weighting": "equal_per_config_then_beat",
    "converged_min_wingbeat": 1
  },
  "per_target": {"CF_x": {"skill": 0.988, "phase_baseline_rmse": 0.40, "phase_baseline_r2": 0.955}}
}
```

### D4. Multi-seed: provenance first, primary seed first, sweep metrics-only, write everything last

`run_training(..., seed=1234, sweep_seeds=())`; the **library default is no sweep**, so existing
callers and tests (and #110 at its own cost) don't train extra models silently. The driver's
`--sweep-seeds N [N ...]` defaults to 1235–1238 (the committed recipe); `--sweep-seeds` with no values
means none.

1. Validate seeds **before reading the dataset or creating `out_dir`**: a sweep seed equal to the
   primary or repeated raises `ValueError`.
2. Validate the digest and hash the dataset bytes up front, as today.
3. Train the primary seed exactly as today; measure inference right after it, as today. **Keep the
   primary model object itself** (on its device) with its predictions and metrics. The checkpoint is
   later saved from that model exactly as today: the committed `surrogate.pt` holds `cuda` storage
   tags, so saving a CPU copy would change its bytes and fail D5(a) for a reason unrelated to the
   science.
4. For each sweep seed, in order, in the same process: carve, fit, predict the holdout, compute
   `per_target`, `config_resolved` and skill against the same baseline. Discard the model.
5. Only after every seed has finished: capture provenance (`build_training_metadata`, which
   re-checks the dataset sha256, as today, after training and before any write), then write all four
   artifacts. A failure in any seed writes nothing.

Code seam (so the order/atomicity test runs torch-free in CI): the per-seed work is a module-level
`_fit_one_seed(...)` that does its own lazy `import torch`; `run_training` calls it once per seed,
then `_measure_inference` for the primary, then the writer (which imports torch for `torch.save`).
The test monkeypatches `_fit_one_seed` and `_measure_inference`; its success-path recorder raises on
the last seed, so no `torch.save` is reached.

```json
"seed_sweep": {
  "primary_seed": 1234, "seeds": [1234, 1235, 1236, 1237, 1238],
  "runs": [{"seed": 1234, "val_configs": ["..."],
            "per_target": {"CF_x": {"skill": 0.988, "r2": 0.999, "rmse": 0.041, "config_mean_r2": -4.17}}}],
  "range": {"CF_x": {"skill": {"min": 0.988, "max": 0.992}, "r2": {}, "rmse": {}, "config_mean_r2": {}}}
}
```

- Range = NaN-aware min/max over all seeds including the primary; all-null → `null`. With n=5,
  min/max is honest; median/IQR would imply a distribution n=5 cannot support.
- Training `run_metadata.json`: `seeds = {"global": 1234, "sweep": [1235, ...]}`
  (`build_training_metadata`'s annotation widens to allow the list). `reproducibility.seeds.global`
  keeps naming the committed model.
- wandb (opt-in) logs the primary run as today; its metrics payload now includes `seed_sweep`.
- **In-process vs subprocess per sweep seed.** In-process is kept: `set_seeds` reseeds every RNG,
  model init is on CPU, and no CUDA RNG is consumed. Residual risk is cuBLAS/allocator state carried
  between seeds on CUDA; a torch-tier test parametrized over `cpu`/`cuda` pins "seed *b* standalone ==
  seed *b* in a sweep" (task 15). If that test fails on `cuda` at C3, the change stops at the same
  decision point as D5(b) (subprocess per sweep seed, or not) **before** C3 is committed.
- Training `run_metadata.json` always carries `seeds.sweep` (an empty list when there is no sweep).
- Caption with one seed: the floor reads "skill ≥ m (single seed, no range)". Off-panel CF_mx/CF_mz
  are given as the plotted seed's value with its range, like the panels.

### D5. Byte-identity and the hand record: a one-time, pre-registered gate, not a permanent CI pin

The retrain is run into a scratch `--out-dir` **outside the repository** first, then checked:

- **(a)** `surrogate.pt` and `holdout_predictions.parquet` byte-identical to the committed ones.
  Mismatch → **halt**: a refactor regression in the primary path.
- **(b)** each seed's `config_mean_r2` equals `seed_variation.json`'s hinge-referenced value exactly.
  If only a sweep seed mismatches, rerun that seed standalone (`--seed s --sweep-seeds`) into scratch.
  Standalone matches the record → in-process state leaks; switch to one subprocess per sweep seed
  (decision point with the user). Standalone also mismatches → general GPU nondeterminism; decide
  with the user. Nothing is loosened to pass.

The outcome is recorded in tasks.md, the CHANGELOG and the PR body. CI does **not** permanently pin
the four sweep seeds to the hand record: that would freeze the committed artifacts to one torch
version, driver and GPU and contradict the spec's "seeded-but-not-bitwise" GPU claim. CI instead
checks the committed artifacts' **internal** consistency (primary run == top-level blocks; seeds;
`val_configs` recomputed from the dataset; run_metadata seeds; skill recomputed from the committed
predictions and dataset). The existing check that the record's seed-1234 `config_mean_r2` equals
`metrics.json` stays (it already pins the committed model to the record), minus its commit-equality
clause, which a retrain at a new commit must break.

### D6. Figure text: numbers on the panels, the definition in the caption

Panel annotation:

```
skill 0.988  (5 seeds: 0.988 to 0.992)
R² 0.999 · RMSE 0.041
```

- Skill and R² print to 3 dp. **Either** value that would print `1.000` prints `>0.999`. Negatives
  use U+2212; ranges are always "lo to hi" (never a dash, so a negative end is unambiguous); a nonzero
  value that would print `±0.000` prints in scientific form (e.g. `−4.0e-04`), so a below-baseline
  flag never shows `0.000`. Null prints `n/a`.
- Caption headline (no repeated panel numbers): "Predicted vs CFD on held-out configurations, seed
  `n`. Skill = 1 − MSE/MSE₀, where MSE₀ is the error of a phase-only baseline (the mean training
  waveform; ignores stroke, frequency and pitch); range over `k` seeds." + the speedup sentence as
  today. With `k == 1`: "single seed, no range" (the one literal used everywhere).
- Caveats line: "pointwise R² mostly reflects the shared waveform (the phase-only baseline alone
  scores R² a/b/c); skill also rewards predicting how waveform amplitude and shape change with the
  kinematics, not only the cycle-mean force (cycle-mean R²: README); skill ≥ `m` for all six targets
  across `k` seeds; off-panel CF_mx `s₁`, CF_mz `s₂`" + coarse-grid / not-validated + lab-frame
  `M_y` (wing-frame conversion not currently tracked).
- **The floor, not a "weakest target".** All six 5-seed ranges overlap, so naming one target as
  weakest would imply a ranking n=5 cannot support. The caption states the floor `m` = min over
  targets of the seed-sweep minimum skill (nulls skipped; all null → "skill undefined for every
  target"). If `m < 0`, it instead names each target whose minimum is below 0 and says it is
  **below the phase-only baseline**, as a subordinate flag. `m == 0` is not "below".
- Skill reads as dominant, a below-baseline skill as an honesty flag, not a co-headline.
- The Sane–Dickinson line is unchanged. The phase-only baseline is never plotted.

### D7. Sidecar `evidence_figure_metrics.json`

Remove `config_mean_r2` (BREAKING for readers; CHANGELOG). Add `primary_seed`, `n_seeds`, and for
**all six** targets: `skill.<c> = {committed, min, max}`, `pointwise_r2.<c>`,
`phase_baseline_pointwise_r2.<c>`; plus `skill_floor = {value, targets_below_phase_baseline}`. Every
number the caption prints is now recorded (#116). `surrogate_rmse` stays panel-only.
`generate_evidence_figure` loses its `seeds` parameter and `make_evidence_figure.py` its `--seed`
flag: the figure's `run_metadata.json` seeds are read from `metrics.json` `seed_sweep`, so they cannot
disagree with the caption.

### D8. README

- Structure of the honest-reading section: (1) "What the figure reports: skill over the phase-only
  baseline" — definition once, the skill table, n=5 caveat, waveform-credit caveat; (2) "Why
  config-resolved (cycle-mean) R² left the figure" — the near-zero-spread argument, the existing
  5-seed config-R² table and "Reading the two columns" kept verbatim, the per-config average-force
  claim limited to targets whose config-R² is seed-robust in the record; (3) headline moment
  bullet, unchanged except wording.
- Skill table, a label plus three value columns, header outside both existing regexes:
  `| target | skill, seed 1234 | skill, 5 seeds | phase-only baseline R² |`, rows
  `` | `CF_x` | 0.988 | 0.988 to 0.992 | 0.955 | ``. Guarded against `metrics.json` (3 dp, U+2212
  normalized).
- **No number other than a config-resolved R² follows a `CF_` name with ≈/= in prose** (the
  `_R2_NEAR_TARGET` guard reads such prose as config-R²). Skill, pointwise R² and phase-only-baseline
  R² appear only in the table.
- Section (2) **keeps the five canonical config-R² quotes** `CF_x ≈…`, `CF_z ≈…`, `CF_my ≈…`,
  `CF_mx ≈…`, `CF_mz ≈…` of the plotted seed: `test_readme_config_resolved_r2_matches_committed_metrics`
  (`_QUOTED_TARGETS`) requires them, and they stay true as "the plotted seed's config-resolved R²".
- Sentences that become false and must change: "the figure reports the per-axis config-resolved R²
  of the committed seed-1234 model (CF_x ≈−4.17, CF_z ≈0.98, CF_my ≈0.07)" (:329–332, reworded to
  "the plotted seed's config-resolved R² is …", quotes kept); the callout "The PR6 figure caption
  uses the honest config-resolved number" (:247–254); "The caption names whichever target is most negative…" and its
  CF_y-tell parenthetical (:362–368, reduced to one historical clause); the sidecar row's "annotated
  `config_mean_r2`" (:313); "a terse Baseline line" (:321 → "quasi-steady-reference line"); the
  normative-schema list (:242–245) and the `metrics.json` row (:237) gain the two new blocks; the
  training command gains `--sweep-seeds`; the latency sentence restates its observed range including
  the new sample. `figures/README.md` :11–13 and :18.
- Roadmap: the new row and the CHANGELOG entry state no skill numbers (the README table is the one
  guarded copy); row 5's pointer names `phase_baseline_skill` / `seed_sweep` too.

### D9. Spec delta strategy

- ADDED: "Phase-only baseline skill in metrics.json"; "Multi-seed sweep reported by the trainer".
- MODIFIED (full text): the four evidence-figure requirements named in the proposal, plus
  "Cluster-free evidence-figure tests" (no phase-only baseline curve on any axis), plus
  `visualization-tooling`'s comparison-figure requirement (its parenthetical names the removed
  accessor; made historical).
- Not modified: "Config-resolved…", "Held-out evaluation metrics" (key list is a lower bound),
  "Training reproducibility and provenance" (D5 keeps CI free of GPU-bitwise pins), "Sane–Dickinson
  quasi-steady reference", "Force-only evidence-figure scope guard" (still two inputs).

## Risks

- **D5 fails.** Pre-registered diagnosis above; no binary is committed before it passes.
- **Re-measured timing trips a literal guard.** The README throughput guard expects
  `1e6 ≤ throughput < 1e7` and "2.4" must not appear in the README; a new sample of ≈2.4×10⁶× would
  print "≈2.4×10⁶×". If either fires, stop and decide with the user (not re-pinned silently).
- **A second PNG blob.** Only one PNG may reach a pushed commit (task 31a).
