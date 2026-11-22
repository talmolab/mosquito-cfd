# Tasks: add-real-comparison-figures

One PR, ordered as the commits below.

## Working rules

- **TDD.** Every behaviour change is test-first: the test is written, run, and seen to fail for the
  stated reason before the implementation.
- **Mutation testing.**
  - Every new guard is mutation-tested on saved-bytes copies (`PYTHONDONTWRITEBYTECODE=1`, restore
    with `write_bytes`, never `git checkout`).
  - Never run mutation tests alongside another test run.
  - The kill tables go in the session scratchpad.
- **Suite.** `uv sync --frozen --group viz`, then `uv run --frozen pytest -v -m "not gpu"` from Git
  Bash. Run ruff check and `ruff format --check` on CI's lint paths: `src/ tests/ scripts/
  examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`.
- **Commit messages.** Say "advances #N", never a closing keyword. End each with the session's
  `Co-Authored-By` trailer.
- **Task ticks.** Ticking edits tracked `tasks.md`.
  - **Between the 8.4 check and the 9.6 data commit, edit no tracked file** (no ticks, no notes),
    except the 9.5 code fix, which is committed. Those ticks go into the 9.7 commit.
  - Every other tick goes into the commit that completes the task.
  - Ticks for tasks with no commit of their own (10.5, 10.6, 11.1–11.3) go into a tick-only
    `chore(openspec)` commit. Before an 11.3 re-render, that tick-only commit comes **before** the fix
    commit, so `HEAD~1` of the data commit is still the code commit.
- **Before any render.** Re-run `git status --porcelain --untracked-files=all` and
  `git diff HEAD --stat` immediately before each render. Both must be empty.
- **Rendering.** Every render goes to a scratch directory **outside the repository**, under the
  session scratchpad. The nine files are then copied into
  `examples/prelim_sweep_fine/figures/coarse_vs_fine/`. A scratch directory inside the repository
  would show up as untracked and fail the pre-render check.
- **Deadline.** Figures on the branch by 2026-11-21 (lab meeting 2026-11-24).

## 0. Baseline, follow-ups, proposal commit

- [x] 0.1 At `c87e39c`: run the full CPU suite and ruff. Record the counts.
- [x] 0.2 `rg` for every importer or executable reference to the old builders, scripts and
  `tests/fixtures/comparison_figure`.
  - Scope: `src/`, `scripts/`, `tests/`, `examples/`, `docs/`, `.claude/`, `README.md`,
    `openspec/project.md`, `openspec/specs/`.
  - Expected hits: the files this change edits or removes.
  - Expected historical mentions, which stay: comments in `visualization/flow_video.py` and
    `kinematics_video.py`, and the `docs/CHANGELOG.md` entries for #73–#75.
  - The live `openspec/specs/visualization-tooling/spec.md`: rewritten at archive.
- [ ] 0.3 File follow-up issues, asking the user first, as these are outward-facing:
  - the evidence figure adopting `TARGET_LABELS` (its `CF_x (stroke-axis force)` is ambiguous);
  - `docs/coordinate-convention.md`'s "Forces" section reading as if it covered the lab-frame
    corpus `CF_*`.
- [x] 0.4 After the last `/review-openspec` round is reconciled, commit the whole change directory,
  review files included: `docs(openspec): propose add-real-comparison-figures (advances #114, #130)`.

## 1. Training provenance records the Python data stack (#130 item 4)

- [x] 1.1 **Test first** (`tests/test_force_surrogate_train.py`, CI tier).
  - `library_versions.python == platform.python_version()`.
  - `numpy`, `pandas` and `pyarrow` equal `importlib.metadata.version(...)` and are non-null
    strings.
  - `seeds` is top-level.
  - With `importlib.metadata.version` patched to raise `PackageNotFoundError` for `pyarrow`,
    `pyarrow` is `None` and the other keys are unaffected.
  - The existing `torch`/`physicsnemo` asserts are unchanged.
- [x] 1.2 Implement in `build_training_metadata`, reusing `_library_version`, and update the
  docstring.
- [x] 1.3 Mutation-test 1.1:
  - drop each key;
  - swap the `pyarrow`/`pandas` distributions;
  - `sys.version` instead of `platform.python_version()`;
  - `None` for python.
- [x] 1.4 Commit: `feat(force-surrogate): record the Python data stack in training provenance (advances #130)`.

## 2. Synthetic corpus helper

- [x] 2.1 `tests/_comparison_corpus.py::write_repo(root, coarse=..., fine=...)` writes
  `root/examples/prelim_sweep{,_fine}/` and `root/examples/prelim_sweep_fine/run_metadata.json`.
  Each corpus is built the way `run_training` does:
  - **Dataset.** `dataset.parquet` with `config_name`, `split`, `time`, `phase`, `wingbeat` and the
    six targets:
    - wingbeats `0..N−1` in every configuration (default N = 2);
    - training configurations plus six holdout configurations;
    - an **even** number of rows per configuration and beat.
  - **Metrics.** `metrics.json` is assembled as:
    1. `build_phase_only_baseline`;
    2. `build_seed_run` per seed, on per-seed predictions with per-seed error scales;
    3. `build_metrics(..., phase_baseline=)`, with fixed `inference` and `reproducibility` blocks
       copied in shape from the committed file;
    4. `summarize_seed_sweep`;
    5. written with `train.write_json`.
  - **Surrogate files.** `holdout_predictions.parquet`, and `surrogate/run_metadata.json` with the
    dataset's real sha256 and a fixed digest.
  - **Two edit stages.**
    - `edit_runs(runs)` edits per-seed dicts **before** `summarize_seed_sweep`, so `range` stays
      consistent. It is used for boundary R², `> 1` and null values on non-primary seeds.
    - `edit_metrics(dict)` edits the assembled JSON. It is used for range, ulp and block-mismatch
      defects.
    - `edit_dataset(df)` edits the dataset frame **before** it is hashed, and before the baseline,
      the predictions and `metrics.json` are built from it, so guard 5 still passes. It is used for
      `{0, 2}` wingbeats and the extra beat. A dataset duplicate key goes on a holdout configuration,
      because `build_phase_only_baseline` refuses a duplicate phase in a training one.
  - **Null and constant targets.**
    - Equal true cycle means are produced by construction: holdout true values alternating
      `0.5 ± 1`, so the means are bitwise equal. The training configurations' values for that target
      differ from the holdout alternation, so the skill stays finite. This fixture is used for the
      diagnostic only.
    - A target with the **same dyadic constant** (for example `0.75`) in every configuration,
      holdout included, makes the baseline SSE exactly `0.0` and the skill null by construction.
    - Neither is in the default corpus.
    - A non-zero waveform is kept wherever a log axis must have positive data.
  - **Byte differences.** The coarse and fine corpora differ in every file.
- [x] 2.2 Test the helper independently:
  - **(a) Key tree.** The fixture `metrics.json` key tree equals the committed
    `examples/prelim_sweep/surrogate/metrics.json` key tree, with `per_config`'s configuration keys
    replaced by one wildcard and `inference`/`reproducibility` compared by key set.
  - **(b) Known answer, literal values.**
    - `CF_x`, built from 2-point linear-ramp training beats, with truth = baseline + 1 and surrogate
      error ±0.1, gives baseline RMSE `1.0` and skill `0.99`.
    - `CF_y`, with holdout truth constant per configuration at `[0, 0, 0, 0, 0, 6]`, gives σ
      `sqrt(5)`.
  - **(c) Byte differences.** The coarse and fine fixtures differ in every file.
- [x] 2.3 Commit: `test(force-surrogate): synthetic corpus helper for comparison-figure tests (advances #114)`.

## 3. Shared loader, guards and provenance

This section is additive; the old builders stay until 7.

- [x] 3.1 **Tests first.** Parametrize over the three builders. Until sections 4–6 they are stubs
  that call `validate_image_digest`, `_load_corpus` and `_check_pair`, then raise
  `NotImplementedError`.
  - **Every defect listed in the spec scenario "each defect is refused before any output":**
    - a `ValueError` naming the corpus and the **first guard in the spec's order** that the defect
      trips;
    - an empty `out_dir`;
    - `plt.get_fignums()` unchanged.
  - **The digest is checked first:** a mutable digest with non-existent corpus directories raises
    the digest error.
  - **A valid pair** reaches `NotImplementedError`.
- [x] 3.2 **Tests first**, directly on the helpers:
  - `_portable_path` on `PureWindowsPath`, on `PurePosixPath`, on a relative path with an absolute
    root, and on an outside-root or `..` path (refused).
  - `_provenance(...)` records:
    - all 8 roles with their real sha256;
    - a portable `inputs.file` and `inputs.hash` for `coarse_metrics`;
    - `corpus_docker_images`;
    - 5 non-null `library_versions`;
    - `renderer_sources` equal to the LF-normalised sha256 of the two files, read from their own
      locations;
    - `figure`.
  - `_write_outputs(...)`, given a trivial `Figure` built in the test:
    - writes exactly three files;
    - with `savefig` patched to raise, leaves no file and no open figure;
    - with the second `os.replace` patched to raise, leaves exactly the first file (the PNG; the write
      order is PNG, metrics, run_metadata), no temporary file, and no open figure.
- [x] 3.3 Implement `_load_corpus`, `_check_pair`, `_beat_structure`, `_portable_path`,
  `_provenance` and `_write_outputs`, and the three builder stubs that raise `NotImplementedError`. Builder tests use `filterwarnings("error")`.
- [x] 3.4 Commit: `feat(force-surrogate): comparison-figure input loading, guards and provenance (advances #114)`.

## 4. `skill_ranges` and the shared constants

- [x] 4.1 **Tests first.**
  - **Values.**
    - Per-seed values come from `runs[i].per_target.<c>.skill`, in seed order.
    - None equals an `r2`, `rmse`, `config_mean_r2`, `phase_baseline_r2` or `phase_baseline_rmse`.
    - The primary equals `phase_baseline_skill`.
  - **`ranges_overlap`.**
    - Touching pairs give `yes`, pairs one ulp apart give `no`, overlapping pairs give `yes`, and a
      null range gives `n/a`.
    - It agrees with `_readme_guards.overlap_cell` on those pairs and on the committed metrics
      (`no` for `CF_y` only).
  - **Notes.** Exactly one when only `CF_y` is disjoint; none when all overlap.
  - **All-null target.** It records `n/a`, no bar, zero markers and no note.
  - **Caption and labels.**
    - The required phrases, with primary seed 42, three seeds and six configurations: `seed 42`,
      `3 seeds`, `RULE_SENTENCE.format(n=3)`.
    - The beat label for `{0, 1}`/`{1}` and for `{0..3}`/`{1..3}`.
    - `TARGET_LABELS`.
    - Nothing matches the forbidden pattern, `_COMPARATIVE`, `_FINE_COMPARATIVE` or `_BANNED`.
    - The forbidden-pattern scenario: `normalised` and `timespan` pass; `wing-normal`, `spanwise`,
      `chordwise`, `spans` and `rolling` match.
  - **README constants.** The fine README's "Coarse vs fine" section, whitespace-collapsed and
    case-insensitive, contains `OWN_BASELINE_PHRASE` and `RULE_SENTENCE.format(n=5)`. This test sits
    here so the constants are final before any render.
  - **End-to-end.** The real builder writes three files with full provenance, and
    `compute_skill_ranges_metrics` equals the builder's sidecar.
- [x] 4.2 Implement:
  - `compute_skill_ranges_metrics`, `build_skill_ranges_caption` and `build_skill_ranges`;
  - the shared caption pieces;
  - `TARGET_LABELS`, `RULE_SENTENCE`, `OWN_BASELINE_PHRASE` and `FORBIDDEN_WORDS`.
- [x] 4.3 Commit: `feat(force-surrogate): skill_ranges figure (advances #114)`.

## 5. `error_histograms`

- [x] 5.1 **Tests first.**
  - **Bin convention.** `_bin_counts` on `[-3.5, -3.0, 0.0, 3.0, 3.5]`.
  - **Counts and density.**
    - Counts equal `np.histogram` on the 601 edges.
    - Out-of-range values are counted, and counts + below + above = `n_rows`.
    - Density is `counts / (n_rows · np.diff(edges))`.
  - **Identity.** On the recomputed values, `(rmse_s/rmse0)²` equals `1 − skill` at `rel=1e-12,
    abs=0`. `skill_recorded` equals `runs[0]` exactly.
  - **Thresholds.**
    - `phase_baseline_rmse × (1 + 1e-8)` is refused; `× (1 + 1e-11)` is accepted.
    - The recorded skill set to `1 − (1 − skill)·(1 + 1e-8)` is refused, and to
      `1 − (1 − skill)·(1 + 1e-11)` accepted. The edit is applied to `runs[0]` via `edit_runs` and to
      `phase_baseline_skill` via `edit_metrics`.
  - **Refusals.** A definition-list order change. A null recorded skill.
  - **Annotation.** `seed 42 skill <x> (3 seeds: <lo> to <hi>)`, verbatim, on the 42 / 3-seed
    fixture.
  - **Known answers.**
    - **K2: the baseline excludes the holdout and weights configurations equally.**
      - Setup: training targets `sin 2πφ + c` with `c = [−1, 0, +1]` and row counts 4, 8, 16;
        holdout truth `sin 2πφ + 10`; query phases equal to the reference phases.
      - Expected: baseline `sin 2πφ` and `rmse0 = 10`.
      - Leaking the holdout, or weighting by row count, changes `rmse0`.
    - **K3: pooled skill.**
      - Setup: configuration A with 2 rows, SSE_s 1, SSE₀ 2; configuration B with 4 rows, SSE_s 1,
        SSE₀ 8.
      - Expected: pooled skill `0.8`, not the per-configuration mean `0.6875` or the row-weighted
        `0.75`.
  - **Caption.**
    - The required phrases, including `seed 42`, `skill = 1 − (RMSE / RMSE₀)²` and
      `consecutive timesteps of 6 configurations`.
    - The beat label for `{0, 1}`/`{1}` and for `{0..3}`/`{1..3}`.
    - Nothing matches the forbidden pattern, `_COMPARATIVE` or `_FINE_COMPARATIVE`.
- [x] 5.2 Implement `compute_error_histograms_metrics`, the caption and `build_error_histograms`.
- [x] 5.3 Commit: `feat(force-surrogate): error_histograms figure (advances #114)`.

## 6. `cycle_mean_r2_diagnostic`

- [x] 6.1 **Tests first.**
  - **K1 (the 23/35 fixture).**
    - σ = `sqrt(35/12)`, which fails if `ddof=1`.
    - ε = `1`.
    - R² = `23/35` in form T.
    - The within-configuration ±0.5 error leaves ε unchanged.
    - The seed with offset 3 gives R² = `−73/35` and `ε_s = 3 > σ`.
  - **Agreement.**
    - The primary equals `config_resolved` and `runs[0]`.
    - The five `ε_s` equal `σ·sqrt(1 − R²_s)` at `rel=1e-12, abs=0`.
    - The primary's measured `ε²/σ²` equals `1 − R²` in form T.
    - Recorded R² × (1 + 1e-10) on the 23/35 fixture is refused; × (1 + 1e-14) is accepted.
    - A primary R² of `1 − 1e-6` is accepted (per-configuration offsets ±`1e-3·σ`). This kills a
      tolerance relative to `1 − R²` on the `ε²/σ²` check.
  - **Boundaries** (non-primary seeds, via `edit_runs`).
    - R² `0.0` gives `ε == σ`.
    - R² `1.0` gives `ε == 0.0`, recorded as a floor marker labelled `0`.
    - R² `−1e6` is drawn with no warning.
  - **Null.** The `0.5 ± 1` fixture gives null values, σ exactly `0.0`, the `n/a` drawn state and no
    warning.
  - **Waveform RMS.** Alternating ±1 with even row counts gives `1.0`.
  - **Caption.**
    - The required phrases with `3 seeds` and `6 holdout configurations`.
    - It does not contain `OWN_BASELINE_PHRASE`.
    - The beat label for `{0, 1}`/`{1}` and for `{0..3}`/`{1..3}`.
    - Nothing matches the forbidden pattern, `_COMPARATIVE` or `_FINE_COMPARATIVE`.
  - **Block not swapped.** The recorded R² equals no `per_target` or `phase_baseline_skill` value.
- [x] 6.2 Implement `compute_cycle_mean_r2_diagnostic_metrics`, the caption and
  `build_cycle_mean_r2_diagnostic`.
- [x] 6.3 Commit: `feat(force-surrogate): cycle_mean_r2_diagnostic figure (advances #114)`.

## 7. Driver and removal

- [x] 7.1 **Tests first**, rewriting `tests/test_make_comparison_figure_cli.py` and keeping its
  `importlib` loader.
  - Each `--figure` writes exactly its three files.
  - `--figure coarse_vs_fine_comparison`, and omitting each of the six flags in turn, each exit with
    `code == 2` and leave `out_dir` empty.
- [x] 7.2 Implement `scripts/make_coarse_vs_fine_figures.py`, passing `root=Path.cwd()`. Its
  docstring holds the argument contract.
- [x] 7.3 Remove:
  - `build_coarse_vs_fine_comparison` and `build_config_mean_collapse_diagnostic`;
  - their tests;
  - `scripts/make_comparison_figure.py` and `scripts/make_config_mean_collapse_diagnostic.py`;
  - `tests/fixtures/comparison_figure/`.

  Rewrite the module docstring.
- [x] 7.4 Mutation-test sections 3–7. Each mutant must fail at least one test.
  - **Section 3.**
    - Drop each shared guard in turn.
    - Swap the order of guards 5 and 9.
    - Compare the definition lists as sets.
    - Drop `parse_constant`.
    - Drop the per-configuration beat check.
    - Drop the `converged_min_wingbeat` equality.
    - Drop the duplicate-key check.
    - Write the sidecars before `savefig`.
    - Drop `finally: plt.close`.
    - Drop the outside-root refusal.
    - Swap the coarse and fine roles in `input_files`.
    - Treat `null == null` as unequal in the `runs[0]` check.
  - **Section 4.**
    - Flip `<=` to `<` in `ranges_overlap`.
    - Hard-code `5` in `RULE_SENTENCE`.
    - Drop `_BANNED` from the caption check.
  - **Section 5.**
    - Widen any tolerance to `1e-6`.
    - Use `>` instead of `>=` for out-of-range.
    - Use `density=True`.
    - Use the recorded `rmse0` for `z`.
    - Hard-code `5` or `1234` in the annotation.
  - **Section 6.**
    - Read every seed's R² from `config_resolved`.
    - `ddof=1` in σ, alone and together with ε.
    - Drop the `R² > 1` refusal.
    - Drop the partial-null refusal.
    - Make the `ε²/σ²` tolerance relative to `1 − R²`.
    - Draw zero values as log-axis data.
    - Hard-code `5` in the caption.

  Every survivor gets a test or a written equivalence argument.
- [x] 7.5 Commit: `feat(force-surrogate)!: one coarse-vs-fine driver; remove the retired scatter and collapse builders (advances #114)`.

## 8. Gate before rendering

- [ ] 8.1 Run the full suite, ruff, `openspec validate add-real-comparison-figures --strict` and the
  mutation table.
- [ ] 8.2 An adversarial review of sections 3–7 by a fresh reviewer, reproducing by running code.
  Fixes are committed before 8.3.
- [ ] 8.3 Commit the ticks for 0–8.3 and any new change-directory file:
  `chore(openspec): tick tasks 0-8 (advances #114)`.
- [ ] 8.4 Both pre-render checks (working rules) are empty. **From here until 9.6, tick nothing.**

## 9. Committed-artifact checker, render, commit

- [ ] 9.1 **Test first.** Write `tests/_comparison_guards.py::check_committed_figure(root, figure)`,
  tested in `tests/test_comparison_guards.py` on synthetic layouts from `write_repo`, rendered by
  the real builder with injected git metadata.
  - The unmodified layout passes.
  - Each of the spec scenario's copies fails with `AssertionError` naming the figure and the role or
    field.

  Commit, green: `test(force-surrogate): committed comparison-figure checker (advances #114)`.
- [ ] 9.2 Write `tests/test_committed_comparison_figures.py`:
  - `check_committed_figure` per figure, against the repository;
  - one shared timestamp across the three figures;
  - the independent anchors (D7);
  - `git ls-files --error-unmatch` for the 9 files;
  - the PNG signature;
  - `tests/fixtures/comparison_figure/` absent.

  Run it and see it fail on the absent files. Then move the file out of the repository, to the
  session scratchpad, and confirm that both pre-render checks are empty again.
- [ ] 9.3 Render each figure into a scratch directory at the same clean HEAD:
  - `--coarse-dir examples/prelim_sweep --fine-dir examples/prelim_sweep_fine`;
  - the fine `run_metadata.json` digest;
  - one timestamp.

  Render each a second time into a second scratch directory and `cmp` the PNG and the metrics
  sidecar.
- [ ] 9.4 **Inspect each PNG by eye.**
  - No clipped text, and the caption does not overlap the axes.
  - Log and symlog axes are labelled.
  - Markers are distinguishable.
  - The note appears on the `CF_y` row only.
  - Coarse `CF_x` (−6.70) and fine `CF_mz` (−4.70) are inside the seeds-panel limits.
  - The surrogate histograms are resolved.
- [ ] 9.5 **Binaries checkpoint.** Show the user the three PNGs. For a layout fix:
  1. Commit the code fix.
  2. Re-run 9.3–9.4 for all three figures.
- [ ] 9.6 Copy the nine files into `examples/prelim_sweep_fine/figures/coarse_vs_fine/`. Commit:
  `data(force-surrogate): coarse-vs-fine figures from the committed surrogates (advances #114)`.
  Then check, reading the committed sidecars, that:
  - `git show --stat HEAD` lists exactly the 9 files;
  - each recorded `git.commit` equals `git rev-parse HEAD~1`;
  - each recorded `git.dirty` is `false`.
- [ ] 9.7 Restore `tests/test_committed_comparison_figures.py` and see it pass. Tick 8.4 to 9.7.
  Commit: `test(force-surrogate): committed coarse-vs-fine figures match their inputs and renderer (advances #114)`.

## 10. Docs

- [ ] 10.1 **Test first:** `_readme_guards.check_coarse_qs_ratios`.
  - It takes the bullet slice and collapses its whitespace.
  - It requires two tokens in order and the phrase, and rejects the IB-bias-free regex.
  - It is tested on synthetic bullets for each defect in the spec scenario, then wired to the
    committed coarse README, where it fails today.
- [ ] 10.1b **Test first**, in `tests/test_committed_comparison_figures.py`: the coarse README links
  to `../prelim_sweep_fine/README.md#comparison-figures`, and the fine README has a
  `### Comparison figures` heading whose three PNG links resolve to the committed files. It fails
  today. The test is committed with the README edits
  that make it pass (10.2–10.4).
- [ ] 10.2 Coarse README.
  - Replace the two quasi-steady spans with the text in design D9. Grep the tests for every phrase
    being reworded, including `"2.4" not in readme`.
  - Add the Figure-section link to `../prelim_sweep_fine/README.md#comparison-figures`.
  - Add one sentence in the Surrogate section: the committed surrogate records predate the
    `library_versions` additions, and `uv.lock` at the recorded commit is the record.
  - Add the pointer under the `### Regenerating` heading of the Figure section (line ~463), not the
    other two `Regenerating` headings.

  Commit: `docs: coarse README quasi-steady ratios, guarded against both sidecars (advances #130)`.
- [ ] 10.3 Fine README (design D9).
  - The `### Comparison figures` section.
  - The linking sentence in "Coarse vs fine".
  - The `figures/` row.
  - The Regenerating pointer.
  - A pointer to the coarse README's training-record note.

  `check_comparison_table`, `check_fine_disclosures`, `R2_NEAR_TARGET`, the QS and denominator guards
  and the section-4 constants test stay green.
- [ ] 10.4 `openspec/project.md` (design D9). `rg docs/visualization` is empty outside the archive.
  Keep the phrase `(generic sinusoidal kinematics, van Veen axis convention)`, which
  `tests/test_kinematics_attribution.py` pins.
  Commit 10.3 and 10.4 together: `docs: link the coarse-vs-fine figures; fix stale fine-surrogate text in project.md (advances #114, #130)`.
- [ ] 10.5 Recompute every number in the new prose from the committed JSON, with a scratchpad script
  whose output is kept. Check any historical value against
  `git show <commit>:<path>/evidence_figure_metrics.json` at the commit it names. Check that the coarse
  bullet's causal wording agrees with the fine README's quasi-steady section; that section's sentence
  becomes conditional (design D9) in the same commit as 10.3.
- [ ] 10.6 Mutation-test 10.1 and the section-4 constants test on README copies.
- [ ] 10.7 `docs/CHANGELOG.md`: one Added bullet and one Changed line. Last commit:
  `docs: changelog for the coarse-vs-fine figures (advances #114, #130)`.

## 11. Reconcile, review, merge

- [ ] 11.1 Re-read the proposal, design, deltas and tasks against the code. Update any drift with a
  `### Why N instead of M?` note. File an issue for any workaround. Diff each MODIFIED block against
  its live requirement, so no live scenario is dropped by accident.
- [ ] 11.2 Run `openspec validate --strict`, the full suite and ruff.
- [ ] 11.3 `/review-pr`, then fixes. Each fix commit gets a focused adversarial re-review by
  reproduction.
  - **Any byte change to `comparison_figure.py` or the driver**, a docstring included, triggers the
    re-render rule:
    1. Commit the fix. This commit is red, as designed.
    2. Re-render all three figures into a scratch directory, copy them in, and make one `data(...)`
       commit.
    3. Push the two commits together, never apart.
  - Tell the user if any slides are affected.
- [ ] 11.4 `/pre-merge-check`.
- [ ] 11.5 Grep the PR body and every commit message for closing keywords next to an issue number.
  - Only the PR body says "Closes #114" and "Closes #130", and only if the user approves.
  - It says "advances #131".
  - It notes that the figure sidecars name a commit resolvable via `refs/pull/<n>/head`.
- [ ] 11.6 Run `git merge-base --is-ancestor`. Check that the branch tip is green. **Stop for the
  user's approval before pushing.** Ask about pushing, or a draft PR, before 2026-11-24.

## 12. After merge

- [ ] 12.1 `openspec archive add-real-comparison-figures --yes`, then validate the live specs.
- [ ] 12.2 Add the roadmap row in `docs/force_surrogate/roadmap.md`.
- [ ] 12.3 Clean up the worktree and branch.
