# Reconciliation, review round 1: share-light-corpus-helpers

Round-1 reviewers:

- 1, spec quality (sonnet);
- 2, TDD (opus);
- 4, docs (sonnet);
- 5, git (sonnet).

Two were skipped:

- 3, CI/CD: there is no workflow, Dockerfile, `build-args.env`, `pyproject.toml` or `uv.lock`
  change.
- 6, Math & Physics: no physical, numerical or statistical value is added, changed or relied on.

Each entry below gives the finding (quoted), how it is addressed, and where.

## BLOCKING

**B1 (Subagent 1, B-1).** "Five other requirements and one other spec still say a digest
'containing `sha256:`' is sufficient… `heaving-ellipsoid-validation/spec.md:89, 99, 104` … **not
listed in Impact at all** … add MODIFIED blocks for these requirements, or add one ADDED requirement
stating that every 'digest containing `sha256:`' in this capability means an `is_pinned_image_ref`
reference. Add `heaving-ellipsoid-validation` to Impact."

- **Addressed.** The reviewer's second option is used for `force-surrogate`. MODIFYing all seven
  requirements would collide with F3a and `fix-stale-spec-claims`, which both MODIFY "Committed
  evidence-figure artifacts with provenance" (design D8, E3). The first option is used for
  `heaving-ellipsoid-validation`, which no parallel change touches.
- **Where:**
  - `specs/force-surrogate/spec.md`, ADDED "Image digest wording throughout this capability means a
    digest-pinned reference". Its text reads "The accepted image value SHALL be exactly a reference
    for which `mosquito_cfd._provenance.is_pinned_image_ref` is true, wherever … 'containing
    `sha256:`'…". It names the six requirements and carries the scenario "A bare digest does not
    satisfy a 'containing sha256:' requirement".
  - New `specs/heaving-ellipsoid-validation/spec.md`, MODIFIED CC-V3 (all three `sha256:` mentions).
  - `proposal.md` Impact, which lists both.

## IMPORTANT

**I1 (Subagent 1 I-1; Subagent 4 §1).** "`docs/CHANGELOG.md` is edited per task 6.3 but is not in
Impact's 'Affected code' … `cluster/argo/workflows/force-surrogate-sweep.yaml` is not listed."

- **Addressed.** Impact lists `docs/CHANGELOG.md`. A new "Behavior changes with no edit" line names
  the Argo YAML and says the PR body carries the full caller grep. The enumeration that would go
  stale is dropped, as Subagent 4's DRY suggestion asked.
- **Where:** `proposal.md` → Impact.

**I2 (Subagent 1 I-2; Subagent 4 §4).** "The 'Why' does not follow the 1-2 sentence rule … Move the
measurements and bullets to design.md Context."

- **Addressed.** Why is now a short paragraph, and the measurements, audit and parallel-work check
  moved to design.md.
- **Where:** `proposal.md` → Why; `design.md` → Context and Evidence E1–E3.

**I3 (Subagent 1 I-3).** "The 'wrongly typed git provenance is a ValueError' scenario is a
cross-product … Split into three scenarios … Also pin the message for the non-string cases."

- **Addressed.** It is split into four scenarios: pod `git` block, override, override-first and
  pod-file top level. Each message must contain the value's `repr`.
- **Where:** `specs/run-metadata/spec.md`:
  - "a wrongly typed pod-side git block is a ValueError";
  - "a wrongly typed override is a ValueError";
  - "a valid override never reads the pod's git block";
  - "a pod-side file whose top level is not an object is a ValueError";
  - the requirement text "its message SHALL contain the offending value's `repr`".

**I4 (Subagent 1 I-4).** "`docker_image` absent or `None` … `git` key absent entirely … missing file
… `FileNotFoundError`, but no scenario covers it … `validate_image_digest` on `bytes`."

- **Addressed.**
- **Where:**
  - `specs/run-metadata/spec.md` "malformed digest is rejected" (`null`, "no `docker_image` key at
    all") and "a wrongly typed pod-side git block" ("absent");
  - `specs/force-surrogate/spec.md` "A missing manifest is still FileNotFoundError", and the
    loosely-formed scenario now includes `b"ghcr.io/x@sha256:" + b"a" * 64`;
  - the run-metadata pod-file scenario ("a path that does not exist still raises `FileNotFoundError`").

**I5 (Subagent 1 I-5; Subagent 2 suggestion).** "only 2 are asserts … the other 2 hits are
comments" / "`test_flow_video.py:53`, `test_kinematics_video.py:49`, `test_force_surrogate_driver.py:280`,
`test_force_surrogate_run_one_config.py:305` match `"sha256"`, and `test_metadata_capture.py:294`
matches `"digest"` … Either require `sha256` and `digest` too, or list these tests."

- **Addressed.** The miscount is gone from the proposal. The spec now requires all three
  substrings, and design D5 lists the tests that depend on them.
- **Where:** `specs/force-surrogate/spec.md`, "The message SHALL contain the substrings
  `content-addressable`, `sha256` and `digest`"; `design.md` D5.

**I6 (Subagent 1 I-6).** "No test matches that string … Reword."

- **Addressed.** The sentence was removed when the Risks section was rewritten.
- **Where:** `design.md` → Risks.

**I7 (Subagent 2 #1).** "The spec over-claims that manifest messages are unchanged … an object
manifest holding a 5000-digit integer … A non-UTF-8 manifest raises bare `UnicodeDecodeError` today
… carve the int-digit case out … add the narrowing mutant."

- **Addressed.** The parity boundary is stated explicitly: object top level, valid UTF-8, JSON the
  parser accepts. The int-digit, non-UTF-8 and nesting cases are listed exceptions, each with a
  pinned prefix. Non-UTF-8 now raises `ValueError` "is not valid UTF-8". The narrowing mutant is
  added.
- **Where:**
  - `specs/force-surrogate/spec.md` ADDED manifest requirement ("Error messages SHALL be unchanged
    for every manifest that meets all of the following…") and the scenario "Unparseable manifests
    are reported as invalid JSON or invalid UTF-8";
  - `design.md` D4 "Parity boundary";
  - `tasks.md` 2.2 (`test_unparseable_manifest_is_a_value_error`);
  - `tasks.md` 5.2 ("narrow the except to `(json.JSONDecodeError, RecursionError)`").

**I8 (Subagent 2 #2).** "Most 2.2 behavior tests fail on `ModuleNotFoundError`, not on the behavior …
Write both against `force_surrogate.dataset.load_manifest_configs` first."

- **Addressed.**
- **Where:** `tasks.md` 2.2's heading ("Red, written against
  `force_surrogate.dataset.load_manifest_configs`"), with the per-test expected reds.

**I9 (Subagent 2 #3).** "`test_field_and_force_paths_raise_the_same_manifest_error` passes on old code
unless it asserts the type … the missing-`reynolds` case is an anchor."

- **Addressed.**
- **Where:**
  - `tasks.md` 2.3 ("each give `type(e) is ValueError` with equal messages. Before this commit the
    top-level-`5` case is red (`TypeError` on both paths)");
  - `specs/field-surrogate/spec.md` ("both raise exactly `ValueError` (`type(e) is ValueError` on
    each path)").

**I10 (Subagent 2 #4).** "The subprocess child can import the wrong source tree … Follow the existing
pattern (`tests/test_field_surrogate_snapshot.py:53`) — inherited env, `cwd=REPO_ROOT` — and have the
child print `mosquito_cfd.__file__`."

- **Addressed.**
- **Where:**
  - `design.md` D7 (`env=os.environ | {"PYTHONPATH": str(SRC)}`, `cwd=REPO_ROOT`, and the child
    prints `{"file": mosquito_cfd.__file__, …}`, which the parent checks);
  - both field-surrogate subprocess scenarios ("the interpreter's `mosquito_cfd.__file__` lies in
    the source tree under test").

**I11 (Subagent 2 #5).** "Widening the repository class `[a-z0-9._/:-]*` to `.*` or `\S*` survives …
Add `"ghcr.io/X@sha256:"`, `"ghcr.io/x y@sha256:"`, `"ghcr.io/x:latest #@sha256:"`, `"@sha256:"`,
`"ghcr.io/x@sha256:"+"A"*64` … `"g"*40`."

- **Addressed.** All six values are added, plus `"repo@sha256:"+"a"*63` and `"a"*41`. The widening
  mutant is added.
- **Where:** `specs/field-surrogate/spec.md`, the predicate scenario; `tasks.md` 1.2; `tasks.md` 5.1
  ("the repository class → `.*`").

**I12 (Subagent 2 #6).** "`validate_image_digest: return value.strip()` cannot be killed … Mark it
equivalent."

- **Addressed.**
- **Where:** `tasks.md` 5.3 → "Equivalent mutants to record, not hunt".

**I13 (Subagent 2 #7).** "The override path should never read the pod's `git` block … Add a test
`resolve_git_info({"git": None}, git_commit_override="b"*40)` and `resolve_git_info({}, …)` … add a §5
mutant that type-checks `git` before the override branch."

- **Addressed.**
- **Where:**
  - `specs/run-metadata/spec.md` "a valid override never reads the pod's git block" and the
    requirement sentence "A valid override SHALL be checked and returned before the pod's `git`
    block is read at all";
  - `tasks.md` 3.1 (the override-first anchors) and 5.3 ("type-check `git` before the override
    branch");
  - `design.md` D6.

**I14 (Subagent 2 #8).** "`"git": [["commit","a"*40]]` passes today via `dict(...)` coercion … Add it …
and a §5 mutant keeping `dict(git)` coercion."

- **Addressed.**
- **Where:**
  - `specs/run-metadata/spec.md` "a wrongly typed pod-side git block" (`[["commit", "a" * 40]]`,
    "The list of pairs is refused, not coerced to a dict");
  - `tasks.md` 3.1 and 5.3 ("keep the `dict(git)` coercion").

**I15 (Subagent 2 #9).** "`"git": ["x"]` and `"git": "abc"` already raise `ValueError` today … So does
`extract_docker_image` with `docker_image` absent. These are anchors, not reds."

- **Addressed.**
- **Where:** `tasks.md` 3.1 ("Anchors: `"git": ["x"]` and `"git": "abc"`") and 4.1
  ("`docker_image` absent (anchor: already `ValueError`)").

**I16 (Subagent 4 §1, item 1).** "Argparse `help=` strings say 'Pinned sha256: image digest (mutable
tags rejected).' … The task-4.2 grep … will NOT find any of these."

- **Addressed.** I verified all eight with `grep -n "help=.*sha256" scripts/*.py`. Task 4.3 rewrites
  them, using the reviewer's suggested text, and the grep is widened.
- **Where:** `tasks.md` 4.3 (all eight file:line targets, and the widened grep
  `'sha256: image digest|sha256 container digest|…'`); `proposal.md` → Impact (the scripts list).

**I17 (Subagent 4 §1, item 2).** "`sidecar.py:29-36` … `:118-139` … `:155-164` … need explicit
rewrites. `:129` 'Returns: The stripped digest' is the most likely to be missed" / "`metadata_capture.py:22`
… and `:512`/`:515`."

- **Addressed.**
- **Where:** `tasks.md` 4.2 (the `sidecar.py:118–139` and `:155–164` docstrings, "no 'Returns: The
  stripped digest'", and `metadata_capture` `:505–516` and `:22`, with the replacement sentence).

**I18 (Subagent 4 §1, fixture README).** "The proposal is factually wrong here … line 11 has
`"image_digest": "sha256:f546ead9…"` … the README is therefore literally correct … the repo is
documented in `docs/force_surrogate/fine-grid-pilot-report.md:48`. No git-log hunt is needed."

- **Addressed.** I verified both by reading the files (`run_metadata_s35_f085_p45.json:11` and
  `fine-grid-pilot-report.md:48`). The audit text is corrected, and the git-log hunt is dropped.
- **Where:** `design.md` E2 (the paragraph after the table); `tasks.md` 4.2 (the README sentence).

**I19 (Subagent 4 §1).** "`docs/CHANGELOG.md:16` … will name a path that no longer exists."

- **Addressed.**
- **Where:** `tasks.md` 6.6 ("Correct line 16's `field_surrogate/_provenance.py` to
  `mosquito_cfd/_provenance.py`"); `tasks.md` 1.3 for the `_provenance` module docstring.

**I20 (Subagent 4 §2).** "The exact regex is restated in the deltas … Fix: define each pattern once
(field-surrogate delta) and have the others say 'a `str` that satisfies
`mosquito_cfd._provenance.is_pinned_image_ref`'."

- **Addressed.** The regexes now appear only in the field-surrogate requirement, which carries the
  original PR #169 text. The `force-surrogate` and `run-metadata` deltas refer to the predicates and
  to that requirement.
- **Where:**
  - `specs/force-surrogate/spec.md` ("`validate_image_digest(value)` SHALL accept exactly the values
    for which `mosquito_cfd._provenance.is_pinned_image_ref(value)` is true. That rule is defined in
    the `field-surrogate` capability…");
  - `specs/run-metadata/spec.md` (both requirement texts).

**I21 (Subagent 4 §2).** "The 'previously accepted X, now refused' list is repeated … the proposal's
BREAKING block should be the only canonical list, and the spec delta lines should be 1 sentence."

- **Addressed.** Each delta carries a one-sentence `**BREAKING:**` marker; the full list is in
  `proposal.md`.
- **Where:** `specs/force-surrogate/spec.md` and `specs/run-metadata/spec.md` (the BREAKING
  sentences).

**I22 (Subagent 4 §5).** "Add the line: '`docker_image` is recorded exactly as the pod wrote it…' to
the `metadata_capture.py` module docstring."

- **Addressed.**
- **Where:** `tasks.md` 4.2 ("the module docstring's `docker_image` line (`:22`): '`docker_image` is
  the pod's digest-pinned reference … recorded exactly as the pod wrote it.'").

**I23 (Subagent 5 I1).** "Section 1 mixes a rename with a rewrite … make the pure move its own
commit … Check the move commit with `git show -M --stat` and confirm it shows 100% similarity."

- **Addressed.**
- **Where:** `tasks.md` 1.1 ("Verify with `git show -M --stat HEAD` that the commit shows
  `_provenance.py` renamed at **100%**"); `design.md` D1.

**I24 (Subagent 5 B1).** "verify this with an actual fresh-interpreter run in commit 1, not by
reading."

- **Addressed.** The moved fresh-interpreter test runs in commit 1.1, which is the pure move. I also
  read `mosquito_cfd/__init__.py`, which holds only `__version__`.
- **Where:** `tasks.md` 1.1 (the moved `test_reading_provenance_loads_no_force_surrogate_stack`).

**I25 (Subagent 5 I2).** "You can safely split off a prior commit that only creates `_manifest.py` and
re-exports it from `dataset.py` … The `corpus` switch plus the test retargeting then go together."

- **Addressed.**
- **Where:** `tasks.md` 2.3 ("`corpus.py` is **untouched** in this commit") and 2.4 ("`FieldCorpus`
  switch (atomic)", with all patch retargets in the same commit).

**I26 (Subagent 5 I3).** "Section 4 must be one commit … Split the docs and instruction sweep … into
its own `docs:` commit."

- **Addressed.**
- **Where:** `tasks.md` 4.2 ("(atomic)", covering the code, fixture and tests) and 4.3 (the docs and
  help-text sweep, with its own commit title).

**I27 (Subagent 5 I4).** "Spec-delta overlap with parallel changes … Re-run `openspec validate
--strict` after `git merge origin/main`."

- **Addressed.** I checked that no parallel change MODIFIES a requirement this change touches (design
  E3), and the change avoids MODIFYing the shared one (D8).
- **Where:** `tasks.md` 6.5 ("`git merge origin/main` … `openspec validate --strict`") and 6.6.1;
  `design.md` E3 and D8.

**I28 (Subagent 5 I5).** "Tell the F3a worktree owner before merging."

- **Addressed.**
- **Where:** `tasks.md` 6.8 ("mention F3a's worktree owner, because `validate_image_digest` tightens
  under their callers too").

**I29 (Subagent 5 I6).** "Make the `validate_image_digest` error message include the expected form
`ghcr.io/<repo>@sha256:<64hex>` … state in the PR body …"

- **Addressed.**
- **Where:** `design.md` D5 (the message names `'<repo>@sha256:<64 hex chars>'` with the
  `ghcr.io/talmolab/mosquito-cfd@sha256:...` example); `specs/force-surrogate/spec.md` ("SHALL name
  the expected `<repo>@sha256:<64 hex>` form"); `tasks.md` 6.8 (the PR-body rollout note).

## Suggestions taken

- `pyarrow` added to the forbidden sets, a `_manifest`-only child, and an AST check of `corpus.py`.
- `importlib` and `__import__` refused in the stdlib AST check.
- The re-export through `mosquito_cfd.force_surrogate`, and a `build_dataset` patch test.
- An end-to-end CLI bare-digest test.
- The name-import and local-copy mutants.
- The "do not touch" diff check (6.4), a Linux run (6.3), and `uv run ruff`.
- The mutation table as its own late commit, run at the final code SHA.
- The CHANGELOG `**BREAKING:**` / `**BREAKING (minor):**` style.
- The Opus 5.5 trailer. The git reviewer wrote "Sonnet 5.5", which is incorrect for this session.

## Suggestions not taken (with reasons)

- **S-1, rename the change ID.** It is verb-led and the user named the worktree after it; a rename
  churns the branch.
- **S-2, move the predicate contract into run-metadata.** The predicates live in `_provenance`, whose
  requirement is in field-surrogate; the other capabilities cross-reference it (I20).
- **S-6, commit the audit script.** A committed test that iterates the run-metadata files would need
  an allowlist for the T3c and pilot files. Task 6.2 re-runs the audit with the shipped predicates
  instead.
- **Trim `tasks.md` Conventions.** These are the user's explicit per-change constraints and are kept
  in one place on purpose.
- **Out of scope, with a follow-up issue:** the `RecursionError` from a deeply nested pod-side
  `run_metadata.json` (Subagent 2), stated as out of scope in the run-metadata requirement. The
  issue is filed in task 6.1.

## Round 2 (adversarial verification of the round-1 fixes, opus)

Of the 29 round-1 entries, 22 were VERIFIED and 5 were PARTIAL (I2, I10, I15, I16, I23). There were
also 7 new IMPORTANT findings and 8 suggestions. All are addressed below.

- **I2 PARTIAL** ("Why is still 5 sentences"). It is now 2 sentences. Where: `proposal.md` → Why.
- **N1 / I15** ("Several 'anchors' in tasks 3.1/4.1 are red under the spec's own repr-in-message
  requirement"). Addressed:
  - `["x"]`, `"abc"`, absent `git` and absent `docker_image` are reclassified as reds, each with its
    probed reason.
  - An absent key reports as `None`.
  - Where:
    - `tasks.md` 3.1 ("Red: already a `ValueError`, but its message says `got ''`, not `None`"; the
      `dict()` message "has no `repr` of the value") and 4.1 ("Red: … it reports `Got ''`, not
      `None`");
    - `specs/run-metadata/spec.md` ("An absent key counts as `None` and reports as `None`"; "an
      absent key reports as `None`");
    - `design.md` D5 and D6.
- **N2 / I10** ("The moved provenance subprocess and AST tests are never upgraded to D7"). Addressed.
  Where: `tasks.md` 1.2 ("Upgrade the two tests moved in 1.1 to design D7"), with child (c), env and
  cwd, the `__file__` check, the full forbidden set, and the `importlib`/`__import__` refusal; 1.1
  names the helper imports and `pyproject.toml:106` `pythonpath = ["tests"]`.
- **N3** ("The prefix for a non-object manifest contradicts itself"). Addressed: `manifest <path>` for
  the non-object case, and `sweep manifest <path>` for the JSON and UTF-8 cases. Where: `proposal.md`
  What Changes, aligned with `design.md` D4.
- **N4 / I16** ("The 4.3 sweep regex misses the stale ``Pinned ``sha256:`` image digest`` docstrings").
  Addressed: the 11 editable docstrings are listed, and the regex gains ```` ``sha256:`` ````. The 4
  in F3a's files are recorded as left as they are, in Out of scope and the 6.1 issue. Where:
  `tasks.md` 4.3 and 6.1; `proposal.md` Impact and Out of scope.
- **N5** ("Commit 2.3 will fail ruff F401"). Addressed with the redundant-alias re-export. Where:
  `design.md` D4 (the code block); `tasks.md` 2.3.
- **N6 / I23** ("`git show -M --stat` cannot show the similarity percentage"). Addressed. Where:
  `tasks.md` 1.1 (`git show -M --name-status HEAD`, expecting `R100`).
- **N7** ("One 'equivalent' mutant is not equivalent"). Addressed: the `or ""` mutant is now listed
  as killed by the absent-key test. Where: `tasks.md` 5.3.
- **S1.** `build_dataset` became `dataset.build_run_metadata` in the force ADDED scenario.
- **S2.** The D5 message says `<64 hex>`, matching the spec.
- **S3.** The `build_dataset` patch anchor moved into the 2.1 anchor commit.
- **S4.** The 4.1 reds list `bytes` → `TypeError` and a list → `AttributeError`.
- **S5.** The sweep uses `[^@]sha256:<`.
- **S6.** Guard-on-guard mutants added: `importlib.import_module` inserted into `_provenance` and
  `_manifest`, and a wrong-`PYTHONPATH` child.
- **S7.** The mutant is now "module-level name import".
- **S8.** The `_IoSpy` lines are corrected to `:592` / `:603`, and the nonexistent "(length N)
  match=" task is removed.
