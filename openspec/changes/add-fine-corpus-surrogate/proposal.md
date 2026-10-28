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
- **Fine CFD cost** (D3). New torch-free `median_cfd_seconds_per_step()` takes the median per-step
  wall time over the 27 committed fine `run_metadata_<config>.json` files, and
  `scripts/cfd_seconds_per_step.py` prints it.
  - `scripts/make_evidence_figure.py` gains `--grid` and `--cfd-seconds-per-step` (required for
    `fine`; refused for `coarse`, whose cost stays fixed at 144 s per wingbeat).
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

- The trainer's behaviour, model, features, split rule, hyperparameters, seeds and metrics schema,
  including the phase-only baseline (`train.build_phase_only_baseline`).
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
  - new `scripts/cfd_seconds_per_step.py`;
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

### Why N instead of M?

Deviations found before the GPU run, each reconciled into design and spec:

- **The fine CFD cost is a median per step, not per wingbeat.** Per-wingbeat time scales with
  1/f*, so the approved median over per-wingbeat times pooled three f* levels and matched the
  representative f*=1.0 config only by chance. The pre-GPU code review found it; the user chose
  per step. The CLI flag is `--cfd-seconds-per-step`, the script `cfd_seconds_per_step.py`, and the
  sidecar's `cfd_seconds_per_wingbeat` is derived (per-step cost × representative rows), so its
  key set and the coarse figure are unchanged (coarse PNG and sidecar re-checked byte-identical).
- **`build_caption` checks the cost against the label.** The review showed the public caption
  builder could print the fine label over the coarse cost.
- **`format_power_of_ten` lives in `tests/_readme_guards.py`**, not the shipped module: only the
  README tests use it.
- **The fine README's disclosure checks are a separate test** in
  `test_committed_surrogate_provenance.py` built on the shared guard helpers, not a parametrization
  of `test_readme_carries_full_disclosures`, whose coarse strings stay as they are.
- **The guards check direction and comparatives README-wide**, the denominator with number
  boundaries, sections skip fenced code, and every content failure is an `AssertionError`: all from
  the pre-GPU review, each fix confirmed by reverting it as a mutation.
- **No `phase_baseline.py`.** The proposal named a module that does not exist; the baseline is in
  `train.py`.
- **Training ran at `5f5db6e`, not C3.** The pre-GPU review produced two more commits (`58ee8fb`
  fixes, `5f5db6e` per-step cost) before the GPU run; the D4 gate and the freeze apply to that
  commit. The figure was generated at C4 (`e0040d6`). Both provenance scopes (design D8) were
  unchanged at C6.

### Outcomes

- **Coarse no-op gate:** `main`'s code and the branch's produced byte-identical coarse PNG and
  sidecar, both equal to the committed ones (each in its own `.venv`, identical frozen packages,
  matplotlib 3.10.8); re-checked after the per-step change. The sidecar half runs in CI.
- **D4 gate (fine training, A5000, `5f5db6e`):** two full 5-seed runs; `surrogate.pt` and
  `holdout_predictions.parquet` byte-identical, `metrics.json` equal outside the inference
  wall-clock fields, `run_metadata.json` equal outside `run_id`, both clean. Torch tier 48 passed,
  0 skipped, the two #129 failures only.
- **Measured blobs (raw):** `surrogate.pt` 41,321 B; `holdout_predictions.parquet` 1,570,974 B;
  `metrics.json` 20,459 B; surrogate `run_metadata.json` 1,094 B; `evidence_figure.png`
  310,190 B; `evidence_figure_metrics.json` 2,485 B; figure `run_metadata.json` 1,120 B
  (≈1.95 MB total).
- **Mutation kills:** C1 13/13, C2 20/20, C3 10/10, review fixes 10/10, per-step 21/21, fine
  artifacts 20/20, fresh-review guards 6/6.
- **Follow-up issue:** #130.
- **Fresh review of C4–C6 (task 23):** no blocking findings. Fixed (C7, docs and tests only, so
  neither provenance scope changed): the MODIFIED Sane–Dickinson text no longer asserts a coarse
  ratio < 1 (≈ 0.7) that the committed coarse value (≈ 1.3) contradicts; the fine README no longer
  implies the omitted lift terms explain an over-prediction; the per-step cost's 2.10–3.30 s range
  and its node/kinematics confound are stated instead of "the per-step time does not depend on the
  kinematics"; the denominator and quasi-steady guards are scoped to their sections (the first
  could not fail); "21 training configurations" now says 21 non-holdout. Left as is: the
  `cfd_cost.py` module docstring's "the per-step rate does not" wording (it cites the pilot's
  2.00–2.02 s/step; editing it would change the figure's provenance scope), filed in #131.
- **Pre-PR `/review-pr` (5 reviewers, branch mode):** no blocking findings. Fixed (tests, test
  config and README only; neither provenance scope changed): README guards hardened against the
  bypasses found (other comparative phrasings and line-wrapped forms, comparatives about the fine
  grid outside the section, duplicated tables/headings, numbers matched as substrings, extra
  per-step or QS values, more ratio wordings, the own-baseline sentence, resolution attribution,
  the QS omitted terms, "amplitude and shape", "sequential", the batch size), each by a synthetic
  defect and confirmed by reverting it (13/13); a committed-binaries existence/format test;
  `pythonpath = ["tests"]` so the helper import works under any `--import-mode`; the README now
  says the surrogate was timed on the RTX A5000, that both grids share the holdout and validation
  configs, where the overlap rule was registered, and where the figure ran. The `src` hardening
  the reviewers found (input validation in `resolve_grid`/`compute_speedup`/`cfd_cost`, exports,
  POSIX paths in provenance, CLI usage errors) is deferred to #131: no committed artifact depends
  on it, and fixing it would change the committed figure's provenance scope. The coarse CI check
  compares the regenerated sidecar as parsed JSON (exact except the two QS RMS values at rel
  1e-12); the PNG's byte identity was checked by hand.

### Delivery

One PR against `main` from branch `add-fine-corpus-surrogate`, committed in the order of tasks.md.
Nothing is pushed until the figure and README are final.
