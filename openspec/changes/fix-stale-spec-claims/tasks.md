# Tasks

## Conventions

- **Closing keywords.** Commits say "advances #170" / "advances #115". Only the PR body closes them,
  and no negated closing keyword appears anywhere. Every commit ends with the session's
  `Co-Authored-By` trailer.
- **Order and red runs.** Tests come before the text or code they guard. Each red run is recorded in
  its commit message (command and failing test ids). Each commit heading gives its CI state (full
  `-m "not gpu"` suite).
- **Branch hygiene.** If `origin/main` moves, merge it in (never rebase) and re-run the full suite,
  because a merge can bring a delta that touches a guarded requirement. Before any full-suite run:
  `uv sync --frozen --group viz`. Run `openspec validate fix-stale-spec-claims --strict` at every
  commit that touches the change dir (CI does not run it).
- **Windows runs.** Mutation and scratch runs set `PYTHONIOENCODING=utf-8`.
- **Per-test detail** (cases, expected tables, mutants) lives in `design.md` D4–D7. The tasks below
  reference it rather than repeating it.

## 0. Proposal — commit A: `docs(openspec): propose fix-stale-spec-claims` (green)

- [x] 0.1 `openspec validate --strict`; `/review-openspec` rounds until not BLOCKED; every
      BLOCKING/IMPORTANT finding reconciled verbatim in `review-reconciliation.md`; user approval.
      The approval summary tells the user that the bench change's stale "predates them"
      parenthetical is left to that change or the follow-up.
- [x] 0.2 File the follow-up issue (`proposal.md` "Out of scope"). Its first item names the
      owner of the "predates them" fix. Filed as #176.
- [x] 0.3 Overlap check (`design.md` D7): compare every worktree's
      `openspec/changes/*/specs/{force-surrogate,flapping-wing-validation}` requirement names
      against `GUARDED`. Record the result.
- [x] 0.4 Only after approval, commit the change dir, including `review-reconciliation.md`. If
      `GUARDED` names change after 0.3, re-run 0.3 first. Ruff and pytest are unaffected (docs
      only).

## 1. Fixture module — commit B: `test(evidence-figure): move the toy fixture to a shared module` (green)

- [x] 1.1 Create `tests/_evidence_fixture.py` (D6) and import it in
      `test_force_surrogate_evidence_figure.py`. Replace every `rows_per_wingbeat=2000` there that
      means the fixture's rows (lines 387-388, 403-404, 443, 1343, 1378, 1380, 1402-1406).
      Behaviour-preserving: record that file's test count and results before and after.

## 2. Effective-spec helper — commit C: `test(specs): effective-spec builder, tokenizer and formatter` (green)

- [x] 2.1 Unit tests first in `tests/test_live_spec_claims.py`, all synthetic (`tmp_path` or
      strings), covering every case listed in `design.md` D3 and D4:
      - `requirement_blocks` (CRLF, unknown `## ` section);
      - `effective_spec` / `effective_text` / `effective_block` (replace/drop/append, `archive/`,
        non-directory entries, other capabilities, each raise case, the two-change cases, default
        paths resolved at call time from the module attributes);
      - `number_tokens` (D4 cases plus `"x ３ y" → []`);
      - `format_like` (D4 cases plus `(3.0607e-4, "3.06e-4")` and `(2.5, "2")`).

      **Red:** import error (module absent). Record it.
- [x] 2.2 Implement `tests/_spec_claims.py` (D3, D4: `requirement_blocks`, `effective_spec`,
      `effective_text`, `effective_block`, `number_tokens`, `format_like`, `check_block`,
      `retired_hits`), with UTF-8 reads throughout. 2.1 goes green.

## 3. Spec guard — commit D: `test(specs): guard live-spec claims against committed data (advances #115)` (green)

- [x] 3.1 Add the four stale fixtures (D7), then `git ls-files` them.
- [x] 3.2 Write `RETIRED`, `RETIRED_EXAMPLES` (one list per pattern, as string literals), `MUST_PASS`,
      `GUARDED` and `REGISTRY`, then the tests:
      - `test_retired_patterns_match_their_examples`: `set(RETIRED_EXAMPLES) == set(RETIRED)`. Every
        example matches its pattern; code examples are checked through `normalize(python_prose())`.
      - `test_retired_patterns_accept_the_corrective_text`.
      - `test_stale_fixtures_trip_the_guard`:
        - every pattern hits at least one fixture;
        - the (block, pattern) sites are reported;
        - the (block, token, count) table in D7 is reported, as a superset check.
      - `test_no_retired_claim_in_live_specs` (per capability; anchor first).
      - `test_guarded_requirement_numbers_are_registered` (per `GUARDED` name). A missing name fails
        with "update GUARDED/REGISTRY".
      - The synthetic must-fail tests in D7 (including the superscript case), plus one where a
        registered number is duplicated in the text.
- [x] 3.3 **Red record.** Run a scratch `conftest.py` (quoted in the commit message) that
      monkeypatches `_spec_claims.CHANGES_DIR` to an empty `tmp_path`, so the effective text is the
      `c87e39c` live spec. Expected:
      - `test_no_retired_claim_in_live_specs` fails for both capabilities;
      - the registry check fails for every guarded MODIFIED requirement except "Config-resolved…",
        whose stale claim is a word (tripwire only);
      - the three ADDED requirements fail with "update GUARDED/REGISTRY".

      The normal run is green.

## 4. Code prose — commit E1: `docs(force-surrogate): docstrings no longer equate parallelism with batch size or call config_mean_r2 central (advances #115)` (green)

- [x] 4.1 Test first: `test_no_retired_claim_in_code_prose` for `evidence_figure.py` and
      `train.py` (anchors, `retired_hits` on `python_prose`). **Red:** both files. Record.
- [x] 4.2 Fix the `compute_speedup` and `compute_config_resolved` docstrings, and the
      `SYMMETRY_RATIO_TOLERANCE` comment (D2 magnitudes, "materially-truncated", the 6 other
      affected configs).
      Green.

## 5. Kinematics — commit E2: `test(kinematics): call t = T/4 stroke reversal and pin the mid-stroke span-tip (advances #115)` (green)

- [x] 5.1 Test first: extend `test_no_retired_claim_in_code_prose` to `tests/test_wing_kinematics.py`
      (prose and raw names), and add `test_renamed_reversal_test_exists` (ast). **Red:** both.
      Record.
- [x] 5.2 Rename the Euler-angle test and fix its docstring (D6). Green.
- [x] 5.3 Add `test_old_span_tip_is_off_axis_at_mid_stroke` (full vectors, D6). It is green on first
      run. Record that it fails under the mutant that swaps `rotation_matrix` and
      `rotation_matrix_legacy` in that test, and that the distance-only assertion survives that
      mutant.

## 6. #170 test — commit F: `test(force-surrogate): rescale the committed holdout new→old (advances #170)` (green)

- [x] 6.1 Change only the RMSE assertion to `rmse_old == pytest.approx(rmse_committed / _K,
      rel=1e-9, abs=0)` while the scaling is still `* _K`. **Red:** both parametrizations, off by
      `k²`. Record.
- [x] 6.2 Test first: `test_committed_holdout_over_k_is_on_the_peak_tip_reference` (D1). Record that
      it is green, and that it fails under the mutant that divides `f_ref(R_GYRATION)` instead of
      `f_ref(R_TIP)`.
- [x] 6.3 Make the D1 edits:
      - rescale by `/ _K`;
      - add the MAE assertion;
      - rename the locals;
      - `assert f"{_K:.3f}" == "3.120"`;
      - the module comment at `:34`;
      - the docstrings: new convention since #36; `/ k` re-expresses on the peak-tip reference,
        normalization only, not the pre-#36 corpus, and V3 parity.

      Green.

## 7. Speedup and gate tests — commit G: `test(force-surrogate): parallelism is measured, not N; an in-tolerance CFL-limited config fails the gate (advances #115)` (green)

- [x] 7.1 Probe first: build the 7.3 corpus and confirm its precondition holds, before opening the
      commit.
- [x] 7.2 Add the `parallelism_factor != batch_size` assertion. Green on first run; it kills no new
      mutant (D6). Record that.
- [x] 7.3 Add `test_cfl_limited_config_with_nonzero_in_tolerance_ratio_fails` (D6). Green on first
      run. Record that it fails under the mutant that drops `realized.get('min')`. If the
      precondition cannot be met, that is a finding: stop and report rather than change `src/`.

## 8. Docs — commit H: `docs(changelog): stale spec claims and the live-spec guard (advances #170, advances #115)` (green)

- [x] 8.1 `docs/CHANGELOG.md` [Unreleased], nested bullets in the existing style:
      - Changed: the force-surrogate and flapping-wing-validation specs no longer state corpus
        results (speedups, ratios, run figures); the numbers that remain in the modified
        requirements are guarded.
      - Fixed: the #170 wording and test direction; the #115 claims; the docstrings.
      - Added: the live-spec guard (covers the 10 modified and added requirements; follow-up issue
        for the rest).

      Quote no retired literal (`_stale_claims` scans the CHANGELOG). Run
      `tests/test_t4_stale_claims.py` afterwards. If 9.1 later changes what the entry should say,
      add a follow-on commit; do not rewrite H.

## 9. Verification

- [x] 9.1 Mutation testing (D7 runner). Each mutant must turn at least one named test red:
      - **effective-spec:**
        - deltas ignored;
        - MODIFIED appends instead of replacing;
        - REMOVED ignored;
        - `archive/` not skipped;
        - ADDED-duplicate raise removed;
        - RENAMED raise removed;
        - absent-name raise removed;
        - two-variant raise removed from `effective_block`;
        - unknown-section handling removed;
        - non-directory skip removed.
      - **tokenizer:**
        - decimals dropped;
        - comma groups dropped;
        - e-notation dropped;
        - `x`-join split removed;
        - `CC-` strip removed;
        - `re.ASCII` removed (killed by the `３` case);
        - superscript check removed (killed by the superscript must-fail test).
      - **registry:**
        - multiset becomes set (killed by the duplicated-number test);
        - multiset becomes subset;
        - phrase check removed;
        - recompute skipped;
        - fixture check skipped;
        - `format_like` rounds one fewer digit;
        - whitespace collapse removed.
      - **tripwire:**
        - each `RETIRED` pattern dropped in turn (killed by the stale-fixture hit test, not only by
          the set-equality bookkeeping);
        - anchor check removed;
        - prose check reads names only;
        - names check removed.
      - **#170:**
        - RMSE divisor reverted to `*`;
        - MAE divisor reverted to `*`;
        - peak-tip test using `R_GYRATION`.
      - **Kinematics:** rotation functions swapped in the mid-stroke test.
      - **Gate:** `realized.get('min')` dropped.

      Record mutant → killing test in the PR body; kill or justify survivors.
- [x] 9.2 `uv run ruff check . && uv run ruff format --check .`; `uv run pytest -v -m "not gpu"`.
- [x] 9.3 Archive dry-run in a throwaway worktree at the branch head (D7), then remove the worktree.
- [x] 9.4 Re-read the proposal, design, deltas and tasks against the implementation (new-feature
      step 9). Record any deviation as `### Why N instead of M?` in `design.md`, in its own commit
      (`docs(openspec): record implementation deviations`).
- [x] 9.5 `/review-pr`; adversarial re-review of every fix commit; `/pre-merge-check`.
- [ ] 9.6 Before pushing:
      - re-run the 0.3 overlap check;
      - `git log origin/main..HEAD --format=%B | grep -iE '\b(close[sd]?|fix(e[sd])?|resolve[sd]?):? +#[0-9]'`
        must print nothing;
      - ask the user, then `git push -u origin fix-stale-spec-claims`;
      - ask again before opening the PR.

      The PR body:
      - "Closes #170";
      - for #115, the keyword the user chose at approval (Closes, with the follow-up issue named as
        inheriting the remainder, or Advances);
      - the mutant table and the red-run record;
      - the "predates them" note (D2).

## 10. After merge (user merges)

- [ ] 10.1 Branch off updated `origin/main`.
      - Diff `openspec/specs/{force-surrogate,flapping-wing-validation}/spec.md` between `c87e39c`
        and `origin/main`; if a guarded requirement changed, hand-merge it rather than let the
        archive overwrite it.
      - Re-run the overlap check.
      - Run `openspec archive fix-stale-spec-claims` (one commit), then the guard and
        `openspec validate`.
      - Ask the user which route to use (PR, or direct push to main as for `9b3b43a`) before
        pushing.
- [ ] 10.2 Roadmap row in `docs/force_surrogate/roadmap.md`, in a separate commit in the format of
      `c87e39c`:
      - use the next free row number (17 today; re-check, since other sessions may take it) and
        update "rows 7-N followed";
      - record that the guard covers the 10 requirements only, and link the follow-up issue.
- [ ] 10.3 Close-out.
      - Confirm the follow-up issue is open and linked.
      - Remove the worktree and branches. Before force-deleting the squash-merged branch, verify
        its tree matches the merge commit.
