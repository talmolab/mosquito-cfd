# Surrogate-data exploration (lab meeting 2026-11-24)

Exploratory experiments; nothing here is production code. Design:
`docs/superpowers/specs/2026-11-16-surrogate-exploration-design.md`.

| | Experiment | Status | Report |
|---|---|---|---|
| 0 | Environment gate and sizing | done: seed 1234 reproduced exactly; 30 s per fit | [report](step0_environment/report.md) |
| E0 | Beat 1 versus beat 2 | done: the beats differ by 5–17% of peak (fine grid, median); `CF_z` mean drops 14% | [report](e0_periodicity/report.html) |
| E0b | Six beats, coarse grid, centre config | done: forces settle; beat 2 (the training beat) is 0.8–2.9% of peak from beat 6, beat 4 is under 0.5%; first two beats reproduce the corpus run to 3e-14 | [report](e0b_long_run/report.html) |
| E1 | Hover gate | done: Track B error is 1–2% of peak and inside all three yardsticks for every held-out config and component (worst seed) | [report](e1_hover_gate/report.html) |
| E2 | Residual map (leave-one-config-out) | done: no clustering at stroke reversal (share 0.11–0.18 vs 0.20 if uniform); left-out error under 3% of peak everywhere; the one phase feature is a kink at the beat boundary, traced to the CFD not being periodic | [report](e2_residuals/report.html) |
| E3 | Data-efficiency curve | done: about 15 configs suffice for the MLP (skill 0.984); below 12 it depends on which configs; designed subsets no better than random; 20 force samples per beat are enough | [report](e3_data_efficiency/report.html) |
| E4 | Ablations and ridge comparator | done: a cross-validated Fourier-polynomial ridge model beats the MLP (skill 0.9991 vs 0.987) on the full grid; more phase harmonics lift the MLP to 0.995; frequency barely matters | [report](e4_ablations/report.html) |
| E5 | POD of the velocity field | done: held-out near-wing reconstruction error is 16% at 64 modes and 9% at 256; no sharp low-rank cut-off; forces need far fewer modes (linear probe R² 0.92 at 16) | [report](e5_pod/report.html) |
| E6 | Stock `Mesh_Reduced` vs POD | done: trains on the A5000 only up to about 18k nodes; at 216 latent values its held-out error is 16% vs 4.6% for POD (8× block-averaged patch, one seed, untuned) | [report](e6_mesh_reduced/report.html) |
