# Review reconciliation: add-settled-beat-corpus, round 1

Round 1 reviewed commit `840621f`. Five reviewers ran: spec quality (S), testing (T),
documentation (Doc), git workflow (G) and math/physics (M). The CI/build reviewer was skipped
because no CI workflow, Dockerfile, dependency or packaging file changes; the one-line ruff-path
edit to `ci.yml` was added later, in round 1.

Each entry has three parts:
- the finding, quoted verbatim or nearly so;
- how it was resolved;
- where it now lives, as `file › section › quoted line`.

## BLOCKING

**M1.** *"the Stage 1 criterion and the 54-run gate are not the same test, and the gate is
predictably stricter … define N\* = min N such that, for every Stage 1 run truncated at N,
`T_N(trunc) ≤ tol`, and also E_N(full run) ≤ tol."*
- **Resolution:** adopted verbatim as `pass(N)` (a) and (b). The gate applies test (a).
- **Where:**
  - `design.md › D3`: "(a) Truncated: the metric on the run's first `N` beats alone … This is
    exactly the test the regenerated corpus faces in D6"
  - `spec.md › Pre-registered settled-beat decision rule`: "(a) the metric computed on that run's
    first `N` beats alone is contracting with `T ≤ SETTLED_TOLERANCE`"
  - `stage2-spec-draft.md › ADDED 2`: "apply the decision rule's truncated test (a)"

**S-B1 / Doc-B3.** *"Any consumer that trains on, scores or plots the settled beat SHALL select
`wingbeat == training_wingbeat` … the spec would contradict itself."*
- **Resolution:** the requirement now binds only the guards and the gate. The trainer requirement
  is MODIFIED so that the trainer refuses multi-beat datasets until it is migrated.
- **Where:**
  - `stage2-spec-draft.md › ADDED 1`: "The corpus guards and the acceptance gate SHALL use it"
  - `stage2-spec-draft.md › MODIFIED › trainer`: "the trainer SHALL raise `ValueError` for a
    dataset whose maximum `wingbeat` exceeds 1"
  - `design.md › D6`

**S-B2 / T-B2 / Doc-B2.** *"A plain `submit_workflow.sh full` would therefore be deadline-killed
… Neither requirement is MODIFIED."*
- **Resolution:** `full` always computes the deadline. Both requirements are MODIFIED, and the
  change is marked BREAKING.
- **Where:**
  - `design.md › D9`: "`submit_workflow.sh full` always computes the deadline, unless
    `--active-deadline-seconds` is given"
  - `stage2-spec-draft.md › MODIFIED` (three entries)
  - `proposal.md › Impact › BREAKING`

**S-B3 / T-I4 / Doc-I (phase drift) / M (CONTRADICTED).** *"'every beat of every configuration
has plotfiles at the same 20 phases' … is false for f=0.85 and f=1.15 … use a frame stride that
lands on beat boundaries."*
- **Resolution:** time-triggered `amr.plot_per`/`check_per`. These exist in the pinned AMReX and
  do not alter `dt` (verified in the image, `AMReX_Amr.cpp:2360–2445`). Each frame is within one
  step of its phase, with no build-up. A test simulates the crossing rule at `f* = 0.85` over
  8 beats.
- **Where:**
  - `design.md › D7`: "`amr.plot_per = 1/(20·f*)`: 20 frames per beat, each within one step of
    phase `k/20`, with no build-up across beats"
  - `stage2-spec-draft.md › ADDED 3` (last scenario)
  - `tasks.md › 8.1`

**T-B1.** *"The deadline formula has no source for the mesh resolution … the manifest's `grid` key
holds the kinematic levels."*
- **Resolution:** the rates come from a per-corpus `cluster_sizing.json`, not from the grid. A
  missing file is an error.
- **Where:** `design.md › D9`: "Each new corpus directory carries `cluster_sizing.json`"

**T-B3.** *"The settling gate fails open … `not_applicable` is decided from the manifest's
`n_wingbeats < 3`, never from observed beats … `B ≠ n_wingbeats` fails."*
- **Resolution:** adopted as written, with `MIN_BEATS` = 5.
- **Where:**
  - `design.md › D6`: "It is `not_applicable` only when the manifest's `n_wingbeats < MIN_BEATS`,
    decided from the manifest, never from the observed beats. A run whose complete-beat count
    differs from `n_wingbeats` fails."
  - `stage2-spec-draft.md › ADDED 2` (second scenario)

**T-B4.** *"Existing tests that will break and are not mentioned"* (the deadline, smoke, Argo,
acceptance-gate, corpus-guard and live-spec-claims tests).
- **Resolution:** each test is listed by file and line in the task that changes it, as a
  deliberate change.
- **Where:** `tasks.md › 10.1` and `› 12.1` ("Deliberately changed existing tests"), and
  `› 15.1` (`test_corpus_guards.py:524-531`)

**G-B1.** *"The 'merge commit of PR 1' is not a usable citation … each run record stores the SHA,
… SHA-256 for `PREREGISTRATION.md`, `settling.py` and `generate_decks.py` … a committed
`deviations` list … do not use `git cat-file` in CI."*
- **Resolution:** adopted as written.
- **Where:**
  - `design.md › D3 › Precedence proof`
  - `spec.md › The settling criterion is pre-registered and its precedence is provable`: "a
    committed `deviations.json` entry (`old_sha256`, `new_sha256`, `reason`, `pr`) accounts for the
    change. No such test SHALL read git history."

**G-B2.** *"Keep ONE change but stage the delta. PR 1 carries only the Stage 1 ADDED
requirements."*
- **Resolution:** adopted. The Stage 2 text is in `stage2-spec-draft.md`, and PR 2 moves it into
  the delta alongside its code.
- **Where:** `design.md › D1`: "PR 1's spec delta carries only the Stage 1 requirements"

**G-B3.** *"`.gitignore` does not cover the new directories."*
- **Resolution:** the ignore rules land in PR 1 and PR 2, with positive and negative
  `git check-ignore` tests.
- **Where:** `tasks.md › 4.3` and `› 12.4`; `design.md › D8`

**Doc-B1.** *"There is no root `CHANGELOG.md`; the file is `docs/CHANGELOG.md`."*
- **Resolution:** fixed.
- **Where:** `tasks.md › 6.2`: "Short top-of-file entry in `docs/CHANGELOG.md`"

## IMPORTANT

**M2.** Noise floor and fallback. *"(a) Drop a ratio only when both numerator and denominator are
below the floor, else treat it as ρ ≥ 1 … (b) 'T = s_B' silently assumes ρ = 0.5 … (c) Add an
absolute settled floor … (d) Specify B ≥ 5, or exclude b ≤ 3 from ρ."*
- **Resolution:** all four are adopted.
  - (a) Growth from the floor counts as not contracting.
  - (b) The at-floor bound is `2·max s` (assumes ρ ≤ 2/3), stated in the report.
  - (c) The floor is 0.1·tolerance.
  - (d) `MIN_BEATS = 5` and `FIRST_RATIO_BEAT = 4`.
- **Where:** `design.md › D2` steps 6–7; `spec.md › Beat-to-beat settling metric` (the scenarios
  "Growth from the floor…" and "A run that has reached the floor…")

**M3.** *"Phase-grid jitter at f085/f115 … measure each run's self-jitter … and set the floor from
it."*
- **Resolution:** the floor (1e-3) is set above the measured jitter (1e-4 to 5e-4). Jitter `J` is
  computed per run; if `J > STEP_FLOOR`, the outcome is `stop`. A scenario covers an exactly
  periodic signal with a spike at off-integer steps per beat.
- **Where:** `design.md › D2` step 9; `spec.md` (the scenario "Off-integer steps per beat stay
  below the floor")

**M4.** *"Worst case not sampled … Replace s45_f100_p45 with s35_f085_p30."*
- **Resolution:** the user chose three worst-case configurations at 8 beats each.
- **Where:** `proposal.md › Stage 1` table

**M5.** *"Settling into a domain-dependent state (not discussed)."*
- **Resolution:** the user chose to record the caveat, measure mean-lift drift, and file an issue
  for a domain-size study.
- **Where:** `design.md › D11`; `spec.md › A settling report…` ("mean CF_z per beat")

**M6.** *"C3-coarse's `1e-6` is below one print step … set the threshold from physics."*
- **Resolution:** fine comparisons are byte-identical CSV rows. Coarse C3 is reported only,
  because the image and `init_iter` differ by design.
- **Where:** `design.md › D4` table, rows C1–C3

**M7.** *"C2 cannot be run with the allowed deck diff … Use 1000 + restart + 1000 … check that
the force CSV is appended … no duplicate rows."*
- **Resolution:** adopted. CSV append mode is verified in the source (`DiffusedIB*.cpp`).
- **Where:** `design.md › D4` row C2; `tasks.md › 4.1` and `› 5.1`

**M8.** *"The scenario '60% truncated last beat is missed by the old guard' is false … Change the
scenario to about 95%."*
- **Resolution:** changed to 95%.
- **Where:** `design.md › D6` ("truncated at 95%"); `tasks.md › 10.1`

**M (coarse headroom).** *"Coarse 'about 4× headroom': CONTRADICTED … 2.45×."*
- **Resolution:** the claim is removed. C4 now checks the realized timestep on the coarse runs
  too.
- **Where:** `design.md › D4` row C4 ("every long run")

**M (wall time).** *"'2.2–3.6 days' CONTRADICTED"* (Doc raised the same).
- **Resolution:** recomputed as 3.0 / 3.5 / 4.0 days at N = 6 / 7 / 8.
- **Where:** `proposal.md › Cost`

**M (step-weighted mean).** The formula multiplies Σmax_step by `s_mean`, so the step-weighted
mean (2.321) is the right one.
- **Resolution:** adopted.
- **Where:** `design.md › D9`: "2.321 (step-weighted)"

**M (Stage 1 disk).** *"'about 0.2 TB': CONTRADICTED … about 0.29 TB."*
- **Resolution:** recomputed as ≈0.31 TB for the 8-beat runs.
- **Where:** `proposal.md › Cost`

**T-I1.** Vacuous checks:
- **Pinning anchor:** an anchored constants block plus mutation tests. `tasks.md › 3.1–3.2`.
- **DECISION recompute:** an external E0b range check. `tasks.md › 13.1`.
- **Register behind existence:** dropped in favour of `has_parquet=False` in the same commit as
  the decks. `design.md › D5`.
- **Deck diff "subset" → "equal":** `spec.md › Settling-check decks…`: "SHALL equal the key set
  declared".

**T-I2.** The C1, C2 and extension decks are untested.
- **Resolution:** they are generated and tested, and no extension is needed because all runs are
  8 beats.
- **Where:** `tasks.md › 4.1`

**T-I3.** Coarse `ns.init_iter = 0` writes no velocity.
- **Resolution:** coarse runs, the Stage 1 runs included, use `ns.init_iter = 2`, so the result
  transfers.
- **Where:** `design.md › D4`; `proposal.md › Open for approval 2`

**T-I5 / T-I6.** Metric and decision edge cases.
- **Where:** `tasks.md › 1.1` and `› 2.1` (boundaries, B = 5/6, row-count alternation, tiny peak,
  no recompute, B = 7)

**T-I7.** Run-record completeness, and which controls apply to which run.
- **Where:** `tasks.md › 5.3`; per-run declared controls in `› 4.1`

**T-I8.** The coarse rate is never committed.
- **Resolution:** a coarse `cluster_sizing.json` is written from the smoke run.
- **Where:** `tasks.md › 14.2`

**T-I9.** Supersession fields.
- **Resolution:** required fields are `superseded`, `reason` and `pr`; the file is not written on
  error.
- **Where:** `stage2-spec-draft.md › ADDED 5`

**T-I10.** CI feasibility.
- **Resolution:** ruff paths in `tasks.md › 6.1`; `argo lint --offline` run locally in
  `› 12.2`; the 2-beat gate scenario rewritten as synthetic (`stage2-spec-draft.md › ADDED 2`);
  the field statistic is the vector norm with strict `>` and values off the boundary
  (`tasks.md › 5.2`).

**S-I1.** Guard and gate requirements overlap without a MODIFIED delta.
- **Resolution:** both are now MODIFIED.
- **Where:** `stage2-spec-draft.md › MODIFIED` ("Post-run acceptance gate", "Committed corpora
  are guarded…")

**S-I2 / G-I3.** Registry glob, coarse `has_per_config_metadata`, CC-F1 on coarse.
- **Where:** `design.md › D5` and `› D6`; `tasks.md › 13.4`

**S-I3.** Smoke max-step has no requirement.
- **Where:** `stage2-spec-draft.md › MODIFIED` ("The smoke workflow requirement")

**S-I4.** Decision scenarios, enum and precedence.
- **Where:** `spec.md › Pre-registered settled-beat decision rule` (three-value enum, precedence,
  four scenarios)

**S-I5.** Edge cases at B = 3/4.
- **Resolution:** `MIN_BEATS = 5`.
- **Where:** `spec.md` (the scenario "Too few beats are rejected")

**S-I6.** Decision versus gate consistency. Same as M1.

**S-I7.** Impact omissions and BREAKING markers.
- **Where:** `proposal.md › Impact`

**S-I8 / G-I1.** PR boundaries; PR 2 too big.
- **Resolution:** four PRs. The N-independent tooling is separate from the results and decks.
- **Where:** `proposal.md › What changes` table; `tasks.md`

**S-I9 / Doc (one-off procedure in the spec).**
- **Resolution:** the permanent spec now names no configurations or control IDs. Those live in
  `PREREGISTRATION.md` and the settling manifest.
- **Where:** `spec.md` (generic "controls the settling manifest declares")

**Doc-I1–I7.** Missed docs.
- **Where:** `tasks.md › 6.2`, `› 12.3` (with text guards), `› 15.2`, `› 15.3`

**Doc-I8 / G-I4.** Shared files with bench PR 2.
- **Resolution:** the PR 1 entries are kept short, and the 2-beat README notes wait for bench
  PR 2.
- **Where:** `tasks.md › 6.2` and `› 15.3`

**Doc (DRY, durable homes).**
- **Resolution:**
  - `PREREGISTRATION.md` is the single narrative home of the rule.
  - The settling README links to it rather than restating it.
  - Data locations and backup status go in the corpus READMEs and `project.md`.
- **Where:** `tasks.md › 3.1`, `› 5.5`, `› 15.2`; `design.md › D8`

**Doc (7.5 s/step unsourced).**
- **Resolution:** cited as the 2026-09 local probe, and remeasured by C1.
- **Where:** `proposal.md › Cost`

**G-I2.** Commits too large.
- **Resolution:** the groups are split.
- **Where:** `tasks.md` (1/2/3, 5.1–5.5, 10.1–10.3 as separate commits, 12 split)

**G-I5.** Branch per PR.
- **Where:** `tasks.md` (Rules; PR headings)

**G-I7.** Run from a clean `main` SHA.
- **Where:** `tasks.md › 7.1`

## Deferred, with a reason

- **M (deadline not a strict bound with several preemptions).** This is stated as a sizing choice,
  not a guarantee; the runbook's trimmed-manifest resume covers it. The resume-on-retry follow-up
  is filed in 15.4 if C2 passes.
- **Bench `late_beat` consolidation.** That code belongs to another session; it is listed in
  `design.md › D10`.

**Superseded in round 2:**
- T-I3: the coarse corpus keeps `init_iter = 0`; see M2-5.
- C2 and its deck in T-I2 / M7: C2 is removed; see M2-4.
- "resume-on-retry if C2 passes": now #205.

# Round 2 (reviewed `da58f09`)

Three reviewers ran: math/physics (M2), spec and tests (ST2), and docs and git (DG2). All three
returned NEEDS REVISION.

## BLOCKING

**ST2-B1 / M2-2. Jitter.** *"J > 1e-3 on the committed beat 2 … 26 of 55 config×grid cases
exceed STEP_FLOOR … its argmax is always grid point k = 0 … J ≈ endjump/30."*
- **Resolution:**
  - The 256-point grid is removed from the gate, and beats are compared at their own sample
    resolution. The grid hit or missed one-sample reversal spikes, even at f100.
  - `J` is now `rms(Δ²w_B)/(8P)` over interior samples, with no wrap. This is the
    linear-interpolation error bound at half a sample spacing.
  - Measured `J` is at most 2.7e-4 on every committed final beat, and about 2e-5 on E0b.
  - The noise floor is `ν = 3J`. `MAX_NOISE = 2e-3` leaves 2.5× margin over the noisiest committed
    beat.
  - The spike scenario now has an amplitude of `0.05·P`.
- **Where:**
  - `design.md › D2` steps 2 and 4 ("There is no 256-point grid"; the `J` formula)
  - `spec.md › Beat-to-beat settling metric`: the Distance and Jitter bullets, and the scenario
    "Off-integer steps per beat add less than the noise floor"
  - `tasks.md › 1.2` ("`J ≤ 2.7e-4` on the final beat of every configuration of both committed
    corpora")

**M2-3. Counterexamples to pass(N).** Rising ratios, a slow mode at the floor, and growth inside
the floor all passed. The reviewer's fix: *"Skip a ratio only when both steps are ≤ 3·J_nowrap …
inflate ρ when the ratios are rising (ρ = max r + max(0, r_B − r_{B−2}))."*
- **Resolution:** adopted as written. All three counterexamples now fail: `T` is 1.44% and 1.73%
  for the first two, and the third is not contracting.
- **Where:**
  - `design.md › D2` steps 5–6, and the "Stress tests" table
  - `spec.md` scenarios "Rising ratios widen the bound", "A slow mode below one percent is not
    mistaken for noise" and "Growth from the noise floor is not contracting"

**M2-4 (C1/C3). Byte-identical comparison fails on round-off.** *"3999 of 4000 rows are
identical; row 1 differs in round-off … compare parsed values with an absolute tolerance of about
1e-9·max|column|, and pre-register it."*
- **Resolution:** adopted as written.
- **Where:**
  - `design.md › D4` controls table
  - `spec.md › A settling report…`: scenario "Round-off passes the force comparison and a real
    difference fails"

**M2-4 (C2). The restart control fails predictably.** A restart truncates the CSV by line count
and resets the marker state.
- **Resolution:** confirmed in `DiffusedIB.cpp:1405-1450` and filed as **#205**. C2 is removed,
  and no Stage 1 run restarts. The checkpoints are kept (open question 3).
- **Where:** `design.md › D4` ("No restart control") and `› D7` (last table row)

**ST2-B2. Two live requirements contradict the plan, and the draft used wrong requirement
names.**
- **Resolution:**
  - Added: "Argo sweep-submission parallelism is overridable…" and "Argo sweep-submission provisions
    the NFS workspace…".
  - Renamed to "Surrogate input and target construction" and "Cluster-side Argo orchestration of
    the corpus".
  - All requirement headers are now exact.
- **Where:** `stage2-spec-draft.md › MODIFIED` (nine entries); `proposal.md › Impact`

**ST2-B3. More existing tests break.**
- **Resolution:** listed by file and line.
- **Where:** `tasks.md › 12.1` (`test_submit_workflow_parallelism.py:96-119`,
  `test_submit_workflow_provision.py:116, 147, 324, 353, 529`)

**ST2-B4. `full` hard-fails on the old corpora.**
- **Resolution:** `prelim_sweep_fine` gets a `cluster_sizing.json`. `prelim_sweep` intentionally
  needs an explicit deadline, and a scenario covers it.
- **Where:** `design.md › D5` (last bullet); `stage2-spec-draft.md` (auto-scale entry);
  `tasks.md › 12.1–12.2`

**DG2-B. The stop path contradicts merging PR 2 early.**
- **Resolution:** PR 2 merges only after 13.2 decides `regenerate`. On `stop`, its branch is
  closed unmerged.
- **Where:** `design.md › D1` ("**merges only after PR 3's decision is `regenerate`**"); the
  `tasks.md` PR 2 heading and `› 13.2`

**M2-5. The init_iter premise is contradicted.**
- **Resolution:** checked with the project's CC-F1 check on E0b `plt12000`, written at
  `init_iter = 0`: x_velocity runs from −21.1 to 4.2. The coarse corpus keeps `init_iter = 0`, and
  its smoke run runs CC-F1. The stale spec claim is filed as **#206**.
- **Where:** `design.md › Context` and `› D4`; `tasks.md › 14.2`

## IMPORTANT

- **ST2-I1 / DG2. The precedence check only lands in PR 3 and can pass vacuously.**
  - **Resolution:** a checker with synthetic tests lands in PR 1, and it fails when `DECISION.md`
    exists without enough records. `git_dirty` is added to the record checks.
  - **Where:** `tasks.md › 3.3` and `› 5.3`; `spec.md` scenario "A decision without run records
    fails"
- **DG2. The precedence claim is attested, not proven.**
  - **Resolution:** stated as such, with its scope limited to the fine-grid and 8-beat data. The
    `generate_decks.py` hash is gated.
  - **Where:** `design.md › D3 › Precedence proof`; `spec.md › … precedence is attested`
- **ST2-I2. It is unclear which functions refuse multi-beat data.**
  - **Resolution:** `filter_converged_beat` and `build_phase_only_baseline`. Bench calls are
    refused on purpose.
  - **Where:** `design.md › D6`; `stage2-spec-draft.md`
- **ST2-I3. Provenance and CC-F1 keying.**
  - **Resolution:** `field_capture` records `frames_per_beat` and `checkpoints_per_beat`. CC-F1
    keys on `frames_per_beat > 0`. The rationale text is fixed.
  - **Where:** `design.md › D6`; `stage2-spec-draft.md › ADDED 3`; `tasks.md › 8.1`
- **ST2-I4 / DG2. The coarse `cluster_sizing.json`.**
  - **Resolution:** the fine grid's measured spread (2.321/2.137 and 3.302/2.137) is applied to the
    coarse smoke rate, stated as an assumption. The file is committed in PR 4. Fine `s_max` is
    refreshed from the fine smoke run.
  - **Where:** `design.md › D9`; `tasks.md › 14.2`, `› 14.4`, `› 15.1`
- **ST2-I5. The Stage 1 and Stage 2 decks are not linked, and the image is unpinned.**
  - **Resolution:** a deck-equality test in 13.4, and each grid's image is pinned.
  - **Where:** `tasks.md › 13.4`; `design.md › D4` ("Images")
- **ST2-I6. The fixture is ambiguous.**
  - **Resolution:** paths, blobs, `git_dirty` and the peak/mask convention are all named.
  - **Where:** `tasks.md › 1.2`; `design.md › D4` ("Known answers")
- **ST2-I7. The source of `dt`.**
  - **Resolution:** a required argument, taken from the manifest's `fixed_dt`.
  - **Where:** `spec.md › Beat-to-beat settling metric` (Beats bullet)
- **ST2-I8. `maxDuration` cannot be patched per submission.**
  - **Resolution:** a static `"105h"` with a coverage test.
  - **Where:** `design.md › D9` ("Retry budget")
- **DG2. Why sources, and labels used before definition.**
  - **Resolution:** E0b and E1 are cited; C1–C4, the tail bound, E0, E0b and gh-04 are defined at
    first use; "top 3" and "worst" are aligned.
  - **Where:** `proposal.md › Why` and `› Stage 1`
- **DG2. Durable homes.**
  - **Resolution:** D10 goes into `DECISION.md` and roadmap row 19. The backup question is asked
    before 15.2.
  - **Where:** `design.md › D10`; `tasks.md › 13.1` and `› 15.2`
- **DG2. Missed docs.**
  - **Where:**
    - `tasks.md › 12.3`: `submit_workflow.sh` lines 84, 95 and 333;
      `force-surrogate-smoke.yaml:37`; the argo README line 139; the runbook lines 41–57
    - `tasks.md › 15.2`: the field roadmap lines 213, 395 and 407
    - `tasks.md › 15.3`: the fine README line 327
    - `tasks.md › 6.1`: `project.md:212`
- **M2 minor items.**
  - **Resolution:** C4 is restricted to interior steps; the crossing rule uses step end times;
    "at least N beats" is used consistently; coarse sizes are 8.2 MB and 25 MB; the reason both
    grids share N, and its cost, are stated.
  - **Where:** `design.md › D3`, `› D4` and `› D7`
- **DG2. Two vague round-1 entries** ("MODIFIED (three entries)", and T-I2).
  - **Resolution:** superseded by ST2-B2, and by removing C2.

## Also done after round 2

- `training_wingbeat` moved out of PR 1, so it lands with its requirement in PR 2.
- `MAX_NOISE` raised from 1e-3 to 2e-3. At 1e-3 it left only 20% margin over the noisiest
  committed beat (`3J = 8.1e-4`).
- The smoke configuration's committed rate corrected to 2.137 s/step (7432 s / 3478 steps).

## Not adopted

- **M2-4 alternative: patch IAMReX.** Out of scope; tracked as #205.

**Superseded in round 3** (pointers above that no longer match the files):
- Round 1:
  - M2 "0.1·tolerance" and the old scenario names;
  - M3 `STEP_FLOOR`, the 1e-3 floor and "1e-4 to 5e-4";
  - M6 "byte-identical CSV rows" and "coarse C3 reported only" (C3 is now gated on both grids, with
    a tolerance);
  - G-B1 "provable" (now "attested");
  - S-I4 "four scenarios" (now five);
  - T-B3 "never from the observed beats" (unchanged in meaning; wording moved);
  - T-B1 "Each new corpus directory" (now each submittable corpus).
- Round 2:
  - ST2-B1 "J at most 2.7e-4" and "`MAX_NOISE = 2e-3`" (both from the clamped-row artifact; see
    M3-B1);
  - ST2-I8 `"105h"` (now `"120h"`);
  - ST2-I4 "committed in PR 4" (now in sizing PRs).

# Round 3 (reviewed `84ff57e`)

Two reviewers ran: math/physics (M3) and consistency/tests (C3R). Both returned NEEDS REVISION.

## BLOCKING

**M3-B1. Clamped final step.** *"At f085 the final step is clamped by `stop_time`, and the metric
does not exclude it … the last row of every committed f085 final beat is a spike of up to 0.104·P
… Fix: drop rows whose step end exceeds `stop_time` (`time + dt > stop_time + ε`) before the beat
split, in `settling.py` and in C3 … restate the J measurements without that row (≤ 6.4e-5) … add a
scenario with a clamped final sample."*
- **Resolution:** adopted as written.
  - Re-measured: `J ≤ 6.4e-5` on every committed final beat.
  - `MAX_NOISE` is lowered to 4e-4 (raised to 6e-4 in round 4).
  - The known answers are unchanged, because the E0b runs are f100 and therefore not clamped.
- **Where:**
  - `design.md › D2` step 0 ("Clamped steps are dropped") and step 4 ("Measured, with clamped
    rows dropped: at most 6.4e-5")
  - `spec.md` "Clamped steps" bullet and scenario "A clamped final step is dropped"
  - `design.md › D4` C3 row ("excluding the reference's clamped final row")
  - `tasks.md › 1.1` and `› 5.1`

**M3-B2. The spike scenario cannot be satisfied.** *"Replace the scenario with 'an exactly periodic
smooth signal built from a committed beat, on the true f085/f115 step grids, gives s_b ≤ ν'."*
- **Resolution:** replaced as written.
- **Where:** `spec.md` scenario "Off-integer steps per beat add less than the noise floor";
  `tasks.md › 1.2`

**C3R-B1. The fine C1/C3 comparison fails on the `init_iter = 2` duplicates, and its reference is
not in git.**
- **Resolution:**
  - The run's rows are compared after the extractor's validated de-duplication.
  - The reference is the configuration's rows of the committed `dataset.parquet`, matched by
    `time`, so CI can re-check the comparison.
  - A test covers the `init_iter` duplicate pair.
- **Where:**
  - `spec.md › A settling report…`: "de-duplicate the run's force rows with the extractor's
    validated rule … match … the committed `dataset.parquet` by `time`", and scenario
    "Init-iteration duplicates do not fail the comparison"
  - `design.md › D4` ("Comparison")
  - `tasks.md › 5.1`

## IMPORTANT

- **M3-I1. The all-skipped branch can hide slow modes.** *"use T = max s·ρ_cap/(1−ρ_cap) with
  ρ_cap = 0.96 (24·max s), and set MAX_NOISE = 4e-4."*
  - **Resolution:** adopted.
  - **Where:** `design.md › D2` step 7; `spec.md` Tail-bound bullet and scenario "A run at the
    noise floor…" (`T = 9.6e-4`)
- **M3-I2. Two modes can defeat the three-ratio window.**
  - **Resolution:** stated as a limitation, cross-checked against the reported mean-CF_z drift.
  - **Where:** `design.md › D2` "Known limitations"; `PREREGISTRATION.md` (task 3.1)
- **M3-I3. Two noise-level steps that straddle ν read as growth.** *"call it growth only when
  s_b > 2ν."*
  - **Resolution:** adopted.
  - **Where:** `design.md › D2` step 5; `spec.md` Ratios bullet and scenario "Two noise-level steps
    straddling the floor are not growth"
- **M3-I4. A tolerance of 1e-9 of the column maximum is bit-exactness for a 6-significant-figure
  CSV.**
  - **Resolution:** the tolerance is now `max(1e-9·max|col|, one print step)`, pre-registered as
    "bit-identical, allowing a flip of the last printed digit". A C1 failure stops the work and is
    reported to the user.
  - **Where:** `spec.md` (force comparison paragraph); `design.md › D4` ("Tolerance")
- **C3R-I1. 105h has no headroom, and the rate files have no commit point.**
  - **Resolution:** `"120h"`, with sizing PRs landing before each full sweep. The ADDED 6 scenario
    was reworded to match.
  - **Where:** `design.md › D9`; `tasks.md › 14.2` and `› 14.4`; `stage2-spec-draft.md › ADDED 6`;
    `proposal.md` (sizing PRs)
- **C3R-I2. "Nine" requirements.**
  - **Resolution:** now "eleven".
  - **Where:** `proposal.md › Impact`
- **C3R-I3. `training_wingbeat` has no task.**
  - **Where:** `tasks.md › 10.1`
- **C3R-I4. Commits go red between a test task and its implementation task.**
  - **Resolution:** each tests-first task is committed together with its implementation task.
  - **Where:** `tasks.md` Rules
- **C3R-I5. The report recompute cannot cover the field values in CI.**
  - **Resolution:** the CI recompute covers force-derived numbers only. Field values carry their
    plotfile hashes.
  - **Where:** `design.md › D3` ("Recomputation") and `› D4`; `tasks.md › 5.3` and `› 13.1`
- **C3R-I6. Missing writers.**
  - **Resolution:** `scripts/record_settling_run.py` / `settling.write_run_record`. The Stage 1
    dataset is built by the existing extractor from the settling manifest. C4 uses
    `metadata_capture`'s realized-timestep summary.
  - **Where:** `tasks.md › 4.2` and `› 5.3`
- **C3R-I7. Report-only precedence trigger.**
  - **Where:** `tasks.md › 3.3`
- **C3R-I8 / M3. CF_my is the binding target for `s45_f100_p30`.**
  - **Resolution:** pinned at 0.01245.
  - **Where:** `design.md › D2`; `tasks.md › 1.2` and `› 2.1`; `proposal.md` ("CF_my 1.245%")
- **C3R-I9. Stale round-1 pointers.**
  - **Resolution:** listed under "Superseded in round 3" above.
- **C3R-I10. CC-F1 keying and the open-question number.**
  - **Resolution:** CC-F1 runs on `frames_per_beat > 0` or `plot_int > 0`; the open question is 3.
  - **Where:** `design.md › D6` and `› D7`; `tasks.md › 10.2`
- **Suggestions adopted:**
  - stress-table steps aligned with the spec;
  - tests for the maximum absolute difference, `stop_time` and the `ν = MAX_NOISE` boundary;
  - schemas moved into 5.3;
  - "256-point phase grid" wording;
  - geometric-scenario tolerance;
  - the `FIRST_RATIO_BEAT` wording;
  - `pass(5)` stated as harder by design;
  - one `DiffusedIB.cpp` range;
  - the 13.1 E0b match now uses the C1 tolerance, with report-and-decide on failure.

# Round 4 (fix re-review of `bab82a7`)

One reviewer re-checked the round-3 fix commit. They implemented the metric independently and
found nothing in the numbers CONTRADICTED. The verdict was NEEDS REVISION, with no blocking
findings.

## IMPORTANT

- **R4-1. The tolerance fails about half of legitimate last-digit flips.** *"Of 100k random
  6-significant-figure flips, 48.9% have |a−b| > unit when computed in floating point … write 'at
  most 1.5 units in the 6th significant figure' … state that the unit is 0 for a reference value of
  exactly 0."*
  - **Resolution:** adopted as written. The column maximum is taken over the matched reference
    rows.
  - **Where:** `spec.md` force comparison paragraph ("1.5 units in the 6th significant figure …
    For a reference value of exactly 0 the second term is 0"); `design.md › D4` ("Tolerance");
    `tasks.md › 5.1` (the `1.00000` against `0.999999` case)
- **R4-2. "Missing" is never defined for the comparison.** *"every run row matches exactly one
  reference row, and every reference row with time ≤ the run's last kept time is matched."*
  - **Resolution:** adopted. A run that stops cleanly at step 380 would still satisfy that rule,
    so the run must also reach its declared step count.
  - **Where:** `spec.md` ("SHALL contain every step up to the control's declared step count") and
    scenario "A truncated run fails the comparison"; `design.md › D4` ("Coverage"); `tasks.md › 5.1`
- **R4-3. The stale tolerance in the pre-registration task.**
  - **Resolution:** fixed.
  - **Where:** `tasks.md › 3.1`
- **R4-4. `MAX_NOISE` headroom.** *"the scenario's own 8-beat f115 reconstruction reaches
  ν = 3.07e-4."*
  - **Resolution:** `MAX_NOISE` is raised to 6e-4, about 2× over 3.07e-4. The all-skipped bound
    becomes at most 2.9%. The "too much noise" scenario moves to `ν = 9e-4`.
  - **Where:** `design.md › D2` constants table and step 7; `spec.md` constants and decision
    scenario

## SUGGESTION, all adopted

- The interpolation is named (linear; `s_b ≤ 0.57·ν`, or 0.30·ν with a cubic spline).
- "≈6.4e-5 (< 6.5e-5)".
- Tasks 1.1 + 1.2 + 1.3 are committed together.
- Row counts sum to `max_step` minus the clamped row.
- The `+ 1e-9` slack is written out in task 1.1.
- The `settled_sweep_fine` source is described before and after its sizing PR.
- The manifest key is `dt`.
