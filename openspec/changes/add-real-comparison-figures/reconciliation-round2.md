# Reconciliation of review round 2

**Round-2 verdict: BLOCKED.** There were four blockers:

- S-3.1, three live scenarios dropped from the force-surrogate MODIFIED block;
- G-N-B1 and G-N-B2, render-time dirtiness;
- D-N1, a false quasi-steady attribution;
- T-R2-B1, section 3 not green.

All are fixed below. Every round-1 item was re-checked by its own reviewer. Those still PARTIAL are
listed again with their fix.

**Abbreviations.**

- Reviewer prefixes: S = spec quality, T = TDD, D = docs, G = git, M = math.
- **viz** = `specs/visualization-tooling/spec.md`, **fs** = `specs/force-surrogate/spec.md`.
- **Req** = requirement, **Sc** = scenario.

## BLOCKING

- **S-3.1.** "The MODIFIED block carries five [scenarios] … Dropped: 'Seeded training step is deterministic on the CPU torch device (torch tier)', 'wandb is disabled by default without importing wandb', 'wandb online failure does not block metrics.json'. … Fix: append those three scenarios to the MODIFIED block verbatim … Add a task step: 'diff each MODIFIED block against the live requirement before archive'."
  - **Fix:**
    - all three scenarios are restored verbatim, from live lines 1421–1437;
    - a task step was added;
    - the "uninstalled package" scenario that S-3.8 asked for was also added.
  - **Where:**
    - fs, MODIFIED Req "Training reproducibility and provenance": the last four scenarios;
    - tasks 11.1 ("Diff each MODIFIED block against its live requirement").

- **G-N-B1.** "Task ticks dirty the tree at render time … Fix: Add a rule under 'Working rules': never tick a task whose completion sits between the 8.4 check and the 9.6 commit until after 9.6 … Add to 9.3 a `git diff HEAD --stat` assertion that is empty."
  - **Fix:** adopted.
  - **Where:**
    - tasks, Working rules ("Between the 8.4 check and the 9.6 data commit, tick nothing; those ticks go into the 9.7 commit"; "Before any render. `git status --porcelain --untracked-files=all` and `git diff HEAD --stat` must both be empty");
    - tasks 8.4, 9.7;
    - design D7.

- **G-N-B2.** "Untracked review artefacts … Fix: state in 0.3 that the proposal commit is made after the last `/review-openspec` round has been reconciled, or add a line to 8.3 that commits any new files in the change dir."
  - **Fix:** both are adopted.
  - **Where:** tasks 0.4 ("After the last `/review-openspec` round is reconciled, commit the whole change directory, review files included"); tasks 8.3 ("and any new change-directory file").

- **D-N1.** "D9 (coarse README bullet) says to attribute the gap 'to the model's omitted terms, as the sidecar note does'. Both parts are wrong … Fix: delete that clause from D9 and use the drafted bullet above. Add to tasks 10.5 a cross-check that the coarse bullet's causal wording agrees with the fine README QS section."
  - **Fix:** the clause is withdrawn, the reviewer's drafted bullet is used verbatim, and the cross-check is added.
  - **Where:**
    - design D9, Coarse README (the drafted spans, plus "The round-1 instruction to attribute the gap to the omitted terms was wrong and is withdrawn");
    - tasks 10.5.
  - **Note:** the round-1 suggestion M-S8 introduced this error, and I adopted it without checking the fine README. M-S8 is withdrawn.

- **T-R2-B1.** "Replacement for tasks:80-81: 'Parametrize over the three builders. Until sections 4–6 they are stubs that call `validate_image_digest` and `_load_corpus`/`_check_pair`, then raise `NotImplementedError`.' Replacement for tasks:111-119: 'Provenance and writing discipline are tested directly on `_provenance(...)` and `_write_outputs(...)`, with a trivial `Figure` built in the test …'"
  - **Fix:** adopted verbatim. G-N-I1 is the same finding.
  - **Where:** tasks 3.1 (stub definition); tasks 3.2 (helpers tested directly); tasks 4.1 ("End-to-end. The real builder writes three files with full provenance").

## IMPORTANT

- **S-3.2.** "Add the following to the shared list … 'the coarse and fine seed lists differ'; 'the per-seed `val_configs` differ'; '`runs[0].seed` differs from `primary_seed`'; 'a prediction's `CF_c_true` differs from the dataset's holdout row' … delete the duplicates from the per-figure requirements."
  - **Fix:** adopted. All are shared guards 9–11, and the per-figure duplicates are removed.
  - **Where:** viz, Req "Comparison figures validate their inputs before writing anything", the ordered list.

- **S-3.3(a), M-N4.** "make a partial null skill a refusal, as for R²." The math reviewer worded it: "A null skill SHALL be all-or-none per corpus and target … treats `null == null` as equal."
  - **Fix:** adopted.
  - **Where:**
    - viz, shared guard 10 ("A null `skill` or `config_mean_r2` is either null for every seed of that corpus and target, or for none of them"; "with a null equal only to a null");
    - viz, Sc "a target whose skills are all null";
    - design D2.

- **S-3.3(b), T-R2-I6.** "the perturbation is applied to the runs before `summarize_seed_sweep`, so `range` stays consistent."
  - **Fix:** the helper gets a two-stage hook, and the boundary and >1 scenarios say so.
  - **Where:** tasks 2.1 (`edit_runs` / `edit_metrics`); viz, the defect list ("both placed before `summarize_seed_sweep`"); viz, Sc "boundary values of R²".

- **S-3.3(c).** "change `phase_baseline_skill.per_target.CF_x.skill` by one ulp, leaving `runs` and `range` untouched, and assert the message names `phase_baseline_skill`."
  - **Fix:** adopted.
  - **Where:** viz, the defect list ("`phase_baseline_skill.per_target.CF_x.skill` changed by one ulp, with `runs` and `range` unchanged").

- **S-3.3(d).** "Say in task 2.1 that the per-seed error scales are per-seed parameters."
  - **Fix:** adopted.
  - **Where:** tasks 2.1 ("on per-seed predictions with per-seed error scales").

- **S-3.4, D-N2, T-R2-I12, M-N8.** "Give both literals in the spec. Make the rule constant seed-count-free … Define containment as case-insensitive and whitespace-normalised." The docs reviewer drafted `RULE_SENTENCE` as a `{n}` template and verified that it matches the README.
  - **Fix:** the docs reviewer's template is adopted. It is not seed-count-free in its output, but `{n}` comes from the data, so nothing is hard-coded. Both literals are now in the spec. Containment is whitespace-collapsed and case-insensitive. No README edit is needed.
  - **Where:**
    - viz, Req "…captions and labels…" (the `RULE_SENTENCE` literal and the `OWN_BASELINE_PHRASE` literal);
    - Sc "the README carries the shared constants";
    - tasks 4.1;
    - design D6.

- **S-3.5, D-N3, M-N7.** "SHALL NOT match `(?i)\b(chord|drag|normal|span|pitch|roll)\b`". The docs reviewer refined it so it also catches `spanwise` and `chordwise`.
  - **Fix:** the docs reviewer's pattern is adopted: `(?i)\b(?:(?:chord|span|drag|pitch|roll)\w*|normal)\b`.
  - **Where:** viz, caption Req ("Forbidden"); Sc "the forbidden-word pattern matches whole framings only"; tasks 4.1.

- **S-3.6.** "put [`skill = 1 − (RMSE / RMSE₀)²`] in the spec bullet for `error_histograms`."
  - **Fix:** adopted.
  - **Where:** viz, caption Req, `error_histograms` bullet.

- **S-3.7.** The same finding as G-N-B1; see above.

- **S-3.8.** "add a scenario 'a rebuilt baseline whose `reference_configs` differ … (compared as lists, not sets) is refused' … Task 3.1's non-contiguous `{0, 2}` … Add … 'an uninstalled package is recorded as `null`'."
  - **Fix:** all three are adopted.
  - **Where:**
    - viz, Sc "a baseline definition that differs is refused";
    - viz, the defect list ("a dataset whose wingbeats are `{0, 2}`");
    - fs, Sc "An uninstalled package is recorded as null";
    - tasks 1.1.

- **S-3.9, M-N6, T-I5 (partial).** "write one form: 'with `a` = recomputed `1 − R²` and `b` = recorded `1 − R²`, require `|a − b| ≤ 1e-12·max(1, |b|)`', and cite it from the other two places."
  - **Fix:** this is defined once as "tolerance form T" and cited everywhere. The design's earlier `max(1, |a|)` is corrected.
  - **Where:** viz, MODIFIED Req "…reproduce their source data exactly…" ("**Tolerance form T.**"); viz, Req "cycle-mean R² diagnostic" ("in form T"); design D4.

- **S-3.10.** "Add a short `### Why N instead of M?` note … explaining why the diagnostic now recomputes instead of reading `config_resolved` verbatim."
  - **Fix:** adopted.
  - **Where:** design D4, "Why recompute instead of 'read verbatim, never re-derived'?".

- **G-N-I2.** "the fix commit is red by design until the re-render commit lands; squash-merge hides it; do not push between the two."
  - **Fix:** adopted.
  - **Where:** tasks 11.3 (the three-step re-render); tasks 11.6 ("Check that the branch tip is green"); design D7.

- **G-N-I3.** "hash `ast.dump` … or add a rule that comments and docstrings are frozen after 8.2 … Write 10.3's README check first, in 8.2, so the constant wording is settled before any render."
  - **Fix:** the constants' README test moves before any render (to section 4). On granularity, raw-byte hashing is kept and stated: any byte change, a docstring included, forces a re-render. That is stricter than an AST hash, and a re-render costs seconds.
  - **Where:** tasks 4.1 ("README constants … This test sits here so the constants are final before any render"); design D6; design D7 ("Hashing raw bytes rather than an AST is the simpler and stricter choice").

- **G-N-I4.** "State this in D7 so the F3a session knows: '`train.py` changes are caught only if they change a number'."
  - **Fix:** adopted.
  - **Where:** design D7, "Imported code".

- **D-N4 (diagnostic caption false).** "Make that phrase per-figure: required in `skill_ranges` and `error_histograms`, replaced in the diagnostic by something true, for example `cycle-mean R² is computed on each grid's own six holdout configurations`."
  - **Fix:** adopted, with `<k>` read from the data.
  - **Where:** viz, caption Req ("`skill_ranges` and `error_histograms` SHALL also state…"; "`cycle_mean_r2_diagnostic` SHALL state instead…"); Sc "required and forbidden wording" ("the diagnostic caption does not contain `OWN_BASELINE_PHRASE`").

- **D-N5.** "Fix: the recipe and tasks 11.3 should render into a scratch directory (untracked, so `git diff HEAD` stays empty) and then copy the nine files over … Say this in D7 and in the README recipe."
  - **Fix:** adopted, for every render.
  - **Where:**
    - viz, Req "Committed comparison figures…", "Re-rendering";
    - tasks, Working rules ("Every render goes to an untracked scratch directory");
    - tasks 9.3, 9.6, 11.3;
    - design D7, D9.

- **D-N6.** "Add a one-line pointer after each block: 'then re-render the comparison figures (see Comparison figures)'."
  - **Fix:** adopted.
  - **Where:** design D9 (fine Regenerating pointer; coarse "Regenerating block gets the same one-line pointer"); tasks 10.2, 10.3.

- **D-N7.** "The bullet-slice start and end rules and the phrase check should all say 'after collapsing whitespace'."
  - **Fix:** adopted.
  - **Where:** fs, ADDED Req ("After its whitespace runs are collapsed to one space…"); tasks 10.1.

- **D-14, D-15** (round 1, previously unreconciled).
  - **D-14:** do not word the QS sentence as a resolution effect. It is now covered by the drafted bullet, which states both ratios, "stays above 1 on the fine grid" and no cause.
  - **D-15:** do not repeat the "equally tight" claim without a number. It is now covered by the proposal Background (M-I5).

- **M-N1, T-R2-I1.** "the sidecar records `rmse0` and `rmse_surrogate` as recomputed and `skill` verbatim …" (math). And from TDD: "the sidecar's `rmse0`, `rmse_surrogate` and `1 − skill` are the recomputed values, and `(rmse_surrogate/rmse0)²` equals that `1 − skill` to `rel=1e-12` … the recorded skill … stored separately as `skill_recorded`."
  - **Fix:** the TDD form is adopted. The identity is exact by construction, and `skill_recorded` is kept separately.
  - **Where:** viz, Req "error-histogram…" (the sidecar list); Sc "the recomputed skill is consistent with its two RMSEs"; design D3.

- **M-N2, T-R2-I10.** "the recorded skill set to `1 − (1 − skill)·(1 + 1e-8)` is refused, and to `1 − (1 − skill)·(1 + 1e-11)` is accepted" … "the `1 − skill` threshold test edits `phase_baseline_skill`, `runs[0]` and `range` together".
  - **Fix:** adopted. The annotation's source is pinned to `runs[0]` and `range`.
  - **Where:** viz, Sc "a recorded skill that does not reproduce is refused"; viz, error-histogram Req (annotation source); tasks 5.1.

- **M-N3, T-R2-I4.** "a verbatim per-seed `skill` value … and separately `rmse0` … moved by 1e-8 relative". And from TDD: "a per-seed `skill` (compared exactly) and, separately, an `eps` value (compared at `rel=1e-12`) moved by `1e-10` relative. Also list the committed-check tolerance for each sidecar key."
  - **Fix:** the TDD pair is adopted. Per-key tolerances are listed: exact for verbatim, counts, edges, strings and drawn states; `rel=1e-12, abs=0` for every other float.
  - **Where:** viz, Req "Committed comparison figures…" (the tolerance list); Sc "the check fails for each kind of staleness".

- **M-N5, T-S4.** "σ is recorded as computed (the fixture uses a dyadic constant …)."
  - **Fix:** adopted.
  - **Where:** viz, Sc "a null config-mean R² passes through as null" ("alternating `0.5 ± 1` … σ is recorded as computed, here exactly `0.0`"); tasks 2.1; design D4.

- **M-N9.** "Require every configuration's `wingbeat` set to equal `{0..N−1}` … Tie the lower bound to `train.CONVERGED_MIN_WINGBEAT` … Refuse duplicate `(config_name, time)` keys."
  - **Fix:** adopted.
  - **Where:** viz, shared guards 6 and 8; design D5.

- **M-N11.** "…equals the hand-computed RMS, compared as `ε²/σ²` against `1 − R²` within `1e-12·max(1, |1 − R²|)`."
  - **Fix:** adopted, in form T.
  - **Where:** viz, Sc "every seed is plotted…" ("the primary seed's measured `ε²/σ²` equals `1 − R²` in form T"); tasks 6.1.

- **M (task 6.1 threshold).** "`config_resolved.<c>.config_mean_r2` × (1+1e-10) on the K1 fixture (R² = 23/35 …) is refused; × (1+1e-14) is accepted."
  - **Fix:** adopted.
  - **Where:** viz, Sc "a recorded R² that disagrees with the recomputation is refused"; tasks 6.1; design D4.

- **T-R2-I2.** "Builders and `compute_*_metrics` take `root: Path` … `renderer_sources` is keyed by the fixed names … and hashed from the module's own location … Tests pass `root=tmp_path` and monkeypatch … `get_git_info`." The helper must also write the corpus-level `run_metadata.json` under `examples/prelim_sweep{,_fine}`.
  - **Fix:** adopted.
  - **Where:**
    - viz, Req "…validate their inputs…" (first paragraph);
    - viz, Req "Committed comparison figures…" (`renderer_sources` "read from those files' own locations (not from `root`) and keyed by those fixed names");
    - viz driver Req (`root=Path.cwd()`);
    - design D5;
    - tasks 2.1 (`write_repo`).

- **T-R2-I3.** "It checks `input_files` hashes before recomputing, and re-raises any `ValueError` from the library as `AssertionError` naming the figure and the role."
  - **Fix:** adopted.
  - **Where:** viz, Req "Committed comparison figures…" ("SHALL check the input hashes before any recomputation. It SHALL re-raise any `ValueError` …").

- **T-R2-I5.** "Move [one timestamp across the three] out of the `check_committed_figure` list into the repository test."
  - **Fix:** adopted.
  - **Where:** viz, Req "Committed comparison figures…" ("**The CI test.** … SHALL require one `timestamp` across the three"); tasks 9.2.

- **T-R2-I7.** "the key tree, with `per_config`'s configuration-name keys replaced by one wildcard and `inference`/`reproducibility` compared by key set."
  - **Fix:** adopted.
  - **Where:** tasks 2.2(a).

- **T-R2-I8.** "baseline RMSE `1.0` and skill `0.99` on `CF_x` …; σ `sqrt(5)` on `CF_y`, whose holdout truth is constant per configuration at `[0,0,0,0,0,6]`."
  - **Fix:** adopted verbatim.
  - **Where:** tasks 2.2(b).

- **T-R2-I9.** "The sidecar SHALL record every plotted value with its seed, the caption string, and per target the drawn state … per row the number of markers drawn, the bar `[lo, hi]` or `null`, and the `n/a` label."
  - **Fix:** adopted for `skill_ranges` and the diagnostic.
  - **Where:** viz, skill-range Req (sidecar list); viz, diagnostic Req ("the per-target drawn state (floor markers and `n/a` labels)").

- **T-R2-I11.** "Write out the K2 and K3 constructions in tasks 5.1 under a 'Known answers' bullet, and drop the bare K labels."
  - **Fix:** adopted. The K labels are kept only as headings next to their full constructions.
  - **Where:** tasks 5.1 "Known answers"; tasks 6.1 (K1 written out); viz scenarios (the 23/35 fixture written out).

- **T-R2-I12 (hard-coded 5).** "Replace it with `(<n> seeds: <lo> to <hi>)`. Add the 'hard-code 1234/5' mutant to sections 5 and 6 … and the `seed 42`/`3 seeds` cases to tasks 5.1 and 6.1."
  - **Fix:** adopted.
  - **Where:** viz, error-histogram Req (annotation); tasks 5.1, 6.1; tasks 7.4, sections 5 and 6.

- **T-R2-I13.** "Guards run in the listed order; each refusal test asserts the message of the first guard its defect trips."
  - **Fix:** adopted.
  - **Where:** viz, Req "…validate their inputs…" ("**in this order** … A test of a defect SHALL assert the message of the first guard the defect trips"); tasks 3.1.

- **Partial round-1 items, now closed.**
  - **S-I2:** the full defect list is in one scenario.
  - **S-I6:** the "Why recompute" note.
  - **T-B2:** see T-R2-I3, I4, I5.
  - **T-I1:** see T-R2-I7, I8.
  - **T-I2:** see T-R2-I9.
  - **T-I7:** see T-R2-B1.
  - **D-B1:** see D-N1.
  - **D-B2:** see D-N2.
  - **D-I5:** see D-N6.
  - **D-11:** design now opens with "where it lists something the spec also lists, the spec wins".
  - **D-12:** see S-3.4.

## SUGGESTIONS

**Adopted:**

- **G-S1:** 8.3 commit message.
- **G-S2:** 9.6 checks (`git show --stat`, and recorded commit equals `HEAD~1`).
- **D-S1:** proposal fragment.
- **D-S3:** coarse link target plus anchor test (tasks 9.2).
- **D-S4:** `inputs.file` named `coarse_metrics`.
- **D-S6:** fs wrap.
- **D-S7:** the two follow-up issues, tasks 0.3, filed with the user's approval.
- **M-N10:** "six orders of magnitude".
- **T-S1:** relative path in the `_portable_path` scenario.
- **T-S2:** floor markers, `subplots_adjust`, `read_bytes` (design D4, D5).
- **T-S3:** tick rule.
- **T-S5:** `numpy.diff(edges)`.
- **T-S6:** even row counts.
- **S-3.11:** the mixed scenario is split; `inputs.hash` and `figure` are in the checker list; the checker's test file is named; the row count is not hard-coded.

**Declined:**

- **D-S2 (shorter field note in the README):** the README now gives only the two non-obvious facts plus one line ("records its inputs and renderer").
- **D-S5 ("longer runs are planned"):** the user chose the regeneration wording, and it is emitted only while the corpus has 2 beats.
- **G-S3 (reorder docs after 7.5):** the stale command lines between 7.5 and 10.x affect no CI check, and the squash-merge hides them.
