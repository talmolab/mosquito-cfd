# Tasks

## Conventions

- **Test first.** Every implementation task names the test written **first** and the behaviour it
  pins; record red before and green after.
- **Mutation testing.** Every new guard is mutation-tested on a saved-bytes copy of the file under
  test. Restore from those bytes, never with `git checkout`. Record the kill count on the task.
- **Test paths.** Anchor test paths at `Path(__file__)`. CI checks out at depth 1, so no test reads
  git history. Build `CORPORA` and parametrize ids from literals; no file is read at collection time.
- **Wording.** New assertions say "phase-only baseline", never bare "baseline".
- **uv.** Every `uv` call on both hosts uses `--frozen`; WSL calls also pass `--group train`.
  `git diff --exit-code uv.lock` runs before each commit C1–C6.
- **Scripts and subprocesses.** Scripts used in tests run via `sys.executable` or
  `spec_from_file_location`, never via `uv`. Error-message matches use `re.escape(path.name)`.

## Commit plan

Nothing is pushed until task 24.

| Commit | Content | State |
|---|---|---|
| C0 `docs(openspec): propose add-fine-corpus-surrogate` | `openspec/changes/add-fine-corpus-surrogate/**` | green |
| C1 `feat(force-surrogate): median fine-grid CFD cost from run metadata` | §1 | green |
| C2 `feat(force-surrogate): grid-aware evidence figure (coarse output unchanged)` | §2 | green |
| C3 `test(force-surrogate): parametrize committed-artifact guards over both corpora` | §4; fine params strict-xfail with `raises=` | green (listed XFAILs) |
| — | **C1–C3 frozen from task 12 on** (design D8) | |
| C4 `data(force-surrogate): train the surrogate on the fine corpus` | §5 artifacts; the C4 xfail set removed | green (listed XFAILs) |
| C4′ (only if needed) | figure-code fix as a new commit; figure regenerated at C4′ | green |
| C5 `data(force-surrogate): fine evidence figure and README` | §6, every xfail removed | green, full suite incl. gpu |
| C6 `docs: roadmap row 14, CHANGELOG, stale fine-surrogate references; reconcile and check off tasks` | §7 | green |
| (post-merge archive commit) | roadmap row 14 → ✅; tasks 24–25 checked | — |

Run notes (measured numbers, gate outcomes) live in the scratchpad until C5 exists, so the tree is
clean whenever an artifact is generated. tasks.md is checked off in C6 (tasks 0–23) and in the archive
commit (tasks 24–25).

## 0. Blast radius

0. [x] Record the committed tests this change is expected to touch. **Any test outside this list
   that needs editing halts the change for a decision.**
   - `tests/test_force_surrogate_evidence_figure.py`:
     - `test_build_caption_discloses_everything` and `test_cli_delegates_to_library` (new kwargs);
     - the README and committed-artifact tests `test_readme_carries_full_disclosures`,
       `test_readme_config_resolved_r2_matches_committed_metrics`,
       `test_readme_throughput_figures_match_the_committed_sidecar` and
       `test_committed_figure_metrics_matches_committed_inputs` (parametrized per design D6, coarse
       assertions kept literally);
     - new grid-profile, formatter and sidecar-regeneration tests.
   - `tests/test_committed_surrogate_provenance.py`:
     - every test except the two `seed_variation` ones, parametrized per D6;
     - `test_skill_and_config_r2_table_patterns_cannot_cross_match` extended;
     - new settings test.
   - New: `tests/test_force_surrogate_cfd_cost.py`.
   - `tests/test_no_false_diffused_ib_claim.py` must stay green untouched: it asserts the roadmap's
     "2.4 min", so task 21 must not delete that string.

## 1. Fine CFD cost helper (design D3), C1

1. [x] **Test first** (`tests/test_force_surrogate_cfd_cost.py`, tmp_path, torch-free):
   - **Known answers:**
     - (300, 2), (400, 2), (1000, 2) → 200.0, n=3, min 150.0, max 500.0, independent of input order;
     - a single file (3999, 1.9995) → exactly `3999 / 1.9995`;
     - an even count → the mean of the middle two;
     - `gpu_model` is echoed.
   - **`ValueError`**, matched with `re.escape(path.name)`, for:
     - no paths (message: none given);
     - a missing `config`, or a missing `gpu_model`;
     - `wall_time_s` and `cycles_completed` each as: missing, `None`, `True`, `"300"`, 0, −1, NaN,
       inf;
     - a duplicate `config`;
     - two GPU models.
   - **Script:** `scripts/cfd_seconds_per_step.py --metadata-dir <tmp>` (via `sys.executable`)
     prints a value with `float(stdout.strip()) == helper(...)`, with a corpus-level
     `run_metadata.json` lacking `timing` present in the directory.
2. [x] Implement `src/mosquito_cfd/force_surrogate/cfd_cost.py` and the script (Google docstrings).
   Mutation-test task 1:
   - remove each validation branch;
   - median → mean;
   - `round(cycles)`;
   - glob widened to `run_metadata*.json`;
   - bool accepted.

   Record kills. Ruff check + format. Commit C1.

## 2. Grid-aware evidence figure (design D2), C2

3. [x] **Test first** (`tests/test_force_surrogate_evidence_figure.py`, toy fixtures):
   - **Coarse caption:**
     - the default (`grid` omitted) caption equals the `grid="coarse"` caption;
     - it contains verbatim "sequential coarse-grid A40 CFD", "Coarse 64x32x64 grid: pipeline
       readiness, not validated aerodynamics.", "coarse-grid CFD lift", "at this resolution" and
       "examples/prelim_sweep/README.md".
   - **Fine caption:**
     - `grid="fine"` contains verbatim "fine-grid A40 CFD at its median per-wingbeat wall time", the
       fine caveat (design D2 table), "fine-grid CFD lift" and
       "examples/prelim_sweep_fine/README.md";
     - it contains **no** "coarse", "64x32x64", "pipeline readiness" or "at this resolution".
   - **Sidecar note:** `_baseline_reference(..., grid="fine")["note"]` names the fine-grid lift; the
     coarse note is byte-unchanged.
   - **Speedup:** `compute_speedup(inference, 2000, cfd_seconds_per_wingbeat=4000.0)` gives the known
     answer `throughput / (2000/4000)` and the latency known answer; the default equals 144.
   - **Rejected before any file is written** (`ValueError`, and `out_dir` empty or absent):
     - `generate_evidence_figure(grid="fine")` without seconds, and with 0, −1, NaN and inf;
     - `grid="coarse"` with 4375.0;
     - `grid="medium"` (message lists `coarse` and `fine`).
   - **Fine run artifacts:**
     - the sidecar key set equals the coarse key set;
     - `speedup.cfd_seconds_per_wingbeat` equals the value passed;
     - the figure `run_metadata.json` has `grid == "fine"` and the same seconds;
     - a default run records `grid == "coarse"`, 144.0.
   - **Formatter:** `format_power_of_ten` on 3.76e6 → `≈3.8×10⁶×`, 1.14e8 → `≈1.1×10⁸×`,
     9.96e5 → `≈1.0×10⁶×`.
   - **CLI:**
     - `--grid fine --cfd-seconds-per-wingbeat 4375.0` reaches the library;
     - `--grid` defaults to `coarse`;
     - `--grid medium` is rejected by argparse.
   - **`test_committed_sidecar_regenerates_from_committed_inputs[coarse]`** (design D2, CI half):
     parsed-JSON equal; exact except `approx(rel=1e-12)` on the two QS RMS values.
4. [x] Implement `GridProfile`/`GRID_PROFILES` and `format_power_of_ten`, and thread `grid` /
   `cfd_seconds_per_wingbeat` through `build_caption`, `build_figure`, `_baseline_reference`,
   `compute_speedup`, `generate_evidence_figure` and `scripts/make_evidence_figure.py`, keeping the
   "compute everything first, then write" order.
   - Docstrings in `train.py`/`train_surrogate.py` stop implying the coarse corpus only.
   - Mutation-test task 3, recording kills:
     - swap each profile field;
     - drop the fine-`None` check, the finite/positive check, and the coarse-must-be-144 check;
     - hard-code 144;
     - off-by-one exponent in the formatter.
   - Ruff. `git diff --exit-code uv.lock`. Commit C2.

## 3. Coarse no-op gate, manual PNG half (design D2): after C2, before C3 is committed

5. [x] On the Windows host:
   - `git worktree add --detach <scratchpad>/main-dada8f0 dada8f0`.
   - In each worktree's own root, `uv sync --frozen --group viz` (each its own `.venv`).
   - Record in each env:
     - `evidence_figure.__file__` (must lie inside that worktree);
     - `hasattr(ef, "GRID_PROFILES")` (False for main, True for C2);
     - `uv pip freeze --exclude-editable` (must be identical);
     - `matplotlib.__version__`.
   - Any precondition failure halts.
6. [x] Generate the coarse figure from each into `<scratch>/a` (main) and `<scratch>/b` (C2), with
   `uv run --frozen --group viz python scripts/make_evidence_figure.py` from that worktree's root, the
   committed coarse digest and the committed coarse timestamp.
   - **Hard gate:** `cmp` a/b PNG and sidecar, and `cmp` a against the committed coarse PNG and
     sidecar. Any mismatch **halts** for a decision.
   - If a code fix is needed, it amends C2 (allowed only before C3 exists) and the gate is rerun.
   - Remove the temporary worktree (`git worktree remove`). Nothing under `examples/prelim_sweep/`
     changes.

## 4. Committed-artifact guards over both corpora (design D6), C3

7. [x] **Test first: pure guard helpers**, tested on synthetic inputs built from the coarse
   `metrics.json` plus hand-written README text. Each helper passes on a correct case and fails on the
   listed defects.
   - **`check_skill_table`:** perturbed cell; missing row.
   - **`check_cycle_mean_table`:** range off by 0.01; missing row.
   - **`check_comparison_table`:**
     - flipped overlap cell;
     - range off by 0.001;
     - missing row;
     - `null` range not shown as `n/a`;
     - touching ranges marked `no`;
     - a "higher on fine" sentence for a target whose cell is `yes`;
     - a sentence using "improves", "drop" or "shift" (other than "no shift detected").
   - **`check_fine_disclosures`:** each required string removed in turn; a `2.4×` or "pitch moment"
     added.
   - **`check_quoted_in_source`:** a quoted "3.7 %" that is absent from the cited file.
   - **`check_fine_qs_disclosure`:** the README ratio differs from the sidecar's `overshoot_factor`;
     any of "uncalibrated", "translational-only", "symmetric-rotation", "stroke-plane-normal",
     "lab-z", "not overlaid" is missing.
   - **`check_fine_denominator`:** the stated seconds differ from the sidecar rounded; a `×` ratio
     sentence between the two denominators is present.
   - **All helpers:** on README text with no table at all (today's fine README), they raise
     `AssertionError`, not `AttributeError`/`KeyError`/`IndexError`.
8. [x] **Test first: parametrize the §0 tests over `CORPORA`**, keeping every coarse assertion
   literally:
   - the `≈3.8×10⁶×` string;
   - `batch_size == 12535`;
   - `latency_speedup < 1000`, `"2.4" not in readme` and `_QUOTED_TARGETS` stay coarse-only;
   - the fine config-R² prose half becomes `_R2_NEAR_TARGET.findall(fine_readme) == []`, placed
     **after** the positive `check_cycle_mean_table` call in the same test, so it cannot XPASS at C3/C4.

   Add:
   - `test_surrogate_trained_with_the_coarse_settings` (both corpora);
   - `test_committed_sidecar_regenerates_from_committed_inputs[fine]`;
   - the fine-only tests calling the §7 helpers on the real files;
   - the cost-median-equals-sidecar test (27 configs);
   - fine figure `run_metadata` `grid`/seconds;
   - the cross-match test extended to all four table patterns and headers.

   Negative README checks share a test function with a positive one.
9. [x] Mark every fine parametrization and fine-only test
   `xfail(strict=True, raises=(FileNotFoundError, AssertionError), reason="#110: fine artifacts land in C4/C5")`.
   - Do not mark the existing `fine-corpus` record param or the cross-match test.
   - Record the XFAIL node-ID list and pre-register the C4 subset (design D6).
   - `uv sync --frozen --group viz && uv run --frozen pytest -m "not gpu"` from Git Bash: green, and
     the XFAIL set equals the list.
   - Mutation-test the §8 parametrizations on saved-bytes copies of the coarse committed JSON/README,
     and record kills.
   - Ruff. `git diff --exit-code uv.lock`. Commit C3. `git status --porcelain` empty.

## 4b. Pre-GPU code review and the per-step CFD cost (before task 10)

9a. [x] `/code-review` (high) of C1–C3: 10 findings. Fix 9 (one, the duplicated speedup/QS
    computation in `generate_evidence_figure`, predates this change and is left), each fix
    confirmed by reverting it as a mutation (10/10). Commit `58ee8fb`.
9b. [x] At the pre-GPU checkpoint the user chose a **per-step** fine CFD cost (review finding: the
    per-wingbeat median pooled f* levels). Tests first: `median_cfd_seconds_per_step`, `--grid fine
    --cfd-seconds-per-step`, `cfd_seconds_per_wingbeat = s × representative rows`, figure
    `run_metadata` `cfd_seconds_per_step`, README states "x.xx s per step". Mutation-test
    (21/21). Re-check the coarse PNG and sidecar byte-identical. Update proposal (`Why N instead
    of M?`), design D2/D3, spec. Commit before the GPU run.

## 5. Fine training, OPERATOR-RUN (WSL2 + local A5000), NOT CI-GATED, C4

> **Human checkpoint before the GPU run.** First run a local code review of C1–C3 (`/code-review`)
> so that no code fix is needed after artifacts exist.

10. [x] **Pre-flight** in WSL (`wsl -e bash -c`, non-login; `PATH=$HOME/.local/bin:$PATH`), from the
    worktree root, in **every** command or copied script:
    - `export UV_PROJECT_ENVIRONMENT=$HOME/.venvs/mosquito-cfd-train`, then
      `uv sync --frozen --group train`;
    - `test ! -e .venv/bin`;
    - `git --git-dir=<worktree gitdir> status --porcelain` is empty;
    - HEAD == C3;
    - `get_git_info()` reports C3, `dirty: false`, branch `add-fine-corpus-surrogate` (never export
      `GIT_DIR`/`GIT_WORK_TREE`);
    - `CUBLAS_WORKSPACE_CONFIG` unset;
    - the digest comes from `examples/prelim_sweep_fine/run_metadata.json`.

    Scripts are written with the Write tool and copied to `~` with `tr -d '\r'`.
11. [x] Run design D1's command twice, into `$HOME/mosquito-cfd-110/run1/surrogate` and
    `.../run2/surrogate` (ext4; not `/tmp`), with the same timestamp.
12. [x] **Pre-registered gate (design D4 a–c).** Any failure **halts**; nothing is loosened; nothing
    is copied into the repo. From here on, C1–C3 are frozen (design D8).
13. [x] **WSL torch tier:** `uv run --frozen --group train pytest
    tests/test_force_surrogate_train.py tests/test_force_surrogate_train_gpu.py -rs`.
    - Require 0 skipped in `test_force_surrogate_train_gpu.py`.
    - The only allowed failures are the two #129 tests in `tests/test_force_surrogate_train.py`:
      `test_provenance_cpu_tier_digest_timestamp_seeds` and
      `test_run_training_raises_clearly_when_all_holdout_startup_only`.
    - `git diff --exit-code uv.lock`.
    - Record the fine skill per target (plotted seed + range) in the scratchpad.
14. [x] **Human checkpoint before committing binaries.** Report measured blob sizes, then:
    - copy run1's four files into `examples/prelim_sweep_fine/surrogate/`;
    - `git ls-files` shows all four tracked;
    - remove the pre-registered C4 xfail markers (and only those);
    - `uv run --frozen pytest -m "not gpu"` shows the remaining XFAIL set;
    - commit C4, with that list in the message (naming #110 without a closing keyword).

## 6. Fine figure and README, C5

15. [x] Preconditions: `git status --porcelain` empty, and HEAD == C4 (or C4′).
    - `uv run --frozen python scripts/cfd_seconds_per_step.py --metadata-dir examples/prelim_sweep_fine`
      gives `S`.
    - Generate the figure into a scratch dir:
      `uv run --frozen --group viz python scripts/make_evidence_figure.py --predictions
      examples/prelim_sweep_fine/surrogate/holdout_predictions.parquet --metrics
      examples/prelim_sweep_fine/surrogate/metrics.json --grid fine --cfd-seconds-per-step S
      --docker-digest <fine digest> --timestamp <utc> --out-dir <scratch>`.
    - Inspect the PNG visually: caption legible, no clipped text, fine caveat present.
    - Copy it in; `git ls-files` shows the three figure files tracked once added. This happens
      **before** any README edit.
16. [x] Fine README per design D5:
    - replace "Not yet built";
    - extend "What's here";
    - write the seven sections;
    - take every run-derived number from the committed JSON, and every fixed number verbatim from its
      cited source.
17. [x] Remove every remaining xfail marker. Mutation-test the fine guards on saved-bytes copies of
    the fine JSON/README, and record kills:
    - flip an overlap cell;
    - perturb a range;
    - drop a disclosure;
    - change the sidecar seconds;
    - add `CF_z ≈0.5` prose.
18. [x] **One PNG only.** Run the full suite before committing:
    - ruff check + format check over the CI paths;
    - `uv sync --frozen --group viz && uv run --frozen pytest -m "not gpu"` from Git Bash (no XFAIL
      left);
    - the WSL torch tier (task 13 criteria);
    - `git diff --exit-code uv.lock`.

    Commit C5. A figure-code change before the push becomes C4′ plus regeneration, redoing C5 as in
    design D8; a trainer-path change returns to §5.

## 7. Docs, reconcile, ship, C6

19. [x] `docs/force_surrogate/roadmap.md`, with no skill numbers in any of the edits:
    - **Row 14:** replace "*(not yet proposed)*" with `add-fine-corpus-surrogate`, status 🟡, pointing
      to `examples/prelim_sweep_fine/surrogate/metrics.json` and the fine README.
    - **Hardware section:** add a pointer to the fine README for the fine-grid CFD cost (no number).
      Keep "2.4 min".
    - **Grid-resolution finding:** one sentence pointing to the fine README's coarse-vs-fine table.
20. [x] Repoint the stale "fine surrogate does not exist yet" text to the follow-up issue:
    - `openspec/project.md` Pending (the `coarse_vs_fine_comparison.png` item);
    - `tests/fixtures/comparison_figure/README.md` (:8–12, :65–74);
    - flag, but do not fix, the other stale `project.md` lines in the follow-up issue.
21. [x] File the follow-up issue. It references #110 without any closing keyword and covers:
    - rethinking `make_comparison_figure.py`, which plots config-resolved R² that #127 moved off
      figures;
    - the coarse README's QS paragraph ("needs a finer, IB-bias-free grid");
    - the stale `project.md` lines;
    - recording python/numpy/pandas/pyarrow versions in training metadata.

    `docs/CHANGELOG.md`:
    - the D4 and no-op gate outcomes, worded as observed outcomes, not bitwise claims;
    - the recorded commits, reachable via `refs/pull/<N>/head` after the squash;
    - no skill numbers.

    Then `openspec validate add-fine-corpus-surrogate --strict`.
22. [x] Reconcile proposal, design, spec and tasks against the implementation. Record any deviation
    under `### Why N instead of M?` in the proposal, and file an issue for any workaround.
    - **Provenance check:** run `git diff --quiet <recorded commit> HEAD -- <scope>` for each of the
      two scopes in design D8:
      - surrogate record vs the trainer-path scope (non-empty → back to §5);
      - figure record vs the figure scope (non-empty → regenerate the figure only, per D8).
23. [x] Recompute every number in the fine README and CHANGELOG with a script
    (`PYTHONIOENCODING=utf-8`): from the committed JSON, or from the cited source file.
    - A fresh reviewer agent reviews the artifact and docs commits (C4–C6) and the C1–C3 code diff.
    - Check off tasks 0–23. Commit C6.
24. [x] **Human checkpoint before pushing.** Run `/pre-merge-check`. Then:
    - `git rev-list --objects origin/main..HEAD` shows one blob per new binary path.
    - Open the PR to `main`:
      - "Closes #110." on its own line;
      - out-of-scope issues (#115, #124, #102, #101, #129) named without any keyword;
      - blob sizes and both gate outcomes reported.
    - Write the squash message by hand **and** post it as a PR comment, for pasting at merge.
    - Post-push figure-code fixes follow the proposal's policy (BLOCKING only → second PNG, reported).

    *Done as PR #132 (squash `28c82f1`, 2026-10-28). CI green; no post-push review findings, so no
    second PNG. The hand-written squash message was posted as a PR comment, but the merge used
    GitHub's default body. Follow-ups: #130, #131.*
25. [x] After merge (human checkpoint): run `/cleanup-merged`, including the OpenSpec archive. In the
    archive commit, flip roadmap row 14 to ✅ and check off tasks 24–25.
