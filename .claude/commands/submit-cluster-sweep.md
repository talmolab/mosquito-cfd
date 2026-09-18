# Submit Cluster Sweep

Submit the force-surrogate 27-config Argo cluster sweep with checks along the way, so a
geometry/kinematics or metadata bug is caught on 2-3 finished configs instead of after burning
all the GPU-hours on the full corpus. Formalizes the runbook already documented (more thinly,
and scattered) across `cluster/argo/README.md`, `cluster/argo/scripts/submit_workflow.sh`'s
header comments, and `openspec/specs/runai-cluster-skill/spec.md`.

## Human Checkpoints — Read This Before Anything Else

This touches a real, expensive, multi-day, shared-lab-quota cluster job. Gathering information,
running read-only checks, and preparing commands is fine to do autonomously. **Stop and get the
user's explicit go-ahead before any of these:**
- Running `smoke` (Step 2) — the first real GPU spend.
- Running `full` (Step 3) — the real 27-config, multi-day spend.
- Overriding any committed default (`--parallelism`, `--active-deadline-seconds`) — state the
  override and why; never silently substitute your own computed value.
- Reducing `--parallelism`, deferring, or proceeding anyway because of tight GPU quota (Step 1).
- Acting on Step 4's mid-sweep decision gate, in **either** direction — letting the fan-out run
  unattended for the remaining days, or stopping a live workflow. Report the finding, then wait
  for acknowledgment. (Gathering the evidence for that decision is autonomous; acting on it isn't.)

## Cluster Environment Quick Reference

- **WSL wrapper** — every `cluster/argo/scripts/*`, `runai`, `kubectl`, `argo` command below is
  written wrapped in:
  ```bash
  wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && <command>"
  ```
  `gh` and `uv run python` commands run on the host, unwrapped.
- **RunAI token expiry** — if any `runai ...` command fails with an auth/token error, this is
  RunAI's own login token, which expires independently of `kubectl`/`argo` auth (a known,
  previously-hit gotcha). Run `runai login` and retry before assuming a real cluster problem —
  see `openspec/specs/runai-cluster-skill/spec.md` for the exact recovery command.
- **First-time environment setup** — KUBECONFIG path, the `runai` binary path, and the
  Windows/WSL/cluster path-mapping table live in `openspec/runai-dev-workflow.md`. `/validate-env`
  does **not** cover any of this — it only checks the local Python/Docker/GPU dev environment.

## Step 0: Confirm the Target Corpus With the User — Do Not Infer It

There are two 27-config corpora: `examples/prelim_sweep` (coarse) and `examples/prelim_sweep_fine`
(fine grid, 256³). **Ask which one — don't assume from context or memory.** `--corpus-dir` and
`--workspace-hostpath` must be passed together and their basenames must match, or
`submit_workflow.sh`'s provisioning step refuses. For the fine corpus:
```bash
--corpus-dir examples/prelim_sweep_fine \
--workspace-hostpath /hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine
```

**The coarse corpus (`examples/prelim_sweep`) still forces `amr.plot_int = -1`** unconditionally
(force-only design, `generate_sweep()` / `openspec/specs/force-surrogate/spec.md`) — it is not
designed to produce a time series of AMReX plotfiles. **Once `add-fine-corpus-field-capture`'s
code+regeneration PR has landed on `main`** (check `git log --oneline -- examples/prelim_sweep_fine/inputs/`
if unsure — the fine corpus's own deck content is the source of truth, not this note), the **fine
corpus** (`examples/prelim_sweep_fine`) is no longer force-only — its decks carry
`amr.plot_int=100, ns.init_iter=2` — so a real run against it does produce plotfiles. Before that
PR lands, the fine corpus is still force-only exactly like the coarse one, and Step 2's CC-F1
check below does not apply. Either way,
Step 4's CSV/force-based check remains the recommended mid-sweep default (cheaper, doesn't need a
completed plotfile time series); don't reach for `make_flow_video.py`/`make_kinematics_video.py`'s
multi-frame workflow mid-sweep purely as a substitute for it. For a **fine-corpus** run
specifically, also run Step 2's `check_plotfile_velocity.py` check against the smoke config's
plotfile before proceeding to `full` — that's the CC-F1 defect this check exists to catch.

**Stale committed metadata warning** — before submitting anything, check whether
`<corpus-dir>/run_metadata_<config>.json` files already exist from a prior, superseded run (see
that corpus's `sweep_provenance.json`'s `supersession_history` list, if present). Flag this to the
user; if the new run fails partway, stale pre-fix and fresh post-fix files are otherwise
indistinguishable by filename alone until someone diffs `workflow_uid`/`pod` fields inside them.

**Pilot-invalidation trigger** — before trusting any prior pilot's stability go/no-go for this
corpus's timestep, confirm whether the geometry, grid resolution, or kinematic range has changed
since that pilot ran. If any have, the pilot's GO does **not** transfer — a geometry change
invalidates a stability pilot as surely as a grid change does (see the corrected `ns.fixed_dt`/
`ns.cfl` mechanism note in `openspec/project.md`'s Conventions, and
`docs/force_surrogate/fine-grid-pilot-report.md`'s erratum, for a concrete instance where this was
missed: a hinge-geometry fix doubled tip speed after the pilot ran, and its GO was assumed to
transfer without re-confirming). If in doubt, a worst-config smoke run (Step 2) is cheap
insurance; a full re-pilot is not always necessary.

## Step 1: Pre-Submission Checks — All Read-Only, Zero Cluster Spend

1. **Fetch the current post-merge `:fp64` digest** — never reuse a memorized/older value. Do
   this first: item 2 below needs it as an argument.
   ```bash
   gh run list --workflow=docker.yml --branch main --limit 1 --json databaseId
   gh api repos/talmolab/mosquito-cfd/actions/runs/<run-id>/jobs --jq '.jobs[] | select(.name=="Build FP64 Image") | .id'
   gh run view --job <job-id> --log | grep "Emit FP64 image digest"
   ```
   If any of these three commands returns nothing (no recent successful run, no matching job, no
   matching log line), **stop** — do not fall back to a memorized or guessed digest.
2. **Geometry sanity, cluster-free** (uses the digest from item 1):
   ```bash
   uv run python scripts/make_wing_phase_diagnostic.py \
       --corpus-dir <corpus-dir> --out-dir <scratchpad> \
       --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST> \
       --timestamp $(date -u +%Y-%m-%dT%H:%M:%S%z)
   ```
   Plots the wing marker cloud at four wingbeat phases with the hinge marked. Catches a
   `fix-force-surrogate-sweep-hinge`-class geometry bug for free, before any GPU time is spent.
3. **Check for a still-running leftover workflow** (avoid double-submitting), wrapped:
   ```bash
   cluster/argo/scripts/monitor_workflow.sh list
   ```
4. **Check current GPU quota headroom** before submitting or raising `--parallelism`, wrapped:
   ```bash
   runai project list
   kubectl describe resourcequota -n runai-talmo-lab
   ```
   talmo-lab's shared quota has been seen well over 100% allocated. Sweep pods are
   `priorityClassName: interactive-preemptible` — they're always schedulable, but at or near
   full quota they **will** be preempted rather than blocked, eating into the retry budget issue
   #64 sized for exactly this. Zero headroom is not a "proceed anyway" signal: bring it to the
   user and propose a lower `--parallelism` (letting Step 3's auto-scale recompute the coupled
   deadline) rather than submitting at the original concurrency regardless. This also affects
   other lab members' jobs — don't decide unilaterally to take the remaining headroom.

## Step 2: `template` → `lint` → `smoke`, in That Order, Never Skipped

**STOP — get the user's explicit go-ahead before running `smoke`.** This is the first real GPU
spend.

```bash
cluster/argo/scripts/submit_workflow.sh template
cluster/argo/scripts/submit_workflow.sh lint
```
`argo lint` is the authoritative structural validator — a failure means a real manifest bug.
Stop and fix it; don't retry past it hoping it self-resolves.

```bash
cluster/argo/scripts/submit_workflow.sh smoke --image ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST> \
    --corpus-dir <corpus-dir> --workspace-hostpath <workspace-hostpath>
```
Runs exactly one config end-to-end (scheduling, GPU, the corrected decks) before the 27-way
fan-out, and re-provisions the NFS workspace from the git-committed corpus — closing issue #62's
class of bug (stale content silently sitting on NFS). The pilot config's own historical mean is
~2.4h (`PER_CONFIG_HOURS` in `submit_workflow.sh`) — if smoke is still `Pending`/`Running` well
past that, suspect scheduling/quota rather than a slow simulation; check pod events (a stuck
`Unschedulable`/`NonPreemptibleOverQuota` state has a documented symptom/fix in
`openspec/runai-dev-workflow.md`) rather than just waiting longer.

**Independently re-verify the result**, wrapped:
```bash
cluster/argo/scripts/monitor_workflow.sh get force-surrogate-smoke-<id>
```
`argo submit --watch`'s stream has died mid-run before while the workflow kept running fine
server-side — never conclude success or failure from the CLI's own exit code alone. Inspect the
smoke config's `IB_Particle_1.csv`/`run.log`/`run_metadata.json` by hand before proceeding.

**Field-capture corpora only (CC-F1)** — if the smoke run's corpus has field capture enabled
(e.g. the fine corpus as of `add-fine-corpus-field-capture`, `amr.plot_int>0`), also check the
smoke config's plotfile before trusting any of it as future training data:
```bash
uv run python scripts/check_plotfile_velocity.py --plotfile <workspace-hostpath>/runs/<config>/plt00100
```
This guards against a known defect: with `ns.init_iter=0`, IAMReX silently never persists the
velocity field to the plotfile — forces are unaffected (marker-derived, not plotfile-derived), so
this defect would otherwise go unnoticed until Stage 2 (field-surrogate) work tries to consume the
plotfiles later. Not needed for a force-only corpus (no plotfiles exist to check).

**Record the result — a mandatory check with no recorded outcome is indistinguishable from one
that was never run.** Persist it into the corpus's `sweep_provenance.json` immediately:
```python
from mosquito_cfd.force_surrogate.acceptance_gate import record_check_result
record_check_result(
    "<corpus-dir>/sweep_provenance.json", "cc_f1",
    plotfile="<workspace-hostpath>/runs/<config>/plt00100",
    x_velocity_min=..., x_velocity_max=..., verdict="pass",
)
```
This is exactly the field the post-run acceptance gate (see "After the Sweep Completes") checks
for on a field-capture corpus — recording it here means the gate doesn't fail later for a check
that actually passed but was never written down.

**Pass the smoke config through the acceptance gate itself before spending the `full` budget --
not just the checks above.** `smoke` defaults to the corpus's CFL-worst config specifically so
this one run is the load-bearing check against a defect that a milder config's local probe can't
surface (design D4: a startup-transient-only local probe never reaches a stroke reversal, where
flapping-wing aerodynamics can exceed the impulsive-start velocities the probe does exercise --
`add-fine-corpus-run-verification` task 7.2, issue #92). Running the real acceptance gate here,
not just eyeballing the raw files, catches the same defect class Step 4's mid-sweep check and the
post-run gate catch, but before committing the other 26 configs' GPU-hours instead of after.

The acceptance gate (`check_corpus_acceptance.py`) is a **complete-corpus** check by design --
pointed at the real `sweep_manifest.json` with only 1 of N configs actually run, every other
config is correctly reported as `"no force CSV found (dropped from the corpus)"`, which would
always fail. Scope it to just the smoke config with a reduced one-config manifest instead:

1. Generate this config's metadata (not yet produced by the sweep itself):
   ```bash
   uv run python scripts/generate_run_metadata.py \
       --pod-metadata <workspace-hostpath as a local/mounted path>/runs/<config>/run_metadata.json \
       --csv <workspace-hostpath as a local/mounted path>/runs/<config>/IB_Particle_1.csv \
       --run-log <workspace-hostpath as a local/mounted path>/runs/<config>/run.log \
       --manifest <corpus-dir>/sweep_manifest.json \
       --deck <corpus-dir>/inputs/inputs.3d.<config> \
       --config-name <config> \
       --tier fine-grid-corpus-full \
       --workflow-name force-surrogate-smoke-<id> \
       --output <corpus-dir>/run_metadata_<config>.json
   ```
   (Harmless to redo later in "After the Sweep Completes" step 1, which regenerates it for all
   27 anyway -- this just produces it early for the one config being gated here.)
2. Build the reduced manifest (the full real manifest's matching entry, filtered down to one --
   not hand-retyped, so its field values can't drift from the real one):
   ```bash
   uv run python -c "
   import json
   manifest = json.load(open('<corpus-dir>/sweep_manifest.json'))
   config = next(c for c in manifest['configs'] if c['name'] == '<config>')
   json.dump({'configs': [config]}, open('<scratchpad>/smoke_manifest.json', 'w'))
   "
   ```
3. Run the gate against it, pointed at the corpus's real `sweep_provenance.json` (so it sees the
   CC-F1 result just recorded above, if this is a field-capture corpus):
   ```bash
   uv run python scripts/check_corpus_acceptance.py \
       --manifest <scratchpad>/smoke_manifest.json \
       --provenance <corpus-dir>/sweep_provenance.json \
       --csv-dir <workspace-hostpath as a local/mounted path>/runs \
       --metadata-dir <corpus-dir>
   ```
   A failure here means something is genuinely wrong with the CFL-worst config specifically --
   stop and debug before spending any of the `full` budget on the other 26; don't treat it as a
   flaky check to retry past.

## Step 3: Submit `full`

**STOP — get the user's explicit go-ahead before running this.** This is the real spend: 27
configs, multi-day, shared quota.

```bash
cluster/argo/scripts/submit_workflow.sh full --image ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST> \
    --corpus-dir <corpus-dir> --workspace-hostpath <workspace-hostpath> \
    --active-deadline-seconds 93600  # see table below -- always pass one of these two, every submission
```

`--parallelism` and `--active-deadline-seconds` are coupled (issues #63/#64's root cause — a
deadline sized for one concurrency silently deadline-kills a run at a different one) **and the
committed workflow default is margin-free even at its own concurrency**, so always pass one of
the two rows below explicitly — never submit `full` with neither flag:

| What you want | What to pass |
|---|---|
| Committed concurrency (3), but with the 4h retry margin the plain default lacks | `--active-deadline-seconds 93600` (or `--parallelism 3`, which auto-scales to the same value) |
| Different concurrency N | Either pass an explicit `--active-deadline-seconds`, or omit it and let auto-scale compute one from `N` and the manifest's real config count |
| (never do this) | Submitting with **neither** flag — silently uses the committed `86400s`/24h, which has zero retry margin |

`93600` = `ceil(27 configs × 2.4h/config ÷ 3 parallelism + 4h retry margin)`, rounded up to a
whole hour. Re-derive this from `PER_CONFIG_HOURS`/`RETRY_MARGIN_HOURS` in `submit_workflow.sh`
rather than trusting this exact number if the corpus size or those constants ever change. Whatever
you choose, **tell the user explicitly** that you're overriding the committed default and why —
don't silently substitute a computed value into the command.

## Step 4: Mid-Sweep Check — Mandatory, Do Not Skip Straight to "Wait for Completion"

**This is the entire point of this runbook.** Once just 2-3 of the 27 configs finish — not all
27, and don't wait for the DAG's own `verify-complete` node, which only runs at the very end —
gather this evidence (autonomous), then report it and wait for the user before acting on it:

1. Get the actual finished config names yourself — re-verify this even if the user reports a
   count ("3 finished") themselves; don't trust a raw phase/node count either way, it
   double-counts fan-out nodes. Dedupe by `displayName`, wrapped:
   ```bash
   cluster/argo/scripts/monitor_workflow.sh get force-surrogate-sweep-<id>
   ```
2. For each finished config, spot-check `runs/<config>/`:
   - **A quick in-run check first, on the raw `run.log`, catches truncation cheaply — before
     spending GPU-hours on the rest of the fan-out:**
     ```bash
     grep -o 'DT = [0-9.eE+-]*' runs/<config>/run.log | awk '{if ($3+0 < 0.000499) c++} END {print c+0}'
     ```
     A nonzero count means `ns.cfl` is binding below the deck's nominal `ns.fixed_dt` — the
     failure mode behind issue #92. Converts a potential ~65 GPU-h loss into ~2 GPU-h caught
     early; if this fires, stop and confirm with the user before letting the rest of the fan-out
     run (this is exactly the class of defect the acceptance gate catches post-hoc, but far
     cheaper to catch here, mid-sweep).
   - `IB_Particle_1.csv`'s **distinct-`iStep`** row count matches `sweep_manifest.json`'s
     `max_step` for that config — **not** the raw row count, which over-satisfies under
     `ns.init_iter>0` (it includes `1+init_iter` extra rows at `iStep=0` that `check_completion`'s
     `>=` threshold check doesn't distinguish from real progress).
   - `run_metadata.json`'s `interior_dt_below_nominal` is `false` and `stability` does not start
     with `cfl_limited_at_`. **`stability == "stable_at_5e-4"` alone is not a suffient check** —
     `fixed_dt` is the deck's *declared* value, not what the run actually held, so a CFL-limited
     run can still show `fixed_dt: 0.0005` in the same file. Read `stability`'s full value and
     `interior_dt_below_nominal` together.
   - **This is mid-sweep, on a partial corpus — its pass/fail semantics differ from the post-run
     acceptance gate's.** Most of the 27 configs legitimately have `reached_stop_time: false` at
     this point simply because they're still running; that is not itself a defect signal here,
     unlike in the gate below (which runs once, after every config has finished, where the same
     field means something is wrong). Don't conflate the two checks' meaning of the same field.
3. Build a partial dataset from just those configs and eyeball real force output:
   ```bash
   uv run python scripts/extract_forces.py \
       --manifest <corpus-dir>/sweep_manifest.json \
       --input-dir <workspace-hostpath as a local/mounted path>/runs \
       --allow-missing \
       --out <scratchpad>/partial_dataset.parquet \
       --units <scratchpad>/partial_dataset.units.json \
       --metadata <scratchpad>/partial_run_metadata.json \
       --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST> \
       --timestamp $(date -u +%Y-%m-%dT%H:%M:%S%z)
   ```
   `--allow-missing` skips the 24 configs that haven't finished yet instead of hard-failing. Check
   each finished config's CF_x/CF_z: no NaN/Inf, non-zero magnitude, oscillating at that config's
   own kinematic frequency.
4. **Report to the user, then wait for their go-ahead either way:**
   - Clean → propose letting the fan-out continue unattended, rechecking via `monitor_workflow.sh
     get` every few hours (background the wait, don't poll tightly).
   - Anything wrong (short/missing CSV, `_fallback` stability, NaN/zero forces) → propose
     stopping (`monitor_workflow.sh stop force-surrogate-sweep-<id>`) and debugging from that
     config's `run.log`/CSV before resubmitting anything. Don't execute the stop yourself without
     the user confirming — it's real GPU work lost, even though it's the right call once a
     corpus-wide bug looks likely.

## Step 5: Recovery if a Run Stalls or Gets Partially Killed

Trim `sweep_manifest.json` to just the missing config names, resubmit `full` against the trimmed
file (get the user's go-ahead first, same as any other `full` submission), then restore the
original:
```bash
git checkout -- <corpus-dir>/sweep_manifest.json
```
This is the exact pattern that recovered the coarse corpus's first attempt — never hand-edit the
committed manifest permanently for a partial resubmission.

## After the Sweep Completes

`verify-complete` gates overall workflow success on every config's CSV completeness — don't call
it done before that DAG node passes. Then, independently:

1. `scripts/generate_run_metadata.py` for each config — now correctly pod-scoped per the
   `fix-wall-time-pod-selection` fix (issue #65), replacing any stale committed
   `run_metadata_<config>.json` files from a superseded prior run (flagged in Step 0).
2. **Run the post-run acceptance gate — mandatory, blocks the next step.** A truncated (#92) or
   duplicated-row (#94) run must never reach a committed `dataset.parquet`:
   ```bash
   uv run python scripts/check_corpus_acceptance.py \
       --manifest <corpus-dir>/sweep_manifest.json \
       --provenance <corpus-dir>/sweep_provenance.json \
       --csv-dir <workspace-hostpath as a local/mounted path>/runs \
       --metadata-dir <corpus-dir>
   ```
   This is the **complete-corpus** check — unlike Step 4's mid-sweep check on a partial corpus,
   every config is expected to have `reached_stop_time: true` and `interior_dt_below_nominal:
   false` here; a failure means something is genuinely wrong, not merely "still running." It also
   requires a non-partial, passing CC-F1 result on a field-capture corpus — if Step 2 recorded
   one, this passes; if not, fix that first rather than treating the gate's failure as a new
   problem. Do not proceed to the next step until this passes.
3. `scripts/extract_forces.py` (no `--allow-missing` this time) → the full `dataset.parquet`.
4. Close issues #63/#64 on GitHub (this repo's convention: close once verified in practice, not
   just once the code fix merges).
5. Update `openspec/project.md`'s Pending section and the corpus's `sweep_provenance.json`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Assuming which corpus (fine vs. coarse) without asking | Always confirm with the user first (Step 0) |
| Reaching for `make_flow_video.py` mid-sweep as a substitute for Step 4 | Step 4's CSV/force check is cheaper and doesn't need a completed plotfile time series — use it as the default even for the field-capture-enabled fine corpus |
| Skipping the CC-F1 `check_plotfile_velocity.py` check on a field-capture corpus's smoke plotfile | `ns.init_iter=0` silently zeroes the velocity field with no other symptom — forces still look fine, only Stage 2 work would notice later |
| Overriding `--parallelism` without touching the deadline | They're coupled — always pass one of the two (Step 3) |
| Submitting `full` with no flags, assuming "committed default" means "safe" | It's margin-free (24h, no retry buffer) — always pass `--active-deadline-seconds` or `--parallelism` explicitly (Step 3) |
| Treating a `runai` auth error as a real cluster problem | It's usually just an expired RunAI login token — `runai login` and retry |
| Proceeding at full `--parallelism` when quota headroom is near zero | Propose a lower value to the user instead — zero headroom guarantees preemption, not a scheduling block (Step 1) |
| Trusting `argo submit --watch`'s exit code alone | Independently re-verify via `monitor_workflow.sh get` |
| Counting raw DAG phase/node counts as "N configs done" | Dedupe by `displayName` first |
| Waiting for all 27 before any check | Check at 2-3 finished configs (Step 4) — that's the whole point |
| Acting on Step 4's decision gate without the user's go-ahead | Report the finding and wait — gathering evidence is autonomous, acting on it isn't |
| Reusing a memorized `:fp64` digest | Re-pull it live every session (Step 1, item 1) |
| Not noticing stale `run_metadata_<config>.json` files from a superseded prior run | Check `sweep_provenance.json`'s `supersession_history` list before submitting (Step 0) |
| Assuming a prior pilot's stability GO transfers to this run unconditionally | Confirm geometry/grid/kinematic range hasn't changed since the pilot ran (Step 0) — a geometry change invalidates it as surely as a grid change does |
| Reading `stability == "stable_at_5e-4"` alone as proof of a healthy run | Also check `interior_dt_below_nominal` — `fixed_dt` is the deck's declared value, not what the run held (Step 4) |
| Building `dataset.parquet` straight from `extract_forces.py` after metadata generation | Run the post-run acceptance gate first — it's mandatory, not optional (After the Sweep Completes) |
| Treating a mandatory check (e.g. CC-F1) as done because you looked at the output | Record the result into `sweep_provenance.json` — an unrecorded check is indistinguishable from one never run (Step 2) |

## Related Commands

- `/validate-env` — confirms the local Python/Docker/GPU dev environment only; does **not** check
  cluster/RunAI/KUBECONFIG readiness (see `openspec/runai-dev-workflow.md` for that)
- `/new-feature` — if the mid-sweep check (or anything else) surfaces a real code bug
