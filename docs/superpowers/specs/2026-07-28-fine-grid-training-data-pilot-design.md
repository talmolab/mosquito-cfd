# Fine-grid training-data pilot — design

**Date:** 2026-07-28
**Status:** SUPERSEDED by `openspec/changes/add-fine-grid-training-pilot/` (or its archived
location post-merge). This file is historical discussion only — it captures the original
brainstorming and is retained for that context, but is **not maintained**. Do not update it;
update the OpenSpec change's `proposal.md`/`design.md`/`tasks.md` instead. A subsequent
5-agent review of the OpenSpec change found and fixed several errors that were present in this
document when it was written (an unsourced parallel-execution time estimate, a factual error
about GPU memory usage on the A5000 vs. A40, and an execution plan that didn't account for
`argo submit --watch` blocking or for preemptible-pod retry-from-scratch risk) — treat the
OpenSpec change as authoritative wherever the two disagree.

## Why

Track B's force-surrogate training corpus (`examples/prelim_sweep/`, 27 configs, committed,
tests passing) was generated entirely on the **coarse 64×32×64 grid**
(`base_inputs.3d.validation`, confirmed: `amr.n_cell = 64 32 64`). The T3b/T3c grid-convergence
work (this repo, merged) showed that grid is badly under-resolved for `CF_chord`:

| Grid | CF_chord | vs. QS-model target (~0.43) |
|---|---|---|
| Coarse (current corpus) | 0.923 | +115% |
| Medium 128³ | 0.554 | +29% (GCI band 0.28–0.83 — still not trustworthy) |
| Fine 256³ | 0.411 | ~4–5% — close agreement |

`CF_normal` is comparatively well-behaved even at medium (only -4.5% medium→fine), but the
surrogate is trained on both components, and chord is badly wrong at the corpus's current
resolution. Fine 256³ is the resolution our own validation work says is actually needed —
medium is an improvement but does not reach a trustworthy regime for chord.

Regenerating the full 27-config corpus at fine resolution is a large, unproven undertaking:
fine-grid CFD has only ever been run once, locally, for a single config (the flapping-wing
validation case), and needed a manual CFL/dt fallback (`5e-4` → `2.5e-4`) to stay stable. The
other 26 sweep configs span a different, generally lower-demand kinematic range (stroke
35–55°, f* 0.85–1.15 vs. the validated case's 70°/1.0), so it is not known whether they need
the same fallback, and a serial 20-day cluster job is the wrong place to discover a stability
problem on day 8.

**This spec covers a pilot only**: 3 configs, to establish (a) whether fine-grid at this
kinematic range is CFL-stable at the sweep's standard `dt=5e-4`, and (b) a real, measured
cost estimate for the full 27-config regeneration — before committing cluster time to it.

## Non-goals

- Regenerating all 27 configs. Explicitly deferred pending this pilot's outcome.
- Modifying `src/mosquito_cfd/force_surrogate/sweep.py`. It already accepts `base_inputs_path`
  as a parameter — no code change needed for a pilot at a different resolution.
- Touching `examples/prelim_sweep/` (the frozen, byte-identical coarse corpus — a deliberate
  reproducibility guarantee per the original Track B design, "never regenerated").
- Re-training the surrogate on any new data. Out of scope until the full corpus (if pursued)
  is committed.

## Design

### New artifacts

- `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` — a byte-for-byte clone of the frozen
  `examples/prelim_sweep/base_inputs.3d.validation`, with exactly one field changed:
  `amr.n_cell = 256 128 256` (was `64 32 64`). `ns.fixed_dt` starts at `5e-4`, unchanged from
  the coarse base — **not** pre-emptively dropped to `2.5e-4`. This is a genuinely new
  question (this kinematic range is lower-demand than the validated case that needed the
  fallback), and the whole point of the pilot is to test it empirically rather than assume.
- A short, one-off pilot-generation script (not a permanent library function) that calls the
  existing, unmodified `generate_sweep()`:
  ```python
  generate_sweep(
      base_inputs_path="examples/prelim_sweep_fine_pilot/base_inputs.3d.fine",
      output_dir="examples/prelim_sweep_fine_pilot",
      timestamp=<caller-supplied ISO-8601>,
      configs=[PILOT_CONFIGS],  # the 3 configs below
      n_wingbeats=2,            # matches N_WINGBEATS, the sweep's standard duration
      dt=5e-4,
  )
  ```
  This reuses the tested, unmodified sweep machinery (manifest, provenance sidecar,
  deterministic deck rendering) rather than hand-rolling deck edits.

### Pilot configs (highest-Reynolds-first)

Picked to span the sweep's full Reynolds range at a fixed pitch (45°) to isolate the
stroke×frequency (CFL-driving) axis, run in this order specifically because config 1 is
closest to the already-known-CFL-marginal validated case — if it's stable, the other two
almost certainly are too, and if it's not, we learn that fastest:

| Order | Config | Re | f* | `max_step` @ dt=5e-4 | Est. wall time @ 7.909 s/step |
|---|---|---|---|---|---|
| 1 | `s55_f115_p45` | 90.47 | 1.15 | 3,478 | ~7.6 h |
| 2 | `s45_f100_p45` | 64.37 | 1.00 | 4,000 | ~8.8 h |
| 3 | `s35_f085_p45` | 42.55 | 0.85 | 4,706 | ~10.3 h |

(`max_step = round(n_wingbeats / f* / dt)`, per `derive_run_duration` — unchanged formula.)
Total serial, best case (no CFL fallback needed): **~26.8 hours**. If all 3 need the
`dt=2.5e-4` fallback (doubled `max_step`): **~53.5 hours**. Real numbers will differ — this
pipeline's `s/step` was measured on the flapping-wing validation deck, not this sweep's deck,
which is the pilot's job to actually measure.

### Execution

Serial, one GPU at a time (per user's explicit choice — lower risk than 3-GPU parallel, can
abort after any config that looks wrong before committing more cluster time):

1. Submit config via the existing `cluster/argo/scripts/submit_workflow.sh smoke` command
   (already built for "submit one config via the template" — no new Argo tooling needed),
   with `SMOKE_CONFIG_NAME` / `SMOKE_INPUT_FILE` / `SMOKE_MAX_STEP` overridden per config, and
   `WORKSPACE_HOSTPATH` pointed at the new `prelim_sweep_fine_pilot` directory (never the
   frozen corpus's path).
2. Watch the pod log for the first ~10–15 minutes for immediate blow-up/NaN signatures before
   committing to the full multi-hour wait.
3. Let it run to completion, OR if it diverges: apply the T3c precedent (`ns.fixed_dt = 2.5e-4`
   at runtime, `max_step` doubled) and re-submit — recording that this config needed the
   fallback (itself a useful data point about which regimes are CFL-limited at fine
   resolution).
4. Record wall time, `s/step`, and stability outcome (stable at 5e-4 / needed fallback /
   unstable even at 2.5e-4) per config before moving to the next.

### Deliverables

- Committed `run_metadata_*.json` per pilot config (git/docker/hardware/timing — same schema
  as `run_metadata_t3c.json`).
- A short pilot report, same shape as `docs/aerodynamics_validation/t3c-handoff.md`: per-config
  stability/timing table, a real (measured, not estimated) cost projection for the full
  27-config fine-grid corpus, and a go/no-go recommendation.
- The 3 fine-grid force CSVs + decks, committed under `examples/prelim_sweep_fine_pilot/`.

### Error handling

- If a config diverges even after the `2.5e-4` fallback: stop, do not attempt a second
  fallback speculatively. Record it as "unstable at this kinematic range" in the pilot report
  and treat it as a real finding, not a bug to route around.
- If the pod is preempted (the workflow already uses `interactive-preemptible` priority with a
  retry strategy — a pre-existing, tested behavior, not new to this pilot): let the existing
  retry handle it; only escalate if a config fails to complete after retries.

### Testing

This is an operator-run pilot (real cluster time, real GPU-hours), not cluster-free library
code — there is no unit-test surface beyond what `generate_sweep()` already has tested. The
"test" is the pilot itself: does it run stably, and what does it cost. The deck-generation
script should be reviewed for correctness (right base deck, right configs, right `dt`) before
submission, since a mistake here wastes real cluster hours.

## Open questions for the implementation plan

- Exact mechanics of getting `prelim_sweep_fine_pilot/` onto the NFS path the Argo workflow
  mounts (mirrors the existing Z:\ drive → NFS pattern used for `flapping_wing/` and
  `prelim_sweep/`).
- Whether `amrex.the_arena_init_size` needs adjusting for this deck (T3c used 18–28 GiB on an
  A5000 for the validated-case fine grid; the RunAI cluster's A40s have 48 GB, should have
  headroom, but worth confirming before the first submission).
