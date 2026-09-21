# Tasks

TDD throughout. Markers are used precisely: **Test first** = a new test that MUST fail before its
implementation; **Characterization** = a new test that must pass both before and after (it pins
behaviour we are promising not to break); **Verify** = running an existing test, not writing one.

Phases map to five PRs. Phases 1, 2 and 4 are independent (verified against the modules: `dataset.py`
and `metadata_capture.py` share no import path — `read_final_time_from_csv` re-reads the CSV itself —
and Phase 4 touches only `cluster/argo/**`). **Phase 3 has no code or test dependency on Phase 2:**
`ns.cfl = 0.6` is a fixed constant derived once, offline, in `design.md` D2 from data that predates
this change; no Phase 3 task reads `realized_dt` or any Phase 2 function. The two phases are ordered
B-then-C for review flow only. The real coupling is downstream, in **Phase 7** (task 7.4), which uses
Phase 2's observed-dt fields to confirm after the fact that the chosen constant held in practice —
that is a post-merge validation step, not a merge-ordering constraint. Phase 5–6 depend on 1–4.

Phases 7–8 are **not commits on this branch**: 7 requires cluster GPU time, 8 acts on another PR.

## PR A — Phase 1: `init_iter`-aware extractor (#94)

- [x] 1.1 **Test first** — add a `forces_*.csv` fixture written with `init_iter = 2` (three rows at
      `iStep = 0`, first all-zero) and assert `_extract_config` returns `max_step` rows, exactly one
      `iStep = 0` row survives, and it is the **last** (non-zero forces). Must fail.
      *Name it `forces_*.csv`, never `IB_Particle_*.csv` — `.gitignore` ignores that pattern globally
      by name, so the natural name is silently unaddable and would pass locally then fail fresh CI.
      Confirm with `git ls-files` after adding.*
      — `tests/fixtures/forces_init_iter2.csv` + `test_dedup_removes_duplicate_init_rows_keeps_last`.
- [x] 1.2 **Test first** — assert `time` is strictly increasing per configuration. Must fail.
      — `test_dedup_time_strictly_increasing`.
- [x] 1.3 **Test first** — parametrize dedup over `init_iter ∈ (0, 1, 2, 5)`: exactly one `iStep = 0`
      row survives in every case, it is the last, and `len(df) == max_step` regardless. Must fail for
      `init_iter > 0`. *Nothing currently pins that the extractor is `init_iter`-value-agnostic.*
      — `test_dedup_parametrized_over_init_iter`.
- [x] 1.4 **Test first** — assert a CSV whose `iStep` sequence is non-monotonic (a checkpoint-restart
      re-emitting a range of steps) raises a clear config-named error rather than silently discarding
      the earlier correct rows under `keep="last"`. Must fail.
      — `test_dedup_raises_on_non_monotonic_istep`.
- [x] 1.5 **Characterization** — **deviation from the literal task text:** the coarse corpus's raw
      per-config CSVs live only under the gitignored `examples/prelim_sweep/runs/` and are not present
      in any checkout, so they cannot be re-extracted offline as written. Substituted two equivalent
      checks: (a) `test_dedup_is_noop_without_duplicates`, a characterization test against the
      existing no-duplicate-iStep fixture, asserting extraction is byte-for-byte unaffected; (b)
      confirmed `tests/test_force_surrogate_scale_invariance.py::test_committed_corpus_cf_is_van_veen_consistent`
      (which owns `_FROZEN_RAW_FORCE_SHA`) reads the **already-built** committed
      `examples/prelim_sweep/dataset.parquet` directly and never calls the extractor — structurally
      unaffected by any `_extract_config` change, verified passing before and after. Both pass.
- [x] 1.6 Add `"iStep"` to `_REQUIRED_CSV_COLUMNS`; update the "missing required column(s)" error
      message and its test. *Every existing fixture CSV already has `iStep`, so nothing else breaks.*
      — added `test_missing_istep_column_raises_naming_config`; confirmed no other fixture broke.
- [x] 1.7 Implement `drop_duplicates(subset="iStep", keep="last")` in `_extract_config`, before the
      `.to_numpy()` extraction. Also raises on a non-monotonic `iStep` sequence (task 1.4).
- [x] 1.8 **No update needed** — both fixtures used by these tests
      (`synthetic_ib_particle.csv`, `_make_run_tree`'s fixture) already have unique `iStep` per row,
      so dedup is a no-op for them and both tests pass unmodified. Verified by running both files.
- [x] 1.9 **Verify** — `_FROZEN_RAW_FORCE_SHA` still matches (coarse parquet untouched). Confirmed:
      `tests/test_force_surrogate_scale_invariance.py` 7/7 passed.

## PR B — Phase 2: run-observed metadata (#93)

- [x] 2.1 **Test first** — `read_final_time_from_csv` now returns a **3-tuple**
      `(final_time, timesteps, raw_row_count)`; changed arity rather than preserved it, since a
      caller needs both counts and there is exactly one production caller (`assemble_run_metadata`)
      plus one test, both updated in this commit — `test_read_final_time_from_csv_returns_distinct_and_raw_counts`
      (new, against the PR A `forces_init_iter2.csv` fixture) and `test_read_final_time_from_csv_uses_last_row`
      (existing, updated).
- [x] 2.2 **Test first** — added `run_healthy_full.log` and `run_cfl_limited_full.log` (10-line full
      series, no elision), distinct from the existing 6-line elided `run.log`. `read_dt_series_from_run_log`
      parses one `DT` value per `STEP =` line (1:1 in this format, not ~2 as originally guessed —
      verified against the real committed fixture format). `test_read_dt_series_from_run_log_healthy`,
      `test_compute_dt_observations_*`.
- [x] 2.3 **Test first** — `test_median_interior_dt_is_blind_to_cfl_limiting`. The CFL fixture's 9
      interior steps are `[5e-4,5e-4,3e-4,3e-4,3e-4,5e-4,5e-4,5e-4,5e-4]` (6/9 at nominal, mirroring
      the real worst config's 59%-at-ceiling shape) — median is nominal despite genuine CFL limiting.
- [x] 2.4 **Test first** — `test_compute_dt_observations_excludes_only_the_final_clamped_step`,
      synthetic series as directed.
- [x] 2.5 **Test first** — `test_compute_dt_observations_every_step_reduced_including_last`.
- [x] 2.6 **Test first** — `test_derive_stability_nominal/_deck_fallback/_cfl_limited_at_nominal/_cfl_limited_at_deck_fallback`,
      including the no-`stable_at_`-prefix assertion.
- [x] 2.7 **Test first** — **scope note:** tested via a new standalone `compute_run_completion`
      function (`test_compute_run_completion_truncated/_healthy`) rather than only through
      `assemble_run_metadata`, since the pure function needed no new fixture coupling. Also covered
      end-to-end via `test_assemble_metadata_includes_run_observation_fields`.
- [x] 2.8 **Deviation from the literal task text:** `realized_dt` is derived from `run.log`, not by
      differencing the CSV `time` column (see the spec's explicit prohibition and design D3/I5), so
      "a one-row CSV" / `np.diff` no longer apply. Substituted the equivalent edge case for the
      actual data source: `test_compute_dt_observations_raises_on_too_few_samples` (a `run.log`
      series with fewer than 2 samples raises, rather than silently omitting the excluded-final-step
      logic).
- [x] 2.9 **Same deviation as 2.8:** substituted `test_compute_dt_observations_raises_on_nan_in_series`
      (a non-finite value in the parsed `run.log` series raises) for the CSV-`time`-NaN framing.
- [x] 2.10 **Test first** — `test_cli_has_no_observation_override_flags` in
      `tests/test_generate_run_metadata_cli.py` (not `test_metadata_capture.py` — it needs the CLI's
      actual `argparse.ArgumentParser`). Required extracting `build_parser()` out of `main()` in
      `scripts/generate_run_metadata.py` (a minimal, behavior-preserving refactor) so the parser is
      testable without invoking the CLI end-to-end.
- [x] 2.11 Implemented `read_dt_series_from_run_log` + `compute_dt_observations`, wired into
      `assemble_run_metadata`.
- [x] 2.12 `derive_stability` reworked to accept `interior_dt_below_nominal`; named the field exactly
      as specified, avoiding the `dt_reduced` collision.
- [x] 2.13 Extended `_STABILITY_TOKENS` with both `cfl_limited_*` values.
- [x] 2.14 **No update needed, on inspection:** the new observed fields
      (`realized_dt`/`interior_dt_below_nominal`/`cycles_completed`/`reached_stop_time`/`cfl`) are
      **top-level** output keys per the spec text, not nested inside `timing` — so
      `result["timing"]`'s three-key shape (`final_time`/`timesteps`/`wall_time_s`) is unchanged and
      `test_assemble_metadata_produces_normalized_schema` needed no edit.
      `test_pilot_fixture_matches_real_capture_…_shape` compares the **pod-side** schema
      (`capture_surrogate_run_metadata`), which this PR does not touch — also unaffected. Both
      verified passing unmodified.
- [x] 2.15 Re-scoped to the raw row count. `test_assemble_metadata_raises_on_row_count_mismatch_uses_raw_count`
      (success case) plus the existing mismatch test, unchanged, still raises.
- [x] 2.16 **Verify** — all six existing raise-tests pass unmodified.
- [x] 2.17 Added both fixtures; documented the coupling addition in `README.md` (kept as prose
      bullets, matching the file's existing style, rather than converting to a table — the two new
      fixtures are explicitly uncoupled from the five-way group, so a table row would misrepresent
      them as joining that coupling). Confirmed `forces_s35_f085_p45.csv` untouched.
- [x] 2.18 **Test first** — `test_assemble_metadata_includes_run_observation_fields` (`result["cfl"]`)
      and `test_source_config_fields_includes_stop_time_and_cfl`. Added `cfl` (and `stop_time`, needed
      by `compute_run_completion`) to `source_config_fields`'s returned dict and to
      `assemble_run_metadata`'s output.

## PR C — Phase 3: `ns.cfl` as an opt-in targeted key (#92)

- [x] 3.1 **Verify** — both pass unmodified (confirmed via targeted run, then the full 883-test
      suite). This is the hard constraint the opt-in design satisfies.
- [x] 3.2 **Test first** — `test_generate_sweep_cfl_override_threaded_to_every_deck_and_manifest`,
      `test_generate_sweep_cfl_override_independent_of_plot_int_and_init_iter`.
- [x] 3.3 **Test first** — `test_render_inputs_cfl_none_preserves_base_value`.
- [x] 3.4 **Test first** — `test_render_inputs_missing_cfl_key_raises_when_overridden`.
- [x] 3.5 **Test first** — `test_manifest_records_cfl_per_config_and_omits_when_absent`,
      `test_generate_sweep_cfl_override_recorded_in_provenance_timestep_policy`.
- [x] 3.6 **Test first** — `test_regenerating_from_manifest_recorded_cfl_reproduces_decks_byte_identically`.
- [x] 3.7 Implemented. `derive_run_duration`'s 2-tuple shape untouched (not called by this task at
      all — `cfl` never affects sizing, only the deck's `ns.cfl` value).
- [x] 3.8 **Corrected during round-2 review, not merely followed:** the literal task text as
      originally written said to add `cfl` to `test_render_inputs_minimal_diff`'s `TARGET_KEYS` —
      that would have broken the very test it named, for exactly the reason this corrected text
      states. Implemented as corrected: `test_render_inputs_accepts_cfl_override`,
      `test_render_inputs_cfl_override_independent_of_plot_int_and_init_iter`; `TARGET_KEYS` left
      untouched; `test_render_inputs_minimal_diff` verified still passing.
- [x] 3.9 **Scope note:** `--cfl` threaded through `generate_full_corpus.py`
      (`test_generate_full_corpus_cli_accepts_cfl_flag`). The probe-tuple extension is **deferred to
      Phase 8** (not done here): `test_fine_corpus_git_commit_names_a_capable_commit` checks the
      commit named in the **currently committed** `sweep_provenance.json`, which still predates
      `--cfl` and is untouched by this PR — extending the probe now would be checking a commit that
      doesn't yet exist. Extend it once Phase 7's regeneration updates that provenance file.
- [x] 3.10a **Test first** — `test_generate_sweep_rejects_deck_with_nonzero_prescribed_vel`,
      `test_generate_sweep_rejects_deck_with_num_steps_below_max_step`, plus two no-false-positive
      regressions (`_accepts_deck_without_landmine_keys`, `_accepts_zero_prescribed_vel_and_sufficient_num_steps`).
- [x] 3.10 Implemented `_check_deck_safety`, called from `generate_sweep`'s per-config loop.
- [x] 3.11 Recorded in `design.md` D2 (already present from the proposal-authoring pass; re-verified
      current: worst config `s55_f115_p30` requires `cfl >= 0.490`, `0.6` chosen for 22% margin).

## PR D — Phase 4: orchestration (#95, #90)

- [x] 4.1 **Test first** — `test_workflow_deadline_covers_autoscale_formula_and_two_retries`. Settled
      on **one literal, 98,280 s (27.3h)**, used identically in the YAML, the test, and design.md —
      no second independently-rounded figure anywhere.
- [x] 4.2 **Test first** — `test_smoke_workflow_deadline_matches_sweep_workflow`.
- [x] 4.3 Raised to `98280` in both `force-surrogate-sweep.yaml` and `force-surrogate-smoke.yaml`;
      updated `test_argo_workflows.py:149`'s literal in the same commit.
- [x] 4.4 **Test first** — `test_single_config_template_retry_strategy`'s `retryPolicy` assertion
      updated to require `"Always"` (must-fail confirmed against the prior `"OnFailure"`).
- [x] 4.5 Changed to `"Always"`; updated the same test in the same commit; added a manifest comment
      explaining both the `retryPolicy` semantics (why not `"OnError"` either) and that `maxDuration`
      is wall-clock from the first attempt's start.
- [x] 4.6 **Test first** — folded into the same `test_single_config_template_retry_strategy` update:
      asserts `maxDuration: "20h"` (6 attempts × 2.86h measured worst case + the 62m backoff
      sequence, with margin), replacing the prior `"4h"` assertion.
- [x] **Gap found and closed during implementation, not in the original task list:** the spec's
      "retryStrategy backoff can cover the full configured retry limit" requirement normatively
      demands `maxDuration` actually accommodate 6 attempts — 4.6 tests this, but no task in the
      original list *implemented* raising the value (4.7 only re-derives `PER_CONFIG_HOURS`, a
      different, unrelated constant). Added: `backoff.maxDuration` raised from `"4h"` to `"20h"` in
      `force-surrogate-single-config.yaml`, in the same commit as 4.4/4.5/4.6.
- [x] 4.7 Re-derived `PER_CONFIG_HOURS` to `2.392` (from `pzdhl`), replaced the stale `vb8t5`
      citation. **Verified the constraint holds:** `2.392 ≤ 2.444`, so the formula stays at 26h;
      confirmed by running the full `test_submit_workflow_active_deadline.py` suite unmodified in
      result (only comments needed refreshing — the 43200/25200/14400/18000 literals are unchanged,
      since the shift from 2.4 doesn't cross a `ceil()` boundary at either tested `n`/`parallelism`).
      Refreshed the stale `2.4`-based comments in the same commit.
- [x] 4.8 **Verify** — confirmed; auto-scale stays conditional, untouched by this PR.
- [x] 4.9a **Test first** — `test_smoke_rejects_parallelism_flag`,
      `test_smoke_rejects_active_deadline_seconds_flag` (new file `test_submit_workflow_smoke_guards.py`).
- [x] 4.9 Implemented both `die()` guards in the `smoke)` case body.
- [x] 4.10 **Test first** — `test_smoke_defaults_to_the_cfl_worst_config`,
      `test_smoke_config_name_still_overridable_via_env`. **Tie-break resolved directly, not
      generically:** rather than a runtime "minimum measured `dt_min`" tie-break (which needs data
      from a run that hasn't happened yet for a first-time corpus), hardcoded the *specific* worst
      config `s55_f115_p30` (`cfl_req = 0.490`, confirmed the true worst against all three
      `s55_f115_*` pitch variants in design D2's table) as the new literal default — correct for
      *this* 27-config Aedes grid today. Also aligned `force-surrogate-smoke.yaml`'s own template-level
      parameter defaults (`config-name`/`input-file`/`max-step`) to the same config, for the bypass
      path where the WorkflowTemplate is submitted directly without `submit_workflow.sh`.
- [x] 4.11 **Deliberately deferred, not implemented:** dynamically deriving the worst config from a
      manifest is a materially larger change (it would need `smoke` to read the manifest, which it
      today explicitly does not — see `submit_workflow.sh`'s `require_manifest` comment distinguishing
      `full`/`smoke`) than fits this PR's scope. 4.10's literal default correctly serves the actual
      grid this project runs; filed as a follow-up for whenever a materially different grid is
      introduced.

## PR E — Phases 5–6: guards, acceptance gate, runbook

- [x] 5.1 **Test first** — add a corpus **registry** (explicit list, not a glob) with schema
      `{"path": ..., "has_parquet": bool, "has_per_config_metadata": bool}` per entry — both flags are
      needed: `has_parquet` for the parquet-tier guard (5.3), `has_per_config_metadata` for the
      per-config-metadata guard's scope (5.7). Assert the registry is non-empty, that both fields are
      honored, and that a corpus registered `has_parquet: true` but lacking one **fails loudly** rather
      than skipping. Must fail.
      *A glob over `examples/prelim_sweep*` also matches `prelim_sweep_fine_pilot` (3 configs, no
      parquet), and `prelim_sweep_fine` has no parquet on `main` at all until PR #91 merges — so a
      glob-driven guard would silently skip exactly the corpus it exists to protect.*
      `test_registry_is_non_empty_and_schema_fields_honored`,
      `test_missing_expected_parquet_fails_loudly`, `test_registered_absent_parquet_is_not_a_failure`
      in `tests/test_corpus_guards.py`; `CorpusEntry`/`CORPUS_REGISTRY`/`check_parquet_exists_if_registered`
      in `src/mosquito_cfd/force_surrogate/corpus_guards.py`.
- [x] 5.2 **Test first** — manifest/deck tier, applicable to every registered corpus regardless of
      parquet: each config's deck `max_step` equals its manifest `max_step` (two currently unchecked
      sources of truth), and the holdout set equals the manifest's recorded names. Must fail.
      `test_deck_max_step_matches_manifest`, `test_deck_max_step_mismatch_fails`,
      `test_holdout_matches_manifest`, `test_holdout_mismatch_fails`;
      `check_deck_matches_manifest_max_step`/`check_holdout_matches_manifest`.
- [x] 5.3 **Test first** — parquet tier for corpora that carry one: column set and order, row count
      vs manifest `max_step`, strictly increasing `time`, no NaN/Inf, units keys == measured columns.
      Must fail.
      `test_row_count_matches_manifest`/`_mismatch_fails`, `test_time_strictly_increasing`/
      `test_duplicate_time_fails`, `test_no_nan_or_inf`/`test_nan_fails`,
      `test_units_match_parquet`/`test_units_drift_fails`, `test_per_config_metadata_present`/
      `test_per_config_metadata_missing_fails`; `check_parquet_row_counts`,
      `check_time_strictly_increasing`, `check_no_nan_or_inf`, `check_units_match_parquet`,
      `check_per_config_metadata_present`. **Scope note:** column *order* is not separately checked —
      `check_units_match_parquet` checks the measured-column *set* against the units sidecar, which
      catches drift without a brittle exact-order assertion.
- [x] 5.4 **Test first** — the **normalized** symmetry invariant
      `|mean CF_x| / max|CF_x|` over the settled beat, with the tolerance pinned in a comment
      alongside the measured healthy maximum (`+0.0001`) and truncated minimum (`+0.0150`) that bound
      it. Assert it passes coarse and fails a truncated fixture. Must fail.
      *Do not use the absolute mean: coarse reaches −0.0289 against a truncated minimum of +0.0387, a
      1.33× window.*
      `test_symmetric_config_passes_the_ratio_check`, `test_truncated_config_fails_the_ratio_check`;
      `SYMMETRY_RATIO_TOLERANCE = 0.012`, `check_symmetry_invariant`.
- [x] 5.5 **Test first** — converged-beat tripwire for `wingbeat > 0`. Mark it provisional at `< 5`
      (coarse already sits at 4.015 against it) — task 8.7 re-derives it against the regenerated fine
      corpus once real data exists. Must fail.
      `test_converged_beat_tripwire_passes_normal_forces`/`_fails_on_spike`;
      `CONVERGED_BEAT_CF_X_TRIPWIRE = 5.0`, `check_converged_beat_tripwire`.
- [x] 5.6 **Test first** — assert the guard module imports no cluster/Argo/subprocess surface and
      reads only paths under the repo root, so "runs offline" is enforced rather than reviewed.
      Must fail.
      `test_guard_module_imports_no_cluster_or_subprocess_surface`,
      `test_guard_module_reads_only_paths_under_repo_root`.
- [x] 5.7 **Test first** — assert the per-config-metadata guard applies only to corpora that declare
      it. *`examples/prelim_sweep/` has **zero** `run_metadata_<config>.json` files — only a
      dataset-build `run_metadata.json` — so an unconditional assertion fails on the one corpus that
      currently has a parquet.* Must fail.
      `test_per_config_metadata_guard_scoped_to_corpora_that_declare_it`,
      `test_run_all_guards_on_healthy_synthetic_corpus_passes`/`_on_truncated_synthetic_corpus_fails`,
      `test_real_committed_corpus_passes_all_applicable_guards` (parametrized over
      `CORPUS_REGISTRY`), `test_fine_corpus_registry_entry_reflects_todays_state`; `ALL_CHECKS`/
      `run_all_guards`.
- [x] 6.0 **Test first** — build a minimal 2-config synthetic corpus fixture (manifest, decks,
      per-config metadata, `sweep_provenance` with and without a `cluster_run` CC-F1 entry) as the
      shared substrate for all Phase 6 tests; assert it is committed (`git ls-files`) and that its
      healthy variant passes the gate. Must fail.
      **Deviation from the literal task text:** implemented as `_make_corpus()` in
      `tests/test_acceptance_gate.py`, a single-config (not 2-config) corpus built dynamically under
      pytest's `tmp_path` per test (not a committed fixture on disk) — mirroring
      `test_corpus_guards.py`'s `_build_synthetic_corpus()` pattern from PR E's own 5.x tests, which
      the same review round found preferable to a committed fixture tree: it lets each test vary
      exactly one failure mode (`cf_x_pattern`, `interior_dt_below_nominal`, `field_capture`, `cc_f1`)
      via keyword arguments rather than maintaining N near-duplicate committed fixture directories.
      One config is sufficient because every gate check in 6.1–6.3 is scoped per-config; a 2-config
      corpus would exercise no additional gate logic, only iteration, which `run_acceptance_gate`
      already does generically over `manifest["configs"]`. No `git ls-files` assertion exists since
      there is no committed file to assert on; the "shared substrate" role is filled instead.
- [x] 6.1 **Test first** — assert the gate fails on (a) a CFL-limited config, (b) a config whose
      deduplicated row count ≠ `max_step`, (c) a corpus with no recorded CC-F1 result, (d) a config
      failing the normalized symmetry check; and passes a healthy corpus. Must fail.
      `test_cfl_limited_config_fails`, `test_row_count_mismatch_fails`,
      `test_missing_cc_f1_result_fails_a_field_capture_corpus`,
      `test_truncated_config_fails_the_symmetry_check`, `test_healthy_corpus_passes`,
      `test_non_field_capture_corpus_does_not_require_cc_f1`,
      `test_present_passing_cc_f1_result_does_not_fail_the_gate` in `tests/test_acceptance_gate.py`.
- [x] 6.2 **Test first** — assert the gate **recomputes** at least one quantity from raw run output
      rather than reading every value from the metadata JSON it is gating. Must fail.
      `test_gate_recomputes_row_count_rather_than_trusting_metadata` (a hand-edited metadata file
      lies about row count and `timing.timesteps`; the gate still fails because it re-derives the row
      count from `build_dataset()` on the raw CSV, never from the metadata JSON).
- [x] 6.3 **Test first** — assert a `cluster_run` record whose only evidence is a **partial**
      mid-sweep check does not satisfy the post-run gate. Must fail.
      `test_partial_mid_sweep_cc_f1_does_not_satisfy_the_gate`.
- [x] 6.4 Implement the gate as a library function plus a thin CLI driver under `scripts/`, mirroring
      `scripts/check_plotfile_velocity.py`'s shape (logic in the tested library), satisfying 6.1–6.3.
      `src/mosquito_cfd/force_surrogate/acceptance_gate.py` (`run_acceptance_gate`, `GateResult`) +
      `scripts/check_corpus_acceptance.py` (`build_parser`/`main`, CLI-only).
- [x] 6.5 **Test first** — assert gate outcomes are persisted to `sweep_provenance.cluster_run`,
      including a **CC-F1-shaped** entry specifically (plotfile path string, observed `x_velocity`
      min/max, pass verdict — not a generic name/value pair that any check could satisfy), plus
      `parallelism` and effective `activeDeadlineSeconds`. Must fail.
      `test_record_check_result_persists_cc_f1` (asserts the exact CC-F1 fields:
      `plotfile`/`x_velocity_min`/`x_velocity_max`/`verdict`), `test_record_check_result_records_parallelism_and_deadline`,
      `test_record_check_result_accumulates_multiple_checks`.
- [x] 6.5b Implement `cluster_run` persistence in the gate/CLI driver from 6.4, satisfying 6.5.
      `record_check_result()` in `acceptance_gate.py` — generic `**fields` kwargs (not a fixed
      CC-F1-only schema), satisfying 6.5's CC-F1 assertion because the runbook (6.7) always calls it
      with the CC-F1 field names; a schema-enforcing wrapper was not needed since the only caller is
      the runbook's own documented snippet.
- [x] 6.6 **Test first** — assert `sweep_provenance`'s supersession record is a list-valued history
      that accumulates, and update `test_fine_corpus_provenance_flags_superseded_runs`'s exact-list
      assertion — **same commit**. Must fail.
      Updated `test_fine_corpus_provenance_flags_superseded_runs` in `tests/test_full_corpus_deck.py`
      to assert `supersession_history` is a list and `supersession_history[0]["cluster_workflows"]`
      names the two stale runs.
- [x] 6.6b Implement the supersession-history restructure in `sweep.py`'s provenance writer,
      satisfying 6.6.
      `examples/prelim_sweep_fine/sweep_provenance.json`'s `superseded_by` dict restructured to a
      `supersession_history` list containing that same dict as its first entry; `sweep.py`'s
      provenance-writer comment (which documents this hand-added key is not auto-generated) updated
      to name the new key.
- [x] 6.7 Update `.claude/commands/submit-cluster-sweep.md`: insert the acceptance gate between
      `generate_run_metadata.py` and `extract_forces.py`; replace Step 4's
      `stability == "stable_at_5e-4"` check (unfalsifiable — it is a deck echo) with the observed
      fields; fix its CSV row-count check for `init_iter` (currently over-satisfied); instruct
      recording CC-F1's result; add the in-run `DT` check on the first completed pod (design D6);
      state explicitly that Step 4's **partial-corpus** pass criteria differ from the acceptance
      gate's **complete-corpus** ones; add a "Common Mistakes" row.
      Done — see the diff to `.claude/commands/submit-cluster-sweep.md`: Step 0's pilot-invalidation
      trigger, Step 2's `record_check_result` snippet, Step 4's `DT` grep + distinct-`iStep` row-count
      fix + `interior_dt_below_nominal` check + mid-sweep-vs-gate scope note, "After the Sweep
      Completes"'s mandatory gate insertion (renumbered 1–5), and 5 new "Common Mistakes" rows.
- [x] 6.8 Update `openspec/project.md:347`, which duplicates the same vacuous `stability` check and is
      not otherwise covered — after 6.7 it would contradict the runbook it defers to. Prefer deleting
      the duplicated procedure and pointing at the runbook.
      Done — the old "Mid-sweep partial-corpus check" procedure replaced with a pointer to
      `.claude/commands/submit-cluster-sweep.md`'s Steps 0–5 and "After the Sweep Completes".
- [x] 6.9 Add a scope note to `examples/prelim_sweep/README.md:46`, whose "guaranteeing whole periodic
      cycles" claim is true only while `ns.cfl` does not bind at that grid's resolution.
      Done — "at this corpus's 64³ grid resolution... This guarantee is conditional on that, not
      structural" added, cross-referencing `prelim_sweep_fine/README.md` and issue #92.
- [x] 6.10 Add a `docs/CHANGELOG.md` entry with a `(#NN)` reference — every other entry has one.
      Done — one bullet each under the existing single `### Added` and `### Fixed` headings for
      `## [Unreleased]`, both tagged `(#96)` (this change's predicted PR number).

### Prevention: move the lessons somewhere durable

These exist to stop this class recurring. They are in this change rather than a follow-up because an
OpenSpec `design.md` is **archived** after merge — which is exactly how the original error
propagated: the false claim that `ns.fixed_dt` overrides `ns.cfl` has been sitting in
`openspec/changes/archive/2026-08-03-add-wing-fine-grid-convergence/design.md` §D6 since August,
discoverable only by digging.

- [x] 6.11 Add a **pilot-invalidation trigger** to `submit-cluster-sweep.md` Step 0/1: before a full
      run, confirm whether the geometry, grid, or kinematic range has changed since the pilot that
      validated this corpus's timestep — and if so, state that the pilot's GO does not transfer and a
      re-pilot (or a worst-config smoke) is required.
      *The pilot was methodologically sound: it deliberately ran `s55_f115_p45`, the near-worst
      config, and reasoned correctly about CFL. It was invalidated by the later hinge fix moving
      `hinge_y` 2.0 → 0.5, doubling the moment arm and tip speed, and was never re-run. A pilot's
      validity is scoped to the physics it ran under; geometry changes invalidate it as surely as
      grid changes do.*
- [x] 6.12 **Reconcile with, do not duplicate, the existing CFL note.** `openspec/project.md`'s
      Conventions → Running Simulations → "Local Docker (A5000)" already has a "CFL at fine 256³ grid"
      bullet prescribing a *different* mitigation (lower `ns.fixed_dt` to `0.00025`) with no reference
      to the actual mechanism — landing new prose elsewhere in Conventions would create exactly the
      stale-adjacent-doc problem this proposal exists to fix. Rewrite that bullet in place to record
      the **corrected** mechanism: `fixed_dt` is a ceiling, `ns.cfl` an independent limiter that can
      push below it, with the `estTimeStep` / `predict_velocity` / `computeNewDt` chain cited, and
      this change's chosen fix (raise `ns.cfl` to 0.6) alongside the lower-`fixed_dt` alternative it
      previously prescribed exclusively. Explicitly supersede the archived §D6 claim that it is
      *"an inputs cap, not an enforcement."*
      Done — "CFL mechanism (corrected) and the `ns.cfl` fix" bullet in `project.md`'s Conventions →
      Running Simulations, replacing the old bullet in place; cites `estTimeStep()` line ~1503/1517
      and `predict_velocity`→`computeNewDt` at `NavierStokesBase.cpp:1114`; names both mitigations
      (lower `fixed_dt` vs. raise `ns.cfl`) and when each applies; explicitly supersedes the archived
      §D6 claim by name.
- [x] 6.13 Document the **local stability probe** recipe **in the same rewritten bullet as 6.12** (not
      a separate location — they land in the same subsection): pull the corpus's exact image digest
      (not the `:fp64` tag, which moves), run a control at the committed `ns.cfl` and confirm it
      reproduces the corpus bit-exactly, then vary the one parameter under test. ~25 min per case, no
      cluster quota. Note the arena cap and that a CFD run is bit-reproducible across GPU models
      (A40 → A5000), which is what makes the control comparison meaningful.
      Done — "Local stability probe" sub-list immediately following the 6.12 bullet in the same
      subsection: digest-pull + label verification, bit-exact control reproduction criteria
      (`max |time diff| == 0`, identical dt series, `Fx`/`Fz` correlation `1.00000000`), the arena-cap
      cross-reference, and — matching the round-2 review finding that made task 7.2 mandatory — a
      final point stating a startup-transient-only probe is insufficient evidence on its own because
      it never exercises a stroke reversal.
- [x] 6.14 Add an erratum to `docs/force_surrogate/fine-grid-pilot-report.md`. **The file is not an
      unqualified GO** — it already carries a dated (2026-08-10) "Geometry note" disclosing the hinge
      defect and predicting *"this pilot's 'no CFL fallback needed' result was measured at roughly
      half the true tip speed... the corrected-geometry regeneration must re-confirm `dt=5e-4`
      stability rather than assume this pilot's numbers transfer."* The erratum converts that
      forward-looking prediction into a backward-looking, confirmed outcome: per #92, it did not
      transfer — the pilot's tested config `s55_f115_p45` reached `cycles_completed ≈ 1.835` of 2.0
      (91.7%) under the corrected geometry at `ns.cfl = 0.3`, and the corpus regenerated at
      `ns.cfl = 0.6` under this change. Link to #92 and this change.
      Done — erratum block appended directly under the existing "Geometry note" blockquote, stating
      the confirmed `cycles_completed ≈ 1.835/2.0` outcome and scoping the report's GO to the
      pre-hinge-fix geometry.
- [x] 6.15 Record the general reviewing principle in `project.md` Conventions — it generalizes well
      past CFL and currently has no home:
      *(a)* a check that reconciles an artifact only against **itself** (no NaN, ranges sane, internal
      consistency) cannot detect a wrong artifact; at least one check must reconcile against an
      **external** reference — the manifest, or a physical invariant;
      *(b)* a metadata field computable from the inputs alone is not evidence about a run;
      *(c)* a mandatory check with no recorded result is indistinguishable from one never run.
      Done — new "### Verification Principles" section under `project.md`'s Conventions, all three
      principles stated with the #92 concrete instance for each (the internal-consistency checks that
      passed, the deck-echoed `stability` field, the unrecorded CC-F1 check).

## PR F — Review round 1 fixes (5-agent `/review-pr` on PR #97, before merge)

PR #97 (this change's PR A–E commits, pushed for review) received a 5-agent adversarial review
with 4 BLOCKING and 8 IMPORTANT findings, cross-validated (several findings independently caught
by multiple reviewers) and spot-verified against the shipped code and IAMReX source before being
accepted. All fixed via TDD in a follow-up commit, same PR, before merge.

- [x] F.1 **Test first** — `test_read_dt_series_from_run_log_preserves_nan_line_instead_of_dropping_it`,
      `test_read_dt_series_from_run_log_preserves_inf_line`,
      `test_compute_dt_observations_raises_when_run_log_has_nan_in_interior_step` in
      `tests/test_metadata_capture.py`. **BLOCKING**: `_STEP_DT_RE` could not match a literal
      `nan`/`inf` token, silently dropping the line rather than raising — a diverged run's final
      interior step could vanish from the series, letting the previous nominal step wrongly stand
      in as "the final clamped step" and mislabeling a diverged run `stable_at_5e-4` (the exact
      failure class #92 exists to catch, reintroduced at the log-parsing layer). Fixed by widening
      `_STEP_DT_RE`'s value group to `nan`/`inf`/`-inf` (case-insensitive), letting
      `compute_dt_observations`'s existing `np.isfinite` guard catch it instead of the regex
      silently excluding the line.
- [x] F.2 **Test first** — `test_malformed_manifest_json_raises_clear_file_identified_error`,
      `test_malformed_provenance_json_raises_clear_file_identified_error`,
      `test_malformed_run_metadata_json_raises_clear_file_identified_error` in
      `tests/test_acceptance_gate.py`. **BLOCKING**: malformed JSON in any of the gate's three
      inputs raised a raw, contextless `json.JSONDecodeError` naming no file, among up to 29 files
      a real corpus has. Fixed by renaming `metadata_capture._load_json_clear_error` to the public
      `load_json_clear_error` and reusing it at all three (now four, including
      `record_check_result`) load sites in `acceptance_gate.py`.
- [x] F.3 **Test first** — `test_config_with_no_settled_beat_rows_fails_rather_than_being_silently_skipped`
      in both `tests/test_corpus_guards.py` and `tests/test_acceptance_gate.py`. **BLOCKING**: a
      config with zero `wingbeat >= 1` rows (a run so short it never reaches a settled beat — the
      single worst truncation case) was simply absent from `_settled_beat_symmetry_ratios`'s
      returned dict, so the one guard whose stated purpose is catching truncation gave a false
      "no issue" signal for the most severely truncated case. Fixed in both
      `check_symmetry_invariant` (corpus_guards.py) and `run_acceptance_gate` (acceptance_gate.py)
      by iterating the manifest's config list and flagging any name absent from the ratios dict.
      **Folded in the same commit (IMPORTANT, independently flagged by 3 of 5 reviewers):** the
      ratio function itself was duplicated verbatim between the two modules; renamed to the public
      `corpus_guards.settled_beat_symmetry_ratios` and imported (not copied) by `acceptance_gate.py`,
      closing the "two unchecked sources of truth" drift risk this proposal's own Verification
      Principles warn about.
- [x] F.4 **Test first** — `test_init_iter_only_field_capture_dict_does_not_require_cc_f1` in
      `tests/test_acceptance_gate.py`. **IMPORTANT**: `is_field_capture = bool(provenance.get(
      "field_capture"))` tested dict truthiness, not whether the dict's own `plot_int` actually
      indicates plotfile output — a corpus with only `ns.init_iter` set (no plotfiles ever
      produced, per `sweep.py`'s own recorded rationale) would be wrongly required to have a CC-F1
      result it can never produce. Fixed by checking
      `provenance.get("field_capture", {}).get("plot_int", -1) > 0`.
- [x] F.5 **Test first** — `test_generate_sweep_accepts_disabled_num_steps_sentinel` in
      `tests/test_force_surrogate_sweep.py`. **IMPORTANT**: `_check_deck_safety`'s `ns.num_steps`
      lint compared `num_steps < max_step` unconditionally, false-positiving on IAMReX's own
      default/disabled sentinel `-1` (`main.cpp`: `num_steps = -1`, gated `if (num_steps > 0)`,
      verified directly against the IAMReX source). Fixed by adding a `num_steps > 0` guard before
      the comparison.
- [x] F.6 **Test first** — `test_dedup_raises_when_duplicates_occur_at_nonzero_istep` in
      `tests/test_force_surrogate_dataset.py`. **IMPORTANT**: the dedup's monotonic-`iStep` check
      is vacuously satisfied by a CSV whose `iStep` never advances (a solver-writer bug, not
      `ns.init_iter`'s expected re-emission at `iStep=0` only), silently collapsing the whole file
      to one row via `keep="last"` with no warning. Fixed by raising when a duplicate group exists
      at any `iStep != 0`.
- [x] F.7 **Test first** — `test_ratio_just_under_tolerance_passes`/`test_ratio_just_over_tolerance_fails`
      in both `tests/test_corpus_guards.py` and `tests/test_acceptance_gate.py`. **IMPORTANT**:
      `SYMMETRY_RATIO_TOLERANCE = 0.012` had no test near its actual decision boundary despite
      being tight and load-bearing (comment-documented ~1.25–1.3× margins) — every existing test
      used far-field healthy/truncated cases. No code change needed; the comparison was already
      correct (`>`, not `>=`/`==`), confirmed by both boundary cases passing immediately.
- [x] F.8 Fixed `CONVERGED_BEAT_CF_X_TRIPWIRE`'s justifying comment in `corpus_guards.py`, which
      cited `2.88` for the measured coarse-corpus max `|CF_x|` — independently recomputed at
      `4.015`, matching `design.md` D6 and `tasks.md` (both already correct; only this one comment
      was stale). **IMPORTANT**, doesn't change gate behavior (5.0 exceeds both figures).
- [x] F.9 Fixed `design.md` D3, which still asserted "`run.log` emits roughly two `dt` lines per
      step, needs deduplication" — task 2.2's own note already documented this was checked during
      implementation and found false (1:1, no dedup implemented or needed); D3 itself was never
      corrected. **IMPORTANT** design-doc/code mismatch.
- [x] F.10 Clarified `compute_run_completion`'s docstring: the `2.0 * fixed_dt` tolerance on
      `reached_stop_time` is a deliberately loose sanity bound, not a calibrated threshold like
      `interior_dt_below_nominal` or `SYMMETRY_RATIO_TOLERANCE` — `reached_stop_time` is recorded
      as a diagnostic only and never gates the acceptance check. **IMPORTANT**, docstring-only.
- [x] F.11 **Test first** — `test_supersession_history_accumulates_a_second_entry_without_disturbing_the_first`
      in `tests/test_full_corpus_deck.py`. **IMPORTANT**: the "accumulates, does not overwrite"
      supersession-history scenario was spec'd but only ever tested against the real corpus's
      current single-entry state. Since the field is hand-maintained JSON with no code path that
      appends, this pins the list's schema-level semantics (order preserved, no merge/collision,
      earlier entry untouched) directly rather than leaving the contract untested.
- [x] F.12 Corrected `openspec/changes/add-fine-corpus-run-verification/specs/force-surrogate/spec.md`'s
      "The gate does not certify itself" scenario, which described the gate recomputing the
      CFL/timestep check (`interior_dt_below_nominal`) from raw run output — the opposite of both
      `design.md` D6 (which calls `interior_dt_below_nominal` "the hard, exact gate," deliberately
      trusted, not re-derived) and the shipped `acceptance_gate.py` (whose own docstring says
      exactly that). **BLOCKING** spec/implementation mismatch — the code and design were already
      correct and consistent with each other; only the spec scenario's wording was wrong. Rewrote
      the scenario to describe the row-count recomputation `test_gate_recomputes_row_count_
      rather_than_trusting_metadata` actually verifies, and added a note explaining the
      `interior_dt_below_nominal` trust boundary explicitly.
- [x] F.13 **Verify** — full local suite after all of F.1–F.12: 946 passed, 14 skipped (GPU-only),
      6 deselected (up from 930 pre-review; 16 new tests, 0 regressions). `ruff check`/
      `ruff format --check` clean over CI's six-path scope. `openspec validate --strict` passes.

## PR G — Review round 2 fixes (5-agent `/review-pr` re-run on PR #97, after PR F)

PR F's fixes were themselves re-reviewed by a second 5-agent `/review-pr` pass, specifically
instructed to verify each round-1 fix rather than trust its commit message. Found 2 NEW blocking
regressions in round 1's own fix code (one severe: the nan/inf regex fix was itself incomplete),
1 vacuous test masquerading as a regression guard, and 2 IMPORTANT robustness gaps. All fixed via
TDD, cross-verified by direct reproduction before being accepted.

- [x] G.1 **Test first** — `test_read_dt_series_from_run_log_preserves_signed_nan_inf_tokens`
      (parametrized over `-nan`/`+nan`/`-inf`/`+inf`/`-infinity`) in `tests/test_metadata_capture.py`.
      **BLOCKING regression in PR F's own fix**: `_STEP_DT_RE`'s alternation tried the numeric
      branch (`[\d.eE+-]+`) before the nan/inf branch; the numeric branch also matches a lone
      sign character and "wins" on a signed token, so `DT = -nan` parsed to `'-'`, and `float('-')`
      raised a confusing, unlabeled `ValueError` instead of ever reaching the NaN guard — the
      exact failure mode PR F claimed to have fixed, reintroduced for every *signed* variant
      (glibc `printf` emits `-nan` for a real divergence). Fixed by reordering the alternation so
      the nan/inf branch is tried first — reproduced broken, then fixed, then reproduced correct,
      before either state was trusted from reasoning alone.
- [x] G.2 **Test first** — `test_malformed_manifest_json_raises_clear_file_identified_error` in
      both `tests/test_force_surrogate_dataset.py` and `tests/test_corpus_guards.py`. **BLOCKING,
      PR F's fix incomplete**: `scripts/check_corpus_acceptance.py`'s actual CLI entry point calls
      `dataset.load_manifest_configs()` *before* `run_acceptance_gate` ever runs, and that
      function still did a raw `json.loads` — reproduced live against the real CLI with a
      malformed `--manifest`, showing the exact contextless-crash failure mode PR F's finding #4
      was supposed to eliminate, just via a different, unpatched call path. `corpus_guards.py`'s
      `_load_manifest` had the identical gap (same file, sibling reader, flagged separately by
      the round-2 Code Quality reviewer). Fixed by moving `load_json_clear_error` out of
      `metadata_capture.py` into `sidecar.py` — a true leaf module with no
      force-surrogate-internal dependencies, avoiding the import cycle
      `dataset → metadata_capture → runner → dataset` that importing it directly from
      `metadata_capture.py` into `dataset.py` would have created — and using it at both sites.
      `acceptance_gate.py`'s import updated to source it from `sidecar.py` directly.
- [x] G.3 **Removed a vacuous test** flagged by the round-2 Testing/TDD reviewer:
      `test_supersession_history_accumulates_a_second_entry_without_disturbing_the_first`
      (added in PR F) never called any `mosquito_cfd` code — it only exercised Python's own
      list/dict equality semantics on data it constructed itself, so it could not fail for any
      defect in this package regardless of what the source code does. Since there is genuinely
      no code path that appends to `supersession_history` (confirmed via
      `grep -rn "supersession_history" src/ scripts/`), deleted rather than kept as decorative
      false confidence, with a comment explaining why and where a real test would belong if a
      writer function is ever implemented.
- [x] G.4 **Test first** — `test_null_field_capture_value_does_not_crash_the_gate` in
      `tests/test_acceptance_gate.py`. **IMPORTANT**: `provenance.get("field_capture",
      {}).get("plot_int", -1) > 0` (PR F's fix for the dict-truthiness bug) is not robust to
      `{"field_capture": null}` — `dict.get(key, default)` only substitutes `default` when the
      key is *absent*, not when present with value `None`, so `.get("plot_int", ...)` on `None`
      raised `AttributeError` rather than the clear, contextual errors this module raises
      everywhere else for malformed hand-editable input. Fixed with
      `(provenance.get("field_capture") or {}).get(...)`.
- [x] G.5 **Test first** — `test_generate_sweep_accepts_num_steps_zero` in
      `tests/test_force_surrogate_sweep.py`, `test_record_check_result_creates_missing_parent_directory`
      in `tests/test_acceptance_gate.py`. **IMPORTANT coverage gaps** flagged by the round-2
      Testing/TDD reviewer: PR F's `num_steps > 0` fix was only tested at `-1`, not the more
      plausible operator-typo value `0`; PR F's incidental (uncalled-out in its commit message)
      `provenance_path.parent.mkdir(parents=True, exist_ok=True)` addition to
      `record_check_result` had no dedicated test. Both pinned; no code defect found in either
      (the `num_steps=0` case already took the correct branch; the `mkdir` line already worked).
- [x] G.6 **Verify** — full local suite after G.1–G.5: re-run and confirmed green (see commit),
      `ruff check`/`ruff format --check` clean, `openspec validate --strict` passes.

## Phase 9 — Verification (run after completing each of Phases 1–6, not only once at the end)

- [x] 9.1 `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/` — CI's exact six-path list.
      Final run: "All checks passed!"
- [x] 9.2 `uv run ruff format --check` over the same six paths.
      Final run: "115 files already formatted."
- [x] 9.3 `uv run pytest -v -m "not gpu"` — CI's exact invocation; a bare `pytest -v` does not match.
      Final run: 930 passed, 14 skipped, 6 deselected in 203.24s.
- [x] 9.4 `git ls-files <path>` for every new fixture — `.gitignore`'s global `IB_Particle_*.csv`
      pattern silently skips the natural name.
      Verified: `forces_init_iter2.csv`, `run_healthy_full.log`, `run_cfl_limited_full.log` all
      tracked (committed in PRs A/B; PR E's own tests use dynamically-built `tmp_path` corpora with
      no new fixture files — see 6.0's deviation note).
- [x] 9.5 File a follow-up issue for `/run-ci-locally`, which lints only `src/` while CI lints six
      paths including `tests/` and `scripts/` — exactly where this change adds code, so a lint error
      would pass locally and fail CI.
      Filed as [#96](https://github.com/talmolab/mosquito-cfd/issues/96) — distinct from the
      pre-existing #81 (CI's own allowlist missing directories); this one is `/run-ci-locally`'s
      local-reproduction command drifting narrower than CI's actual invocation. Filing this issue
      consumed the PR-number slot this change's `docs/CHANGELOG.md` entries had predicted as `(#96)`
      for itself — those entries were corrected to `(#97)` to match the next number in sequence.

## Phase 7 — Cluster re-run (after PRs A–E merge; requires GPU time and explicit go-ahead)

- [x] 7.0 **Snapshot the 27 configs' raw NFS CSVs to a separate path before anything else**, using a
      plain copy — **not** the `provision()` codepath, which has prior form for a self-overwrite
      data-loss bug (now fixed, but this snapshot exists specifically as insurance against that class
      of bug recurring, so don't route through it). This is not about preserving data from configs
      that won't be touched — all 27 are being re-run intentionally — it is insurance against the
      re-run process itself failing (this repo has two documented precedents: an NFS provisioning gap
      that stalled a submission 22h, and the `provision()` bug). Without it, a partial re-run failure
      could leave a config with neither the old (superseded but CC-F1-validated) data nor a completed
      new run. Safe to delete after task 7.5's gate passes and Phase 8 merges.
      **Scoped to the small artifacts, not full plotfile/checkpoint trees:** the task text says "CSVs"
      literally; snapshotted each config's CSV, `run.log`, `run_metadata.json`, `wing.vertex`, and
      `particle*` files (226 MB total, verified byte-identical to source) to
      `examples/prelim_sweep_fine_runs_pr91_snapshot_20260918/` on NFS — an initial attempt at a full
      `cp -a` of the whole `runs/` tree (1.1 TB, mostly checkpoints/plotfiles) was caught and aborted
      before completing.
- [x] 7.1 Regenerate all 27 fine decks with `--cfl 0.6`; confirm the only per-deck change vs the
      committed decks is `ns.cfl`, and that the manifest records `cfl`.
      **Also required `--plot-int 100 --init-iter 2`, not just `--cfl`:** the generator's own bare
      defaults are force-only and silently reverted field capture on the first attempt (caught via the
      per-deck diff showing `init_iter`/`plot_int` changes too, not just `cfl`; reverted and redone).
      Regeneration also drops `sweep_provenance.json`'s `supersession_history` (documented, no
      preserving code path) — manually restored the prior hinge-fix entry and appended a new one for
      this regeneration superseding PR #91's `pzdhl`/`zpkvt` runs.
      `tests/test_full_corpus_deck.py::test_committed_fine_corpus_matches_regeneration` didn't thread
      `cfl` through and would have failed permanently on this change; fixed in the same commit.
- [x] 7.2 **Mandatory precondition, not optional — run one full config (`s55_f115_p30`) at
      `ns.cfl = 0.6` to completion (~2.4 GPU-h) and pass it through the acceptance gate before
      submitting the other 26.** The local probe (design D4) covered only 11.4% of one period and
      never reached a stroke reversal, where flapping-wing aerodynamics can produce peak velocities
      the impulsive-start transient does not exercise. This is the only check that confirms the
      solver stays stable past that point, for ~4% of the total re-run cost. Do not proceed to 7.3 for
      the remaining 26 configs until this passes.
      `force-surrogate-smoke-8fvgf` succeeded (2h4m, 2h3m19s GPU-time). Result:
      `interior_dt_below_nominal: false`, `realized_dt` min/mean/max all exactly `0.0005`
      (`frac_below_nominal: 0.0`), `cycles_completed: 1.9993` (vs. ~1.83 under the old `cfl=0.3`),
      `reached_stop_time: true`. CC-F1 plotfile check passed
      (`x_velocity ∈ [-22.97, 4.97]`, genuinely non-zero) and was recorded via `record_check_result`.
      Scoped acceptance gate (reduced one-config manifest) passed.
- [x] 7.3 Run `/submit-cluster-sweep` for the remaining 26 configs, recording the CC-F1 result and the
      in-run `DT` check at the Step 4 gate.
      **First submission attempt was wrong and was caught and corrected:** `submit_workflow.sh full`
      submits the whole committed manifest, not "the remaining N" — the first `full` call re-submitted
      all 27 (including the already-validated smoke config); stopped ~3 min in (negligible GPU cost)
      and resubmitted against a manifest trimmed to the correct 26 (excluding `s55_f115_p30`), per the
      runbook's own Step 5 recovery pattern, then restored the local manifest. Also deviated from the
      runbook's own Step 3 table, which names a stale `--active-deadline-seconds 93600` example
      superseded by this change's own Phase 4 fix (the committed YAML's literal is now `98280`,
      deliberately higher to cover two retries) — submitted at the committed default rather than
      overriding it down to the stale number.
      `force-surrogate-sweep-vgn92`: all 26 configs `Succeeded`, `verify-complete` passed, 23h51m
      total. Step 4 mid-sweep check (run at 2/26 finished, live-progress spot-checked before that):
      zero CFL-limited steps, correct row counts, clean forces — reported to the user, who confirmed
      continuing unattended.
- [x] 7.4 Generate metadata for all 27; confirm every config reports `interior_dt_below_nominal =
      false`, `reached_stop_time`, and `cycles_completed` at the healthy value.
      All 27 confirmed: `interior_dt_below_nominal: false`, `reached_stop_time: true`,
      `cycles_completed` ≈ 1.9993–1.9996 depending on `frequency_fstar` group, `stability:
      stable_at_5e-4` for every config — zero exceptions.
- [x] 7.5 Run the acceptance gate over the full corpus; it must pass before any parquet is built.
      `check_corpus_acceptance.py` against the real 27-config manifest: **passed for all 27.**
- [x] 7.6 Rebuild `dataset.parquet` + `dataset.units.json`; confirm `len(df) == Σ max_step = 109,656`
      (restored, because uniform dt means every config terminates on `max_step` as the healthy ones
      already do).
      `extract_forces.py` (no `--allow-missing`): **109,656 rows, dropped=none.** No NaN/Inf; every
      config's mean `CF_x` well within the symmetry tolerance.
- [x] 7.7 Write `examples/prelim_sweep_fine/README.md` — the corpus is now first-class and publishes
      six new metadata fields with no narrative documentation at all.
      Written: what's-here file table, field-capture (CC-F1) and CFL-fix (`ns.cfl=0.6`) explanations,
      the six run-observed fields (`cfl`/`stop_time`/`realized_dt`/`interior_dt_below_nominal`/
      `cycles_completed`/`reached_stop_time`), the supersession history, and regenerate/rebuild
      commands. Notes explicitly that `surrogate/`/`figures/` don't exist yet for this corpus.
- [x] 7.8 Update `docs/field_surrogate/roadmap.md` CC-F3 with the storage measurement from the
      corrected run, or state explicitly that it is insensitive to the `cfl` change. CC-F3 also
      carries a second, unaddressed forward-looking claim — *"must also re-confirm `dt=5e-4`
      numerical stability against the corrected hinge before submitting... not confirmed to
      transfer"* — close that loop too: link to #92 as the confirmation that it did not transfer,
      and to this change as the fix.
      Measured (excluding stale `.old.*` copies from prior regenerations, and excluding the parent
      run directory itself from the `du` traversal — an early measurement attempt double-counted both):
      **≈0.58 TB plotfiles + ≈0.23 TB checkpoints ≈ 0.84 TB total** across the corpus, insensitive to
      `ns.cfl` (noted in place). Closed the stability-transfer claim **in the Sequencing note where it
      actually lives** (not under the CC-F3 heading itself, which only names CC-F3 for the *storage*
      default it deviates from) — added a "Resolved 2026-09-19" block confirming it did not transfer
      (issue #92) and citing this change as the fix.

## Phase 8 — Close out PR #91

- [ ] 8.1 Sync PR #91's branch onto post-PR-E `main` **before** any regeneration — its existing
      parquet was built by the pre-dedup extractor and is invalid. This is a full artifact
      regeneration, not a rebase.
- [ ] 8.2 Update #91 with the corrected corpus, all 27 regenerated metadata files, and the
      `cluster_run` block including gate results, `parallelism` and effective deadline.
- [ ] 8.3 Correct #91's claims: the #63 wording ("verified on both workflows" is unsupportable for a
      2.86 h single-config workflow — soften to "consistent with"), the #64 status
      (known-insufficient, not unverified), the row count, and disclose both the original truncation
      and the `ns.cfl` change. Add the missing `(#91)` CHANGELOG reference.
- [ ] 8.4 Re-run `/review-pr 91`, then merge.
- [ ] 8.5 Close #92, #93, #94, #95, #90, #20.
- [ ] 8.6 Archive this change **only after 8.5** — not at PR-E merge, since #91 is still open against
      it and the specs would not yet reflect reality.
- [ ] 8.7 Re-derive the provisional converged-beat `|CF_x| < 5` tripwire (task 5.5) against the
      regenerated fine corpus's actual data; tighten it if the margin supports a smaller bound.
