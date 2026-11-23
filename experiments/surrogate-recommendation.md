# Which surrogates suit this problem

Revised 2026-11-17 against experiments E0–E7 on branch `explore-surrogate-experiments`. Each point
is the design's draft point, followed by what the experiments changed. Points no experiment
touched are marked **untested**.

## Short version

1. For periodic hover forces, a kinematics-only regression is enough, and a 3,960-coefficient
   Fourier-polynomial ridge model does better than the current MLP on the full 21-config grid
   (and only there: it is unreliable with fewer configs).
2. The limit on hover-force accuracy is now the training data, not the model: the training beat is
   still 1–5% of peak away from settled flapping (coarse grid, two configs), which is as large as
   the surrogate's error or larger.
3. If a flow latent is needed, start from POD in a wing-fixed frame. For the same fluid at full
   resolution it reconstructs held-out flow about four times better than lab-frame POD at equal
   size (4.3% against 17.8% at 64 modes). The same ridge model that predicts forces also predicts
   the 64 wing-frame coefficients of unseen configs from kinematics alone, giving the near-wing
   velocity field to 8.1% (E7).
4. Stock `Mesh_Reduced` is not a good first encoder here: it trains usefully only up to about 18k
   nodes on a 24 GB GPU and, at equal latent size, reconstructed held-out flow 3.4 times worse
   than POD (stock model, untuned, one seed, 8× block-averaged patch).
5. Whether any flow latent is needed at all is still open. It needs commanded-change runs, which
   do not exist.

## Point by point

### 1. Periodic hover forces: a kinematics-only model is the right tool — **confirmed, and simpler than thought**

- E1: Track B's held-out error is 1.1–1.8% of peak (by component, median over configs), inside all
  three yardsticks (grid-convergence band, coarse-versus-fine difference, beat-1-to-beat-2
  difference) for all 6 holdout configs and all 6 components on the worst of 5 seeds. Two of those
  yardsticks are weak: the grid band is borrowed from one config and the margin is thin (3.2%
  against 3.7%), and the beat-to-beat difference is the start-up transient. Against E0b's
  settled-beat estimate (beat 2 against beat 6: 0.8–2.9% at 45° pitch, 0.8–5.0% at 30°) the
  surrogate error is about equal, not well inside.
- E4: a ridge regression on Fourier (16 harmonics) × polynomial (degree 3) features, with its size
  chosen by cross-validation inside the training configs, reaches holdout skill 0.9991 against the
  the MLP's 0.986–0.991 (5 seeds, median 0.987). The ridge figure is one deterministic fit on one
  split, so it has no range. Giving the MLP 3 phase harmonics lifts it to 0.993–0.996; making it
  larger with no harmonics (256 wide, 5 deep) reaches 0.995–0.997. Phase harmonics and model size
  each close most of the gap, so the shortfall is not missing physics, but this does not say which
  of the two is the cause.
- E3: the ridge model needs the full grid. Median skill over 5 random subsets is 0.9988 at 18
  configs, but one of the five fell to 0.41; it is 0.906 at 15 and 0.29 at 12. The MLP degrades
  more gently (median 0.984 at 15, 0.957 at 12). With fewer than the full 21 configs, keep the MLP.
- E4: frequency carries little information once forces are normalised (dropping it costs 0.017 of
  skill; dropping stroke costs 0.19; dropping pitch drops the model below the baseline).
- Not tested: quasi-steady model plus learned correction. That waits for #141 and #133.

**Recommendation:** keep an MLP as the shipped Track B model, with phase harmonics or more
capacity (the comparison bench decides which); report the ridge model beside it as the reference
a learned model must beat.

### 2. Changing commands: test history dependence with kinematics history first — **untested, but the case for it is stronger**

- E2 found no clustering of error at stroke reversal (share of squared error 0.11–0.18 against
  0.20 if uniform) and under 3% of peak error for every left-out config. There is no sign in the
  periodic data of physics the kinematics-only model cannot express.
- E0 and E0b show the flow has a memory of several beats: beat 2 differs from beat 1 by up to 17%
  of peak (fine grid), and on the coarse grid the change per beat is still 1–3% at beat 3. The
  flow pictures from the two 6-beat runs put the change in the shed wake, not in the vortex
  attached to the wing (seen in a few frames, not measured over the beat). A
  commanded change will excite the same slow transient. That is exactly what a windowed or
  recurrent model on kinematics history is meant to capture, and what a phase-only input cannot.
- The commanded-change configs still do not exist, so arm A itself was not run.

**Recommendation:** unchanged. The first commanded-change runs should include a cold start and a
step change, and should be at least 5 beats long after the change (the 30° pitch run is still
1.6% of peak from settled after 4).

### 3. If a flow latent is needed: start linear, then grid-based — **confirmed, with a frame change**

- E5: lab-frame POD of the near-wing patch has no sharp cut-off. Held-out error is 16% at 64 modes
  and 9% at 256. The forces need far fewer (linear probe R² 0.92 at 16 modes).
- E5 follow-up: in a wing-fixed frame the same energy needs about half the modes (99% in 30
  instead of 67; held-out error at 64 modes 5.8% instead of 14.3%, on a 4× block-averaged grid and
  a smaller region). Much of the lab-frame cost is the wing moving through a fixed grid.
- E5 follow-up 2 (2026-11-17): the comparison repeated on matched regions at full resolution.
  Both frames describe the fluid inside one wing-fixed box (chord ±0.75, span 0 to 3.0, normal
  ±0.875). Held-out error at 64 modes is 4.3% in the wing frame against 17.8% for the lab-frame
  basis scored on the same fluid; 99% of the energy needs 24 modes in the wing frame against 180
  for the lab field cut to the same box. Smoothing the lab field as hard as the wing-frame
  resample can smooth it moves the lab error only to 17.0%, so the resample is not the cause.
  The box stops at the wing tip; a box reaching past the tip needs a wider cached patch.
- E7 (2026-11-17): the E4 ridge model, fitted to the wing-frame POD coefficients of the 21
  training configs, predicts the 6 holdout configs' near-wing velocity field from kinematics and
  phase alone to 8.1% at 64 modes. The floor for this basis is 4.3%, and reusing the nearest
  training snapshot gives 19.2%. In the lab frame the same procedure gives 24% (whole patch).
  This is interpolation inside the 3 × 3 × 3 grid on second-beat data, one deterministic fit.
- Not tested: a convolutional autoencoder or FNO, and any latent dynamics model.

**Recommendation:** make wing-frame POD the baseline latent. Any learned encoder is judged against
it at equal latent size on held-out configs, and should be given the wing pose or work in wing
coordinates. For periodic hover, a learned field model also has to beat the E7 ridge prediction
(8.1%), which needs no encoder at all.

### 4. `Mesh_Reduced` — **measured: feasible only when small, and worse than POD as run**

- E6: the stock model (15 blocks, 128 wide) uses about 0.6 MiB of GPU memory per node. On the
  A5000 it trains at 4.6k nodes with batch 4 and fits 18k nodes at batch 1; 37k nodes ran only by
  spilling out of GPU memory (25 s per step) and 147k ran out of memory.
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
0.55 s per training step (forward and backward, batch 1) here, so stepping the full field with a graph network is not an RL
inner-loop candidate.

## What I would do next, in order

1. Decide whether the corpus needs longer runs (E0b). The 30°-pitch 6-beat run is done: it needs
   5 beats to come under 1% of peak, against 4 for the centre config.
2. Add phase harmonics to Track B and report the ridge comparator (a `/new-feature` change).
3. Generate a few commanded-change runs and run arm A on them.
4. Only if arm A fails: wing-frame POD latent, then a convolutional autoencoder against it.
