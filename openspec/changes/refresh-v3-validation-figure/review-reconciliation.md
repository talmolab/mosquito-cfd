# Review reconciliation: refresh-v3-validation-figure

## Round 1 (2026-11-18): BLOCKED

Reviewers: 1 sonnet, 2 opus, 3 skipped (no CI, Docker, dependency or packaging change), 4 sonnet,
5 sonnet, 6 opus. Findings are quoted verbatim (trimmed to the finding's own sentences); locations
are in the revised files.

### BLOCKING

**R1-B1 (TDD).** "The binding rule is met in letter only: both guards go red because a key is
missing, never because a value is stale. [...] Add as task 1.1b (and run it again at 2.3):
`test_summary_guard_flags_the_stale_v3_values`: take the committed summary at `e600581` with only the
keys renamed [...] and the stale values kept. Assert the whole-summary comparator raises [...]
matching `v3\.CF_x\.r2_van_veen` against a fresh `main()` summary. Assert the source check from 1.2
raises against the same dict for CF_x and CF_z. [...] Factor 1.1's comparison into a helper
[...] Factor 1.2's check into `_assert_v3_matches_sources(summary: dict)`."

- Addressed: tasks.md:30 (1.1b `test_stale_v3_values_are_rejected`, stale literal, both helpers
  named, green from 2.3 before regeneration, tasks.md:65); spec.md:32 (scenario "The stale V3 values
  are rejected").
- Deviation, not substitution: the helpers return a list of mismatch messages
  (`_summary_mismatches`, `_v3_source_mismatches`) instead of raising, so one run reports every
  mismatch (the same reviewer's S3). The test asserts the list names `v3.CF_x.r2_van_veen` and
  `v3.CF_z.r2_van_veen`, which is the reviewer's `match` check.

**R1-B2 (TDD).** "The comparator has no tests of its own, and its zero-tolerance branch is never
exercised. [...] Add as task 1.0, written before 1.1 and red first because the helper does not exist
yet: `test_summary_comparator_rejects_each_kind_of_drift` (parametrized, synthetic dicts, no
`main()`). Each case must raise, with `match` on the dotted key path: (a) missing nested key `a.b`;
(b) extra nested key; (c) missing top-level block; (d) non-zero value off by 1e-9 relative; (e)
committed `1e-15` vs fresh `2e-15`, which must fail (no absolute floor on non-zero values); (f)
committed `0.0` vs fresh `2e-12`, which must fail; (g) committed `0.0` vs fresh `5e-13`, which must
pass; (h) a non-number (str or bool) that differs, compared with `==`; (i) a value that is a dict on
one side and a number on the other. In addition, two identical dicts must pass."

- Addressed: tasks.md:21 (1.0); spec.md:39 (scenario listing every case); design.md:46 (D2).
- Case (e) changed from `1e-15`/`2e-15`, because under R1-I8 below a committed value with magnitude
  below `1e-12` is compared absolutely, so `1e-15` vs `2e-15` would pass by design. Round 1 replaced
  it with `1e-11`/`2e-11`, which round 2 showed does not test the property (R2-B2); the cases are now
  `1e-11` vs `1.05e-11` and `0.5` vs `0.5 + 8e-13` (gaps below any `1e-12` floor). NaN cases added
  (spec S3).

### IMPORTANT

**R1-I1 (TDD I1, Spec S2).** "The LF test (1.4) is red only on Windows, so CI can never catch a
dropped `newline="\n"`. [...] monkeypatch `pathlib.Path.write_text` with a wrapper that calls the
original with `newline=kwargs.get("newline", "\r\n")`, so it behaves like Windows on every OS. [...]
Add to the spec or design that the writer uses `Path.write_text(..., newline="\n")`."
- Addressed: tasks.md:51-52 (the exact wrapper); spec.md:53 (scenario "even where the platform
  default is CRLF"); design.md D5 and proposal.md "What changes" name `Path.write_text(...,
  newline="\n")`.

**R1-I2 (TDD).** "The full CI command set is missing from the verification checklist. [...] `uv run
pytest -v -m "not gpu"` [...] `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/
examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`; `uv run ruff format --check` on the
same paths. Also run `ruff check examples/flapping_wing/generate_validation_figures.py` by hand."
- Addressed: tasks.md:77 (3.4, the CI paths verbatim); tasks.md:65 (2.3, generator by hand);
  tasks.md:57 (1.6, tests).

**R1-I3 (TDD).** "Mutants are missing for the comparator and parts of the figure test. Add to
section 4: 4.11 Comparator `rel` 1e-12 → 1e-8 [...] 4.12 [...] zero-branch `abs` → 1e-6 [...] 4.13
[...] adds `abs=1e-12` on non-zero values [...] 4.14 [...] drops the extra-key check [...] 4.15 [...]
recurses only one level deep [...] 4.16 Generator `delta = abs(...) + 1e-11` [...] 4.17 Generator
scales the van Veen (right) panel [...] 4.18 [...] x label without "on wing" or "lab frame", or y
label without "surrogate" [...] 4.19 Test 1.1 reads the summary from `tmp_path` instead of the
committed path [...] 4.20 Panel titles show each other's R²: equivalent mutant."
- Addressed: tasks.md table rows 4.9-4.18 (renumbered: 4.14-4.18 comparator, 4.11 delta, 4.9 van
  Veen panel scaled, 4.10 labels); the equivalent mutant is recorded below the table.
- 4.19 is handled in the test, not as a mutant: a mutant that edits test 1.1 into a self-comparison
  can only be detected by re-running other mutants under it, which is circular. 1.1 instead reads
  the module constant `_COMMITTED_SUMMARY` (the repo path) and asserts it is a file outside
  `tmp_path` (tasks.md, paragraph below the table).

**R1-I4 (TDD).** "Spell out in 2.1 that the implementation uses exactly `y / k` [...] Locate each
panel by its title [...] Assert exactly one panel matches per (coef, convention), and four axes in
total. [...] Assert `len(ax.collections) == 1`. [...] Assert the van Veen panel's offsets before any
"peak-tip" title lookup. [...] assert exactly one figure was collected, and close it with the saved
real `plt.close` in a `finally` block."
- Addressed: design.md:33 ("computed with `/ k` exactly"); design.md:72 (D3: one figure, real
  `plt.close` in `finally`, one match per panel, four axes, one `PathCollection`); tasks.md 1.3 (order
  (a) van Veen offsets first; red names (a)).

**R1-I5 (TDD; Git I2).** "Test 1.5's expected red is not recorded."
- Addressed: tasks.md:54-56 (1.5 "Red: `KeyError: 'r2_van_veen'`"); tasks.md:57 (1.6 red set).

**R1-I6 (Math).** "The guard cannot detect a pure rescale or sign flip of the parquet — the exact
failure that produced this bug. [...] Fix: add scale- and sign-sensitive numbers per coefficient to
`v3`, e.g. `true_min`, `true_max` (or mean and RMSE) on the van Veen arrays, covered by the D2
comparison. Add a mutant: committed parquet × (−1) or × 2 (in a scratch copy, monkeypatched path) →
1.1 fails."
- Addressed: design.md:97 (D6: `true_mean`, `true_rms`, `pred_mean`, `pred_rms`); spec.md:59
  (requirement); tasks.md 1.2 (checked against numpy recomputations); tasks.md:106 (mutant 4.13,
  parquet × (−1), scratch copy, path monkeypatched).

**R1-I7 (Math).** "Today's parquet ÷ k is not what any historical corpus held. [...] Fix: title
"peak-tip reference (F_ref at R_TIP; today's coefficients ÷ k)". In the spec and README, say "the
committed coefficients re-expressed on the peak-tip reference F_ref(R_TIP)", not "legacy
coefficients". Drop "#36 before" from the title."
- Addressed: design.md:33 (title `"{coef} peak-tip reference (stored / k): R2=…"`, and the sentence
  "today's coefficients […] expressed on F_ref(R_TIP), not a reproduction of the pre-#36 data");
  spec.md:59-63 ("the same coefficients on the peak-tip reference"); "legacy" and "#36 before" are
  gone from the spec and design. The title is shortened from the reviewer's wording to fit a panel;
  the meaning ("stored / k" = today's coefficients ÷ k) is kept.

**R1-I8 (Math).** "The zero rule is fragile. [...] If a future regeneration on Linux commits
`delta = 1.1e-16`, a Windows run giving 0.0 would fail rel=1e-12. Fix: compare every `delta` key with
`abs=1e-12` regardless of the committed value. Or use `abs=1e-12` whenever |committed| < 1e-12. Put
this in D2 and the spec."
- Addressed with the reviewer's second option: design.md:53 ("if `|committed| < 1e-12` the values
  must agree within `1e-12` absolute"); spec.md:8 ("within `1e-12` absolute where the committed
  value's magnitude is below `1e-12`").

**R1-I9 (Math).** "No independent known-answer test for the ÷k direction and sign (add 1.3b). [...]
merge the committed holdout parquet with `dataset.parquet` on (`config_name`, `time`) with
`validate="one_to_one"`. For CF_x/Fx and CF_z/Fz, assert the peak-tip panel's x offsets ==
approx(−raw / compute_force_reference(frequency_fstar, stroke_amp_deg, R_TIP, SPAN, CHORD,
RHO).f_ref, rel=1e-12) per row (per-config F_ref, not the scalar k). Also assert the generator's k
== approx((R_TIP/R_GYRATION)**2, rel=1e-15). Red/green: mutants 4.6 (×k) and a sign mutant (drop the
negation) must fail it."
- Addressed: tasks.md:47 (1.3b, verbatim mechanism); design.md:105 (D7); spec.md:78 (scenario);
  tasks.md:99 and :105 (mutants 4.6 and 4.12).

**R1-I10 (Math).** "openspec/specs/force-surrogate/spec.md:1888 defines k = f_ref_old/f_ref_new and
new = old × k. [...] spec.md:1896, in the same requirement, says "each new column equals the old
divided by k". That is the opposite direction for the same k. [...] File a follow-up rather than
leaving it unmentioned."
- Verified by reading `:1888` and `:1896`. Filed as #170. proposal.md:54 and :61; design.md D4.

**R1-I11 (Spec I1).** "Requirement 1 bundles three concerns, and one of them is unrelated. [...]
Move the LF sentence and its scenario into its own requirement."
- Addressed: spec.md:49 (new requirement "Validation-figure summary is written with LF line
  endings").

**R1-I12 (Spec I2).** "The scenario "A stale summary fails" cannot be written as a test. [...] Then
add a task in section 1 that unit-tests the comparison helper directly with synthetic dicts."
- Addressed: spec.md:32 and :39 (two testable scenarios replace it); tasks.md:21 and :30.

**R1-I13 (Spec I3).** "The `1e-12` relative tolerance is verified on one platform but applied to every
block, and CI runs Linux. [...] Verify on Linux before committing the number. For example, run
`main()` in the CI container, or run the CI workflow on the branch, and record the max observed
relative difference in the design. Or specify `rel = 1e-9` for `v1`, `v2`, `v4` and `v5`."
- Addressed with the first option (the user chose `rel=1e-12`): tasks.md:80 (3.5, run under WSL
  Ubuntu, record the largest relative difference, stop rather than loosen). design.md:60-68 records
  the math reviewer's analysis (about 9,000 ulps; five summation orders bitwise-equal) as the reason
  to expect it to pass.

**R1-I14 (Spec I4; Docs I1).** "The proposal misses `docs/CHANGELOG.md`, and this repo does keep one.
[...] Add a task: "5.3 `docs/CHANGELOG.md` [Unreleased] entry (`**BREAKING:** v3 summary keys
r2_before/r2_after → r2_van_veen/r2_peak_tip`; new guard)"."
- Addressed: proposal.md:45 and :73; tasks.md:125 (5.2, the reviewer's entry text).

**R1-I15 (Docs I2).** "tasks.md 2.1 leaves some generator text unmentioned. [...] The function
docstring at line 121 [...] The `fig.suptitle` at line 139 [...] Neither the spec nor test 1.3
constrains the suptitle."
- Addressed: tasks.md 2.1 ("suptitle, function docstring"); design.md:40 (suptitle text); spec.md:87
  scenario and tasks.md 1.3 (d): "no axes title or suptitle contains "BEFORE" or "AFTER"".

**R1-I16 (Git I1).** "Upstream is `origin/main`. [...] Put an explicit step in tasks 6.3, right
before the push approval: "`git push -u origin refresh-v3-validation-figure`", then verify with
`git rev-parse --abbrev-ref @{u}`."
- Addressed: tasks.md:136 (6.3, verbatim).

**R1-I17 (Git I3).** "make this explicit in design D5: "V3_scale_invariance.png is not guaranteed
byte-reproducible across platforms; no test compares it; correctness of V3 is checked by the offsets
test (1.3), not by the pixels"."
- Addressed: design.md:93; proposal.md:62 (out of scope: the PNG's pixels have no guard).

**R1-I18 (Git I4).** "`figures/README.md` is read by `tests/test_t4_stale_claims.py` [...],
`tests/test_coordinate_convention_sign.py:68` and `tests/test_kinematics_attribution.py:102`. [...]
Add "run those three test files after editing the README" to 5.1."
- Addressed: tasks.md:127 (5.3); proposal.md:75 (Impact, "Checked, unchanged").

### SUGGESTIONS taken

- Math: "was right only while…" reworded (proposal.md:16, "from the first commit"); "four retrains"
  → three (design.md:63); "≈4500 ulps" → about 9,000 (design.md:64); no "stroke" in the CF_x label
  and the coordinate-convention spec cited (design.md D1).
- Spec S1: no private function name in the spec (spec.md:11, "the R² function the force-surrogate
  trainer uses"). S3: NaN handling (spec.md:8, design.md:53). S4: boundary-pass cases (spec.md:39).
  S5: module-scoped fixture (tasks.md section 1 preamble). S7: requirement title reworded.
- TDD S1 (fixture), S3 (report every mismatch), S4 (PNG risk stated).
- Docs S4/S5: proposal "Why" trimmed to pointers; the history table lives only in design.md; #53
  history phrasing corrected (proposal.md:12-14).
- Git S2 (commit the reconciliation with the proposal, tasks.md:13), S4 (`git status` clean after
  mutation), S5 (merge, never rebase: tasks.md preamble), S1 (regeneration commit titled
  `fix(v3): regenerate`).

### SUGGESTIONS not taken

- Spec S6 (rename the change ID): the user named the worktree and branch
  `refresh-v3-validation-figure`; the ID matches them.
- Docs S7 (one-line note in the force-surrogate spec): that requirement is not modified here; its
  direction problem is #170.
- Git S6 names a different model in the trailer; commits use this session's attribution trailer.

## Round 2 (2026-11-18): TDD BLOCKED; Spec and Math no BLOCKING

Reviewers: 2 opus (TDD), 6 opus (Math), 1 sonnet (Spec). Docs (4) and Git (5) were not re-run: they
raised no BLOCKING finding in round 1 and their IMPORTANT findings were mechanical (R1-I14 to
R1-I18). Round 2 verdicts on round 1: R1-B1, R1-B2, R1-I3, R1-I6, R1-I9, R1-I13 PARTIAL; the rest
RESOLVED.

### BLOCKING

**R2-B1 (TDD N1).** "1.1b passes vacuously in phase 1, and its red claim is false. [...] A
missing-key message names the same path as a value message [...] Fix the message format and assert
the kind of message. In design.md D2 [...] add: "Formats: `"{path}: missing in fresh"`, `"{path}:
missing in committed"`, `"{path}: type {a} != {b}"`, `"{path}: committed {c!r} != fresh {f!r}"`."
In tasks.md 1.1b, replace [...] with "`_summary_mismatches(it, fresh)` contains `"v3.CF_x.r2_van_veen:
committed 0.9931809360713737 != fresh "` and the `CF_z` equivalent (value messages, not key
messages)"."
- Addressed verbatim: design.md D2 (the four formats); tasks.md 1.1b (the exact value-message
  string, and the red "only `missing in fresh` messages appear"); spec.md scenario "Stale values
  under the correct keys are rejected" ("a value mismatch [...] not a key mismatch").

**R2-B2 (TDD N2).** "case (e) does not kill mutant 4.16, so the "no absolute floor" rule is
untested. [...] replace "a number `1e-11` against `2e-11`" with "a number `1e-11` against
`1.05e-11`, a number `0.5` against `0.5 + 8e-13`"."
- Addressed verbatim: spec.md drift scenario; tasks.md row 4.16; this file, R1-B2.

### IMPORTANT

**R2-I1 (TDD N3).** "the 1.4 wrapper as worded raises `TypeError` once the fix passes `newline=`.
[...] "a wrapper that does `kwargs.setdefault("newline", "\r\n")` and then calls the original with
`(self, data, *args, **kwargs)`"." — Addressed verbatim: tasks.md 1.4.

**R2-I2 (TDD N4).** "1.4 passes vacuously on Linux if the writer stops using `Path.write_text`.
[...] "The wrapper records each path it writes; assert the summary path is among them"." —
Addressed: tasks.md 1.4.

**R2-I3 (TDD N5).** "mutant 4.12 cannot be applied. [...] "generator: peak-tip panel plots `-y / k`,
`-yhat / k` (sign flipped) | 1.3, 1.3b"." — Addressed verbatim: tasks.md row 4.12.

**R2-I4 (TDD N6).** "task 3.5 is not executable as written. [...] `git -C <worktree> archive <sha> |
tar -x -C ~/v3check` [...] `uv sync --frozen --group viz` [...] a scratch script that [...] prints,
per leaf, `|fresh − committed| / |committed|` [...] and the maximum. [...] First confirm `uv
--version` works in that distro." — Addressed verbatim: tasks.md 3.5, with a stated fallback (ask
the user; CI's Linux run) if `uv` is unavailable in WSL.

**R2-I5 (TDD N7).** "In phase 1, 1.1 compares old against old with identical keys, so it is red only
on values [...] the direct proof that the guard fails on the stale values. Record the messages.
[...] At 2.3, 1.1 is red only on keys." — Addressed verbatim: tasks.md 1.1 red, 1.6, 2.3.

**R2-I6 (TDD N8).** "the 4.17 pairing is backwards. [...] "1.0 (extra key **in fresh**); 1.1 with
4.3's dropped `v5`"." — Addressed: tasks.md row 4.17; spec.md drift scenario ("a key present only
in fresh, a block present only in fresh").

**R2-I7 (TDD N11).** "1.3b's recorded red reason is false. [...] "**Red:** no panel titled
'peak-tip' (lookup assertion). The value check itself is proved by mutants 4.6 and 4.12."" —
Addressed verbatim: tasks.md 1.3b.

**R2-I8 (Math).** "`pytest.approx(..., rel=X)` without `abs` keeps the default `abs=1e-12`, so two
tolerances the change states are not what is tested. [...] Exact fix in tasks 1.3b: "`==
approx(-raw / F_ref_tip(row), rel=1e-12, abs=0)` … `k == approx((R_TIP / R_GYRATION) ** 2,
rel=1e-15, abs=0)`". Add to design D7: "`abs=0` everywhere"." — Addressed verbatim: tasks.md 1.3b
(and "every `pytest.approx` in this change passes `abs=0`"); design.md D7.

**R2-I9 (Spec N4).** "Design D2 says "This is confirmed on Linux before the push" [...] Suggested
rewrite: "This is to be confirmed on Linux before the push (task 3.5); if any block exceeds 1e-12 the
change stops and the tolerance is revisited with the user."" — Addressed: design.md D2.

### SUGGESTIONS taken

- TDD N9 (`getbasetemp()`; tasks 1.1), N10 (4.13 in place, 4.13b × 2), N12 (4.19 suptitle, 4.20
  wrong radius, depth-3 dicts in 1.0), N13 (V3 tests do not use the `main()` fixture; design D3).
- Math: per-config metric "|r − k|/k ≤ 4.3e-16 (9 pairs)" (D1); condition-number sentence replaces
  "mean/RMS ≈ 1/84" (D2, which round 2 showed was 1/82.5 and the wrong measure); direction-explicit
  suptitle (D1); README wording for the peak-tip panel (tasks 5.1); on-fluid provenance (D7).
- Spec N1: the stale-values scenario no longer names a commit; the literal stays in tasks 1.1b.

### Not taken

- Spec N2, N3, N5 (no change needed, per the reviewer).

## Round 3 (2026-11-18): TDD NEEDS REVISION (no BLOCKING)

Reviewer: 2 opus (TDD), narrowed to the round 2 fixes. It built a reference comparator from D2 and
confirmed every drift/accept case, mutants 4.14-4.18, the phase-1 red of 1.1 (exactly four value
messages, at `v3.CF_*.r2_before`/`r2_after`), the red of 1.1b (`missing in fresh` only), the 1.4
wrapper, and mutant 4.4. Verdicts: all R2 findings RESOLVED except R2-I6 PARTIAL (below).

Line numbers cited in rounds 1-2 refer to the files as they were then and have since moved; each
entry also names its task, section or scenario, which is the stable reference.

**R3-I1 (N1).** "two "Must fail" entries in the mutant table are false. [...] 4.14 cannot fail 1.1b,
because the stale R² values are far outside any tolerance. "1.1 with 4.3's dropped `v5`" under 4.17
leaves 1.1 green." — Addressed verbatim: tasks.md rows 4.14 and 4.17, and the paragraph below the
table. This also corrects R2-I6, whose "1.1 with 4.3's dropped `v5`" half was not a kill.

**R3-I2 (N2).** "1.3b cannot read "the generator's k" as specified. k is a local variable inside
`fig_v3_scale_invariance` [...] Proposed wording for tasks 1.3b: "the scale between the panels,
`vv_x[m] / pt_x[m]` over rows with `pt_x != 0`, `== approx((R_TIP / R_GYRATION) ** 2, rel=1e-15,
abs=0)` (measured max 1.4e-16 relative)"." — Addressed verbatim: tasks.md 1.3b.

**Suggestions taken:** N3 (spec "Given" of the stale-values scenario no longer claims the current
keys); N4 (note above); N5 (tasks 3.5: 60 s timeout on the WSL `uv --version` check).
