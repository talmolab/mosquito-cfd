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
- **Where:** `tasks.md › 3.1`, `› 5.6`, `› 15.2`; `design.md › D8`

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
