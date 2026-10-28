# Tasks

Every implementation task names the test written **first** and the behaviour it pins; record red
before and green after. Every new guard is mutation-tested on a saved-bytes copy of the file under
test (never restored with `git checkout`), and its kill count is recorded on the task. Test paths are
anchored at `Path(__file__)`. CI checks out at depth 1, so no test reads git history. Toy fixture
values that a test asserts are **absent** must be collision-proof (e.g. config-R² −7.123, 0.4567,
not 0.94 / 0.99, which are substrings of plausible skill values). New assertions match
"phase-only baseline", never bare "baseline" (the Sane–Dickinson line uses that word).

Commit plan (CI state is that of the commit when pytest is run on it; nothing is pushed until
task 34):

| Commit | Content | State |
|---|---|---|
| C0 `docs(openspec): propose replace-config-r2-with-baseline-skill` | `openspec/changes/replace-config-r2-with-baseline-skill/**` | green |
| C1 `feat(force-surrogate): phase-only baseline for skill scoring` | §1 | green |
| C2 `feat(force-surrogate): phase_baseline_skill block in metrics.json` | §2 | green |
| C3 `feat(force-surrogate): seed sweep in run_training and --sweep-seeds` | §3 | green (gpu tests run on the A5000) |
| C4 `feat(force-surrogate): evidence figure reports skill over the phase-only baseline` | §4 | green |
| C5 `test(force-surrogate): tie committed artifacts to the seed sweep and phase-only baseline skill` | §5, strict-xfail | green (listed XFAILs) |
| C6 `data(force-surrogate): retrain with the seed sweep` | §6 artifacts; `test_figure_metadata_names_the_committed_surrogate_outputs` marked strict-xfail (the figure's `metrics_json_sha256` is stale until C7) | green (listed XFAILs) |
| C7 `data(force-surrogate): regenerate the evidence figure; README skill table` | §7 figure + READMEs, every xfail marker removed | green, full suite incl. gpu |
| C8 `docs: roadmap, CHANGELOG, visualization-tooling wording; check off tasks` | §8 | green |

Run notes (measured numbers, D5 outcome) live in the scratchpad until C7 exists, so the tree is
clean whenever an artifact is generated; tasks.md is checked off once, in C8.

## 0. Record the blast radius before touching code

0. [x] Record the committed tests this change is expected to touch. **Any test outside this list
   that needs editing halts the change for a decision.**
   - `tests/test_force_surrogate_evidence_figure.py`
     - `_toy_metrics` (:59): gains `phase_baseline_skill` and `seed_sweep`; config-R² literals made
       collision-proof.
     - `test_fixture_matches_committed_pr5_schema` (:99): its committed-schema half gains the new
       blocks → moves into the C5 strict-xfail set.
     - `test_panel_annotation_reads_metrics` (:211), `..._null_renders_na` (:222),
       `..._missing_key_raises` (:229): re-pinned to skill / range / R² / RMSE.
     - `test_build_caption_discloses_everything` (:298), `..._off_panel_claims_are_data_driven_not_hardcoded`
       (:323), `..._flags_an_on_panel_negative_tell_not_just_off_panel` (:342),
       `..._names_the_worst_offender_when_multiple_targets_are_negative` (:364),
       `..._mutates_with_metrics` (:395): re-pinned to skill, phase-only baseline R², the skill floor
       and the below-baseline flag. Its Sane–Dickinson assertions ("not used as a quantitative
       baseline", "uncalibrated", "3.2") are kept unchanged.
     - `test_build_caption_aggregate_r2_does_not_round_to_a_literal_1_00` (:381): **re-pinned** (the
       caption no longer prints the aggregate) to the `>0.999` rule for per-axis R² and skill.
     - `test_build_figure_caption_names_its_single_seed` (:478), `..._says_when_the_seed_is_not_recorded`
       (:488): re-pinned to `seed_sweep.primary_seed`, `k` seeds, "single seed, no range", and
       "missing `seed_sweep` raises".
     - `test_build_figure_caption_states_the_lab_frame_moment_caveat` (:493): stays green unchanged.
     - `test_baseline_not_plotted_anywhere` (:445): kept; extended with "no line/scatter beyond the
       per-config points and the 1:1 line".
     - `test_generate_writes_three_artifacts` (:520), `test_missing_metrics_key_leaves_no_partial_artifact`
       (:712), `test_generate_json_sidecars_are_lf` (:584, extended to `run_metadata.json`):
       sidecar keys / required keys.
     - `test_cli_delegates_to_library` (:767): `--seed` removed from `make_evidence_figure.py`.
     - `test_readme_carries_full_disclosures` (:801), `test_readme_throughput_figures_match_the_committed_sidecar`
       (:869): test code unchanged; README literals change. **Timing-sensitive gates**:
       `1e6 ≤ throughput < 1e7`, `"2.4" not in readme`, `throughput_speedup > 1000`,
       `latency_speedup < 1000`, `batch_size == 12535`, and `test_no_false_diffused_ib_claim.py`'s
       "2.64" substring scan of the regenerated sidecar (a full-precision float can contain it by
       chance). If a re-measured value trips one, stop and decide.
     - `test_readme_config_resolved_r2_matches_committed_metrics` (:849, regex :840, allowlist :844):
       expected green unchanged if D5(a) holds and README prose follows D8.
     - `test_committed_figure_metrics_matches_committed_inputs` (:895): re-pinned to the new sidecar
       keys → C5 strict-xfail set.
   - `tests/test_committed_surrogate_provenance.py`
     - `test_seed_variation_record_matches_the_committed_surrogate` (:113): drop only the final
       commit-equality assertion (a retrain at a new commit must break it; D5); keep the rest.
     - `test_readme_seed_table_is_the_seed_record` (:152), `test_regenerated_records_carry_a_clean_git_commit`
       (:56): unchanged.
     - `test_figure_metadata_names_the_committed_surrogate_outputs` (:102): code unchanged, but red
       between C6 and C7 (new `metrics.json`, stale figure record) → strict-xfail in C6 only.
   - `tests/test_force_surrogate_train_driver.py`: `test_parser_wires_all_flags` (:24) and
     `test_main_delegates_without_importing_torch` (:60) extended with `--sweep-seeds`.
   - `tests/test_force_surrogate_train_gpu.py`: `test_full_round_trip_writes_four_artifacts` (:134)
     extended for the new blocks. `test_run_training_records_the_dataset_it_consumed` (:166) stays
     unchanged (library default is no sweep).
   - Gates expected green unchanged: `test_force_surrogate_train.py` `test_metrics_json_has_config_resolved`
     (:385), `test_metrics_json_keys_round_trip` (:492), `test_predictions_frame_schema_and_membership`
     (:478), `test_provenance_cpu_tier_digest_timestamp_seeds` (:532, `seeds == {"global": 1234}`);
     `test_force_surrogate_scale_invariance.py`; `test_no_false_diffused_ib_claim.py`;
     `test_comparison_figure.py`; `test_make_comparison_figure_cli.py`.
0a. [x] Commit C0 (this proposal). `openspec validate replace-config-r2-with-baseline-skill --strict`.

---

## 1. Phase-only baseline (CPU tier, `train.py`) — C1

1. [x] **Test first** — known answer: two reference configs sampling `sin(2πφ)` and `2 + cos(2πφ)`,
   the second with 3× the rows, rows shuffled. Baseline at query phases equals the unweighted mean
   of the two periodic linear interpolants, not the row-weighted mean; shuffled == sorted input.
2. [x] **Test first** — periodic wrap: a query between a config's last sample (e.g. 0.95) and 1.0
   interpolates toward its phase-0 sample (hand-computed).
3. [x] **Test first** — holdout exclusion: holdout targets set to 1e6 → baseline bitwise unchanged;
   `reference_configs` equals the sorted `split == "train"` configs, including a seed's val configs.
4. [x] **Test first** — beats: a config with two converged beats + a startup beat contributes the
   mean of its two converged beat curves, counted once against a single-beat config; startup rows
   have no effect.
5. [x] **Test first** — `ValueError` naming the problem for: no reference config; a beat with < 2
   rows; a duplicate phase within a beat; a non-finite reference value; a reference phase of
   exactly 1.0 or < 0; a non-finite or out-of-range **query** phase.
6. [x] **Test first** — torch-free: add `build_phase_only_baseline` (and, in §2–§3,
   `compute_baseline_skill`, `summarize_seed_sweep`) to the torch-barred subprocess test
   `test_pure_helpers_import_without_torch`; built twice → bitwise identical.
7. [x] Implement `build_phase_only_baseline(df, query_phase, target_names)` →
   `(predictions, definition)`. Mutation-test 1–5 (row-weighted mean, no `period`, holdout included,
   beats pooled, duplicate/range/query checks removed); record kills. `ruff check` + `ruff format`.
   Commit C1.

## 2. Skill and the `phase_baseline_skill` block (CPU tier) — C2

8. [x] **Test first** — `compute_baseline_skill` known answers: surrogate = truth → 1; surrogate =
   baseline → 0; surrogate with twice the baseline's SSE → −1 (unclipped); baseline = truth → NaN,
   serialized `null`; `phase_baseline_rmse` / `phase_baseline_r2` known answers; zero rows and
   mismatched shapes raise `ValueError`.
9. [x] **Test first** — `build_metrics(..., phase_baseline=...)` writes `phase_baseline_skill` with
   the definition keys under `phase_baseline` and per-target `{skill, phase_baseline_rmse,
   phase_baseline_r2}` for all six targets; with `phase_baseline=None` the block is absent and the §0
   key-set gates stay green.
10. [x] Implement. Mutation-test 8–9; record kills. Ruff. Commit C2.

## 3. Seed sweep — C3

11. [x] **Test first** — `summarize_seed_sweep(runs, primary_seed)`: `seeds` primary first; `range`
    NaN-aware min/max over all seeds incl. the primary; all-`null` → `null`; one seed → min == max.
12. [x] **Test first** (torch-free) — duplicate or negative seeds (sweep == primary; repeated; < 0) raise
    `ValueError` before `dataset_path` is read (pass a nonexistent path) and before `out_dir` exists.
13. [x] **Test first** (torch-free) — order and atomicity, using the seam in design D4: with
    `_fit_one_seed` and `_measure_inference` monkeypatched (the recorder raises on the last seed so
    no `torch.save` is reached), the call order is `[primary, *sweep]`; with the recorder raising on the second seed,
    the error propagates and `out_dir` contains none of the four artifacts.
14. [x] **Test first** — driver: `--sweep-seeds` parses N ints, defaults to the four seeds after `--seed` (1235–1238 for 1234),
    accepts zero values, and passes through to `run_training`; library `run_training` defaults to
    `sweep_seeds=()`. `build_training_metadata(seeds={"global": 1234, "sweep": [1235, 1236]})`
    round-trips (CPU tier).
15. [x] **Test first, torch tier** (`@pytest.mark.gpu`, parametrized over `cpu` and `cuda`, toy
    dataset, few epochs):
    - (a) `sweep_seeds=()` vs `(a, b)`: identical predictions, checkpoint tensors, and every
      `metrics.json` value except `inference`;
    - (b) seed `b` standalone == the `runs` entry for `b` in a sweep after `a`, exactly;
    - (c) `run_metadata.json` seeds record the sweep; `test_full_round_trip_writes_four_artifacts`
      covers the new blocks.

    Run red, then green after task 16, in WSL:
    `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/mosquito-cfd-train uv run --frozen --group train pytest -m gpu tests/test_force_surrogate_train_gpu.py -rs`.
    Record **0 skipped**. If (b) fails on `cuda`, stop before C3 at the D5(b) decision point
    (subprocess per sweep seed, or not) with the user.
16. [x] Implement: seed validation first; per-seed work factored into `_fit_one_seed` (own lazy
    torch import) without changing the primary path's operations or their order; the primary model
    object kept and saved exactly as today (no CPU copy — the committed checkpoint has `cuda`
    storage tags); provenance captured after training and before any write, as today (update the
    `build_training_metadata` docstring only if its wording changes); baseline computed once;
    primary trained first and inference measured right after it, as today; sweep seeds metrics-only;
    all four artifacts written after the last seed. wandb logs the primary run with `seed_sweep` in
    its payload. Driver flag. Mutation-test 11–14; record kills. Ruff. Commit C3.

## 4. Evidence figure (CPU tier) — C4

17. [x] **Test first** — re-pin the §0 figure tests and `_toy_metrics`, then add:
    - annotation: skill (3 dp), "(k seeds: lo to hi)", R², RMSE; each mutated in metrics → text
      changes;
    - rendering: skill and R² 0.9996/0.9997 → `>0.999`; null → `n/a`; range −0.150..0.992 →
      "−0.150 to 0.992"; −0.0004 → scientific, never `−0.000`;
    - caption: plotted seed and `k`; skill defined against the phase-only baseline; phase-only
      baseline R² for the three axes; the amplitude/shape caveat and README pointer; the skill floor
      (changing which target holds the minimum changes the floor value, never names a "weakest"
      target); negative minima named as below the phase-only baseline, a minimum of exactly 0 not;
      null off-panel skill / null baseline R² / null range → `n/a`, all-null → "undefined for every
      target"; CF_mx/CF_mz skill; lab-frame wording; **no** config-R² literal (−7.123, 0.4567)
      anywhere in the caption;
    - `k == 1` → "single seed, no range"; missing `phase_baseline_skill` / `seed_sweep` / a panel
      entry → `KeyError` before any file is written;
    - no line or scatter on any axis beyond the per-config points and the 1:1 line.
18. [x] **Test first** — sidecar: `primary_seed`, `n_seeds`, six-target `skill`, `pointwise_r2`,
    `phase_baseline_pointwise_r2`, `skill_floor` equal metrics.json; no `config_mean_r2`; every
    number the caption prints equals its sidecar value within display rounding (#116); figure
    `run_metadata.json` seeds equal `{"global": primary_seed, "sweep": seeds[1:]}`; both sidecars LF.
19. [x] Implement in `evidence_figure.py` and `scripts/make_evidence_figure.py` (drop the
    script's `--seed` and `generate_evidence_figure`'s `seeds` parameter; seeds from `metrics.json`). Remove `_config_mean_r2` from the figure path; update the stale
    docstring in `comparison_figure.py` (:253–258). Mutation-test 17–18; record kills. Ruff.
    Commit C4.

## 5. Committed-artifact guards (CPU tier), strict-xfail until regenerated — C5

20. [x] **Test first** — `test_committed_seed_sweep_is_internally_consistent`: `seed_sweep.seeds ==
    [primary_seed, *run_metadata.seeds.sweep]`, `primary_seed == run_metadata.seeds.global`; each
    statistic of the primary run entry equals the top-level value; each run's `val_configs` equals
    `make_config_splits(filter_converged_beat(dataset), seed=s).val_configs`, and the primary's
    equals `reproducibility.val_configs`.
21. [x] **Test first** — `test_committed_phase_baseline_skill_recomputes`:
    `build_phase_only_baseline(dataset, holdout_predictions.phase)` + `compute_baseline_skill` on the
    committed predictions equals `metrics.json` `phase_baseline_skill` within 1e-12, and
    `reference_configs` == sorted train configs. (Catches row misalignment inside `run_training`.)
22. [x] **Test first** — `test_readme_skill_table_is_metrics_json`: rows
    `` | `CF_c` | s | lo to hi | b | `` for all six targets equal `metrics.json` at 3 dp (U+2212
    normalized); assert on sample strings that `_TABLE_ROW` cannot match a skill row, that the skill
    regex cannot match a config-R² row, and that the header is matched by neither.
23. [x] Re-pin `test_committed_figure_metrics_matches_committed_inputs`, the committed half of
    `test_fixture_matches_committed_pr5_schema`, and `test_seed_variation_record_matches_the_committed_surrogate`
    per §0.
24. [x] Mark each committed-artifact test that is red against today's artifacts
    `@pytest.mark.xfail(strict=True, reason="#127: regenerated in C6/C7")`; record the node-ID list.
    `uv sync --frozen --group viz && uv run pytest -m "not gpu"`: green, XFAIL set == the list.
    Mutation-test 20–22 on saved-bytes copies of the committed JSON/README; record kills. Ruff.
    Commit C5. `git status --porcelain` empty.

## 6. Retrain — OPERATOR-RUN (WSL2 + local A5000), NOT CI-GATED — C6

> **Human checkpoint before the GPU run.** Before it, run a local code review of C1–C5
> (`/code-review`) so that no code fix is needed after artifacts exist.

25. [x] Pre-flight in WSL from the worktree root: `UV_PROJECT_ENVIRONMENT=$HOME/.venvs/mosquito-cfd-train`,
    `uv sync --frozen --group train`; `get_git_info()` prints C5's 40-hex commit with `dirty: false`
    (WSL git takes `--git-dir` per command; do not export `GIT_DIR`/`GIT_WORK_TREE`);
    `git status --porcelain` empty; `CUBLAS_WORKSPACE_CONFIG` unset; digest from
    `examples/prelim_sweep/run_metadata.json`.
26. [x] Train into a scratch directory **outside the repository** on ext4 (e.g.
    `$HOME/mosquito-cfd-127/surrogate`; not `/tmp`): `uv run --frozen --group train python
    scripts/train_surrogate.py --dataset examples/prelim_sweep/dataset.parquet --out-dir <scratch>
    --docker-digest <digest> --timestamp <utc> --seed 1234 --sweep-seeds 1235 1236 1237 1238
    --epochs 2000 --device cuda --wandb disabled`.
27. [x] **Pre-registered gate (design D5):** (a) `cmp` scratch `surrogate.pt` and
    `holdout_predictions.parquet` against the committed ones; (b) each seed's `config_mean_r2` ==
    `seed_variation.json` hinge-referenced, exactly. Any failure **halts** and follows D5's diagnosis
    with the user; nothing is loosened or re-pinned to pass, and nothing is copied into the repo.
28. [x] `git diff --exit-code uv.lock`. Record measured skill per target (plotted seed + range)
    against #125's bin numbers in the scratchpad (reported, not gated).
29. [x] **Human checkpoint before committing regenerated binaries** (state the size growth). Copy
    `metrics.json` and `run_metadata.json` in (pt/parquet unchanged by D5); remove the xfail markers
    that now pass; add the strict-xfail marker to
    `test_figure_metadata_names_the_committed_surrogate_outputs`; run `pytest -m "not gpu"` and confirm
    the XFAIL set; commit C6 with that list in the message.

## 7. Figure and READMEs — C7

30. [x] `git status --porcelain` empty and HEAD == C6. Regenerate the figure
    (`scripts/make_evidence_figure.py`, same digest, new timestamp). Inspect the PNG visually.
31. [x] README (`examples/prelim_sweep/README.md`), per design D8: restructure the honest-reading
    section; add the guarded skill table; change the false sentences at :247–254, :313, :321,
    :362–368; extend the schema list (:242–245) and the `metrics.json` row (:237); training command
    gains `--sweep-seeds`; reword :329–332 ("the plotted seed's config-resolved R² is …") keeping the
    five canonical `CF_c ≈v` config-R² quotes that `_QUOTED_TARGETS` requires; refresh speedup literals and restate the latency's observed range;
    "config-resolved (cycle-mean) R²", never "skill", for config-R²; no CF-name ≈/= prose except
    config-R²; moments are lab-frame components about the hinge (never "pitch"/"roll" moment);
    wing-frame conversion "deferred, not currently tracked"; n=5 wording ("no shift detected",
    "ranges"). `figures/README.md` :11–13, :18. Extend `test_readme_carries_full_disclosures` for the
    amplitude/shape caveat and CF_mx/CF_mz skill.
31a. [x] **One PNG only.** First remove every remaining xfail marker. Then the full suite before
    committing: ruff check + format check over the CI paths
    (`src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`),
    `uv sync --frozen --group viz && uv run pytest -m "not gpu"` (no XFAIL left), the WSL gpu command
    with `-rs` (0 skipped), `git diff --exit-code uv.lock`. Commit C7. If anything later changes
    `evidence_figure.py` or its script before the push, rewrite local history (`git reset --soft C6`,
    re-commit, regenerate the figure from a clean tree); if it changes `train.py`, its script or
    `metrics.json`, reset to C5 and redo §6 too. Only one PNG blob is ever pushed.

## 8. Docs, reconcile, ship — C8

32. [x] `docs/force_surrogate/roadmap.md`: row 12 → ✅; new row for this change (#127; closes
    #125/#116; no skill numbers, points to `metrics.json` and the README) before #110's row, whose
    "blocked until" points at it; row 5's pointer names `phase_baseline_skill` / `seed_sweep`.
    `docs/CHANGELOG.md`: entry with the D5 outcome, **BREAKING** sidecar key removal, no skill numbers.
    `openspec validate replace-config-r2-with-baseline-skill --strict`.
33. [x] Reconcile proposal / design / spec / tasks against the implementation; record any deviation
    in the proposal under `### Why N instead of M?` and file an issue for any workaround. Provenance:
    `git diff --quiet <surrogate run_metadata commit> HEAD -- src/mosquito_cfd/force_surrogate/train.py scripts/train_surrogate.py`
    and `git diff --quiet <figure run_metadata commit> HEAD -- src/mosquito_cfd/force_surrogate/evidence_figure.py scripts/make_evidence_figure.py`;
    either non-empty forces regeneration under 31a. Check off tasks; commit C8.
34. [ ] **Human checkpoint before pushing.** `/pre-merge-check`; PR to `main`: "Closes #127.",
    "Closes #125.", "Closes #116." on separate lines; "Unblocks #110"; #115/#124/#102 named only as
    out of scope (no closing keyword near them). Name the two recorded commits (reachable via
    `refs/pull/<N>/head` after squash; `inputs.hash` is the content link). Squash message written by
    hand (what changed, the D5 outcome, binary growth), not the default commit list.
35. [ ] After merge: `/cleanup-merged`, including the OpenSpec archive.
