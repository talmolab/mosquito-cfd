# Tasks — fine-grid training-data pilot

TDD for everything cluster-free; the actual CFD runs (Phase 2) are operator/live-cluster work,
not unit-testable. `uv` for all Python ops. Branch: `add-fine-grid-training-pilot` (off `main`).

**Revision note (post-review):** a 5-agent OpenSpec review found several concrete, code-verified
problems in the first draft of this file — a test that would either do nothing or delete the
real 27-config corpus, a `generate_sweep()` call that would crash with `ValueError` as written, a
submission command that blocks and would hit a tool timeout on a multi-hour job, and a monitoring
plan that doesn't observe what it claims to. All are fixed below; see the OpenSpec change's
review history for the full findings.

**Revision note 2 (post-PR-review, pre-merge):** a 5-agent `/review-pr` on PR #58 (after Phase
0-4 had already landed and all 3 cluster runs completed) found 4 BLOCKING + several IMPORTANT
issues, all fixed via TDD before merge:
- `generate_pilot.py` had no runtime guard against `--output` pointing at the frozen coarse
  corpus (a real `unlink()`-against-real-data risk) — added `_validate_output_dir()` +
  3 tests (pure-function, CLI-wiring via a monkeypatched decoy, and the pre-existing static
  isolation guard).
- All 3 committed `run_metadata_<config>.json` had a `timing.final_time` that recorded the
  deck's `stop_time` instead of the force CSV's actual last row (always exactly one `dt`
  earlier — a pre-existing IAMReX writer convention, not a divergence bug) — corrected all 3
  + added a parametrized regression test (`test_pilot_run_metadata_final_time_matches_last_csv_row`).
- 2 of 3 metadata files used a truncated 7-char git SHA instead of the full 40-char one — fixed
  + added `test_pilot_run_metadata_git_commit_is_full_sha`.
- `test_pilot_report_covers_all_attempted_configs` was a whole-document substring check inside a
  per-config loop (never confirmed a given config's *own* line carried its stability outcome,
  and never checked for a numeric figure or the 27-config cost projection at all) —
  strengthened to a per-line, per-config check + a dedicated cost-projection assertion.
- No test tied `generate_pilot.PILOT_CONFIGS` to the test file's own hand-duplicated config list
  — added `test_pilot_configs_match_generate_pilot_script`.
- Also: fixed a wrong citation in the pilot report (cited `t3c-handoff.md`, which doesn't
  contain the cited figures; corrected to `docs/aerodynamics_validation/roadmap.md`); reconciled
  a stale GPU-VRAM comment in the Argo template; parameterized the pod's host-RAM
  limit/request (`pod-memory-limit`/`pod-memory-request`, via `podSpecPatch` since Kubernetes
  `resource.Quantity` fields can't be templated directly) instead of hardcoding it in the shared
  WorkflowTemplate, and re-applied the template to the cluster; added a malformed-JSON
  clear-error test and a `dt_reduced`/`fixed_dt` correlation test; documented the
  unexercised-preemption-retry-path caveat in the pilot report.
See PR #58's review comment for the full original findings list.

---

## 0. Fine-grid base deck — cluster-free

- [x] 0.1 Create `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` as an exact copy of
  `examples/prelim_sweep/base_inputs.3d.validation`, changing only `amr.n_cell` (`64 32 64` →
  `256 128 256`). Header comment documents this is the fine-grid pilot deck and why
  `ns.fixed_dt` is left at `5e-4` (untested-but-plausibly-stable, not pre-emptively dropped).
- [x] 0.2 **Test first (deck invariance):** add `tests/test_fine_pilot_deck.py` with
  `test_fine_pilot_deck_matches_coarse_base_except_n_cell`. Parse both decks into `{key: value}`
  maps (reuse the parsing approach from `tests/test_convergence_deck.py`); assert the symmetric
  difference of keys is empty; assert `amr.n_cell` is `"256 128 256"` in the fine pilot deck and
  `"64 32 64"` in the coarse base; assert every other value is identical. Fails: deck missing or
  an unexpected field changed.
- [x] 0.3 **Verify:** `uv run pytest tests/test_fine_pilot_deck.py -v`.
- [x] 0.4 Update `docs/force_surrogate/roadmap.md` now (no new information needed — this is
  already a merged, known fact) with the specific T3c finding: `CF_chord` is +115% off the
  QS-model target at the corpus's current coarse resolution, and a pilot is in flight
  (`add-fine-grid-training-pilot`) to assess fine-grid feasibility before regenerating. Do not
  wait for the pilot's outcome to flag the known severity — that update is separate (task 3.5).

---

## 1. Pilot deck generation (TDD, cluster-free)

- [x] 1.1 **Test first (byte-reproducibility):** add
  `test_pilot_decks_are_byte_reproducible_from_generate_sweep` to `tests/test_fine_pilot_deck.py`.
  Call `generate_sweep(base_inputs_path=".../base_inputs.3d.fine", output_dir=tmp_path, ...)`
  twice with the 3 pilot configs (`s55_f115_p45`, `s45_f100_p45`, `s35_f085_p45`, each
  `pitch_amp_deg=45`), **`n_holdout=0`** (required — the default `N_HOLDOUT=6` exceeds the
  eligible non-corner configs when only 1 of these 3 is non-corner, and `select_holdout` raises
  `ValueError` otherwise; verified this would fail without the override), `n_wingbeats=2`,
  `dt=5e-4`, and identical `timestamp`; assert the two output trees are byte-identical (deck
  files + `sweep_manifest.json`), and assert the call does not raise. Reuses `generate_sweep()`
  unmodified — this pins the pilot's specific invocation (including the `n_holdout=0`
  requirement), not new code.
- [x] 1.2 **Test first (max_step values):** add `test_pilot_max_step_matches_run_duration_formula`.
  Assert `derive_run_duration(1.15, 2, 5e-4) == (3478, ...)`,
  `derive_run_duration(1.00, 2, 5e-4) == (4000, ...)`,
  `derive_run_duration(0.85, 2, 5e-4) == (4706, ...)`.
- [x] 1.3 **Test first (isolation guard, static):** add
  `test_pilot_output_dir_and_workspace_path_differ_from_coarse_corpus` to
  `tests/test_fine_pilot_deck.py`. This asserts, **statically** (no execution of
  `generate_sweep()` against a real path, no cluster call):
  - the pilot generation script's module-level output-directory constant (to be added in 1.4) is
    not `Path("examples/prelim_sweep")`
  - the pilot's configured `WORKSPACE_HOSTPATH` string (recorded as a constant alongside the
    script, or in a small committed submission-args file — see 2.1) is not the coarse corpus's
    NFS hostpath
  This test is written and must pass **before** task 1.5 (which runs the real script for real) —
  it exists specifically to catch a hardcoded-path mistake before any real generation happens,
  not after. (An earlier draft of this test hashed `examples/prelim_sweep/` before/after running
  the real script — that design is unsafe: pointed at a safe path it proves nothing, pointed at
  the script's real defaults it risks actually triggering `generate_sweep()`'s stale-deck-pruning
  `unlink()` against the committed 27-config corpus before the test could fail. Replaced with
  this static check + a one-time manual hash sanity-check in 1.5, not a repeatable executed test.)
- [x] 1.4 Write a short, one-off pilot-generation script (not a permanent library addition —
  `examples/prelim_sweep_fine_pilot/generate_pilot.py`) that calls `generate_sweep()` with the
  fine base deck, the 3 pilot configs, `n_holdout=0`, `n_wingbeats=2`, `dt=5e-4`, writing into
  `examples/prelim_sweep_fine_pilot/`. Defines the output-directory constant task 1.3 checks.
- [x] 1.5 **Verify:** `uv run pytest tests/test_fine_pilot_deck.py -v` (1.3's static guard must
  already be green). Then run the generation script for real, once, and manually confirm (a) the
  3 decks + manifest land under `examples/prelim_sweep_fine_pilot/inputs/`, and (b) as a one-time
  passive sanity check, `examples/prelim_sweep/`'s committed files are unchanged (`git status`
  shows nothing there) — this is a manual confirmation of the static guarantee 1.3 already
  proved, not a new automated test.

---

## 2. Cluster submission — live RunAI, this session

**Session-continuity note (read before starting this phase):** submission and the initial
~10-15 minute sanity check happen live, in-session. Everything after that — waiting out the
remaining multi-hour run and recording its outcome — is a **detached, come-back-later**
operation: the Argo workflow runs on the cluster independent of this conversation once
submitted. Do not attempt to hold a tool call, a task, or a session open across the full run
duration; `submit_workflow.sh smoke`'s underlying `argo submit --watch` blocks until completion
and would exceed a normal tool call's timeout on a run this long. Submit in a detached/background
mode, confirm the workflow object exists, do the short sanity check, then move on; check status
later via `monitor_workflow.sh get/logs <name>`.

- [x] 2.0 Confirm the current `:fp64` digest (`ghcr.io/talmolab/mosquito-cfd@sha256:...`) — the
  one already used for the original 27-config coarse sweep should already contain
  `run_one_config` and be safe to reuse (this proposal makes no code changes, so no fresh
  merge/build is required). Record the exact digest used; it's captured automatically in each
  config's `run_metadata_*.json` via the existing schema.
  **Done:** `sha256:f546ead9afd9bf490cdc2b255ed0a254f4079262ea6cd4b3d1d7e6c86b0f286a` (confirmed
  via the `docker.yml` "Emit FP64 image digest to job summary" step on the latest main-branch
  build).
- [x] 2.1 Stage `examples/prelim_sweep_fine_pilot/` (decks, `wing.vertex`) onto
  `WORKSPACE_HOSTPATH=/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine_pilot`
  (pinned — mirrors the existing `flapping_wing/`/`prelim_sweep/` Z:\ ↔ NFS pattern exactly; not
  an open question). This is a hard prerequisite for every task below — nothing in this phase
  runs without it.
- [x] 2.2 Bump the single-config Argo template's pod `resources.limits.memory` /
  `requests.memory` for these 3 submissions (e.g. `32Gi` → `64Gi`) — a distinct concern from GPU
  VRAM (below): fine 256×128×256 is ~64× the coarse grid's cell count, and host-side AMReX
  bookkeeping (not just GPU memory) plausibly scales with it. Cheap insurance against a
  mid-run OOMKill (a different failure mode than GPU OOM) several hours into a run.
  **Done:** committed `770847b`, applied to the cluster's live WorkflowTemplate via
  `submit_workflow.sh template`.
- [x] 2.3 Submit config 1 (`s55_f115_p45`, highest Reynolds — closest to the already-known
  CFL-marginal validated case, so submitted first to learn fastest whether the fallback is
  needed at all) via `cluster/argo/scripts/submit_workflow.sh smoke`, **run in a detached/
  background mode** (not as a blocking foreground call), with `SMOKE_CONFIG_NAME=s55_f115_p45`,
  `SMOKE_INPUT_FILE=inputs/inputs.3d.s55_f115_p45`, `SMOKE_MAX_STEP=3478`,
  `WORKSPACE_HOSTPATH` from 2.1, `--image` from 2.0.
  - [x] 2.3.1 Confirm the workflow object was accepted and the pod reaches `Running` phase
    (`monitor_workflow.sh get s55_f115_p45` or equivalent), and watch for the first ~10-15
    minutes for an early phase transition OUT of `Running` (a fast crash-on-launch signature).
    Do **not** rely on `argo logs`/`kubectl logs` to show live solver diagnostics — the runner
    buffers subprocess output and only writes it after the process exits, so log-tailing shows
    nothing useful until completion or crash. Also confirm GPU VRAM via `nvidia-smi`/pod
    describe stays under 48 GB during this window (folds in the arena-size open question — this
    can only actually be confirmed by observing a running pod, not as a prior standalone gate).
    **Done, with a gap:** pod-phase polling (2-min intervals over ~13 min) confirmed clean
    `Running` throughout for all 3 configs. `nvidia-smi` VRAM confirmation was **not possible**
    — the Argo service account lacks `pods/exec` RBAC in `runai-talmo-lab` (`Forbidden`). Relied
    on pod-phase + CSV-row-growth only (both signals D6 already documents as the real live
    signals, since log-tailing shows nothing anyway); AMReX's own end-of-run report confirmed
    VRAM headroom retroactively (`The Arena` max used 7998 MiB / 46068 MiB card) for all 3.
  - [x] 2.3.2 **This is now a detached, later check-in** (may be a new session, hours or a day
    later): `monitor_workflow.sh get s55_f115_p45`. If `Succeeded`: record wall time +
    `s_per_step` from the run's metadata/output; proceed to 2.3.5 (commit) before starting
    config 2. If `Running` and the CSV row count is growing (secondary health signal, checkable
    on the NFS mount without waiting for pod exit): nothing to do yet, check back later. If
    `Failed`/`Error`: go to 2.3.3.
    **Done:** `Succeeded` in 1h58m (7032.46s), `s_per_step=2.022` — well under the ~7.6h
    T3c-carried-over estimate.
  - [x] 2.3.3 If it diverged (caught in 2.3.1's crash-signature check, a stalled/non-growing CSV
    in 2.3.2, or discovered at a later check-in): apply the T3c fallback
    (`ns.fixed_dt=2.5e-4`, `max_step=6956`), re-submit (background again, repeat 2.3.1-2.3.2).
    **Not needed** — config 1 was stable at `dt=5e-4`.
  - [x] 2.3.4 If still unstable at `2.5e-4`: `monitor_workflow.sh stop s55_f115_p45` to free the
    GPU. Record as a genuine "unstable at this kinematic range" finding — do not retry further
    or route around it silently. Copy any partial force CSV/log to
    `examples/prelim_sweep_fine_pilot/` as evidence (e.g.
    `run_metadata_s55_f115_p45_unstable.json` + `forces_s55_f115_p45_partial.csv`) rather than
    discarding it.
    **Not needed** — config 1 completed cleanly.
  - [x] 2.3.5 **Commit config 1's results now** (`run_metadata_s55_f115_p45.json` + force CSV, or
    the unstable-finding artifacts from 2.3.4) — do not wait for configs 2/3. A partial pilot
    (e.g. only config 1 done) should still leave real, committed data.
    **Done:** commit `70c68fb`, pushed.
  - [x] 2.3.6 **Serial gate**: do not start config 2 (task 2.4) until config 1's workflow is
    confirmed in a terminal state (`Succeeded`/stopped-as-unstable) via `monitor_workflow.sh
    get` — never more than 1 GPU committed at once (the explicit reason serial execution was
    chosen over parallel).
    **Done.**
- [x] 2.4 Submit config 2 (`s45_f100_p45`, mid Reynolds), identical procedure to 2.3
  (`SMOKE_MAX_STEP=4000`, fallback `max_step=8000`), including its own 2.4.1-2.4.6 sub-steps
  (sanity check, detached check-in, fallback, abort/evidence, immediate commit, serial gate
  before config 3).
  **Done:** `Succeeded` in 2h13m (8002.88s), `s_per_step=2.001`, no fallback needed. Committed
  `634c561`, pushed.
- [x] 2.5 Submit config 3 (`s35_f085_p45`, lowest Reynolds), identical procedure to 2.3
  (`SMOKE_MAX_STEP=4706`, fallback `max_step=9412`), including its own 2.5.1-2.5.5 sub-steps
  (no serial gate needed after — this is the last config).
  **Done:** `Succeeded` in 2h37m (9448.47s), `s_per_step=2.008`, no fallback needed (final
  step's `DT` is benign-truncated to land exactly on `stop_time`, not a divergence response —
  see the pilot report). Committed `f1f903e`, pushed.

**Note on the local `argo submit --watch` client:** the background process wrapping
`submit_workflow.sh smoke` for configs 2 and 3 reported `failed`/`stopped` locally partway
through each multi-hour run — in both cases this was the local watching client losing its own
connection/being torn down, **not** the cluster workflow itself; `monitor_workflow.sh get`
against the live cluster confirmed the actual Argo workflow was unaffected and continued
running to completion independently. Don't treat a local watch-client failure as a cluster-job
failure — always re-verify via `monitor_workflow.sh get <name>` directly.

---

## 3. Write the pilot report

- [x] 3.1 **Test first (report structure, skipif absent):** add
  `test_pilot_report_covers_all_attempted_configs` to `tests/test_fine_pilot_deck.py`, `skipif`
  the report doesn't exist yet. Parse
  `docs/force_surrogate/fine-grid-pilot-report.md` and assert, for each of the 3 config names
  that was actually attempted (per whatever committed `run_metadata_*.json`/unstable-finding
  files exist), one of the three literal stability strings (`stable_at_5e-4` /
  `stable_at_2.5e-4_fallback` / `unstable`) and a numeric wall-time/`s_per_step` figure appears.
  Written in Phase 0/1 (skipped until Phase 3 landed); now passes for all 3 configs.
- [x] 3.2 **Test first (provenance pin, skipif absent per config):** add
  `test_pilot_run_metadata_schema` to `tests/test_fine_pilot_deck.py`, using
  `pytest.mark.parametrize` over the 3 config names with a per-case `skipif` mark (NOT a single
  function with an internal skip-on-first-missing loop, which would silently stop checking
  later configs) — so a partial pilot reports N passes + (3-N) skips, not one all-or-nothing
  result. Assert the required fields (`git`, `docker_image`, `image_digest`,
  `timing.wall_time_s`, `timing.timesteps`, `timing.s_per_step`, `fixed_dt`, `dt_reduced`) for
  each config whose `run_metadata_*.json` exists.
  Written in Phase 0/1; now passes 3/3 (0 skipped).
- [x] 3.3 Write the pilot report at `docs/force_surrogate/fine-grid-pilot-report.md` (this is a
  Track B / force-surrogate artifact, not an aerodynamics-validation tier — filed under
  `docs/force_surrogate/` alongside `roadmap.md`, cross-referencing the T3c
  `CF_chord`/`CF_normal` numbers already published in `docs/aerodynamics_validation/` rather
  than restating them): per-config stability/timing table, the real (measured) cost projection
  for the full 27-config regeneration, and an explicit go/no-go recommendation.
  **Done:** all 3 configs `stable_at_5e-4`; projected full-27-config cost ~61.2h (~2.55 days)
  serial single-A40; recommendation **GO**.
- [x] 3.4 Open the PR **now if not already open** (see Phase 4 note) rather than holding it open
  only in draft — Phase 0/1's tooling should already be reviewable and CI-green independent of
  whether Phase 2/3 fully completed.
  **Done:** [PR #58](https://github.com/talmolab/mosquito-cfd/pull/58), opened right after
  Phase 0/1 landed.
- [x] 3.5 Update `docs/force_surrogate/roadmap.md` with the pilot's actual outcome (separate
  from 0.4's earlier severity flag): stability results per config, the measured cost estimate,
  and the go/no-go recommendation for the full 27-config regeneration.
  **Done.**

---

## 4. Verification

- [x] 4.1 `uv run ruff check src/ tests/ examples/prelim_sweep_fine_pilot/` and
  `uv run ruff format --check` on the same paths — clean. Confirm
  `examples/prelim_sweep_fine_pilot/` is added to CI's lint invocation
  (`.github/workflows/ci.yml`'s ruff steps currently hardcode a directory list — per that file's
  own comment, a new example directory must be added there explicitly, or the new
  `generate_pilot.py` script is silently never linted in CI).
- [x] 4.2 `uv run pytest tests/test_fine_pilot_deck.py -v` — all 8 tests PASS (0 skipped): all 3
  configs completed, so the Phase 3 skipif-gated tests now run for real.
- [x] 4.3 The full suite `uv run pytest tests/` is green: 473 passed, 14 skipped (no
  regressions — the delta from Phase 0/1's 469/18 is exactly the 4 Phase-3 tests flipping from
  skip to pass).
- [x] 4.4 `openspec validate add-fine-grid-training-pilot --strict` passes.

**PR strategy**: single PR, opened right after Phase 0/1 commits land (cluster-free, CI-green) —
do not wait until Phase 2/3 fully complete to open it. Mirrors `add-wing-fine-grid-convergence`
(T3c)'s actual PR #52 lifecycle: opened early, stayed open across the multi-hour cluster run,
merged once the data + report commits landed.

**Commit sequence** (each safe to make at the point listed):
1. `feat(force-surrogate): add fine-grid pilot base deck (invariance-guarded)` —
   `base_inputs.3d.fine` + task 0.2's test. Safe immediately (Phase 0).
2. `docs(force-surrogate): flag CF_chord +115% coarse-grid finding in roadmap` — task 0.4. Safe
   immediately, no new info needed.
3. `feat(force-surrogate): generate fine-grid pilot decks via generate_sweep()` —
   `generate_pilot.py`, generated decks/manifest, tasks 1.1-1.3's tests. Safe once Phase 1 is
   green (before Phase 2 starts).
4. Per config, as each actually finishes (not batched): `feat(force-surrogate): commit fine-grid
   pilot config N (<name>) results` — that config's `run_metadata_*.json` + force CSV (or
   unstable-finding artifacts).
5. `docs(force-surrogate): fine-grid pilot report + roadmap outcome + go/no-go` — tasks 3.1-3.3,
   3.5. Lands after whichever configs actually complete; does not block on all 3.

---

## Explicitly deferred (follow-on change, if the pilot recommends proceeding)

- Regenerating all 27 configs at fine resolution.
- Any change to `src/mosquito_cfd/force_surrogate/sweep.py`.
- Re-training the surrogate on new data.
