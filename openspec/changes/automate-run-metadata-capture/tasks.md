# Tasks — automate run-metadata capture

TDD throughout — this entire change is cluster-free and unit-testable with fixture data. `uv` for
all Python ops. Branch: `automate-run-metadata-capture` (off `main`, post PR #58 merge).

---

## 0. Fixtures

- [ ] 0.1 Add `tests/fixtures/run_metadata/` with, for the `s35_f085_p45` pilot config: a copy of
  its committed force CSV, a hand-reconstructed pod-side `run_metadata.json` (matching the real
  schema `capture_surrogate_run_metadata` produces — git/hardware/orchestration/docker_image
  fields, no `timing` block, since that's the gap this change fixes), a synthetic `run.log`
  excerpt containing a realistic AMReX "The Arena" max-used line, the config's
  `sweep_manifest.json` entry, and a canned Argo `get -o json`-shaped status response with
  `startedAt`/`finishedAt` timestamps consistent with the pilot's reported wall time (7032.46s /
  1h58m — use whichever pilot config's numbers are easiest to cross-check against
  `docs/force_surrogate/fine-grid-pilot-report.md`).
- [ ] 0.2 Document in a fixture README (or module docstring) that these values are cross-checked
  against the real, already-committed, already-corrected
  `examples/prelim_sweep_fine_pilot/run_metadata_s35_f085_p45.json` — this is the TDD oracle for
  the whole change (D4 in `design.md`).

---

## 1. Force-CSV last-row reader (TDD, cluster-free)

- [ ] 1.1 **Test first:** `tests/test_generate_run_metadata.py::test_read_final_time_from_csv_uses_last_row`
  — given the fixture CSV, assert the reader returns `time=2.3525` and `timesteps=4706`, not the
  deck's `stop_time=2.352941176`.
- [ ] 1.2 **Test first:** `test_read_final_time_raises_on_empty_csv` — a CSV with header only
  raises a clear error, not an `IndexError`.
- [ ] 1.3 Implement the reader in `scripts/generate_run_metadata.py` (or a small
  `src/mosquito_cfd/force_surrogate/metadata_capture.py` module if it needs to be importable from
  tests elsewhere) to make 1.1–1.2 pass.

## 2. run.log Arena-max parser (TDD, cluster-free)

- [ ] 2.1 **Test first:** `test_parse_arena_max_mib_from_run_log` — given the fixture `run.log`
  excerpt, assert the parser extracts `7998` (or the fixture's chosen value) as an integer MiB
  figure.
- [ ] 2.2 **Test first:** `test_parse_arena_max_mib_returns_none_when_absent` — a `run.log` with no
  Arena line returns `None` rather than raising, since some run.log variants may not include it.
- [ ] 2.3 Implement the parser to make 2.1–2.2 pass.

## 3. Manifest/deck sourcing (TDD, cluster-free)

- [ ] 3.1 **Test first:** `test_kinematics_and_grid_sourced_from_manifest` — given the fixture
  `sweep_manifest.json` entry, assert `stroke_amp_deg`, `frequency_fstar`, `pitch_amp_deg`,
  `reynolds`, grid, `fixed_dt`, and `max_step` are read verbatim, with no CLI override path.
- [ ] 3.2 **Test first:** `test_manifest_lookup_raises_on_missing_config` — an unknown config name
  raises a clear `KeyError`-wrapping error naming the config and the manifest path.
- [ ] 3.3 Implement to make 3.1–3.2 pass.

## 4. Docker-digest and git-commit passthrough validation (TDD, cluster-free)

- [ ] 4.1 **Test first:** `test_docker_digest_field_is_single_and_validated` — given a pod-side
  `run_metadata.json` with a valid `sha256:...` digest, assert the output has exactly one image
  identity field matching the digest regex (reuse `sidecar.validate_image_digest`'s regex or
  import it directly — do not duplicate the pattern).
  test verifies: does not carry over the t3c-lineage's split `docker_image`/`image_digest`
  fields, doesn't strip/reformat the digest, uses `sidecar.validate_image_digest` from
  `src/mosquito_cfd/force_surrogate/sidecar.py:98-122` rather than a new regex.
- [ ] 4.2 **Test first:** `test_git_commit_must_be_full_sha` — given a pod-side `run_metadata.json`
  with a truncated (7-char) `git.commit`, the generator raises a validation error rather than
  passing it through (this is the actual bug PR #58's review caught — assert it can't recur).
- [ ] 4.3 Implement to make 4.1–4.2 pass.

## 5. Argo workflow-status query wrapper (TDD, injected/faked)

- [ ] 5.1 **Test first:** `test_wall_time_from_argo_status_timestamps` — given the fixture Argo
  status JSON (or an injected fake query function returning it, following the `FakeRunner`
  injection pattern in `tests/test_force_surrogate_run_one_config.py`), assert `wall_time_s`
  equals `finishedAt - startedAt` in seconds.
- [ ] 5.2 **Test first:** `test_argo_status_query_failure_produces_clear_error` — a query that
  raises (e.g. `argo` CLI not found, or the workflow name doesn't exist) surfaces a clear,
  actionable error rather than a raw subprocess traceback.
- [ ] 5.3 Implement the wrapper as an injectable function (default implementation shells out to
  `argo get <workflow-name> -o json`; tests inject a fake) to make 5.1–5.2 pass.

## 6. Schema assembler (TDD, cluster-free)

- [ ] 6.1 **Test first:** `test_assemble_metadata_produces_normalized_schema` — given all fixture
  inputs (1–5) plus a `--tier` value, assert the assembled dict has the normalized shape from
  `design.md` D2: single docker-identity field, structured `stability`/`arena_max_mib`/`node`/
  `gpu_model` (no free-text `run_platform` paragraph), `kinematics`/grid/`fixed_dt`/`max_step`
  from the manifest, `timing.{final_time,timesteps,wall_time_s}`, `orchestration.{workflow_uid,
  pod,node,retry}` passed through from the pod-side file.
- [ ] 6.2 **Test first:** `test_assemble_metadata_notes_field_optional` — omitting `--notes`
  produces valid output with no `notes` key; passing `--notes "..."` includes it verbatim.
- [ ] 6.3 **Test first:** `test_assemble_metadata_matches_known_correct_pilot_config` — the
  fixture-driven end-to-end reproduction from `design.md` D4: assert `final_time`, `git.commit`,
  and `kinematics` in the assembled output match the real, already-committed
  `run_metadata_s35_f085_p45.json` exactly (this is the strongest test in the suite — it pins the
  tool against ground truth a human already hand-verified).
- [ ] 6.4 Implement the assembler to make 6.1–6.3 pass.

## 7. CLI wiring

- [ ] 7.1 **Test first:** `test_cli_writes_output_file` — invoke the CLI's `main()` with fixture
  paths + `--tier`/`--workflow-name` args via `subprocess`/direct `main()` call (follow whichever
  pattern `tests/test_fine_pilot_deck.py`'s CLI tests use), assert a `run_metadata_<config>.json`
  file is written matching the assembler's output.
- [ ] 7.2 **Test first:** `test_cli_rejects_missing_required_args` — omitting `--tier` or
  `--workflow-name` fails with a clear argparse error, not a downstream `KeyError`.
- [ ] 7.3 Implement `scripts/generate_run_metadata.py`'s `main()`/argparse wiring to make 7.1–7.2
  pass. Document usage in the script's module docstring (mirrors `generate_pilot.py`'s docstring
  convention).

## 8. Real-artifact validation (decide, per design.md D4 open question)

- [ ] 8.1 Check whether the 3 pilot configs' real pod-side `run_metadata.json`/`run.log` still
  exist on the NFS `runs/` tree (gitignored, may have been cleaned up since the pilot). If yes:
  run the real tool against them and diff the result against the committed
  `run_metadata_<config>.json` files (post-normalization differences expected and fine; verify no
  *value* regressions — same `final_time`, same `git.commit`, same kinematics). If the tool's
  output is a strict improvement, replace the 3 committed files with it in this PR. If the
  artifacts are gone, explicitly document that in this task (do not silently skip) and rely on the
  fixture-level tests (6.3) as the sole validation.

## 9. Docs

- [ ] 9.1 Update `openspec/project.md`'s "Current State → Implemented" line (around line 120,
  "Run metadata capture with docker/git/hardware tracking") to reference the new automated
  generator and note it now covers timing/kinematics/orchestration fields previously hand-typed.
- [ ] 9.2 Add a short usage note (README or module docstring) pointing the full 27-config corpus
  follow-on at this tool instead of hand-authoring its 27 metadata files.

## 10. Validate and ship

- [ ] 10.1 `openspec validate automate-run-metadata-capture --strict`.
- [ ] 10.2 Full test suite green (`uv run pytest`).
- [ ] 10.3 `/pre-merge-check`, open PR.
