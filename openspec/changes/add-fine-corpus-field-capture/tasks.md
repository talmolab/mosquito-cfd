## Tasks

> **Commit granularity**: within each section, "write test(s)" and "implement" checkboxes are
> separate tracking steps but land in the same commit — a commit with only a new failing test
> would leave `pytest -v` red on `main`'s history. **Exception**: within Section 4, tasks 15-16
> (CLI flags, fully test-covered) and tasks 17-18 (the real 27-config regeneration, a manual data
> update) are two SEPARATE commits, not one — so a bad regeneration (e.g. `--plot-int` needs
> adjusting once real storage cost is known) can be reverted/redone without touching the already-
> correct, already-tested generator code.

> **PR split** (rationale recorded in full in `design.md`'s Decision 7 — cite that, not Decision 3
> or 6, which are about different decisions): this change lands as two PRs, not one:
> - **PR A** (Sections 1-4, 6 except task 28, 7): `sweep.py`/`generate_full_corpus.py` parameter
>   threading, the real fine-corpus regeneration, manifest/provenance schema, module docstring, and
>   four of the spec delta's five requirements (all four MODIFIED requirements — everything except
>   the ADDED CC-F1 requirement, which belongs to PR B).
> - **PR B** (Section 5, and Section 6's task 28): the CC-F1 verification check + its thin CLI
>   driver + wiring it into `/submit-cluster-sweep`'s runbook. Section 5's own task 22 covers the
>   ADDED CC-F1 requirement's delta coverage; task 23 (Section 6) covers PR A's four MODIFIED
>   requirements — the check is split across the two PRs because neither PR alone can honestly
>   assert 1:1 coverage of the *other* PR's delta scenarios.
> **Ordering caveat — PR B is not fully independent of PR A**: task 28 (below) states the fine
> corpus "is no longer force-only" — true only once PR A has actually merged. PR B's own code
> (tasks 19-21) has zero dependency on PR A and can be reviewed in parallel, but **task 28 must not
> merge before PR A does**, even though its PR can be opened and reviewed in parallel. Both PRs go
> through `/review-pr` independently before merge; Section 7 (below) is deliberately not marked
> wholesale PR A or PR B — see its own text for why.
>
> **Do NOT run `openspec archive add-fine-corpus-field-capture` until BOTH PRs have merged.** The
> committed spec delta's ADDED "Field-capture plotfile velocity verification (CC-F1)" requirement
> is implemented entirely in PR B — if this change is archived after PR A merges but before PR B
> does, the live `openspec/specs/force-surrogate/spec.md` would assert CC-F1 exists with zero
> implementing code anywhere in the repo. Nothing mechanically enforces this ordering (a
> self-review round flagged that only PR-body prose currently says so) — this note is the
> enforcement mechanism until/unless a stronger one exists.

### 1. `render_inputs()` gains an `init_iter` parameter; `plot_int` becomes overridable [TDD] [PR A]

**Correction to this change's own earlier framing:** `render_inputs()` already has a
`plot_int: int = -1` keyword parameter today, and it already applies an override correctly when
called with one — that part is NOT new code. What's actually missing is (a) nothing ever calls it
with a non-default `plot_int`, which Section 2 fixes, and (b) `ns.init_iter` has no parameter at
all yet, which is genuinely new. Task 6 below only adds the `init_iter` parameter; `plot_int`
needs no signature change, only new test coverage confirming the already-existing behavior.

- [x] 1. Write `test_render_inputs_defaults_to_force_only`: call `render_inputs(base_text, ...)`
    with no `plot_int`/`init_iter` argument at all, assert `amr.plot_int == "-1"` and `ns.init_iter`
    unchanged from the base text — pins today's exact default behavior. Rename/rewrite the existing
    `test_render_inputs_forces_plot_int_minus_one` into this: `plot_int` is a *default*, not an
    unconditional *force*, now that Section 2 will call it with real overrides elsewhere.
- [x] 2. Write `test_render_inputs_accepts_plot_int_override`: call with `plot_int=100`, assert the
    generated file's `amr.plot_int == "100"` and no other targeted key changes. This exercises
    `render_inputs()`'s existing (not new) override path — the test is new, the code under test
    isn't.
- [x] 3. Write `test_render_inputs_accepts_init_iter_override`: call with `init_iter=2` (and
    `plot_int` at its default `-1`), assert `ns.init_iter == "2"` in the output, using a base
    fixture with `ns.init_iter = 0` so the rewrite is observable.
- [x] 4. Write `test_render_inputs_init_iter_none_preserves_base_value`: call with `init_iter=None`
    (the explicit default) against a base fixture with a non-zero `ns.init_iter` (e.g. `3`), assert
    the output still has `ns.init_iter == "3"` — proves `None` means pass-through, not "rewrite to
    zero."
- [x] 5. Write `test_render_inputs_missing_init_iter_key_raises_when_overridden`: a base fixture
    lacking an `ns.init_iter` line at all, call with `init_iter=2` supplied, assert `ValueError` —
    mirrors the existing missing-target-key guard already enforced for `amr.plot_int`, now applied
    consistently to the new optional key when it's actually requested.
- [x] 6. Implement: add **only** `init_iter: int | None = None` as a new keyword parameter to
    `render_inputs()` (the `plot_int: int = -1` parameter already exists — do not re-add it); add
    `ns.init_iter` to the replacement dict only when `init_iter is not None`. Run tasks 1-5 to
    green; confirm every other pre-existing `render_inputs`/`generate_sweep` test still passes
    unmodified.

### 2. `generate_sweep()` threads both parameters through, at both hardcode sites [depends: 1] [PR A]

`generate_sweep()` currently hardcodes `plot_int=-1` at **two independent sites** — its per-config
call to `render_inputs()`, and (separately) its manifest-building `config_records` dict, which
writes a literal `"plot_int": -1` regardless of what was actually rendered to the deck. Both must
be un-hardcoded together; fixing only the `render_inputs()` call site would leave the manifest
wrongly claiming `-1` for decks that actually got `plot_int=100`.

- [x] 7. Write `test_generate_sweep_defaults_are_byte_identical_to_before`: following the same
    pattern as the coarse corpus's existing `test_committed_sweep_matches_regeneration` (byte-
    identity regression test, not a spot-check), call `generate_sweep()` with no `plot_int`/
    `init_iter` argument against the existing coarse base deck and assert every generated file is
    byte-identical to the already-committed coarse corpus output. This is the load-bearing
    regression pin proving the coarse corpus's own generation is completely unaffected by this
    change — no hedging ("or, equivalently, assert every key matches") is acceptable here, since a
    byte-diff can catch things a per-key assertion misses (whitespace, line-ending, ordering).
- [x] 8. Write `test_generate_sweep_threads_plot_int_and_init_iter_to_every_config`: call with
    `plot_int=100, init_iter=2`, assert every one of the 27 generated decks has both values, **and**
    every one of the 27 manifest `config_records` entries also has both values (this is the
    regression test for the second hardcode site — Section 3 covers the dedicated manifest-schema
    tests, but this task's assertion is what actually proves the two sites agree with each other).
- [x] 9. Write `test_generate_sweep_plot_int_override_alone_leaves_init_iter_at_default`: call with
    only `plot_int=100` (`init_iter` omitted). Assert every deck's `amr.plot_int == "100"` **and**
    `ns.init_iter` unchanged from the base, **and** every manifest record's `"plot_int"` is `100`
    while the record has no `"init_iter"` key at all. This closes a real seam a combined-override
    test (task 8) cannot see: a wiring bug that only threads one parameter when the other is also
    supplied would pass task 8 but fail here.
- [x] 10. Write `test_generate_sweep_init_iter_override_alone_leaves_plot_int_at_default`: call with
    only `init_iter=2` (`plot_int` omitted). Assert every deck's `ns.init_iter == "2"` **and**
    `amr.plot_int == "-1"` (the default, unchanged), **and** every manifest record's `"init_iter"`
    is `2` while `"plot_int"` is still `-1`. Mirrors task 9 for the other parameter.
- [x] 11. Implement: add `plot_int: int = -1, init_iter: int | None = None` parameters to
    `generate_sweep()`; thread `plot_int` and `init_iter` into (a) the per-config `render_inputs()`
    call (removing the hardcoded `plot_int=-1` literal there) and (b) the `config_records` dict
    construction (removing the separately hardcoded literal `"plot_int": -1` there too — do not fix
    only one site). Run tasks 7-10 to green; run the full existing `tests/test_force_surrogate_sweep.py`
    and `tests/test_full_corpus_deck.py` suites and confirm every pre-existing test passes unmodified
    (the coarse corpus's own tests must show zero diff).

### 3. Manifest and provenance schema extension [depends: 2] [PR A]

This section implements the new MODIFIED delta scenarios "Field-capture override is recorded in
the manifest and provenance, force-only omits both" and "Default (force-only) generation omits the
field-capture fields entirely" in `specs/force-surrogate/spec.md`'s "Reproducible sweep manifest
with units sidecar" requirement.

- [x] 12. Write `test_manifest_records_init_iter_per_config`: generate with `init_iter=2`, assert
    every config's manifest record has `"init_iter": 2` (mirroring the existing `"plot_int"`
    field). Also assert the default case (`init_iter=None`): the manifest record has **no**
    `"init_iter"` key at all (per the spec delta's explicit choice — omit, don't record `null`).
- [x] 13. Write `test_provenance_records_field_capture_block`: generate with `plot_int=100,
    init_iter=2`, assert `sweep_provenance.json` has a new `"field_capture": {"plot_int": 100,
    "init_iter": 2, ...}` block. Also test the default case: no override → no `field_capture` block
    at all in `sweep_provenance.json`.
- [x] 14. Implement the manifest/provenance schema additions in `generate_sweep()`. Run tasks 12-13
    to green; confirm `tests/test_full_corpus_deck.py::test_fine_corpus_provenance_flags_superseded_runs`
    still passes unmodified (the existing `superseded_by` block describing the vb8t5/retry-failed-trz9k
    staleness is untouched by this addition — it's a different, coexisting top-level key, not a
    field this change has any reason to alter).

### 4. `generate_full_corpus.py` CLI flags + regenerate the fine corpus [depends: 3] [PR A]

- [x] 15. Write `test_generate_full_corpus_cli_accepts_plot_int_and_init_iter_flags`: invoke
    `generate_full_corpus.py`'s CLI (subprocess or `uv run --isolated`, matching this repo's
    existing CLI-test pattern) with `--plot-int 100 --init-iter 2` against a scratch output
    directory, assert the generated decks reflect both values. **Write and pass this test before
    task 17's real regeneration** — it is the thing that actually proves the new flags are wired
    to `generate_sweep()`'s new parameters, rather than discovering the wiring is broken only after
    the real 27-config regeneration has already overwritten the committed corpus.
- [x] 16. Add `--plot-int` (`type=int, default=-1`) and `--init-iter` (`type=int, default=None`)
    CLI arguments to `examples/prelim_sweep_fine/generate_full_corpus.py`'s `main()`, threaded to
    the `generate_sweep()` call. Run task 15 to green. **Commit tasks 15-16 together, separately
    from tasks 17-18** (see the commit-granularity note at the top of this file).
- [x] 17. Regenerate `examples/prelim_sweep_fine/` for real: run `generate_full_corpus.py
    --plot-int 100 --init-iter 2 --timestamp <fresh ISO-8601 timestamp>`. Confirm via `git diff
    --stat` that exactly `examples/prelim_sweep_fine/inputs/*.3d.*` (27 files), `sweep_manifest.json`,
    and `sweep_provenance.json` changed. **`sweep_manifest.units.json` should NOT appear in this
    diff** — it records units metadata for manifest fields, not per-run values, and neither
    `plot_int` nor `init_iter` is a unit-bearing quantity; if it does change, that's a sign the
    implementation touched something it shouldn't have — investigate before proceeding, don't
    assume it's expected. Spot-check 2-3 generated decks by hand: `amr.plot_int = 100`,
    `ns.init_iter = 2`, every other key (including the corrected hinge from
    `fix-force-surrogate-sweep-hinge`) unchanged from the pre-regeneration committed decks.
- [x] 18. The 27 already-committed (but never-CFD-run) `run_metadata_<config>.json` files under
    `examples/prelim_sweep_fine/` still describe the old, hinge-buggy, force-only, superseded
    `vb8t5`/`trz9k` runs — confirm they are untouched by this regeneration (they describe pod-side
    run output, not deck content, so this is a decks-only regeneration and does not touch them) and
    that this is still accurately reflected by `sweep_provenance.json`'s existing `superseded_by`
    block sitting alongside the new `field_capture` block from task 14. Commit tasks 17-18 together,
    as the second, separate commit for this section.

### 5. CC-F1 non-zero-velocity check [depends: none — independent of Sections 1-4] [PR B]

Module home decided in `design.md`'s Decision 6 — pinned now, not left to implementation-time
judgment: extends `mosquito_cfd.benchmarks.stress_integral` (co-locating the check with the
`extract_eulerian_box` reader it depends on; CC-F2 already flags a second reader as redundant),
plus a thin `scripts/check_plotfile_velocity.py` CLI driver for direct operator use.

- [x] 19. Write `test_velocity_check_passes_on_nonzero_field`: run the check against the existing
    committed synthetic AMReX plotfile fixture (`tests/fixtures/lev_boxlib_plt`, issue #33), which
    has genuine non-zero `x_velocity` — assert it passes. **Scope the check to `x_velocity`
    specifically, not "every velocity component is non-zero"**: this same fixture has a
    legitimately-zero `z_velocity` everywhere (solid-body rotation in the x/y plane), and a naive
    all-components check would false-positive-reject this real, valid fixture.
- [x] 20. Write `test_velocity_check_raises_clear_error_on_all_zero_x_velocity`: a fixture or
    monkeypatched variant with an all-zero `x_velocity` array (leaving other components as-is),
    assert the raised error names the `ns.init_iter=0` defect by name (e.g. references
    `RESULTS.md`'s documented zero-velocity-at-init_iter=0 bug), not a generic assertion message —
    so an operator seeing this error during a real smoke run immediately knows what to check.
- [x] 21. Implement the check in `mosquito_cfd.benchmarks.stress_integral`, built on the existing
    `extract_eulerian_box` (no new plotfile reader). Add the `scripts/check_plotfile_velocity.py`
    CLI driver, mirroring this repo's existing thin-driver convention (e.g.
    `scripts/extract_forces.py` around `force_surrogate` library code), so an operator can run it
    directly against a real smoke-run plotfile during `/submit-cluster-sweep`'s Step 2. Run tasks
    19-20 to green.
- [x] 22. Confirm the ADDED "Field-capture plotfile velocity verification (CC-F1)" requirement's
    three scenarios in `specs/force-surrogate/spec.md` each map 1:1 to a test from tasks 19-20 —
    this is the PR-B half of the delta-coverage check; task 23 (Section 6, PR A) covers the other
    half.

### 6. Spec delta, docstrings, and downstream doc updates [PR A unless noted]

- [x] 23. Confirm each of the spec delta's **four MODIFIED** requirements — "Force-only input
    generation with minimal diff," "Reproducible sweep manifest with units sidecar," "Cluster-free
    injected executor seam (force-only)," and "Cluster-side Argo orchestration of the corpus" — has
    every one of its scenarios mapped 1:1 to a test from Sections 1-4 (1:1 check, not assumed).
    This is the PR-A half of the delta-coverage check split from task 22 above: PR A's own tests
    (Sections 1-4) don't need Section 5 to exist to verify these four requirements, and PR B's
    Section 5 tests can't verify these four either — each PR can only honestly check its own half.
    [PR A]
- [x] 24. Update `sweep.py`'s module docstring: the "Force-only (D6)" framing needs to describe the
    new optional field-capture parameters, not just restate the old unconditional force. [PR A]
- [x] 25. Update `docs/field_surrogate/roadmap.md` at **all four** locations that reference "the
    follow-on change to `fix-force-surrogate-sweep-hinge`" by description rather than by change-id
    (verified as exactly four, no more, no fewer, via a full-file grep for "follow-on"):
    - The Sequencing note (paragraph starting "Rather than pay for a second full regeneration
      later...").
    - The CC-F3 "Superseded 2026-08-10" callout.
    - The F1 row's "Status" cell in the PR/issue split table ("subsumed by the full-corpus
      field-capture run in the follow-on change to...").
    - The "Dependency order" sentence ("F2 onward now depend on the follow-on change to...").
    Give all four their actual change-id (`add-fine-corpus-field-capture`) now that it exists. Do
    NOT mark F1-F6 as started/complete in the process — this change is decks/generator-code only,
    not F2 (reader) or later. [PR A]
- [x] 26. Update `openspec/project.md` at **two separate, unrelated locations** (do not conflate
    them into one edit):
    - The **Pending** section (~line 157): note that the fine corpus's decks now include field
      capture (`plot_int=100`, `init_iter=2`), so the pending cluster resubmission's deliverable is
      both the corrected-geometry force data AND field-capture plotfiles in one run.
    - The **Visualization Tooling** section's "Mid-sweep partial-corpus check" note (~lines
      327-349): this note currently asserts "every deck's `amr.plot_int` is forced to `-1` by
      `generate_sweep()`... force-only by design," citing both `openspec/specs/force-surrogate/spec.md`
      and `cluster/argo/README.md`'s "Force-only (CC-6)" note as sources — a documentation-review
      finding this task list's earlier draft missed entirely (it is a separate block of the same
      file from the Pending section above, easy to overlook as "already covered"). Update it to be
      accurate for the fine corpus post-regeneration; the CSV/force-based mid-sweep check itself
      stays valid either way (per the existing note's own reasoning). [PR A]
- [x] 27. Update `cluster/argo/README.md`'s "## What the workflow guarantees" section — the line
    "**Force-only (CC-6).** The workflow produces the per-config IB-particle CSV corpus only" is a
    documentation-review finding this task list's earlier draft also missed. The workflow's own
    steps genuinely still only ever read/write the IB-particle CSV regardless of what the submitted
    corpus's decks contain (this doesn't change), but the wording should be clarified so a reader
    doesn't take "Force-only" as "no corpus this workflow runs will ever produce plotfiles" — mirror
    the workflow-agnostic wording already used in this change's own spec delta for "Cluster-side
    Argo orchestration of the corpus." [PR A]
- [x] 28. Update `.claude/commands/submit-cluster-sweep.md` at two points, and this task **must not
    merge before PR A**, even though it can be reviewed alongside PR B's other tasks (see the
    ordering caveat in the PR-split note at the top of this file):
    - Step 0's framing and the Common Mistakes table row about reaching for `make_flow_video.py`:
      the fine corpus is no longer force-only after PR A lands (only the coarse corpus is). Update
      the "Every deck in both corpora forces `amr.plot_int = -1`" claim to be accurate
      post-regeneration. The CSV/force-based mid-sweep check (Step 4) remains fully valid
      regardless — it never depended on the force-only property, only on the fact that a
      video-based check couldn't work when no plotfiles existed at all.
    - **Add an explicit Step 2 instruction** telling the operator to run
      `scripts/check_plotfile_velocity.py` (task 21) against the smoke config's plotfile before
      proceeding to `full` — this is the actual integration point the CC-F1 check was built for
      (design.md Decision 4); without this, PR B would ship a tested, reusable script the runbook
      never tells anyone to invoke. [PR B, but see the merge-ordering note above]

### 7. Validation [not wholesale PR A or PR B — see below]

Section 7 is deliberately not tagged as belonging entirely to one PR: PR A and PR B are reviewed
and merged independently, and each needs its own passing validation at merge time, plus a final
combined check once both are on `main`.

- [x] 29. Run `openspec validate add-fine-corpus-field-capture --strict` and resolve any issues.
    Run once per PR at merge time (the change isn't archived until both land, so this can be
    re-run cheaply either way).
- [x] 30. Run `uv run ruff check` / `uv run ruff format --check` on every touched file (repo-wide,
    matching CI's exact invocation, not just the touched files) — once for PR A's diff, once for
    PR B's diff.
- [x] 31. Run the test suite (`uv run pytest -v -m "not gpu"`) **twice, at different times**:
    - **At PR A's merge**: confirm every pre-existing test passes unmodified alongside the new ones
      from Sections 1-4, with particular attention to `tests/test_force_surrogate_sweep.py`,
      `tests/test_full_corpus_deck.py`, and `tests/test_fine_pilot_deck.py` (the three files flagged
      during codebase exploration as having tests that pin exact current values PR A touches).
      Section 5's tests do not exist yet if PR B hasn't merged — do not expect them.
    - **At PR B's merge**: confirm Section 5's new tests pass, plus a full re-run confirming nothing
      in PR A's already-merged code regressed.
    - **Once both are on `main`**: one final combined run, plus confirming task 22's and this
      task's own delta-coverage checks (split across Sections 5 and this note) together account for
      every scenario in the full spec delta — the check that an earlier draft of task 20 tried to
      do in one shot before the PR split made that impossible to do honestly from either PR alone.
    - **Status**: implementation for both PRs' content landed together pre-split on this branch;
      one combined `pytest -v -m "not gpu"` run against all of it passed (822 passed, 14 skipped,
      6 deselected, 0 failed) before the branch was split into PR A/PR B commits below. The
      per-PR-merge and final-combined re-runs above are re-run at actual merge time on GitHub, not
      skipped — this status note records that the code was never green-lit unverified.
