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

Rejected 3-GPU parallel execution (faster wall-clock, ~18-20h) in favor of serial: lower risk,
never has more than 1 GPU committed from the `talmo-lab` RunAI quota at once, and allows
aborting after any config that looks wrong before committing more cluster time. Submission
uses the existing `cluster/argo/scripts/submit_workflow.sh smoke` command — already built for
"submit one config via the template" — with `SMOKE_CONFIG_NAME` / `SMOKE_INPUT_FILE` /
`SMOKE_MAX_STEP` / `WORKSPACE_HOSTPATH` overridden per pilot config.

## D6 — Divergence handling mirrors the T3c precedent, and is a finding, not a bug

Watch the pod log for the first ~10-15 minutes of each run for immediate blow-up/NaN before
committing to the full multi-hour wait. If a config diverges at `dt=5e-4`: apply the same
fallback T3c used (`ns.fixed_dt = 2.5e-4`, `max_step` doubled) and re-submit, recording that
this config needed it. If a config is still unstable even at `2.5e-4`: stop, do not attempt a
further speculative fallback — record it as a genuine "unstable at this kinematic range"
finding in the pilot report, not something to route around silently.

## D7 — Deliverables and their test surface

Because this is operator-run (real cluster time), there is no unit-test surface for the actual
CFD execution — the "test" is the pilot itself. What *is* testable and cluster-free:

- A deck-invariance guard (mirrors `tests/test_convergence_deck.py`'s existing
  coarse↔medium↔fine pattern): `base_inputs.3d.fine` must be an exact copy of
  `examples/prelim_sweep/base_inputs.3d.validation` except `amr.n_cell`.
- A schema/provenance pin test for the committed pilot `run_metadata_*.json` files (mirrors
  `tests/test_wing_convergence_fine.py`'s pattern), `skipif` the pilot data doesn't exist yet
  (Session A vs. Session B split, same pattern as `add-wing-fine-grid-convergence`).

## Open questions carried into `tasks.md`

- Exact mechanics of staging `prelim_sweep_fine_pilot/` onto the NFS path the Argo workflow
  mounts (mirrors the existing Z:\ drive → NFS pattern already used for `flapping_wing/` and
  `prelim_sweep/`).
- Whether `amrex.the_arena_init_size` needs adjusting for this deck (T3c used 18-28 GiB on an
  A5000 for the validated-case fine grid; the RunAI cluster's A40s have 48 GB — should have
  headroom, worth confirming on the first submission rather than assuming).
