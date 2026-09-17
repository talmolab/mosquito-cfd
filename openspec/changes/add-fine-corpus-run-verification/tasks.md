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

- [ ] 5.1 **Test first** — add a corpus **registry** (explicit list, not a glob) with schema
      `{"path": ..., "has_parquet": bool, "has_per_config_metadata": bool}` per entry — both flags are
      needed: `has_parquet` for the parquet-tier guard (5.3), `has_per_config_metadata` for the
      per-config-metadata guard's scope (5.7). Assert the registry is non-empty, that both fields are
      honored, and that a corpus registered `has_parquet: true` but lacking one **fails loudly** rather
      than skipping. Must fail.
      *A glob over `examples/prelim_sweep*` also matches `prelim_sweep_fine_pilot` (3 configs, no
      parquet), and `prelim_sweep_fine` has no parquet on `main` at all until PR #91 merges — so a
      glob-driven guard would silently skip exactly the corpus it exists to protect.*
- [ ] 5.2 **Test first** — manifest/deck tier, applicable to every registered corpus regardless of
      parquet: each config's deck `max_step` equals its manifest `max_step` (two currently unchecked
      sources of truth), and the holdout set equals the manifest's recorded names. Must fail.
- [ ] 5.3 **Test first** — parquet tier for corpora that carry one: column set and order, row count
      vs manifest `max_step`, strictly increasing `time`, no NaN/Inf, units keys == measured columns.
      Must fail.
- [ ] 5.4 **Test first** — the **normalized** symmetry invariant
      `|mean CF_x| / max|CF_x|` over the settled beat, with the tolerance pinned in a comment
      alongside the measured healthy maximum (`+0.0001`) and truncated minimum (`+0.0150`) that bound
      it. Assert it passes coarse and fails a truncated fixture. Must fail.
      *Do not use the absolute mean: coarse reaches −0.0289 against a truncated minimum of +0.0387, a
      1.33× window.*
- [ ] 5.5 **Test first** — converged-beat tripwire for `wingbeat > 0`. Mark it provisional at `< 5`
      (coarse already sits at 4.015 against it) — task 8.7 re-derives it against the regenerated fine
      corpus once real data exists. Must fail.
- [ ] 5.6 **Test first** — assert the guard module imports no cluster/Argo/subprocess surface and
      reads only paths under the repo root, so "runs offline" is enforced rather than reviewed.
      Must fail.
- [ ] 5.7 **Test first** — assert the per-config-metadata guard applies only to corpora that declare
      it. *`examples/prelim_sweep/` has **zero** `run_metadata_<config>.json` files — only a
      dataset-build `run_metadata.json` — so an unconditional assertion fails on the one corpus that
      currently has a parquet.* Must fail.
- [ ] 6.0 **Test first** — build a minimal 2-config synthetic corpus fixture (manifest, decks,
      per-config metadata, `sweep_provenance` with and without a `cluster_run` CC-F1 entry) as the
      shared substrate for all Phase 6 tests; assert it is committed (`git ls-files`) and that its
      healthy variant passes the gate. Must fail.
- [ ] 6.1 **Test first** — assert the gate fails on (a) a CFL-limited config, (b) a config whose
      deduplicated row count ≠ `max_step`, (c) a corpus with no recorded CC-F1 result, (d) a config
      failing the normalized symmetry check; and passes a healthy corpus. Must fail.
- [ ] 6.2 **Test first** — assert the gate **recomputes** at least one quantity from raw run output
      rather than reading every value from the metadata JSON it is gating. Must fail.
- [ ] 6.3 **Test first** — assert a `cluster_run` record whose only evidence is a **partial**
      mid-sweep check does not satisfy the post-run gate. Must fail.
- [ ] 6.4 Implement the gate as a library function plus a thin CLI driver under `scripts/`, mirroring
      `scripts/check_plotfile_velocity.py`'s shape (logic in the tested library), satisfying 6.1–6.3.
- [ ] 6.5 **Test first** — assert gate outcomes are persisted to `sweep_provenance.cluster_run`,
      including a **CC-F1-shaped** entry specifically (plotfile path string, observed `x_velocity`
      min/max, pass verdict — not a generic name/value pair that any check could satisfy), plus
      `parallelism` and effective `activeDeadlineSeconds`. Must fail.
- [ ] 6.5b Implement `cluster_run` persistence in the gate/CLI driver from 6.4, satisfying 6.5.
- [ ] 6.6 **Test first** — assert `sweep_provenance`'s supersession record is a list-valued history
      that accumulates, and update `test_fine_corpus_provenance_flags_superseded_runs`'s exact-list
      assertion — **same commit**. Must fail.
- [ ] 6.6b Implement the supersession-history restructure in `sweep.py`'s provenance writer,
      satisfying 6.6.
- [ ] 6.7 Update `.claude/commands/submit-cluster-sweep.md`: insert the acceptance gate between
      `generate_run_metadata.py` and `extract_forces.py`; replace Step 4's
      `stability == "stable_at_5e-4"` check (unfalsifiable — it is a deck echo) with the observed
      fields; fix its CSV row-count check for `init_iter` (currently over-satisfied); instruct
      recording CC-F1's result; add the in-run `DT` check on the first completed pod (design D6);
      state explicitly that Step 4's **partial-corpus** pass criteria differ from the acceptance
      gate's **complete-corpus** ones; add a "Common Mistakes" row.
- [ ] 6.8 Update `openspec/project.md:347`, which duplicates the same vacuous `stability` check and is
      not otherwise covered — after 6.7 it would contradict the runbook it defers to. Prefer deleting
      the duplicated procedure and pointing at the runbook.
- [ ] 6.9 Add a scope note to `examples/prelim_sweep/README.md:46`, whose "guaranteeing whole periodic
      cycles" claim is true only while `ns.cfl` does not bind at that grid's resolution.
- [ ] 6.10 Add a `docs/CHANGELOG.md` entry with a `(#NN)` reference — every other entry has one.

### Prevention: move the lessons somewhere durable

These exist to stop this class recurring. They are in this change rather than a follow-up because an
OpenSpec `design.md` is **archived** after merge — which is exactly how the original error
propagated: the false claim that `ns.fixed_dt` overrides `ns.cfl` has been sitting in
`openspec/changes/archive/2026-08-03-add-wing-fine-grid-convergence/design.md` §D6 since August,
discoverable only by digging.

- [ ] 6.11 Add a **pilot-invalidation trigger** to `submit-cluster-sweep.md` Step 0/1: before a full
      run, confirm whether the geometry, grid, or kinematic range has changed since the pilot that
      validated this corpus's timestep — and if so, state that the pilot's GO does not transfer and a
      re-pilot (or a worst-config smoke) is required.
      *The pilot was methodologically sound: it deliberately ran `s55_f115_p45`, the near-worst
      config, and reasoned correctly about CFL. It was invalidated by the later hinge fix moving
      `hinge_y` 2.0 → 0.5, doubling the moment arm and tip speed, and was never re-run. A pilot's
      validity is scoped to the physics it ran under; geometry changes invalidate it as surely as
      grid changes do.*
- [ ] 6.12 **Reconcile with, do not duplicate, the existing CFL note.** `openspec/project.md`'s
      Conventions → Running Simulations → "Local Docker (A5000)" already has a "CFL at fine 256³ grid"
      bullet prescribing a *different* mitigation (lower `ns.fixed_dt` to `0.00025`) with no reference
      to the actual mechanism — landing new prose elsewhere in Conventions would create exactly the
      stale-adjacent-doc problem this proposal exists to fix. Rewrite that bullet in place to record
      the **corrected** mechanism: `fixed_dt` is a ceiling, `ns.cfl` an independent limiter that can
      push below it, with the `estTimeStep` / `predict_velocity` / `computeNewDt` chain cited, and
      this change's chosen fix (raise `ns.cfl` to 0.6) alongside the lower-`fixed_dt` alternative it
      previously prescribed exclusively. Explicitly supersede the archived §D6 claim that it is
      *"an inputs cap, not an enforcement."*
- [ ] 6.13 Document the **local stability probe** recipe **in the same rewritten bullet as 6.12** (not
      a separate location — they land in the same subsection): pull the corpus's exact image digest
      (not the `:fp64` tag, which moves), run a control at the committed `ns.cfl` and confirm it
      reproduces the corpus bit-exactly, then vary the one parameter under test. ~25 min per case, no
      cluster quota. Note the arena cap and that a CFD run is bit-reproducible across GPU models
      (A40 → A5000), which is what makes the control comparison meaningful.
- [ ] 6.14 Add an erratum to `docs/force_surrogate/fine-grid-pilot-report.md`. **The file is not an
      unqualified GO** — it already carries a dated (2026-08-10) "Geometry note" disclosing the hinge
      defect and predicting *"this pilot's 'no CFL fallback needed' result was measured at roughly
      half the true tip speed... the corrected-geometry regeneration must re-confirm `dt=5e-4`
      stability rather than assume this pilot's numbers transfer."* The erratum converts that
      forward-looking prediction into a backward-looking, confirmed outcome: per #92, it did not
      transfer — the pilot's tested config `s55_f115_p45` reached `cycles_completed ≈ 1.835` of 2.0
      (91.7%) under the corrected geometry at `ns.cfl = 0.3`, and the corpus regenerated at
      `ns.cfl = 0.6` under this change. Link to #92 and this change.
- [ ] 6.15 Record the general reviewing principle in `project.md` Conventions — it generalizes well
      past CFL and currently has no home:
      *(a)* a check that reconciles an artifact only against **itself** (no NaN, ranges sane, internal
      consistency) cannot detect a wrong artifact; at least one check must reconcile against an
      **external** reference — the manifest, or a physical invariant;
      *(b)* a metadata field computable from the inputs alone is not evidence about a run;
      *(c)* a mandatory check with no recorded result is indistinguishable from one never run.

## Phase 9 — Verification (run after completing each of Phases 1–6, not only once at the end)

- [ ] 9.1 `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/` — CI's exact six-path list.
- [ ] 9.2 `uv run ruff format --check` over the same six paths.
- [ ] 9.3 `uv run pytest -v -m "not gpu"` — CI's exact invocation; a bare `pytest -v` does not match.
- [ ] 9.4 `git ls-files <path>` for every new fixture — `.gitignore`'s global `IB_Particle_*.csv`
      pattern silently skips the natural name.
- [ ] 9.5 File a follow-up issue for `/run-ci-locally`, which lints only `src/` while CI lints six
      paths including `tests/` and `scripts/` — exactly where this change adds code, so a lint error
      would pass locally and fail CI.

## Phase 7 — Cluster re-run (after PRs A–E merge; requires GPU time and explicit go-ahead)

- [ ] 7.0 **Snapshot the 27 configs' raw NFS CSVs to a separate path before anything else**, using a
      plain copy — **not** the `provision()` codepath, which has prior form for a self-overwrite
      data-loss bug (now fixed, but this snapshot exists specifically as insurance against that class
      of bug recurring, so don't route through it). This is not about preserving data from configs
      that won't be touched — all 27 are being re-run intentionally — it is insurance against the
      re-run process itself failing (this repo has two documented precedents: an NFS provisioning gap
      that stalled a submission 22h, and the `provision()` bug). Without it, a partial re-run failure
      could leave a config with neither the old (superseded but CC-F1-validated) data nor a completed
      new run. Safe to delete after task 7.5's gate passes and Phase 8 merges.
- [ ] 7.1 Regenerate all 27 fine decks with `--cfl 0.6`; confirm the only per-deck change vs the
      committed decks is `ns.cfl`, and that the manifest records `cfl`.
- [ ] 7.2 **Mandatory precondition, not optional — run one full config (`s55_f115_p30`) at
      `ns.cfl = 0.6` to completion (~2.4 GPU-h) and pass it through the acceptance gate before
      submitting the other 26.** The local probe (design D4) covered only 11.4% of one period and
      never reached a stroke reversal, where flapping-wing aerodynamics can produce peak velocities
      the impulsive-start transient does not exercise. This is the only check that confirms the
      solver stays stable past that point, for ~4% of the total re-run cost. Do not proceed to 7.3 for
      the remaining 26 configs until this passes.
- [ ] 7.3 Run `/submit-cluster-sweep` for the remaining 26 configs, recording the CC-F1 result and the
      in-run `DT` check at the Step 4 gate.
- [ ] 7.4 Generate metadata for all 27; confirm every config reports `interior_dt_below_nominal =
      false`, `reached_stop_time`, and `cycles_completed` at the healthy value.
- [ ] 7.5 Run the acceptance gate over the full corpus; it must pass before any parquet is built.
- [ ] 7.6 Rebuild `dataset.parquet` + `dataset.units.json`; confirm `len(df) == Σ max_step = 109,656`
      (restored, because uniform dt means every config terminates on `max_step` as the healthy ones
      already do).
- [ ] 7.7 Write `examples/prelim_sweep_fine/README.md` — the corpus is now first-class and publishes
      six new metadata fields with no narrative documentation at all.
- [ ] 7.8 Update `docs/field_surrogate/roadmap.md` CC-F3 with the storage measurement from the
      corrected run, or state explicitly that it is insensitive to the `cfl` change. CC-F3 also
      carries a second, unaddressed forward-looking claim — *"must also re-confirm `dt=5e-4`
      numerical stability against the corrected hinge before submitting... not confirmed to
      transfer"* — close that loop too: link to #92 as the confirmation that it did not transfer,
      and to this change as the fix.

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
