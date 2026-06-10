# Force-surrogate kinematic sweep (`prelim_sweep`)

A reproducible corpus of **27 IAMReX input decks** over the *Aedes aegypti*-anchored kinematic
grid, generated for the Track B force-only surrogate (see
[`docs/force_surrogate/roadmap.md`](../../docs/force_surrogate/roadmap.md), row #2). These decks are
the input side of the eventual predicted-vs-CFD evidence figure; PR3 runs them on the cluster, PR4
extracts forces, PR5 trains, PR6 plots.

**Force-only (CC-6):** every deck sets `amr.plot_int = -1` — no field plotfiles (forces come from
the IB-particle CSV), which sidesteps the velocity-field-in-plotfiles issue entirely.

## What's here

| File | Contents |
|---|---|
| `inputs/inputs.3d.s{φ}_f{f*×100}_p{α}` | 27 decks, one per grid point (e.g. `inputs.3d.s35_f085_p30`). |
| `sweep_manifest.json` | Deterministic config description: per-config kinematics, `nu_star`, `reynolds`, `max_step`/`stop_time`, `plot_int`, train/holdout `split`; plus grid levels and the holdout seed. |
| `sweep_manifest.units.json` | Units of the measured columns (dimensionless / deg). |
| `sweep_provenance.json` | git commit, base-inputs SHA256, and the caller-supplied timestamp (kept **separate** from the manifest so the non-reproducible git SHA cannot defeat byte-identity). |
| `generate_sweep.py` | Thin driver; all logic lives in `mosquito_cfd.force_surrogate.sweep`. |

## The grid

Levels and their *Aedes* grounding (Bomphrey et al. 2017, *Nature* 544:92–95) are the
source-attributed `AEDES_*` constants in
[`force_surrogate/constants.py`](../../src/mosquito_cfd/force_surrogate/constants.py); per-config
Reynolds numbers are in `sweep_manifest.json` — they are not re-tabulated here to avoid drift.
Summary: stroke amplitude φ ∈ {35, 45, 55}°, dimensionless frequency f\* ∈ {0.85, 1.0, 1.15}
(≈ 610/717/824 Hz), pitch amplitude α ∈ {30, 45, 60}° → 27 configs.

> **Note on the kinematics.** The validated demo (`examples/flapping_wing/`) uses a **70°** stroke —
> a generic large-amplitude case, *not* the mosquito value. This sweep deliberately re-anchors on the
> *Aedes* stroke (≈39°, Bomphrey 2017), which the {35, 45, 55}° levels bracket.

## Reynolds policy (CC-7: ν\* held fixed)

Viscosity `ns.vel_visc_coef = ν* = 0.115` is **held fixed** across all 27 configs, so the Reynolds
number (≈ 43–90) varies as a deterministic function of the swept φ and f\*. This keeps the
(φ, f\*, α) → force map well-posed (Re is a function of the inputs, not a hidden variable) and keeps
every deck differing from the validated base in only the swept/derived keys. Per-config Re is
recorded in the manifest. (See `design.md` D1 of the `add-force-surrogate-sweep-config` change.)

## Run duration

Each deck covers **2 whole wingbeats**: `stop_time = 2 / f*`, `max_step = round(stop_time / 5e-4)`
(the validated `dt`). So low-frequency configs run longer in steps, guaranteeing whole periodic
cycles for force extraction.

## Held-out configs (CC-4)

6 configs (seeded, drawn from grid **non-corners** so the figure measures interpolation) are labelled
`split = "holdout"` in the manifest. The label only excludes them from *training* — all 27 are still
generated and run, since the held-out set is the CFD ground truth.

## Regenerating

```bash
uv run python examples/prelim_sweep/generate_sweep.py   # run from the repo root
```

Regeneration is **byte-identical** (fixed seed + fixed caller timestamp); the test
`test_committed_sweep_matches_regeneration` enforces this.
