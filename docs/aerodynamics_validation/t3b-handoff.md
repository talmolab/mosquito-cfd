# T3b handoff — medium-grid flapping-wing run + grading (operator A40)

Tier **T3b** ([#46](https://github.com/talmolab/mosquito-cfd/issues/46)) runs the medium-grid flapping
sim and grades it with the report-only tooling delivered in **T3a** (OpenSpec change
`add-wing-grid-convergence`). This is a handoff prompt for the operator who has the Salk RunAI A40; it
states **only the delta** from the existing coarse run — it does **not** re-transcribe the full
command.

## Prerequisite (from T3a, already merged)

- Deck: [`examples/flapping_wing/inputs.3d.convergence_medium`](../../examples/flapping_wing/inputs.3d.convergence_medium)
  — an exact copy of the confirmed coarse `inputs.3d.validation` changing **only** `amr.n_cell`
  (`64 32 64` → `128 64 128`); `ns.fixed_dt = 5e-4` and `particle_inputs.radius = 1.5` held (guarded by
  `tests/test_convergence_deck.py`).
- Grader: `mosquito_cfd.benchmarks.wing_convergence.wing_grid_convergence_from_body_forces` (report-only
  2-grid GCI band, p = 1..2) + `mosquito_cfd.benchmarks.lev` (vorticity / Q-criterion).

## The run — delta from the coarse `Run Commands (Reproducibility)`

Start from the flapping-wing [`RESULTS.md` → "Run Commands (Reproducibility)"](../../examples/flapping_wing/RESULTS.md#run-commands-reproducibility)
section (same container, same `mpirun … amr3d.gnu.MPI.CUDA.ex` invocation, same working directory with
`wing.vertex`). Change **only**:

1. **Deck:** swap `inputs.3d.validation` → **`inputs.3d.convergence_medium`**.
2. **Pin:** unchanged — same `ghcr.io/talmolab/mosquito-cfd:fp64` image at **IAMReX `f93dc794`** (grid
   refinement needs no solver change; FP64 throughout).
3. **⚠ Plotfiles — DROP the `amr.plot_int=-1 amr.check_int=-1` overrides** from the RESULTS Run-Commands
   line. Those overrides suppress *all* plotfiles, but the **LEV half of T3b needs the `t ≈ 0.5` velocity
   field**. The medium deck sets `amr.plot_int = 100`, so simply omitting the `-1` override writes plotfiles;
   write them into a run dir named **`t3b-medium`** (recorded as `plotfile_dir` in the metadata, so the LEV
   test can find them — the coarse side is the existing `t2a-newconv4`). **Before tearing down the ~hours-long
   job, confirm the `t ≈ 0.5` plotfile exists** (`plt01000` at the held `dt = 5e-4`, or the plt nearest
   `current_time ≈ 0.5`). If you must reduce `dt` for stability (design D4), reduce it only to a value that
   **keeps a plotfile landing exactly on `t = 0.5`** (raise `amr.plot_int` proportionally), and record
   `fixed_dt`/`max_step`/`dt_reduced` in the metadata.
4. **Provenance:** capture `run_metadata_t3b.json` via `mosquito_cfd.benchmarks.metadata.capture_run_metadata`
   (image digest, IAMReX commit `f93dc794`, **inputs hash of `inputs.3d.convergence_medium`**, git SHA,
   hardware, timing, plus the named `extra` fields `fixed_dt`/`max_step`/`dt_reduced`/`plotfile_dir`) — the
   same helper T2a used for `run_metadata_t2a.json`.
5. **Commit** the medium `forces_medium.csv` (the 29-column IB-particle write-out) + `run_metadata_t3b.json`.

## Cost / stability expectations

- **~8× the coarse cost.** 128×64×128 has **8× the cells** of 64×32×64 (≈0.13 M → ≈1.05 M, a 2×2×2
  refinement) and **8× the boxes** at `amr.max_grid_size = 32` (4 → 32), so ≈8× the memory plus larger
  per-step linear solves — expect an **hours-long** wall time (the coarse 2000-step run was ~minutes).
  The A40 (48 GB) has ample headroom at this size; it is an unattended job, not interactive.
- **CFL / dt fallback (design D4).** dt is **held** at `5e-4` in the deck so the temporal error is
  identical to the coarse run (isolating the spatial + IB-regularization refinement). At Δx = 0.0625 the
  estimated `CFL ≈ 28·5e-4/0.0625 ≈ 0.22 < 0.3` (same peak `u_max ≈ 28` both grids; coarse ≈ 0.11), so
  the medium run should be stable at the held dt. **If it is not**, the operator may reduce dt at
  run-time — record that reduction in `run_metadata_t3b.json`; it is a **run-time fallback, not a deck
  change** (baking a smaller dt into the deck would reintroduce the temporal confounding T3a's
  deck-invariance test forbids).

## Grading (report-only)

- Feed the committed coarse `forces_t2a_newconv.csv` and medium `forces_medium.csv` to
  `wing_grid_convergence_from_body_forces(coarse_csv, medium_csv, f_star=1.0, phi_amp_deg=70.0,
  pitch_amp_deg=45.0)` → per-component `relative_change` + `gci_p1`/`gci_p2` for peak
  `CF_chord`/`CF_normal`. **Report** these — there is no pass bar and no tolerance to loosen; `gci_p1`
  is the reported band edge, **not** a rigorous upper bound. "Not converged at coarse" is a valid,
  informative outcome (feeds #40).
  - **Before grading, confirm both CSVs are non-empty and cover the same physical window**
    (`stop_time = 1.0`). The grader compares each CSV's independent window-max peak, so it will
    *silently* return a plausible number if you accidentally pair the wrong two runs or a truncated
    write-out; and a header-only (0-row) CSV surfaces a low-level `ValueError` from the reused
    reconstruction, not a self-describing one — the T3b `assert_gradeable_pair` guard enforces this
    (non-empty + `max(time)≈1.0` + matching unique-`iStep` time grids + deck `fixed_dt` equality).
- LEV (the T3b wiring): at **mid-stroke `t ≈ 0.5`** (the `plt01000`-phase plotfile, max stroke velocity —
  the most LEV-discriminating phase; **not** `t = 0.25` stroke reversal), extract the velocity field by
  **reusing `mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box`** (verified: wing plotfiles carry
  all six `('boxlib', …)` fields it needs) over a **wing near-field box derived from the plotfile's
  `particle_position_*` bbox + margin**, pass `u,v,w` + per-axis `dx` to `lev.vorticity_magnitude` /
  `lev.q_criterion` (medium is isotropic Δx = 0.0625), and **report** the resolution-fair `q_pos_vol`
  (integrated positive Q) coarse-vs-medium contrast (peak Q is resolution-biased — secondary) — a reported
  present/absent reading, **not** a gate.
- Add the RESULTS convergence section + a reproducibility guard (the T2b
  `tests/test_results_reproducibility.py` pattern: recompute the reported numbers from the committed
  coarse + medium CSVs).

## Scope

T3b **advances** Tier T4 (#40) — #40 stays open. T3b closes the T3 EPIC (#46) once the graded run +
RESULTS land; the fine 256³ grid and the true observed-order (3-grid) verdict remain out of scope
(H100/grant).
