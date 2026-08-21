## Tasks

**Real dependency order** (verified twice by independent review rounds): Phase 0 → 3 (diagnostic
needs Phase 0's guard module) and Phase 4 (provisioning + CLI timestamp fix, closes #62) are both
independent of Phase 1 (the deck fix itself) and of each other. Phase 1 → 2 → 5 → 6 are hard-coupled
(see PR 2 below). Phase 7's docs split across both PRs (see below).

**Four-PR split** (revised after round-2 review found the original two-PR split was internally
contradictory — Phase 6 needs Phase 1's fix, which per Phase-1's own coupling can't land without
Phase 5's cluster-run commit):

- **PR 1a** — Phase 4 only. Fully standalone infra fix, closes issue #62, substantively unrelated
  to wing geometry (discovered in the same audit, not causally connected). Smallest, safest, most
  independently reviewable unit — merge first.
- **PR 1b** — Phase 0 tasks 1-4 & 6 + Phase 3. Cluster-free geometry tooling (regression guard +
  diagnostic visualization), depends on nothing but each other. Task 5 is *written* here (it's a
  test, authored alongside its siblings) but intentionally ships red/`xfail` in this PR — it only
  *passes* once PR 2's Phase 1 fixes the decks it checks; see task 46.
- **PR 1c** — Phase 7 tasks 42-44 only (docs imports/pointers that don't claim the fix is done).
- **PR 2** — Phase 0 task 5 (goes green here) + Phase 1 + Phase 2 + Phase 5 + Phase 6 + Phase 7
  task 45. Gated on the cluster checkpoint (task 34). This is the PR that actually changes
  simulated data.
- **Phase 8 (tasks 46-49) is cross-cutting sign-off, not exclusively PR 2**: task 48 closes issue
  #62 in PR 1a's own description, and task 49 runs `/pre-merge-check` separately for PR 1a/1b/1c
  before PR 2 is even mentioned. Each PR does its own Phase-8-relevant checks at its own merge time.

### Phase 0 — regression guard (TDD, cluster-free, before touching any deck)

1. [x] Write `tests/test_sweep_hinge_geometry.py`: `test_hinge_at_span_root_for_correct_deck` against
   the **live** `examples/flapping_wing/inputs.3d.validation` (must pass against today's already-correct
   deck — the calibration baseline from `design.md` D1). The implementation does not exist yet — this
   test must fail with an `ImportError`/`AttributeError` first.
2. [x] Write `test_hinge_at_span_root_rejects_midspan_pivot`: a synthetic deck string with
   `hinge_y == particle_inputs.y` (zero arm) must fail.
3. [x] Write `test_hinge_at_span_root_rejects_spurious_offset`: a synthetic deck string with a
   *correct* span-axis arm but `hinge_z != particle_inputs.z` must fail, naming the offending axis.
4. [x] Write `test_hinge_at_span_root_handles_empty_vertex_file`: an empty/zero-marker vertex file
   raises a clear `ValueError` naming the file.
5. [x] Write `test_hinge_at_span_root_for_coarse_and_fine_base_decks` against
   `examples/prelim_sweep/base_inputs.3d.validation` and
   `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` — **expected to fail** until Phase 1 lands
   (in PR 2; this test is written here in Phase 0 but only goes green in PR 2's Phase 1 commit).
6. [x] Implement `assert_hinge_at_span_root` in `src/mosquito_cfd/force_surrogate/geometry_guard.py`
   per `design.md` D1. Run tests 1-4 green, test 5 red (expected — PR 1b ships with test 5
   intentionally red against the not-yet-fixed decks; this is fine because PR 1b's own commit
   doesn't touch those decks, and `pytest`'s overall exit code for PR 1b's CI run is scoped to what
   that PR changes — see Phase 8 note on this).

### Phase 3 — wing-phase diagnostic (TDD; depends only on Phase 0)

7. [x] Write tests for `build_wing_phase_figure` per `design.md` D2: figure structure via the
   Matplotlib object model; its metrics dict matches Phase 0's `assert_hinge_at_span_root` numbers
   exactly for the same deck; runs with no CFD output present.
8. [x] Write `test_build_wing_phase_figure_writes_three_artifacts` (mirrors
   `tests/test_force_surrogate_evidence_figure.py::test_generate_writes_three_artifacts`).
9. [x] Write `test_wing_phase_diagnostic_rejects_mutable_docker_tag` (mirrors
   `test_generate_rejects_mutable_tag`).
10. [x] Implement `build_wing_phase_figure` in
    `src/mosquito_cfd/force_surrogate/wing_phase_diagnostic.py`, importing
    `rotation_matrix`/`euler_angles` from `mosquito_cfd.benchmarks.wing_kinematics`.
11. [x] Write a CLI smoke test for the new driver **before** implementing the CLI.
12. [x] Write `test_wing_phase_diagnostic_default_sample_is_documented`, scoped to what's verifiable
    within this PR: the CLI's own `--help` output names the default sample configs and states why
    they were chosen. (The spec's sibling documentation channel — a figures README — doesn't exist
    yet at this point in the sequence; PR 1b must not depend on PR 2's `examples/prelim_sweep/figures/README.md`,
    which task 37 creates later. Task 37 additionally documents this same default sample once that
    README exists, satisfying the rest of the spec scenario at that point — not a new obligation,
    just where the second half of an already-existing requirement actually gets fulfilled.)
13. [x] Implement the thin CLI driver (`scripts/`) with a **named, literal** default sample — the
    validated point (`examples/flapping_wing/inputs.3d.validation`'s kinematics) plus the two grid
    corners `s35_f085_p30` and `s55_f115_p60` — and an explicit `--config all` override.

### Phase 4 — provisioning + CLI timestamp fixes (TDD; closes #62; independent of Phases 0/1/3)

14. [x] Write `tests/test_submit_workflow_provision.py` mirroring
    `tests/test_submit_workflow_parallelism.py`'s stub-`argo` convention: a `tmp_path` fake
    `corpus_dir` and fake `workspace_hostpath` (with `CLUSTER_NFS_PREFIX`/`LOCAL_NFS_PREFIX` left at
    their real defaults, since a plain `tmp_path` string is already outside the `/hpi/hpi_dev`
    prefix and `to_local_path` is a no-op on it). Tests, all expected to fail first:
    - `test_provision_copies_and_verifies_by_hash_for_full` (manifest required)
    - `test_provision_copies_and_verifies_by_hash_for_smoke` (manifest NOT required — exercises the
      `smoke` path explicitly, not just `full`)
    - `test_provision_fails_when_corpus_dir_does_not_exist` (distinct error from the next case)
    - `test_provision_fails_when_inputs_missing_within_existing_corpus_dir`
    - `test_provision_fails_when_manifest_missing_for_full` (the third `die()` branch —
      `require_manifest=true` — distinct from `smoke`'s path, which never requires it)
    - `test_provision_fails_on_corpus_workspace_basename_mismatch` (the coarse-corpus-dir /
      fine-workspace-hostpath mismatch scenario — the concrete near-term risk this session found)
    - `test_no_provision_flag_skips_copy_but_still_submits`
    - `test_provisioned_wing_vertex_matches_canonical_source`, **parametrized over at least two
      different corpus-dir/workspace-hostpath pairs** (coarse-shaped and fine-shaped fixtures), to
      actually prove the "any corpus-dir" claim rather than checking it once
    - `test_to_local_path_default_mapping`: a pure string-substitution test asserting
      `/hpi/hpi_dev/...` → `/mnt/hpi_dev/...` with the real default prefixes (no filesystem access,
      the one piece of this fix that can't otherwise be exercised in CI)
    - `test_parallelism_and_provisioning_do_not_interfere`: an invalid `--parallelism` value still
      fails fast even with a valid corpus-dir/workspace-hostpath pair present
15. [x] Implement the `provision` step, `to_local_path` translation, `--corpus-dir`/`--no-provision`
    flags in `cluster/argo/scripts/submit_workflow.sh` per `design.md` D4 (fixed version, with the
    WSL/cluster path translation and the basename cross-check). Wire `provision` into `full`
    (`require_manifest=true`) and `smoke` (`require_manifest=false`), running before the existing
    `--parallelism` sed-patch logic. Run task 14 green. Update the script's header comment + `help`
    output for the new flags.
16. [x] Update `cluster/argo/README.md`'s Prerequisites/procedure section to document `provision`,
    `--corpus-dir`, and `--no-provision` — the script's own `--help` text isn't sufficient, since
    this README is the primary operator-facing document for the whole submission workflow.
17. [x] Write a failing test asserting `examples/prelim_sweep_fine/generate_full_corpus.py`'s
    `main()` exits non-zero via argparse's required-argument error when `--timestamp` is omitted,
    **and that no file is read or written** (mirrors task 20's decoy-directory-not-created pattern) —
    add this to `tests/test_full_corpus_deck.py` as `test_main_requires_timestamp`.
18. [x] Write the equivalent failing test for `examples/prelim_sweep/generate_sweep.py`'s `main()`,
    added to `tests/test_force_surrogate_sweep.py` (which already loads this exact script via
    `spec_from_file_location` and already exercises its `main()` in `test_driver_smoke`, line ~524
    — that's the established home for this script's CLI tests, not a new file) as
    `test_main_requires_timestamp`.
19. [x] Remove `default=DEFAULT_TIMESTAMP` from both scripts' `--timestamp` `add_argument` call
    (make it required); remove the now-unused `DEFAULT_TIMESTAMP` module constant from each if
    nothing else references it. Run tasks 17-18 green.
20. [x] **Update `tests/test_full_corpus_deck.py::test_generate_full_corpus_main_rejects_frozen_paths_via_cli`**
    to pass an explicit `--timestamp` alongside `--output` in both `main([...])` calls, per the spec
    delta's "frozen-path rejection is not masked by the timestamp requirement" scenario. Confirm the
    test still asserts the decoy directory was never created.
21. [x] Add a one-line comment next to `examples/prelim_sweep_fine_pilot/generate_pilot.py`'s own
    `DEFAULT_TIMESTAMP` pointing at this change's id — the identical pattern is intentionally left
    functionally unfixed there (the pilot isn't re-run by this change), but not left unmarked.
22. [x] Ran `grep -rn '\.main(\[' tests/` at the time this task was first checked off: exactly 3
    matches without `--timestamp` (the two calls in `test_full_corpus_deck.py` fixed by task 20,
    and the one call in `test_fine_pilot_deck.py` targeting the untouched `generate_pilot.py`).
    **Note (round-2 PR review):** this count is a point-in-time audit, not a standing invariant.
    Re-running it now (after adding the malformed-timestamp regression tests) gives 8 total
    `.main([` call sites, 3 of which omit `--timestamp`: the original `generate_pilot.py` exception
    (`test_fine_pilot_deck.py:203`) plus 2 *deliberate* "confirm omission is rejected" calls
    (`test_force_surrogate_sweep.py::test_main_requires_timestamp`,
    `test_full_corpus_deck.py::test_main_requires_timestamp`) — both intentional, not a gap. The
    5 remaining calls all supply `--timestamp` explicitly (including the new malformed-value tests,
    which supply a *present-but-invalid* value, not an omitted one). Re-run and re-classify each
    call site by intent (not just count) if this driver surface changes again.

### Phase 1 — fix the two base decks (PR 2 — begins the coupled sequence)

23. [x] Edit `examples/prelim_sweep/base_inputs.3d.validation`: `hinge_y = 2.0 → 0.5`,
    `hinge_z = 2.5 → 4.0`. Update the deck's inline comment.
24. [x] Edit `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` identically.
25. [x] Run Phase 0's test 5 — now green. Run
    `tests/test_fine_pilot_deck.py::test_fine_pilot_deck_matches_coarse_base_except_n_cell` — must
    still pass (both bases changed identically).
26. [x] **Deviation from the original plan (discovered during implementation):** do NOT regenerate
    `tests/fixtures/run_metadata/inputs.3d.s35_f085_p45`. Its own README documents it as an "exact
    copy of the committed deck," cross-checked as read-only ground truth against the real,
    already-committed pilot config alongside sibling fixtures (`forces_s35_f085_p45.csv`,
    `run_metadata_s35_f085_p45.json`, `argo_status_*.json`) that all pertain to that SAME real,
    un-regenerated CFD run (the pilot's actual CFD is intentionally not re-run by this change).
    Regenerating just this one fixture with the corrected hinge would silently diverge it from the
    real deck it claims to mirror and from its own sibling fixtures — breaking the invariant this
    task was meant to preserve, not fixing anything. Confirmed unchanged (byte-identical to
    `examples/prelim_sweep_fine_pilot/inputs/inputs.3d.s35_f085_p45`, which itself is correctly
    *not* touched) and `tests/test_metadata_capture.py` passes (39/39) with no edit.

### Phase 2 — update the tests/docstrings this fix intentionally supersedes

27. [x] Update `tests/test_force_surrogate_sweep.py`'s `BASE_INPUTS` comment ("frozen snapshot...
    never regenerated") to reference this change and the one-time exception.
28. [x] Update `src/mosquito_cfd/force_surrogate/sweep.py`'s docstring(s) similarly.
29. [x] **Update `tests/test_force_surrogate_scale_invariance.py`'s `_FROZEN_RAW_FORCE_SHA`** to the
    post-regeneration hash. `_FROZEN_RAW_FORCE_SHA` hashes `dataset.parquet`'s raw columns, which
    only exist after Phase 5's extract/train step (task 36) — update this in the **same commit** as
    task 36, not earlier (the new hash isn't known until `dataset.parquet` exists). Done: new hash
    `02b04f46a99655122f402433e4d0c1afb8cd0e5b28c9b85236ed96cbab14486e` (differs from the pre-fix
    value, confirming the corrected hinge geometry changed the raw CFD forces as expected).
30. [x] `test_committed_sweep_matches_regeneration` requires no code change — passes by construction
    once Phase 5 regenerates and commits the corpus together. Do not weaken or delete it.

### Phase 5 — regenerate the coarse corpus end-to-end (still PR 2)

31. [x] **Deviation discovered here:** `examples/prelim_sweep/generate_sweep.py`'s `BASE_INPUTS`
    pointed at the live `examples/flapping_wing/inputs.3d.validation`, not the frozen snapshot the
    tests/CC-V6 design depend on (correct only at the driver's original pre-T2a commit; never
    updated when T2a froze the snapshot). Caught before committing by comparing the driver's output
    against a direct `generate_sweep()` call with the correct base — see proposal.md "Why N instead
    of M." Fixed the constant, added `test_driver_base_inputs_matches_the_frozen_snapshot`
    (`tests/test_force_surrogate_sweep.py`), reverted the incorrect first regeneration attempt, then
    regenerated `examples/prelim_sweep/` decks + `sweep_manifest.json` + `sweep_manifest.units.json`
    correctly via `generate_sweep()`'s CLI with the corrected base deck and an explicit fresh
    timestamp (now mandatory per Phase 4 task 19). Commit together with Phase 1 (tasks 23-26) —
    `test_committed_sweep_matches_regeneration` reads the frozen-snapshot base deck and byte-compares
    against the committed corpus, so these cannot land in separate pushes. (Task 29's `_FROZEN_RAW_FORCE_SHA`
    update lands later, with task 36 — `dataset.parquet` doesn't exist yet at this point.)
32. [x] Run the Phase 3 diagnostic's CLI (its default sample) against the regenerated coarse decks
    as a manual, visual pre-submission sanity check — an operator looking at the PNG, not a pytest
    assertion. Run once (task 37 supersedes it; do not duplicate).
33. [x] **Fetch a fresh `:fp64` digest for this change's own merge**: per `cluster/argo/README.md`'s
    Prerequisites, wait for `docker.yml`'s `build-fp64` job triggered by this change's own merge
    (PR 1a/1b/1c all add new files under `src/`/`cluster/`, each triggering a rebuild on merge to
    `main` — use the digest from whichever of those merges is most recent by the time PR 2 submits,
    not any digest noted earlier in this process). Done: `sha256:07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3`,
    verified present in every one of the 27 configs' `run_metadata.json` on the cluster NFS share.
34. [x] **Checkpoint with user before cluster submission.** Confirm no stale `WORKSPACE_HOSTPATH` /
    `CORPUS_DIR` env var is exported (echo the resolved values before submitting — Phase 4's
    basename-mismatch guard is a safety net, not a substitute for checking); note there is no
    scripted RunAI quota-headroom check in this repo. Done in a prior session (see
    cluster-submission-handoff memory) — checkpoint occurred before the two Argo submissions below.
35. [x] Submit the 27-config coarse re-run via `cluster/argo/scripts/submit_workflow.sh full`
    (Phase 4's `provision` step now runs automatically) using the digest from task 33. Done across
    two Argo workflows in a prior session: `force-surrogate-sweep-9454x` (5/27 before a 24h
    `activeDeadlineSeconds` ceiling from cluster-wide GPU saturation) and `force-surrogate-sweep-8nbjt`
    (the remaining 22). Independently re-verified this session: all 27 configs have `status:
    "completed"` in their `run_metadata.json`, rows matching the manifest's `max_step`, the pinned
    digest from task 33, and a `deck_sha256` matching the corrected-geometry deck bytes on disk.
36. [x] Verify completion, then re-run extract → train → evidence-figure to regenerate
    `dataset.parquet`, `surrogate/{holdout_predictions.parquet,metrics.json,surrogate.pt,run_metadata.json}`,
    and `figures/{evidence_figure.png,evidence_figure_metrics.json,run_metadata.json}`. Done: extract
    via `scripts/extract_forces.py` (109,656 rows, no configs dropped), train via
    `scripts/train_surrogate.py --device cuda` on the local A5000 (holdout aggregate R²=0.999), then
    `scripts/make_evidence_figure.py`.
    **Deviation discovered here:** the regenerated `metrics.json` flipped which off-panel axis has
    a negative config-resolved R² and which has genuine between-config signal — the corrected-geometry
    corpus gives `CF_x` (an on-panel headline axis) R²≈-0.01 and `CF_y` (off-panel) R²≈0.81, whereas
    the pre-fix corpus had it the other way (`CF_y` negative, `CF_x`≈0.94); `CF_mx`≈0.99 now clearly
    beats `CF_my`≈0.51 for between-config moment skill. `evidence_figure.py::build_caption` had
    hardcoded this old ranking as literal prose — `f"CF_y config-resolved R² = {r2} < 0"` (always
    claiming CF_y is negative) and `"CF_mx/CF_mz omitted (waveform-only, no between-config signal)"`
    — so the regenerated caption would have asserted "CF_y config-resolved R² = 0.81 < 0", a false
    claim baked into a committed evidence artifact. Fixed by computing the off-panel disclosure from
    `metrics` at call time (whichever axis is actually negative, if any; the real CF_mx/CF_mz numbers
    instead of an assumed "no signal") — TDD: added
    `test_build_caption_off_panel_claims_are_data_driven_not_hardcoded` in
    `tests/test_force_surrogate_evidence_figure.py` (confirmed red against the old code, green after
    the fix), then regenerated the figure with the corrected caption. `PANEL_COEFFICIENTS` (the fixed
    3-axis panel choice, design D1) is unchanged — only the caption's off-panel prose is now
    data-driven rather than assuming one corpus's ranking holds for all future ones.
37. [x] Run the Phase 3 diagnostic against the final regenerated decks (same sample as task 32, run
    once total) and commit its output under `examples/prelim_sweep/figures/`. Create
    `examples/prelim_sweep/figures/README.md` (new file, modeled on
    `examples/flapping_wing/figures/README.md`'s file-table + "Regenerate" section), and add a
    one-line cross-reference from `examples/prelim_sweep/README.md`'s existing
    "Figure (`figures/`)" section (confirmed present at that exact header). Done: default sample
    (`validated`, `s35_f085_p30`, `s55_f115_p60`), hinge visually confirmed at the span root
    `(4.0, 0.5, 4.0)` (black triangle) at all four phases in all three renders.
38. [x] **Refresh every hardcoded result number** that changes with the regenerated corpus — this is
    NOT limited to `evidence_figure_metrics.json`-sourced values: also check `surrogate/metrics.json`-
    sourced numbers, which appear separately in `docs/force_surrogate/roadmap.md`'s PR-table row for
    `add-force-surrogate-train` ("Held-out-config R²≈0.98 (config-mean R²≈0.75–0.94)") and in
    `examples/prelim_sweep/README.md`'s "honest reading" section ("pointwise aggregate R² ~0.98").
    Search both files for every number traceable to either JSON artifact and replace with the
    regenerated values. Done: updated both files' aggregate/config-resolved R² numbers, the
    overshoot factor (2.3×→1.3×), and the speedup decomposition (latency floor 310×→470×,
    parallelism factor ~12,000×→~8,050×, corrected to note it's measured independently from batch
    size rather than assumed equal to it). Also found and fixed two more spots task 38's own wording
    didn't anticipate: `docs/force_surrogate/roadmap.md`'s PR6 table row and
    `evidence_figure.py`'s own module docstring both separately hardcoded "~310x latency floor."
    Also updated `tests/test_force_surrogate_evidence_figure.py::test_readme_carries_full_disclosures`'s
    hardcoded "~310" assertion to "~470" (same commit — the test checks the README's literal text).

### Phase 6 — regenerate the fine corpus's decks only (no CFD run; still PR 2 — needs Phase 1's fix)

39. [x] Regenerate `examples/prelim_sweep_fine/` decks + manifest via `generate_full_corpus.py`
    against the corrected fine base deck (task 24), passing an explicit fresh `--timestamp` (now
    required by task 19 — the CLI itself enforces it, no separate reminder needed).
40. [x] Run the Phase 3 diagnostic (manual/visual) against a sample of the regenerated fine decks.
    **Note (attribution corrected post-review):** running this against the fine corpus is what
    surfaced a bug in the diagnostic CLI's `_sweep_config_kwargs` (it hardcoded
    `<corpus-dir>/base_inputs.3d.validation` as the hinge/centre source, which happened to work for
    the coarse corpus but not the fine one, whose base deck lives under
    `examples/prelim_sweep_fine_pilot/` with a different name) — but the fix itself (reading
    hinge/centre from each config's own generated deck instead) and its regression test
    (`test_cli_runs_against_a_corpus_with_no_base_deck_of_its_own`,
    `tests/test_wing_phase_diagnostic_cli.py`) were relocated to PR 1b's (#69) own review-fix commit
    during this change's stacked-PR review, since that is the PR that introduced the CLI in the
    first place — not implemented fresh in this PR's commit. `git blame`/`git log -S` on those two
    files confirms the fix lives on the `fix-hinge-geometry-guard` branch, not this one.
41. [x] Add a `superseded_by` field to `examples/prelim_sweep_fine/sweep_provenance.json` naming the
    now-stale cluster workflows `force-surrogate-sweep-vb8t5` and
    `force-surrogate-retry-failed-trz9k` (noting their NFS `wing.vertex` was already-correct — only
    the hinge was stale for that run), plus a `test_fine_corpus_provenance_flags_superseded_runs`
    asserting the key is present and non-empty.

### Phase 7 — docs

**PR 1c (cluster-free, no claim that the fix is complete):**

42. [x] `git show duncan-meeting-prep:docs/field_surrogate/roadmap.md` → commit onto `main` at
    `docs/field_surrogate/roadmap.md`, updating its sequencing note to record that the standalone F1
    pilot is superseded by a full-corpus field-capture run bundled with the **follow-on change**.
43. [x] **Port the `docs/force_surrogate/roadmap.md` CC-6 + "Out of scope" edit**, retrieved via
    `git diff main duncan-meeting-prep -- docs/force_surrogate/roadmap.md` (confirmed this session to
    cleanly show exactly the CC-6 supersession note + reworded "Out of scope" section — apply that
    diff directly, don't hand-reconstruct it). Land in the same commit as task 42 — task 42 alone
    leaves the imported file's own header referencing a note that won't otherwise exist.
44. [x] Add a one-line pointer note in `docs/force_surrogate/fine-grid-pilot-report.md` referencing
    this fix wherever it discusses corpus force accuracy/validity.

**PR 2 (claims the fix is done, so gated on Phase 5/6 actually landing):**

45. [ ] `openspec/project.md` "Current State" — add a bullet: "Fixed a wing-hinge geometry defect
    (root hinge collapsed to a midspan pivot in the git-committed base decks) dating to the
    2026-07-02 axis-convention refactor; separately found and fixed a stale/incorrect `wing.vertex`
    on the coarse corpus's cluster NFS share (issue #62) that had been running the pre-T2a axis
    convention entirely; regenerated `examples/prelim_sweep/`'s decks +
    `dataset.parquet`/`surrogate/*`/`figures/*` end-to-end and `examples/prelim_sweep_fine/`'s decks
    (CFD re-run deferred); automated NFS provisioning going forward — `fix-force-surrogate-sweep-hinge`".
    Also edit the existing "Pending" bullet about the full fine-grid corpus's live cluster run to
    note the run which already happened (`vb8t5`/`trz9k`) is superseded and needs re-submission.
    Also add the one-line pointer to this fix in the archived `add-fine-grid-corpus-full` and
    `add-fine-grid-training-pilot` proposals' own force-accuracy/validity discussion, per this
    proposal's "What Changes" item 10 ("Documentation pointers") — flagged in PR #70's review as
    promised by `proposal.md` but not yet covered by any task (PR 1c's tasks 42-44 only touch
    `docs/`).

### Phase 8 — verification and sign-off

46. [ ] Per-PR: `uv run pytest` and `uv run ruff check .` green for that PR's own diff. Note PR 1b
    intentionally ships with Phase 0 task 5 red (asserts against the not-yet-fixed decks) — since
    `pytest`'s default run includes the whole suite, PR 1b must either mark test 5
    `xfail(reason="fixed in the follow-on PR 2, see fix-force-surrogate-sweep-hinge")` or PR 1b and
    PR 1's other slices must land in an order where test 5 is never the tip of a pushed/reviewed
    state without an accompanying `xfail` — decide and document whichever approach is used at
    implementation time; do not leave a genuinely red, unmarked test in any pushed branch.
47. [ ] For PR 2: confirm `tests/test_force_surrogate_scale_invariance.py` passes (task 29's updated
    hash) and `tests/test_no_false_diffused_ib_claim.py` passes against the regenerated figure.
    Re-verify `test_radius_of_gyration_traced_from_wing_vertex` still passes unchanged.
48. [ ] Close issue #62 in PR 1a's description (`Closes #62`) — only once task 15's fix is
    confirmed to actually operate on the WSL-mounted path, not just pass its stub-based tests (spot
    check: run `provision` for real, once, against a scratch NFS subdirectory before relying on it
    for the real corpus in task 35).
49. [ ] `/pre-merge-check` for each of PR 1a, 1b, 1c independently; `/pre-merge-check` for PR 2 after
    the cluster run completes and lands.
