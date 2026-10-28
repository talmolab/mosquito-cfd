# Replace config-resolved R² on the evidence figure with skill over a phase-only baseline

## Why

Each evidence-figure panel prints **config-resolved R²** (`config_mean_r2`): R² over the six
holdout configurations' cycle means. For `CF_x`, `CF_my` and `CF_mz` on this corpus that is an
ill-conditioned metric. Their six true cycle means barely differ (std 0.006 / 0.004 / 0.013 against
waveform std 1.8 / 0.6 / 3.5), so errors invisible on the scatter (for `CF_x`, ~0.2% of the force
swing) give large negative values that swing with the seed: `CF_mz` spans −8.45 to +0.92 over seeds
1234–1238 (`surrogate/seed_variation.json`; issue #127). Pointwise R² alone is no fix: it is
0.998–0.999 for every target, but a phase-only baseline that ignores the kinematics already scores
0.90–0.97. Skill over that baseline, `1 − MSE(surrogate)/MSE(baseline)`, measured 0.97–0.99 for every
target and stable to ~0.02 across 5 seeds on both datasets (#125 analysis). It must land before
#110, so the fine-corpus surrogate does not commit its own single-seed config-R² figure.

## What Changes

- **Phase-only baseline and skill in `metrics.json`** (design D1–D3). A torch-free helper builds the
  baseline from the train-split configurations; the trainer writes a new top-level
  `phase_baseline_skill` block.
- **Multi-seed sweep in the trainer** (D4). One run trains the primary seed (1234, committed) and
  sweep seeds (CLI default: the four seeds after the primary, so 1235–1238; metrics only); `metrics.json` gains a `seed_sweep` block with
  per-seed metrics and per-target ranges. All four artifacts are written only after every seed has
  finished.
- **Evidence figure reports skill** (D6–D7). Panels show skill with its seed range, pointwise R²
  and RMSE; the caption defines skill, gives the phase-only baseline's own pointwise R², and stops
  printing config-resolved R². The sidecar records every number the caption prints, for all six
  targets (**resolves #116**). **BREAKING** for sidecar readers: `evidence_figure_metrics.json` drops
  `config_mean_r2`.
- **`scripts/make_evidence_figure.py`** records the seeds from `metrics.json` instead of a `--seed`
  flag that could disagree with the caption.
- **`config_resolved` stays** in `metrics.json` and the README, and the comparison figure still reads
  it. It moves off the evidence figure, not out of the record.
- **Docs**: README honest-reading section restructured around skill (D8); `figures/README.md`;
  roadmap (row 12 → ✅, new row for this change); CHANGELOG; the `visualization-tooling` spec's
  reference to the removed `_config_mean_r2` accessor made historical.
- **Artifacts regenerated**: surrogate `metrics.json` + `run_metadata.json`, then the figure, its
  sidecar and `run_metadata.json`. The seed-1234 checkpoint and predictions are expected to be
  byte-identical (D5).

### What does NOT change

- The corpora, the extractor, the model, its features, split rule, hyperparameters and committed
  seed.
- `config_resolved` and its requirement; `comparison_figure.py` and its outputs.
- `surrogate/seed_variation.json` (the frozen, hand-assembled record).
- The fixed panel set, the lab-frame moment wording, the speedup decomposition, and the
  Sane–Dickinson reference line (whose "not used as a quantitative baseline" wording its own
  requirement pins).

## Impact

- **Specs:** `force-surrogate` — 2 ADDED, 5 MODIFIED ("Predicted-vs-CFD evidence figure on held-out
  configurations", "Headline moment axis is CF_my, named as a component", "Honest evidence-figure
  caption and speedup annotation", "Committed evidence-figure artifacts with provenance",
  "Cluster-free evidence-figure tests"). `visualization-tooling` — 1 MODIFIED ("Force-surrogate
  comparison figures reproduce their source data exactly, not an approximation"; wording only).
- **Code:** `src/mosquito_cfd/force_surrogate/train.py`, `evidence_figure.py`, `__init__.py`,
  `comparison_figure.py` (docstring only); `scripts/train_surrogate.py`,
  `scripts/make_evidence_figure.py`.
- **Tests:** new `tests/test_force_surrogate_phase_baseline.py` and
  `test_force_surrogate_seed_sweep.py`; `tests/test_force_surrogate_train.py`, `test_force_surrogate_train_gpu.py`,
  `test_force_surrogate_train_driver.py`, `test_force_surrogate_evidence_figure.py`,
  `test_committed_surrogate_provenance.py` (blast radius in tasks.md §0).
- **Docs:** `examples/prelim_sweep/README.md`, `examples/prelim_sweep/figures/README.md`,
  `docs/force_surrogate/roadmap.md`, `docs/CHANGELOG.md`.
- **Committed artifacts:** `surrogate/metrics.json` (8.8 → 20.4 KB),
  `surrogate/run_metadata.json`, `figures/evidence_figure.png` (one new 312 KB blob),
  `figures/evidence_figure_metrics.json`, `figures/run_metadata.json`. D5 held, so there is no new
  checkpoint or predictions blob.
- **Issues:** closes #127, #125, #116. Unblocks #110, which reuses the baseline and sweep unchanged.

### Deliberately out of scope

- #115 (stale numbers in the live spec text; the caption requirement keeps its #115 note), #124,
  #102.
- A stronger baseline (per-config amplitude scaling or a calibrated quasi-steady model; the
  Sane–Dickinson code gives `CF_z` only, uncalibrated).
- An ensemble surrogate (a different model and claim). The fine corpus (#110).

### Why N instead of M?

Deviations found while implementing, each reconciled into design D4 and the spec:

- **The CLI's default sweep is the four seeds after `--seed`, not a fixed 1235–1238.** A fixed
  default made re-training any recorded sweep seed as the primary (`--seed 1236`) fail as a
  duplicate seed. For the committed `--seed 1234` the sweep is unchanged.
- **Negative seeds are rejected** with duplicates, before the dataset is read.
- **The phase-only baseline is built before the primary seed trains,** not after. It reads only the
  dataset, so a malformed dataset now fails in seconds rather than after a full training run; the
  primary seed's outputs are unaffected (the D5 gate confirmed them byte-identical).
- **The four artifacts are not written via a temporary directory and rename.** The spec promises
  only that a failing seed writes nothing, which holds because every write follows the last seed. A
  failure part-way through the writes themselves (disk full) can still leave some files; the
  documented recipe (README, tasks 26) trains into a scratch directory and copies in, so a partial
  write never reaches the repository.

### Delivery

One PR against `main`, committed in the order of tasks.md (proposal → code commits → guards →
retrain → artifacts → figure + README → docs). Nothing is pushed until the figure is final.
