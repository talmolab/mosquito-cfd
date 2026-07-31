# Design: fine-grid training-data pilot

Full discussion, alternatives considered, and the cost derivation live in
`docs/superpowers/specs/2026-07-28-fine-grid-training-data-pilot-design.md` (reviewed and
approved with the user before this OpenSpec change was scaffolded). This file is the condensed,
OpenSpec-native summary.

## D1 — Reuse `generate_sweep()` unmodified; don't add a resolution parameter to it

`generate_sweep()` already accepts `base_inputs_path` as a parameter. Pointing it at a new fine
base deck requires zero code changes. Adding a formal `--resolution` flag or similar to the
sweep API would be premature — we don't yet know fine-grid is CFL-stable across this sweep's
kinematic range, and touching the code path that produces the tested, frozen coarse corpus for
an unproven capability is the wrong order of operations.

## D2 — New base deck, new output directory; never touch the frozen corpus

`examples/prelim_sweep/base_inputs.3d.validation` is explicitly frozen by the original Track B
design ("templates off the byte-identical snapshot so it is never regenerated"). The pilot's
base deck (`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`) and generated pilot decks
live in a sibling directory, `examples/prelim_sweep_fine_pilot/`, so there is no risk of
mixing pilot artifacts into the frozen coarse corpus or its manifest.

## D3 — `ns.fixed_dt` starts at the sweep's standard `5e-4`, not a pre-emptive `2.5e-4` fallback

The only fine-grid run to date (the flapping-wing validation deck: stroke=70°, f*=1.0) needed
the `5e-4 → 2.5e-4` CFL fallback. But every one of this sweep's 27 configs has a **lower**
stroke×frequency product (max `55°×1.15=63.25` vs. the validated case's `70×1.0=70`), so it is
a genuinely open question whether the fallback is needed here at all — worth testing rather
than assuming, since skipping it (if stable) roughly halves the pilot's total cost.

## D4 — Pilot config selection: 3 configs, highest-Reynolds-first

| Order | Config | Re | f* | `max_step` @ dt=5e-4 (`n_wingbeats=2`) | Est. wall time @ 7.909 s/step (T3c-measured rate) |
|---|---|---|---|---|---|
| 1 | `s55_f115_p45` | 90.47 | 1.15 | 3,478 | ~7.6 h |
| 2 | `s45_f100_p45` | 64.37 | 1.00 | 4,000 | ~8.8 h |
| 3 | `s35_f085_p45` | 42.55 | 0.85 | 4,706 | ~10.3 h |

Pitch is held at 45° across all 3 to isolate the stroke×frequency (CFL-driving) axis.
`max_step = round(n_wingbeats / f* / dt)`, the existing `derive_run_duration` formula,
unchanged. Order is highest-Reynolds-first specifically because config 1 is closest to the
already-known-CFL-marginal validated case: if it's stable, the other two almost certainly are
too; if it's not, we learn that fastest rather than last.

Total serial estimate: **~26.8 h** if no config needs the fallback; **~53.5 h** if all 3 do.
The `s/step` rate is carried over from the flapping-wing validation deck's measured T3c rate
(same solver, same physics, different sweep-config kinematics) — getting the *real* rate for
this deck is one of the pilot's explicit goals, so treat the estimate as provisional.

## D5 — Serial execution, one GPU at a time (per explicit user choice)

Rejected parallel execution in favor of serial: lower risk, never has more than 1 GPU committed
from the `talmo-lab` RunAI quota at once, and allows aborting after any config that looks wrong
before committing more cluster time. (An earlier draft of this section cited a specific "~18-20h"
parallel-execution estimate; that number wasn't derived from anything and was arithmetically
questionable — parallel wall-clock should be bounded by the slowest single config, ~10.3h, not
18-20h. Dropped rather than fixed, since the decision doesn't depend on the parallel option's
exact cost — serial was chosen for risk/quota reasons, not because parallel was measured and
found slower.) Submission uses the existing `cluster/argo/scripts/submit_workflow.sh smoke`
command — already built for "submit one config via the template" — with `SMOKE_CONFIG_NAME` /
`SMOKE_INPUT_FILE` / `SMOKE_MAX_STEP` / `WORKSPACE_HOSTPATH` overridden per pilot config.

## D5a — Submission is detached, not a blocking wait (revised after review)

`submit_workflow.sh smoke` invokes `argo submit ... --watch`, which **blocks until the workflow
reaches a terminal state** — for an estimated 7.6-20.6h single-config run, that is not something
to invoke as a normal, waited-on foreground command; the tool environment's own call-timeout
ceiling (10 minutes) would trip long before the run finishes. The actual submission pattern is:

1. Submit with the streaming/log-following behavior disabled or run in a detached/background
   mode (e.g. `nohup ... &` under WSL, or the tool environment's own background-execution
   option) — the goal is only to POST the workflow object to the cluster; the workflow then
   runs independent of whether the submitting process (or the whole conversation session) is
   still alive.
2. Confirm the workflow object was accepted (`cluster/argo/scripts/monitor_workflow.sh get
   <name>`) and do a *short* initial check — not by tailing solver output (see D6 below, which
   doesn't show live diagnostics anyway), but by confirming the pod reaches `Running` phase and
   stays there past the first few minutes (an immediate crash-on-launch shows up as an early
   phase transition out of `Running`).
3. Everything after that is a **separate, later check-in** — potentially in a different
   conversation/session, hours or a day later — via `monitor_workflow.sh get/logs <name>`. Do
   not hold a tool call, task, or session open waiting out the full run duration.

## D5b — Preemption risk is real and needs an explicit decision, not silence

The single-config pod template uses `priorityClassName: interactive-preemptible` (class 75 —
genuinely preemptible on the shared `talmo-lab` GPU quota) with a 5-attempt retry
(`retryStrategy`, `retryPolicy: OnFailure`). `run_one_config.py` has **no checkpoint/restart**
capability (it always runs the deck from `t=0`, and the fine deck almost certainly has
`amr.check_int` disabled the way the T3c deck did) — so a pod evicted mid-run does not resume;
the retry restarts from step 0, silently discarding all prior wall-clock progress. Combined with
the workflow's `activeDeadlineSeconds: 86400` (24h hard kill), a single preemption partway
through the longest pilot config's fallback estimate (~20.6h) could push the total past the 24h
ceiling with no advance warning.

**Decision**: accept this risk for the pilot (3 small, individually-abortable, serially-run
configs — the blast radius of one bad restart is at most one config's wall time, not the whole
pilot), rather than requesting a non-preemptible priority class or a longer deadline for what is
explicitly exploratory, cluster-time-bounded work. If a config's wall time during the actual
pilot run comes in far above the estimate, check whether preemption/restart was the cause
(`monitor_workflow.sh get <name>` shows retry count) before concluding the kinematic regime
itself is more CFL-demanding than expected.

## D6 — Divergence detection and handling mirrors the T3c precedent, and is a finding, not a bug

**Revised after review**: `run_one_config.py` invokes the solver via
`subprocess.run(..., capture_output=True)`, which buffers all stdout/stderr internally and only
writes it to `run.log` after the process exits. Tailing the pod log (`argo logs --follow` /
`kubectl logs -f`) during the run will **not** show live solver diagnostics — an earlier version
of this design said to "watch the pod log for blow-up/NaN," which doesn't work given this
buffering. The two signals that actually are observable live:

- **Pod phase**: an early divergence-driven crash exits the solver (and the wrapping subprocess)
  quickly, so `monitor_workflow.sh get <name>` / `kubectl get pods` shows the pod leaving
  `Running` well before the multi-hour estimate — check this at the ~10-15 minute mark (D5a
  step 2), not by reading log content.
- **Force-CSV row growth**: `IB_Particle_1.csv` (or the configured `csv_name`) is written
  incrementally to the NFS-mounted run directory; a stalled or non-growing row count past the
  first checkpoint interval is a secondary health signal, checkable without waiting for the pod
  to exit.

Handling: if a config diverges at `dt=5e-4` (detected via either signal above, or discovered at
a later check-in): apply the same fallback T3c used (`ns.fixed_dt = 2.5e-4`, `max_step` doubled)
and re-submit, recording that this config needed it. If a config is still unstable even at
`2.5e-4`: stop (`monitor_workflow.sh stop <name>` to free the GPU), do not attempt a further
speculative fallback — record it as a genuine "unstable at this kinematic range" finding in the
pilot report, and commit any partial force-CSV/log artifacts as evidence rather than silently
discarding them.

## D7 — Deliverables and their test surface

Because this is operator-run (real cluster time), there is no unit-test surface for the actual
CFD execution — the "test" is the pilot itself. What *is* testable and cluster-free:

- A deck-invariance guard (mirrors `tests/test_convergence_deck.py`'s existing
  coarse↔medium↔fine pattern): `base_inputs.3d.fine` must be an exact copy of
  `examples/prelim_sweep/base_inputs.3d.validation` except `amr.n_cell`.
- A **static** path-inequality assertion that the pilot's `WORKSPACE_HOSTPATH`/output directory
  constant is not the coarse corpus's path — checked without ever actually invoking generation
  against the real frozen-corpus path (see D-note below on why a live re-execution test is
  unsafe).
- A schema/provenance pin test for the committed pilot `run_metadata_*.json` files (mirrors
  `tests/test_wing_convergence_fine.py`'s pattern), parametrized per config (not a single
  function with an internal skip loop, which would stop checking later configs once it hits a
  missing one) — `skipif` per config until that config's data exists (Session A vs. Session B
  split, same pattern as `add-wing-fine-grid-convergence`).
- A pilot-report structural check (`skipif` the report doesn't exist yet): each of the 3 config
  names appears alongside one of the three stability tokens (`stable_at_5e-4` /
  `stable_at_2.5e-4_fallback` / `unstable`) and a numeric wall-time/`s_per_step` figure.

**Note on the isolation-guard test's design**: an earlier draft of this test ran the pilot
generation script for real and hashed `examples/prelim_sweep/` before/after. That's unsafe as a
repeatable automated test: pointed at a safe path, it never proves anything (vacuous); pointed at
the script's real default paths to actually catch a typo, a wrong default could trigger
`generate_sweep()`'s stale-deck-pruning logic and delete the 27 committed coarse decks before the
test could report failure. The fix is to assert the output-directory *constant* is correct
statically (import it, compare the string/Path, never execute generation against the coarse
path), and treat the one-time hash-before/after check as a passive, manual sanity check performed
once during the real (non-repeated) operator run — not something CI re-triggers every run.

## Open questions — resolved

- **NFS staging path**: pinned, not left open —
  `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine_pilot` (mirrors the
  existing pattern for `flapping_wing/` and `prelim_sweep/` exactly; staged from
  `Z:\users\eberrigan\mosquito-cfd\examples\prelim_sweep_fine_pilot\`). This is a hard dependency
  for all of Phase 2 (nothing in Phase 2 can run without it), so it is resolved here rather than
  left as a skippable task.
- **GPU VRAM (`amrex.the_arena_init_size`)**: T3c's actual A5000 run used **18 GiB** (on a 24 GB
  card); the separate A40 cluster deck recommends **28 GiB** as its arena cap (a different piece
  of hardware — these two numbers are not a range on the same GPU, correcting an error in an
  earlier draft of this document that read "18-28 GiB on a 24 GB A5000," which is impossible).
  The RunAI A40s have 48 GB VRAM, so 28 GiB should have headroom; confirm on the first
  submission via `nvidia-smi`/pod describe rather than assuming.
- **Pod system memory (a distinct concern from GPU VRAM)**: the single-config pod template
  requests/limits **Kubernetes-enforced host RAM** (`memory: 32Gi` limit), separate from GPU
  VRAM. Fine 256×128×256 is ~64× the coarse grid's cell count, and AMReX host-side bookkeeping
  (MultiFab metadata, staging buffers, particle structures) plausibly scales with cell count too
  — this was not previously asked as its own question. Bump the pod's `memory` limit for the 3
  pilot submissions (e.g. to `64Gi`; cheap insurance, A40 nodes should have host-RAM headroom) to
  avoid discovering a host-RAM OOMKill (a distinct failure mode from GPU OOM) several hours into
  a run.
- **Image digest**: `submit_workflow.sh` hard-fails (`require_image`) without `--image`/
  `FP64_IMAGE` pinned by `@sha256:`. Since this proposal makes no code changes, the currently
  tagged `:fp64` digest (the one already used for the original 27-config coarse sweep) should
  already contain `run_one_config` and be safe to reuse — confirm this rather than triggering an
  unnecessary fresh merge/build, and record the exact digest used in each pilot config's
  `run_metadata_*.json` (already an existing field).
