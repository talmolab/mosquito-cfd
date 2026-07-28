## Why

Track B's force-surrogate training corpus (`examples/prelim_sweep/`, 27 configs, committed,
tests passing) was generated entirely on the **coarse 64×32×64 grid**
(`base_inputs.3d.validation`: `amr.n_cell = 64 32 64`). The T3b/T3c grid-convergence work
(`add-wing-grid-convergence` / `grade-wing-grid-convergence-medium` / T3c, all merged) showed
that grid badly under-resolves `CF_chord`:

| Grid | CF_chord | vs. QS-model target (~0.43) |
|---|---|---|
| Coarse (current corpus resolution) | 0.923 | +115% |
| Medium 128³ | 0.554 | +29% (GCI band 0.28–0.83 — still not trustworthy) |
| Fine 256³ | 0.411 | ~4–5% — close agreement |

`CF_normal` is comparatively well-behaved even at medium (only -4.5% medium→fine), but the
surrogate trains on both components, and chord is badly wrong at the corpus's current
resolution. Fine 256³ is the resolution our own validation work shows is actually needed —
medium is an improvement but does not reach a trustworthy regime for chord.

Regenerating the full 27-config corpus at fine resolution is large and unproven: fine-grid CFD
has only ever run once, locally, for a single config (the flapping-wing validation deck itself,
stroke=70°/f*=1.0), and needed a manual CFL/dt fallback (`5e-4` → `2.5e-4`) to stay stable. The
sweep's 27 configs span a different, generally lower-demand kinematic range (stroke 35–55°, f*
0.85–1.15), so it is not known whether they need the same fallback — and a serial ~20-day
cluster job to regenerate all 27 is the wrong place to discover a stability problem on day 8.

## What Changes

This proposal covers a **pilot only**: 3 configs, run serially on the RunAI cluster we already
have access to (no grant/new hardware needed), to establish (a) whether fine-grid CFD is
CFL-stable across this sweep's kinematic range at the standard `dt=5e-4`, and (b) a real,
measured cost estimate for the full 27-config regeneration — before committing cluster time to
it.

- Add `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`: a byte-for-byte clone of the
  frozen `examples/prelim_sweep/base_inputs.3d.validation`, differing only in `amr.n_cell`
  (`64 32 64` → `256 128 256`). `ns.fixed_dt` starts at `5e-4`, unchanged — the fallback is
  applied only if a config actually diverges, not pre-emptively.
- Generate 3 pilot decks (highest-Reynolds-first: `s55_f115_p45`, `s45_f100_p45`,
  `s35_f085_p45`) by calling the existing, **unmodified**
  `mosquito_cfd.force_surrogate.sweep.generate_sweep()` against the new fine base deck and a
  new output directory — no changes to `sweep.py` itself.
- Submit each config serially via the existing `cluster/argo/scripts/submit_workflow.sh smoke`
  command (already built for "submit one config via the template") against a new,
  pilot-specific workspace path — never the frozen `examples/prelim_sweep/` corpus.
- Commit per-config `run_metadata_*.json`, the fine-grid force CSVs, and a pilot report with a
  real cost projection and a go/no-go recommendation for the full 27-config regeneration.

## Non-goals

- Regenerating all 27 configs. Explicitly deferred pending this pilot's outcome (a follow-on
  change, if the pilot recommends proceeding).
- Modifying `src/mosquito_cfd/force_surrogate/sweep.py`. It already accepts `base_inputs_path`
  as a parameter — no code change needed to point it at a different-resolution base deck.
- Touching `examples/prelim_sweep/` (the frozen, byte-identical coarse corpus — a deliberate
  reproducibility guarantee from the original Track B design: "never regenerated").
- Re-training the surrogate on any new data.
- Adding a formal "resolution" concept to the sweep API. Premature until fine-grid is proven
  viable at cluster scale across this kinematic range.

## Impact

- Affected specs: `force-surrogate` (adds a small pilot-scoped capability: a fine-grid base
  deck invariant, reproducible pilot-deck generation, and committed pilot results with a
  go/no-go recommendation).
- Affected code: none (`sweep.py`, the Argo templates, and `submit_workflow.sh` are all reused
  unmodified).
- New data: `examples/prelim_sweep_fine_pilot/` (decks, force CSVs, run metadata, pilot report).
- Cluster cost: ~27–54 GPU-hours on the Salk RunAI `talmo-lab` project (serial, 1 GPU at a
  time; see `design.md` for the per-config estimate and why the range is wide).

See `docs/superpowers/specs/2026-07-28-fine-grid-training-data-pilot-design.md` for the full
design discussion (already reviewed and approved with the user) and `design.md` in this
directory for the condensed architectural summary.
