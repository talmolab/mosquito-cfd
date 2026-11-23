# Build the real coarse-vs-fine force-surrogate figures (#114) and clear the fine-surrogate follow-ups (#130)

## Why

Both force surrogates are committed, but no figure compares them. The two builders meant to,
in `comparison_figure.py`, have never run on real data and describe a "collapse on the fine grid"
finding that the corrected corpora do not show. This change replaces them with three real-data
figures that each rebuild by one command and fail CI when their inputs or renderer change. It also
clears the #130 doc and provenance follow-ups.

### Background

- **The scatter builder.** On the committed artifacts it draws two seed-1234 `CF_x` scatters that
  both lie on the 1:1 line. Its six configuration-mean diamonds stack at the origin: the true
  cycle means are 0.007–0.029 against axes reaching ±3.5. The panels have different limits, and
  there is no skill, seed range or caption.
- **The diagnostic builder.** It reports one seed's cycle-mean R² (`CF_x`: −6.70 coarse, −2.86 fine),
  the quantity #127 removed from the evidence figure as ill-conditioned.
- **Where the "collapse" claim came from.** It came from the 2026-08-11 deck figure the builders
  were promoted from, which was built on data from before the wing-vertex and hinge fixes
  (#62, #71). On the corrected
  corpora the five-seed cycle-mean R² ranges overlap for every target (`CF_x`: coarse −6.70 to 0.65,
  fine −2.86 to 0.77), so the metric is dominated by the seed on both grids.
- **The deadline.** The figures are wanted for the 2026-11-24 lab meeting. A corpus regeneration
  with longer runs is planned after it, so every figure must be cheap to rebuild and must fail
  loudly when its inputs change.

## What Changes

- **Three figures replace the two old builders.** One driver,
  `scripts/make_coarse_vs_fine_figures.py --figure <name>`, renders one figure per call into
  `examples/prelim_sweep_fine/figures/coarse_vs_fine/`:
  - `skill_ranges`: the only coarse-vs-fine comparison. It shows the five-seed skill ranges under
    the pre-registered overlap rule.
  - `error_histograms`: within each grid, the surrogate's error beside the phase-only baseline's,
    in baseline-RMSE units, for the committed seed, annotated with its five-seed skill range.
  - `cycle_mean_r2_diagnostic`: why cycle-mean R² is ill-conditioned, shown for all five seeds.
- **Guards.** Each figure is guarded against its inputs, the renderer source, and the README rule
  (design D2–D7).
- **Training metadata, forward only.** `train.build_training_metadata` records python, numpy,
  pandas and pyarrow versions for future training runs (#130 item 4). The committed surrogate
  records are not edited.
- **Docs.** `openspec/project.md` loses its stale fine-corpus text. The coarse README's
  quasi-steady bullet states both grids' ratios, under a guard. The fine README gains a
  "Comparison figures" section. `docs/CHANGELOG.md` gets an entry (#130 items 2 and 3).
- **BREAKING (internal only).** Removed:
  - `build_coarse_vs_fine_comparison` and `build_config_mean_collapse_diagnostic`;
  - `scripts/make_comparison_figure.py` and `scripts/make_config_mean_collapse_diagnostic.py`;
  - their tests;
  - `tests/fixtures/comparison_figure/`.

  Nothing else imports them.

## Impact

- **Affected specs:**
  - `visualization-tooling`: 3 MODIFIED, 7 ADDED;
  - `force-surrogate`: 1 MODIFIED, 1 ADDED.
- **Affected code:**
  - `src/mosquito_cfd/force_surrogate/comparison_figure.py` (rewritten);
  - `src/mosquito_cfd/force_surrogate/train.py` (`build_training_metadata` only);
  - new `scripts/make_coarse_vs_fine_figures.py`.
- **Tests:**
  - `tests/test_comparison_figure.py` and `tests/test_make_comparison_figure_cli.py` rewritten;
  - new `tests/_comparison_corpus.py`, `tests/test_comparison_corpus.py`,
    `tests/test_comparison_figure_guards.py`, `tests/_comparison_guards.py`,
    `tests/test_comparison_guards.py`, `tests/test_committed_comparison_figures.py` and
    `tests/test_readme_comparison_docs.py`;
  - `tests/test_force_surrogate_train.py`, `tests/_readme_guards.py` and
    `tests/test_committed_surrogate_provenance.py` extended.
- **Docs:**
  - `openspec/project.md`, `docs/CHANGELOG.md`;
  - `examples/prelim_sweep/README.md`, `examples/prelim_sweep_fine/README.md`;
  - after merge, `docs/force_surrogate/roadmap.md`.
- **Artifacts:**
  - added: 9 files in `examples/prelim_sweep_fine/figures/coarse_vs_fine/`;
  - removed: `tests/fixtures/comparison_figure/`.
- **Untouched:**
  - both `surrogate/` directories and both `dataset.parquet` files;
  - both evidence figures;
  - `evidence_figure.py` and `cfd_cost.py`.
- **Compute:** CPU only, seconds per figure.
- **Issues:**
  - closes #114 and #130;
  - advances #131, item 8, for the new sidecars only.
- **Coordination:**
  - The parallel F3a change (`add-surrogate-comparison-bench`, not yet committed) edits other
    hunks of the same three docs and other functions of `train.py` (design D10).
  - The future corpus regeneration must re-render these figures (design D7).
