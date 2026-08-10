# Fine-grid training-data pilot — report

OpenSpec change `add-fine-grid-training-pilot`. Reports the outcome of the 3-config pilot at
fine 256×128×256 resolution, run serially on the Salk RunAI `talmo-lab` cluster, per
`design.md`'s go/no-go framing: is fine-grid CFD stable across this sweep's kinematic range at
the standard `dt=5e-4`, and what does that mean for the cost of regenerating the full 27-config
corpus at fine resolution?

This pilot collects raw force CSVs only — it does **not** extract force coefficients or compare
against the QS-model target. The `CF_chord`/`CF_normal` grid-convergence numbers that motivate
this pilot (coarse +115%, fine ~4-5% off target) are already published in the T3c row of
`docs/aerodynamics_validation/roadmap.md` (`CF_chord`: 0.923 coarse → 0.554 medium → 0.411 fine)
and are not restated here.

> **Geometry note (`fix-force-surrogate-sweep-hinge`, 2026-08-10):** the base deck this pilot ran
> from (`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`) carried a wing-hinge geometry
> defect (a midspan pivot, not a root hinge) since the 2026-07-02 axis-convention refactor. That
> fix is orthogonal to **this report's own finding** — the `dt=5e-4` numerical-stability result is
> a property of the rigid-body pivot's motion smoothness, not its placement, and is not affected —
> but the raw force magnitudes in the committed `forces_<config>.csv` files reflect the buggy
> geometry and should not be trusted for anything beyond the stability go/no-go this report makes.

## Per-config results

| Config | Re | f* | max_step | Stability | Wall time | s/step | Retries |
|---|---|---|---|---|---|---|---|
| `s55_f115_p45` | 90.47 | 1.15 | 3478 | `stable_at_5e-4` | 7032.46 s (1.95 h) | 2.021984 | 0 |
| `s45_f100_p45` | 64.37 | 1.00 | 4000 | `stable_at_5e-4` | 8002.88 s (2.22 h) | 2.000719 | 0 |
| `s35_f085_p45` | 42.55 | 0.85 | 4706 | `stable_at_5e-4` | 9448.47 s (2.62 h) | 2.007749 | 0 |

Provenance: `examples/prelim_sweep_fine_pilot/run_metadata_<config>.json` (schema matches
`run_metadata_t3c.json`: git/docker/hardware/timing — this is these 3 files' as-committed,
pre-normalization schema; `automate-run-metadata-capture` normalizes the schema for future runs,
but does not retrofit these 3) + `examples/prelim_sweep_fine_pilot/forces_<config>.csv`
(the committed `IB_Particle_1.csv`, verified against the pinned 29-column IB-particle schema).
Cluster: RunAI `talmo-lab`, image `ghcr.io/talmolab/mosquito-cfd@sha256:f546ead9afd9bf490cdc2b255ed0a254f4079262ea6cd4b3d1d7e6c86b0f286a`
(the current post-merge `:fp64`; no fresh build needed per `design.md`'s "no code changes"
non-goal), all 3 configs landed on `gpu-node14` (NVIDIA A40, 46068 MiB).

## Stability: no CFL fallback needed for any config

All 3 configs completed at the sweep's standard `ns.fixed_dt = 5e-4` — **none needed the
`2.5e-4` fallback** that the validated flapping-wing deck (stroke=70°, f*=1.0) required. This
answers `design.md` D3's open question: every one of this sweep's 27 configs has a lower
stroke×frequency product than the validated case (max `55°×1.15=63.25` vs. `70×1.0=70`), and the
pilot confirms this lower CFL-driving product is enough to stay stable at the full timestep
across the pilot's tested range (highest-Reynolds-first: `s55_f115_p45` submitted first
specifically to learn this fastest, per `design.md` D4 — it was stable, so the remaining two
lower-Re configs were expected to be stable too, and were).

`s35_f085_p45`'s final step shows a truncated `DT = 0.0004411765` (vs. `0.0005` for the other
4705 steps) — this is **not** a CFL/divergence response. `max_step × dt` (`4706 × 0.0005 =
2.353`) slightly overshoots `stop_time` (`2.352941176...`) because of the `round()` in
`derive_run_duration`; AMReX clamps the final step to land exactly on `stop_time`. Confirmed by
grepping every `DT =` value in that config's `run.log`: 4705 steps at `0.0005`, 1 at
`0.0004411765`.

No preemptions: all 3 configs show `retry: "0"` in their `run_metadata_*.json`'s
`orchestration` block, despite `talmo-lab`'s RunAI quota sitting at 171.74% allocation
(34.35/20.00 GPUs) at submission time — the `interactive-preemptible` priority class accepted
risk (`design.md` D5b) did not materialize into an actual eviction for any of the 3 runs. GPU
VRAM was not independently confirmed via `nvidia-smi` (the Argo service account lacks
`pods/exec` RBAC in `runai-talmo-lab`); AMReX's own end-of-run report shows `The Arena` max used
7998 MiB against a 46068 MiB card for all 3 configs — comfortable headroom. Host RAM (the
32Gi→64Gi pod-memory bump, `770847b`) was not observably a bottleneck either.

## Cost projection for the full 27-config corpus

The measured per-step cost is essentially **constant across configs** (2.00–2.02 s/step, mean
**2.010151 s/step**) despite `max_step` varying with frequency — the grid resolution and AMR
settings are identical across the sweep; only the prescribed kinematics differ, and that does not
change the per-step compute cost. This means the total cost projects linearly from `max_step`
alone, independent of stroke/pitch (which don't appear in `derive_run_duration`):

- `max_step(f*) = round(4000 / f*)`: `f*=0.85 → 4706`, `f*=1.00 → 4000`, `f*=1.15 → 3478`.
- The full 27-config grid has 3 stroke × 3 pitch = **9 configs per frequency level**, so total
  steps = `9 × (4706 + 4000 + 3478) = 9 × 12184 = 109656` steps.
- Projected total wall time = `109656 × 2.010151 s ≈ 220425 s ≈ 61.2 hours ≈ 2.55 days`
  (serial, 1 GPU at a time — matches the pilot's own execution policy, `design.md` D5).

This is dramatically cheaper than the design-time estimate used to scope the pilot itself
(**~26.8–53.5 hours for just 3 configs**, extrapolated from the T3c flapping-wing deck's
7.909 s/step): the actual fine-grid sweep-config rate (~2.01 s/step) is **~3.9× faster** than
that carried-over estimate. The T3c deck's `s_per_step` came from a different kinematic point
(stroke=70°, f*=1.0, a locally-patched IAMReX build on a different GPU); the pilot's own
measurement, on the actual sweep decks and the actual `:fp64` cluster image, supersedes it as
the basis for planning the full regeneration.

## Go/no-go recommendation: **GO**

All 3 pilot configs — spanning the sweep's full kinematic range at 45° pitch — completed cleanly
at the standard `dt=5e-4` with no divergence, no CFL fallback, and no preemption. The measured
cost for the full 27-config corpus at fine 256×128×256 resolution is **~61 hours (~2.55 days)**
of serial single-A40 wall time, a small, bounded, single-lab-quota-scale job — not the ~20-day
worst case that motivated running this pilot before committing.

**Recommendation:** proceed with a follow-on change to regenerate the full 27-config corpus at
fine resolution (explicitly deferred here per `proposal.md`'s non-goals — this pilot does not
itself regenerate the corpus, modify `sweep.py`, or retrain the surrogate). Given the ~2.55-day
serial cost, that follow-on should reconfirm current RunAI quota headroom and preemption
exposure before committing the full run, and should budget for the possibility that a
config outside this pilot's tested pitch level (30°/60°, not just the pilot's 45°) needs the
CFL fallback — this pilot did not vary pitch, since pitch is not a CFL-driving parameter in
`derive_run_duration`, but it also was not empirically tested at the other 2 pitch levels.

**Caveat: the preemption/retry path itself is unexercised, not just unobserved.** All 3 pilot
configs show `retry: "0"` — genuinely no preemption occurred — but that means whether a
Run:ai-preempted pod actually surfaces to Argo as a retryable `Failed` (picked up by the
`retryStrategy`'s `retryPolicy: OnFailure`) versus a non-retried `Error` has never been
empirically confirmed, by this pilot or the earlier coarse 27-config run. Given the follow-on's
~61-hour exposure on a cluster already over its non-preemptible GPU quota, this is worth
validating (e.g. a deliberate test eviction) before relying on the retry path for real.
