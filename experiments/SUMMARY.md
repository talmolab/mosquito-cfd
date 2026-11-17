# Surrogate exploration: one-page summary

Branch `explore-surrogate-experiments` (local only, cut from `main` at `80d653a`). Written
2026-11-17 for the lab meeting on 2026-11-24. Each experiment's full report is `report.html` in
its folder; the surrogate recommendation is in
[surrogate-recommendation.md](surrogate-recommendation.md).

## Data used

- **Forces:** `examples/prelim_sweep_fine/dataset.parquet` and `examples/prelim_sweep/dataset.parquet`
  at `80d653a`, re-extracted in #146 (`69d0000`), which includes the #71 hinge fix and the #118
  hinge-referenced moments. 27 configs; the corpus's own 6 holdout configs are the test set
  everywhere.
- **Fields:** fine-corpus plotfiles from the cluster share, second wingbeat only, 558 snapshots
  over 27 configs, each checked for `ns.cfl = 0.6`, `fixed_dt = 5e-4`, grid 256 × 128 × 256 and
  solver hash. The stale `.old.*` run folders were not read.
- **New CFD:** one 6-beat coarse run of `s45_f100_p45` on the local A5000 (E0b). No RunAI jobs.

## Results

| | Result in one sentence | Figure | Slide-ready? |
|---|---|---|---|
| E0 | The second beat is not a repeat of the first: on the fine grid they differ by 5–17% of peak (median over 27 configs), most in `CF_z`, `CF_mx`, `CF_my`. | `e0_periodicity/figures/beat_difference_heatmap.png` | **Yes.** All 27 configs, both grids, no model involved. |
| E0b | Continued to 6 beats, the forces settle: beat 2 is 0.8–2.9% of peak from beat 6, beat 4 under 0.5%. | `e0b_long_run/figures/beat_to_beat_change.png` | **Yes, labelled** "coarse grid, one config". Do not quote it as the fine-grid settling rate. |
| E1 | Track B's held-out error (1.1–1.8% of peak by component, median over configs; 2.5% worst) is inside the grid-convergence band, the coarse-versus-fine difference and the beat-1-to-beat-2 difference for every holdout config and component, on the worst of 5 seeds. | `e1_hover_gate/figures/hover_gate.png` | **Yes, but only with three caveats on the slide.** (1) The grid-convergence band mixes grid and timestep refinement and comes from one config (#133 is open), and the margin is thin: worst-seed normal-peak error 3.2% against 3.7%. (2) The beat-to-beat yardstick is the start-up transient (4–19% of peak); against E0b's settled-beat estimate (beat 2 vs beat 6: 0.8–2.9%) the surrogate error is about equal, not well inside. (3) So say "the surrogate is as accurate as the training data is known", not "within CFD uncertainty". |
| E2 | Leave-one-config-out error is under 3% of peak for every config (RMS over seeds; 3.5% on the worst single seed) and does not cluster at stroke reversal; the one phase feature is a kink at the beat boundary caused by the training data not being periodic. | `e2_residuals/figures/residual_heatmap.png`, `residual_by_phase.png` | **Yes.** 27 leave-one-out fits. |
| E3 | The MLP holds median skill 0.984 with 15 of 21 training configs; at 12 the median is 0.957 but the worst subset is 0.65; designed subsets were no better than random ones; 20 force samples per beat suffice. | `e3_data_efficiency/figures/data_efficiency.png` | **Yes** for the curve. The designed-subset comparison is small (one design each) — say "no evidence designed is better", not "random is better". |
| E4 | A cross-validated Fourier-polynomial ridge model (3,960 coefficients) beats the MLP on holdout skill (0.9991 vs 0.987); 3 phase harmonics lift the MLP to 0.995; frequency barely matters. | `e4_ablations/figures/ablation_arms.png` | **Yes.** The ridge size was chosen inside the training configs, not on holdout. Add that it is reliable only on the full 21 configs: at 18, one of five random subsets fell to skill 0.41. |
| E5 | Lab-frame POD of near-wing velocity has no sharp cut-off (held-out error 16% at 64 modes, 9% at 256), but forces are linearly readable from 16 modes (R² 0.92). | `e5_pod/figures/pod_spectrum_and_error.png` | **Yes.** |
| E5 (wing frame) | For the same fluid at full resolution, a wing-fixed frame reconstructs held-out flow about four times better than the lab frame at equal size: 4.3% against 17.8% at 64 modes. | `e5_pod/figures/pod_matched_region.png` | **Yes.** Both frames are scored on the fluid inside one wing-fixed box; a smoothing control rules out the resample as the cause. Say that the box stops at the wing tip, so the tip vortex outside it is not covered. The earlier 4× figure (`pod_lab_vs_wing_frame.png`, 30 modes against 67) compared different regions and is superseded. |
| E6 | Stock `Mesh_Reduced` fits at most about 18k nodes on the A5000 and, at 216 latent values, reconstructs held-out flow at 16% error against 4.6% for POD. | `e6_mesh_reduced/figures/mesh_reduced_vs_pod.png` | **The memory limit: yes.** The 16% vs 4.6%: **only as "stock, untuned, one seed, 8× block-averaged"** — it is not a verdict on tuned graph encoders. |

## Issue drafts (not filed, nothing fixed)

- [plotfile-markers-lag-header-time-by-two-steps.md](issue-drafts/plotfile-markers-lag-header-time-by-two-steps.md):
  wing-marker positions in a plotfile match the kinematics at t − 2Δt, not at the header time.
- [cluster-manifest-copy-lists-26-configs.md](issue-drafts/cluster-manifest-copy-lists-26-configs.md):
  the manifest copy on the cluster share lacks `s55_f115_p30`; the committed manifest has all 27.

## Observations that are not bugs but affect the corpus

- Runs are 2 beats long and the flow needs about 4 to settle to within 0.5% of peak (E0b, coarse,
  one config).
- The last plotfile of each run is written at `stop_time`. For f* = 0.85 that is not a whole
  number of steps, and the field cache's time check refused it; the final plotfiles of the
  f* = 0.85 and 1.0 runs (start of a third beat) are not in the cache. For f* = 1.15 the run ends
  on step 3478 (phase 0.9999), which is in the cache, 78 steps after the previous snapshot.

## Dropped or not done, and why

- **Quasi-steady model comparison and correction ablation:** out of scope while #141/#133 are
  being fixed in another session.
- **First-beat field snapshots:** not cached; E5 and E6 need only the second beat.
- **Fine-grid 6-beat run:** too large for the local GPU budget; a RunAI job was ruled out.
- **`Mesh_Reduced` at finer resolution, a lighter variant, a convolutional-autoencoder comparator,
  and the `Sequence_Model` time-stepper:** the stock model does not fit beyond 18k nodes, and the
  600-epoch run used the time set aside for a second variant.
- **Arm A (kinematics history) and DoMINO:** need commanded-change runs that do not exist.

## Reproducing

`uv run pytest experiments/tests -q` (46 tests). Each `report.html` regenerates from its
`outputs/` in a few seconds with
`uv run --with marimo marimo export html experiments/<exp>/report.py -o experiments/<exp>/report.html`.
The field cache (about 35 GB) and the 6-beat run folders are not in git. They are kept on the
share at `Z:\users\eberrigan\mosquito-cfd\examples\explore_surrogate_2026-11\` (`field_cache\` and
`e0b_long_run\`); the local cache was deleted on 2026-11-17. To re-run E5 or E6 from the cache,
copy `field_cache\` back to `experiments/_cache/`.
