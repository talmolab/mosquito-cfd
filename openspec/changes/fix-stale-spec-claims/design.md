# Design: fix-stale-spec-claims

## Context

Issue #115 found result numbers frozen into live requirement bodies and scenario Givens that went
stale when the corpora were rebuilt. Since then the corpora were retrained twice (#126 hinge moments,
#147 on-wing sign), the evidence figure moved to baseline-relative skill (#127/#128), and T4 was
re-graded on a corrected model (#141/#133, PR #168). For this proposal both live specs were swept
line by line, and every data-dependent literal was recomputed from committed artifacts (JSON sidecars
first; the committed parquets and CSVs through the package's own functions where no JSON exists).
`proposal.md` lists what is stale.

Existing guards: `tests/_stale_claims.py` (PR #168) reads RESULTS.md, the figures README, roadmaps and
the CHANGELOG; `tests/test_results_reproducibility.py` binds numbers to phrases in RESULTS.md; PR
#172's comparator checks the V1–V5 summary against a fresh regeneration. None reads a spec.

## D1. Direction of `k` (#170)

`k = f_ref_old / f_ref_new = f_ref(R_TIP) / f_ref(R_GYRATION) = (R_TIP / R_GYRATION)² =
3.1197210117…` is kept (V3 uses the same definition). It prints as **3.120** at three decimals; the
spec's long-standing "≈ 3.119" truncated it, and `test_convention_factor_is_geometry_ratio` passed
only through `rel=1e-3`. The delta prints `≈ 3.120`, and that test's literal becomes `3.120`.

The requirement states once that `CF_new = k · CF_old`, so old→new multiplies and new→old divides,
and fixes `:1896` ("multiplied by `k`") and the two `k = −1` sentences (`−CF_old`; `k = −1` is its
own inverse). Dividing the committed parquet by `k` re-expresses it on the peak-tip reference
`F_ref(R_TIP)`. That changes the normalization only. The result is not the pre-#36 corpus, because
since #36 the raw columns were regenerated (`fix-force-surrogate-sweep-hinge`) and the moment
reference (#108) and sign (#109) changed. V3's docstring says the same. Verified for this proposal:

- the holdout parquet's `CF_{x,y,z}_true` equal `−F / f_ref(R_GYRATION)` exactly, on all 12,535 rows;
- `c74d69b`'s new/old ratio is `k` for all 12 `CF_*` columns;
- `RMSE_old / RMSE_committed = 1/k` to 12 digits.

The test rescales by `/ _K`. R² is unchanged either way. RMSE and MAE assert
`== pytest.approx(committed / _K, rel=1e-9, abs=0)`. The locals are `r2_committed`,
`r2_old_convention`, `rmse_committed`, `rmse_old`, `mae_committed` and `mae_old`.
`test_convention_factor_is_geometry_ratio` asserts `f"{_K:.3f}" == "3.120"`, since `rel=1e-3` cannot
tell 3.119 from 3.120. The module comment at `:34` and the docstrings at `:42`/`:44` change with it.

**The direction is tied to data, not just to the assertion.** A new
`test_committed_holdout_over_k_is_on_the_peak_tip_reference` joins the holdout parquet to
`dataset.parquet` on (`config_name`, `time`) and asserts, per configuration, `CF_x_true / _K ==
-Fx / f_ref(R_TIP)` (`rel=1e-12`, `abs=0`). The `× k` direction fails it. This is "V3 parity": V3's
peak-tip panel (`test_flapping_wing_validation_figures.py::test_v3_peak_tip_panel_matches_raw_forces_on_tip_reference`)
asserts the same identity for the figure.

**Red first:** change the RMSE assertion to `/ _K` while the scaling is still `* _K`. It fails off
by `k²`. Then change the scaling.

## D2. Literal vs behaviour, per item

Rule: a corpus result whose value is not the point is deleted, and the behaviour it illustrated is
stated without it. No corpus result is refreshed into a spec, so the specs stop going stale on
rebuilds. The numbers that stay are design constants, code constants or synthetic fixture values,
and every one of them in a guarded requirement is registered (D4).

| Item | Choice | New text states |
|---|---|---|
| `:1682` ~310× coarse latency | delete | the latency floor is reported on both profiles whether or not it exceeds 1,000×, never asserted to |
| `:1721` ≈12,009× | delete | the parallelism factor is measured, not the batch size |
| `:1677` `= latency × batch_size` | replace | the parallelism factor is `throughput_speedup ÷ latency_speedup` by definition and equals `N · t_single / t_batch`, a ratio of two measured timings that can exceed or fall short of N (fine: 15,463 > 12,535; coarse: 7,470 < 12,535) |
| `:1680` "(N=12,535)" | replace | `N` = the sidecar's `speedup.batch_size` |
| `:1655` "six cycle means" | replace | "the held-out configurations' cycle means" (holdout count is corpus design, not stated) |
| `:1721`/`:1727` 5.17e7, 2000, 12,535, ≈3.7×10⁶×, ≈310× | label | synthetic fixture values; the throughput is printed `≈ 3.72e6` so its exponent is checkable |
| `:1727` "~10⁶×" fabricated number | replace | the units mismatch "would multiply the latency speedup by the rows per wingbeat" |
| `:1691-1697` note | rewrite | the requirement states no corpus result; scenario numbers are fixture values |
| `:1593-1595` ≈0.7 / ≈1.3 / #115 | delete | ratio reported as measured, no bound, no direction; `overshoot_factor` named as a historical key that asserts no direction |
| `:1631` scenario title "overshoot" | rename | "The quasi-steady RMS ratio is recorded and disclosed, …" |
| `:1637` under-predicts | replace | neutral; no claim that the model over- or under-predicts |
| `:2694-2696` 2.9%, 1.3×, two orders | delete | normalizing *reduces*, does not remove, the pitch-amplitude dependence (recomputed maxima of the normalized ratio: p30 0.0056, p60 0.0091 coarse; 0.0041, 0.0081 fine, 4 d.p.); the ratio is a backstop behind the timestep and row-count checks; it is the lab-frame `CF_x` (the old text said "chordwise") |
| `:2711` 3.06e-4 | delete | "fell below its declared `ns.fixed_dt` (a CFL-limited run)" |
| `:2724`, `:2829` 83% | delete | partial coverage large enough to break the symmetry; the symmetry check is not claimed to catch every truncation |
| `:2754` "(previous scenario)" | replace | names the scenario (the previous one is now a different scenario) |
| `:1355-1357` physically-central | replace | `config_mean_r2` is a diagnostic, never the headline |
| FWV `:221-229` α=0 midstroke | replace | stroke reversal at `t = T/4, 3T/4`; mid-stroke at `t = 0, T/2`; names the two measures (new: lab `|x|` = `r·sin φ`; old: distance from the stroke axis `r·|sin α|`); reversal isolates the sweep because the pitch is zero there; the old/new contrast is the span body axis (y vs z), since at reversal the two rotation matrices are identical |

`3.06e-4` and 83% come from the archived `add-fine-corpus-run-verification` design (D2/D3:
s55_f115_p30, dt_min 3.0607e-4, 1.829 cycles). No committed data artifact or test uses them.

Two corrections went beyond deletion.

- **Truncation scenarios.** "A truncated config fails the normalized symmetry check" overstated the
  check. #92's truncation was CFL limiting: complete step count, short simulated time. The row-count
  check therefore passes it, and the timestep check catches it. The archived D6 records 5 of 15
  affected configs inside the healthy band. Both scenarios now say this.
- **Mid-stroke tip.** The test measures the new tip's `|x|` and the old tip's `hypot(x, y)`. At
  mid-stroke the old tip's axis distance is `r·sin 45° = 1.0607`, while the new tip's `|x|` is 0. The
  requirement names both measures. The known-answer test asserts **full vectors**: at mid-stroke
  `rotation_matrix` and `rotation_matrix_legacy` give the same distance and the same `|x|`
  (`Ry(α)` vs `Rx(α)` on the old tip: `(1.06, 0, 1.06)` vs `(0, −1.06, 1.06)`), so only the vectors
  distinguish them.

**Collision avoided.** The draft also modified "Committed evidence-figure artifacts with provenance"
(for one stale parenthetical). The in-flight `add-surrogate-comparison-bench` change modifies that
requirement too. Two MODIFIED deltas on one block race at archive, and the second silently overwrites
the first. That requirement is therefore dropped from this change. The bench change copies the block
unchanged, so its stale "predates them" parenthetical has no owner.

- It becomes a follow-up-issue item. If the bench change is still open when the follow-up is picked
  up, the fix goes there; otherwise the follow-up fixes it.
- The user is told in the approval summary, and the PR body says so.
- This session does not edit the other session's worktree.

**Docstrings** (comment-only `src/` edits, since each states a claim this change retires):

- `evidence_figure.py::compute_speedup` says "equals ``latency_speedup * batch_size``";
- `train.py::compute_config_resolved` says "the physically-central cycle-averaged force";
- the `SYMMETRY_RATIO_TOLERANCE` comment in `corpus_guards.py` gives signed pre-#147 ranges. It is
  rewritten as magnitudes:
  - non-truncated configs across both committed corpora have `|ratio|` at most 0.0092 (recomputed
    maximum 0.00914);
  - the fine corpus's 9 materially-truncated configs measured 0.0150 to 0.1648;
  - the other 6 affected configs (15 in all; archived D6 listed 5 of them, and
    `s55_f085_p30` at 0.0001 is the sixth, found by diffing `e1ca8b5` and `ab7f88c`) measured
    0.0001 to 0.0071, inside the healthy band.

  The margins (0.012/0.00914 = 1.31×, 0.0150/0.012 = 1.25×) stand. This comment is not a tripwire
  target: it holds numbers, not retired phrases.

## D3. Effective spec text

The live spec changes only when a change is archived, after merge. A guard reading only the live
spec would fail on this PR, which is exactly what it should be gating. Editing the live spec in the
PR as well would duplicate every block and invite the conflicts the archive step manages.

`tests/_spec_claims.py` builds the effective text from the live spec plus the active changes' deltas
for the capability. The functions are pure where possible, so the tests can pass strings or
`tmp_path` trees.

- `requirement_blocks(text)` splits on `### Requirement:` up to the next `### Requirement:` or
  `## ` heading. It is CRLF-safe (names are stripped), and any `## ` section other than
  ADDED/MODIFIED/REMOVED ends a block and is not applied (e.g. `add-apex-benchmarking`'s
  `## Cross-References`).
- `effective_spec(capability, *, specs_dir=None, changes_dir=None)` returns an ordered mapping of
  requirement name → list of block variants. `None` resolves at call time to the module attributes
  `SPECS_DIR` / `CHANGES_DIR` (from `Path(__file__).parents[1]`), so a test can monkeypatch them.
  Every read is `encoding="utf-8"`.
  - Active changes are the directories in `changes_dir` other than `archive/`; non-directory
    entries are skipped.
  - Two active changes that both ADD a name: the second raises as "already present". A MODIFIED
    delta whose target only another active change ADDS: raises as "absent from the live spec".
  - MODIFIED replaces; REMOVED drops; ADDED appends.
  - It raises when a MODIFIED or REMOVED name is absent from the live spec, an ADDED name is already
    present, or RENAMED appears.
- Two active changes modifying one requirement: both variants are kept.
  - `effective_text(capability)` concatenates every variant; the tripwire reads this.
  - `effective_block(capability, name)` raises when there is more than one variant, naming both
    change directories and saying the second to merge must reconcile. The registry reads this.

  So an overlap between *other* sessions' changes on requirements this guard does not number-check
  never turns main red. One on a guarded requirement does, loudly and with a fix named.

## D4. Enumeration-complete registry

`GUARDED` names every requirement this change modifies or adds (8 force-surrogate, 2
flapping-wing-validation). For each one, `check_block(name, text, entries) -> list[str]` returns
failure messages. The test asserts the list is empty for the effective block, and non-empty with
specific substrings on synthetic inputs.

- **Token rule.**
  - Before tokenizing: `CC-<n>` is stripped, and a digit–`x`/`×`–digit join is spaced, so
    `256x128x256` and `64×32×64` give all their dimensions.
  - Tokens: `(?<![A-Za-z_#.\d])\d+(?:[.,]\d+)*(?:e[-+]?\d+)?(?!\d)` with `re.ASCII`. Python's `\d`
    already ignores superscripts (category No), but without `re.ASCII` it matches other Nd digits
    such as `３` or `٣`; the unit cases include `"x ３ y" → []`.
  - Tokens and phrases are taken from the raw, whitespace-collapsed block, never from `normalize()`
    output (which drops `_` and `*`).
  - A digit followed by a superscript digit or sign (`\d[⁰¹²³⁴-⁹⁻⁺]`; `¹²³` sit outside
    U+2070–U+2079) in a guarded block fails the check, so a `×10ⁿ` form cannot bring back an
    unchecked order of magnitude.
  - Skipped: identifiers (`s45_f115_p60`, `sha256`, `D6`, `F1`), issue references (`#115`) and
    superscripts.
  - Tokenized: `1e-9`, `5.17e7`, `3.72e6`, `12,535`, `UTF-8`'s `8`, `ISO-8601`'s `8601`, `T/4`'s `4`.
  - Tokens are sign-blind (`−1` gives `1`). No recomputed entry is negative; a recomputed entry whose
    value is negative is rejected by the registry's own self-check.
- **Entry.** `Entry(phrase, literal, kind, source, count=1)`.
  - The phrase must occur in the whitespace-collapsed block, and the literal must be among the
    phrase's own tokens (the same tokenizer, never a separate regex).
  - `count` covers repeated declared tokens (the FWV block has many `0`s).
  - Text tokens and registry literals must be equal as multisets, so an unregistered number fails
    and so does an entry whose number is gone.
- **Kinds.**
  - `recomputed`: `source()` reads a committed artifact or a code constant through its module at
    call time (`constants.R_GYRATION`, `evidence_figure.CFD_SECONDS_PER_WINGBEAT`), never a name
    bound at import.
  - `fixture`: `source()` reads `tests/_evidence_fixture.py` (D6) through its module.
  - `declared`: `source` is the reason. Presence is the only check, so per Verification Principle 1
    it is not evidence about data. Only non-results may be declared: tolerances, grid sizes, counts
    fixed by design, synthetic known-answer inputs or outputs, citation years (`1999`),
    mathematical and unit-conversion constants in formulas (`2π`, `/1000`, `1/(f*·dt)`, `0/0`), and
    quoted retired text that a named test asserts absent (`2.4`:
    `test_force_surrogate_evidence_figure.py:462,1142`). An output must name the existing test that
    pins it (e.g. `0.2`/`0.875`: `test_force_surrogate_train.py:306-308`).
- **Printing.** `format_like(value, literal)` renders `value` in the literal's notation and compares
  strings exactly: fixed decimals (`3.120`), comma grouping (`12,535`), integer (`144`, `310`), and
  e-notation with the literal's mantissa digits, no `+`, no zero padding and the minus sign kept
  (`5.17e7`, `3.72e6`, `3.06e-4`). Rounding is Python's (half to even: `(2.5, "2")` is a unit case).
  There is no tolerance.

## D5. Retired-claim tripwire

`retired_hits(text, patterns) -> list[str]` applies regexes to `_stale_claims.normalize(text)`. The
normalized form has links reduced, `*`, `_` and backticks dropped, whitespace collapsed and the text
lower-cased, so the patterns are written in that form.

| Pattern (normalized) | Stale sentence it was written against |
|---|---|
| `310\s*×\s*on the coarse grid` | FS `:1682` |
| `12,009` | FS `:1691`, `:1721` |
| `fit that under-predicts` | FS `:1637` (bare `under-predict` would hit the new "over- or under-predicts") |
| `tracked (separately )?in (issue )?#115` | FS `:1595`, `:1692` |
| `equals\s+latencyspeedup\s*[×*]?\s*batchsize` | FS `:1677`; `evidence_figure.py:472` (`normalize` strips `*`, so the operator is optional) |
| `two orders of\s+magnitude` | FS `:2696` |
| `usable tolerance window` | FS `:2694` |
| `physically-central` | FS `:1356`; `train.py:531` |
| `≈\s*0\.7\)` | FS `:1593` |
| `covered only 83\s*%` | FS `:2724`, `:2829` |
| `3\.06e-4` | FS `:2711` |
| `α\s*=\s*0\s+mid-?stroke` | FWV `:221`, `:229` |
| `≈\s*0\s+at\s+mid-?stroke` | FWV `:223` |
| `quarter-period\s+mid-?stroke` | `test_wing_kinematics.py:110` |
| `vs\s+cfd\s*≈\s*2\.61` | forward-only (removed by #168; issue #115 comment) |
| `~\s*0\.058` | forward-only (as above) |

The last two cannot go red on today's text. They guard against a regression, and the delta says so.

- **Targets.**
  - The effective text of both specs.
  - `_stale_claims.python_prose` of `src/mosquito_cfd/force_surrogate/evidence_figure.py`,
    `src/mosquito_cfd/force_surrogate/train.py` and `tests/test_wing_kinematics.py`.
  - The kinematics file's `def test_` names, checked raw (normalization strips `_`) for
    `midstroke_has_zero_pitch`.
- **Examples.** `RETIRED_EXAMPLES` maps each pattern to a **list** with one verbatim stale sentence
  per site in the table, code sites included. They are string literals in the test module; CI's
  shallow checkout cannot `git show`. Each code-site example is stored as a minimal Python source
  fragment (a `# …` comment or a `def f():` with a docstring) and checked through
  `normalize(python_prose(...))`, exactly as the guard reads it. The sentences were taken from git at
  `c87e39c` (or, for the two forward-only patterns, from the live spec at `5fd6b2c^`, before #168); `set(RETIRED_EXAMPLES) == set(RETIRED)` is asserted. Each pattern must match its
  example, and none may match `MUST_PASS`. That list holds every corrective sentence this change
  wrote (e.g. "with no claim that the model over- or under-predicts the CFD lift", "the pitch is zero",
  "stroke reversal, … mid-stroke is `t = 0`") and the coarse `CF_normal ≈ 2.61` quotes at FWV `:278`
  and `:796`.
- **Self-trip.** The ADDED requirements describe the retired claims in words and do not quote them.
- **Anchors.** Positive anchors are substring checks on the raw text, in requirements this change
  does not touch:
  - `### Requirement: Moment coefficients are referenced to the wing hinge`
  - `### Requirement: RESULTS.md headline numbers reproducible from committed CSVs`
  - `def compute_speedup`, `def compute_config_resolved` and `def test_rotation_is_orthonormal` for
    the code targets.

## D6. Tests touched beyond the guard

- `tests/_evidence_fixture.py` (new). `_POINTWISE`, `_SKILL`, `_CONFIG_R2`, `_CONFIG_R2_LITERALS`,
  `_toy_metrics` and `TOY_ROWS_PER_WINGBEAT = 2000` move here from
  `test_force_surrogate_evidence_figure.py`. Both modules import it, so there is one module object
  under either import mode. Every `rows_per_wingbeat=2000` in that file that means the fixture's rows
  uses the constant; the behaviour is unchanged.
- `test_compute_speedup_throughput_headline` gains
  `sp["parallelism_factor"] != pytest.approx(sp["batch_size"], rel=1e-3)` (fixture: 11,994 vs
  12,535). It documents the requirement but kills no new mutant: the existing
  `assert_allclose(parallelism_factor, throughput/latency)` already kills "factor returned as
  `batch_size`". Recorded honestly in the PR.
- `tests/test_wing_kinematics.py`:
  - `test_euler_angles_midstroke_has_zero_pitch` is renamed
    `test_euler_angles_at_stroke_reversal_have_zero_pitch`, with docstring "At stroke reversal
    (t = T/4), φ is at amplitude and α (∝ cos) is 0."
  - New `test_old_span_tip_is_off_axis_at_mid_stroke` asserts full vectors:
    - `rotation_matrix_legacy(0, α, 0) @ (0, 0, r) == approx((0, −r·sin α, r·cos α), abs=1e-12)`;
    - `rotation_matrix(0, α, 0) @ (0, r, 0) == approx((0, r, 0), abs=1e-12)`;
    - the distance `hypot(...[:2]) == r·sin α`.

    Swapping the two functions makes the vector assertions fail. The distance and `|x|` alone
    cannot tell them apart.
  - The guard checks (ast) that the renamed test exists and that its docstring says "stroke
    reversal".
- `tests/test_acceptance_gate.py`:
  - `_make_corpus` defaults to a symmetric pattern (ratio ≈ 0, floating-point), so `test_cfl_limited_config_fails`
    is already "symmetric but CFL-limited" with a trivial ratio.
  - The new `test_cfl_limited_config_with_nonzero_in_tolerance_ratio_fails` uses
    `settled_fx_override` for a non-zero ratio inside the tolerance (≈ 0.008), with
    `interior_dt_below_nominal=True` and rows equal to `max_step`. It asserts:
    - (precondition) `0 < settled_beat_symmetry_ratios(...) < SYMMETRY_RATIO_TOLERANCE`;
    - `result.failures` is exactly the CFL entry;
    - the entry contains the config name and `0.0003` (how `3e-4` renders).

    It is green on first run and is killed by a mutant that drops `realized.get('min')` from the
    message.
- `test_force_surrogate_scale_invariance.py`: D1 (`/ _K`, MAE, `3.120`, names, docstrings).

## D7. Verification

- **Permanent red.** Four fixtures are added, each checked with `git ls-files` after adding:
  - `tests/fixtures/spec_claims/stale_force_surrogate.md` and `stale_flapping_wing_validation.md`:
    the `c87e39c` text of the 7 guarded MODIFIED requirements.
  - `stale_code_prose.txt`: the `c87e39c` `python_prose` of the three code targets.
  - `stale_fwv_pre168.md`: the `5fd6b2c^` T4 sentences.

  Tests on them:
  - Every `RETIRED` pattern has at least one hit across the four.
  - The tripwire reports each expected (block, pattern) site.
  - `check_block` reports each expected (block, token, count) that the stale text has beyond the
    registry. The check is ⊇, not equality, so a later delta to a guarded requirement does not break
    the permanent fixture. The expected table, computed by the round-2 TDD prototype:

    | Block | Extra tokens in stale text |
    |---|---|
    | Sane–Dickinson | `1`, `0.7`, `1.3` |
    | Honest caption | `1,000`, `12,535`, `310`×2, `12,009`×2, `3.7`×2, `10`×3 |
    | Re-normalization | `3.119` |
    | Gate | `2.9`, `1.3`, `3.06e-4`, `5e-4`, `83` |
    | Corpora | `83` |

  - The Config-resolved block's stale claim is a word, not a number. Its multiset is unchanged, so
    only the tripwire flags it.

  This red holds forever, including after archive. The one-off red for the TDD record monkeypatches
  `_spec_claims.CHANGES_DIR` to an empty `tmp_path`, so the effective text is the stale live spec. It
  is run from a scratch `conftest.py`, quoted verbatim in the commit message. No file is moved.
- **Synthetic must-fail tests** (permanent; each also kills a mutant):
  - an unregistered number;
  - a stale registry entry (number gone);
  - a missing phrase;
  - a recomputed source drifted through `monkeypatch.setattr(constants, "R_GYRATION", …)` to a value
    that changes k's third decimal, with an assertion that the drifted k formats differently;
  - a fixture source drifted;
  - a spec number drifted (`3.120 → 3.121`) and an exponent drifted (`3.72e6 → 3.72e7`);
  - a guarded block containing `3.72×10⁶`, `~10³×` and `1×10⁻⁹`, with `3.72`, `10` and `1`
    registered, fails naming the superscript;
  - a reinserted `RETIRED_EXAMPLES` sentence in raw text, for every pattern;
  - an empty spec and an unrelated spec (no anchor);
  - a source with a bad docstring and a clean name, and one with a clean docstring and a bad name;
  - a wrapped registry phrase (whitespace collapse);
  - messages contain the requirement, number and phrase (registry) and the pattern and file
    (tripwire).
- **`effective_spec` unit tests** (synthetic `tmp_path` trees):
  - replace, drop and append;
  - `archive/` ignored;
  - other-capability changes ignored;
  - an unknown `## ` section ends a block;
  - each raise case;
  - two changes on one requirement give both variants in `effective_text` and a raise naming both in
    `effective_block`;
  - CRLF input.
- **`format_like` and token unit tests:** `(3.11972, "3.120")`, `(3722400, "3.72e6")`,
  `(5.17e7, "5.17e7")`, `(12535, "12,535")`, `(310.34, "310")`, `(144.0, "144")`, and the token cases
  in D4.
- **Mutation testing.** In-process runner in the scratchpad: `PYTHONDONTWRITEBYTECODE=1`,
  `PYTHONIOENCODING=utf-8`, purge `mosquito_cfd*`, `_spec_claims`, `_stale_claims`,
  `_evidence_fixture` and test modules from `sys.modules`, then `pytest.main`. Originals are saved as
  bytes and restored with `write_bytes`, nothing else runs at the same time, and every anchor is
  asserted to occur exactly once. The mutant list is in `tasks.md` 9.1. Survivors are killed or
  justified in the PR body.
- **Archive dry-run.** In a throwaway worktree at the PR head: `openspec archive fix-stale-spec-claims
  --yes`, then the guard and `openspec validate --strict`, then discard. This proves the guard holds
  on the archived live text.
- **Overlap check.** Before marking the PR ready and again before archive, list every worktree's
  `openspec/changes/*/specs/{force-surrogate,flapping-wing-validation}` requirement names and
  compare them with `GUARDED`.

## D8. Alternatives considered

- **Refresh and guard every corpus number (option c).** This keeps numbers in the spec that the
  README and sidecars already state, and it guarantees churn on every rebuild, which is #115's root
  cause.
- **Guard all ~65 matching literals now.** The user chose a follow-up issue.
- **Edit the live specs in the PR.** Rejected in D3.
- **Keep the evidence-figure-artifacts requirement and fix merge order with the bench change.**
  Rejected. It couples two independent sessions for one parenthetical (D2).
- **Raise on any two-change overlap.** Rejected. It would turn main red for sessions unrelated to
  this guard (D3).

## Implementation deviations (task 9.4)

The implementation was checked against D1–D7. Everything named there is implemented as written,
with the exceptions below.

### Why compute the gate test's ratio from the override, not via `settled_beat_symmetry_ratios`?

D6 said the new gate test would assert `0 < settled_beat_symmetry_ratios(...) < tolerance`. That
function takes a built dataset frame, but `_make_corpus` writes raw CSVs and runs the gate's own
extraction internally. Building the frame separately would duplicate the gate's extraction path in
the test. The test instead computes `|mean|/max|·|` directly on the settled-beat `Fx` override.
`_write_csv`'s docstring documents that the ratio is scale-invariant in `Fx`, because `f_ref` is
fixed for the corpus. The gate's own result then confirms the precondition: exactly one failure,
the CFL one, and no symmetry failure.

### Why a pytest plugin object rather than a scratch `conftest.py` for the red record?

D7 and task 3.3 said to use a scratch `conftest.py`. A conftest is picked up from the rootdir or
test path, so using one would mean writing it inside the worktree. A plugin object passed to
`pytest.main(plugins=[...])` from a scratchpad script does the same monkeypatch
(`_spec_claims.CHANGES_DIR` → an empty temp dir) and touches no repository file. Commit
`aa2732f` records the command and its result (11 failed, 1 passed).

### Why move the anchor checks into helpers (an addition)?

Mutation testing (9.1) showed that the spec and code anchor asserts, the raw-name check and the
CRLF check could not fail on clean data. They now live in `_scan_spec`, `_code_prose_hits` and
`_retired_test_names`, and unit tests feed those helpers empty or unrelated text. The CRLF test
checks block bodies as well as names (`988ea70`).

### Why are two mutants left alive?

They are equivalent under the real layout, and the checks are kept as defensive intent:

- `archive/` not skipped: archived changes live at `changes/archive/<dated>/specs/…`, so
  `changes/archive/specs/<cap>/spec.md` never exists.
- non-directory entries not skipped: `<file>/specs/<cap>/spec.md` is never a file.

The 16 "pattern dropped" mutants were run as "pattern made unmatchable" (the key kept, so the
set-equality bookkeeping cannot kill them). Each is killed by
`test_retired_patterns_match_their_examples`, which checks behaviour.

### Why did the delta text change after approval?

The PR review (5 reviewers, report-only, 2026-11-22) found three spec-text problems. Each was
fixed in the delta:

- **A corpus claim this change introduced.** The caption Note said the fixture's 2000 rows and
  12,535-row batch "coincide with the committed sidecars' values". The guard checked only the
  fixture half, so a rebuilt corpus would falsify it unnoticed: the #115 failure mode. The sentence
  is deleted and added to `RETIRED` (with `_RETIRED_WITHIN_THIS_CHANGE`, since no pre-change
  fixture holds it).
- **The FWV mid-stroke scenario.** It said the two compositions "give the same distance and the
  same `|x|`". That is true only of a swap, and false read literally. It now states the swap
  sense, and says the angles come from the kinematics with `sin α_amp ≠ cos α_amp`. The test
  moved from α = 45° to 30° for the same reason.
- **The corpora truncation scenario's And.** It now names which check catches which truncation:
  row count for an early stop, the timestep check for a CFL-limited run.

The rest of the PR-review response is code and tests:

- the parser accepts every delta form OpenSpec applies;
- the registry is hardened;
- every source has a drift test;
- the comment-number guard;
- the docstring wording.

See `review-reconciliation.md`, "PR review".

### Why does the guard raise on some deltas that OpenSpec silently ignores?

The adversarial re-review of the PR-review fixes found that `93516cc` had over-generalized. The
guard applied three delta forms that OpenSpec 0.13 ignores:

- `## MODIFIED  Requirements` (two inner spaces);
- a second section of the same kind;
- a `*` bullet under REMOVED.

The reviewer confirmed this with a scratch project: `openspec validate --strict` passes on all
three, and `openspec archive` leaves the live text unchanged. That is fail-open again.

The parser is now matched to OpenSpec's source (`core/parsers/requirement-blocks.js`):

- a section title is trimmed and compared, lower-cased, with `<kind> requirements`;
- a block starts at `^###\s+Requirement:`;
- a REMOVED entry is a `^###\s*Requirement:` header line or a dash bullet.

Where OpenSpec would silently ignore a section that holds requirement blocks, or keep only the
last of two same-kind sections, the guard raises. That fails closed: an author sees an error
instead of a check against text that will never be live.

Parity check against OpenSpec on all 76 delta files under `openspec/changes/`, active and
archived:

- 75 match exactly (names and block text);
- 1 raises: the archived `add-arbitrary-geometry` delta. It has a
  `## FUTURE Requirements (Post-Award)` section, which OpenSpec ignores. The guard never reads
  archived changes; an active change in that form would fail loudly.
