# T3c handoff — fine-grid 256×128×256 flapping-wing run + 3-grid grading (operator A40)

Tier **T3c** ([#50](https://github.com/talmolab/mosquito-cfd/issues/50)) runs the fine-grid flapping
sim and grades it with the 3-grid Richardson convergence tooling delivered in **Session A** (this
change, `add-wing-fine-grid-convergence`). This is a handoff prompt for the operator who has the
Salk RunAI A40; it states **only the delta** from the existing medium run (T3b) — it does **not**
re-transcribe the full command.

## Prerequisite (from Session A, already committed)

- **Deck:** [`examples/flapping_wing/inputs.3d.convergence_fine`](../../examples/flapping_wing/inputs.3d.convergence_fine)
  — an exact copy of `inputs.3d.convergence_medium` changing **only** `amr.n_cell`
  (`128 64 128` → `256 128 256`) and adding `amrex.the_arena_init_size = 28` (the A40 arena cap).
  `ns.fixed_dt = 5e-4` and `particle_inputs.radius = 1.5` are **held** (guarded by
  `tests/test_convergence_deck.py::test_fine_deck_matches_medium_except_n_cell_and_arena` and
  `test_all_three_decks_share_fixed_dt_and_radius`).
- **3-grid grader:** `mosquito_cfd.benchmarks.wing_convergence.wing_grid_convergence_from_body_forces`
  now accepts `fine_csv` as the third positional parameter (backward-compat: 2-grid when `None`).
- **Triple guard:** `mosquito_cfd.benchmarks.wing_convergence.assert_gradeable_triple` — call this
  before grading to confirm the triple is non-empty, covers the window, and shares the same time grid.

## The run — delta from the medium `t3b-handoff.md`

Start from the flapping-wing [`RESULTS.md` → "Run Commands (Reproducibility)"](../../examples/flapping_wing/RESULTS.md#run-commands-reproducibility)
section (same container, same `mpirun … amr3d.gnu.MPI.CUDA.ex` invocation, same working directory with
`wing.vertex`). Change **only**:

1. **Deck:** swap `inputs.3d.convergence_medium` → **`inputs.3d.convergence_fine`**.
2. **Pin:** unchanged — same `ghcr.io/talmolab/mosquito-cfd:fp64` image at **IAMReX `f93dc794`**
   (grid refinement needs no solver change; FP64 throughout).
3. **⚠ GPU memory:** the deck already sets `amrex.the_arena_init_size = 28` (caps AMReX's arena at
   28 GiB, leaving ~12 GiB headroom on the A40's 40 GB GPU). Before submitting, confirm
   `nvidia-smi` shows adequate free memory. If the run OOMs despite the cap:
   - Do NOT reduce the cap below 28 (that risks MPI/CUDA overhead OOM).
   - Record `oom_blocker = true` in `run_metadata_t3c.json` and stop — document the blocker in
     RESULTS; #50 stays open with a note "H100 required."
4. **⚠ Plotfiles:** the deck sets `amr.plot_int = 100`, so plotfiles are written every 100 steps.
   Write them into a run dir named **`t3c-fine`** (recorded as `plotfile_dir` in metadata, enabling
   LEV at the fine grid). **Before tearing down the ~hours-long job, confirm the `t ≈ 0.5` plotfile
   exists** (e.g. `plt01000` at `dt = 5e-4`, or the nearest `current_time ≈ 0.5`). Without it, the
   fine LEV is absent — note "force-only run, LEV not available for fine grid" in RESULTS if needed.
5. **Provenance:** capture `run_metadata_t3c.json` via `mosquito_cfd.benchmarks.metadata.capture_run_metadata`
   with the **same fields as `run_metadata_t3b.json`** plus the named extra fields:
   `tier = "T3c"`, `grid = "256 128 256"`, `fixed_dt`, `max_step`, `dt_reduced`, `plotfile_dir`.
   `inputs.hash` must be the sha256 of `inputs.3d.convergence_fine` — the T3c schema-pin test
   (`test_run_metadata_t3c_fields`) asserts this.
6. **Commit:** the fine `forces_fine.csv` (29-column IB-particle write-out) + `run_metadata_t3c.json`
   beside coarse/medium. The `test_fine_csv_matches_ib_particle_contract` and
   `test_run_metadata_t3c_fields` tests flip from SKIPPED → PASS on this commit.

## Cost / stability expectations

- **~8× the medium cost.** 256×128×256 has **8× the cells** of 128×64×128 (≈1.05 M → ≈8.4 M,
  a 2×2×2 refinement) and **8× the boxes** at `amr.max_grid_size = 32`, so ≈8× the memory plus
  larger per-step linear solves. The T3b medium run took ~hours on the A40; expect **~2 hr** for
  fine (AMReX scaling observations from T3b). This is an unattended job, not interactive.
- **CFL / dt fallback (design D6).** `dt = 5e-4` is held in the deck. At Δx = 0.03125:
  ```
  CFL ≈ 28 · 5e-4 / 0.03125 ≈ 0.45  -- borderline but stable in principle
  ```
  (medium ≈ 0.22 at Δx = 0.0625; coarse ≈ 0.11 at Δx = 0.125). **If the fine run diverges:**
  - Reduce to `ns.fixed_dt = 2.5e-4` at **run time** (NOT a deck change — baking it in would
    reintroduce temporal confounding).
  - Raise `max_step = 4000` to reach `stop_time = 1.0` at the reduced dt.
  - Confirm plotfiles still land near `t ≈ 0.5` (e.g. `plt02000` at `dt = 2.5e-4`).
  - Record `dt_reduced = true` and `fixed_dt = 2.5e-4` in `run_metadata_t3c.json`.
  - **⚠ `assert_gradeable_triple` will raise `"time-grid"`** if called with the default deck-based
    dt; pass the actual `fixed_dt = 2.5e-4` from metadata, not the deck, when confirming the triple.
  - RESULTS must flag: "Note: fine run used `dt = 2.5e-4` for stability; temporal confounding
    introduced; the medium→fine delta reflects both spatial and temporal refinement; the
    coarse/medium 2-grid comparison (same `dt = 5e-4`) remains temporally isolated."

## Pre-commit sanity check (before committing data)

```python
from mosquito_cfd.benchmarks.wing_convergence import assert_gradeable_triple

assert_gradeable_triple(
    "examples/flapping_wing/forces_t2a_newconv.csv",  # coarse
    "examples/flapping_wing/forces_medium.csv",       # medium
    "examples/flapping_wing/forces_fine.csv",         # fine (new)
    coarse_deck="examples/flapping_wing/inputs.3d.validation",
    medium_deck="examples/flapping_wing/inputs.3d.convergence_medium",
    fine_deck="examples/flapping_wing/inputs.3d.convergence_fine",
)
```

This confirms the triple is non-empty, covers `stop_time = 1.0`, shares the same iStep time grid,
and all three decks carry the same `ns.fixed_dt`. If `dt` was reduced, the time-grid check will
raise — see the fallback procedure above.

## Grading (report-only, no verdict)

```python
from mosquito_cfd.benchmarks.wing_convergence import (
    assert_gradeable_triple,
    wing_grid_convergence_from_body_forces,
)

coarse = "examples/flapping_wing/forces_t2a_newconv.csv"
medium = "examples/flapping_wing/forces_medium.csv"
fine   = "examples/flapping_wing/forces_fine.csv"

assert_gradeable_triple(coarse, medium, fine)
out = wing_grid_convergence_from_body_forces(
    coarse, medium, fine,
    f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0,
)
# out["cf_chord"] and out["cf_normal"] each carry:
#   observed_order, cf_exact_richardson, gci_fine, monotone
#   (IB coupling caveat: cf_exact_richardson is illustrative, not a definitive h→0 limit)
```

Record per-component `observed_order`, `cf_exact_richardson`, `gci_fine`, `monotone` for the RESULTS
section. "Non-monotone" or "negative observed order" are valid, informative outcomes — not failures.

## Scope

T3c **closes** issue [#50](https://github.com/talmolab/mosquito-cfd/issues/50) on merge. The PR body
carries `Closes #50`. No other issues are touched. Pre-merge check:
```bash
git log main..HEAD --format='%B' | grep -Ei '(clos|fix|resolv)[a-z]*:?[[:space:]]+#[0-9]+'
```
must print only `#50`. Any other match is an accidental closing keyword.
