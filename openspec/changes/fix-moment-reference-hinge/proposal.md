# Correct the moment reference point to the wing hinge

## Why

`CF_mx/CF_my/CF_mz` are computed about `kernel.location` — for every flapping-wing deck the
wing's **mid-span** point `(4, 2, 4)`, not the hinge `(4, 0.5, 4)`. The origin is *inherited*
from the immersed-boundary particle's own position, not chosen (issue #108).

This is not our convention diverging from a citation — it diverges from **both** of van Veen's
frames. §2.4 defines the wing frame as "a right-handed coordinate frame with the origin at the wing
hinge location" and the world frame as "a right-handed world reference frame with its origin at the
root of the wing". Neither is at mid-span.

The decisive evidence is that **the repository has documented a hinge origin all along**:
`docs/coordinate-convention.md`, the project's mandated canonical frame page, already states
"Right-handed, origin at the wing hinge", sourced to van Veen et al. (2022) §2.4. That
page has `## Axes`, `## Kinematic angles`, `## Forces` and `## Simulation deck mapping` — and **no
`## Moments` section**. The canonical page declared a hinge origin, the forces section was written,
moments were never covered, and the extractor quietly inherited the particle origin. Meanwhile
`normalization.py`'s `MomentCoefficients` docstring calls the reference "the body center".

The arithmetic was never wrong — `M = Σ (r − P) × F` about `P = kernel.location` is a valid
moment. What is wrong is the choice of `P`, its documentation, and its divergence from the frame
the rest of the repo already claims.

Four verified facts set the scope:

1. **Both corpora are affected.** All 27 coarse and all 27 fine decks carry identical
   `particle_inputs.y = 2.0` / `hinge_y = 0.5` geometry, so the displacement is exactly
   `(0, 1.5, 0)` in every committed run. Confirmed against raw cluster output, not just the deck:
   the `X,Y,Z` columns of `IB_Particle_1.csv` are a constant `(4, 2, 4)` for every row.
2. **`M_y` is mathematically invariant; `M_x` and `M_z` are not.** Because `d_x = d_z = 0`, the
   y-component of `d × F` is identically zero: `ΔM = (0, 1.5, 0) × F = (1.5·F_z, 0, −1.5·F_x)`.
   (Stated as `d_x = d_z = 0` rather than "spanwise" deliberately — `y` is the span axis only in
   the rest pose, and the moment about the *instantaneous* span axis is not invariant under
   `Rz(φ)`.)

   The correction is large for the other two. All figures below are over **settled beats**
   (`wingbeat ≥ 1`), the window the trainer's converged-beat filter uses and the window every
   other per-config statistic in this repo uses:

   | | `rms(ΔM_x)/rms(M_x)` | `rms(ΔM_z)/rms(M_z)` | per-config cycle-mean corr, `M_x` |
   |---|---|---|---|
   | fine | 482% | 279% | 0.714 |
   | coarse | 485% | 259% | 0.788 |

   Reproduce with `rms(1.5·F_z)/rms(M_x)` and `rms(1.5·F_x)/rms(M_z)` on the committed parquet.
   (Over *all* rows, including the startup transient, the fine figures are 503% / 319% / 0.648 —
   an earlier draft quoted those without stating the window.) Corrected `CF_mx` is a materially
   different learning target on either window.
3. **The correction is exact and executable.** Per-marker force and moment are the same marker
   sum, cleared and accumulated in lockstep across the `loop_ns` multidirect sub-iterations
   (`DiffusedIB.cpp:363-364, 393-394, 866-871` at pinned commit `f93dc794`), so the parallel-axis
   identity holds through the accumulation. All 27 raw CSVs are present on `Z:` for **both**
   corpora, verified usable (`iStep` present, row counts match each manifest's `max_step`).
4. **Nothing guards this today.** The one committed test that reconciles coefficients against raw
   columns (`tests/test_force_surrogate_scale_invariance.py:111-113`) checks `CF_x`, `CF_z` and
   `CF_my` — precisely the three quantities invariant under this fix. `CF_mx` and `CF_mz` have no
   numeric assertion against either corpus, so the defect was undetectable and a regression would
   remain so.

This blocks #110 (train the surrogate on the fine corpus): `CF_mx` currently carries the repo's
best evidence of genuine between-config skill (config-resolved R² 0.993 on the coarse corpus), and
that number will not survive the correction. Training first would commit a `surrogate.pt`,
`metrics.json` and evidence figure with two knowingly wrong-referenced targets.

## What Changes

- **BREAKING — moment reference point becomes the wing hinge**, applied at extraction via the
  parallel-axis shift `M_hinge = M_origin + (r_origin − r_hinge) × F`, with the offset **derived
  per configuration** from the CSV's own `X,Y,Z` and the deck's `hinge_*`, never hardcoded.
  Corpora extracted before this change carry different `CF_mx`/`CF_mz`.
- **`build_dataset` gains a deck source.** The extractor currently never opens a deck and does not
  even read `X,Y,Z`. Decks are located via the manifest's existing `input_file` entry resolved
  against the manifest's directory, so no new CLI flag is needed; the hinge is read with the
  existing ParmParse-aware `read_deck_value`. `X,Y,Z` become required CSV columns.
- **Both `dataset.parquet` files are re-extracted** from the raw CSVs on `Z:`, so the two corpora
  stay on one convention — the coarse-vs-fine comparison places them side by side and would
  otherwise be invalid.
- **The coarse surrogate is retrained and its evidence figure regenerated**, so no committed
  artifact disagrees with the code that produces it.
- **A CI regression guard is added** asserting `CF_mx == (Mx + a·Fz)/m_ref` and
  `CF_mz == (Mz − a·Fx)/m_ref` against both committed parquets, and that `CF_mx` is *not* equal to
  `Mx/m_ref` so the check cannot pass vacuously.
- **The reference point is documented canonically** — a `## Moments` section in
  `docs/coordinate-convention.md`, with everything else cross-referencing it.
- **The frame is recorded in each corpus's `run_metadata.json`**, not in `dataset.units.json`.
- **Raw `Mx/My/Mz` keep their as-written IAMReX values**; only derived `CF_m*` move.

### What does NOT change

- **The evidence figure's panel set stays frozen** (`CF_x`, `CF_z`, `CF_my`), deliberately, so the
  figure cannot cherry-pick whichever moment scores best per corpus. The spec's *stated
  justification* for the freeze is corrected — it currently asserts `CF_my` is "the only moment
  with genuine configuration-to-configuration signal", which is already false today — but the
  decision itself is unchanged.
- **Forces** (`CF_x/CF_y/CF_z`) are untouched.
- **No CFD re-run.** Analysis only; solver output is authoritative and unmodified.
- **The axes are not rotated.** These remain *lab-frame* components, now about the hinge origin.

### Corrections to an earlier draft of this proposal

- "The headline panel is numerically unchanged" was **wrong**. The surrogate is a single
  shared-trunk multi-output network (`train.py:404-409`, `out_features=6`), so retraining against
  changed `CF_mx`/`CF_mz` targets perturbs every prediction, `CF_my` included; and the caption
  renders the off-panel `CF_mx`/`CF_mz` R² onto the PNG. The `CF_my` *dataset column* is invariant;
  the *panel* is not.
- "`M_y` invariance catches a reversed cross product" was **wrong**. `d × F` and `F × d` both give
  exactly zero in the y-component. The order is pinned by the `±a·F_z`/`∓a·F_x` clause instead.
- An instruction to export `GIT_DIR`/`GIT_WORK_TREE` before retraining was **wrong and unsafe**.
  `metadata.py:26-66` already translates a Windows worktree pointer for WSL and retries
  automatically (landed in `7998f98`, #78, after the bad committed artifact was written). A manual
  export pointing at `.git` rather than `.git/worktrees/<name>` would silently record *main's*
  HEAD and pre-empt the correct retry.

## Impact

- **Affected specs**: `force-surrogate` (hinge reference, derived-offset validation, shift helper,
  moment normalization, dataset extraction, dataset build provenance, headline moment axis);
  `coordinate-convention` (canonical moment reference point)
- **Affected code**: `force_surrogate/dataset.py`, `force_surrogate/normalization.py`,
  `force_surrogate/acceptance_gate.py` (calls `build_dataset`), `scripts/extract_forces.py`
  (calls `build_dataset`), `force_surrogate/evidence_figure.py` (comments asserting a superseded
  per-corpus moment ranking)
- **Affected artifacts**: both `dataset.parquet`; both corpus `run_metadata.json`; both
  `sweep_provenance.json` regeneration records; `examples/prelim_sweep/surrogate/*`;
  `examples/prelim_sweep/figures/*` — approximately **26 MiB** of regenerated binaries
- **Affected docs**: `docs/coordinate-convention.md` (new `## Moments` section),
  `examples/prelim_sweep/README.md` (moment-ranking passage at `:327-338`, the config-mean range at
  `:249`, the latency disclosure at `:358`, and the schema note at `:179`),
  `docs/force_surrogate/roadmap.md:190-193`, `docs/CHANGELOG.md`
- **Affected tests**: named up front in tasks.md task 0 — any test outside that list needing an
  edit halts the change
- **Unblocks**: #110 (fine-corpus surrogate training)

### Deliberately out of scope

- **#114** — the first real coarse-vs-fine comparison figures. Blocked on this change and #110.
- **#115** — the live force-surrogate spec restates result numbers stale against even the *current*
  coarse artifacts (`CF_y −3.61` when it is `+0.811`, `~310×` when it is `468×`, `R²≈0.98` when it
  is `0.999`). Pre-existing drift, not caused here; folding it in would enlarge this review surface
  for no benefit.
- **#116** — the evidence figure prints off-panel `CF_mx`/`CF_mz` R² onto the PNG that
  `evidence_figure_metrics.json` does not record. Pre-existing, but this change makes those two
  numbers the ones a reader will look for.
- **#102** (Git LFS) — not a blocker for a correctness fix, but worth deciding before #110 adds the
  next round of committed binaries.

### Delivery

Three PRs, because a cross-product sign convention must not be reviewed alongside 26 MiB of diffs
GitHub cannot render:

1. **PR1** — pure `shift_moment_reference` helper + tests + docstring/canonical docs. No binaries.
2. **PR2** — wire into extraction, add the regression guard, re-extract both corpora. The guard
   lands *before* the re-extraction so the stale state shows red rather than silently green.
3. **PR3** — retrain the coarse surrogate, regenerate the figure, refresh prose.
