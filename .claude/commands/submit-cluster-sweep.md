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

**Every deck in both corpora forces `amr.plot_int = -1`** (force-only design, `generate_sweep()` /
`openspec/specs/force-surrogate/spec.md`) — neither corpus is designed to produce a time series
of AMReX plotfiles. Don't reach for `make_flow_video.py`/`make_kinematics_video.py`'s multi-frame
workflow mid-sweep; it needs exactly the kind of output these decks don't produce. Use Step 4's
CSV/force-based check instead.

**Stale committed metadata warning** — before submitting anything, check whether
`<corpus-dir>/run_metadata_<config>.json` files already exist from a prior, superseded run (see
that corpus's `sweep_provenance.json`'s `superseded_by` field, if present). Flag this to the user;
if the new run fails partway, stale pre-fix and fresh post-fix files are otherwise indistinguishable
by filename alone until someone diffs `workflow_uid`/`pod` fields inside them.

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
   - `IB_Particle_1.csv` row count matches `check_completion`'s expectation for that config's
     `max_step` (from `sweep_manifest.json`) — see `check_completion` in
     `src/mosquito_cfd/force_surrogate/runner.py`.
   - `run_metadata.json`'s `stability` field is exactly `stable_at_5e-4` — a `_fallback` suffix
     means an emergency CFL dt-reduction happened, worth knowing before more configs hit the
     same wall.
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
2. `scripts/extract_forces.py` (no `--allow-missing` this time) → the full `dataset.parquet`.
3. Close issues #63/#64 on GitHub (this repo's convention: close once verified in practice, not
   just once the code fix merges).
4. Update `openspec/project.md`'s Pending section and the corpus's `sweep_provenance.json`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Assuming which corpus (fine vs. coarse) without asking | Always confirm with the user first (Step 0) |
| Reaching for `make_flow_video.py` mid-sweep | These corpora aren't designed to produce plotfile time series — use Step 4's CSV/force check instead |
| Overriding `--parallelism` without touching the deadline | They're coupled — always pass one of the two (Step 3) |
| Submitting `full` with no flags, assuming "committed default" means "safe" | It's margin-free (24h, no retry buffer) — always pass `--active-deadline-seconds` or `--parallelism` explicitly (Step 3) |
| Treating a `runai` auth error as a real cluster problem | It's usually just an expired RunAI login token — `runai login` and retry |
| Proceeding at full `--parallelism` when quota headroom is near zero | Propose a lower value to the user instead — zero headroom guarantees preemption, not a scheduling block (Step 1) |
| Trusting `argo submit --watch`'s exit code alone | Independently re-verify via `monitor_workflow.sh get` |
| Counting raw DAG phase/node counts as "N configs done" | Dedupe by `displayName` first |
| Waiting for all 27 before any check | Check at 2-3 finished configs (Step 4) — that's the whole point |
| Acting on Step 4's decision gate without the user's go-ahead | Report the finding and wait — gathering evidence is autonomous, acting on it isn't |
| Reusing a memorized `:fp64` digest | Re-pull it live every session (Step 1, item 1) |
| Not noticing stale `run_metadata_<config>.json` files from a superseded prior run | Check `sweep_provenance.json`'s `superseded_by` field before submitting (Step 0) |

## Related Commands

- `/validate-env` — confirms the local Python/Docker/GPU dev environment only; does **not** check
  cluster/RunAI/KUBECONFIG readiness (see `openspec/runai-dev-workflow.md` for that)
- `/new-feature` — if the mid-sweep check (or anything else) surfaces a real code bug
