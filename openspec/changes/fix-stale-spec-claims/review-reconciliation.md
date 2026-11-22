# Review reconciliation: fix-stale-spec-claims

Review round 1 (2026-11-18). Reviewers: 1 sonnet (spec), 2 opus (TDD), 3 skipped (no CI, Docker,
dependency or packaging change), 4 sonnet (docs), 5 sonnet (git), 6 opus (math/physics).
Verdict: **BLOCKED**. Each BLOCKING and IMPORTANT finding is quoted, then the resolution, then where
the reviewer's mechanism now appears. "FS" is the force-surrogate delta, "FWV" the
flapping-wing-validation delta.

## BLOCKING

**R1 (math B1, TDD B1).** "'≈ 3.119' cannot pass D4's own recompute rule … `f\"{v:.{d}f}\"` …
gives '3.120' … Fix: print '≈ 3.120' … and update proposal.md, design.md D1/D7 and the D7 mutant
(e.g. 3.120 → 3.121)."

- Resolution: `k` is printed `≈ 3.120` in both places. The existing test literal becomes `3.120`.
  The drift mutant is `3.120 → 3.121`.
- Where:
  - FS "Re-normalization…" body ("≈ 3.120), so re-expressing it on the old (peak-tip, `F_ref(R_TIP)`) reference divides by `k`") and its scenario When.
  - `design.md` D1 ("It prints as **3.120** at three decimals").
  - `tasks.md` 3.2 ("spec number drift (`3.120 → 3.121`)") and 5.2 ("`3.119` to `3.120` in `test_convention_factor_is_geometry_ratio`").

**R2 (spec B1, TDD B2).** "The FWV tripwire pattern is under-specified, and the delta text is full
of the phrases it would match … pin the pattern in D5 to the single adjacent form" / "Two of the FWV
retired patterns, as written in D5, match nothing in the live text … Write every pattern as a
whitespace-tolerant regex in normalized form … Add a test per pattern with `_MUST_FAIL` examples
(the verbatim stale sentences …) and `_MUST_PASS` examples … must include the delta's new sentences."

- Resolution:
  - Every pattern is now a normalized-form regex with whitespace tolerance and adjacent forms only:
    `α\s*=\s*0\s+mid-?stroke` and `≈\s*0\s+at\s+mid-?stroke`.
  - `cf_y −3.61` and `r² ≈ 0.98` are dropped (absent and unmatchable).
  - `RETIRED_EXAMPLES` holds each pattern's verbatim stale sentence; `MUST_PASS` holds every
    corrective sentence and the coarse `≈ 2.61` quotes.
  - The FWV text was also reworded to avoid putting "α = 0" next to "mid-stroke" ("the pitch is
    zero").
  - Prototype run: no pattern matches either delta, and every non-forward-only pattern matches the
    live text.
- Where:
  - `design.md` D5 (pattern table; "Examples." bullet).
  - `tasks.md` 3.2 (`test_retired_patterns_match_their_examples`, `test_retired_patterns_accept_the_corrective_text`).
  - FWV ADDED requirement and scenario "Stroke reversal is not called mid-stroke".

**R3 (spec B2, TDD B4).** "The ADDED FWV requirement introduces a new corpus-dependent number,
`2.61` … Fix: drop the number from the scenario text."

- Resolution: dropped.
- Where: FWV scenario "Coarse T2a values in a coarse context are not flagged" ("which quote the coarse T2a peaks"). `design.md` D4 no longer claims the FWV blocks hold only declared tokens.

**R4 (git B1).** "A live collision with `add-surrogate-comparison-bench` … `## MODIFIED` block for
'Committed evidence-figure artifacts with provenance' … one of our six modified requirements …
Archive is a lost-update hazard … Record the collision … Fix the merge order explicitly … Add a task
… re-run the … check over all worktrees … Before archive (6.1), diff the live requirement."

- Resolution: the collision is removed rather than sequenced. That requirement is dropped from this
  change (its only edit was one parenthetical). The overlap check is still a task, before the PR,
  before ready, and before archive, and the pre-archive live-spec diff is kept.
- Mechanism change: the reviewer's "fix the merge order explicitly" is replaced by removing the
  overlap. Justification: with no shared requirement there is no order to fix, and pinning another
  session's merge order for a one-line parenthetical couples two independent branches.
- `effective_spec` also no longer raises on overlaps of requirements it does not number-check (git
  I5, TDD S1).
- Where:
  - `proposal.md` "What does not change" (the bench bullet).
  - `design.md` D2 ("**Collision avoided.**") and D3 (two-change rule); D8 alternative.
  - `tasks.md` 0.3, 8.5, 9.1.

**R5 (git B2, TDD I1).** "The 'red' runs (1.1–1.5) cannot be reproduced from committed state …
moving the deltas out … is a working-tree mutation with real risk … Fix: prove red in a throwaway
worktree" / "run the red through it with an empty `tmp_path` as `changes_dir` … Better still, a
permanent non-vacuity test: save the pre-change stale requirement blocks as
`tests/fixtures/spec_claims/…` … This red holds forever."

- Resolution: no file is moved. The permanent red is the stale-fixture test (the TDD reviewer's
  stronger mechanism). The one-off TDD record uses `changes_dir` monkeypatched to an empty
  `tmp_path`, so no throwaway worktree is needed for the red. A throwaway worktree is still used for
  the archive dry-run. Commit labels now state each commit's CI state.
- Where:
  - `design.md` D7 ("**Permanent red.**").
  - `tasks.md` 3.1, 3.2 (`test_stale_fixture_trips_the_guard`) and 3.3 (red record), plus the
    per-commit CI states in the task headings.

**R6 (TDD B3).** "Most D7 guard mutants survive the tests in 1.x … Add these permanent tests:
`test_unregistered_number_fails` … `test_stale_registry_entry_fails` … `test_missing_phrase_fails` …
`test_tripwire_fails_without_anchor` … `test_kinematics_check_reads_docstrings` … `_RETIRED_EXAMPLES`
… The reinsertion test inserts the raw example into the raw text … Also missing from the mutant list:
REMOVED ignored, ADDED-dup raise removed, archive not skipped, RENAMED raise removed, recompute
skipped entirely, fixture-kind check skipped, `CC-`/`D<n>` strip removed."

- Resolution: every listed test is added, and the mutant list now includes every listed mutant.
- Where:
  - `tasks.md` 3.2 ("Synthetic must-fail tests") and 8.1 (mutant list).
  - `design.md` D7 ("**Synthetic must-fail tests**").

## IMPORTANT

**R7 (math I1).** "'Dividing by the configuration's settled-beat peak removes that scaling' is
contradicted by committed data … Suggested wording: '… reduces (does not remove) that scaling' … the
ranges recorded beside `SYMMETRY_RATIO_TOLERANCE` … predate the #147 sign flip."

- Resolution: the text now says it reduces the dependence and does not remove it. Recomputed:
  normalized ratio p30 ≤ 0.0056, p60 ≤ 0.0091 (coarse); 0.0041 vs 0.0081 (fine). The constant's
  comment is rewritten as sign-free magnitudes.
- Where:
  - FS gate body ("Dividing by the configuration's settled-beat peak reduces that dependence; it does not remove it").
  - `design.md` D2 (gate row; **Docstrings** bullet).
  - `tasks.md` 4.1.

**R8 (math I2).** "'Horizontal excursion' means two different things … the requirement should name
both quantities. For example: 'the new span-tip's in-plane displacement r·sinφ_amp at reversal; the
old span-tip's distance from its stroke axis, r·|sin α|, which is 0 at reversal and r·sin α_amp at
mid-stroke.'" Also TDD I8: "Add `test_old_span_tip_is_off_axis_at_mid_stroke`."

- Resolution: adopted verbatim in substance, plus the mid-stroke scenario and its test.
- Where:
  - FWV MODIFIED body ("At reversal the new span-tip's in-stroke-plane displacement is `r·sin φ_amp` … the old span-tip's distance from that axis is `r·|sin α|`") and scenario "At mid-stroke the old span-tip is tilted off its axis".
  - `design.md` D6.
  - `tasks.md` 4.3.

**R9 (math I3, TDD I4).** "The registry rule cannot check the order of magnitude in '≈3.7×10⁶×' …
Fix: … print `3.72e6`. Then add a drift test that changes only the exponent" / "Specify a
`format_like(value, literal)` helper … Unit-test it on (3.11972,"3.120"), (3722400,…), (5.17e7,"5.17e7"),
(12535,"12,535"), (310.34,"310"), (144.0,"144")."

- Resolution: the throughput is printed `≈ 3.72e6`, and the `~10⁶×` hypothetical is reworded with no
  number. `format_like` is specified with exactly those unit cases, and the exponent-drift test is
  added.
- Where:
  - FS caption scenario ("≈ 3.72e6").
  - `design.md` D4 ("**Printing.**").
  - `tasks.md` 2.1 (`format_like` cases) and 3.2 ("exponent drift (`3.72e6 → 3.72e7`)").

**R10 (math I4).** "'Re-expressing it in the old (peak-tip) convention divides by k' overstates what
/k recovers … Suggested wording: 'on the peak-tip reference F_ref(R_TIP) (normalization arm only;
sign and moment reference unchanged)'. Mirror it in the test docstring."

- Resolution: adopted.
- Where:
  - FS scale-invariance body ("That re-expression changes the normalization only: the sign and the moment reference point stay as committed, so it is not the corpus as it was before #36").
  - `tasks.md` 5.2 (docstring).

**R11 (docs I1, docs I2, math I5, TDD I8 docstring).** "`evidence_figure.py:471-474` … says the
headline 'equals ``latency_speedup * batch_size``' … `train.py:531` … 'the physically-central
cycle-averaged force' … Fix the docstring in this change … extending [the tripwire] to this
docstring would be consistent."

- Resolution: both docstrings are fixed in this change (no behaviour change), and the tripwire scans
  both files' prose. `sane_dickinson_cf_z`'s `U/U_tip` mislabel (math I5) is a different claim and
  goes to the follow-up.
- Where:
  - `proposal.md` "Docstrings and comments", Impact "Code".
  - `design.md` D2 ("**Docstrings**") and D5 ("**Targets.**").
  - `tasks.md` 4.1 and 3.2 (`test_no_retired_claim_in_code_prose`).

**R12 (docs I4, math S3).** "The sidecar key `overshoot_factor` bakes in a direction … Add one
sentence … 'the key name is historical; it does not assert direction'" / "Consider retitling the
scenario to 'RMS ratio'."

- Resolution: both adopted.
- Where:
  - FS Sane–Dickinson body ("key `overshoot_factor`; the name is historical and asserts no direction").
  - Scenario "The quasi-steady RMS ratio is recorded and disclosed, not presented as a baseline".

**R13 (math I6).** "The same 83% literal remains in an unmodified requirement … `:2829` … It is not
in `RETIRED` … the proposal's reason should say so [archived design]."

- Resolution: "Committed corpora are guarded by cluster-free reconciliation tests" is added as a
  MODIFIED requirement and its scenario rewritten; `covered only 83\s*%` is in `RETIRED`. The
  proposal now names the archived source of `3.06e-4` / 83%.
- Where:
  - FS that requirement's scenario "A truncated corpus is caught by the normalized symmetry invariant".
  - `design.md` D2 (row, and the paragraph after the table) and D5 (table).
  - `proposal.md` table row "`:2711`, `:2724`, `:2829`".

**R14 (spec I1).** "`design.md:119-120` and the registry scope are inconsistent with the ADDED
requirements … state in D4 and task 1.4 that both ADDED guard requirements are in GUARDED … remove
the `α = 0` tokens from the force-surrogate ADDED text."

- Resolution: `GUARDED` is stated as 8 force-surrogate plus 2 flapping-wing-validation requirements,
  modified and added. The FS ADDED text no longer mentions the kinematics instant.
- Where:
  - `design.md` D4 (first sentence).
  - `tasks.md` 3.3 ("the two ADDED requirements fail with 'update GUARDED/REGISTRY'").
  - FS ADDED "Data-dependent claims…".

**R15 (spec I2, TDD I8 scenario gaps).** "The new scenario 'config_mean_r2 is reported but never
headlined' has no task that tests it … map this scenario to the existing test" plus the TDD list
(mid-stroke claim, renamed-test positive check, MAE, parallelism ≠ N, message content, truncation
'And', CFL message).

- Resolution:
  - Scenario-to-test map: "config_mean_r2 is reported but never headlined" →
    `test_force_surrogate_evidence_figure.py` `_CONFIG_R2_LITERALS` checks (sidecar, caption,
    README).
  - Kinematics names → `test_no_retired_claim_in_code_prose` and `test_renamed_reversal_test_exists`.
  - Mid-stroke → `test_old_span_tip_is_off_axis_at_mid_stroke`.
  - /k RMSE and MAE → task 5.
  - Parallelism ≠ N → task 6.1.
  - Truncation "And" → `test_symmetric_but_cfl_limited_config_fails`.
  - CFL message → task 6.2.
- Where: `tasks.md` 3.2, 4.3, 5.2, 6.1, 6.2; `design.md` D6.

**R16 (spec I3, docs S1).** "The tripwire's phrase list is restated in prose … not testable from the
spec … add … `RETIRED` must contain at least one pattern per category" / "Cut it to: 'phrases listed
in `RETIRED` …'"

- Resolution: the docs reviewer's mechanism is taken. The category list is removed, and the
  requirement makes each pattern testable against its own stale sentence and the corrective text.
  The spec reviewer's category count is not adopted: `set(RETIRED_EXAMPLES) == set(RETIRED)` plus a
  match test per pattern pins each pattern, which a category count would not.
- Where: FS ADDED "Data-dependent claims…" ("Retired claims." bullet); `tasks.md` 3.2.

**R17 (TDD I2).** "The drift tests must survive archive and patch the right names … Separate the I/O
from the checks: `check_block(...)` and `retired_hits(...)` … `source()` must read
`mosquito_cfd.force_surrogate.constants.R_GYRATION` at call time … Pick a drift that changes the
third decimal of k … patch `_toy_metrics` on the module object."

- Resolution: adopted.
- Where:
  - `design.md` D3 ("pure where possible"), D4 ("**Kinds.**": "through its module at call time, never a name bound at import"), D7.
  - `tasks.md` 3.2.

**R18 (TDD I3).** "Under `--import-mode=importlib` … a second module copy can exist … move
`_POINTWISE`, `_SKILL`, `_CONFIG_R2`, `_toy_metrics` and `_TOY_ROWS_PER_WINGBEAT` into
`tests/_evidence_fixture.py` … `rows_per_wingbeat=2000` is a literal in at least six more places."

- Resolution: adopted, and every fixture-meaning literal is converted.
- Where: `design.md` D6; `tasks.md` 1.1 (line list).

**R19 (TDD I5).** "The token rule's unit tests miss real cases … `256x128x256` … `3.7×10⁶×` …
`1e-9`/`3.06e-4` … `UTF-8` … `ISO-8601` … `k = −1` … `[1, 3]`, `T/4`, `sha256:` … Require `[0-9]`
(or `re.ASCII`) … The phrase check … must use the same tokenizer … allow a `count` field."

- Resolution: adopted. The digit–`x`–digit join is split, so grid dimensions are tokens (also math
  S6).
- Where: `design.md` D4 ("**Token rule.**", "**Entry.**"); `tasks.md` 2.1.

**R20 (TDD I6).** "Every read … needs `encoding=\"utf-8\"`. Add a unit test where
`requirement_blocks` gets CRLF input."

- Resolution: adopted.
- Where: `design.md` D3; `tasks.md` 2.1, 2.2.

**R21 (TDD I7).** "effective_spec unit tests missing … ADDED name that already exists … REMOVED of a
missing name … another active change with deltas only for other capabilities … An unknown `## `
section … Default paths … A requirement in `GUARDED` that is absent … fails with a message."

- Resolution: adopted. REMOVED of an absent name raises, the same as MODIFIED.
- Where:
  - FS ADDED "Guards on specification text read the effective specification" (body and scenarios).
  - `tasks.md` 2.1 and 3.2.

**R22 (TDD I9).** "Add to 5.x: in a throwaway worktree at the PR head, run `openspec archive …
--yes`, then the guard … then discard."

- Resolution: adopted. The "git diff --exit-code after restore" part is moot, because no file is
  moved now.
- Where: `design.md` D7 ("**Archive dry-run.**"); `tasks.md` 8.3.

**R23 (git I1-I4, I6).** "1.6 … must land BEFORE the 1.4 registry tests … Split [commit 1.7] …
Commit 3.4 is misdescribed … Task 4.1 (CHANGELOG) has no commit step … CI state per commit is
unrecorded … run `openspec validate` locally at every commit that touches the change dir … Do NOT
split 'move dir' and 'apply deltas'."

- Resolution: the commit plan follows the reviewer's (A–H).
  - The fixture module comes first.
  - The helper and the guard are split.
  - Kinematics is renamed with its red test.
  - The CHANGELOG is its own commit.
  - CI states are in the headings, and `openspec validate` runs at each change-dir commit.
  - The archive stays one `openspec archive` commit.
- Where: `tasks.md` "Conventions" and section headings 0–7, plus 9.1.

**R24 (git I5).** "any other session's change dir on main that modifies one of our six requirements
makes `effective_spec` raise on main … its error message should name both change dirs and say who
reconciles."

- Resolution: adopted, and narrowed: only for number-checked requirements (R4).
- Where:
  - FS ADDED "Guards on specification text…" ("naming both changes").
  - `design.md` D3 ("naming both change directories and saying the second to merge must reconcile").

**R25 (docs, CHANGELOG IMPORTANT).** "Match the existing style: nested bullets … mention that the
specs now carry no corpus-measured speedups and that the modified requirements' numbers are guarded
… If you edit … docstrings, note it under Fixed … run [`_stale_claims`] test after editing."

- Resolution: adopted.
- Where: `tasks.md` 7.1.

## SUGGESTIONS adopted

- math S1: the gate "primary" tension is gone; the ratio is now "a backstop behind the timestep and
  row-count checks".
- math S2: lab-frame `CF_x`, not "chordwise".
- math S4: the parallelism factor "can be larger or smaller than `N`".
- math S5: "six cycle means" is now "the held-out configurations' cycle means".
- math S7: "(previous scenario)" now names the scenario.
- math S8: the forward-only patterns are labelled as such.
- docs S2: the FWV ADDED requirement keeps only FWV-specific content.
- docs S4: the parallelism wording no longer reads as a tautology.
- spec S2: the absent-name raise is in the spec.
- spec S3: Impact lists the CHANGELOG and roadmap.
- spec S4: the FS ADDED requirement is split in two.
- TDD S1: the overlap raise is limited to guarded requirements.
- TDD S2: a wrapped-phrase test.
- TDD S3: anchors are raw substring checks.
- TDD S4: the CHANGELOG quotes no retired literal.
- TDD S5: `pytest -m "not gpu"` and `PYTHONIOENCODING`.
- git S2–S4: noted in tasks.

## SUGGESTIONS not adopted

- docs S3/S6 (trim `design.md`): kept long. The mutant list moved to `tasks.md` 8.1, but the D4/D5
  detail is what the TDD reviewer needed to find R2 and R19.
- spec S1 (split the truncation "And" into its own scenario): kept as an "And". It now has a
  concrete test (`test_symmetric_but_cfl_limited_config_fails`), which was the reviewer's concern.
- TDD I8 watch item (`overshoot_factor > 1` on toy data): toy data, not a corpus claim; listed in
  the follow-up.

---

# Round 2 (2026-11-18)

Reviewers: 1 sonnet (spec, no BLOCKING, 8.5/10), 2 opus (TDD, BLOCKED), 3 skipped (no CI, Docker,
dependency or packaging change), 4 sonnet (docs, no BLOCKING), 5 sonnet (git, no BLOCKING), 6 opus
(math, BLOCKED). Verdict: **BLOCKED**. Both blockers were reproduced before fixing.

Note on round 1: R7's resolution above quotes "p30 ≤ 0.0056, p60 ≤ 0.0091". Those bounds are false
at their printed precision (round-2 math I3); the corrected maxima are in `design.md` D2 and
`proposal.md`.

## BLOCKING

**S2-R1 (TDD B1).** "The `equals…latencyspeedup…batchsize` pattern misses `evidence_figure.py` …
`normalize` strips `*` … Verified: `equals\s+latencyspeedup\s*[×*]?\s*batchsize` matches …
`RETIRED_EXAMPLES` maps each pattern to a **list** with one verbatim example per stale site … A code
example goes through `normalize(python_prose(...))`."

- Reproduced: the old pattern misses the docstring and the new one matches.
- Resolution: adopted as written. The prototype now hits all three code targets pre-fix and nothing
  in either delta.
- Where: `design.md` D5 (the table row "operator is optional"; the "**Examples.**" bullet: "a
  **list** with one verbatim stale sentence per site in the table, code sites included … checked
  through `normalize(python_prose(...))`"); `tasks.md` 3.2.

**S2-R2 (math B1, TDD B2).** "The new mid-stroke test cannot kill the rotation-swap mutant … have
the mid-stroke test assert the full vector, `legacy(0,α,0)@(0,0,r) == (0, −r sin α, r cos α)` …
correct 4.3 and 8.1 to name the test that actually kills each mutant."

- Reproduced: at mid-stroke, legacy and new give `(0, −1.06, 1.06)` and `(1.06, 0, 1.06)` on the old
  tip, which have the same `hypot`. Both give `x = 0` on the new tip. At reversal the two matrices
  are equal.
- Resolution:
  - Full-vector assertions on both tips.
  - The FWV scenario now requires the full vectors and says why.
  - The requirement body now says the old/new contrast is the span body axis, not the composition.
  - Task 5.3 records that the distance-only assertion survives the swap.
- Where:
  - FWV scenario "At mid-stroke the old span-tip is tilted off its axis" ("the full vectors are
    asserted, because the old and new rotation compositions agree on the distance and on `|x|` at
    this instant").
  - `design.md` D2 ("**Mid-stroke tip.**") and D6.
  - `tasks.md` 5.3 and 9.1 (Kinematics).

## IMPORTANT

**S2-R3 (math I1).** "'In-stroke-plane displacement `r·sin φ_amp`' is not a displacement … What the
test measures is `|x|`, the lab-x coordinate … rename it."

- Resolution: renamed throughout to the lab `x` coordinate, `|x|`, and "a point on the arc" is
  dropped.
- Where: FWV body ("the new span-tip's lab `x` coordinate … has magnitude `r·sin φ_amp`") and its
  first scenario; `design.md` D2 row.

**S2-R4 (math I2).** "'Truncated ≥ 0.0150' needs the 'materially-truncated' qualifier, in the
comment and in the corpus-guards requirement … Say 'materially-truncated minimum'."

- Resolution: adopted in the requirement, the gate body and the comment plan. The comment plan also
  names the 5 mild configs.
- Where: FS "Committed corpora…" body ("materially-truncated minimum"); FS gate body; `design.md` D2
  docstrings bullet; `tasks.md` 4.2.

**S2-R5 (math I3).** "The '≤' bounds are false at their printed precision … write 'max 0.0091 (4
d.p.)' or '≤ 0.0092'."

- Resolution: "maximum … 4 d.p." in `proposal.md` and `design.md` D2. The comment plan says "at most
  0.0092 (recomputed maximum 0.00914)".

**S2-R6 (math I4).** "add [the raw-corpus regeneration] … and mirror it in the test docstring."

- Resolution: adopted.
- Where: FS scale-invariance body ("the raw columns were regenerated since
  (`fix-force-surrogate-sweep-hinge`), and the moment reference point and the sign changed");
  `design.md` D1; `tasks.md` 6.3.

**S2-R7 (spec I1).** "Scenario title still makes the claim … 'A configuration with a sufficiently
truncated settled wingbeat fails …' … the same applies to line 431."

- Resolution: both scenarios are retitled "A sufficiently truncated …", and the Note's quote follows.

**S2-R8 (spec I2).** "'SHALL make the build raise' … rewrite: '…SHALL make building that
requirement's text for the per-number check raise, naming both changes'."

- Resolution: adopted verbatim.

**S2-R9 (docs I1).** "FWV stroke-motion requirement gives a wrong or unclear reason for measuring at
reversal … Rewrite the sentence: 'The comparison is made at reversal because the pitch is zero there
…'."

- Resolution: adopted in substance. The cryptic "(stroke `Rz(φ)` about the span)" is replaced by an
  explicit description of the two conventions.
- Where: FWV body.

**S2-R10 (docs I2).** "points at a change name that stops meaning anything after archive … Rewrite:
'For every requirement listed in the test module's `GUARDED` registry…'."

- Resolution: adopted for both bullets (`GUARDED`; `RETIRED` / `RETIRED_EXAMPLES`).

**S2-R11 (docs I3, git R4 wording).** "the drop leaves the stale text with no owner … Name the owner
in the follow-up issue bullet … post a comment on the bench change's tracking issue (or add a line to
its `tasks.md`)."

- Resolution: the owner is named in the follow-up item: the bench change if it is still open,
  otherwise the follow-up. The user is told in the approval summary, and the PR body says so.
- Mechanism change: the reviewer's "post a comment … or add a line to its tasks.md" is not done.
  Justification:
  - the bench change has no tracking issue to comment on;
  - editing another session's worktree is out of bounds for this session (the user's setup rule);
  - the user is the right person to relay it.
- Where: `design.md` D2 ("**Collision avoided.**"); `proposal.md` "What does not change" and the
  follow-up list.

**S2-R12 (docs I4, R25 gap).** "Add one line … under Changed … Roadmap row 17 … Say 'next free row'
… The `corpus_guards.py` SYMMETRY comment is edited but not scanned … say … unguarded."

- Resolution: all three adopted.
- Where: `tasks.md` 8.1 (Changed bullet) and 10.2 (next free row); `design.md` D2 ("This comment is
  not a tripwire target").

**S2-R13 (git, commit D label).** "commit D is labelled green but is red by its own task text … (a)
Move the code-prose and renamed-reversal tests out of D into E."

- Resolution: option (a). The code-prose tests ship with their fixes in E1/E2, so D is green.

**S2-R14 (git, commit E message).** "two types in one subject … `fix` is wrong … split E into E1
`docs(force-surrogate): …` and E2 `test(kinematics): …`."

- Resolution: adopted.
- Where: `tasks.md` sections 4 and 5.

**S2-R15 (git, closing keyword for #115).** "#115 is only partially resolved … Either use `Advances
#115` … or keep `Closes #115` and add a PR-body sentence naming the follow-up issue. State the choice
explicitly."

- Resolution: put to the user at approval. `tasks.md` 9.6 uses the chosen keyword and adds the
  mechanical closing-keyword grep.

**S2-R16 (git, 9.1 route).** "State which route applies, a PR or a direct push to main, and say that
the user authorizes the push."

- Resolution: `tasks.md` 10.1 asks the user which route to use.

**S2-R17 (TDD I1).** "3.3's expected red is wrong in two places … Config-resolved … registry check
passes … There are 3 ADDED requirements."

- Resolution: adopted verbatim in `tasks.md` 3.3.

**S2-R18 (TDD I2).** "The stale-fixture expectation is incomplete, and exact equality ties the
permanent fixture to every future registry edit … The test asserts each listed (block, token, count)
is reported (⊇)."

- Resolution: adopted, with the reviewer's computed table.
- Where: `design.md` D7.

**S2-R19 (TDD I3).** "The `re.ASCII` mutant survives, and D4's reason for it is wrong … add the token
case "x ３ y" → []."

- Resolution: the rationale is corrected and the case added.
- Where: `design.md` D4; `tasks.md` 2.1 and 9.1.

**S2-R20 (TDD I4).** "The 6.2 test duplicates an existing test … Replace 6.2 with: build the case
with `settled_fx_override` giving a non-zero ratio inside `SYMMETRY_RATIO_TOLERANCE` … assert …
exactly one entry … `0.0003` … killed by the mutant that drops `realized.get('min')`."

- Resolution: adopted as written. Checked that `_make_corpus` has `settled_fx_override`.
- Where: `design.md` D6; `tasks.md` 7.1 and 7.3.

**S2-R21 (TDD I5).** "The #170 direction is not tied to data … join the holdout parquet to
`dataset.parquet` … assert `CF_x_true / _K == −Fx / f_ref(R_TIP)` per configuration."

- Resolution: adopted as `test_committed_holdout_over_k_is_on_the_peak_tip_reference`. "V3 parity" is
  defined by naming the V3 test.
- Where: `design.md` D1; `tasks.md` 6.2.

**S2-R22 (TDD I6).** "Use `assert f"{_K:.3f}" == "3.120"`."

- Resolution: adopted.
- Where: `design.md` D1; `tasks.md` 6.3.

**S2-R23 (TDD I7).** "defaults are `None`, resolved at call time from module attributes … or a
scratch conftest given verbatim in the commit message."

- Resolution: adopted, using module attributes plus a scratch conftest.
- Where: `design.md` D3, D7; `tasks.md` 3.3.

**S2-R24 (TDD I8).** "The FWV ADDED scenario promises more than a pattern list can test … reword it
to 'the guard fails on each retired phrase'."

- Resolution: the reword option is taken. The scenario now reads: "it reports nothing, and inserting
  any of this specification's retired stale sentences into either makes it fail".

**S2-R25 (TDD I9).** "Code-only and forward-only patterns have no behavioural killer … Add
`stale_code_prose.txt` … and `stale_fwv_pre168.md` … asserts every pattern has at least one hit
across the fixtures."

- Resolution: adopted.
- Where: `design.md` D7; `tasks.md` 3.1, 3.2 and 9.1.

## SUGGESTIONS adopted

- Spec:
  - S1: D3 states the ADDED-by-two and MODIFIED-of-another's-ADDED cases.
  - S2: "about 65" is used everywhere.
  - S3: the FWV ADDED requirement names its forward-only `RETIRED` entries.
- Docs:
  - S2: the gate parenthetical is simplified; "~N×" becomes "~X×"; the change history is dropped
    from the caption Note; the coarse scenario's Given is rewritten.
  - SUGGESTION 1: tasks reference D4–D7 instead of repeating them; line numbers are stated as
    `c87e39c`.
- Math:
  - S1: "within 1e-9".
  - S2: the `:34` comment.
  - S3: superseded by S2-R22.
  - S4: a sentence on the fixture coincidence.
  - S5: the gate Note names `add-fine-corpus-run-verification`.
  - S6 (also TDD S4): the D7 cross-reference.
  - S7: added to the follow-up.
  - S8: the declared definition is widened.
- TDD:
  - S1: the kill in 6.1 is recorded honestly.
  - S2: `format_like` keeps the sign; rounding is pinned.
  - S3: the examples are string literals.
  - S5: a duplicated-number test.
  - S6: a superscript-exponent check.
  - S7: tokens are taken from the raw text.
  - S8: non-directory entries are skipped.
- Git:
  - 7.1 probes first.
  - The rule for following up on H.
  - The closing-keyword grep.
  - The overlap check before the push.
  - The full suite after any merge-in.

---

# Round 3 (2026-11-18)

Verdict: **NEEDS REVISION**. No reviewer found a BLOCKING issue.

| Reviewer | Model | Result |
|---|---|---|
| 1. Spec | sonnet | 9/10, no BLOCKING |
| 2. TDD | opus | no BLOCKING |
| 3. CI | — | skipped (no CI, Docker, dependency or packaging change) |
| 4. Docs | sonnet | no BLOCKING |
| 5. Git | sonnet | no BLOCKING |
| 6. Math | opus | NOT BLOCKED |

Every IMPORTANT finding is reconciled below. Each was applied before the change went to the user for
approval.

## IMPORTANT

**S3-R1 (TDD I1).** "The superscript class `[⁰-⁹]` misses ¹, ², ³ and ⁻ … Suggested wording for D4:
'A digit followed by a superscript digit or superscript sign (`\d[⁰¹²³⁴-⁹⁻⁺]`) in a guarded block
fails the check.'"

- Resolution: adopted verbatim.
- Where: `design.md` D4.
- A prototype confirms zero hits on both deltas.

**S3-R2 (TDD I2).** "No named test kills the 'superscript check removed' mutant … add … 'a guarded
block containing `3.72×10⁶`, `~10³×` and `1×10⁻⁹`, with `3.72`, `10` and `1` registered, fails naming
the superscript'."

- Resolution: adopted verbatim.
- Where: `design.md` D7; `tasks.md` 3.2 and 9.1.

**S3-R3 (TDD I3).** "The D7 table is stale for the Honest caption block. `12,535` should be ×1, not
×2."

- Resolution: corrected.
- Where: `design.md` D7 table.

**S3-R4 (TDD I4).** "D4's list of declarable kinds is closed … Suggested wording: '…citation years,
mathematical and unit-conversion constants in formulas, and quoted retired text that a named test
asserts absent.'"

- Resolution: adopted, with the reviewer's examples and pins.
- Where: `design.md` D4 "Kinds".

**S3-R5 (math I1).** "The planned `SYMMETRY_RATIO_TOLERANCE` comment undercounts the mildly truncated
configs … exactly 15 configs end early … The 15th is s55_f085_p30 … |ratio| 0.000147 … Fix: 'The
other 6 affected configs measured 0.0001 to 0.0071, inside the healthy band.'"

- Resolution: adopted, naming the sixth config and how it was found.
- Task 4.2 recomputes the values when the comment is written.
- Where: `design.md` D2 docstrings bullet; `tasks.md` 4.2.
- The proposal's "the archived D6 … records 5 of 15 affected configs as indistinguishable" is kept,
  because it quotes D6 accurately. The true count of 6 is stated in the design.

**S3-R6 (spec IMPORTANT, docs I-3).** "`proposal.md` Impact … lists only two fixtures … add …
`stale_code_prose.txt` and `stale_fwv_pre168.md`" / "change the proposal bullet to 'kept as four
fixtures' … change the design reference to '`tasks.md` 9.1'."

- Resolution: all three adopted.

**S3-R7 (docs I-1).** "'This change' in the ADDED force-surrogate requirement will dangle after
archive … Rewrite: 'Given each corrective sentence recorded in the test module's `MUST_PASS` list' …
'report every stale site recorded in the fixtures' … 'Given the stale text of the guarded
requirements as it stood before issue #115 was fixed, kept as a committed test fixture'."

- Resolution: adopted. Two retained mentions of "this change's code" belong to the pre-existing
  byte-identity scenario and are out of scope.

**S3-R8 (docs I-2).** "The S2-R11 relay has no task. Add to 0.1 … Add to 0.2: 'the issue's first
line names the owner of the "predates them" fix'."

- Resolution: adopted.
- Where: `tasks.md` 0.1, 0.2.

**S3-R9 (git I1).** "The 9.6 grep misses `Closes: #N` … false-positives on 'prefix #N' … Suggested
form: `grep -iE '\b(close[sd]?|fix(e[sd])?|resolve[sd]?):? +#[0-9]'`."

- Resolution: adopted verbatim.
- Where: `tasks.md` 9.6.

**S3-R10 (git I2).** "Say explicitly that A is committed only after approval, and that the 10
requirement names must not change between the overlap check and the commit."

- Resolution: adopted.
- Where: `tasks.md` 0.4.

## SUGGESTIONS adopted

- Math:
  - S1: "with zero pitch" qualifies the old-convention sentence.
  - S2: θ is zero at all four instants.
  - S3: the caption Note covers both sidecars.
- Docs:
  - S-2: the mid-stroke Then is split into Then/And.
  - S-3: the Note is reworded.
  - S-4: "regenerated since, to fix a geometry defect rather than as a re-normalization".
  - Minor: the RENAMED paragraph break.
- TDD:
  - S1: code examples are stored as source fragments.
  - S2: "≈ 0, floating-point".

## Not adopted

- The docs claim that "~X×" was replaced by "≈310×" is incorrect. Both "~X×" occurrences are present
  in the Sane–Dickinson requirement; "≈310×" is the separate fixture value in the latency scenario.
- Docs S-1 and S-5 are trims of `design.md` D3 and the FWV body. The FWV body was tightened only
  where math S1/S2 required it. D3 is kept as written, because it is the implementer's reference.
- Spec suggestions:
  - The FWV naming scenario partly duplicates the ADDED requirement. It is kept, because it carries
    the positive "renamed test exists" check.
  - The "issue #115" history reference in the ADDED body is kept. It names the failure mode, and the
    tokenizer skips it.
- Git:
  - S1 (shorter E1/G subjects): the subjects are shortened at commit time.
  - S3 (the bench archive hand-merge): noted for the user and not this change's job.

---

# Approval and pre-commit checks

- **Approval** (2026-11-22): approved by the user, with "Closes #115" chosen for the PR body; the
  follow-up issue inherits the unguarded remainder.
- **Follow-up issue:** filed as #176. Its first section names the owner of the "predates them" fix.
- **Overlap check (task 0.3)** (2026-11-22, `origin/main` still `c87e39c`): the force-surrogate
  deltas in three other active changes share no requirement name with the 10 in `GUARDED`. The three
  changes are `add-real-comparison-figures`, `add-surrogate-comparison-bench` and
  `share-light-corpus-helpers`. No other worktree has a flapping-wing-validation delta.

---

# PR review (`/review-pr`, branch mode, 2026-11-22)

Five reviewers: code quality, testing/TDD, scientific rigor, performance/build, behavioural
correctness. Verdict: **COMMENT**. No BLOCKING findings. Each IMPORTANT finding is listed with
the commit that resolves it.

## Fixed in commit 93516cc

**PR-1 (behavioural I1).** "Some deltas that OpenSpec applies are silently not applied by the
guard … `## Modified Requirements` … `###  Requirement: A` (two spaces) … the delta is dropped …
fail open."

- The finding was reproduced.
- Section titles are now case-insensitive, headings accept flexible whitespace, and bullet-form
  REMOVED entries are parsed.
- An unclassified section that holds requirement blocks raises.

## Fixed in commit 5d440d9

**PR-2 (code I1).** "The 'permanent red' stale-fixture test breaks on unrelated registry edits
… assert `>=` by parsing the count."

- Adopted.

**PR-3 (code I2).** "`check_block` failure messages are not actionable … add the hint 'register
it in REGISTRY…'."

- Adopted (`_HOW_TO_FIX`).

**PR-4 (code I3).** "REGISTRY is verbatim-phrase heavy … group entries by phrase, e.g. a
`P(phrase, [...])` helper."

- Adopted.

**PR-5 (TDD I1).** "The 'Each source of a recomputed number is load-bearing' scenario is only
tested for 2 of the 7 non-declared entries."

- Adopted: one drift per distinct source, plus a coverage test over every non-declared literal.

**PR-6 (TDD I2).** "`check_block`'s phrase-binding check has no test … unknown kind … negative
source."

- All three cases were added.

## Fixed in this commit

**PR-7 (science I1).** "A new corpus-dependent claim that the guard does not check … 'coincide
with the committed sidecars' values' … delete the 'coincide' sentence."

- The sentence is deleted and its pattern retired.

**PR-8 (TDD I3).** "The mid-stroke kinematics test uses α = 45°, where sin α = cos α … use
α = 30° … get the angles from `euler_angles(0.0, …)`."

- Adopted.

**PR-9 (TDD I4).** "The numbers the gate requirement now delegates to are unguarded … add
`test_symmetry_tolerance_comment_healthy_max_matches_committed_corpora`."

- Adopted, covering the recomputable numbers: the healthy maximum and its rounding, and the
  healthy-side margin.
- The truncated range comes from git `e1ca8b5` and cannot be recomputed in CI. This is stated in
  the test's docstring.

## Suggestions adopted

- Uppercase E-notation is accepted.
- Retired patterns tolerate common variants.
- Count binding is enforced.
- Spec-quoted `MUST_PASS` sentences must actually occur in the spec.
- The dead `block is None` branch is removed.
- "Modified or removed" in the two-change message.
- Test names replace line numbers in the declared reasons.
- "Not N by construction" in the docstring.
- The D6 note in the comment.
- The swap sense in the mid-stroke wording.
- Row count and the timestep check are named separately.

## Suggestions not adopted

- **Exempting `256³` from the superscript ban.** No guarded requirement uses `³`. A future author
  gets the actionable hint.
- **Leading-dot decimals and `_310_` italics.** These are known tokenizer blind spots, recorded
  in #176.
- **Making the `_evidence_fixture` names public.** Kept private: they are test-only helpers.
- **Signs.** The registry stays sign-blind (#176).

## Mutation re-run

- 61 mutants, 59 killed. The two survivors are the equivalent ones.
- Separately, 4 new-test mutants (the comment's maximum and margin, the kinematics sin/cos swap,
  the rotation swap): all killed.
