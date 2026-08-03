# Tasks — automate run-metadata capture

TDD throughout — this entire change is cluster-free and unit-testable with fixture data. `uv` for
all Python ops. Branch: `automate-run-metadata-capture` (off `main`, post PR #58 merge).

**Revision note (post-review, round 1):** a 5-agent `/review-openspec` found the original draft
conflicted with a live `force-surrogate` spec requirement and an existing test (fixed by making
"don't touch the 3 committed pilot files" a hard non-goal, not a during-implementation decision —
see `design.md` D4), hedged on module location (fixed — see D5, task 1.0), rested on a false
`.gitignore` assumption (fixed — new task 0.3, see D6), left the `stability` field's derivation
vague (fixed — concrete `fixed_dt`-only rule, task 3.4), and was missing several error-path tests,
a commit-sequence section, and explicit lint commands.

**Revision note (post-review, round 2):** a second 5-agent pass verified round 1's fixes and found
task 7.3 was an untestable "raises-or-warns" hedge with no backing spec requirement (fixed — added
a dedicated spec requirement requiring `raise`, task 7.3 rewritten to match), a missing test to
guard the task-0.1 fixture against silently drifting from the real `capture_surrogate_run_metadata`
schema (fixed — new task 0.4), 3 stale task-number cross-references surviving the round-1 edit
(fixed — task 1.0, the commit-sequence section, and this note itself), and `proposal.md` still
carrying the pre-correction "two inconsistent lineages" framing (fixed directly in `proposal.md`).

**Revision note (post-implementation, `/review-pr` self-review before opening a PR):** a 5-agent
review of the actual implementation (not the proposal) found 3 real BLOCKING correctness gaps
undetected by the proposal-stage reviews, since they only surface once real code exists:
`compute_wall_time_s` could silently select Argo's own `"Retry"`-type wrapper node (whose
`startedAt` spans back to the first failed attempt) over the true successful attempt — a real
risk given `force-surrogate-single-config.yaml`'s actual `retryStrategy: {limit: 5}`; verified by
hand-simulating the old logic against a realistic 3-node fixture and confirming it silently
returned the full 17848s span instead of the correct 10096s. `parse_arena_max_mib`'s regex
matched any `*Arena*` line, not just `"[The Arena]"`, so a real GPU log's Device/Managed/Pinned
Arena lines could win the `max()` and report the wrong arena's peak. Deck identity was never
cross-validated against the pod's own `deck_sha256`, reproducing PR #58's "trust the wrong
artifact" failure class in a new spot. All three fixed, plus the IMPORTANT findings (pod `status`
now gated, `rows` now required rather than silently skipped when absent, deck/manifest field
lookups now raise clear errors instead of bare `KeyError`s) — see commit `3df231d`. 100% coverage
maintained; 527 passed / 14 skipped, no regressions.

**Revision note (post-PR-review, PR #59):** a 5-agent `/review-pr` pass against the pushed PR
(no BLOCKING findings) surfaced one real IMPORTANT gap the proposal never specced: the deck-hash
check added in the prior fix round verified `--deck` against the pod's `deck_sha256` but never
persisted the verified hash in the output — once the pod-side (uncommitted) artifacts are
cleaned up, there was no way to audit which deck produced a committed file. Fixed: `deck_sha256`
is now a top-level output field, and two spec requirements ("pod-reported run status must be
completed", "deck identity is cross-validated ... and persisted in the output") were added to
formalize guards that existed in code/tests but were never specced (see task 12 below). Also
fixed: task 9.3's own claim that `inputs hash` "does not exist in either the old or new schema"
was itself factually wrong (it exists in the old schema as `inputs.hash`; corrected in place
above); an `is None`-vs-falsy bug where an empty-string `deck_sha256` slipped past the
"must be present" guard into a confusing mismatch message instead of the clear "missing" one; a
CWD-relative path in the sole end-to-end oracle test that could silently skip if pytest ran from
a non-root directory; and a missing timeout on the Argo status-query subprocess (raised as a
non-blocking suggestion twice now — added a 30s timeout with a clear error).

---

## 0. Fixtures and `.gitignore` fix

- [x] 0.1 Add `tests/fixtures/run_metadata/` with, for the `s35_f085_p45` pilot config: a copy of
  its committed force CSV, a hand-reconstructed pod-side `run_metadata.json` matching the REAL
  schema `capture_surrogate_run_metadata`/`capture_run_metadata` actually produce (verified against
  `src/mosquito_cfd/benchmarks/metadata.py` and `src/mosquito_cfd/force_surrogate/sidecar.py` —
  `git`/`hardware`/`orchestration`/a single digest-validated `docker_image` field/`run_id`/
  `timestamp`, plus `run_one_config.py`'s own `extra` keys `config`/`deck`/`deck_sha256`/`command`/
  `ib_particle_csv`/`log`/`rows`/`max_step`/`threshold`/`status` — no `timing` block, since that's
  the gap this change fixes), a synthetic `run.log` excerpt containing a realistic AMReX "The
  Arena" max-used line, the config's `sweep_manifest.json` entry, and a canned Argo `get -o
  json`-shaped status response with `startedAt`/`finishedAt` timestamps consistent with
  `s35_f085_p45`'s actual committed wall time (9448.466969s / 2h37m — NOT `s55_f115_p45`'s
  7032.46s; verify against the correct config's own `run_metadata_s35_f085_p45.json` before use).
- [x] 0.2 Document in a fixture README (or module docstring) that these values are cross-checked
  against the real, already-committed, already-corrected
  `examples/prelim_sweep_fine_pilot/run_metadata_s35_f085_p45.json` as read-only ground-truth test
  data (D4) — this is the TDD oracle for the whole change, and the fixture file is NOT a copy that
  gets written back to that path.
- [x] 0.3 **Fix the `.gitignore` gap (D6):** generalize `examples/prelim_sweep/runs/` (line 24) to
  `examples/prelim_sweep*/runs/`, covering `examples/prelim_sweep_fine_pilot/runs/` (currently
  unmatched — verified via `git check-ignore -v`) and the upcoming full-corpus follow-on's own
  `runs/` tree. Verify manually with `git check-ignore -v examples/prelim_sweep_fine_pilot/runs/foo`
  before/after; not a pytest (gitignore behavior isn't unit-testable in the normal sense), but
  record the before/after `git check-ignore` output in the commit message.
- [x] 0.4 **Test first (fixture drift guard):**
  `test_pilot_fixture_matches_real_capture_surrogate_run_metadata_shape` — call
  `capture_surrogate_run_metadata` with mocked `subprocess`/`socket.gethostname`/digest inputs,
  and assert `set(result.keys())` (plus `run_one_config.py`'s own `extra` keys) matches the
  task-0.1 fixture's pod-side `run_metadata.json` key set exactly. If `benchmarks/metadata.py` or
  `sidecar.py`'s schema changes later, this test fails loudly instead of the fixture silently going
  stale.

## 1. Module layout (D5)

- [x] 1.0 Create `src/mosquito_cfd/force_surrogate/metadata_capture.py` as the home for all logic
  in tasks 2-7 below (importable, unit-testable, can `import` `sidecar.validate_image_digest`
  directly). `scripts/generate_run_metadata.py` (task 8) is a thin argparse CLI wrapper over this
  module only — no parsing/validation logic lives in the script itself.

## 2. Force-CSV last-row reader (TDD, cluster-free)

- [x] 2.1 **Test first:** `tests/test_metadata_capture.py::test_read_final_time_from_csv_uses_last_row`
  — given the fixture CSV, assert the reader returns `time=2.3525` and `timesteps=4706`, not the
  deck's `stop_time=2.352941176`.
- [x] 2.2 **Test first:** `test_read_final_time_raises_on_empty_csv` — a CSV with header only
  raises a clear error, not an `IndexError`.
- [x] 2.3 **Test first:** `test_read_final_time_raises_on_missing_csv_file` — a nonexistent CSV
  path raises a clear, path-naming error.
- [x] 2.4 Implement the reader in `metadata_capture.py` to make 2.1–2.3 pass.

## 3. run.log Arena-max parser and stability derivation (TDD, cluster-free)

- [x] 3.1 **Test first:** `test_parse_arena_max_mib_from_run_log` — given the fixture `run.log`
  excerpt, assert the parser extracts `7998` (or the fixture's chosen value) as an integer MiB
  figure.
- [x] 3.2 **Test first:** `test_parse_arena_max_mib_returns_none_when_absent` — a `run.log` with no
  Arena line returns `None` rather than raising.
- [x] 3.3 **Test first:** `test_parse_arena_max_mib_raises_on_missing_log_file` — a nonexistent
  `run.log` path raises a clear, path-naming error (distinct from "no Arena line present").
- [x] 3.4 **Test first (D2's concrete stability rule):**
  `test_stability_derived_from_fixed_dt_alone` — given `fixed_dt=5e-4` assert `stability ==
  "stable_at_5e-4"`; given `fixed_dt=2.5e-4` assert `stability == "stable_at_2.5e-4_fallback"`; no
  separate `dt_reduced`-style flag is read as input to this function.
- [x] 3.5 Implement the parser and the `derive_stability(fixed_dt)` function in
  `metadata_capture.py` to make 3.1–3.4 pass.

## 4. Manifest/deck sourcing (TDD, cluster-free)

- [x] 4.1 **Test first:** `test_kinematics_grid_fixed_dt_max_step_sourced_from_manifest` — given
  the fixture `sweep_manifest.json` entry, assert `stroke_amp_deg`, `frequency_fstar`,
  `pitch_amp_deg`, `reynolds`, grid, `fixed_dt`, AND `max_step` are all read verbatim, with no CLI
  override path for any of them (matches the spec.md scenario covering all of these, not just
  kinematics).
- [x] 4.2 **Test first:** `test_manifest_lookup_raises_on_missing_config` — an unknown config name
  raises a clear `KeyError`-wrapping error naming the config and the manifest path.
- [x] 4.3 **Test first:** `test_manifest_lookup_raises_on_malformed_manifest_json` — a manifest
  file that fails to parse as JSON raises a clear, file-identified error (mirrors
  `test_fine_pilot_deck.py`'s `_load_metadata` malformed-JSON precedent).
- [x] 4.4 Implement to make 4.1–4.3 pass.

## 5. Docker-digest and git-commit passthrough validation (TDD, cluster-free)

- [x] 5.1 **Test first:** `test_docker_digest_field_is_single_named_and_validated` — given a
  pod-side `run_metadata.json` with a valid `sha256:...` digest, assert the output has exactly one
  image-identity field, **named `docker_image`** (pin the key name, not just "some field matches
  the regex"), matching the digest regex. Reuse `sidecar.validate_image_digest` — import it
  directly, do not duplicate its pattern.
- [x] 5.2 **Test first:** `test_malformed_digest_is_rejected` — given a pod-side `run_metadata.json`
  whose image field is a bare tag (e.g. `ghcr.io/talmolab/mosquito-cfd:fp64`) or a
  truncated/malformed digest, assert the generator raises a clear validation error naming the
  offending value.
- [x] 5.3 **Test first:** `test_git_commit_must_be_full_sha` — given a pod-side `run_metadata.json`
  with a truncated (7-char) `git.commit`, assert the generator raises a validation error rather
  than passing it through (this is the actual bug PR #58's review caught — assert it can't recur).
- [x] 5.4 **Test first:** `test_pod_run_metadata_raises_on_missing_file` — a nonexistent pod-side
  `run_metadata.json` path raises a clear, path-identified error.
- [x] 5.5 **Test first:** `test_pod_run_metadata_raises_on_malformed_json` — a pod-side
  `run_metadata.json` that fails to parse as JSON raises a clear, path-identified error (distinct
  from 5.4's "file doesn't exist").
- [x] 5.6 Implement to make 5.1–5.5 pass.

## 6. Argo workflow-status query wrapper (TDD, injected/faked)

- [x] 6.1 **Test first:** `test_wall_time_from_argo_status_timestamps` — given the fixture Argo
  status JSON (or an injected fake query function returning it, following the `FakeRunner`
  injection pattern in `tests/test_force_surrogate_run_one_config.py`), assert `wall_time_s`
  equals `finishedAt - startedAt` in seconds.
- [x] 6.2 **Test first:** `test_wall_time_reflects_only_final_successful_attempt` — given a fixture
  Argo status showing one failed attempt followed by a successful retry, assert `wall_time_s`
  uses only the successful attempt's duration, not the sum.
- [x] 6.3 **Test first:** `test_wall_time_s_override_bypasses_argo_query` — given `--wall-time-s
  7032.46` is supplied, assert the injected Argo-query function is never called and `wall_time_s`
  is `7032.46` exactly.
- [x] 6.4 **Test first:** `test_argo_status_missing_timestamps_raises_clear_error` — a status
  response that parses successfully but omits `startedAt`/`finishedAt` raises a clear error
  (distinct from 6.5's "query itself fails").
- [x] 6.5 **Test first:** `test_argo_status_query_failure_produces_clear_error` — a query that
  raises (e.g. `argo` CLI not found, or the workflow name doesn't exist) surfaces a clear,
  actionable error rather than a raw subprocess traceback.
- [x] 6.6 Implement the wrapper as an injectable function in `metadata_capture.py` (default
  implementation shells out to `argo get <workflow-name> -o json`; tests inject a fake) plus the
  `--wall-time-s` override path, to make 6.1–6.5 pass.

## 7. Schema assembler (TDD, cluster-free)

- [x] 7.1 **Test first:** `test_assemble_metadata_produces_normalized_schema` — given all fixture
  inputs (2–6) plus a `--tier` value, assert the assembled dict has the normalized shape from
  `design.md` D2: single named `docker_image` digest field, structured `stability`/
  `arena_max_mib`/`node`/`gpu_model` (no free-text `run_platform` paragraph), `kinematics`/`grid`/
  `fixed_dt`/`max_step` from the manifest, `timing.{final_time,timesteps,wall_time_s}`,
  `orchestration.{workflow_uid,pod,node,retry}` passed through from the pod-side file.
- [x] 7.2 **Test first:** `test_assemble_metadata_notes_field_optional` — omitting `--notes`
  produces valid output with no `notes` key; passing `--notes "..."` includes it verbatim.
- [x] 7.3 **Test first:** `test_assemble_metadata_raises_on_row_count_mismatch_between_pod_and_csv`
  — given a pod-side `run_metadata.json` whose own `rows` field disagrees with the CSV-derived
  `timesteps` count, assert the generator **raises** a clear error naming both values (per the
  dedicated spec requirement "pod-reported row count is cross-validated against the CSV") — a
  single, concrete, TDD-able behavior, not a raise-or-warn hedge. This is exactly the class of
  silent-inconsistency bug this whole change exists to prevent.
- [x] 7.4 **Test first:** `test_assemble_metadata_matches_known_correct_pilot_config` — the
  fixture-driven end-to-end reproduction from `design.md` D4: assert `final_time`, `git.commit`,
  and `kinematics` in the assembled output match the real, already-committed
  `run_metadata_s35_f085_p45.json` exactly. This reads the committed file as read-only ground
  truth; it does NOT write to or modify that file.
- [x] 7.5 Implement the assembler in `metadata_capture.py` to make 7.1–7.4 pass. The module's
  top-level docstring SHALL document the full assembled schema (every field name and where it's
  sourced from) — this becomes the one canonical schema description that `specs/run-metadata/spec.md`
  formalizes as requirements and that task 9.3's doc fixes point readers toward.

## 8. CLI wiring

- [x] 8.1 **Test first:** `test_cli_writes_output_file` — invoke `scripts/generate_run_metadata.py`
  `main()` with fixture paths + `--tier`/`--workflow-name` args, assert a
  `run_metadata_<config>.json` file is written matching the assembler's output.
  Nothing in this test or the CLI touches the 3 committed pilot files (D4).
- [x] 8.2 **Test first:** `test_cli_rejects_missing_required_args` — omitting `--tier` fails with
  a clear argparse error, not a downstream `KeyError`. **Deviation from the original wording
  (reconciled during implementation, see `### Why workflow-name is optional?` below):**
  `--workflow-name` is NOT argparse-required — it's optional per the `--wall-time-s` override
  design (a config using the override never needs a workflow name for timing purposes). Covered
  instead by `test_cli_missing_workflow_name_and_wall_time_s_raises_clear_error`: omitting BOTH
  `--workflow-name` and `--wall-time-s` raises a clear `ValueError` naming `workflow_name` (not a
  downstream `KeyError`) — the original test intent (a clear, specific failure, not silent
  misbehavior) is preserved even though the mechanism (library `ValueError` vs. argparse
  `SystemExit`) differs from the original wording's assumption.
- [x] 8.3 **Test first:** `test_cli_wall_time_s_flag_skips_argo_query` — passing `--wall-time-s`
  produces output without invoking the Argo-query path.
- [x] 8.4 Implement `scripts/generate_run_metadata.py`'s `main()`/argparse wiring (thin wrapper
  over `metadata_capture.py`, per D5/task 1.0) to make 8.1–8.3 pass. The module docstring SHALL
  state explicitly: (a) this tool is operator-run only, never invoked from CI; (b) it must be run
  before the source Argo workflow is garbage-collected, or with `--wall-time-s` supplied manually.

## 9. Docs

- [x] 9.1 Update `openspec/project.md`'s "Current State → Implemented" line (around line 120,
  "Run metadata capture with docker/git/hardware tracking") to reference the new automated
  generator, note it now covers timing/kinematics/orchestration fields previously hand-typed, and
  note that `examples/flapping_wing/run_metadata_{t3c,t3b,t2a}.json` and the 3 committed pilot
  files intentionally remain on the pre-normalization schema (D4 non-goal).
- [x] 9.2 Annotate `docs/force_surrogate/fine-grid-pilot-report.md`'s "schema matches
  `run_metadata_t3c.json`" line as describing the pilot files' as-committed (pre-normalization)
  schema specifically, not the schema new runs will use going forward.
- [x] 9.3 Correct `docs/force_surrogate/roadmap.md` CC-1's run-metadata field description: it
  currently reads "container digest, IAMReX commit, inputs hash, git SHA, host, and a
  caller-supplied timestamp" — **correction (a PR review caught this claim was itself wrong):**
  `inputs hash` DOES exist in the old schema (as `inputs.hash`) and now also exists in the new
  schema (as the flat `deck_sha256` field, persisted per the "deck identity is cross-validated
  ... and persisted in the output" spec requirement added post-implementation). `IAMReX commit`
  is genuinely not part of this change's schema. Replace the field list with a one-line summary
  instead of re-enumerating individual fields: "git (full SHA), a single digest-validated
  `docker_image`, a verified `deck_sha256`, hardware/orchestration, and timing/kinematics/
  stability for force-surrogate runs — full schema in `metadata_capture.py`'s module docstring
  and `specs/run-metadata/spec.md`, not re-enumerated here." (Single canonical source per task
  7.5; this task only points to it.)
- [x] 9.4 Add a short usage note (module docstring in `scripts/generate_run_metadata.py`) pointing
  the full 27-config corpus follow-on at this tool instead of hand-authoring its 27 metadata files.

## 10. Commit sequence / PR strategy

Matches this repo's convention (confirmed via `git log`: conventional-commit prefixes,
`Co-Authored-By` trailer) and the archived pilot's own `tasks.md` precedent of an explicit
commit-sequence section. Each commit below leaves `uv run pytest` and `uv run ruff check` green.

1. `chore: generalize .gitignore runs/ pattern to cover fine-grid corpus tiers` (task 0.3)
2. `test(force-surrogate): add run-metadata fixtures for automate-run-metadata-capture` (0.1–0.2)
3. `feat(force-surrogate): read final_time from force-CSV last row` (1.0, 2) — includes creating
   the `metadata_capture.py` module scaffold from task 1.0
4. `feat(force-surrogate): parse Arena max-used MiB and derive stability from fixed_dt` (3)
5. `feat(force-surrogate): source kinematics/grid/fixed_dt/max_step from sweep manifest` (4)
6. `feat(force-surrogate): validate docker digest + full-SHA git commit` (5)
7. `feat(force-surrogate): add Argo workflow-status wall-time query with manual override` (6)
8. `feat(force-surrogate): assemble normalized run-metadata schema` (7)
9. `feat(force-surrogate): add generate_run_metadata CLI` (8)
10. `docs: document normalized run-metadata schema and generator usage` (9)

**Explicitly NOT in this PR:** any commit touching `examples/prelim_sweep_fine_pilot/run_metadata_
*.json` or `tests/test_fine_pilot_deck.py`'s `_REQUIRED_METADATA_FIELDS` (D4 non-goal — a future,
separately-reviewed change if pursued).

### Why workflow-name is optional?

Task 8.2 originally assumed `--tier` and `--workflow-name` were both simple argparse-required
flags. During implementation this proved wrong: `resolve_wall_time_s`'s whole point is that
`workflow_name` is only needed to query Argo, and that query is explicitly skippable via
`--wall-time-s` (spec.md's "wall-clock timing ... with a manual override" requirement). Making
`--workflow-name` unconditionally argparse-required would force every `--wall-time-s` invocation
to also supply a workflow name it doesn't need, contradicting the override's purpose. Resolution:
`--workflow-name` stays optional at the CLI layer; `resolve_wall_time_s` enforces "one of
`workflow_name` or `wall_time_s_override` must be present" with a clear `ValueError`, tested by
`test_cli_missing_workflow_name_and_wall_time_s_raises_clear_error`. `--tier` remains the only
argparse-required flag beyond the file paths.

## 11. Validate and ship

- [x] 11.1 `openspec validate automate-run-metadata-capture --strict`.
- [x] 11.2 `uv run pytest` (full suite green).
- [x] 11.3 `uv run ruff check src/ scripts/ tests/` (a subset of CI's full lint scope, which also
  covers `examples/prelim_sweep/` and `examples/prelim_sweep_fine_pilot/` — fine here since this
  change touches no files under `examples/`).
- [x] 11.4 `uv run ruff format --check src/ scripts/ tests/`.
- [x] 11.5 `/pre-merge-check`, open PR — [PR #59](https://github.com/talmolab/mosquito-cfd/pull/59).

## 12. Post-PR-review hardening (retroactive — see the PR #59 revision note above)

- [x] 12.1 Persist the verified `deck_sha256` as a top-level output field (previously computed
  and checked but discarded); add the corresponding spec requirement and
  `test_assemble_metadata_produces_normalized_schema`'s deck_sha256 assertion.
- [x] 12.2 Add a spec requirement for the pod `status` gate (guard already existed in code/tests
  from the prior fix round; only the spec was missing).
- [x] 12.3 Fix the `is None`-vs-falsy bug: an empty-string `deck_sha256` now correctly triggers
  the "missing" error, not a confusing mismatch message —
  `test_assemble_metadata_raises_on_empty_string_deck_sha256`.
- [x] 12.4 Anchor `test_assemble_metadata_matches_known_correct_pilot_config`'s
  `_REAL_COMMITTED_METADATA` path to `Path(__file__).parent.parent` instead of a bare
  CWD-relative path (was silently skippable if pytest ran from a non-root directory).
- [x] 12.5 Add a 30s timeout to `query_argo_workflow_status`'s subprocess call, with a clear
  `RuntimeError` on expiry — `test_argo_status_query_timeout_produces_clear_error`.
- [x] 12.6 Correct `roadmap.md` CC-1 and `tasks.md` 9.3's own factually-wrong claim that
  `inputs hash` doesn't exist in either schema.

## 13. Re-validate and push

- [x] 13.1 `openspec validate automate-run-metadata-capture --strict`.
- [x] 13.2 `uv run pytest` (full suite green, 529 passed / 14 skipped, no regressions).
- [x] 13.3 `uv run ruff check` / `ruff format --check` clean.
- [x] 13.4 Push and confirm CI green on PR #59.
