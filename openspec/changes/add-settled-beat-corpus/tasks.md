# Tasks: add-settled-beat-corpus

> **Archive after PR 4 merges.** If Stage 1 ends in `stop`, the PR 2 branch is closed unmerged and
> the change is archived after PR 3 with the Stage 1 delta only (`design.md` D1).

Rules:
- Tests come first: each is written and seen to fail for the right reason before the code.
- Every new guard is shown to be failable: mutate it, and the test must fail.
- One commit per numbered task unless noted. A tests-first task is committed **together with**
  its implementation task (e.g. 1.1 + 1.2 + 1.3, 2.1 + 2.2), so every commit is green.
- Commit messages say `advances #192` (plus `#101`/`#103` where relevant) and never use a closing
  keyword.
- Before each commit: `uv run --frozen ruff check`, `ruff format --check` and
  `uv run --frozen pytest -m "not gpu"`, from Git Bash.
- PR 1 uses the existing branch. PRs 2–4 each get a fresh branch from `origin/main`.
- Merge `main` in, never rebase. Run `git merge-base --is-ancestor origin/main HEAD` and
  `openspec validate add-settled-beat-corpus --strict` before every push.
- **HUMAN GATE** means the user's explicit go-ahead.

## PR 1 — settling metric, pre-registration, Stage 1 decks (branch `add-settled-beat-corpus`)

### 1. Metric (`force_surrogate/settling.py`)
- [x] 1.1 Tests first (`tests/test_settling.py`):
  - one test per scenario of "Beat-to-beat settling metric";
  - boundaries:
    - exactly 95% of rows counts as complete;
    - `ρ` exactly 1 is not contracting;
    - a step exactly at `ν` counts as noise;
    - `B = 5` uses two ratios and `B = 6` uses three;
  - at `f*` 0.85 and 1.15, per-beat row counts built as `step · dt` alternate (for example
    2352/2353) and sum to `max_step` minus the clamped rows (one at `f085`);
  - a tiny but nonzero peak (`1e-6`) is accepted;
  - `wingbeat` and `phase` are used as given; a frame with a deliberately inconsistent `wingbeat`
    is not "corrected";
  - `dt` and `stop_time` are required arguments;
  - a clamped final row (`time + dt > stop_time + 1e-9`) carrying a `0.1 · P` spike is dropped, and
    the result equals the run without it;
  - `ν` exactly at `MAX_NOISE` is accepted, and just above it is reported for `stop`;
  - the maximum absolute difference is reported beside every RMS value;
  - every `ValueError` path names the configuration and the cause.
- [x] 1.2 Known-answer fixtures:
  - Copy the needed columns of `explore-surrogate-experiments` `b99c7b2`
    `experiments/e0b_long_run/outputs/long_run.parquet` (blob `f232bca`, `s45_f100_p45`) and
    `outputs_s45_f100_p30_fields/long_run.parquet` (blob `ef8f74a`) into
    `tests/fixtures/settling/`.
  - Add a README with the source, the blobs, the SHA-256, and the note that the source run records
    say `git_dirty: true`. Check that the files are tracked with `git ls-files`.
  - Tests:
    - E0b's 256-point resampling, with the `phase ≥ 0.05` mask on the differences and the peak over
      all 256 points, reproduces E0b's beat-to-previous tables to `5e-5`;
    - the pre-registered rule gives `s45_f100_p30` CF_my `T = 0.01245 ± 1e-4` (the binding
      target; CF_z `0.01168 ± 1e-4`) and `s45_f100_p45` CF_my `T = 0.01007 ± 1e-4`, with no
      settled beat in either;
    - with clamped rows dropped, `J ≤ 6.5e-5` on the final beat of every configuration of both
      committed corpora;
    - an exactly periodic 8-beat signal built by periodic linear interpolation of each committed
      `f085`/`f115` final beat, on the true step grid, gives `s_b ≤ ν` and `ν ≤ MAX_NOISE` for
      every target.
- [x] 1.3 Implement `resample_beats` (figures and the E0b reproduction only), `settling_metrics`
  and `jitter`.

### 2. Decision rule
- [x] 2.1 Tests first:
  - one test per scenario of "Pre-registered settled-beat decision rule";
  - `pass(N)` needs every `N′ ≥ N`;
  - `B = 7` because the last beat is incomplete;
  - the result names the run, beat and target; on the two E0b fixtures (`B = 6`) the action is
    `stop`, and `s45_f100_p30`'s failure is reported on CF_my.
- [x] 2.2 Implement `decide_beat_count`.

### 3. Pre-registration and precedence
- [x] 3.1 Write `examples/settling_check/PREREGISTRATION.md`, the single narrative home of the
  criterion. It covers:
  - the rule and its rationale (tail bound, rising-ratio term, noise floor from `J`, why sample
    resolution);
  - the three configurations and why they were chosen;
  - the controls, the coverage rule and the tolerance
    `max(1e-9 · max |column|, 1.5 units in the 6th significant figure)`;
  - the outcome table;
  - the domain caveat (#204);
  - the scope statement that the criterion predates the fine-grid and 8-beat data only;
  - the near-wing box;
  - the constants block between `<!-- settling-constants:start -->` and
    `<!-- settling-constants:end -->`.
- [x] 3.2 Tests first, then the pinning helper:
  - the block parses and equals `settling.py`;
  - a missing anchor raises;
  - a mutated copy of the file fails;
  - a monkeypatched constant fails;
  - the constants sentence in the change's delta, or in the live spec after archive (path
    resolved), carries the same values.
- [x] 3.3 Tests first, then the precedence checker (`settling.check_precedence`), on synthetic
  trees:
  - unchanged files pass;
  - an edit with no `deviations.json` entry fails;
  - an edit with a matching entry passes;
  - a `DECISION.md` with zero or too few run records fails;
  - a `settling_report.json` with zero run records (and no `DECISION.md`) fails.
  - The repository test runs it on `examples/settling_check/`. It passes trivially in PR 1, where
    no records or decision exist yet, and becomes binding in PR 3.

### 4. Stage 1 decks (`examples/settling_check/`)
- [x] 4.1 Tests first (`tests/test_settling_decks.py`):
  - the differing key set equals the declared set;
  - a deck missing `amrex.the_arena_init_size`, and one with a changed `ns.cfl`, each fail by name;
  - `max_step` is 18824 / 16000 / 13913, and `stop_time` equals `derive_run_duration`'s;
  - `plot_per = 1/(20 f*)` and `check_per = 1/f*`;
  - `ns.init_iter`, `ns.cfl`, `ns.fixed_dt` and the grid equal the source deck's;
  - the manifest carries both decks' SHA-256 and the controls declared per run (C1 for
    `s55_f115_p30` on each grid; C3 and C4 for every run), and pins each grid's image digest;
  - the C1 decks are the corpus deck plus `max_step = 400` and the arena key, with their own
    declared set;
  - regeneration is byte-identical.
- [x] 4.2 Implement `generate_decks.py` (using `metadata_capture.parse_deck`), and commit the
  decks and `settling_manifest.json`. The manifest's per-run entries carry the fields
  `scripts/extract_forces.py` needs (name, input file, kinematics, `max_step`, `stop_time`), so the
  Stage 1 `dataset.parquet` is built by the existing extractor, not new code.
- [x] 4.3 `.gitignore`: add `examples/settling_check/**/runs/`. `git check-ignore` tests: a run
  directory is ignored; `dataset.parquet`, the decks, the manifest, `records/*.json` and the figure
  are not.

### 5. Controls and report (one commit each)
- [x] 5.1 Tests first, then `settling.compare_force_csv(run_csv, reference, *, config_name, dt,
  run_stop_time, reference_stop_time, declared_steps)`. The reference is the configuration's
  rows of the committed `dataset.parquet`, matched by step index after the extractor's
  de-duplication. Tests:
  - identical values pass;
  - a `5e-13` round-off perturbation passes, and so does a flip of the last printed digit
    (including `1.00000` against `0.999999`);
  - a run stopping 20 steps short of its declared step count fails, naming the first missing step;
  - a `1e-4 · max` perturbation near the peak fails, naming the column and `time`;
  - the two `init_iter = 2` duplicate `iStep == 0` rows pass, and a duplicate or missing step
    anywhere else fails;
  - the reference's clamped final row is excluded (C3 at `f085`).
- [x] 5.2 Tests first, then `settling.field_change_stats`:
  - identical arrays give 0;
  - a `0.12 · u_ref` offset gives median 0.12 and fraction 1;
  - a `0.08 · u_ref` offset gives fraction 0 (strict `>`, vector difference norm);
  - a shape mismatch or non-finite input raises.
- [x] 5.3 Tests first, then `scripts/check_settling.py`, on a synthetic run tree:
  - every report field of "A settling report records its controls and its inputs";
  - `controls_incomplete` and a non-zero exit when a declared control is missing;
    `control_failed` when a record is invalid or a control failed; `precedence_failed`;
    `data_incomplete` when a run has no rows, too few beats, or the wrong CSV;
  - run-record completeness: image digest equal to the manifest's pin, IAMReX label, command,
    hardware, seconds per step, git-derived provenance (see 6.4), and the gated file hashes;
  - the record writer `scripts/record_settling_run.py` (`settling.build_run_record`, checked by
    `settling.validate_run_record`) produces a
    complete record from a synthetic run directory; C4 uses `metadata_capture`'s realized-timestep
    summary with clamped steps excluded;
  - field-change values are copied into the report with the SHA-256 of the plotfile headers they
    came from; the CI recompute covers force-derived numbers only.
  - The schemas for `settling_manifest.json`, `records/*.json` and `settling_report.json` are
    defined in this task as JSON-schema-like tables in `examples/settling_check/README.md`, and
    the tests check them.
- [x] 5.4 Tests first (the sidecar numbers equal the report's), then
  `scripts/make_settling_figure.py`: step change per beat on a log axis, one panel per target, six
  runs, with the tolerance line (the per-run, per-coefficient noise floors are in the metrics
  sidecar, not drawn: 36 lines would hide the data), following the project's figure-sidecar
  convention.
- [x] 5.5 Finish `examples/settling_check/README.md`: commands, file map, controls per run, the
  data location on the share. It links to `PREREGISTRATION.md` without restating it.

### 6. Docs, CI and PR 1
- [x] 6.1 Add `examples/settling_check/` to the ruff paths in `.github/workflows/ci.yml` and in
  `openspec/project.md:212`.
- [x] 6.2 Add a short top-of-file entry in `docs/CHANGELOG.md`. In `openspec/project.md`: add
  `settling_check/` to the directory tree, and one Verification Principle ("pre-register a
  criterion before the data that judge it exist, and say which data it predates").
- [ ] 6.3 `/review-pr`, a focused re-review of each fix commit, then `/pre-merge-check` (no
  Copilot review). **HUMAN GATE: approval before pushing.**
- [x] 6.4 PR-review fixes (tests first, in `tests/test_settling_hardening.py`), each reproduced
  before it was fixed:
  - a NaN/inf force now fails C1/C3, and a missing column is a failure, not a crash;
  - the precedence check compares the set of records with runs **and** controls, and reports
    malformed JSON by name;
  - a run must reach its deck's `max_step` (C1 included), and the report requires the declared
    beats;
  - provenance is derived from git (`record_settling_run.py launch` / `record`), not typed in;
  - the report validates every record, accepts only boolean `true` as a pass, and requires each
    dataset to come from the CSV its record hashes;
  - `settling.py` is gated, and the decision, tolerance and threshold numbers are pre-registered
    (12 constants);
  - the decision's beat and target describe the same beat, and a NaN noise floor stops;
  - integer `wingbeat` and the first beat's completeness are checked;
  - orphan decks are flagged; the `.gitignore` tests fail on a git error;
  - the `project.md` arena unit is corrected to bytes.
- [x] 6.5 Fixes from the focused re-review of 6.4 (tests first, second section of
  `tests/test_settling_hardening.py`):
  - a NaN noise floor in any coefficient stops (`noisiest_target`);
  - only new, untracked records are exempt from the dirty check;
  - the upstream must be `origin/main` and must exist ("fetch origin");
  - `launch` refuses a dirty or off-`main` checkout before a run starts;
  - the IAMReX label comes only from `docker image inspect`;
  - raw-file hashes and the field-change shape are validated, and the CSV link fails closed;
  - an infinite reference value fails, and a short or malformed run is `data_incomplete`;
  - a missing docker or `hardware.json` is a clean refusal.
- [x] 6.6 Fixes from the third focused re-review (tests first, third section of
  `tests/test_settling_hardening.py`):
  - a launch state without its git status is not a clean launch;
  - `launch` refuses a run directory inside the checkout that git does not ignore;
  - only new `*.json` files directly in `records/` are exempt from the dirty check;
  - skip-worktree and assume-unchanged files count as dirty;
  - the report turns only `SettlingDataError` into `data_incomplete`, so a bug still raises;
  - a NaN value labels the binding target.

## Stage 1 runs on gh-04 (after PR 1 is merged)

- [ ] 7.1 Prepare (read-only):
  - check out the merged `main` SHA on gh-04 and verify it is an ancestor of `origin/main`, with a
    clean tree;
  - pull both images by digest and record their IAMReX labels;
  - check free disk and that the GPU is idle;
  - nothing to copy: the control references are the committed `dataset.parquet` rows.
- [ ] 7.2 **HUMAN GATE: go-ahead for the controls.** Run C1 on both grids. Record the results and
  seconds per step.
- [ ] 7.3 Report C1 and the projected wall time for the six runs. Stop if C1 fails.
- [ ] 7.4 **HUMAN GATE: go-ahead for the long runs.**
  - Run fine `s35_f085_p30`, `s45_f100_p30`, `s55_f115_p30`, then the three coarse runs, 8 beats
    each, one at a time.
  - Before each run: `scripts/record_settling_run.py launch --run-dir <dir>`. After it:
    `record --name <run> --run-dir <dir>` (`--field-change` for fine runs), which runs C3 and C4.
    Then `scp` to the share (layout `<grid>/<config>`), verify the file count and CSV hash, and
    extract.
  - Stop on any failed control.

## PR 2 — regeneration tooling (branch `add-settled-beat-corpus-tooling`; written while 7.x runs, **merged only after 13.2 says `regenerate`**)

Each group adds its entries from `stage2-spec-draft.md` to the delta (full text for the MODIFIED
ones) in the same commit as its code.

### 8. Generator and drivers
- [ ] 8.1 Tests first: the field-capture scenarios in the draft, including the crossing-rule phase
  check at `f* = 0.85` over 8 beats. Also:
  - the provenance rationale no longer says no output is produced;
  - non-positive arguments raise.
- [ ] 8.2 Implement 8.1 in `sweep.py`.
- [ ] 8.3 Tests first:
  - both drivers take `--n-wingbeats`, `--frames-per-beat` and `--checkpoints-per-beat`;
  - N = 6 gives 14118 / 12000 / 10435;
  - a write into a directory whose manifest has a different `n_wingbeats` is refused, with an
    unchanged tree hash;
  - a manifest without `n_wingbeats` raises;
  - omitting the flags reproduces the 2-beat corpora;
  - the regeneration tests read their settings from each corpus's own manifest.
- [ ] 8.4 Implement 8.3.

### 9. Supersession writer (#103)
- [ ] 9.1 Tests first: the draft's scenarios, and that the file is not written on error.
- [ ] 9.2 Implement the writer with a CLI. Add a text-guard test that the runbook calls the CLI.

### 10. Guards, gate, trainer refusal (three commits)
- [ ] 10.1 `settling.training_wingbeat` and the final-beat symmetry ratio. Tests first:
  - `training_wingbeat` returns 5 for a 6-beat manifest;
  - on both 2-beat corpora, `wingbeat == training_wingbeat` selects exactly the rows
    `wingbeat >= 1` selects;
  - ratios are bit-identical on both 2-beat corpora;
  - a synthetic 6-beat run truncated at 95% fails the new ratio while the old one stays inside
    0.012;
  - a manifest without `n_wingbeats` raises.

  Deliberately changed existing tests:
  - `test_live_spec_claims.py:748` (signature and pinned maximum);
  - `test_acceptance_gate.py:99-113`, `162`, `235`, `250` (the fixture manifest gains
    `n_wingbeats` and its CSVs end at the requested beat);
  - `test_corpus_guards.py:114` (synthetic manifests gain `n_wingbeats`).
- [ ] 10.2 Settling acceptance. Tests first: the draft's scenarios, plus:
  - `not_applicable` comes from the manifest;
  - `cluster_run.settling` is written;
  - `frames_per_beat > 0` triggers CC-F1, and so does `plot_int > 0` (the 2-beat fine corpus);
  - the mid-sweep check command runs the same function on a partial run tree.
- [ ] 10.3 Trainer refusal. Tests first:
  - a 6-beat synthetic frame is refused by `filter_converged_beat` and by
    `build_phase_only_baseline`, naming the follow-up issue;
  - both committed corpora still train (existing tests unchanged).

### 11. Storage manifest
- [ ] 11.1 Tests first: the draft's scenarios on a fake run tree, with the crossing rule on step
  end times.
- [ ] 11.2 Implement `storage_manifest.py` and `scripts/write_storage_manifest.py`.

### 12. Cluster sizing (#101; a shell/workflow commit and a docs commit)
- [ ] 12.1 Tests first:
  - the step-based deadline gives 50400 s and 25200 s on toy manifests with
    `cluster_sizing.json`;
  - doubling every `max_step` raises the deadline;
  - the deadline is always computed when `--active-deadline-seconds` is not given;
  - a missing `cluster_sizing.json`, and zero configs, are errors;
  - `prelim_sweep` without an explicit deadline fails;
  - `cluster_sizing.json` recomputes from its `source`;
  - smoke `max-step` comes from the manifest, and a disagreeing environment value is an error;
  - the committed `maxDuration: "120h"` covers every committed manifest that has a
    `cluster_sizing.json`.

  Deliberately changed existing tests:
  - `test_submit_workflow_active_deadline.py`:
    - 227–255: fixtures gain `max_step` and `cluster_sizing.json`; 43200 → 50400;
    - 258–275: 14400 → error;
    - 278–297: 18000 → 25200;
  - `test_submit_workflow_smoke_guards.py:85-124`: fixtures gain a manifest;
  - `test_submit_workflow_parallelism.py:96-119`: `test_omitting_parallelism_is_a_true_noop` is
    reversed, and the fixture corpus gains `cluster_sizing.json`;
  - `test_submit_workflow_provision.py:116, 147, 324, 353, 529`: `_make_corpus` writes configs with
    `max_step` and a `cluster_sizing.json`, and each "argo not invoked" test asserts its specific
    stderr;
  - `test_argo_workflows.py:59, 149, 160-186`: `"20h"` → `"120h"`; "committed ≥ formula" becomes
    "always patched".
- [ ] 12.2 Implement in `submit_workflow.sh`, the workflow files and the WorkflowTemplate. Commit
  `examples/prelim_sweep_fine/cluster_sizing.json`.
- [ ] 12.3 Docs, with text-guard tests that the stale values are gone:
  - `.claude/commands/submit-cluster-sweep.md` lines 41–57 (corpus list, coarse field capture and
    CC-F1) and 247–249 and 363 (24 h); also the step-based numbers, the settling and storage steps,
    and the supersession CLI;
  - `cluster/argo/README.md` lines 78, 89, 132–139;
  - `submit_workflow.sh` lines 20, 84, 95, 333;
  - `force-surrogate-smoke.yaml:37`.
- [ ] 12.4 `.gitignore`: add `examples/settled_sweep*/runs/`, with `check-ignore` tests.
- [ ] 12.5 `/review-pr`, re-review of fix commits, `/pre-merge-check`. Then **HUMAN GATE before
  pushing**; the merge waits for 13.2.

## PR 3 — Stage 1 results, decision, corpus decks (branch `add-settled-beat-corpus-results`)

- [ ] 13.1 Commit the Stage 1 datasets, `records/`, `settling_report.json`, the figure and
  `DECISION.md`. `DECISION.md` covers:
  - the rule applied and `N*`;
  - the jitter values;
  - the field change;
  - the mean-lift drift and the domain caveat;
  - the D10 downstream list.

  Data and tests go in one commit. The tests:
  - `DECISION.md`'s count equals `decide_beat_count` recomputed from the committed datasets;
  - the force-derived numbers of the report recompute to `rel = 1e-12` (field values are checked
    against their recorded plotfile hashes only);
  - the precedence check passes;
  - external reference: the coarse `s45_f100_p30` run's raw forces over beats 1–6 match the E0b
    fixture of the same configuration and image within the C1 comparison tolerance. If the
    comparison fails there, the difference is reported and the user decides.
- [ ] 13.2 **HUMAN GATE: the user confirms the outcome.**
  - On `regenerate` or `regenerate_needs_cost_approval`: confirm `N` and the cost, then merge PR 2.
  - On `stop`: report, close the PR 2 branch, merge PR 3 and archive (D1).
- [ ] 13.3 Record the chosen `N` in `proposal.md`, `design.md` and this file. Record any deviation
  in a `### Why … instead of …?` section and in `deviations.json`.
- [ ] 13.4 Generate `examples/settled_sweep` and `examples/settled_sweep_fine` with `N`, 20 frames
  and 1 checkpoint per beat. Commit:
  - the decks, the manifests and the fine `cluster_sizing.json`;
  - the provenance, with a supersession entry written by the CLI;
  - the registry entries (`has_parquet=False`; `has_per_config_metadata=True` for coarse).

  Tests:
  - regeneration is byte-identical;
  - the deck guards and the CFL, `prescribed_vel` and `num_steps` lints pass;
  - for the three settling configurations, each corpus deck equals its settling deck except
    `max_step`, `stop_time` and the arena key.
- [ ] 13.5 `/review-pr`, re-review of fix commits, `/pre-merge-check`. **HUMAN GATE before
  pushing.**

## Cluster runs (after PR 3 is merged)

- [ ] 14.1 Run `/submit-cluster-sweep` steps 0–1 for each corpus: digest pinned per grid (D4),
  wing-phase diagnostic, quota. Provision the share directories (decks, `wing.vertex`, manifest)
  and keep a listing as evidence. Record free space on `Z:`.
- [ ] 14.2 **HUMAN GATE: coarse smoke** (full-length `s55_f115_p30`). Then:
  - measure seconds per step and plotfile and checkpoint sizes;
  - write the coarse `cluster_sizing.json` (D9 factors) and land it on `main` in a small sizing
    PR (fresh branch; its test recomputes the file from the smoke metadata; **HUMAN GATE before
    pushing**);
  - run CC-F1 on one late plotfile (#206);
  - run the one-config gate with settling.
- [ ] 14.3 **HUMAN GATE: coarse full sweep**, with the mid-sweep settling check on each completed
  configuration.
- [ ] 14.4 **HUMAN GATE: fine smoke**: refresh the fine `s_max` (D9) in a sizing PR, bumping
  `maxDuration` if its test requires (**HUMAN GATE before pushing**). Then **HUMAN GATE: fine full
  sweep**, with the same checks.
- [ ] 14.5 Post-run: run the acceptance gate with settling on all 27 configurations of each
  corpus, and write the per-config run metadata and the storage manifests. On any failure, stop and
  report.

## PR 4 — the corpora (branch `add-settled-beat-corpus-data`)

- [ ] 15.1 One commit:
  - both datasets, units, run metadata, provenance (with `cluster_run.settling`) and storage
    manifests;
  - `has_parquet=True`;
  - `test_corpus_guards.py:524-531` expected peaks, and the healthy symmetry maximum recomputed by
    a test.

  If that maximum is above 0.012, stop; do not re-tune.
- [ ] 15.2 Write (backup decided 2026-11-23: one copy only, on `Z:`):
  - the corpus READMEs: what each corpus is, how it differs from the 2-beat corpus, the image per
    grid, where the raw runs live, the backup status, how to regenerate, the domain caveat, and
    the restart limitation (#205);
  - `openspec/project.md`: directory tree, and Cluster Path Mappings with the `Z:` raw-run paths;
  - `docs/force_surrogate/roadmap.md`: row 19, with the D10 list;
  - `docs/field_surrogate/roadmap.md`:
    - items 6 (line 213) and 7 (line 407, now answered);
    - line 395;
    - the storage note (lines 304–307), labelled as the 2-beat corpus;
    - the fine settling result.
- [ ] 15.3 After bench PR 2 has merged, add "superseded by" notes to both 2-beat corpus READMEs:
  - qualify "the converged beat" as the 2-beat corpus's beat 2;
  - qualify `examples/prelim_sweep_fine/README.md:327`'s "force-only defaults".
- [ ] 15.4 File the D10 issues that do not exist yet. Tick #197.
- [ ] 15.5 Reconcile `proposal.md`, `design.md` and the delta with what was built. Then
  `/review-pr`, re-review of fix commits and `/pre-merge-check`. **HUMAN GATE before pushing.**
- [ ] 15.6 After merge: archive the change with the openspec CLI.
