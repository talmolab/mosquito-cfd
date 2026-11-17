# Which surrogates suit this problem

Revised 2026-11-17 against experiments E0–E6 on branch `explore-surrogate-experiments`. Each point
is the design's draft point, followed by what the experiments changed. Points no experiment
touched are marked **untested**.

## Short version

1. For periodic hover forces, a kinematics-only regression is enough, and a 3,960-coefficient
   Fourier-polynomial ridge model does better than the current MLP on the full 21-config grid.
2. The limit on hover-force accuracy is now the training data, not the model: the training beat is
   still 1–3% of peak away from settled flapping (coarse grid, one config), which is as large as
   the surrogate's error.
3. If a flow latent is needed, start from POD in a wing-fixed frame. It needs about half the modes
   of lab-frame POD.
4. Stock `Mesh_Reduced` is not a good first encoder here: it reaches only about 18k nodes on a
   24 GB GPU and, at equal latent size, reconstructed held-out flow 3.4 times worse than POD.
5. Whether any flow latent is needed at all is still open. It needs commanded-change runs, which
   do not exist.

## Point by point

### 1. Periodic hover forces: a kinematics-only model is the right tool — **confirmed, and simpler than thought**

- E1: Track B's held-out error is 1.1–1.8% of peak, inside all three yardsticks (grid-convergence
  band, coarse-versus-fine difference, beat-to-beat difference) for all 6 holdout configs and all
  6 components on the worst of 5 seeds.
- E4: a ridge regression on Fourier (16 harmonics) × polynomial (degree 3) features, with its size
  chosen by cross-validation inside the training configs, reaches holdout skill 0.9991 against the
  MLP's 0.987. Giving the MLP 3 phase harmonics lifts it to 0.995. So most of the MLP's remaining
  error is its single-harmonic phase input, not missing physics.
- E3: the ridge model needs the full grid (skill 0.9988 at 18 configs, 0.906 at 15, 0.29 at 12);
  the MLP degrades more gently (0.984 at 15, 0.957 at 12). With fewer than about 18 configs, keep
  the MLP.
- E4: frequency carries little information once forces are normalised (dropping it costs 0.017 of
  skill; dropping stroke costs 0.19; dropping pitch drops the model below the baseline).
- Not tested: quasi-steady model plus learned correction. That waits for #141 and #133.

**Recommendation:** keep the MLP as the shipped Track B model but add phase harmonics; report the
ridge model beside it as the reference a learned model must beat.

### 2. Changing commands: test history dependence with kinematics history first — **untested, but the case for it is stronger**

- E2 found no clustering of error at stroke reversal (share of squared error 0.11–0.18 against
  0.20 if uniform) and under 3% of peak error for every left-out config. There is no sign in the
  periodic data of physics the kinematics-only model cannot express.
- E0 and E0b show the flow has a memory of several beats: beat 2 differs from beat 1 by up to 17%
  of peak (fine grid), and on the coarse grid the change per beat is still 1–2% at beat 3. A
  commanded change will excite the same slow transient. That is exactly what a windowed or
  recurrent model on kinematics history is meant to capture, and what a phase-only input cannot.
- The commanded-change configs still do not exist, so arm A itself was not run.

**Recommendation:** unchanged. The first commanded-change runs should include a cold start and a
step change, and should be at least 4 beats long after the change.

### 3. If a flow latent is needed: start linear, then grid-based — **confirmed, with a frame change**

- E5: lab-frame POD of the near-wing patch has no sharp cut-off. Held-out error is 16% at 64 modes
  and 9% at 256. The forces need far fewer (linear probe R² 0.92 at 16 modes).
- E5 follow-up: in a wing-fixed frame the same energy needs about half the modes (99% in 30
  instead of 67; held-out error at 64 modes 5.8% instead of 14.3%, on a 4× block-averaged grid and
  a smaller region). Much of the lab-frame cost is the wing moving through a fixed grid.
- Not tested: a convolutional autoencoder or FNO, and any latent dynamics model.

**Recommendation:** make wing-frame POD the baseline latent. Any learned encoder is judged against
it at equal latent size on held-out configs.

### 4. `Mesh_Reduced` — **measured: feasible only when small, and worse than POD as run**

- E6: the stock model (15 blocks, 128 wide) uses about 0.6 MiB of GPU memory per node. On the
  A5000 it trains at 4.6k nodes with batch 4, fits 18k nodes at batch 1, and fails beyond that.
  The full-resolution patch is 2.4 million cells.
- At 216 latent values on a 4,608-node graph, after 600 epochs, held-out error is 16% against
  4.6% for POD with 216 modes; it matches POD with about 39 modes. One seed, no tuning, 374
  training snapshots.

**Recommendation:** drop stock `Mesh_Reduced` as the default arm B. If a neural encoder is wanted,
a 3-D convolutional autoencoder on the wing-frame box is the cheaper next experiment.

### 5. DoMINO: lowest priority for the RL goal — **untested**

Nothing here bears on it. The reasons in the draft stand (geometry-to-fields, no state, no
published continuous-motion result, adapter incomplete in #112).

### 6. Still not appropriate: PINN, full-field MeshGraphNet stepping — **untested**

E6's memory measurement adds one data point: message passing on even an 18k-node graph costs
0.55 s per training step here, so stepping the full field with a graph network is not an RL
inner-loop candidate.

## What I would do next, in order

1. Decide whether the corpus needs longer runs (E0b). A 6-beat coarse run of one 30°-pitch config
   (about 7 hours on the A5000) shows the slowest case.
2. Add phase harmonics to Track B and report the ridge comparator (a `/new-feature` change).
3. Generate a few commanded-change runs and run arm A on them.
4. Only if arm A fails: wing-frame POD latent, then a convolutional autoencoder against it.
