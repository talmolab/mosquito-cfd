## ADDED Requirements

### Requirement: Fine-grid pilot base deck is deck-invariant except grid resolution

`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` SHALL be an exact copy of the frozen
`examples/prelim_sweep/base_inputs.3d.validation` (the sweep's coarse base deck), changing
**only** `amr.n_cell` (`64 32 64` → `256 128 256`). `ns.fixed_dt`, `particle_inputs.radius`,
and every other key SHALL be identical, so the coarse↔fine difference is isolated to spatial
refinement (the fallback to `ns.fixed_dt = 2.5e-4`, if a config's run diverges, happens as a
per-config runtime override — not a change baked into this shared base deck).

#### Scenario: Fine base deck matches the frozen coarse base deck except n_cell

- **Given** `examples/prelim_sweep/base_inputs.3d.validation` (the frozen coarse base) and
  `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`
- **When** both decks are parsed into `{key: value}` maps (comments stripped, whitespace
  normalized)
- **Then** the symmetric difference of keys is empty, and the only differing value is
  `amr.n_cell` (`"64 32 64"` in the coarse base, `"256 128 256"` in the fine base)

### Requirement: Fine-grid pilot decks are reproducibly generated via the unmodified sweep generator

The 3 pilot decks SHALL be produced by calling the existing, unmodified
`mosquito_cfd.force_surrogate.sweep.generate_sweep()` against the fine base deck and a
pilot-specific output directory — no changes to `sweep.py` itself, and no hand-edited decks.

#### Scenario: Pilot decks are byte-reproducible from the fine base deck and the 3 pilot configs

- **Given** `base_inputs.3d.fine`, the 3 pilot configs (`s55_f115_p45`, `s45_f100_p45`,
  `s35_f085_p45`, each with `pitch_amp_deg=45`), `n_wingbeats=2`, and `dt=5e-4`
- **When** `generate_sweep()` is called twice with identical arguments (aside from the
  caller-supplied timestamp)
- **Then** the two runs produce byte-identical `inputs/inputs.3d.<name>` deck files and an
  identical `sweep_manifest.json` (mirroring the existing byte-reproducibility guarantee
  already proven for the coarse 27-config corpus)

#### Scenario: Pilot max_step matches the existing run-duration formula

- **Given** the 3 pilot configs' `frequency_fstar` values (1.15, 1.00, 0.85), `n_wingbeats=2`,
  and `dt=5e-4`
- **When** `derive_run_duration` computes each config's `max_step`
- **Then** the values are exactly 3478, 4000, and 4706 respectively (`round(n_wingbeats / f* /
  dt)`, the existing, unmodified formula)

### Requirement: Fine-grid pilot artifacts are isolated from the frozen coarse corpus

Nothing generated or submitted for this pilot SHALL write into, modify, or otherwise touch
`examples/prelim_sweep/` (the frozen, byte-identical 27-config coarse corpus) — the same
frozen-artifact guarantee already established elsewhere in this spec for the corpus's raw force
columns (see "Re-normalization preserves surrogate skill (scale-invariance)"), extended here to
a sibling pilot process rather than a re-normalization trigger. All pilot artifacts (base deck,
generated decks, manifests, force CSVs, run metadata, report) SHALL live under a separate
`examples/prelim_sweep_fine_pilot/` directory, and cluster submission SHALL target a
pilot-specific `WORKSPACE_HOSTPATH`, never the coarse corpus's path.

#### Scenario: Pilot output directory and workspace path are statically distinct from the coarse corpus's

- **Given** the pilot generation script's output-directory constant and the pilot's configured
  `WORKSPACE_HOSTPATH`
- **When** each is compared against `examples/prelim_sweep/` and the coarse corpus's own NFS
  hostpath, respectively — as a static check, not one that requires actually running generation
  or submitting a workflow
- **Then** both are confirmed distinct strings/paths before any generation or submission happens

#### Scenario: Coarse corpus is unperturbed by the pilot

- **Given** the frozen `examples/prelim_sweep/` directory's committed contents (decks,
  `sweep_manifest.json`, `dataset.parquet`, `run_metadata.json`) before the pilot is run
- **When** the fine-grid pilot is generated and submitted
- **Then** every file under `examples/prelim_sweep/` is byte-identical to its pre-pilot state
  (checked via `sha256`, mirroring the existing frozen-corpus reproducibility tests) — this is a
  passive, one-time confirmation of the static guarantee above, not a repeatable automated test
  that re-executes generation against the real corpus path on every run

### Requirement: Fine-grid pilot per-config run metadata is committed with provenance

Each attempted pilot config's provenance SHALL be committed once its cluster run completes (or
is abandoned as unstable): `run_metadata_<config-name>.json` with the same schema as
`run_metadata_t3c.json` (git/docker/hardware/timing), committed incrementally per config as it
finishes rather than held until all 3 configs are done.

#### Scenario: Per-config run metadata is committed once its run completes (Session B)

- **Given** a pilot config's cluster run has completed (stable, with or without the fallback)
- **When** `examples/prelim_sweep_fine_pilot/run_metadata_<config-name>.json` is read
- **Then** it has the same required fields as `run_metadata_t3c.json` (`git`, `docker_image`,
  `image_digest`, `timing.wall_time_s`, `timing.timesteps`, `timing.s_per_step`, `fixed_dt`,
  `dt_reduced`) — this scenario is checked (and skipped if not yet true) **per config
  independently**, matching the `add-wing-fine-grid-convergence` Session A/Session B pattern, so
  a partially-complete pilot (e.g. 1 of 3 configs done) still reports 1 pass + 2 skips rather
  than one all-or-nothing result

### Requirement: Fine-grid pilot report documents per-config stability and a cost/go-no-go verdict

A pilot report SHALL document, per attempted config, whether it was stable at `dt=5e-4`, needed
the `2.5e-4` fallback, or was unstable even with the fallback — plus a real (measured, not
merely estimated) cost projection for the full 27-config regeneration and an explicit go/no-go
recommendation. An unstable-even-with-fallback config SHALL be recorded as a genuine finding,
not silently omitted or retried indefinitely, and any partial force-CSV/log artifacts from an
aborted run SHALL be committed as evidence alongside that finding rather than discarded.

#### Scenario: Pilot report is present and covers all attempted configs

- **Given** the pilot has been run (fully or partially, including a config that never
  completes or is found unstable)
- **When** the pilot report is read
- **Then** it lists a stability outcome (`stable_at_5e-4` / `stable_at_2.5e-4_fallback` /
  `unstable`) and a measured wall-time / `s_per_step` for every config that was attempted, and
  a full 27-config cost projection derived from those measurements
