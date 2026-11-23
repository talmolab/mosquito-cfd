# Design: real coarse-vs-fine force-surrogate figures

The normative statements (guard lists, caption phrases, labels, tolerances) live in the delta specs.
This file records the reasons and the mechanisms; where it lists something the spec also lists, the
spec wins.

## Context

- **The two surrogates.** Both come from one trainer, one set of flags and one holdout split.
  - Each `metrics.json` carries `per_target`, `config_resolved`, `phase_baseline_skill` (with the
    baseline definition) and `seed_sweep`.
  - `seed_sweep` covers seeds 1234–1238, the primary first. Each run records its `val_configs` and,
    per target, `skill`, `r2`, `rmse` and `config_mean_r2`. A `range` block summarises the runs.
- **What is committed.** Only the primary seed's predictions: 12,535 rows over 6 configurations,
  `wingbeat == 1` only. Every dataset configuration has wingbeats 0 and 1.
- **The pre-registered rule.** The fine README's "Coarse vs fine" table and its guard hold it:
  disjoint 5-seed skill ranges on raw values, with touching ranges counted as overlapping. Only
  `CF_y` is disjoint today. `CF_mz` overlaps by 1.0e-4.
- **Verified on the committed data,** bitwise unless stated (recomputed in review rounds 1–3):
  - the rebuilt baseline reproduces skill and RMSE, with a relative difference of 0.0 on Windows
    against the WSL-trained JSON;
  - `compute_config_resolved` reproduces `config_resolved`;
  - `range == {min, max}(runs)`;
  - every seed is scored on the same rows: `skill_s == 1 − (rmse_s/rmse₀)²` with a difference of 0;
  - the predictions' `*_true` columns equal the dataset's holdout rows with `wingbeat >= 1`, in
    order, with no duplicate `(config_name, time)` keys;
  - the D4 identity holds to 4.4e-14 relative;
  - no `|z| > 3`;
  - the closest `z` to a 601-edge bin boundary is 7.5e-9, about six orders of magnitude above the
    roughly 1e-14 floating-point error of `z`.

## Goals / Non-goals

- **Goals.**
  - Three figures, each saying one thing the data support.
  - The comparison cannot imply more than the rule allows.
  - Every number is traceable to committed bytes.
  - Each figure rebuilds by one command and fails CI when its inputs or renderer change.
- **Non-goals.**
  - Retraining.
  - Per-seed predictions.
  - The evidence figures and `evidence_figure.py`.
  - #131 items other than 8.
  - #148/#149.
  - The corpus regeneration.

## Decisions

### D1 — Three figures, each with one job; the old builders are removed

| figure | its one job | seeds shown |
|---|---|---|
| `skill_ranges` | the only cross-grid comparison: skill ranges under the rule | all |
| `error_histograms` | what skill means within each grid: surrogate error beside baseline error | the primary, with its range |
| `cycle_mean_r2_diagnostic` | why cycle-mean R² is ill-conditioned on six configurations | all |

**The scatter is retired for real data.** The evidence figures already show predicted against CFD
per grid. Two identical-looking panels carry no comparison.

**Removals.** The old builders, scripts, tests and synthetic renders are removed after the new
builders exist, so every commit stays green. Two kinds of historical mention stay: comments in
`visualization/flow_video.py` and `kinematics_video.py`, and the #73–#75 entries in
`docs/CHANGELOG.md`.

**Labels.** A module constant `TARGET_LABELS` holds the label table (spec). It deliberately differs
from the evidence figure's `_panel_title` (`CF_x (stroke-axis force)`, `CF_m (aerodynamic moment,
M_y component)`). The two reasons:

- the stroke is a rotation about lab z, so "stroke-axis" is ambiguous for a lab-x force;
- `evidence_figure.py` is out of scope.

A follow-up issue proposes that the evidence figure adopt `TARGET_LABELS`.

### D2 — `skill_ranges`

- **Layout.** Markers per seed and a bar from min to max. The primary seed's marker is distinct.
  Null targets are labelled `n/a`.
- **Values.** Read verbatim.
- **Overlap.** `ranges_overlap` uses the README rule, and tests check it against
  `_readme_guards.overlap_cell`.
- **The in-axes note** is generic: it cannot know why a future disjointness happens. The README
  carries the `CF_y`-specific seed-artifact argument.
- **The sidecar** records the drawn state (marker count, bar, `n/a`), the notes and the caption. The
  figure is closed before tests can inspect it, so these assertions are made against the sidecar.
- **Nulls are all-or-none.** `compute_baseline_skill`'s sentinel depends only on the truth and the
  baseline, which every seed shares. So a null skill is all-or-none per corpus and target, exactly as
  `config_mean_r2` is. The shared guard refuses a partial null instead of drawing one, because the
  trainer cannot produce one.

### D3 — `error_histograms`

- **Baseline.** Rebuilt with `build_phase_only_baseline(dataset_df, predictions.phase)`. Its
  definition must equal `phase_baseline_skill.phase_baseline`, with lists compared as lists.
  - `rmse₀` must equal `phase_baseline_rmse` at `rel=1e-9, abs=0`.
  - `1 − skill` must equal the recorded `1 − skill` at `rel=1e-9, abs=0`.

  Comparing the complement keeps the check well-conditioned near both 0 and 1. A null recorded skill
  is refused: a histogram in units of a near-zero RMSE has no meaning.
- **Recorded and recomputed values.** `z` uses the recomputed `rmse₀`. The sidecar records the
  recomputed `rmse0`, `rmse_surrogate` and `skill = 1 − (rmse_surrogate/rmse0)²`, so the identity holds
  to `rel=1e-12` by construction. It records `skill_recorded` (from `runs[0]`) and its range verbatim
  for the annotation. Recorded and recomputed differ by at most the `1e-9` acceptance tolerance.
- **Plot.** 2 rows × 6 columns, on edges `linspace(-3, 3, 601)`, with log density
  `counts / (n_rows · numpy.diff(edges))`. The edges are not exactly uniform: `diff` varies by about
  1e-15. Out-of-range counts are printed. The annotation and caption follow the spec.
- **Predictions are tied to the dataset** (shared guard 9). This also refuses predictions swapped
  between corpora.

### D4 — `cycle_mean_r2_diagnostic`

**Identity.** Cycle means are computed as `compute_config_resolved` does.

- σ is the population standard deviation of the true cycle means.
- ε is the RMS of `p̄ − t̄`.
- `_r2` is `1 − SSE/SST` with `SST = Σ(t̄ − mean t̄)²`, so `config_mean_r2 = 1 − ε²/σ²` exactly.

**Why ε_s is exact for every seed.** σ is seed-independent: it uses only the true cycle means, and
every seed is scored on the same rows. So `ε_s = σ·sqrt(1 − R²_s)` holds for every seed from its
committed R².

**Tolerance form T:** `|a − b| ≤ 1e-12·max(1, |b|)`, with `b` the recorded value. It is applied to
`1 − R²`, and to `ε²/σ²` against `1 − R²_primary`. The bound is absolute below 1 and relative above,
so it stays well-conditioned at R² → 1, at R² = 0 and at large negative R².

A `× (1 + 1e-10)` perturbation of R² is refused only for `R² > 0.01` or `R² < −1/99`. The test therefore uses the
23/35 fixture (66× margin) and checks that `× (1 + 1e-14)` is accepted.

**Nulls.** `_r2`'s sentinel depends only on the true cycle means, so a null is all-or-none (shared
guard 10). If null, σ is recorded as computed and every `ε_s` is null.

- σ is exactly 0.0 only when the equal cycle means are bitwise equal. The fixtures use a dyadic
  constant with even row counts.
- Zero or null scale values are drawn as floor markers, never as log-axis data. A log axis with no
  positive data raises a `UserWarning`, which `filterwarnings("error")` would turn into a test
  failure.

**Panels.**

- **Scales** (log): waveform RMS, σ, and the `ε_s`.
- **Seeds** (symlog, linear within ±1): the `config_mean_r2` values, with 0 and 1 marked.

The waveform row and its phase-wrap artifact are dropped. The figure is renamed from
`config_mean_collapse`.

#### Why recompute instead of "read verbatim, never re-derived"?

The live requirement trusted `config_resolved` verbatim. A swapped or edited block would then have
gone into the figure unnoticed.

Recomputing from the committed predictions and requiring equality keeps the original protection,
which is never reporting a number from the wrong block, because the equality fails if the wrong
block is read. It also catches a `metrics.json` that no longer matches its predictions.

### D5 — Inputs, guards, provenance

- **The `root` seam.** Builders and `compute_<figure>_metrics` take `root: Path`. The driver passes
  `Path.cwd()`, and tests pass `tmp_path`.
  - Inputs resolve as `root / <corpus dir> / ...`.
  - `renderer_sources` hashes the two renderer files from their own locations, keyed by fixed names,
    so a `tmp_path` root works.
  - Tests monkeypatch `mosquito_cfd.benchmarks.metadata.get_git_info`. It uses `Path.cwd()`, and
    tests inject `dirty`.
- **Guards.** The ordered list (spec) runs before any output, and a refusal names the first guard
  tripped. The order puts cheap and structural checks before cross-file ones. A defect that trips two
  guards therefore has one deterministic message.
- **The beat lower bound** is `train.CONVERGED_MIN_WINGBEAT`, checked equal to
  `phase_baseline.converged_min_wingbeat`, not a literal 1.
- **Paths.** `_portable_path` resolves a relative path against `root`, then makes it relative and
  posix. It refuses anything outside `root`.
- **`*_run_metadata.json`** is captured by `capture_surrogate_run_metadata` with the caller digest,
  by convention the fine corpus's CFD digest. Then:
  - `inputs.file` is overridden with the portable `coarse_metrics` path, because
    `capture_run_metadata` records `str(path)`;
  - `input_files`, `corpus_docker_images`, `library_versions`, `renderer_sources` and `figure` are
    added.
- **Writing.**
  - Every value is computed first.
  - The PNG goes to a `BytesIO`, and the figure is closed in `finally`.
  - The JSON is serialised to strings.
  - Each file is written to a temporary name and moved into place with `os.replace`, in the order
    PNG, metrics, run_metadata. A failure between two `os.replace` calls leaves exactly the files
    already moved (for example the PNG alone) and no temporary file. That is documented and tested.
  - Explicit `subplots_adjust` is used, not `tight_layout`, which can warn with a long caption.
  - Files are read with `Path.read_bytes`, so no `ResourceWarning` is raised.

#### Why per-corpus guard order instead of one global order?

The code loads the coarse corpus completely (guards 2–10), then the fine corpus, then pairs them
(guard 11). A global order would run guard 2 on both corpora before guard 3 on either, so a coarse
defect at guard 7 and a fine defect at guard 2 would report the fine one first. Either rule gives
one deterministic message per defect. Per-corpus loading keeps `_load_corpus` a single function
that returns one validated corpus, and the spec's guard requirement now states this order.

#### Why more checks than the spec's eleven?

Review rounds and mutation testing found inputs that passed the eleven guards as first written and
then failed later, or loaded wrongly without failing. Examples are `1e999` in a JSON file, which
loads as `inf`; an integer too large for a float; a boolean column; a prediction `phase` that
differs from the dataset's; and a `seeds` list that disagrees with `runs`. Each was added inside
the guard it belongs to, so the numbering and the first-guard rule are unchanged. The spec now
lists them.

#### Why make `root` absolute in `_load_pair`?

With a relative `root` other than `.`, an input path was joined to `root` and then made relative to
it again, so the recorded path was wrong. `_load_pair` makes `root` absolute once, before either
corpus is read. `_prepare` is guard 1 followed by `_load_pair`. The `compute_*_metrics` functions,
which take no digest, call `_load_pair` directly.

#### Why can `renderer_sources` hold `null`?

`_renderer_sources` hashes `scripts/make_coarse_vs_fine_figures.py` from the repository layout. In
an installed package without `scripts/`, that file is absent. Recording `null` keeps the builders
usable there, and the committed-figure check still fails, because the committed sidecars record a
hash.

### D6 — Captions and shared constants

- **Captions** are built by pure functions (spec lists the required and forbidden content).
- **Shared constants.** `RULE_SENTENCE` (a template with `{n}`) and `OWN_BASELINE_PHRASE` are
  constants in `comparison_figure.py`.
  - The README test collapses whitespace in the "Coarse vs fine" section and searches it
    case-insensitively. `RULE_SENTENCE.format(n=5)` and `OWN_BASELINE_PHRASE` both already match the
    current README text (checked in round 2), so no guarded README prose changes.
  - These constants must be final before any render. Their README test is therefore written in
    section 4, not section 10.
- **The diagnostic** uses no phase-only baseline, so its caption states the configuration count
  instead of the own-baseline phrase.
- **`_BANNED`** applies to `skill_ranges` only. The diagnostic must be able to say an error is larger
  than the spread.
- **The forbidden-word pattern** catches `spanwise`, `chordwise` and `wing-normal`, and lets
  `normalised` and `timespan` through.

### D7 — Location, committed-artifact checks, re-render rule

- **Location.** `examples/prelim_sweep_fine/figures/coarse_vs_fine/`, 9 files.
- **The checker.** `tests/_comparison_guards.py::check_committed_figure(root, figure)`, with its own
  tests in `tests/test_comparison_guards.py`. It checks the input hashes first. A stale input
  therefore fails as a named hash mismatch, not as a library `ValueError`; any library `ValueError` is
  re-raised as `AssertionError` naming the figure.
  - **Tolerances** (spec): exact for verbatim values, counts, edges, strings and drawn states;
    `rel=1e-12, abs=0` for every other float, with exact zeros compared exactly.
  - **Run metadata.** Only the listed fields are checked. `library_versions` is not compared with the
    CI environment.
  - **The cross-figure timestamp** is checked in the repository test, not the per-figure helper.
- **`git.dirty`** comes from `git diff HEAD`. It ignores untracked files, but it counts every modified
  tracked file, including `tasks.md` ticks and a figure file overwritten in place. Three consequences:
  - Task ticks are frozen between the pre-render check and the data commit (tasks working rules).
  - Every render, the first included, goes to a scratch directory outside the repository, and the
    nine files are then copied in (spec: Re-rendering).
  - `git status --porcelain --untracked-files=all` and `git diff HEAD --stat` are both checked before
    each render.
- **The re-render rule.** Any byte change to `comparison_figure.py` or the driver after a render, a
  docstring or comment included, means all three figures are re-rendered. The re-render is made from
  a clean tree with the change committed, in one `data(...)` commit.
  - CI enforces this through `renderer_sources`.
  - The fix commit is red until the re-render commit lands. The two are pushed together, never apart.
  - Re-rendering costs seconds. Hashing raw bytes rather than an AST is the simpler and stricter
    choice.
- **Imported code.** `train.py` (which F3a edits) and `benchmarks/metadata.py` are not hashed. A
  change there is caught only if it changes a recorded number.
- **The corpus regeneration** fails these checks on purpose. That future change must retrain, then
  re-render. The fine README's "Comparison figures" section says so, and both READMEs' Regenerating
  blocks point there.

### D8 — Training metadata, forward only

- `build_training_metadata` keeps `seeds` at the top level.
- Under `library_versions` it adds `python` (`platform.python_version()`), plus `numpy`, `pandas`
  and `pyarrow`, read with `_library_version`; each is `None` if not installed.
- The committed surrogate records are not rewritten. The coarse README says once, in its Surrogate
  section, that they predate the field and that `uv.lock` at the recorded commit is the record. The
  fine README points there.
- F3a's `surrogate_h3/` picks up the new keys if this merges first.

### D9 — Docs

**Fine README.**

- A new sibling section, `### Comparison figures`, after "Coarse vs fine". Its heading does not
  contain "Coarse vs fine", and it lies outside the guarded section, where only `_COMPARATIVE`,
  `_FINE_COMPARATIVE` and the denominator-ratio check apply. It holds:
  - the three links;
  - `skill_ranges draws the table above and is the only comparison between the grids;
    error_histograms and cycle_mean_r2_diagnostic each describe one grid at a time`;
  - that each sidecar records its inputs and renderer, and CI fails if any changes;
  - that `docker_image` is the fine corpus's CFD digest, with both digests under
    `corpus_docker_images`;
  - that `git.commit` is the code commit the figures were rendered from;
  - that a corpus regeneration makes these checks fail on purpose: retrain, then re-render into a
    scratch directory and copy in;
  - that the committed surrogate records predate the `library_versions` additions (a pointer to the
    coarse README's note);
  - the one regeneration recipe:

    ```bash
    # from the repository root, on a clean committed tree
    out="$(mktemp -d)"
    digest="$(python -c 'import json;print(json.load(open("examples/prelim_sweep_fine/run_metadata.json"))["docker_image"])')"
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    for fig in skill_ranges error_histograms cycle_mean_r2_diagnostic; do
      uv run --frozen --group viz python scripts/make_coarse_vs_fine_figures.py --figure "$fig" \
        --coarse-dir examples/prelim_sweep --fine-dir examples/prelim_sweep_fine \
        --out-dir "$out" --docker-digest "$digest" --timestamp "$ts"
    done
    cp "$out"/* examples/prelim_sweep_fine/figures/coarse_vs_fine/
    ```
- Inside "Coarse vs fine", one sentence: `The committed figure of these ranges, and two within-grid
  figures, are described under [Comparison figures](#comparison-figures).`
- The `figures/` row mentions `figures/coarse_vs_fine/`.
- The Regenerating block gets a one-line pointer: "then re-render the comparison figures".
- The Speedup paragraph is untouched.

**Coarse README, quasi-steady bullet.** Two spans are replaced. The text below was simulated against
every guard in round 2.

- First span, replacing "At this coarse grid … not investigated here.":

  > At this coarse grid it overshoots the CFD lift ~1.3× in RMS, and on the 256×128×256 grid ~1.4×
  > (each is `quasi_steady_reference.overshoot_factor` in that corpus's
  > `figures/evidence_figure_metrics.json`). The ratio has changed with each corpus correction (#36,
  > #71); its history is in the git log of `figures/evidence_figure_metrics.json`. The ratio stays
  > above 1 on the fine grid. Why the uncalibrated model over-predicts the lift was not investigated
  > here; the omitted terms would be expected to add lift, so they are unlikely to explain it.

- Last sentence:

  > A *fair* quantitative comparison would require scale-calibrating the QS model to the CFD, which
  > makes it a fitted model and is out of scope here.

**Why this wording.**

- **The historical ratio.** The current README's "down from ~2.3× before the corrected hinge geometry
  (#71)" is wrong. Git history shows the committed coarse `overshoot_factor` was 2.27 at #25, 0.73 at
  #36 (the last commit before #71) and 1.34 from #71 on. The new text therefore names no historical
  value.
- **The causal claim.** That the omitted terms would add lift is a physics expectation, not a
  measurement: added mass and symmetric-rotation lift change sign over the stroke. Both READMEs
  therefore use the conditional wording. The fine README's sentence "the omitted terms would add lift,
  so the omissions do not explain the gap" becomes "would be expected to add lift, so they are unlikely
  to explain the gap". `check_fine_qs_disclosure` does not key on that sentence (its required words
  are kept).
- **Withdrawn.** The round-1 instruction to attribute the gap to the omitted terms was wrong and is
  withdrawn.

`check_coarse_qs_ratios` (fs spec) guards the bullet.

**Coarse README, other edits.**

- The Figure section gets one link to `../prelim_sweep_fine/README.md#comparison-figures`. A test
  checks that the anchor exists.
- The Regenerating block gets the same one-line pointer.

**`openspec/project.md`.**

- Delete the two stale Pending items cleanly.
- Fix "decks + manifest only, no CFD output yet" and "(CFD re-run deferred)".
- Make the CLI-driver sentence count-free.
- Fix the Visualization Tooling parenthetical.
- Replace the two old command blocks with a pointer.

**`docs/CHANGELOG.md`.** One Added bullet, one Changed line; history kept.

### D10 — Coordination and order

- **F3a** edits other hunks of the same three docs, and other `train.py` functions.
  - This PR is expected to merge first. F3a then merges `main` in; it never rebases.
  - The hunk list is in D9, for the user to pass on.
  - The CHANGELOG change is the last commit and a single bullet.
- **Lab meeting.** The slides may use PNGs from branch commits. Those commits resolve for others only
  once pushed. The approval checkpoint asks about pushing, or a draft PR, before 2026-11-24. A
  re-render after the slides are built changes the PNGs, and the user is told which slides.

## Risks / Trade-offs

- **The figures go stale at the corpus regeneration.** That is intended, and the rebuild is one
  command per figure.
- **Seed-1234 histograms could be read across grids.** The caption forbids that reading,
  baseline-RMSE units are used, and each panel shows its seed range.
- **The in-axes note is generic.** The README explains `CF_y`.
- **Raw-byte renderer hashes** force a re-render even for a comment fix. The cost is seconds.
- **Removing public functions.** They are internal, and flagged BREAKING.

## Migration

None for users. The fine README recipe shows the new driver.

## Open Questions

None. The user settled figures, location, caption label and extras on 2026-11-16/18. Push timing is
asked at the approval checkpoint.
