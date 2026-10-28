# Train the force surrogate on the fine corpus and build its evidence figure

## Why

Every force-surrogate number quoted today comes from the coarse 64×32×64 corpus. That grid
under-resolves `CF_chord` by +115% against the van Veen quasi-steady model target. The fine corpus
(`examples/prelim_sweep_fine/`) is complete and verified (#97, #100), and its moments have been
hinge-referenced since #118, but it has no trained surrogate and no evidence figure (#110). #110 was
blocked on #127, which merged as PR #128.

#110's own "Suggested scope" is stale and is superseded here:
- the figure reports skill over the phase-only baseline with its seed range (#127), not
  `config_resolved`;
- #108 is merged;
- the corpus has 27 configs, not 26;
- its quoted coarse numbers predate #108/#127 and are not reused.

## What Changes

- **Train the fine surrogate** with the existing trainer, with no functional change, using the
  coarse run's hyperparameters and seeds (2000 epochs, seed 1234, sweep 1235–1238, 3 validation
  configs). Artifacts go to `examples/prelim_sweep_fine/surrogate/` (design D1). A pre-registered
  gate requires two full runs to be byte-identical before anything is committed (D4).
- **Make the evidence figure grid-aware** (D2). The five hard-coded coarse references in
  `evidence_figure.py` move into a `GridProfile` (`coarse`, `fine`).
  - The default, `coarse`, reproduces the committed coarse figure byte for byte. This is checked
    once by hand (PNG) and permanently in CI (sidecar).
  - The fine caveat says the figure shows agreement with CFD, not with experiment, and that grid
    convergence was checked only at one wing motion outside this sweep (exact text in D2).
- **Fine CFD cost** (D3). New torch-free `median_cfd_seconds_per_wingbeat()` takes the median per-wingbeat
  wall time over the 27 committed fine `run_metadata_<config>.json` files, and
  `scripts/cfd_seconds_per_wingbeat.py` prints it.
  - `scripts/make_evidence_figure.py` gains `--grid` and `--cfd-seconds-per-wingbeat` (required for
    `fine`; must be 144 for `coarse`).
  - CI recomputes the committed value.
  - The README discloses that the coarse and fine denominators are not like-for-like.
- **Fine evidence figure** in `examples/prelim_sweep_fine/figures/`.
- **Fine README** (D5) replaces "Not yet built" with:
  - the skill table;
  - a cycle-mean R² 5-seed table;
  - a coarse-vs-fine 5-seed skill-range table under a pre-registered overlap rule;
  - the quasi-steady reference and the CF_mx/CF_mz exclusion;
  - the validation status of the fine CFD, with sources;
  - the speedup disclosure;
  - the regeneration commands.

  Every table is guarded.
- **Committed-artifact guards parametrized over both corpora** (D6). They are built on pure helper
  functions, so they are tested before the fine artifacts exist. These checks stay coarse-only
  deliberately:
  - `seed_variation.json` and the five canonical config-R² quotes, which exist only for coarse;
  - `latency_speedup < 1000`, which is a coarse fact (on the fine grid the floor is expected above
    1,000×);
  - the `"2.4" not in readme` substring check, which the fine README replaces with a pattern check.
- **Docs**:
  - roadmap row 14 (🟡 while open, ✅ after merge), plus pointers in its Hardware and
    Grid-resolution sections;
  - CHANGELOG;
  - the stale "fine surrogate does not exist yet" text in `openspec/project.md` and
    `tests/fixtures/comparison_figure/README.md`.

### What does NOT change

- The trainer's behaviour, model, features, split rule, hyperparameters, seeds and metrics schema;
  `phase_baseline.py`.
- Both corpora and the extractor. No coarse artifact is recommitted (`examples/prelim_sweep/**`),
  and the coarse README is unchanged.
- The figure's panel set, its annotation formatting, its sidecar key set, and its scope guard (still
  two file inputs).
- `comparison_figure.py` / `make_comparison_figure.py`.
- The `cpu_only` bitwise-reproducibility claim. The D4 gate is an observed outcome, not a new claim.

## Impact

- **Specs:** `force-surrogate`.
  - 3 ADDED:
    - "Fine-corpus surrogate and evidence figure are committed with a reproducibility gate"
    - "Fine-grid CFD cost is derived from committed run metadata"
    - "Fine README compares coarse and fine skill under a pre-registered overlap rule"
  - 7 MODIFIED:
    - "Committed training artifacts"
    - "Force-only training scope guard"
    - "Predicted-vs-CFD evidence figure on held-out configurations"
    - "Sane–Dickinson quasi-steady reference (computed, not overlaid)"
    - "Honest evidence-figure caption and speedup annotation"
    - "Committed evidence-figure artifacts with provenance"
    - "Committed surrogate artifacts are tied to the dataset they were trained on"
- **Code:**
  - `src/mosquito_cfd/force_surrogate/evidence_figure.py`;
  - new `src/mosquito_cfd/force_surrogate/cfd_cost.py`;
  - `scripts/make_evidence_figure.py`;
  - new `scripts/cfd_seconds_per_wingbeat.py`;
  - docstrings only in `train.py` and `scripts/train_surrogate.py`.
- **Tests:**
  - `tests/test_force_surrogate_evidence_figure.py`;
  - `tests/test_committed_surrogate_provenance.py`;
  - new `tests/test_force_surrogate_cfd_cost.py` (blast radius in tasks.md §0).
- **Docs:**
  - `examples/prelim_sweep_fine/README.md`;
  - `docs/force_surrogate/roadmap.md`;
  - `docs/CHANGELOG.md`;
  - `openspec/project.md` (Pending item);
  - `tests/fixtures/comparison_figure/README.md`.
- **Committed artifacts (new):**
  - `examples/prelim_sweep_fine/surrogate/{surrogate.pt, holdout_predictions.parquet, metrics.json, run_metadata.json}`
  - `examples/prelim_sweep_fine/figures/{evidence_figure.png, evidence_figure_metrics.json, run_metadata.json}`

  These should total about 2.0 MB of new blobs, going by the coarse equivalents (~41 KB, ~1.6 MB,
  ~20 KB, ~1 KB, ~310 KB, ~2.5 KB, ~1 KB). Measured sizes are reported at the binary checkpoint and in
  the PR. Exactly one blob per path is pushed.
- **Issues:** closes #110. Files one follow-up issue (tasks 21).

### Deliberately out of scope

- #115 (stale numbers in live spec text), #124, #102 (no LFS), #101, #129, #79 (species wording).
- A coarse-vs-fine **figure**. `make_comparison_figure.py` becomes runnable once the fine predictions
  exist, but it plots config-resolved R², which #127 moved off figures. It goes to the follow-up
  issue.
- Re-tuning or a convergence study for the fine training. Wing-frame moment conversion (deferred,
  not currently tracked).

### Post-push figure-fix policy (decided at approval, 2026-10-28)

- Pushed blobs are permanent. After the push, **only a BLOCKING** review finding that touches figure
  code justifies regenerating the figure and pushing a second PNG blob, reported in the PR. Any
  non-blocking figure-code finding goes to a follow-up issue, and the committed figure stays
  consistent with its committed code.

### Delivery

One PR against `main` from branch `add-fine-corpus-surrogate`, committed in the order of tasks.md.
Nothing is pushed until the figure and README are final.
