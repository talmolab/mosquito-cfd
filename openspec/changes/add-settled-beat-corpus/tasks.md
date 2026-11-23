# Tasks: add-settled-beat-corpus

> **Archive only after PR 4 merges.** If Stage 1 ends in `stop`, archive after PR 3 with the
> Stage 1 delta only (`design.md` D1).

Rules:
- **Tests first.** Every test is written first and seen to fail for the right reason. A new guard
  is also shown to be failable: the guard is mutated and the test must fail.
- **Commits.** One commit per numbered group unless the group is split below. Messages say
  `advances #192` (plus `#101`/`#103` where relevant) and never use a closing keyword.
- **Checks before each commit:** `uv run --frozen ruff check` and `ruff format --check`, plus
  `uv run --frozen pytest -m "not gpu"` from Git Bash.
- **Branches.** Each PR gets a fresh branch from `origin/main`. Merge `main` in, never rebase. Run
  `git merge-base --is-ancestor origin/main HEAD` before every push.
- **Before each push:** `openspec validate add-settled-beat-corpus --strict`.
- **HUMAN GATE** marks a step that needs the user's explicit go-ahead.

## PR 1 — settling metric, pre-registration, Stage 1 decks (branch `add-settled-beat-corpus`)

### 1. Metric (`force_surrogate/settling.py`)
- [ ] 1.1 Tests first (`tests/test_settling.py`):
  - one test per scenario of "Beat-to-beat settling metric";
  - the boundaries: exactly 95% of rows (complete), `ρ` exactly 1 (not contracting), a
    denominator exactly at `STEP_FLOOR` (skipped when the numerator is too), `B = 5` (two ratios)
    and `B = 6` (three ratios);
  - per-beat row counts at `f*` 0.85 and 1.15 built as `step · dt` alternate (e.g. 2352/2353) and
    sum to `max_step`;
  - a tiny but nonzero peak (`1e-6`) is allowed and reported;
  - the metric reads `wingbeat` and `phase` and never recomputes them (a frame with a
    deliberately inconsistent `wingbeat` is used as given);
  - every `ValueError` path names the config and the column.
- [ ] 1.2 Known-answer fixture: copy the needed columns (`config_name, time, phase, wingbeat,
  frequency_fstar, CF_*`) of the E0b coarse 6-beat runs into `tests/fixtures/settling/`, with a
  README giving the source (`explore-surrogate-experiments` `b99c7b2` outputs, or the run CSV on
  the share) and the SHA-256. Check with `git ls-files` that the fixture is tracked. Test that it
  reproduces E0b's beat-to-previous table to `5e-5` with the mask, and gives `T_CF_z = 0.0118 ±
  1e-4` with the pre-registered rule.
- [ ] 1.3 Implement `resample_beats`, `settling_metrics`, `jitter`, `training_wingbeat`.

### 2. Decision rule
- [ ] 2.1 Tests first: one test per scenario of "Pre-registered settled-beat decision rule", plus:
  - `pass(N)` needs every `N′ ≥ N`;
  - a run with `B = 7` because its last beat is incomplete;
  - jitter above the floor gives `stop`;
  - the result names run, beat and target.
- [ ] 2.2 Implement `decide_beat_count`.

### 3. Pre-registration (written before the pinning test)
- [ ] 3.1 Write `examples/settling_check/PREREGISTRATION.md`. It holds the rule, the rationale for
  the tail bound, the three configurations and why they were chosen, the controls, the outcome
  table, the domain caveat, and the constants in a fenced block between
  `<!-- settling-constants:start -->` and `<!-- settling-constants:end -->`.
- [ ] 3.2 Tests first: the constants block parses and equals `settling.py`.
  - A missing anchor raises.
  - A mutated copy of the file, with a different tolerance, fails.
  - Mutating `SETTLED_TOLERANCE` in a monkeypatched module fails.

### 4. Stage 1 decks (`examples/settling_check/`)
- [ ] 4.1 Tests first (`tests/test_settling_decks.py`):
  - The differing key set **equals** the declared set per grid.
  - `max_step` and `stop_time` equal `derive_run_duration(f*, 8)`: 18824, 16000 and 13913.
  - `plot_per`/`check_per` equal `1/(20 f*)` and `1/f*`.
  - The coarse decks have `ns.init_iter = 2`.
  - `ns.cfl`, `ns.fixed_dt` and the grid equal the source.
  - The manifest carries both decks' SHA-256 and the controls declared per run (C1/C2 for fine
    `s55_f115_p30`; C3/C4 for every run).
  - Regeneration is byte-identical.
  - The C1 and C2 decks (the unmodified corpus deck with `max_step` 400; 1000 then
    `amr.restart = chk01000` with `max_step` 2000) are generated with their own declared key sets
    and tested the same way.
- [ ] 4.2 Implement `generate_decks.py`; commit decks and `settling_manifest.json`.
- [ ] 4.3 `.gitignore`: add `examples/settling_check/**/runs/`. Test with `git check-ignore` that
  a run directory is ignored and that `dataset.parquet`, the decks, the manifest, the run records
  and the figure are not.

### 5. Controls and report
- [ ] 5.1 Tests first for `compare_force_csv`:
  - byte-identical rows pass;
  - one changed digit fails and names the column and `iStep`;
  - a duplicate or missing `iStep` (the restart append case) fails;
  - coarse mode reports per-target RMS without a verdict.
- [ ] 5.2 Tests first for `field_change_stats`:
  - identical arrays give 0;
  - an offset of `0.12 · u_ref` gives median 0.12 and fraction 1;
  - an offset of `0.08 · u_ref` gives fraction 0;
  - a shape mismatch or non-finite input raises.
- [ ] 5.3 Tests first for `scripts/check_settling.py` on a synthetic run tree:
  - every report field in "A settling report records its controls and its inputs";
  - `controls_incomplete` and a non-zero exit when a declared control is missing;
  - run-record completeness: image digest equal to the pinned one, IAMReX label equal to
    `docker/build-args.env`, command, hardware, seconds per step, start SHA, three file hashes.
- [ ] 5.4 Implement 5.1–5.3.
- [ ] 5.5 Tests first, then `scripts/make_settling_figure.py`. The figure is the step change per
  beat on a log axis, one panel per target, six runs, with the tolerance and floor lines, in the
  project's figure-sidecar convention. Test that the sidecar's numbers equal the report's.
- [ ] 5.6 `examples/settling_check/README.md`: commands, file map, the controls each run needs,
  the data location on the share. It links to `PREREGISTRATION.md` and does not restate it.

### 6. Docs, CI and PR 1
- [ ] 6.1 `.github/workflows/ci.yml`: add `examples/settling_check/` to the ruff paths.
- [ ] 6.2 Short top-of-file entry in `docs/CHANGELOG.md`. In `openspec/project.md`: add
  `settling_check/` to the directory tree, and add one Verification Principle ("pre-register a
  criterion before the data that judge it exist").
- [ ] 6.3 `/review-pr`, a focused re-review of each fix commit, then `/pre-merge-check` (no Copilot
  review). **HUMAN GATE: approval before pushing.**

## Stage 1 runs on gh-04 (after PR 1 is merged)

- [ ] 7.1 Prepare (read-only):
  - On gh-04, `git fetch`, check out the `main` SHA, and verify it is an ancestor of `origin/main`
    with a clean tree.
  - Verify the image digest and its IAMReX label.
  - Check free disk and that the GPU is idle.
  - Copy the committed cluster force CSV of fine `s55_f115_p30` from the share and record its
    SHA-256.
- [ ] 7.2 **HUMAN GATE: go-ahead for the controls.** Run C1 (400 steps) and C2 (1000, restart, to
  2000). Record the results and seconds per step.
- [ ] 7.3 Report C1/C2 and the projected wall time for the six runs. Stop if C1 fails.
- [ ] 7.4 **HUMAN GATE: go-ahead for the long runs.**
  - Fine `s35_f085_p30`, `s45_f100_p30`, `s55_f115_p30`, then the three coarse runs, 8 beats
    each, one at a time.
  - After each run: extract, run C3 and C4, write the record, and copy the run to the share
    (`scp` from gh-04, then verify the file count and CSV hash).
  - Stop on any failed control.

## PR 2 — regeneration tooling (fresh branch `add-settled-beat-corpus-tooling`; may be written while 7.x runs)

Each group below adds its Stage 2 requirements from `stage2-spec-draft.md` to the delta (full text
for the MODIFIED ones) in the same commit as its code.

### 8. Generator and drivers
- [ ] 8.1 Tests first: the field-capture scenarios in the draft, including the crossing-rule phase
  check at `f* = 0.85` over 8 beats. Non-positive arguments raise.
- [ ] 8.2 Implement 8.1 in `sweep.py`.
- [ ] 8.3 Tests first:
  - Both drivers take `--n-wingbeats`, `--frames-per-beat` and `--checkpoints-per-beat`.
  - Each refuses a directory whose manifest has a different `n_wingbeats`, with an unchanged tree
    hash.
  - A manifest without `n_wingbeats` raises.
  - Omitting the flags reproduces the 2-beat corpora.
  - The regeneration tests read `n_wingbeats` and the field-capture settings from each corpus's
    own manifest.
- [ ] 8.4 Implement 8.3.

### 9. Supersession writer (#103)
- [ ] 9.1 Tests first: the draft's scenarios, plus a file that is not written on error.
- [ ] 9.2 Implement it with a CLI; a test that the runbook calls the CLI instead of describing a
  hand edit.

### 10. Guards, gate, trainer refusal (split into three commits)
- [ ] 10.1 Final-beat symmetry ratio. Tests first:
  - bit-identical ratios on both 2-beat corpora;
  - a synthetic 6-beat run truncated at 95% fails the new ratio, while the old ratio stays inside
    0.012;
  - `test_live_spec_claims.py:748`'s call and pinned maximum are updated to the manifest-aware
    signature;
  - `test_acceptance_gate.py`'s fixture manifest gains `n_wingbeats`, and its CSVs end at the
    requested beat, so `test_healthy_corpus_passes` and the just-under/over tolerance tests keep
    their meaning;
  - `test_corpus_guards.py`'s synthetic manifests gain `n_wingbeats`;
  - a manifest without it raises.
- [ ] 10.2 Settling acceptance. Tests first: the draft's scenarios. `not_applicable` comes from
  the manifest. `cluster_run.settling` is written. `plot_per > 0` triggers CC-F1. The mid-sweep
  check command runs the same function on a partial run tree.
- [ ] 10.3 Trainer refusal. Tests first: a 6-beat synthetic dataset raises, naming the follow-up
  issue. Both committed corpora still train (existing tests unchanged).

### 11. Storage manifest
- [ ] 11.1 Tests first: the draft's scenarios on a fake run tree.
- [ ] 11.2 Implement `storage_manifest.py` and `scripts/write_storage_manifest.py`.

### 12. Cluster sizing (#101; split into a shell/workflow commit and a docs commit)
- [ ] 12.1 Tests first:
  - The step-based deadline: 50400 s and 25200 s on toy manifests with `cluster_sizing.json`.
  - Doubling every `max_step` raises the deadline.
  - It is always computed without `--active-deadline-seconds`; a missing `cluster_sizing.json` or
    zero configs is an error.
  - A test recomputes the fine rates (2.321 step-weighted, 3.302) from the 27 committed run
    metadata files.
  - Smoke `max-step` comes from the manifest, and a disagreeing environment value is an error.
  - `maxDuration` covers `limit + 1` attempts.

  Deliberately changed existing tests:
  - `test_submit_workflow_active_deadline.py` 227–255 (fixtures gain `max_step`; 43200 → 50400),
    258–275 (14400 → error) and 278–297 (18000 → 25200);
  - `test_submit_workflow_smoke_guards.py` 85–124 (fixtures gain a manifest);
  - `test_argo_workflows.py` 59, 149, 160–186 ("committed ≥ formula" replaced by "always
    patched").
- [ ] 12.2 Implement in `submit_workflow.sh` and the workflow files. Run `argo lint --offline`
  locally on the rendered workflow; if `backoff.maxDuration` cannot be templated, commit `"105h"`
  with its test and record why in `design.md`.
- [ ] 12.3 Docs, with text-guard tests that the stale values are gone:
  - `.claude/commands/submit-cluster-sweep.md`: the corpus list, CC-F1 for coarse, step-based
    numbers, the settling and storage steps, the supersession CLI, the 86400/24 h references at
    247–249 and 363;
  - `cluster/argo/README.md` 78, 89 and 132–137;
  - `submit_workflow.sh:20`.
- [ ] 12.4 `.gitignore`: `examples/settled_sweep*/runs/`, with `check-ignore` tests.
- [ ] 12.5 `/review-pr`, re-review of fix commits, `/pre-merge-check`. **HUMAN GATE before
  pushing.**

## PR 3 — Stage 1 results, decision, corpus decks (fresh branch `add-settled-beat-corpus-results`)

- [ ] 13.1 Commit the Stage 1 datasets, run records, `settling_report.json`, the figure and
  `DECISION.md` (the rule applied, `N*`, the domain caveat with the mean-lift drift).
  - Tests: `DECISION.md`'s `N` equals `decide_beat_count` recomputed from the committed datasets.
  - The report recomputes to `rel = 1e-12`.
  - The precedence test from the spec passes.
  - The coarse `s45_f100_p30` step changes for beats 2–6 fall within the ranges E0b measured on
    the same configuration (external reference).
- [ ] 13.2 **HUMAN GATE: the user confirms N** (and the cost, if `regenerate_needs_cost_approval`).
  If the action is `stop`, report and end here (archive per D1).
- [ ] 13.3 Record the chosen N in `proposal.md`, `design.md` and here. Record any deviation in a
  `### Why … instead of …?` section and in `deviations.json`.
- [ ] 13.4 Generate `examples/settled_sweep` and `examples/settled_sweep_fine` with N, 20 frames
  and 1 checkpoint per beat, and coarse `ns.init_iter = 2`. Commit the decks, manifests,
  provenance (supersession entry via the CLI) and the fine `cluster_sizing.json`.
  - Register both corpora with `has_parquet=False` and coarse `has_per_config_metadata=True` in
    the same commit.
  - Tests: byte-identical regeneration; the deck guards; the CFL, `prescribed_vel` and `num_steps`
    lints.
- [ ] 13.5 `/review-pr`, re-review of fix commits, `/pre-merge-check`. **HUMAN GATE before
  pushing.**

## Cluster runs (after PR 3 is merged)

- [ ] 14.1 `/submit-cluster-sweep` steps 0–1 for each corpus: digest, wing-phase diagnostic,
  quota. Provision the new share directories (decks, `wing.vertex`, manifest) and produce a
  listing as evidence. Record free space on `Z:`.
- [ ] 14.2 **HUMAN GATE: coarse smoke** (full-length `s55_f115_p30`). Measure seconds per step and
  plotfile/checkpoint sizes, write the coarse `cluster_sizing.json`, run CC-F1, and run the
  one-config gate with settling.
- [ ] 14.3 **HUMAN GATE: coarse full sweep.** Mid-sweep settling check on each completed config.
- [ ] 14.4 **HUMAN GATE: fine smoke**, then **HUMAN GATE: fine full sweep**, with the same checks.
- [ ] 14.5 Post-run: the acceptance gate with settling on all 27 configs per corpus, per-config run
  metadata and storage manifests. On any failure, stop and report.

## PR 4 — the corpora (fresh branch `add-settled-beat-corpus-data`)

- [ ] 15.1 In one commit:
  - extract both datasets and commit the parquet, units, run metadata, provenance (including
    `cluster_run.settling`) and the storage manifests;
  - flip `has_parquet=True`;
  - update `test_corpus_guards.py:524-531`'s expected peaks and the healthy symmetry maximum
    (recomputed by a test).
  If the healthy maximum is above 0.012, stop; do not re-tune.
- [ ] 15.2 Corpus READMEs: what each corpus is, how it differs from the 2-beat corpus, where the
  raw runs live, the backup status, how to regenerate, and the domain caveat. Also update
  `openspec/project.md` (directory tree, Cluster Path Mappings with the `Z:` raw-run paths), row 19
  of `docs/force_surrogate/roadmap.md`, and `docs/field_surrogate/roadmap.md` (the storage note
  labelled "2-beat corpus", plus the fine settling result).
- [ ] 15.3 After bench PR 2 has merged: add "superseded by" notes to both 2-beat corpus READMEs,
  qualifying "the converged beat" as the 2-beat corpus's beat 2.
- [ ] 15.4 File the D10 issues that do not exist yet, and the resume-on-retry follow-up if C2
  passed. Tick #197.
- [ ] 15.5 Reconcile `proposal.md`, `design.md` and the delta with what was built. Then
  `/review-pr`, re-review of fix commits, `/pre-merge-check`. **HUMAN GATE before pushing.**
- [ ] 15.6 After the merge: archive the change with the openspec CLI.
