# Tasks

Commits say "advances #124"; only the PR body closes #124 (and says "advances" for #137, which stays
open). Every commit ends with the session's `Co-Authored-By` trailer. Tests come before the code
they test; each red run is recorded (command and failing test names) in its commit message. Red
middle commits are intended: the repo squash-merges and CI judges only the PR head. If `origin/main`
moves, merge it in; never rebase.

## 0. Proposal

- [ ] 0.1 `openspec validate refresh-v3-validation-figure --strict`; `/review-openspec`; reconcile
      every BLOCKING/IMPORTANT finding in `review-reconciliation.md`; user approval.
- [ ] 0.2 Commit the change directory including `review-reconciliation.md`
      (`docs(openspec): propose refresh-v3-validation-figure`).

## 1. Tests first (`tests/test_flapping_wing_validation_figures.py`), commit `test(v3)`

Tests 1.1, 1.1b and 1.5 share one module-scoped fixture that runs `main(out_dir=...)` once in
`tmp_path_factory`. The V3 tests (1.3, 1.3b) render V3 with their own
`fig_v3_scale_invariance(tmp_path)` call under the `plt.close` collector and do not request that
fixture; 1.4 has its own patched run. Comparator, message formats and fixture per `design.md`
D2/D3.

- [ ] 1.0 `test_summary_comparator_rejects_each_kind_of_drift` (parametrized, synthetic dicts nested
      three levels deep like `v3.CF_x.r2_van_veen`, no `main()`): each drift case of the spec
      scenario "The comparison rejects each kind of drift and accepts rounding" yields a message of
      the D2 format for its kind at its dotted path; each accept case yields `[]`.
      **Red:** `_summary_mismatches` does not exist. The helper is test code, written in this same
      commit, so 1.0 is green by 1.6; its red is recorded from the run before the helper existed.
- [ ] 1.1 `test_committed_summary_matches_regeneration`: `_summary_mismatches(committed, fresh) == []`,
      committed read from the module constant `_COMMITTED_SUMMARY = REPO /
      "examples/flapping_wing/figures/validation_figures_summary.json"`; the test asserts
      `_COMMITTED_SUMMARY.is_file()` and that it is not under `tmp_path_factory.getbasetemp()` (no
      self-comparison). **Red (phase 1): value mismatches only**, at `v3.CF_x.r2_before`,
      `v3.CF_x.r2_after` and the `CF_z` pair: the keys are equal on both sides (old generator, old
      summary), so this is the direct proof that the guard fails on the stale values. Record the
      messages.
- [ ] 1.1b `test_stale_v3_values_are_rejected`: the `e600581` summary as a literal with `v3` keys
      renamed and stale values kept. `_summary_mismatches(it, fresh)` contains
      `"v3.CF_x.r2_van_veen: committed 0.9931809360713737 != fresh "` and the `CF_z` equivalent
      (value messages, not key messages); `_v3_source_mismatches(it)` (the 1.2 check, as a helper)
      contains value messages at both paths. **Red:** fresh still has the old keys, so only
      `missing in fresh` messages appear at those paths and the value-message assertion fails.
      Green from 2.3 on, before regeneration.
- [ ] 1.2 `test_committed_v3_r2_matches_parquet_and_metrics`: `_v3_source_mismatches(committed) == []`;
      it reads the committed parquet and `metrics.json` directly (no `main()`), and for `CF_x`, `CF_z`
      compares `r2_van_veen` with `_r2(true, pred)` and with `metrics["per_target"][coef]["r2"]`, and
      `true_mean`/`true_rms`/`pred_mean`/`pred_rms` with numpy recomputations, under the D2 rule.
      **Red:** missing keys (reported as mismatches, not a raw `KeyError`).
- [ ] 1.3 `test_v3_panels_plot_both_normalizations`: render V3 with the `plt.close` collector (D3).
      In this order: (a) the panel titled with the coef and "van Veen" has one scatter whose offsets
      `assert_array_equal` `(true, pred)`; (b) the "peak-tip" panel's equal `(true / k, pred / k)`
      with `k` from `compute_force_reference` and the expression `/ k`; (c) titles carry the R² to
      six decimals from the returned summary; (d) no axes title or suptitle contains "BEFORE" or
      "AFTER"; (e) x labels contain the coef, "lab frame", "on wing"; y labels "surrogate" and the
      coef. **Red:** (a) — the panel labelled van Veen plots the parquet × k.
- [ ] 1.3b `test_v3_peak_tip_panel_matches_raw_forces_on_tip_reference` (D7): merge with
      `validate="one_to_one"`; peak-tip x offsets `== approx(-raw / F_ref_tip(row), rel=1e-12, abs=0)`
      for `CF_x`/`Fx` and `CF_z`/`Fz`; the scale between the panels, `vv_x[m] / pt_x[m]` over rows
      with `pt_x != 0` (k is local to the generator and not in the summary, so it is read from the
      plotted data), `== approx((R_TIP / R_GYRATION) ** 2, rel=1e-15, abs=0)` (measured max 1.4e-16
      relative). Every `pytest.approx` in this change passes `abs=0` explicitly (its default
      `abs=1e-12` would otherwise dominate). **Red:** no panel titled "peak-tip" (the lookup
      assertion). The value check itself is proved by mutants 4.6 and 4.12.
- [ ] 1.4 `test_summary_is_written_with_lf`: monkeypatch `pathlib.Path.write_text` with a wrapper
      that does `kwargs.setdefault("newline", "\r\n")`, records `self`, and calls the original with
      `(self, data, *args, **kwargs)`; run `main(out_dir=tmp_path)`; assert the summary path is among
      the recorded paths (the writer must go through `Path.write_text`, design D5) and
      `b"\r" not in` the summary bytes. **Red on every platform** (CR bytes).
- [ ] 1.5 Update `test_validation_figures_generate_with_tested_numbers`: keep `delta < 1e-9`; assert
      `r2_van_veen`, `r2_peak_tip`, `true_mean`, `true_rms`, `pred_mean`, `pred_rms` are present.
      **Red:** `KeyError: 'r2_van_veen'`.
- [ ] 1.6 Run the file; record the red set (1.1 on values, 1.1b, 1.2, 1.3, 1.3b, 1.4, 1.5; 1.0
      green).
      `uv run ruff check tests/` and `uv run ruff format --check tests/` clean. Commit tests only.

## 2. Generator, commit `fix(v3)`

- [ ] 2.1 `fig_v3_scale_invariance` per `design.md` D1 and D6 (panels, `/ k`, titles, labels,
      suptitle, function docstring, new keys and mean/RMS fields); module docstring line for V3.
- [ ] 2.2 `main`: `Path.write_text(..., newline="\n")`.
- [ ] 2.3 Run: 1.0, 1.1b, 1.3, 1.3b, 1.4, 1.5 green; 1.1 red on keys (`r2_before`/`r2_after`
      committed against `r2_van_veen`/`r2_peak_tip`/mean/RMS fresh); 1.2 red (missing keys in the
      committed summary). Record. `uv run ruff check` and `ruff format --check` on the
      generator file by hand (CI does not lint `examples/flapping_wing/`); do not reformat the
      untouched rest of the file.

## 3. Regenerate, commit `fix(v3): regenerate`

- [ ] 3.1 `uv run python examples/flapping_wing/generate_validation_figures.py` in the worktree.
- [ ] 3.2 Diff every written file against `HEAD` (D5): V1, V2, V4, V5 byte-identical; `v1`, `v2`,
      `v4`, `v5` blocks unchanged; only `V3_scale_invariance.png` and the `v3` block change. Anything
      else: stop and report. Record the result in the commit message.
- [ ] 3.3 Read the regenerated V3 PNG: panel directions, titles, labels and R² legible.
- [ ] 3.4 `uv run pytest -v -m "not gpu"` (whole suite) green; `uv run ruff check src/ tests/
      scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`
      and `uv run ruff format --check` on the same paths, as in `.github/workflows/ci.yml`.
- [ ] 3.5 Under WSL `Ubuntu` (first run `wsl -d Ubuntu -- uv --version` with a 60 s timeout; a hang
      or error counts as unavailable: report and ask, the fallback being CI's own Linux run of the
      PR): `git -C <worktree> archive <sha> | tar -x
      -C ~/v3check` (committed bytes only, no `.venv`); in it `uv sync --frozen --group viz` (as
      `ci.yml`); `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_flapping_wing_validation_figures.py`;
      and a scratch script that runs `main(out_dir=<tmp>)` and prints, per leaf,
      `|fresh − committed| / |committed|` (absolute if `|committed| < 1e-12`) and the maximum.
      Record the maximum in design D2 and the PR. If any value exceeds `1e-12`, stop and report; do
      not loosen the tolerance without the user.

## 4. Mutation tests (no commit)

Scratchpad script; `PYTHONDONTWRITEBYTECODE=1`; in-process `pytest.main` with `mosquito_cfd*` and
test modules purged from `sys.modules`; originals backed up as bytes and restored with
`write_bytes`; no other test run at the same time; `git status --short` empty afterwards. Each mutant
must make the named test fail:

| # | Mutant | Must fail |
|---|---|---|
| 4.1 | committed JSON `v3.CF_x.r2_van_veen` × (1 + 1e-9) | 1.1, 1.2 |
| 4.2 | committed JSON `v2.s_yy` × (1 + 1e-9) | 1.1 |
| 4.3 | committed JSON: drop `v5`; separately, extra key in `v4` | 1.1 (each) |
| 4.4 | committed JSON `v3.CF_z.delta` = `2e-12` | 1.1 |
| 4.5 | `metrics.json` `per_target.CF_z.r2` × (1 + 1e-9) | 1.2 |
| 4.6 | generator: peak-tip panel × k instead of / k | 1.3, 1.3b |
| 4.7 | generator: swap the two panel titles | 1.3 |
| 4.8 | generator: drop `newline="\n"` | 1.4 |
| 4.9 | generator: van Veen panel scaled by k | 1.3 |
| 4.10 | generator: x label without "on wing"; separately y label without "surrogate" | 1.3 |
| 4.11 | generator: `delta = abs(...) + 1e-11` | 1.1 |
| 4.12 | generator: peak-tip panel plots `-y / k`, `-yhat / k` (sign flipped) | 1.3, 1.3b |
| 4.13 | committed holdout parquet `CF_*_true`/`CF_*_pred` × (−1), written in place (saved bytes, restored with `write_bytes`) | 1.1, 1.2, 1.3b |
| 4.13b | same, × 2 | 1.1, 1.2 (mean and RMS) |
| 4.14 | comparator `rel` 1e-12 → 1e-8 | 1.0 (cases `1e-9` relative and `0.5`/`0.5 + 8e-13`) |
| 4.15 | comparator near-zero `abs` → 1e-6 | 1.0 |
| 4.16 | comparator adds `abs=1e-12` on non-zero values | 1.0 (cases `1e-11`/`1.05e-11` and `0.5`/`0.5 + 8e-13`) |
| 4.17 | comparator iterates committed keys only | 1.0 (key present only in fresh; block present only in fresh) |
| 4.18 | comparator recurses one level only | 1.0 (depth-3 case) |
| 4.19 | generator: suptitle contains "BEFORE" | 1.3 |
| 4.20 | generator: k = F_ref(R_TIP) / F_ref(1.5) | 1.3b |

Under 4.17, 4.3's dropped `v5` no longer fails 1.1 (1.1 goes green): this is why the walk must cover
fresh's keys. 1.1b is not a tolerance check: the stale R² differ by 6.3e-4 and 1.3e-2 relative, so no
tolerance mutant can kill it.

Test 1.1 must not become a self-comparison (fresh against fresh), which would let 4.1–4.4 pass.
That is guarded in the test itself, not by a mutant (a mutant of the test could only be detected by
re-running other mutants under it): see 1.1's `_COMMITTED_SUMMARY` and `getbasetemp()` assertions.

Known equivalent mutants, recorded in the PR, not gaps: `r2_van_veen` computed on the `/ k` arrays;
panel titles showing each other's R² (equal to six decimals).

## 5. Docs, commit `docs(v3)`

- [ ] 5.1 `examples/flapping_wing/figures/README.md` V3 row: the van Veen and peak-tip panels, stating
      that the peak-tip panel is the committed coefficients divided by k (today's on-wing,
      hinge-moment coefficients re-expressed on F_ref(R_TIP)), not the pre-#36 corpus;
      `ΔR² < 1e-9`, values in `validation_figures_summary.json`, link to the coordinate-convention
      "Force and moment sign" section; no R² digits.
- [ ] 5.2 `docs/CHANGELOG.md` [Unreleased]: V3 relabel and regeneration, the guard, and
      `**BREAKING:** v3 summary keys r2_before/r2_after → r2_van_veen/r2_peak_tip`.
- [ ] 5.3 Grep docs and specs for the old V3 numbers and "BEFORE/AFTER" (none at `e600581`); run
      `tests/test_t4_stale_claims.py`, `tests/test_coordinate_convention_sign.py`,
      `tests/test_kinematics_attribution.py` and the whole suite.

## 6. Close-out

- [ ] 6.1 Re-read proposal/design/spec against the implementation; record any deviation with a
      "Why N instead of M?" section.
- [ ] 6.2 Comment on #137: items 3–4 done here; items 1–2 open.
- [ ] 6.3 `/review-pr`, adversarial re-review of each fix commit, `/pre-merge-check`. Before the
      push: `git status --short` empty; user approval; then `git push -u origin
      refresh-v3-validation-figure` (the branch's upstream is `origin/main`; never a bare
      `git push`), and verify `git rev-parse --abbrev-ref @{u}`. User approval before opening the PR.
- [ ] 6.4 After merge: archive on a branch off updated `origin/main` (diff live specs first); add
      `docs/force_surrogate/roadmap.md` row 16; ask before pushing; remove worktree and branches.
